import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal, get_scoped, require, require_internal
from app.core.errors import NotFound
from app.db.session import get_db
from app.domain.workflow import LEAD_PIPELINE, check_lead_transition
from app.models import Contact, DiscoveryCall, Lead, Organisation
from app.models.crm import Activity
from app.schemas.common import ORM, ActivityOut, Page
from app.services.common import apply_sort, audit, org_name_map, paginate, record_activity, user_name_map

router = APIRouter(tags=["crm"])


class LeadOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    organisation_name: str | None = None
    title: str
    status: str
    source: str
    owner_id: uuid.UUID | None
    owner_name: str | None = None
    primary_contact_id: uuid.UUID | None
    estimated_value: Decimal | None
    summary: str | None
    status_changed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LeadCreate(BaseModel):
    organisation_id: uuid.UUID | None = None
    organisation_name: str | None = Field(None, min_length=2, max_length=200)
    industry: str | None = Field(None, max_length=120)
    title: str = Field(min_length=2, max_length=200)
    source: str = Field("outbound", max_length=60)
    estimated_value: Decimal | None = Field(None, ge=0)
    summary: str | None = Field(None, max_length=4000)
    owner_id: uuid.UUID | None = None


class LeadPatch(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=200)
    owner_id: uuid.UUID | None = None
    estimated_value: Decimal | None = Field(None, ge=0)
    summary: str | None = Field(None, max_length=4000)
    source: str | None = Field(None, max_length=60)


class StatusIn(BaseModel):
    status: str
    note: str | None = Field(None, max_length=2000)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    kind: str = Field("note", pattern="^(note|call|email|meeting)$")


def _enrich(db: Session, leads: list[Lead]) -> list[LeadOut]:
    orgs = org_name_map(db, [ld.organisation_id for ld in leads])
    users = user_name_map(db, [ld.owner_id for ld in leads])
    return [LeadOut.model_validate(ld).model_copy(update={"organisation_name": orgs.get(ld.organisation_id),
                                                          "owner_name": users.get(ld.owner_id)}) for ld in leads]


@router.get("/crm/pipeline")
def pipeline(principal: Principal = Depends(require("crm.read")), db: Session = Depends(get_db)):
    leads = db.scalars(select(Lead).order_by(Lead.updated_at.desc())).all()
    enriched = _enrich(db, list(leads))
    return {"stages": LEAD_PIPELINE + ["lost"],
            "columns": {s: [ld.model_dump(mode="json") for ld in enriched if ld.status == s] for s in LEAD_PIPELINE + ["lost"]}}


@router.get("/crm/leads", response_model=Page[LeadOut])
def list_leads(q: str | None = None, status: str | None = None, owner_id: uuid.UUID | None = None,
               source: str | None = None, sort: str | None = None, page: int = Query(1, ge=1),
               page_size: int = Query(20, ge=1, le=100), principal: Principal = Depends(require("crm.read")),
               db: Session = Depends(get_db)):
    stmt = select(Lead).join(Organisation, Organisation.id == Lead.organisation_id)
    if q:
        stmt = stmt.where(or_(Lead.title.ilike(f"%{q}%"), Organisation.name.ilike(f"%{q}%"), Lead.summary.ilike(f"%{q}%")))
    if status:
        stmt = stmt.where(Lead.status.in_(status.split(",")))
    if owner_id:
        stmt = stmt.where(Lead.owner_id == owner_id)
    if source:
        stmt = stmt.where(Lead.source == source)
    stmt = apply_sort(stmt, Lead, sort, {"created_at", "updated_at", "status", "title", "estimated_value"})
    items, total = paginate(db, stmt, page, page_size)
    return Page(items=_enrich(db, items), total=total, page=page, page_size=page_size)


@router.post("/crm/leads", response_model=LeadOut, status_code=201)
def create_lead(body: LeadCreate, request: Request, principal: Principal = Depends(require("crm.write")),
                db: Session = Depends(get_db)):
    from app.api.v1.auth import _slugify

    if body.organisation_id:
        org = db.get(Organisation, body.organisation_id)
        if org is None or org.kind != "customer":
            raise NotFound("Organisation not found")
    else:
        if not body.organisation_name:
            from app.core.errors import AppError
            raise AppError("organisation_id or organisation_name is required", code="organisation_required")
        org = Organisation(name=body.organisation_name, slug=_slugify(body.organisation_name, db), kind="customer",
                           industry=body.industry)
        db.add(org)
        db.flush()
    lead = Lead(organisation_id=org.id, title=body.title, source=body.source, estimated_value=body.estimated_value,
                summary=body.summary, owner_id=body.owner_id or principal.id, status="new",
                status_changed_at=datetime.now(UTC))
    db.add(lead)
    db.flush()
    record_activity(db, org.id, "lead", lead.id, "system", "Lead created", principal.id)
    audit(db, principal.id, "lead.create", "lead", lead.id, org.id, request=request)
    db.commit()
    return _enrich(db, [lead])[0]


@router.get("/crm/leads/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return _enrich(db, [get_scoped(db, Lead, lead_id, principal, "crm.read")])[0]


@router.patch("/crm/leads/{lead_id}", response_model=LeadOut)
def patch_lead(lead_id: uuid.UUID, body: LeadPatch, request: Request, principal: Principal = Depends(get_principal),
               db: Session = Depends(get_db)):
    lead = get_scoped(db, Lead, lead_id, principal, "crm.write")
    changes = body.model_dump(exclude_unset=True)
    if "owner_id" in changes and changes["owner_id"] != lead.owner_id:
        name = user_name_map(db, [changes["owner_id"]]).get(changes["owner_id"], "unassigned")
        record_activity(db, lead.organisation_id, "lead", lead.id, "assignment", f"Assigned to {name}", principal.id)
    for k, v in changes.items():
        setattr(lead, k, v)
    audit(db, principal.id, "lead.update", "lead", lead.id, lead.organisation_id, changes, request)
    db.commit()
    return _enrich(db, [lead])[0]


@router.post("/crm/leads/{lead_id}/status", response_model=LeadOut)
def change_status(lead_id: uuid.UUID, body: StatusIn, request: Request, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)):
    lead = get_scoped(db, Lead, lead_id, principal, "crm.write")
    check_lead_transition(lead.status, body.status)
    old = lead.status
    lead.status, lead.status_changed_at = body.status, datetime.now(UTC)
    record_activity(db, lead.organisation_id, "lead", lead.id, "status_change",
                    f"Status {old} → {body.status}" + (f": {body.note}" if body.note else ""), principal.id,
                    {"from": old, "to": body.status})
    audit(db, principal.id, "lead.status", "lead", lead.id, lead.organisation_id, {"from": old, "to": body.status}, request)
    db.commit()
    return _enrich(db, [lead])[0]


@router.post("/crm/leads/{lead_id}/notes", response_model=ActivityOut, status_code=201)
def add_note(lead_id: uuid.UUID, body: NoteIn, principal: Principal = Depends(get_principal),
             db: Session = Depends(get_db)):
    lead = get_scoped(db, Lead, lead_id, principal, "crm.write")
    act = record_activity(db, lead.organisation_id, "lead", lead.id, body.kind, body.body, principal.id)
    db.commit()
    return ActivityOut.model_validate(act).model_copy(update={"actor_name": principal.user.full_name})


@router.get("/crm/leads/{lead_id}/activities", response_model=list[ActivityOut])
def lead_activities(lead_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    lead = get_scoped(db, Lead, lead_id, principal, "crm.read")
    acts = db.scalars(select(Activity).where(Activity.organisation_id == lead.organisation_id)
                      .order_by(Activity.created_at.desc()).limit(200)).all()
    names = user_name_map(db, [a.actor_id for a in acts])
    return [ActivityOut.model_validate(a).model_copy(update={"actor_name": names.get(a.actor_id)}) for a in acts]


# ------------------------------------------------------------------ contacts
class ContactIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=60)
    job_title: str | None = Field(None, max_length=120)
    is_primary: bool = False
    notes: str | None = Field(None, max_length=4000)


class ContactOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    job_title: str | None
    is_primary: bool
    notes: str | None
    created_at: datetime


@router.get("/organisations/{org_id}/contacts", response_model=list[ContactOut])
def list_contacts(org_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("crm.read", org_id)
    return db.scalars(select(Contact).where(Contact.organisation_id == org_id).order_by(Contact.full_name)).all()


@router.post("/organisations/{org_id}/contacts", response_model=ContactOut, status_code=201)
def create_contact(org_id: uuid.UUID, body: ContactIn, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    principal.require("crm.write", org_id)
    c = Contact(organisation_id=org_id, **body.model_dump())
    db.add(c)
    db.commit()
    return c


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: uuid.UUID, body: ContactIn, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    c = get_scoped(db, Contact, contact_id, principal, "crm.write")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return c


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: uuid.UUID, request: Request, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    c = get_scoped(db, Contact, contact_id, principal, "crm.write")
    audit(db, principal.id, "contact.delete", "contact", c.id, c.organisation_id, request=request)
    db.delete(c)
    db.commit()


# ------------------------------------------------------------------ discovery calls (bookings)
class CallPatch(BaseModel):
    status: str | None = Field(None, pattern="^(requested|confirmed|completed|cancelled)$")
    assigned_to: uuid.UUID | None = None
    organisation_id: uuid.UUID | None = None


class CallOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID | None
    full_name: str
    email: str
    company: str
    job_title: str | None
    phone: str | None
    topic: str
    message: str | None
    preferred_slot: datetime
    timezone: str
    status: str
    kind: str
    assigned_to: uuid.UUID | None
    created_at: datetime


@router.get("/crm/discovery-calls", response_model=list[CallOut])
def list_calls(status: str | None = None, principal: Principal = Depends(require_internal),
               db: Session = Depends(get_db)):
    principal.require("crm.read")
    stmt = select(DiscoveryCall)
    if status:
        stmt = stmt.where(DiscoveryCall.status == status)
    return db.scalars(stmt.order_by(DiscoveryCall.preferred_slot.desc()).limit(200)).all()


@router.patch("/crm/discovery-calls/{call_id}", response_model=CallOut)
def patch_call(call_id: uuid.UUID, body: CallPatch, request: Request, principal: Principal = Depends(require_internal),
               db: Session = Depends(get_db)):
    principal.require("crm.write")
    call = db.get(DiscoveryCall, call_id)
    if call is None:
        raise NotFound("Discovery call not found")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(call, k, v)
    audit(db, principal.id, "discovery_call.update", "discovery_call", call.id, call.organisation_id, changes, request)
    db.commit()
    return call
