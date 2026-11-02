"""Assessment Agent and Opportunity Research Agent.

Both receive deterministic scores as input and may only *explain* them. Validation rejects any output that
restates a score different from the computed value.
"""

import json
import re

from pydantic import BaseModel, Field

from app.ai.agents.framework import AgentSpec, register


# ------------------------------------------------------------------ Assessment Agent
class DimensionIn(BaseModel):
    label: str
    score: float
    level: str


class AssessmentAgentIn(BaseModel):
    organisation: str
    industry: str | None = None
    objectives: list[str] = []
    overall: float
    classification: str
    dimensions: dict[str, DimensionIn]
    strengths: list[dict]
    weaknesses: list[dict]
    risks: list[dict]
    first_project: dict | None = None


class AssessmentNarrative(BaseModel):
    executive_summary: str = Field(description="3-5 sentence summary for an executive audience")
    dimension_commentary: dict[str, str] = Field(description="One short paragraph per dimension key")
    first_project_rationale: str
    adoption_recommendations: list[str] = Field(min_length=3, max_length=6)
    key_message: str


def _assess_prompt(i: AssessmentAgentIn, _ctx: dict) -> str:
    return (
        "Write the narrative for an AI readiness report. The scores below were computed by a deterministic, "
        "weighted scoring engine. Do NOT change, recompute or invent any score; quote them exactly if you use them.\n\n"
        f"Organisation: {i.organisation} ({i.industry or 'industry not stated'})\n"
        f"Stated objectives: {', '.join(i.objectives) or 'none'}\n"
        f"Overall score: {i.overall}/100 ({i.classification})\n"
        f"Dimension scores: {json.dumps({k: v.model_dump() for k, v in i.dimensions.items()})}\n"
        f"Strengths: {json.dumps(i.strengths)}\nWeaknesses: {json.dumps(i.weaknesses)}\nRisks: {json.dumps(i.risks)}\n"
        f"Recommended first project (from deterministic opportunity ranking): {json.dumps(i.first_project)}\n"
        "Return dimension_commentary keyed by the same dimension keys."
    )


def _assess_mock(i: AssessmentAgentIn, _ctx: dict) -> AssessmentNarrative:
    ordered = sorted(i.dimensions.items(), key=lambda kv: kv[1].score, reverse=True)
    best, worst = ordered[0][1], ordered[-1][1]
    fp = (i.first_project or {}).get("title", "a focused pilot")
    commentary = {
        k: (f"{d.label} scored {d.score:.1f}/100 ({d.level}). "
            + ("This is a relative strength you can build on." if d.score >= 65 else
               "Adequate foundations with targeted gaps to close." if d.score >= 45 else
               "This is a constraint that should be addressed alongside the first project."))
        for k, d in i.dimensions.items()
    }
    recs = [w.get("title", "") for w in i.weaknesses][:2]
    return AssessmentNarrative(
        executive_summary=(
            f"{i.organisation} achieved an overall AI readiness score of {i.overall:.1f}/100, classified as "
            f"{i.classification}. The strongest dimension is {best.label} ({best.score:.1f}) and the weakest is "
            f"{worst.label} ({worst.score:.1f}). {len(i.risks)} risk(s) were identified from the answers provided. "
            f"We recommend starting with {fp}, while addressing the weakest foundations in parallel."
        ),
        dimension_commentary=commentary,
        first_project_rationale=(
            f"{fp} ranked first in the deterministic opportunity prioritisation, balancing business impact against "
            "data availability, integration effort and security risk for your current readiness profile."
        ),
        adoption_recommendations=[
            f"Start with {fp} as a time-boxed pilot with a measured baseline.",
            *[f"Address: {r}" for r in recs if r],
            "Establish an evaluation dataset and human-review checkpoints before scaling.",
            "Track usage, cost and quality from day one so value can be demonstrated.",
        ][:6],
        key_message=f"Readiness is {i.classification.lower()}: prove value with {fp}, fix {worst.label.lower()} gaps.",
    )


def _assess_validate(i: AssessmentAgentIn, o: AssessmentNarrative) -> list[str]:
    errors = []
    missing = set(i.dimensions) - set(o.dimension_commentary)
    if missing:
        errors.append(f"dimension_commentary missing keys {sorted(missing)}")
    allowed = {f"{i.overall:.1f}", f"{i.overall:.0f}", *{f"{d.score:.1f}" for d in i.dimensions.values()},
               *{f"{d.score:.0f}" for d in i.dimensions.values()}}
    for m in re.finditer(r"(\d{1,3}(?:\.\d)?)\s*/\s*100", o.executive_summary):
        if m.group(1) not in allowed:
            errors.append(f"executive_summary states score {m.group(1)}/100 which does not match computed scores")
    return errors


ASSESSMENT_AGENT = register(AgentSpec(
    name="assessment_agent",
    responsibility="Explain deterministic readiness scores and write adoption recommendations",
    input_schema=AssessmentAgentIn, output_schema=AssessmentNarrative,
    system_prompt=("You are a senior AI strategy consultant. You explain readiness results clearly and "
                   "conservatively. You never alter computed scores and never promise financial outcomes."),
    build_prompt=_assess_prompt, mock=_assess_mock, validate=_assess_validate,
))


# ------------------------------------------------------------------ Opportunity Research Agent
class OpportunityIn(BaseModel):
    catalog_key: str
    title: str
    priority_score: float
    rank: int
    factors: dict
    adjustments: list[str]
    roi: dict


class OpportunityAgentIn(BaseModel):
    organisation: str
    industry: str | None = None
    business_problem: str | None = None
    opportunities: list[OpportunityIn]


class OpportunityNarrativeItem(BaseModel):
    catalog_key: str
    narrative: str = Field(description="Why this opportunity fits, key prerequisites, and caveats")


class OpportunityReport(BaseModel):
    portfolio_summary: str
    items: list[OpportunityNarrativeItem]


def _opp_prompt(i: OpportunityAgentIn, _ctx: dict) -> str:
    return (
        "Explain the following AI opportunities, which were ranked by a deterministic scoring formula. "
        "Do not change ranks or numbers. Treat all financial figures as illustrative estimates and say so.\n"
        f"Organisation: {i.organisation} ({i.industry or 'n/a'}). Business problem: {i.business_problem or 'n/a'}\n"
        f"Opportunities: {json.dumps([o.model_dump() for o in i.opportunities])}\n"
        "Return one item per catalog_key."
    )


def _opp_mock(i: OpportunityAgentIn, _ctx: dict) -> OpportunityReport:
    items = []
    for o in i.opportunities:
        f = o.factors
        strengths = [k.replace("_", " ") for k, v in f.items() if v >= 4]
        concerns = [k.replace("_", " ") for k, v in f.items() if v <= 2]
        hi = o.roi.get("estimated_annual_value_high")
        items.append(OpportunityNarrativeItem(
            catalog_key=o.catalog_key,
            narrative=(
                f"Ranked #{o.rank} with a priority score of {o.priority_score:.1f}. "
                + (f"Favourable on {', '.join(strengths)}. " if strengths else "")
                + (f"Watch {', '.join(concerns)}. " if concerns else "")
                + (f"Illustrative estimate: up to {o.roi.get('currency', 'GBP')} {hi:,} annual value under the stated "
                   "assumptions; this is not a guaranteed outcome." if hi else "")
            ),
        ))
    top = i.opportunities[0].title if i.opportunities else "n/a"
    return OpportunityReport(
        portfolio_summary=(f"{len(i.opportunities)} opportunities were evaluated for {i.organisation}. {top} offers the "
                           "best balance of impact and feasibility today. Figures are estimates based on explicit "
                           "assumptions and should be validated during discovery."),
        items=items,
    )


def _opp_validate(i: OpportunityAgentIn, o: OpportunityReport) -> list[str]:
    missing = {x.catalog_key for x in i.opportunities} - {x.catalog_key for x in o.items}
    return [f"missing narratives for {sorted(missing)}"] if missing else []


OPPORTUNITY_AGENT = register(AgentSpec(
    name="opportunity_research_agent",
    responsibility="Explain ranked AI opportunities, prerequisites and caveats",
    input_schema=OpportunityAgentIn, output_schema=OpportunityReport,
    system_prompt=("You are an AI solutions consultant. You explain why opportunities fit a business, the "
                   "prerequisites and risks. Financial values are always estimates, never guarantees."),
    build_prompt=_opp_prompt, mock=_opp_mock, validate=_opp_validate,
))
