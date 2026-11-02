import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.registry import provider_status
from app.api.deps import Principal, get_principal, provider_org, require, require_internal
from app.core.config import settings
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.rbac import CUSTOMER_ROLES, INTERNAL_ROLES
from app.core.security import hash_password, password_policy_errors
from app.db.session import get_db
from app.deploy.adapters import effective_adapter_status
from app.domain.opportunities import DEFAULT_FINANCIAL_ASSUMPTIONS, DEFAULT_WEIGHTS
from app.domain.question_bank import COMPANY_SIZES, DIMENSIONS, PROFILE_OBJECTIVES
from app.models import (
    AIApplication,
    Assessment,
    AuditLog,
    Deployment,
    DiscoveryCall,
    Incident,
    Job,
    Lead,
    Membership,
    ModelUsage,
    Notification,
    Opportunity,
    Organisation,
    PlatformSetting,
    Project,
    Proposal,
    Role,
    SupportTicket,
    Task,
    User,
)
from app.models.crm import Activity
from app.schemas.common import ORM, ActivityOut, JobOut, Page
from app.services.common import audit, notify, org_name_map, paginate, user_name_map
from app.services.delivery import rate_card

router = APIRouter(tags=["platform"])


# ------------------------------------------------------------------ public (anonymous)
class DiscoveryCallIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    company: str = Field(min_length=2, max_length=200)
    job_title: str | None = Field(None, max_length=120)
    phone: str | None = Field(None, max_length=60)
    topic: str = Field(min_length=2, max_length=80)
    message: str | None = Field(None, max_length=4000)
    preferred_slot: datetime
    timezone: str = Field("UTC", max_length=60)
    kind: str = Field("discovery", pattern="^(discovery|contact)$")


class DiscoveryCallOut(ORM):
    id: uuid.UUID
    full_name: str
    email: str
    company: str
    job_title: str | None
    topic: str
    message: str | None
    preferred_slot: datetime
    timezone: str
    status: str
    kind: str
    organisation_id: uuid.UUID | None
    assigned_to: uuid.UUID | None
    created_at: datetime


@router.post("/public/discovery-calls", response_model=DiscoveryCallOut, status_code=201, tags=["public"])
def book_discovery_call(body: DiscoveryCallIn, request: Request, db: Session = Depends(get_db)):
    if body.kind == "discovery" and body.preferred_slot < datetime.now(UTC):
        raise AppError("Preferred slot must be in the future", code="invalid_slot")
    call = DiscoveryCall(**body.model_dump())
    db.add(call)
    db.flush()
    notify(db, provider_org(db).id, f"{body.kind}.requested",
           f"{'Discovery call' if body.kind == 'discovery' else 'Contact request'}: {body.company}",
           f"{body.full_name} <{body.email}> - {body.topic}", link="/app/crm?tab=calls", audience="internal")
    audit(db, None, f"public.{body.kind}_requested", "discovery_call", call.id, request=request)
    db.commit()
    return call


@router.get("/public/meta", tags=["public"])
def public_meta():
    return {"objectives": PROFILE_OBJECTIVES, "company_sizes": list(COMPANY_SIZES),
            "dimensions": [{"key": k, **v} for k, v in DIMENSIONS.items()], "mock_ai": settings.mock_ai,
            "ai_provider": settings.ai_provider}


# ------------------------------------------------------------------ organisations
class OrgOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    kind: str
    industry: str | None
    size: str | None
    website: str | None
    country: str | None
    description: str | None
    is_demo: bool
    created_at: datetime


class OrgSummary(OrgOut):
    lead_status: str | None = None
    lead_id: uuid.UUID | None = None
    readiness_score: float | None = None
    active_projects: int = 0


class OrgUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    industry: str | None = Field(None, max_length=120)
    size: str | None = Field(None, max_length=40)
    website: str | None = Field(None, max_length=300)
    country: str | None = Field(None, max_length=80)
    description: str | None = Field(None, max_length=4000)


@router.get("/organisations", response_model=Page[OrgSummary])
def list_organisations(q: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                       principal: Principal = Depends(require("org.read")), db: Session = Depends(get_db)):
    stmt = select(Organisation).where(Organisation.kind == "customer")
    ids = principal.org_ids()
    if ids is not None:
        stmt = stmt.where(Organisation.id.in_(ids))
    if q:
        stmt = stmt.where(or_(Organisation.name.ilike(f"%{q}%"), Organisation.industry.ilike(f"%{q}%")))
    items, total = paginate(db, stmt.order_by(Organisation.name), page, page_size)
    out = []
    for o in items:
        lead = db.scalar(select(Lead).where(Lead.organisation_id == o.id).order_by(Lead.created_at.desc()).limit(1))
        score = db.scalar(select(Assessment.overall_score).where(Assessment.organisation_id == o.id,
                                                                 Assessment.status == "scored")
                          .order_by(Assessment.submitted_at.desc()).limit(1))
        active = db.scalar(select(func.count()).select_from(Project).where(Project.organisation_id == o.id,
                                                                          Project.status == "active"))
        out.append(OrgSummary(**OrgOut.model_validate(o).model_dump(), lead_status=lead.status if lead else None,
                              lead_id=lead.id if lead else None, readiness_score=float(score) if score else None,
                              active_projects=active or 0))
    return Page(items=out, total=total, page=page, page_size=page_size)


@router.get("/organisations/{org_id}", response_model=OrgOut)
def get_organisation(org_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("org.read", org_id)
    org = db.get(Organisation, org_id)
    if org is None:
        raise NotFound("Organisation not found")
    return org


@router.patch("/organisations/{org_id}", response_model=OrgOut)
def update_organisation(org_id: uuid.UUID, body: OrgUpdate, request: Request,
                        principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("org.read", org_id)
    if not (principal.has("org.manage") or principal.has("users.manage", org_id)):
        raise Forbidden("Missing permission: org.manage")
    org = db.get(Organisation, org_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(org, k, v)
    audit(db, principal.id, "organisation.update", "organisation", org.id, org.id, changes, request)
    db.commit()
    return org


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None


class MemberIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    role: str
    temporary_password: str = Field(min_length=10, max_length=128)


@router.get("/organisations/{org_id}/members", response_model=list[MemberOut])
def list_members(org_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("org.read", org_id)
    rows = db.execute(select(User, Role.key).join(Membership, Membership.user_id == User.id)
                      .join(Role, Role.id == Membership.role_id).where(Membership.organisation_id == org_id)
                      .order_by(User.full_name)).all()
    return [MemberOut(user_id=u.id, email=u.email, full_name=u.full_name, role=r, is_active=u.is_active,
                      last_login_at=u.last_login_at) for u, r in rows]


@router.post("/organisations/{org_id}/members", response_model=MemberOut, status_code=201)
def add_member(org_id: uuid.UUID, body: MemberIn, request: Request, principal: Principal = Depends(get_principal),
               db: Session = Depends(get_db)):
    principal.require("org.read", org_id)
    if not principal.has("users.manage", org_id):
        raise Forbidden("Missing permission: users.manage")
    org = db.get(Organisation, org_id)
    allowed = INTERNAL_ROLES if org.kind == "provider" else CUSTOMER_ROLES
    if body.role not in allowed:
        raise AppError(f"Role '{body.role}' is not assignable in this organisation. Allowed: {allowed}",
                       code="invalid_role")
    if body.role == "super_admin" and not principal.is_super_admin:
        raise Forbidden("Only super admins can grant super admin")
    if errs := password_policy_errors(body.temporary_password):
        raise AppError("Password " + ", ".join(errs), code="weak_password")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None:
        user = User(email=body.email.lower(), full_name=body.full_name,
                    password_hash=hash_password(body.temporary_password))
        db.add(user)
        db.flush()
    elif db.scalar(select(Membership).where(Membership.user_id == user.id)):
        raise Conflict("User already belongs to an organisation", code="already_member")
    role = db.scalar(select(Role).where(Role.key == body.role))
    db.add(Membership(user_id=user.id, organisation_id=org_id, role_id=role.id))
    audit(db, principal.id, "membership.create", "user", user.id, org_id, {"role": body.role}, request)
    db.commit()
    return MemberOut(user_id=user.id, email=user.email, full_name=user.full_name, role=body.role,
                     is_active=user.is_active, last_login_at=user.last_login_at)


@router.get("/organisations/{org_id}/journey")
def organisation_journey(org_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    """End-to-end engagement view used by both the internal dashboard and the customer portal."""
    principal.require("org.read", org_id)
    customer = not principal.is_internal
    org = db.get(Organisation, org_id)
    if org is None:
        raise NotFound("Organisation not found")
    assessments = db.scalars(select(Assessment).where(Assessment.organisation_id == org_id)
                             .order_by(Assessment.created_at.desc())).all()
    opps = db.scalars(select(Opportunity).where(Opportunity.organisation_id == org_id).order_by(Opportunity.rank)).all()
    pq = select(Proposal).where(Proposal.organisation_id == org_id)
    if customer:
        pq = pq.where(Proposal.status.in_(["sent", "accepted", "rejected"]))
    proposals = db.scalars(pq.order_by(Proposal.created_at.desc())).all()
    projects = db.scalars(select(Project).where(Project.organisation_id == org_id)).all()
    apps = db.scalars(select(AIApplication).where(AIApplication.organisation_id == org_id)).all()
    deps = db.execute(select(Deployment).where(Deployment.organisation_id == org_id)
                      .order_by(Deployment.created_at.desc()).limit(10)).scalars().all()
    incidents = db.scalars(select(Incident).where(Incident.organisation_id == org_id)
                           .order_by(Incident.detected_at.desc())).all()
    tickets = db.scalars(select(SupportTicket).where(SupportTicket.organisation_id == org_id)
                         .order_by(SupportTicket.created_at.desc())).all()
    aq = select(Activity).where(Activity.organisation_id == org_id)
    if customer:
        aq = aq.where(Activity.customer_visible.is_(True))
    activity = db.scalars(aq.order_by(Activity.created_at.desc()).limit(30)).all()
    stages = [
        {"key": "assess", "label": "Assessment", "done": any(a.status == "scored" for a in assessments)},
        {"key": "opportunities", "label": "Opportunities", "done": bool(opps)},
        {"key": "proposal", "label": "Proposal", "done": any(p.status == "accepted" for p in proposals)},
        {"key": "build", "label": "Build", "done": any(p.stage in ("testing", "deployment", "production", "handover")
                                                      for p in projects)},
        {"key": "deploy", "label": "Deploy", "done": any(d.status == "healthy" for d in deps)},
        {"key": "run", "label": "Run", "done": any(p.stage in ("production", "handover") for p in projects)},
    ]
    names = user_name_map(db, [a.actor_id for a in activity])
    return {
        "organisation": OrgOut.model_validate(org).model_dump(mode="json"), "stages": stages,
        "assessments": [{"id": str(a.id), "status": a.status, "overall_score": float(a.overall_score) if a.overall_score
                         else None, "classification": a.classification, "submitted_at": a.submitted_at,
                         "report_status": a.report_status} for a in assessments],
        "opportunities": [{"id": str(o.id), "title": o.title, "rank": o.rank, "priority_score": float(o.priority_score),
                           "status": o.status} for o in opps],
        "proposals": [{"id": str(p.id), "title": p.title, "status": p.status, "total_estimate":
                       float(p.total_estimate or 0), "currency": p.currency, "sent_at": p.sent_at} for p in proposals],
        "projects": [{"id": str(p.id), "name": p.name, "stage": p.stage, "status": p.status,
                      "target_date": p.target_date} for p in projects],
        "applications": [{"id": str(a.id), "name": a.name, "status": a.status} for a in apps],
        "deployments": [{"id": str(d.id), "version": d.version, "status": d.status, "created_at": d.created_at,
                         "is_demo": d.is_demo} for d in deps],
        "incidents": [{"id": str(i.id), "code": i.code, "title": i.title, "severity": i.severity, "status": i.status,
                       "detected_at": i.detected_at} for i in incidents],
        "tickets": [{"id": str(t.id), "code": t.code, "subject": t.subject, "status": t.status,
                     "priority": t.priority} for t in tickets],
        "activity": [ActivityOut.model_validate(a).model_copy(update={"actor_name": names.get(a.actor_id)})
                     .model_dump(mode="json") for a in activity],
    }


# ------------------------------------------------------------------ users (staff directory for assignment)
@router.get("/users/staff", response_model=list[MemberOut])
def staff_directory(principal: Principal = Depends(require_internal), db: Session = Depends(get_db)):
    return list_members(provider_org(db).id, principal, db)


# ------------------------------------------------------------------ notifications & jobs
class NotificationOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str | None
    audience: str
    read_at: datetime | None
    created_at: datetime


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(unread: bool = False, principal: Principal = Depends(get_principal),
                       db: Session = Depends(get_db)):
    if principal.is_internal:
        stmt = select(Notification).where(Notification.audience == "internal")
    else:
        stmt = select(Notification).where(Notification.organisation_id.in_(principal.org_ids()),
                                          Notification.audience == "customer")
    stmt = stmt.where(or_(Notification.user_id.is_(None), Notification.user_id == principal.id))
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    return db.scalars(stmt.order_by(Notification.created_at.desc()).limit(50)).all()


@router.post("/notifications/{nid}/read", status_code=204)
def mark_read(nid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    n = db.get(Notification, nid)
    visible = n and ((n.audience == "internal" and principal.is_internal) or
                     (n.audience == "customer" and principal.can_access_org(n.organisation_id) and not principal.is_internal))
    if not visible:
        raise NotFound("Notification not found")
    n.read_at = datetime.now(UTC)
    db.commit()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None or (job.organisation_id and not principal.can_access_org(job.organisation_id)):
        raise NotFound("Job not found")
    return job


# ------------------------------------------------------------------ dashboard overview
@router.get("/dashboard/overview")
def dashboard_overview(principal: Principal = Depends(require_internal), db: Session = Depends(get_db)):
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    count = lambda m, *w: db.scalar(select(func.count()).select_from(m).where(*w)) or 0  # noqa: E731
    tasks_total = count(Task)
    tasks_done = count(Task, Task.status == "done")
    usage = db.execute(select(func.count(), func.coalesce(func.sum(ModelUsage.input_tokens + ModelUsage.output_tokens), 0),
                              func.coalesce(func.sum(ModelUsage.cost_usd), 0))
                       .where(ModelUsage.created_at >= month_start)).one()
    pipeline = dict(db.execute(select(Lead.status, func.count()).group_by(Lead.status)).all())
    recent = db.scalars(select(Activity).order_by(Activity.created_at.desc()).limit(15)).all()
    orgs = org_name_map(db, [a.organisation_id for a in recent])
    names = user_name_map(db, [a.actor_id for a in recent])
    projects = db.scalars(select(Project).where(Project.status == "active")).all()
    return {
        "total_customers": count(Organisation, Organisation.kind == "customer"),
        "active_projects": len(projects),
        "pending_proposals": count(Proposal, Proposal.status.in_(["draft", "in_review", "approved", "sent"])),
        "deployments": {"total": count(Deployment),
                        "healthy": count(Deployment, Deployment.status == "healthy"),
                        "awaiting_approval": count(Deployment, Deployment.status == "awaiting_approval")},
        "open_incidents": count(Incident, Incident.status.in_(["open", "investigating", "identified"])),
        "open_tickets": count(SupportTicket, SupportTicket.status.in_(["open", "in_progress", "waiting_on_customer"])),
        "discovery_calls_requested": count(DiscoveryCall, DiscoveryCall.status == "requested"),
        "ai_usage_month": {"requests": usage[0], "tokens": int(usage[1]), "estimated_cost_usd": float(usage[2] or Decimal(0))},
        "task_completion": {"done": tasks_done, "total": tasks_total,
                            "percent": round(tasks_done / tasks_total * 100) if tasks_total else 0},
        "pipeline": pipeline,
        "projects": [{"id": str(p.id), "name": p.name, "stage": p.stage, "organisation_id": str(p.organisation_id)}
                     for p in projects],
        "recent_activity": [{"id": str(a.id), "message": a.message, "kind": a.kind, "entity_type": a.entity_type,
                             "entity_id": str(a.entity_id), "organisation": orgs.get(a.organisation_id),
                             "actor": names.get(a.actor_id), "created_at": a.created_at.isoformat()} for a in recent],
        "mock_ai": settings.mock_ai,
    }


# ------------------------------------------------------------------ audit logs
class AuditOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    actor_name: str | None = None
    action: str
    resource_type: str
    resource_id: str | None
    details: dict
    ip_address: str | None
    request_id: str | None
    created_at: datetime


@router.get("/audit-logs", response_model=Page[AuditOut])
def audit_logs(action: str | None = None, organisation_id: uuid.UUID | None = None, actor_id: uuid.UUID | None = None,
               since_days: int = Query(30, ge=1, le=365), page: int = Query(1, ge=1),
               page_size: int = Query(50, ge=1, le=100),
               principal: Principal = Depends(require("audit.read")), db: Session = Depends(get_db)):
    stmt = select(AuditLog).where(AuditLog.created_at >= datetime.now(UTC) - timedelta(days=since_days))
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    if organisation_id:
        stmt = stmt.where(AuditLog.organisation_id == organisation_id)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    items, total = paginate(db, stmt.order_by(AuditLog.created_at.desc()), page, page_size)
    names = user_name_map(db, [i.actor_id for i in items])
    return Page(items=[AuditOut.model_validate(i).model_copy(update={"actor_name": names.get(i.actor_id)})
                       for i in items], total=total, page=page, page_size=page_size)


# ------------------------------------------------------------------ settings
class SettingIn(BaseModel):
    value: dict


SETTING_DEFAULTS = {"opportunity_weights": DEFAULT_WEIGHTS, "financial_assumptions": DEFAULT_FINANCIAL_ASSUMPTIONS}


@router.get("/settings")
def get_settings(principal: Principal = Depends(require_internal), db: Session = Depends(get_db)):
    stored = {s.key: s.value for s in db.scalars(select(PlatformSetting)).all()}
    return {
        "ai": {"provider": settings.ai_provider, "mock_mode": settings.mock_ai, "providers": provider_status(),
               "embedding_provider": settings.embedding_provider, "embedding_dimensions": settings.embedding_dimensions},
        "deployment_adapters": effective_adapter_status(),
        "opportunity_weights": {**DEFAULT_WEIGHTS, **stored.get("opportunity_weights", {})},
        "financial_assumptions": {**DEFAULT_FINANCIAL_ASSUMPTIONS, **stored.get("financial_assumptions", {})},
        "rate_card": rate_card(db),
        "environment": settings.app_env,
    }


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingIn, request: Request, principal: Principal = Depends(require("settings.manage")),
                db: Session = Depends(get_db)):
    if key not in ("opportunity_weights", "financial_assumptions", "rate_card"):
        raise NotFound("Unknown setting")
    if key == "opportunity_weights":
        unknown = set(body.value) - set(DEFAULT_WEIGHTS)
        if unknown or any(not isinstance(v, int | float) or v < 0 for v in body.value.values()):
            raise AppError("Weights must be non-negative numbers for known factors",
                           details={"allowed": list(DEFAULT_WEIGHTS)}, code="invalid_weights")
        if sum(body.value.values()) <= 0:
            raise AppError("At least one weight must be positive", code="invalid_weights")
    row = db.get(PlatformSetting, key) or PlatformSetting(key=key, value={})
    row.value = body.value
    db.merge(row)
    audit(db, principal.id, "settings.update", "setting", key, None, body.value, request)
    db.commit()
    return {"key": key, "value": body.value}
