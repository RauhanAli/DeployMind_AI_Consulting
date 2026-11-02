import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.agents.framework import AgentError, AgentRunner, provenance
from app.ai.agents.run import INCIDENT_AGENT, IncidentAgentIn
from app.api.deps import Principal, get_principal, get_scoped, provider_org, require, require_internal
from app.core.errors import AppError, Forbidden
from app.db.session import SessionLocal, get_db
from app.domain.workflow import (
    INCIDENT_FLOW,
    INCIDENT_SEVERITIES,
    SLA_HOURS,
    TICKET_FLOW,
    check_transition,
    sla_deadlines,
    sla_state,
)
from app.models import (
    AIApplication,
    Budget,
    Environment,
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    EvaluationRun,
    Incident,
    IncidentUpdate,
    ModelPricing,
    SupportTicket,
    TicketComment,
)
from app.schemas.common import ORM, Page
from app.services import operations as ops
from app.services.common import (
    audit,
    next_code,
    notify,
    org_name_map,
    paginate,
    record_activity,
    user_name_map,
)
from app.workers.tasks import enqueue_evaluation

router = APIRouter(tags=["run"])


# ------------------------------------------------------------------ monitoring
@router.get("/monitoring/overview")
def monitoring_overview(app_id: uuid.UUID | None = None, organisation_id: uuid.UUID | None = None,
                        hours: int = Query(24, ge=1, le=24 * 90), source: str = Query("real", pattern="^(real|demo|all)$"),
                        principal: Principal = Depends(require("monitoring.read")), db: Session = Depends(get_db)):
    ids = principal.org_ids()
    if organisation_id:
        principal.require("monitoring.read", organisation_id)
        ids = [organisation_id]
    if app_id:
        get_scoped(db, AIApplication, app_id, principal, "monitoring.read")
    return ops.monitoring_overview(db, ids, app_id=app_id, hours=hours, source=source)


@router.get("/monitoring/stream")
async def monitoring_stream(app_id: uuid.UUID | None = None, source: str = Query("real", pattern="^(real|demo|all)$"),
                            principal: Principal = Depends(require("monitoring.read"))):
    """SSE: pushes a fresh 1-hour overview every 5 seconds for the live dashboard."""
    ids = principal.org_ids()

    async def gen():
        for _ in range(720):
            with SessionLocal() as s:
                data = ops.monitoring_overview(s, ids, app_id=app_id, hours=1, source=source)
            yield f"event: overview\ndata: {json.dumps(data, default=str)}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ------------------------------------------------------------------ evaluations
class DatasetIn(BaseModel):
    app_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    description: str = Field("", max_length=4000)


class DatasetOut(ORM):
    id: uuid.UUID
    app_id: uuid.UUID
    name: str
    description: str
    case_count: int = 0
    created_at: datetime


class CaseIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    expected_answer: str = Field("", max_length=4000)
    expected_sources: list[str] = Field(default_factory=list)
    expected_keywords: list[str] = Field(default_factory=list)
    must_refuse: bool = False
    tags: list[str] = Field(default_factory=list)


class CaseOut(ORM):
    id: uuid.UUID
    question: str
    expected_answer: str
    expected_sources: list
    expected_keywords: list
    must_refuse: bool
    tags: list


class RunIn(BaseModel):
    dataset_id: uuid.UUID
    label: str = Field(min_length=2, max_length=200)
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    system_prompt: str | None = Field(None, max_length=8000)
    retrieval: dict | None = None
    llm_judge: bool = False
    baseline_run_id: uuid.UUID | None = None


class RunOut(ORM):
    id: uuid.UUID
    app_id: uuid.UUID
    dataset_id: uuid.UUID
    label: str
    status: str
    config: dict
    metrics: dict
    baseline_run_id: uuid.UUID | None
    regressions: list
    judge: str
    finished_at: datetime | None
    error: str | None
    created_at: datetime


class ResultOut(ORM):
    id: uuid.UUID
    case_id: uuid.UUID
    question: str | None = None
    answer: str
    retrieved_sources: list
    cited_sources: list
    metrics: dict
    passed: bool


@router.get("/evaluations/datasets", response_model=list[DatasetOut])
def list_datasets(app_id: uuid.UUID | None = None, principal: Principal = Depends(require("evaluation.read")),
                  db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(EvaluationDataset), EvaluationDataset)
    if app_id:
        stmt = stmt.where(EvaluationDataset.app_id == app_id)
    out = []
    for d in db.scalars(stmt.order_by(EvaluationDataset.created_at)).all():
        n = len(db.scalars(select(EvaluationCase.id).where(EvaluationCase.dataset_id == d.id)).all())
        out.append(DatasetOut.model_validate(d).model_copy(update={"case_count": n}))
    return out


@router.post("/evaluations/datasets", response_model=DatasetOut, status_code=201)
def create_dataset(body: DatasetIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    a = get_scoped(db, AIApplication, body.app_id, principal, "evaluation.write")
    d = EvaluationDataset(organisation_id=a.organisation_id, **body.model_dump())
    db.add(d)
    db.commit()
    return d


@router.get("/evaluations/datasets/{did}/cases", response_model=list[CaseOut])
def list_cases(did: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    d = get_scoped(db, EvaluationDataset, did, principal, "evaluation.read")
    return db.scalars(select(EvaluationCase).where(EvaluationCase.dataset_id == d.id).order_by(EvaluationCase.created_at)).all()


@router.post("/evaluations/datasets/{did}/cases", response_model=CaseOut, status_code=201)
def add_case(did: uuid.UUID, body: CaseIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    d = get_scoped(db, EvaluationDataset, did, principal, "evaluation.write")
    c = EvaluationCase(organisation_id=d.organisation_id, dataset_id=d.id, **body.model_dump())
    db.add(c)
    db.commit()
    return c


@router.delete("/evaluations/cases/{cid}", status_code=204)
def delete_case(cid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    c = get_scoped(db, EvaluationCase, cid, principal, "evaluation.write")
    db.delete(c)
    db.commit()


@router.post("/evaluations/runs", response_model=RunOut, status_code=202)
def start_run(body: RunIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    d = get_scoped(db, EvaluationDataset, body.dataset_id, principal, "evaluation.write")
    app = db.get(AIApplication, d.app_id)
    if body.provider and body.provider != "mock":
        from app.api.v1.knowledge import _check_provider
        _check_provider(body.provider)
    config = {"provider": body.provider or app.provider, "model": body.model or app.model,
              "prompt_version": body.prompt_version or app.prompt_version,
              "retrieval": {**app.retrieval_config, **(body.retrieval or {})}, "llm_judge": body.llm_judge,
              "grounded_mode": app.grounded_mode}
    if body.system_prompt:
        config["system_prompt"] = body.system_prompt
    run = EvaluationRun(organisation_id=d.organisation_id, app_id=app.id, dataset_id=d.id, label=body.label,
                        config=config, baseline_run_id=body.baseline_run_id, triggered_by=principal.id)
    db.add(run)
    db.flush()
    enqueue_evaluation(db, run.id)
    audit(db, principal.id, "evaluation.run", "evaluation_run", run.id, run.organisation_id, request=request)
    db.commit()
    db.refresh(run)
    return run


@router.get("/evaluations/runs", response_model=list[RunOut])
def list_runs(app_id: uuid.UUID | None = None, dataset_id: uuid.UUID | None = None,
              principal: Principal = Depends(require("evaluation.read")), db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(EvaluationRun), EvaluationRun)
    if app_id:
        stmt = stmt.where(EvaluationRun.app_id == app_id)
    if dataset_id:
        stmt = stmt.where(EvaluationRun.dataset_id == dataset_id)
    return db.scalars(stmt.order_by(EvaluationRun.created_at.desc()).limit(100)).all()


@router.get("/evaluations/runs/{rid}")
def get_run(rid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    run = get_scoped(db, EvaluationRun, rid, principal, "evaluation.read")
    rows = db.execute(select(EvaluationResult, EvaluationCase.question)
                      .join(EvaluationCase, EvaluationCase.id == EvaluationResult.case_id)
                      .where(EvaluationResult.run_id == run.id).order_by(EvaluationCase.created_at)).all()
    return {"run": RunOut.model_validate(run).model_dump(mode="json"),
            "results": [ResultOut.model_validate(r).model_copy(update={"question": q}).model_dump(mode="json")
                        for r, q in rows]}


@router.get("/evaluations/compare")
def compare_runs(run_ids: str = Query(..., description="Comma-separated run ids"),
                 principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    ids = [uuid.UUID(x) for x in run_ids.split(",") if x][:6]
    runs = [get_scoped(db, EvaluationRun, i, principal, "evaluation.read") for i in ids]
    keys = [*ops.METRIC_KEYS, "pass_rate", "latency_p50_ms", "latency_p95_ms", "total_cost_usd"]
    return {"runs": [{"id": str(r.id), "label": r.label, "config": r.config, "created_at": r.created_at} for r in runs],
            "metrics": {k: [r.metrics.get(k) for r in runs] for k in keys}}


# ------------------------------------------------------------------ incidents
class IncidentIn(BaseModel):
    organisation_id: uuid.UUID
    title: str = Field(min_length=3, max_length=300)
    description: str = Field("", max_length=8000)
    severity: str = Field(pattern="^sev[1-4]$")
    app_id: uuid.UUID | None = None
    environment_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    detected_at: datetime | None = None


class IncidentPatch(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=300)
    description: str | None = Field(None, max_length=8000)
    severity: str | None = Field(None, pattern="^sev[1-4]$")
    assignee_id: uuid.UUID | None = None
    root_cause: str | None = Field(None, max_length=8000)
    resolution: str | None = Field(None, max_length=8000)
    customer_impact: str | None = Field(None, max_length=4000)


class IncidentStatusIn(BaseModel):
    status: str
    message: str = Field(min_length=2, max_length=4000)
    notify_customer: bool = False


class IncidentNoteIn(BaseModel):
    message: str = Field(min_length=2, max_length=8000)
    public: bool = False


class IncidentOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    organisation_name: str | None = None
    project_id: uuid.UUID | None
    app_id: uuid.UUID | None
    environment_id: uuid.UUID | None
    code: str
    title: str
    description: str
    severity: str
    status: str
    assignee_id: uuid.UUID | None
    assignee_name: str | None = None
    detected_at: datetime
    identified_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    root_cause: str | None
    resolution: str | None
    customer_impact: str | None
    ai_analysis: dict
    created_at: datetime


class UpdateOut(ORM):
    id: uuid.UUID
    kind: str
    status: str | None
    message: str
    public: bool
    author_id: uuid.UUID | None
    author_name: str | None = None
    created_at: datetime


def _incident_out(db: Session, rows: list[Incident], principal: Principal) -> list[IncidentOut]:
    names = user_name_map(db, [r.assignee_id for r in rows])
    orgs = org_name_map(db, [r.organisation_id for r in rows])
    out = []
    for r in rows:
        o = IncidentOut.model_validate(r).model_copy(update={"assignee_name": names.get(r.assignee_id),
                                                             "organisation_name": orgs.get(r.organisation_id)})
        if not principal.is_internal:
            o = o.model_copy(update={"ai_analysis": {}, "description": ""})
        out.append(o)
    return out


@router.get("/incidents/meta")
def incidents_meta():
    return {"severities": INCIDENT_SEVERITIES, "flow": {k: sorted(v) for k, v in INCIDENT_FLOW.items()}}


@router.get("/incidents", response_model=Page[IncidentOut])
def list_incidents(organisation_id: uuid.UUID | None = None, status: str | None = None, severity: str | None = None,
                   page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                   principal: Principal = Depends(require("incident.read")), db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(Incident), Incident)
    if organisation_id:
        stmt = stmt.where(Incident.organisation_id == organisation_id)
    if status:
        stmt = stmt.where(Incident.status.in_(status.split(",")))
    if severity:
        stmt = stmt.where(Incident.severity == severity)
    items, total = paginate(db, stmt.order_by(Incident.detected_at.desc()), page, page_size)
    return Page(items=_incident_out(db, items, principal), total=total, page=page, page_size=page_size)


@router.post("/incidents", response_model=IncidentOut, status_code=201)
def create_incident(body: IncidentIn, request: Request, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)):
    principal.require("incident.write", body.organisation_id)
    for model, fid in ((AIApplication, body.app_id), (Environment, body.environment_id)):
        if fid and get_scoped(db, model, fid, principal).organisation_id != body.organisation_id:
            raise AppError("Linked resource belongs to another organisation", code="organisation_mismatch")
    inc = Incident(**body.model_dump(exclude={"detected_at"}), detected_at=body.detected_at or datetime.now(UTC),
                   code=next_code(db, Incident, body.organisation_id, "INC"), reported_by=principal.id, status="open")
    db.add(inc)
    db.flush()
    db.add(IncidentUpdate(organisation_id=inc.organisation_id, incident_id=inc.id, author_id=principal.id,
                          kind="status_change", status="open", message="Incident opened", created_at=datetime.now(UTC)))
    audit(db, principal.id, "incident.create", "incident", inc.id, inc.organisation_id, {"severity": inc.severity}, request)
    db.commit()
    return _incident_out(db, [inc], principal)[0]


@router.get("/incidents/{iid}", response_model=IncidentOut)
def get_incident(iid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return _incident_out(db, [get_scoped(db, Incident, iid, principal, "incident.read")], principal)[0]


@router.patch("/incidents/{iid}", response_model=IncidentOut)
def patch_incident(iid: uuid.UUID, body: IncidentPatch, request: Request, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    inc = get_scoped(db, Incident, iid, principal, "incident.write")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(inc, k, v)
    if "assignee_id" in changes:
        name = user_name_map(db, [inc.assignee_id]).get(inc.assignee_id, "nobody")
        db.add(IncidentUpdate(organisation_id=inc.organisation_id, incident_id=inc.id, author_id=principal.id,
                              kind="note", message=f"Assigned to {name}", created_at=datetime.now(UTC)))
    audit(db, principal.id, "incident.update", "incident", inc.id, inc.organisation_id, changes, request)
    db.commit()
    return _incident_out(db, [inc], principal)[0]


@router.post("/incidents/{iid}/status", response_model=IncidentOut)
def incident_status(iid: uuid.UUID, body: IncidentStatusIn, request: Request, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)):
    inc = get_scoped(db, Incident, iid, principal, "incident.write")
    check_transition(INCIDENT_FLOW, inc.status, body.status, "incident")
    if body.status == "resolved" and not (inc.resolution or "").strip():
        raise AppError("Record a resolution before resolving the incident", code="resolution_required")
    if body.status == "closed" and not (inc.root_cause or "").strip():
        raise AppError("Record the root cause before closing the incident", code="root_cause_required")
    now = datetime.now(UTC)
    inc.status = body.status
    if body.status == "identified":
        inc.identified_at = now
    elif body.status == "resolved":
        inc.resolved_at = now
    elif body.status == "closed":
        inc.closed_at = now
    db.add(IncidentUpdate(organisation_id=inc.organisation_id, incident_id=inc.id, author_id=principal.id,
                          kind="status_change", status=body.status, message=body.message, public=body.notify_customer,
                          created_at=now))
    if body.notify_customer:
        notify(db, inc.organisation_id, "incident.update", f"[{inc.code}] {inc.title}: {body.status}", body.message,
               link=f"/portal/incidents/{inc.id}")
    record_activity(db, inc.organisation_id, "incident", inc.id, "status_change", f"{inc.code} → {body.status}",
                    principal.id, customer_visible=body.notify_customer)
    audit(db, principal.id, "incident.status", "incident", inc.id, inc.organisation_id,
          {"status": body.status, "notified": body.notify_customer}, request)
    db.commit()
    return _incident_out(db, [inc], principal)[0]


@router.post("/incidents/{iid}/updates", response_model=UpdateOut, status_code=201)
def incident_note(iid: uuid.UUID, body: IncidentNoteIn, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)):
    inc = get_scoped(db, Incident, iid, principal, "incident.write")
    u = IncidentUpdate(organisation_id=inc.organisation_id, incident_id=inc.id, author_id=principal.id,
                       kind="customer_notification" if body.public else "note", message=body.message,
                       public=body.public, created_at=datetime.now(UTC))
    db.add(u)
    if body.public:
        notify(db, inc.organisation_id, "incident.update", f"[{inc.code}] Update: {inc.title}", body.message,
               link=f"/portal/incidents/{inc.id}")
    db.commit()
    return UpdateOut.model_validate(u).model_copy(update={"author_name": principal.user.full_name})


@router.get("/incidents/{iid}/updates", response_model=list[UpdateOut])
def incident_timeline(iid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    inc = get_scoped(db, Incident, iid, principal, "incident.read")
    q = select(IncidentUpdate).where(IncidentUpdate.incident_id == inc.id)
    if not principal.is_internal:
        q = q.where(IncidentUpdate.public.is_(True))
    rows = db.scalars(q.order_by(IncidentUpdate.created_at)).all()
    names = user_name_map(db, [r.author_id for r in rows])
    return [UpdateOut.model_validate(r).model_copy(update={"author_name": names.get(r.author_id)}) for r in rows]


@router.post("/incidents/{iid}/analyze", response_model=IncidentOut)
def analyze_incident(iid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    inc = get_scoped(db, Incident, iid, principal, "incident.write")
    env = db.get(Environment, inc.environment_id) if inc.environment_id else None
    try:
        outcome = AgentRunner(db, inc.organisation_id, app_id=inc.app_id).run(INCIDENT_AGENT, IncidentAgentIn(
            title=inc.title, description=inc.description, severity=inc.severity, detected_at=inc.detected_at,
            app_id=str(inc.app_id) if inc.app_id else None, environment=env.name if env else None))
    except AgentError as exc:
        raise AppError(f"Incident analysis failed: {exc}", code="ai_generation_failed")
    inc.ai_analysis = {**outcome.output.model_dump(), "provenance": provenance("incident_analysis_agent", outcome)}
    db.add(IncidentUpdate(organisation_id=inc.organisation_id, incident_id=inc.id, author_id=principal.id, kind="note",
                          message="AI incident analysis generated (advisory)", created_at=datetime.now(UTC)))
    db.commit()
    return _incident_out(db, [inc], principal)[0]


# ------------------------------------------------------------------ support
class TicketIn(BaseModel):
    organisation_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    subject: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=3, max_length=8000)
    category: str = Field("general", pattern="^(general|bug|question|feature_request|access|billing)$")
    priority: str = Field("medium", pattern="^(low|medium|high|urgent)$")


class TicketPatch(BaseModel):
    priority: str | None = Field(None, pattern="^(low|medium|high|urgent)$")
    assignee_id: uuid.UUID | None = None
    status: str | None = None
    resolution_notes: str | None = Field(None, max_length=8000)


class TicketCommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    internal: bool = False


class TicketOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    organisation_name: str | None = None
    project_id: uuid.UUID | None
    code: str
    subject: str
    description: str
    category: str
    priority: str
    status: str
    requester_id: uuid.UUID | None
    requester_name: str | None = None
    assignee_id: uuid.UUID | None
    assignee_name: str | None = None
    response_due_at: datetime
    resolution_due_at: datetime
    first_response_at: datetime | None
    resolved_at: datetime | None
    resolution_notes: str | None
    sla_response: str = ""
    sla_resolution: str = ""
    created_at: datetime
    updated_at: datetime


class TicketCommentOut(ORM):
    id: uuid.UUID
    author_id: uuid.UUID | None
    author_name: str | None = None
    body: str
    internal: bool
    created_at: datetime


def _tickets_out(db: Session, rows: list[SupportTicket]) -> list[TicketOut]:
    now = datetime.now(UTC)
    names = user_name_map(db, [r.requester_id for r in rows] + [r.assignee_id for r in rows])
    orgs = org_name_map(db, [r.organisation_id for r in rows])
    return [TicketOut.model_validate(r).model_copy(update={
        "requester_name": names.get(r.requester_id), "assignee_name": names.get(r.assignee_id),
        "organisation_name": orgs.get(r.organisation_id),
        "sla_response": sla_state(r.response_due_at, r.first_response_at, now),
        "sla_resolution": sla_state(r.resolution_due_at, r.resolved_at, now)}) for r in rows]


@router.get("/support/meta")
def support_meta():
    return {"sla_hours": {k: {"response": v[0], "resolution": v[1]} for k, v in SLA_HOURS.items()},
            "flow": {k: sorted(v) for k, v in TICKET_FLOW.items()}}


@router.get("/support/tickets", response_model=Page[TicketOut])
def list_tickets(organisation_id: uuid.UUID | None = None, status: str | None = None, priority: str | None = None,
                 assignee_id: uuid.UUID | None = None, q: str | None = None, page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=100), principal: Principal = Depends(require("support.read")),
                 db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(SupportTicket), SupportTicket)
    if organisation_id:
        stmt = stmt.where(SupportTicket.organisation_id == organisation_id)
    if status:
        stmt = stmt.where(SupportTicket.status.in_(status.split(",")))
    if priority:
        stmt = stmt.where(SupportTicket.priority == priority)
    if assignee_id:
        stmt = stmt.where(SupportTicket.assignee_id == assignee_id)
    if q:
        stmt = stmt.where(SupportTicket.subject.ilike(f"%{q}%"))
    items, total = paginate(db, stmt.order_by(SupportTicket.created_at.desc()), page, page_size)
    return Page(items=_tickets_out(db, items), total=total, page=page, page_size=page_size)


@router.post("/support/tickets", response_model=TicketOut, status_code=201)
def create_ticket(body: TicketIn, request: Request, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)):
    org_id = body.organisation_id or (next(iter(principal.customer_orgs)) if len(principal.customer_orgs) == 1 else None)
    if org_id is None:
        raise AppError("organisation_id is required", code="organisation_required")
    principal.require("support.write", org_id)
    now = datetime.now(UTC)
    resp, res = sla_deadlines(body.priority, now)
    t = SupportTicket(organisation_id=org_id, project_id=body.project_id, subject=body.subject,
                      description=body.description, category=body.category, priority=body.priority,
                      code=next_code(db, SupportTicket, org_id, "SUP"), requester_id=principal.id,
                      response_due_at=resp, resolution_due_at=res, status="open")
    db.add(t)
    db.flush()
    notify(db, provider_org(db).id, "ticket.created", f"[{t.code}] {t.subject}", f"Priority {t.priority}",
           link=f"/app/support/{t.id}", audience="internal")
    audit(db, principal.id, "ticket.create", "support_ticket", t.id, org_id, {"priority": t.priority}, request)
    db.commit()
    return _tickets_out(db, [t])[0]


@router.get("/support/tickets/{tid}", response_model=TicketOut)
def get_ticket(tid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return _tickets_out(db, [get_scoped(db, SupportTicket, tid, principal, "support.read")])[0]


@router.patch("/support/tickets/{tid}", response_model=TicketOut)
def patch_ticket(tid: uuid.UUID, body: TicketPatch, request: Request, principal: Principal = Depends(get_principal),
                 db: Session = Depends(get_db)):
    t = get_scoped(db, SupportTicket, tid, principal, "support.read")
    changes = body.model_dump(exclude_unset=True)
    is_manager = principal.has("support.manage", t.organisation_id)
    if not is_manager:
        # customers may only close their own resolved tickets or reopen them
        if set(changes) - {"status"} or changes.get("status") not in ("closed", "in_progress"):
            raise Forbidden("Missing permission: support.manage")
    if "status" in changes:
        check_transition(TICKET_FLOW, t.status, changes["status"], "ticket")
        if changes["status"] == "resolved":
            if not (changes.get("resolution_notes") or t.resolution_notes):
                raise AppError("Resolution notes are required to resolve a ticket", code="resolution_required")
            t.resolved_at = datetime.now(UTC)
            notify(db, t.organisation_id, "ticket.resolved", f"[{t.code}] resolved", changes.get("resolution_notes")
                   or t.resolution_notes or "", link=f"/portal/support/{t.id}")
        elif changes["status"] in ("in_progress", "open"):
            t.resolved_at = None
    if "priority" in changes and changes["priority"] != t.priority:
        t.response_due_at, t.resolution_due_at = sla_deadlines(changes["priority"], t.created_at)
    for k, v in changes.items():
        setattr(t, k, v)
    db.add(TicketComment(organisation_id=t.organisation_id, ticket_id=t.id, author_id=principal.id, internal=True,
                         body="Updated: " + ", ".join(f"{k}={v}" for k, v in changes.items())))
    audit(db, principal.id, "ticket.update", "support_ticket", t.id, t.organisation_id, changes, request)
    db.commit()
    return _tickets_out(db, [t])[0]


@router.get("/support/tickets/{tid}/comments", response_model=list[TicketCommentOut])
def ticket_comments(tid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    t = get_scoped(db, SupportTicket, tid, principal, "support.read")
    q = select(TicketComment).where(TicketComment.ticket_id == t.id)
    if not principal.is_internal:
        q = q.where(TicketComment.internal.is_(False))
    rows = db.scalars(q.order_by(TicketComment.created_at)).all()
    names = user_name_map(db, [r.author_id for r in rows])
    return [TicketCommentOut.model_validate(r).model_copy(update={"author_name": names.get(r.author_id)}) for r in rows]


@router.post("/support/tickets/{tid}/comments", response_model=TicketCommentOut, status_code=201)
def add_ticket_comment(tid: uuid.UUID, body: TicketCommentIn, principal: Principal = Depends(get_principal),
                       db: Session = Depends(get_db)):
    t = get_scoped(db, SupportTicket, tid, principal, "support.write")
    internal = body.internal and principal.is_internal  # customers can never post internal notes
    c = TicketComment(organisation_id=t.organisation_id, ticket_id=t.id, author_id=principal.id, body=body.body,
                      internal=internal)
    db.add(c)
    if principal.is_internal and not internal:
        if t.first_response_at is None:
            t.first_response_at = datetime.now(UTC)
        if t.status == "open":
            t.status = "in_progress"
        notify(db, t.organisation_id, "ticket.reply", f"[{t.code}] New reply", body.body[:500],
               link=f"/portal/support/{t.id}")
    elif not principal.is_internal and t.status == "waiting_on_customer":
        t.status = "in_progress"
    db.commit()
    return TicketCommentOut.model_validate(c).model_copy(update={"author_name": principal.user.full_name})


# ------------------------------------------------------------------ costs
class BudgetIn(BaseModel):
    organisation_id: uuid.UUID
    project_id: uuid.UUID | None = None
    monthly_limit_usd: Decimal = Field(gt=0)
    alert_threshold_pct: int = Field(80, ge=10, le=100)


class PricingIn(BaseModel):
    provider: str = Field(min_length=2, max_length=30)
    model: str = Field(min_length=1, max_length=120)
    input_per_million: Decimal = Field(ge=0)
    output_per_million: Decimal = Field(ge=0)
    effective_from: datetime | None = None
    notes: str = Field("", max_length=300)


@router.get("/costs/summary")
def costs_summary(days: int = Query(30, ge=1, le=365), organisation_id: uuid.UUID | None = None,
                  include_demo: bool = True, principal: Principal = Depends(require("cost.read")),
                  db: Session = Depends(get_db)):
    ids = principal.org_ids()
    if organisation_id:
        principal.require("cost.read", organisation_id)
        ids = [organisation_id]
    return ops.cost_summary(db, ids, days, include_demo)


@router.get("/costs/budgets")
def list_budgets(principal: Principal = Depends(require("cost.read")), db: Session = Depends(get_db)):
    rows = db.scalars(principal.scope_filter(select(Budget), Budget)).all()
    names = org_name_map(db, [b.organisation_id for b in rows])
    return [{"id": str(b.id), "organisation_id": str(b.organisation_id), "organisation_name": names.get(b.organisation_id),
             "project_id": str(b.project_id) if b.project_id else None, "monthly_limit_usd": float(b.monthly_limit_usd),
             "alert_threshold_pct": b.alert_threshold_pct, **ops.budget_status(db, b)} for b in rows]


@router.post("/costs/budgets", status_code=201)
def upsert_budget(body: BudgetIn, request: Request, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)):
    principal.require("cost.manage", body.organisation_id)
    b = db.scalar(select(Budget).where(Budget.organisation_id == body.organisation_id,
                                       Budget.project_id.is_(None) if body.project_id is None else Budget.project_id == body.project_id))
    if b is None:
        b = Budget(organisation_id=body.organisation_id, project_id=body.project_id, monthly_limit_usd=0)
        db.add(b)
    b.monthly_limit_usd, b.alert_threshold_pct = body.monthly_limit_usd, body.alert_threshold_pct
    audit(db, principal.id, "budget.upsert", "budget", None, body.organisation_id, body.model_dump(mode="json"), request)
    db.commit()
    return {"id": str(b.id), **ops.budget_status(db, b)}


@router.post("/costs/budgets/check")
def check_budgets_now(principal: Principal = Depends(require("cost.manage")), db: Session = Depends(get_db)):
    return {"alerts_raised": ops.check_budgets(db)}


@router.get("/costs/pricing")
def list_pricing(principal: Principal = Depends(require("cost.read")), db: Session = Depends(get_db)):
    rows = db.scalars(select(ModelPricing).order_by(ModelPricing.provider, ModelPricing.model,
                                                    ModelPricing.effective_from.desc())).all()
    return [{"id": str(r.id), "provider": r.provider, "model": r.model, "input_per_million": float(r.input_per_million),
             "output_per_million": float(r.output_per_million), "effective_from": r.effective_from, "notes": r.notes}
            for r in rows]


@router.post("/costs/pricing", status_code=201)
def add_pricing(body: PricingIn, request: Request, principal: Principal = Depends(require_internal),
                db: Session = Depends(get_db)):
    principal.require("cost.manage")
    eff = (body.effective_from or datetime.now(UTC)).date()
    row = db.scalar(select(ModelPricing).where(ModelPricing.provider == body.provider, ModelPricing.model == body.model,
                                               ModelPricing.effective_from == eff))
    if row is None:
        row = ModelPricing(provider=body.provider, model=body.model, effective_from=eff, input_per_million=0,
                           output_per_million=0)
        db.add(row)
    row.input_per_million, row.output_per_million, row.notes = body.input_per_million, body.output_per_million, body.notes
    audit(db, principal.id, "pricing.upsert", "model_pricing", None, None, body.model_dump(mode="json"), request)
    db.commit()
    return {"id": str(row.id)}
