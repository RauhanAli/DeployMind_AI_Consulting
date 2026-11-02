"""Incident Analysis Agent and Evaluation (judge) Agent."""

import json
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from app.ai.agents.framework import AgentSpec, register
from app.rag.text import support_ratio, token_f1


# ------------------------------------------------------------------ Incident Analysis Agent
class IncidentAgentIn(BaseModel):
    title: str
    description: str
    severity: str
    detected_at: datetime
    app_id: str | None = None
    environment: str | None = None


class IncidentAnalysis(BaseModel):
    summary: str
    likely_causes: list[str]
    evidence: list[str]
    suggested_actions: list[str]
    customer_update_draft: str


def _incident_tools(i: IncidentAgentIn) -> list[tuple[str, dict]]:
    end = i.detected_at + timedelta(minutes=30)
    start = i.detected_at - timedelta(hours=2)
    return [("telemetry_window", {"app_id": i.app_id, "start": start.isoformat(), "end": end.isoformat()}),
            ("recent_deployments", {"app_id": i.app_id, "before": end.isoformat()})]


def _incident_prompt(i: IncidentAgentIn, ctx: dict) -> str:
    return (
        "Analyse this production incident for an AI application. Use only the evidence provided; if the evidence is "
        "inconclusive say so. Draft a short, non-technical customer update without speculating on root cause.\n"
        f"Incident: {json.dumps(i.model_dump(mode='json'))}\n"
        f"Telemetry around detection: {json.dumps(ctx.get('telemetry_window'))}\n"
        f"Recent deployments: {json.dumps(ctx.get('recent_deployments'))}"
    )


def _incident_mock(i: IncidentAgentIn, ctx: dict) -> IncidentAnalysis:
    t = ctx.get("telemetry_window") or {}
    deps = ctx.get("recent_deployments") or []
    causes, evidence, actions = [], [], []
    if t.get("requests"):
        evidence.append(f"{t['requests']} requests in window, error rate {t['error_rate']:.1%}, "
                        f"P95 latency {t['p95_latency_ms']} ms")
    for e in t.get("top_errors", []):
        evidence.append(f"Error '{e['error']}' occurred {e['count']} times")
    if deps:
        d = deps[0]
        evidence.append(f"Deployment {d['version']} to {d['environment']} at {d['created_at']} ({d['status']})")
        causes.append(f"Change introduced by deployment {d['version']} shortly before detection")
        actions.append(f"Compare {d['version']} with the previous release; roll back if errors correlate")
    if t.get("error_rate", 0) > 0.05:
        causes.append("Elevated error rate from a dependency (LLM provider or retrieval database)")
        actions.append("Check provider status and connection-pool saturation; enable fallback model if configured")
    if t.get("p95_latency_ms", 0) > 3000:
        causes.append("Latency regression, possibly retrieval or provider-side slowdown")
        actions.append("Inspect retrieval timings and HNSW index health; review recent configuration changes")
    if not causes:
        causes.append("Evidence is inconclusive from telemetry alone")
        actions.append("Collect logs for affected requests and reproduce in staging")
    actions.append("Post a customer update and schedule a post-incident review")
    return IncidentAnalysis(
        summary=f"{i.severity.upper()} incident '{i.title}'. {len(evidence)} evidence item(s) gathered from telemetry and "
                "deployment history.",
        likely_causes=causes, evidence=evidence, suggested_actions=actions,
        customer_update_draft=(f"We are investigating an issue affecting {i.environment or 'the service'}: {i.title}. "
                               "Our engineers are actively working on it and we will share another update within "
                               "60 minutes."),
    )


INCIDENT_AGENT = register(AgentSpec(
    name="incident_analysis_agent",
    responsibility="Correlate telemetry and deployments to suggest causes and actions (advisory only)",
    input_schema=IncidentAgentIn, output_schema=IncidentAnalysis,
    system_prompt=("You are an SRE assisting with incident response. Be evidence-led and concise. You suggest; "
                   "humans decide and act."),
    build_prompt=_incident_prompt, mock=_incident_mock,
    tools=["telemetry_window", "recent_deployments"], plan_tools=_incident_tools,
))


# ------------------------------------------------------------------ Evaluation Agent (LLM-as-judge)
class JudgeIn(BaseModel):
    question: str
    expected_answer: str
    answer: str
    context: list[str]


class JudgeOut(BaseModel):
    correctness: float = Field(ge=0, le=1)
    faithfulness: float = Field(ge=0, le=1)
    context_relevance: float = Field(ge=0, le=1)
    rationale: str


def _judge_prompt(i: JudgeIn, _ctx: dict) -> str:
    return (
        "Grade the answer. correctness: agreement with the expected answer. faithfulness: every claim supported by "
        "the context. context_relevance: how relevant the retrieved context is to the question. Scores 0..1.\n"
        f"Question: {i.question}\nExpected: {i.expected_answer}\nAnswer: {i.answer}\n"
        f"Context:\n" + "\n---\n".join(i.context[:6])
    )


def _judge_mock(i: JudgeIn, _ctx: dict) -> JudgeOut:
    ctx = " ".join(i.context)
    return JudgeOut(
        correctness=round(token_f1(i.answer, i.expected_answer), 3) if i.expected_answer else 0.0,
        faithfulness=round(support_ratio(i.answer, ctx), 3),
        context_relevance=round(token_f1(i.question, ctx, recall_only=True), 3),
        rationale="Mock judge: lexical overlap metrics (deterministic).",
    )


EVALUATION_AGENT = register(AgentSpec(
    name="evaluation_agent",
    responsibility="Model-based grading of answers (complements deterministic metrics)",
    input_schema=JudgeIn, output_schema=JudgeOut,
    system_prompt="You are a strict evaluator of retrieval-augmented answers. Output calibrated scores.",
    build_prompt=_judge_prompt, mock=_judge_mock, temperature=0.0, max_tokens=600,
))
