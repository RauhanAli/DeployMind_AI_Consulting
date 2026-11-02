"""Controlled agent orchestration on LangGraph.

Each agent is a small compiled graph:

    gather_context --> generate --> validate --(ok)--> END
                          ^             |
                          +--(retry)----+   (bounded by max_attempts)

- gather_context executes the agent's *deterministic tool plan* through the ToolRegistry, which only allows
  tools on the agent's allowlist. Tools receive the caller's organisation id, so they are tenant-scoped by
  construction. The LLM never chooses tools that have side effects.
- generate calls the configured LLM provider with a typed output schema (structured output).
- validate applies business validation; failures are fed back for a bounded retry.
Every LLM call is recorded in model_usage (tokens, cost, latency, success) and wrapped in a tracing span.
"""

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypedDict, TypeVar

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.providers.base import LLMResult, ProviderError
from app.ai.registry import get_llm, record_usage
from app.core.tracing import current_trace_id, span

log = logging.getLogger("deploymind.agents")

I = TypeVar("I", bound=BaseModel)  # noqa: E741  (agent Input/Output type variables)
O = TypeVar("O", bound=BaseModel)  # noqa: E741

ToolFn = Callable[..., Any]
TOOLS: dict[str, ToolFn] = {}


def tool(name: str):
    def deco(fn: ToolFn) -> ToolFn:
        TOOLS[name] = fn
        return fn
    return deco


class AgentError(Exception):
    pass


@dataclass
class AgentSpec(Generic[I, O]):
    name: str
    responsibility: str
    input_schema: type[I]
    output_schema: type[O]
    system_prompt: str
    build_prompt: Callable[[I, dict], str]
    mock: Callable[[I, dict], O]
    tools: list[str] = field(default_factory=list)
    plan_tools: Callable[[I], list[tuple[str, dict]]] = lambda _i: []
    validate: Callable[[I, O], list[str]] = lambda _i, _o: []
    temperature: float = 0.2
    max_tokens: int = 3000
    max_attempts: int = 2


@dataclass
class AgentOutcome(Generic[O]):
    output: O
    provider: str
    model: str
    is_mock: bool
    attempts: int
    tool_calls: list[dict]
    input_tokens: int
    output_tokens: int
    latency_ms: int
    trace_id: str


class _State(TypedDict, total=False):
    input: Any
    context: dict
    tool_calls: list
    output: Any
    errors: list
    attempts: int
    results: list


AGENT_REGISTRY: dict[str, AgentSpec] = {}


def register(spec: AgentSpec) -> AgentSpec:
    AGENT_REGISTRY[spec.name] = spec
    return spec


class AgentRunner:
    def __init__(self, db: Session, org_id: uuid.UUID, *, provider: str | None = None,
                 project_id: uuid.UUID | None = None, app_id: uuid.UUID | None = None):
        self.db = db
        self.org_id = org_id
        self.provider_name = provider
        self.project_id = project_id
        self.app_id = app_id

    def call_tool(self, spec: AgentSpec, name: str, args: dict) -> Any:
        import app.ai.tools  # noqa: F401  (registers built-in tools for every entry point: API, worker, seed)

        if name not in spec.tools:
            raise AgentError(f"Agent '{spec.name}' is not authorised to use tool '{name}'")
        fn = TOOLS.get(name)
        if fn is None:
            raise AgentError(f"Tool '{name}' is not registered")
        with span(f"tool.{name}", agent=spec.name):
            return fn(self.db, self.org_id, **args)

    def _graph(self, spec: AgentSpec):
        llm = get_llm(self.provider_name)

        def gather_context(state: _State) -> _State:
            ctx, calls = {}, []
            for name, args in spec.plan_tools(state["input"]):
                t0 = time.perf_counter()
                try:
                    ctx[name] = self.call_tool(spec, name, args)
                    calls.append({"tool": name, "args": args, "ok": True,
                                  "ms": int((time.perf_counter() - t0) * 1000)})
                except AgentError:
                    raise
                except Exception as exc:  # tool failure is recorded and surfaced, never swallowed
                    calls.append({"tool": name, "args": args, "ok": False, "error": str(exc)[:300]})
                    raise AgentError(f"Tool '{name}' failed: {exc}") from exc
            return {"context": ctx, "tool_calls": calls, "attempts": 0, "results": [], "errors": []}

        def generate(state: _State) -> _State:
            inp, ctx = state["input"], state["context"]
            prompt = spec.build_prompt(inp, ctx)
            if state.get("errors"):
                prompt += "\n\nYour previous answer failed validation. Fix these problems:\n- " + "\n- ".join(state["errors"])
            attempts = state.get("attempts", 0) + 1
            with span(f"agent.{spec.name}.generate", attempt=attempts, provider=llm.name):
                try:
                    res: LLMResult = llm.structured(
                        system=spec.system_prompt, prompt=prompt, schema=spec.output_schema,
                        temperature=spec.temperature, max_tokens=spec.max_tokens, mock=lambda: spec.mock(inp, ctx),
                    )
                except (ProviderError, ValueError) as exc:
                    record_usage(self.db, org_id=self.org_id, agent=spec.name, provider=llm.name,
                                 model=getattr(llm, "default_model", "unknown"), success=False,
                                 project_id=self.project_id, app_id=self.app_id, is_mock=llm.is_mock)
                    raise AgentError(f"{spec.name} generation failed: {exc}") from exc
            record_usage(self.db, org_id=self.org_id, agent=spec.name, result=res,
                         project_id=self.project_id, app_id=self.app_id)
            return {"output": res.parsed, "attempts": attempts, "results": [*state.get("results", []), res]}

        def validate(state: _State) -> _State:
            return {"errors": spec.validate(state["input"], state["output"])}

        def route(state: _State) -> str:
            if not state.get("errors"):
                return "done"
            if state.get("attempts", 0) >= spec.max_attempts:
                return "fail"
            return "retry"

        def fail(state: _State) -> _State:
            raise AgentError(f"{spec.name} output failed validation: {state.get('errors')}")

        g = StateGraph(_State)
        g.add_node("gather_context", gather_context)
        g.add_node("generate", generate)
        g.add_node("validate", validate)
        g.add_node("fail", fail)
        g.add_edge(START, "gather_context")
        g.add_edge("gather_context", "generate")
        g.add_edge("generate", "validate")
        g.add_conditional_edges("validate", route, {"done": END, "retry": "generate", "fail": "fail"})
        g.add_edge("fail", END)
        return g.compile()

    def run(self, spec: AgentSpec[I, O], inp: I) -> AgentOutcome[O]:
        if not isinstance(inp, spec.input_schema):
            inp = spec.input_schema.model_validate(inp)
        with span(f"agent.{spec.name}", org_id=str(self.org_id)):
            t0 = time.perf_counter()
            log.info("agent_start", extra={"agent": spec.name, "org_id": str(self.org_id)})
            try:
                state = self._graph(spec).invoke({"input": inp})
            except ProviderError as exc:
                raise AgentError(str(exc)) from exc
            results: list[LLMResult] = state["results"]
            last = results[-1]
            outcome = AgentOutcome(
                output=state["output"], provider=last.provider, model=last.model, is_mock=last.is_mock,
                attempts=state["attempts"], tool_calls=state["tool_calls"],
                input_tokens=sum(r.input_tokens for r in results), output_tokens=sum(r.output_tokens for r in results),
                latency_ms=int((time.perf_counter() - t0) * 1000), trace_id=current_trace_id(),
            )
            log.info("agent_done", extra={"agent": spec.name, "attempts": outcome.attempts,
                                          "tokens": outcome.input_tokens + outcome.output_tokens,
                                          "latency_ms": outcome.latency_ms, "mock": outcome.is_mock})
            return outcome


def provenance(agent: str, outcome: AgentOutcome) -> dict:
    return {"agent": agent, "provider": outcome.provider, "model": outcome.model, "is_mock": outcome.is_mock,
            "attempts": outcome.attempts, "tool_calls": outcome.tool_calls, "trace_id": outcome.trace_id,
            "input_tokens": outcome.input_tokens, "output_tokens": outcome.output_tokens,
            "disclaimer": "AI-generated draft. Requires review by an authorised engineer before use."}
