import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.agents.delivery import DISCOVERY_FIELDS
from app.ai.agents.framework import AgentError
from app.api.deps import Principal, get_principal, get_scoped, require
from app.core.errors import AppError, Forbidden, InvalidTransition, NotFound
from app.db.session import get_db
from app.models import (
    ActionItem,
    ArchitectureDocument,
    DiscoverySession,
    Organisation,
    Project,
    Proposal,
    ProposalVersion,
    Requirement,
    Stakeholder,
)
from app.schemas.common import ORM, Page
from app.services import delivery as svc
from app.services.common import audit, idempotent, org_name_map, paginate, user_name_map
from app.services.pdf import proposal_pdf

router = APIRouter(tags=["build"])


def _agent_call(fn):
    try:
        return fn()
    except AgentError as exc:
        raise AppError(f"AI assistant failed: {exc}", code="ai_generation_failed")


# ------------------------------------------------------------------ discovery sessions
class SessionIn(BaseModel):
    organisation_id: uuid.UUID
    title: str = Field(min_length=2, max_length=200)
    session_date: date | None = None
    lead_id: uuid.UUID | None = None


class SessionPatch(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=200)
    session_date: date | None = None
    answers: dict[str, str] | None = None
    technical_notes: str | None = Field(None, max_length=50000)
    meeting_notes: str | None = Field(None, max_length=50000)


class SessionOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    organisation_name: str | None = None
    lead_id: uuid.UUID | None
    title: str
    status: str
    owner_id: uuid.UUID | None
    owner_name: str | None = None
    session_date: date | None
    answers: dict
    technical_notes: str
    meeting_notes: str
    ai_analysis: dict
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _session_out(db: Session, s: DiscoverySession) -> SessionOut:
    return SessionOut.model_validate(s).model_copy(update={
        "organisation_name": org_name_map(db, [s.organisation_id]).get(s.organisation_id),
        "owner_name": user_name_map(db, [s.owner_id]).get(s.owner_id)})


@router.get("/discovery/fields")
def discovery_fields():
    return DISCOVERY_FIELDS


@router.get("/discovery/sessions", response_model=Page[SessionOut])
def list_sessions(organisation_id: uuid.UUID | None = None, status: str | None = None, page: int = Query(1, ge=1),
                  page_size: int = Query(20, ge=1, le=100), principal: Principal = Depends(require("discovery.read")),
                  db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(DiscoverySession), DiscoverySession)
    if organisation_id:
        stmt = stmt.where(DiscoverySession.organisation_id == organisation_id)
    if status:
        stmt = stmt.where(DiscoverySession.status == status)
    items, total = paginate(db, stmt.order_by(DiscoverySession.updated_at.desc()), page, page_size)
    return Page(items=[_session_out(db, s) for s in items], total=total, page=page, page_size=page_size)


@router.post("/discovery/sessions", response_model=SessionOut, status_code=201)
def create_session(body: SessionIn, request: Request, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    principal.require("discovery.write", body.organisation_id)
    s = DiscoverySession(organisation_id=body.organisation_id, title=body.title, session_date=body.session_date,
                         lead_id=body.lead_id, owner_id=principal.id, answers={k: "" for k in DISCOVERY_FIELDS})
    db.add(s)
    db.flush()
    svc.advance_lead(db, body.organisation_id, "discovery", principal.id, "discovery session opened")
    audit(db, principal.id, "discovery.create", "discovery_session", s.id, s.organisation_id, request=request)
    db.commit()
    return _session_out(db, s)


@router.get("/discovery/sessions/{sid}", response_model=SessionOut)
def get_session(sid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return _session_out(db, get_scoped(db, DiscoverySession, sid, principal, "discovery.read"))


@router.patch("/discovery/sessions/{sid}", response_model=SessionOut)
def patch_session(sid: uuid.UUID, body: SessionPatch, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)):
    s = get_scoped(db, DiscoverySession, sid, principal, "discovery.write")
    if s.status == "completed":
        raise InvalidTransition("Completed sessions are read-only; reopen first")
    data = body.model_dump(exclude_unset=True)
    if "answers" in data:
        unknown = set(data["answers"]) - set(DISCOVERY_FIELDS)
        if unknown:
            raise AppError(f"Unknown questionnaire fields {sorted(unknown)}", code="invalid_fields")
        s.answers = {**s.answers, **data.pop("answers")}
    for k, v in data.items():
        setattr(s, k, v)
    db.commit()
    return _session_out(db, s)


@router.post("/discovery/sessions/{sid}/analyze", response_model=SessionOut)
def analyze(sid: uuid.UUID, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    s = get_scoped(db, DiscoverySession, sid, principal, "discovery.write")
    _agent_call(lambda: svc.analyze_discovery(db, s))
    audit(db, principal.id, "discovery.ai_analyze", "discovery_session", s.id, s.organisation_id, request=request)
    db.commit()
    return _session_out(db, s)


class RequirementOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    session_id: uuid.UUID | None
    project_id: uuid.UUID | None
    code: str
    title: str
    description: str
    category: str
    priority: str
    status: str
    source: str
    acceptance_criteria: str
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime


class ImportIn(BaseModel):
    indexes: list[int] | None = None
    include_integrations: bool = True


@router.post("/discovery/sessions/{sid}/import-requirements", response_model=list[RequirementOut])
def import_requirements(sid: uuid.UUID, body: ImportIn, principal: Principal = Depends(get_principal),
                        db: Session = Depends(get_db)):
    """Create DRAFT requirements from the AI analysis. They still require explicit engineer approval."""
    s = get_scoped(db, DiscoverySession, sid, principal, "discovery.write")
    rows = svc.requirements_from_analysis(db, s, body.indexes)
    if body.include_integrations:
        svc.import_suggested_integrations(db, s)
    db.commit()
    return rows


@router.post("/discovery/sessions/{sid}/complete", response_model=SessionOut)
def complete_session(sid: uuid.UUID, request: Request, principal: Principal = Depends(get_principal),
                     db: Session = Depends(get_db)):
    s = get_scoped(db, DiscoverySession, sid, principal, "discovery.write")
    missing = [DISCOVERY_FIELDS[k] for k in ("business_problem", "current_workflow", "existing_systems")
               if not (s.answers.get(k) or "").strip()]
    if missing:
        raise AppError("Required discovery fields are empty", details={"missing": missing}, code="discovery_incomplete")
    s.status, s.completed_at = "completed", datetime.now(UTC)
    audit(db, principal.id, "discovery.complete", "discovery_session", s.id, s.organisation_id, request=request)
    db.commit()
    return _session_out(db, s)


@router.post("/discovery/sessions/{sid}/reopen", response_model=SessionOut)
def reopen_session(sid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    s = get_scoped(db, DiscoverySession, sid, principal, "discovery.write")
    s.status, s.completed_at = "in_progress", None
    db.commit()
    return _session_out(db, s)


class StakeholderIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    role: str = Field(min_length=2, max_length=120)
    email: str | None = Field(None, max_length=320)
    influence: str = Field("medium", pattern="^(low|medium|high)$")
    notes: str | None = Field(None, max_length=4000)


class StakeholderOut(ORM):
    id: uuid.UUID
    session_id: uuid.UUID
    name: str
    role: str
    email: str | None
    influence: str
    notes: str | None


class ActionIn(BaseModel):
    description: str = Field(min_length=2, max_length=4000)
    owner: str | None = Field(None, max_length=200)
    due_date: date | None = None
    status: str = Field("open", pattern="^(open|done)$")


class ActionOut(ORM):
    id: uuid.UUID
    session_id: uuid.UUID
    description: str
    owner: str | None
    due_date: date | None
    status: str


@router.get("/discovery/sessions/{sid}/stakeholders", response_model=list[StakeholderOut])
def list_stakeholders(sid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    s = get_scoped(db, DiscoverySession, sid, principal, "discovery.read")
    return db.scalars(select(Stakeholder).where(Stakeholder.session_id == s.id).order_by(Stakeholder.created_at)).all()


@router.post("/discovery/sessions/{sid}/stakeholders", response_model=StakeholderOut, status_code=201)
def add_stakeholder(sid: uuid.UUID, body: StakeholderIn, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)):
    s = get_scoped(db, DiscoverySession, sid, principal, "discovery.write")
    st = Stakeholder(organisation_id=s.organisation_id, session_id=s.id, **body.model_dump())
    db.add(st)
    db.commit()
    return st


@router.delete("/stakeholders/{stid}", status_code=204)
def delete_stakeholder(stid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    st = get_scoped(db, Stakeholder, stid, principal, "discovery.write")
    db.delete(st)
    db.commit()


@router.get("/discovery/sessions/{sid}/actions", response_model=list[ActionOut])
def list_actions(sid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    s = get_scoped(db, DiscoverySession, sid, principal, "discovery.read")
    return db.scalars(select(ActionItem).where(ActionItem.session_id == s.id).order_by(ActionItem.created_at)).all()


@router.post("/discovery/sessions/{sid}/actions", response_model=ActionOut, status_code=201)
def add_action(sid: uuid.UUID, body: ActionIn, principal: Principal = Depends(get_principal),
               db: Session = Depends(get_db)):
    s = get_scoped(db, DiscoverySession, sid, principal, "discovery.write")
    a = ActionItem(organisation_id=s.organisation_id, session_id=s.id, **body.model_dump())
    db.add(a)
    db.commit()
    return a


@router.patch("/actions/{aid}", response_model=ActionOut)
def patch_action(aid: uuid.UUID, body: ActionIn, principal: Principal = Depends(get_principal),
                 db: Session = Depends(get_db)):
    a = get_scoped(db, ActionItem, aid, principal, "discovery.write")
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    db.commit()
    return a


# ------------------------------------------------------------------ requirements
class RequirementIn(BaseModel):
    session_id: uuid.UUID | None = None
    organisation_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    description: str = Field("", max_length=8000)
    category: str = Field(pattern="^(functional|non_functional|security|integration|data)$")
    priority: str = Field("should", pattern="^(must|should|could)$")
    acceptance_criteria: str = Field("", max_length=4000)


class RequirementPatch(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=300)
    description: str | None = Field(None, max_length=8000)
    category: str | None = Field(None, pattern="^(functional|non_functional|security|integration|data)$")
    priority: str | None = Field(None, pattern="^(must|should|could)$")
    acceptance_criteria: str | None = Field(None, max_length=4000)


@router.get("/requirements", response_model=list[RequirementOut])
def list_requirements(session_id: uuid.UUID | None = None, organisation_id: uuid.UUID | None = None,
                      project_id: uuid.UUID | None = None, status: str | None = None,
                      principal: Principal = Depends(require("discovery.read")), db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(Requirement), Requirement)
    for col, val in ((Requirement.session_id, session_id), (Requirement.organisation_id, organisation_id),
                     (Requirement.project_id, project_id), (Requirement.status, status)):
        if val:
            stmt = stmt.where(col == val)
    return db.scalars(stmt.order_by(Requirement.code)).all()


@router.post("/requirements", response_model=RequirementOut, status_code=201)
def create_requirement(body: RequirementIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("discovery.write", body.organisation_id)
    if body.session_id:
        get_scoped(db, DiscoverySession, body.session_id, principal)
    r = Requirement(**body.model_dump(), code=svc.next_requirement_code(db, body.organisation_id), source="manual")
    db.add(r)
    db.commit()
    return r


@router.patch("/requirements/{rid}", response_model=RequirementOut)
def patch_requirement(rid: uuid.UUID, body: RequirementPatch, principal: Principal = Depends(get_principal),
                      db: Session = Depends(get_db)):
    r = get_scoped(db, Requirement, rid, principal, "discovery.write")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    if r.status == "approved":  # editing an approved requirement sends it back for review
        r.status, r.approved_by, r.approved_at = "draft", None, None
    db.commit()
    return r


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")


@router.post("/requirements/{rid}/decision", response_model=RequirementOut)
def decide_requirement(rid: uuid.UUID, body: DecisionIn, request: Request, principal: Principal = Depends(get_principal),
                       db: Session = Depends(get_db)):
    r = get_scoped(db, Requirement, rid, principal, "requirements.approve")
    r.status = body.decision
    r.approved_by = principal.id if body.decision == "approved" else None
    r.approved_at = datetime.now(UTC) if body.decision == "approved" else None
    audit(db, principal.id, f"requirement.{body.decision}", "requirement", r.id, r.organisation_id, request=request)
    db.commit()
    return r


@router.delete("/requirements/{rid}", status_code=204)
def delete_requirement(rid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    r = get_scoped(db, Requirement, rid, principal, "discovery.write")
    if r.status == "approved":
        raise InvalidTransition("Approved requirements cannot be deleted; reject instead")
    db.delete(r)
    db.commit()


# ------------------------------------------------------------------ architecture
class ArchitectureOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    session_id: uuid.UUID | None
    project_id: uuid.UUID | None
    title: str
    version: int
    status: str
    content: dict
    mermaid: str
    source: str
    generated_model: str | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    review_notes: str | None
    created_at: datetime
    updated_at: datetime


class ArchGenerateIn(BaseModel):
    session_id: uuid.UUID


class ArchEditIn(BaseModel):
    title: str | None = Field(None, max_length=200)
    content: dict | None = None
    mermaid: str | None = Field(None, max_length=20000)


class ReviewIn(BaseModel):
    notes: str = Field(min_length=3, max_length=4000)


@router.get("/architecture", response_model=list[ArchitectureOut])
def list_architecture(session_id: uuid.UUID | None = None, organisation_id: uuid.UUID | None = None,
                      principal: Principal = Depends(require("architecture.read")), db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(ArchitectureDocument), ArchitectureDocument)
    if session_id:
        stmt = stmt.where(ArchitectureDocument.session_id == session_id)
    if organisation_id:
        stmt = stmt.where(ArchitectureDocument.organisation_id == organisation_id)
    return db.scalars(stmt.order_by(ArchitectureDocument.created_at.desc())).all()


@router.post("/architecture/generate", response_model=ArchitectureOut, status_code=201)
def generate_architecture(body: ArchGenerateIn, request: Request, principal: Principal = Depends(get_principal),
                          db: Session = Depends(get_db)):
    s = get_scoped(db, DiscoverySession, body.session_id, principal, "architecture.write")
    doc = _agent_call(lambda: svc.generate_architecture(db, s, principal.id))
    audit(db, principal.id, "architecture.generate", "architecture", doc.id, doc.organisation_id, request=request)
    db.commit()
    return doc


@router.get("/architecture/{aid}", response_model=ArchitectureOut)
def get_architecture(aid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return get_scoped(db, ArchitectureDocument, aid, principal, "architecture.read")


@router.put("/architecture/{aid}", response_model=ArchitectureOut)
def edit_architecture(aid: uuid.UUID, body: ArchEditIn, request: Request, principal: Principal = Depends(get_principal),
                      db: Session = Depends(get_db)):
    d = get_scoped(db, ArchitectureDocument, aid, principal, "architecture.write")
    if body.title is not None:
        d.title = body.title
    if body.content is not None:
        d.content = {**d.content, **body.content}
    if body.mermaid is not None:
        d.mermaid = body.mermaid
    d.source = "edited"
    if d.status == "reviewed":  # any edit invalidates the review
        d.status, d.reviewed_by, d.reviewed_at = "draft", None, None
    audit(db, principal.id, "architecture.edit", "architecture", d.id, d.organisation_id, request=request)
    db.commit()
    return d


@router.post("/architecture/{aid}/review", response_model=ArchitectureOut)
def review_architecture(aid: uuid.UUID, body: ReviewIn, request: Request, principal: Principal = Depends(get_principal),
                        db: Session = Depends(get_db)):
    d = get_scoped(db, ArchitectureDocument, aid, principal, "architecture.review")
    d.status, d.reviewed_by, d.reviewed_at, d.review_notes = "reviewed", principal.id, datetime.now(UTC), body.notes
    audit(db, principal.id, "architecture.review", "architecture", d.id, d.organisation_id, request=request)
    db.commit()
    return d


# ------------------------------------------------------------------ proposals
class ProposalOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    organisation_name: str | None = None
    session_id: uuid.UUID | None
    architecture_id: uuid.UUID | None
    title: str
    status: str
    current_version: int
    total_estimate: Decimal | None
    currency: str
    created_by: uuid.UUID | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    sent_at: datetime | None
    decided_at: datetime | None
    decision_comment: str | None
    created_at: datetime
    updated_at: datetime


class VersionOut(ORM):
    version: int
    source: str
    generated_model: str | None
    change_note: str
    author_id: uuid.UUID | None
    created_at: datetime


class ProposalDetail(ProposalOut):
    content: dict
    versions: list[VersionOut]
    project_id: uuid.UUID | None = None


class ProposalGenerateIn(BaseModel):
    session_id: uuid.UUID
    architecture_id: uuid.UUID


class ProposalEditIn(BaseModel):
    content: dict
    change_note: str = Field("", max_length=300)


class TransitionIn(BaseModel):
    status: str = Field(pattern="^(draft|in_review|approved|sent)$")


class CustomerDecisionIn(BaseModel):
    decision: str = Field(pattern="^(accepted|rejected)$")
    comment: str | None = Field(None, max_length=4000)


CUSTOMER_VISIBLE = ("sent", "accepted", "rejected")
EDITABLE_CONTENT = {"executive_summary", "business_problem", "proposed_solution", "technical_architecture",
                    "deliverables", "milestones", "team", "costs", "risks_and_assumptions", "acceptance_criteria",
                    "support_agreement", "timeline_weeks"}


def _visible_proposal(db: Session, pid: uuid.UUID, principal: Principal) -> Proposal:
    p = get_scoped(db, Proposal, pid, principal, "proposal.read")
    if not principal.is_internal and p.status not in CUSTOMER_VISIBLE:
        raise NotFound("Proposal not found")
    return p


def _detail(db: Session, p: Proposal, principal: Principal) -> ProposalDetail:
    versions = db.scalars(select(ProposalVersion).where(ProposalVersion.proposal_id == p.id)
                          .order_by(ProposalVersion.version.desc())).all()
    content = svc.current_content(db, p)
    if not principal.is_internal:
        content = {k: v for k, v in content.items() if k != "provenance"}
        versions = []
    project = db.scalar(select(Project.id).where(Project.proposal_id == p.id))
    base = ProposalOut.model_validate(p).model_dump()
    base["organisation_name"] = org_name_map(db, [p.organisation_id]).get(p.organisation_id)
    return ProposalDetail(**base, content=content, versions=[VersionOut.model_validate(v) for v in versions], project_id=project)


@router.get("/proposals", response_model=Page[ProposalOut])
def list_proposals(organisation_id: uuid.UUID | None = None, status: str | None = None, page: int = Query(1, ge=1),
                   page_size: int = Query(20, ge=1, le=100), principal: Principal = Depends(require("proposal.read")),
                   db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(Proposal), Proposal)
    if not principal.is_internal:
        stmt = stmt.where(Proposal.status.in_(CUSTOMER_VISIBLE))
    if organisation_id:
        stmt = stmt.where(Proposal.organisation_id == organisation_id)
    if status:
        stmt = stmt.where(Proposal.status == status)
    items, total = paginate(db, stmt.order_by(Proposal.updated_at.desc()), page, page_size)
    names = org_name_map(db, [i.organisation_id for i in items])
    return Page(items=[ProposalOut.model_validate(i).model_copy(update={"organisation_name": names.get(i.organisation_id)})
                       for i in items], total=total, page=page, page_size=page_size)


@router.post("/proposals/generate", response_model=ProposalDetail, status_code=201)
def generate_proposal(body: ProposalGenerateIn, request: Request, principal: Principal = Depends(get_principal),
                      db: Session = Depends(get_db)):
    s = get_scoped(db, DiscoverySession, body.session_id, principal, "proposal.write")
    arch = get_scoped(db, ArchitectureDocument, body.architecture_id, principal, "architecture.read")
    if arch.organisation_id != s.organisation_id:
        raise AppError("Architecture belongs to a different organisation", code="organisation_mismatch")
    p = _agent_call(lambda: svc.generate_proposal(db, s, arch, principal.id))
    audit(db, principal.id, "proposal.generate", "proposal", p.id, p.organisation_id, request=request)
    db.commit()
    return _detail(db, p, principal)


@router.get("/proposals/{pid}", response_model=ProposalDetail)
def get_proposal(pid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return _detail(db, _visible_proposal(db, pid, principal), principal)


@router.get("/proposals/{pid}/versions/{version}")
def get_version(pid: uuid.UUID, version: int, principal: Principal = Depends(get_principal),
                db: Session = Depends(get_db)):
    p = get_scoped(db, Proposal, pid, principal, "proposal.write")
    v = db.scalar(select(ProposalVersion).where(ProposalVersion.proposal_id == p.id, ProposalVersion.version == version))
    if v is None:
        raise NotFound("Version not found")
    return {"version": v.version, "content": v.content, "change_note": v.change_note, "source": v.source,
            "created_at": v.created_at}


@router.put("/proposals/{pid}", response_model=ProposalDetail)
def edit_proposal(pid: uuid.UUID, body: ProposalEditIn, request: Request, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)):
    p = get_scoped(db, Proposal, pid, principal, "proposal.write")
    unknown = set(body.content) - EDITABLE_CONTENT
    if unknown:
        raise AppError(f"Fields not editable: {sorted(unknown)}", code="invalid_fields")
    for c in body.content.get("costs", []):
        if not isinstance(c, dict) or "item" not in c or not isinstance(c.get("amount"), int | float) or c["amount"] < 0:
            raise AppError("Each cost needs an item and a non-negative amount", code="invalid_costs")
    svc.edit_proposal(db, p, body.content, body.change_note, principal.id)
    audit(db, principal.id, "proposal.edit", "proposal", p.id, p.organisation_id, {"version": p.current_version}, request)
    db.commit()
    return _detail(db, p, principal)


@router.post("/proposals/{pid}/transition", response_model=ProposalDetail)
def transition(pid: uuid.UUID, body: TransitionIn, request: Request, principal: Principal = Depends(get_principal),
               db: Session = Depends(get_db)):
    p = get_scoped(db, Proposal, pid, principal, "proposal.write")
    if body.status in ("approved", "sent") and not principal.has("proposal.approve", p.organisation_id):
        raise Forbidden("Only authorised engineers or project managers can approve or send proposals")
    if body.status == "approved" and p.created_by == principal.id and not principal.is_super_admin:
        # AI drafts generated by a user must be reviewed by someone else before approval.
        latest = db.scalar(select(ProposalVersion).where(ProposalVersion.proposal_id == p.id,
                                                         ProposalVersion.version == p.current_version))
        if latest and latest.source == "ai":
            raise Forbidden("An AI-generated draft must be approved by a different authorised reviewer")
    svc.transition_proposal(db, p, body.status, principal.id)
    audit(db, principal.id, f"proposal.{body.status}", "proposal", p.id, p.organisation_id, request=request)
    db.commit()
    return _detail(db, p, principal)


@router.post("/proposals/{pid}/decision", response_model=ProposalDetail)
def customer_decision(pid: uuid.UUID, body: CustomerDecisionIn, request: Request,
                      idempotency_key: str | None = Header(None), principal: Principal = Depends(get_principal),
                      db: Session = Depends(get_db)):
    """Customer accepts or rejects a sent proposal. Acceptance automatically creates the project."""
    p = _visible_proposal(db, pid, principal)
    principal.require("proposal.decide", p.organisation_id)

    def compute():
        svc.transition_proposal(db, p, body.decision, principal.id, body.comment)
        if body.decision == "accepted":
            svc.create_project_from_proposal(db, p, principal.id)
        else:
            from app.api.deps import provider_org
            from app.services.common import notify
            notify(db, provider_org(db).id, "proposal.rejected", f"Proposal rejected: {p.title}",
                   body.comment or "", link=f"/app/proposals/{p.id}", audience="internal")
        audit(db, principal.id, f"proposal.customer_{body.decision}", "proposal", p.id, p.organisation_id,
              {"comment": body.comment}, request)
        return _detail(db, p, principal)

    result = idempotent(db, principal.id, idempotency_key, f"proposal.decision:{pid}", body.model_dump(), compute)
    db.commit()
    return result


@router.get("/proposals/{pid}/pdf")
def proposal_pdf_export(pid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    p = _visible_proposal(db, pid, principal)
    org = db.get(Organisation, p.organisation_id)
    pdf = proposal_pdf(org.name, p, svc.current_content(db, p))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="proposal-{org.slug}-v{p.current_version}.pdf"'})
