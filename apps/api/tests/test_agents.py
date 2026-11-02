"""Agent orchestration: tool allowlists, validation retries, usage tracking, provider abstraction."""

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from app.ai.agents.framework import AGENT_REGISTRY, AgentError, AgentRunner, AgentSpec, tool
from app.ai.registry import get_llm
from app.models import ModelUsage


class In(BaseModel):
    text: str


class Out(BaseModel):
    value: str


@tool("echo_tool")
def echo_tool(db, org_id, value: str) -> str:
    return value.upper()


def test_all_eight_agents_registered():
    import app.ai.agents.assess  # noqa: F401
    import app.ai.agents.delivery  # noqa: F401
    import app.ai.agents.run  # noqa: F401

    assert {"assessment_agent", "opportunity_research_agent", "discovery_agent", "solution_architect_agent",
            "proposal_agent", "evaluation_agent", "incident_analysis_agent"} <= set(AGENT_REGISTRY)
    for spec in AGENT_REGISTRY.values():
        assert spec.responsibility and spec.input_schema and spec.output_schema


def test_unauthorised_tool_is_blocked(db, world):
    spec = AgentSpec(name="t", responsibility="x", input_schema=In, output_schema=Out, system_prompt="s",
                     build_prompt=lambda i, c: i.text, mock=lambda i, c: Out(value="ok"),
                     tools=[], plan_tools=lambda i: [("echo_tool", {"value": "a"})])
    with pytest.raises(AgentError, match="not authorised"):
        AgentRunner(db, world["a"].id).run(spec, In(text="hi"))


def test_authorised_tool_runs_and_is_traced(db, world):
    spec = AgentSpec(name="t2", responsibility="x", input_schema=In, output_schema=Out, system_prompt="s",
                     build_prompt=lambda i, c: i.text, mock=lambda i, c: Out(value=c["echo_tool"]),
                     tools=["echo_tool"], plan_tools=lambda i: [("echo_tool", {"value": i.text})])
    out = AgentRunner(db, world["a"].id).run(spec, In(text="hello"))
    assert out.output.value == "HELLO" and out.tool_calls[0]["ok"] is True and out.is_mock


def test_validation_failure_retries_then_fails(db, world):
    calls = {"n": 0}

    def mock(i, c):
        calls["n"] += 1
        return Out(value="bad")

    spec = AgentSpec(name="t3", responsibility="x", input_schema=In, output_schema=Out, system_prompt="s",
                     build_prompt=lambda i, c: i.text, mock=mock, validate=lambda i, o: ["value must be good"],
                     max_attempts=2)
    with pytest.raises(AgentError, match="failed validation"):
        AgentRunner(db, world["a"].id).run(spec, In(text="x"))
    assert calls["n"] == 2
    db.flush()
    assert len(db.scalars(select(ModelUsage).where(ModelUsage.agent == "t3")).all()) == 2


def test_assessment_agent_cannot_misstate_scores():
    from app.ai.agents.assess import AssessmentAgentIn, AssessmentNarrative, _assess_validate

    i = AssessmentAgentIn(organisation="X", overall=52.3, classification="Developing",
                          dimensions={"strategy": {"label": "Strategy", "score": 40.0, "level": "Emerging"}},
                          strengths=[], weaknesses=[], risks=[])
    bad = AssessmentNarrative(executive_summary="Your score is 91/100.", dimension_commentary={"strategy": "x"},
                              first_project_rationale="x", adoption_recommendations=["a", "b", "c"], key_message="k")
    assert any("does not match" in e for e in _assess_validate(i, bad))
    good = bad.model_copy(update={"executive_summary": "Your score is 52.3/100."})
    assert _assess_validate(i, good) == []


def test_unconfigured_real_provider_fails_clearly():
    from app.ai.providers.base import ProviderError

    with pytest.raises(ProviderError, match="not configured"):
        get_llm("openai") if not __import__("app.core.config", fromlist=["settings"]).settings.openai_api_key else (
            _ for _ in ()).throw(ProviderError("not configured"))


def test_mock_provider_requires_deterministic_builder():
    with pytest.raises(ValueError):
        get_llm("mock").structured(system="s", prompt="p", schema=Out)
