import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.agents.assess import ASSESSMENT_AGENT, OPPORTUNITY_AGENT, AssessmentAgentIn, OpportunityAgentIn
from app.ai.agents.framework import AgentError, AgentRunner, provenance
from app.core.errors import AppError, InvalidTransition
from app.domain import opportunities as opp_domain
from app.domain.question_bank import DIMENSIONS, PROFILE_OBJECTIVES, QUESTION_VERSION, QUESTIONS
from app.domain.scoring import (
    AnswerError,
    build_findings,
    build_plans,
    is_applicable,
    score_assessment,
    validate_answer,
)
from app.models import (
    Assessment,
    AssessmentAnswer,
    AssessmentQuestion,
    AssessmentScore,
    Lead,
    Opportunity,
    Organisation,
    PlatformSetting,
)
from app.services.common import record_activity


def sync_question_bank(db: Session) -> int:
    existing = {(q.key, q.version): q for q in db.scalars(select(AssessmentQuestion)).all()}
    n = 0
    for pos, q in enumerate(QUESTIONS):
        row = existing.get((q["key"], QUESTION_VERSION))
        if row is None:
            row = AssessmentQuestion(key=q["key"], version=QUESTION_VERSION)
            db.add(row)
            n += 1
        row.dimension, row.text, row.help_text = q["dimension"], q["text"], q.get("help_text")
        row.qtype, row.options, row.weight, row.position = q["qtype"], q["options"], Decimal(str(q["weight"])), pos
        row.condition, row.risk_flag = q.get("condition"), q.get("risk_flag")
    db.flush()
    return n


def question_defs(db: Session, version: int) -> list[dict]:
    rows = db.scalars(select(AssessmentQuestion).where(AssessmentQuestion.version == version)
                      .order_by(AssessmentQuestion.position)).all()
    return [{"id": r.id, "key": r.key, "dimension": r.dimension, "text": r.text, "help_text": r.help_text,
             "qtype": r.qtype, "options": r.options, "weight": float(r.weight), "condition": r.condition,
             "risk_flag": r.risk_flag} for r in rows]


def answers_by_key(db: Session, assessment: Assessment) -> dict:
    rows = db.execute(select(AssessmentQuestion.key, AssessmentAnswer.value)
                      .join(AssessmentAnswer, AssessmentAnswer.question_id == AssessmentQuestion.id)
                      .where(AssessmentAnswer.assessment_id == assessment.id)).all()
    return {k: v["v"] for k, v in rows}


def validate_profile(profile: dict) -> dict:
    out = dict(profile)
    bad = [o for o in out.get("objectives") or [] if o not in PROFILE_OBJECTIVES]
    if bad:
        raise AppError(f"Unknown objectives {bad}", code="invalid_profile")
    return out


def save_progress(db: Session, assessment: Assessment, answers: dict, profile: dict | None, step: int | None) -> dict:
    if assessment.status != "draft":
        raise InvalidTransition("Submitted assessments cannot be edited")
    qs = {q["key"]: q for q in question_defs(db, assessment.question_version)}
    errors = {}
    for key, value in answers.items():
        q = qs.get(key)
        if q is None:
            errors[key] = "unknown question"
        elif value is not None and (err := validate_answer(q, value)):
            errors[key] = err
    if errors:
        raise AppError("Invalid answers", details=errors, code="invalid_answers")
    for key, value in answers.items():
        qid = qs[key]["id"]
        row = db.scalar(select(AssessmentAnswer).where(AssessmentAnswer.assessment_id == assessment.id,
                                                       AssessmentAnswer.question_id == qid))
        if value is None:
            if row:
                db.delete(row)
            continue
        if row is None:
            db.add(AssessmentAnswer(assessment_id=assessment.id, question_id=qid, value={"v": value}))
        else:
            row.value = {"v": value}
    if profile is not None:
        assessment.profile = validate_profile({**assessment.profile, **profile})
    if step is not None:
        assessment.current_step = step
    db.flush()
    current = answers_by_key(db, assessment)
    # drop answers to conditional questions that no longer apply
    for q in qs.values():
        if q["key"] in current and not is_applicable(q, current):
            db.execute(delete(AssessmentAnswer).where(AssessmentAnswer.assessment_id == assessment.id,
                                                      AssessmentAnswer.question_id == q["id"]))
            current.pop(q["key"])
    return current


def submit(db: Session, assessment: Assessment, actor_id: uuid.UUID | None) -> Assessment:
    if assessment.status != "draft":
        raise InvalidTransition("Assessment has already been submitted")
    if not assessment.profile.get("company_name"):
        raise AppError("Organisation profile is incomplete", details={"company_name": "required"},
                       code="invalid_profile")
    qs = question_defs(db, assessment.question_version)
    answers = answers_by_key(db, assessment)
    try:
        result = score_assessment(qs, answers)
    except AnswerError as exc:
        raise AppError("Assessment is incomplete or invalid", details=exc.errors, code="assessment_incomplete")

    db.execute(delete(AssessmentScore).where(AssessmentScore.assessment_id == assessment.id))
    for d in result.dimensions.values():
        db.add(AssessmentScore(assessment_id=assessment.id, dimension=d.dimension, score=Decimal(str(d.score)),
                               weight=Decimal(str(d.weight)), level=d.level,
                               breakdown=[c.__dict__ for c in d.breakdown]))
    findings = build_findings(qs, answers, result)
    ranked = generate_opportunities(db, assessment, result_dims={k: v.score for k, v in result.dimensions.items()},
                                    answers=answers)
    first = ranked[0] if ranked else None
    findings["first_project"] = ({"catalog_key": first.catalog_key, "title": first.title,
                                  "priority_score": float(first.priority_score)} if first else None)
    findings.update(build_plans(result, findings["first_project"], findings["weakest_dimensions"]))
    findings["dimension_scores"] = {k: {"label": v.label, "score": v.score, "level": v.level, "weight": v.weight}
                                    for k, v in result.dimensions.items()}
    findings["classification_text"] = result.classification_text

    assessment.overall_score = Decimal(str(result.overall))
    assessment.classification = result.classification
    assessment.findings = findings
    assessment.status = "scored"
    assessment.submitted_at = datetime.now(UTC)
    assessment.report_status = "pending"
    lead = db.scalar(select(Lead).where(Lead.organisation_id == assessment.organisation_id)
                     .order_by(Lead.created_at.desc()).limit(1))
    if lead:
        record_activity(db, assessment.organisation_id, "lead", lead.id, "system",
                        f"AI readiness assessment submitted: {result.overall}/100 ({result.classification})",
                        actor_id, {"assessment_id": str(assessment.id)}, customer_visible=True)
    db.flush()
    return assessment


def opportunity_weights(db: Session) -> dict:
    row = db.get(PlatformSetting, "opportunity_weights")
    return {**opp_domain.DEFAULT_WEIGHTS, **(row.value if row else {})}


def financial_assumptions(db: Session) -> dict:
    row = db.get(PlatformSetting, "financial_assumptions")
    return {**opp_domain.DEFAULT_FINANCIAL_ASSUMPTIONS, **(row.value if row else {})}


def generate_opportunities(db: Session, assessment: Assessment, result_dims: dict | None = None,
                           answers: dict | None = None) -> list[Opportunity]:
    if result_dims is None:
        scores = db.scalars(select(AssessmentScore).where(AssessmentScore.assessment_id == assessment.id)).all()
        result_dims = {s.dimension: float(s.score) for s in scores}
    answers = answers if answers is not None else answers_by_key(db, assessment)
    scored = opp_domain.evaluate(result_dims, assessment.profile, answers, opportunity_weights(db),
                                 financial_assumptions(db))
    db.execute(delete(Opportunity).where(Opportunity.assessment_id == assessment.id))
    rows = []
    for o in scored:
        row = Opportunity(organisation_id=assessment.organisation_id, assessment_id=assessment.id,
                          catalog_key=o.catalog_key, title=o.title, description=o.description,
                          business_impact=o.business_impact, implementation_complexity=o.implementation_complexity,
                          effort_weeks=o.effort_weeks, data_availability=o.data_availability,
                          integration_complexity=o.integration_complexity, security_risk=o.security_risk,
                          roi_assumptions=o.roi_assumptions, priority_score=Decimal(str(o.priority_score)),
                          rank=o.rank, reasoning=o.reasoning,
                          status="shortlisted" if o.rank <= 3 else "identified")
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def rerank(db: Session, org_id: uuid.UUID) -> list[Opportunity]:
    """Re-apply the current (configurable) weights to stored factors without regenerating the catalogue."""
    w = opportunity_weights(db)
    rows = db.scalars(select(Opportunity).where(Opportunity.organisation_id == org_id)).all()
    for r in rows:
        f = r.reasoning["factors"]
        weighted = {k: round(w[k] * v, 3) for k, v in f.items()}
        r.priority_score = Decimal(str(round(sum(weighted.values()) / (5 * sum(w.values())) * 100, 1)))
        r.reasoning = {**r.reasoning, "weights": w, "weighted": weighted}
    rows.sort(key=lambda r: (-float(r.priority_score), r.effort_weeks, r.catalog_key))
    for i, r in enumerate(rows, 1):
        r.rank = i
    db.flush()
    return rows


def generate_report(db: Session, assessment_id: uuid.UUID, provider: str | None = None) -> Assessment:
    """LLM narrative over deterministic results. Scores are never modified here."""
    a = db.get(Assessment, assessment_id)
    if a is None or a.status != "scored":
        raise InvalidTransition("Only scored assessments can have a report generated")
    org = db.get(Organisation, a.organisation_id)
    f = a.findings
    runner = AgentRunner(db, a.organisation_id, provider=provider)
    try:
        outcome = runner.run(ASSESSMENT_AGENT, AssessmentAgentIn(
            organisation=a.profile.get("company_name") or org.name, industry=a.profile.get("industry"),
            objectives=[PROFILE_OBJECTIVES[o] for o in a.profile.get("objectives") or []],
            overall=float(a.overall_score), classification=a.classification,
            dimensions={k: {"label": v["label"], "score": v["score"], "level": v["level"]}
                        for k, v in f["dimension_scores"].items()},
            strengths=f["strengths"], weaknesses=f["weaknesses"], risks=f["risks"], first_project=f.get("first_project"),
        ))
        opps = db.scalars(select(Opportunity).where(Opportunity.assessment_id == a.id).order_by(Opportunity.rank)).all()
        opp_outcome = runner.run(OPPORTUNITY_AGENT, OpportunityAgentIn(
            organisation=org.name, industry=a.profile.get("industry"),
            business_problem=a.profile.get("business_problem"),
            opportunities=[{"catalog_key": o.catalog_key, "title": o.title, "priority_score": float(o.priority_score),
                            "rank": o.rank, "factors": o.reasoning["factors"], "adjustments": o.reasoning["adjustments"],
                            "roi": o.roi_assumptions} for o in opps],
        ))
        narratives = {i.catalog_key: i.narrative for i in opp_outcome.output.items}
        for o in opps:
            o.narrative = narratives.get(o.catalog_key)
        a.report = {**outcome.output.model_dump(), "opportunity_summary": opp_outcome.output.portfolio_summary,
                    "provenance": provenance("assessment_agent", outcome)}
        a.report_status = "ready"
        a.report_model = f"{outcome.provider}:{outcome.model}"
    except AgentError as exc:
        a.report_status = "failed"
        a.report = {"error": str(exc)}
    db.flush()
    return a


def dimensions_meta() -> list[dict]:
    return [{"key": k, **v} for k, v in DIMENSIONS.items()]
