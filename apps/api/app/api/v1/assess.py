import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal, get_scoped, require
from app.core.errors import AppError, InvalidTransition
from app.db.session import get_db
from app.domain.question_bank import DIMENSIONS, QUESTION_VERSION, STEPS
from app.models import Assessment, AssessmentScore, Opportunity, Organisation
from app.schemas.common import ORM, Page
from app.services import assessments as svc
from app.services.common import audit, idempotent, org_name_map, paginate
from app.services.delivery import advance_lead
from app.services.pdf import assessment_pdf
from app.workers.tasks import enqueue_report

router = APIRouter(tags=["assessments"])


class QuestionOut(BaseModel):
    key: str
    dimension: str
    text: str
    help_text: str | None
    qtype: str
    options: list[dict]
    weight: float
    condition: dict | None


class AssessmentCreate(BaseModel):
    organisation_id: uuid.UUID | None = None


class AssessmentOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    organisation_name: str | None = None
    status: str
    current_step: int
    question_version: int
    profile: dict
    overall_score: float | None
    classification: str | None
    report_status: str
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AssessmentDetail(AssessmentOut):
    answers: dict[str, Any]
    steps: list[str]


class ProgressIn(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)
    profile: dict | None = None
    current_step: int | None = Field(None, ge=0, le=len(STEPS) - 1)


class ScoreOut(ORM):
    dimension: str
    score: float
    weight: float
    level: str
    breakdown: list[dict]


class OpportunityOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    assessment_id: uuid.UUID | None
    catalog_key: str
    title: str
    description: str
    business_impact: int
    implementation_complexity: int
    effort_weeks: int
    data_availability: int
    integration_complexity: int
    security_risk: int
    roi_assumptions: dict
    priority_score: float
    rank: int
    reasoning: dict
    narrative: str | None
    status: str


class ReportOut(BaseModel):
    assessment: AssessmentOut
    scores: list[ScoreOut]
    findings: dict
    report: dict
    opportunities: list[OpportunityOut]
    dimensions: list[dict]


@router.get("/assessments/questions", response_model=list[QuestionOut])
def questions(db: Session = Depends(get_db)):
    """Public: the question bank, so the website can render the assessment before sign-up."""
    return [QuestionOut(**{k: q[k] for k in QuestionOut.model_fields}) for q in svc.question_defs(db, QUESTION_VERSION)]


@router.post("/assessments", response_model=AssessmentDetail, status_code=201)
def create_assessment(body: AssessmentCreate, request: Request, principal: Principal = Depends(get_principal),
                      db: Session = Depends(get_db)):
    org_id = body.organisation_id
    if org_id is None:
        if len(principal.customer_orgs) != 1:
            raise AppError("organisation_id is required", code="organisation_required")
        org_id = next(iter(principal.customer_orgs))
    principal.require("assessment.write", org_id)
    org = db.get(Organisation, org_id)
    a = Assessment(organisation_id=org_id, created_by=principal.id, question_version=QUESTION_VERSION,
                   profile={"company_name": org.name, "industry": org.industry, "company_size": org.size,
                            "website": org.website, "contact_name": principal.user.full_name,
                            "contact_email": principal.user.email, "objectives": []})
    db.add(a)
    db.flush()
    audit(db, principal.id, "assessment.create", "assessment", a.id, org_id, request=request)
    db.commit()
    return AssessmentDetail(**AssessmentOut.model_validate(a).model_dump(), answers={}, steps=STEPS)


@router.get("/assessments", response_model=Page[AssessmentOut])
def list_assessments(organisation_id: uuid.UUID | None = None, status: str | None = None,
                     page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                     principal: Principal = Depends(require("assessment.read")), db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(Assessment), Assessment)
    if organisation_id:
        stmt = stmt.where(Assessment.organisation_id == organisation_id)
    if status:
        stmt = stmt.where(Assessment.status == status)
    items, total = paginate(db, stmt.order_by(Assessment.created_at.desc()), page, page_size)
    names = org_name_map(db, [i.organisation_id for i in items])
    return Page(items=[AssessmentOut.model_validate(i).model_copy(update={"organisation_name": names.get(i.organisation_id)})
                       for i in items], total=total, page=page, page_size=page_size)


@router.get("/assessments/{aid}", response_model=AssessmentDetail)
def get_assessment(aid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    a = get_scoped(db, Assessment, aid, principal, "assessment.read")
    return AssessmentDetail(**AssessmentOut.model_validate(a).model_dump(), answers=svc.answers_by_key(db, a), steps=STEPS)


@router.put("/assessments/{aid}/progress", response_model=AssessmentDetail)
def save_progress(aid: uuid.UUID, body: ProgressIn, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)):
    """Save-and-resume: persist partial answers, profile and the current step."""
    a = get_scoped(db, Assessment, aid, principal, "assessment.write")
    answers = svc.save_progress(db, a, body.answers, body.profile, body.current_step)
    db.commit()
    return AssessmentDetail(**AssessmentOut.model_validate(a).model_dump(), answers=answers, steps=STEPS)


@router.post("/assessments/{aid}/submit", response_model=AssessmentOut)
def submit_assessment(aid: uuid.UUID, request: Request, idempotency_key: str | None = Header(None),
                      principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    a = get_scoped(db, Assessment, aid, principal, "assessment.write")

    def compute():
        svc.submit(db, a, principal.id)
        advance_lead(db, a.organisation_id, "assessment", principal.id, "readiness assessment completed")
        audit(db, principal.id, "assessment.submit", "assessment", a.id, a.organisation_id,
              {"overall": float(a.overall_score)}, request)
        enqueue_report(db, a.id)
        return AssessmentOut.model_validate(a)

    result = idempotent(db, principal.id, idempotency_key, f"assessment.submit:{aid}", {}, compute)
    db.commit()
    return result


@router.get("/assessments/{aid}/report", response_model=ReportOut)
def get_report(aid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    a = get_scoped(db, Assessment, aid, principal, "assessment.read")
    if a.status != "scored":
        raise InvalidTransition("Assessment has not been submitted yet")
    scores = db.scalars(select(AssessmentScore).where(AssessmentScore.assessment_id == a.id)).all()
    order = list(DIMENSIONS)
    scores = sorted(scores, key=lambda s: order.index(s.dimension))
    opps = db.scalars(select(Opportunity).where(Opportunity.assessment_id == a.id).order_by(Opportunity.rank)).all()
    return ReportOut(assessment=AssessmentOut.model_validate(a), scores=[ScoreOut.model_validate(s) for s in scores],
                     findings=a.findings, report=a.report, opportunities=[OpportunityOut.model_validate(o) for o in opps],
                     dimensions=svc.dimensions_meta())


@router.post("/assessments/{aid}/report/regenerate", response_model=AssessmentOut)
def regenerate_report(aid: uuid.UUID, request: Request, principal: Principal = Depends(get_principal),
                      db: Session = Depends(get_db)):
    a = get_scoped(db, Assessment, aid, principal, "assessment.write")
    if a.status != "scored":
        raise InvalidTransition("Assessment has not been submitted yet")
    a.report_status = "pending"
    audit(db, principal.id, "assessment.report_regenerate", "assessment", a.id, a.organisation_id, request=request)
    enqueue_report(db, a.id)
    db.commit()
    return a


@router.get("/assessments/{aid}/report.pdf")
def report_pdf(aid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    a = get_scoped(db, Assessment, aid, principal, "assessment.read")
    if a.status != "scored":
        raise InvalidTransition("Assessment has not been submitted yet")
    scores = db.scalars(select(AssessmentScore).where(AssessmentScore.assessment_id == a.id)).all()
    opps = db.scalars(select(Opportunity).where(Opportunity.assessment_id == a.id).order_by(Opportunity.rank)).all()
    org = db.get(Organisation, a.organisation_id)
    pdf = assessment_pdf(org.name, a, scores, opps)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="ai-readiness-{org.slug}.pdf"'})


# ------------------------------------------------------------------ opportunities
class OpportunityPatch(BaseModel):
    status: str = Field(pattern="^(identified|shortlisted|selected|rejected)$")


@router.get("/opportunities", response_model=list[OpportunityOut])
def list_opportunities(organisation_id: uuid.UUID | None = None, principal: Principal = Depends(require("opportunity.read")),
                       db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(Opportunity), Opportunity)
    if organisation_id:
        stmt = stmt.where(Opportunity.organisation_id == organisation_id)
    return db.scalars(stmt.order_by(Opportunity.organisation_id, Opportunity.rank)).all()


@router.get("/opportunities/{oid}", response_model=OpportunityOut)
def get_opportunity(oid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return get_scoped(db, Opportunity, oid, principal, "opportunity.read")


@router.patch("/opportunities/{oid}", response_model=OpportunityOut)
def patch_opportunity(oid: uuid.UUID, body: OpportunityPatch, request: Request,
                      principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    o = get_scoped(db, Opportunity, oid, principal, "opportunity.write")
    o.status = body.status
    audit(db, principal.id, "opportunity.update", "opportunity", o.id, o.organisation_id, {"status": body.status}, request)
    db.commit()
    return o


@router.post("/organisations/{org_id}/opportunities/rerank", response_model=list[OpportunityOut])
def rerank(org_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    """Re-apply the current configurable prioritisation weights."""
    principal.require("opportunity.write", org_id)
    rows = svc.rerank(db, org_id)
    db.commit()
    return rows
