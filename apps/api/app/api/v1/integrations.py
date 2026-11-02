import json
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal, get_scoped, require
from app.core.errors import NotFound, Unauthorized
from app.core.secrets import put_secret
from app.db.session import get_db
from app.models import Integration, IntegrationRun, Secret
from app.schemas.common import ORM, JobOut
from app.services import integrations as svc
from app.services.common import audit, org_name_map
from app.workers.tasks import enqueue_sync

router = APIRouter(tags=["integrations"])


class IntegrationIn(BaseModel):
    organisation_id: uuid.UUID
    project_id: uuid.UUID | None = None
    name: str = Field(min_length=2, max_length=200)
    kind: str
    description: str = Field("", max_length=4000)
    config: dict = Field(default_factory=dict)
    retry_policy: dict = Field(default_factory=lambda: {"max_attempts": 3, "backoff_seconds": 2})


class IntegrationPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    description: str | None = Field(None, max_length=4000)
    config: dict | None = None
    retry_policy: dict | None = None
    status: str | None = Field(None, pattern="^(inventory|configured|active|disabled)$")


class CredentialIn(BaseModel):
    value: str = Field(min_length=4, max_length=8000)


class IntegrationOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    organisation_name: str | None = None
    project_id: uuid.UUID | None
    name: str
    kind: str
    description: str
    config: dict
    status: str
    health: str
    retry_policy: dict
    has_credentials: bool = False
    credential_hint: str | None = None
    last_tested_at: datetime | None
    last_synced_at: datetime | None
    created_at: datetime


class RunOut(ORM):
    id: uuid.UUID
    kind: str
    status: str
    attempts: int
    records_processed: int
    latency_ms: int | None
    message: str
    error: str | None
    created_at: datetime


def _out(db: Session, rows: list[Integration]) -> list[IntegrationOut]:
    secret_ids = [r.credential_secret_id for r in rows if r.credential_secret_id]
    hints = dict(db.execute(select(Secret.id, Secret.fingerprint).where(Secret.id.in_(secret_ids))).all()) if secret_ids else {}
    names = org_name_map(db, [r.organisation_id for r in rows])
    return [IntegrationOut.model_validate(r).model_copy(update={
        "organisation_name": names.get(r.organisation_id), "has_credentials": bool(r.credential_secret_id),
        "credential_hint": hints.get(r.credential_secret_id)}) for r in rows]


@router.get("/integrations/kinds")
def kinds():
    return svc.KINDS


@router.get("/integrations", response_model=list[IntegrationOut])
def list_integrations(organisation_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None,
                      principal: Principal = Depends(require("integration.read")), db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(Integration), Integration)
    if organisation_id:
        stmt = stmt.where(Integration.organisation_id == organisation_id)
    if project_id:
        stmt = stmt.where(Integration.project_id == project_id)
    return _out(db, list(db.scalars(stmt.order_by(Integration.created_at)).all()))


@router.post("/integrations", response_model=IntegrationOut, status_code=201)
def create_integration(body: IntegrationIn, request: Request, principal: Principal = Depends(get_principal),
                       db: Session = Depends(get_db)):
    principal.require("integration.write", body.organisation_id)
    svc.validate_config(body.kind, body.config)
    i = Integration(**body.model_dump(), status="configured" if body.config else "inventory")
    db.add(i)
    db.flush()
    audit(db, principal.id, "integration.create", "integration", i.id, i.organisation_id, {"kind": i.kind}, request)
    db.commit()
    return _out(db, [i])[0]


@router.get("/integrations/{iid}", response_model=IntegrationOut)
def get_integration(iid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return _out(db, [get_scoped(db, Integration, iid, principal, "integration.read")])[0]


@router.patch("/integrations/{iid}", response_model=IntegrationOut)
def patch_integration(iid: uuid.UUID, body: IntegrationPatch, request: Request, principal: Principal = Depends(get_principal),
                      db: Session = Depends(get_db)):
    i = get_scoped(db, Integration, iid, principal, "integration.write")
    changes = body.model_dump(exclude_unset=True)
    if "config" in changes:
        svc.validate_config(i.kind, changes["config"])
    for k, v in changes.items():
        setattr(i, k, v)
    audit(db, principal.id, "integration.update", "integration", i.id, i.organisation_id, changes, request)
    db.commit()
    return _out(db, [i])[0]


@router.put("/integrations/{iid}/credentials", response_model=IntegrationOut)
def set_credentials(iid: uuid.UUID, body: CredentialIn, request: Request, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)):
    """Store credentials encrypted. The value is write-only and never returned by any endpoint."""
    i = get_scoped(db, Integration, iid, principal, "integration.write")
    secret = put_secret(db, i.organisation_id, f"integration:{i.id}", body.value, principal.id)
    i.credential_secret_id = secret.id
    if i.status == "inventory":
        i.status = "configured"
    audit(db, principal.id, "integration.credentials_set", "integration", i.id, i.organisation_id, request=request)
    db.commit()
    return _out(db, [i])[0]


@router.post("/integrations/{iid}/webhook-secret")
def rotate_webhook_secret(iid: uuid.UUID, request: Request, principal: Principal = Depends(get_principal),
                          db: Session = Depends(get_db)):
    """Generate a signing secret for an inbound webhook. Shown exactly once."""
    i = get_scoped(db, Integration, iid, principal, "integration.write")
    if i.kind != "webhook":
        raise NotFound("Not a webhook integration")
    value = "whsec_" + secrets.token_urlsafe(32)
    i.credential_secret_id = put_secret(db, i.organisation_id, f"integration:{i.id}", value, principal.id).id
    i.status = "configured"
    audit(db, principal.id, "integration.webhook_secret_rotated", "integration", i.id, i.organisation_id, request=request)
    db.commit()
    return {"secret": value, "endpoint": f"/api/v1/webhooks/{i.id}", "signature_header": "X-DeployMind-Signature",
            "algorithm": "sha256=HMAC_SHA256(secret, raw_body)", "note": "Store this secret now; it is not shown again."}


@router.post("/integrations/{iid}/test", response_model=RunOut)
def test_integration(iid: uuid.UUID, request: Request, principal: Principal = Depends(get_principal),
                     db: Session = Depends(get_db)):
    i = get_scoped(db, Integration, iid, principal, "integration.write")
    run = svc.execute(db, i, "test")
    audit(db, principal.id, "integration.test", "integration", i.id, i.organisation_id, {"status": run.status}, request)
    db.commit()
    return run


@router.post("/integrations/{iid}/sync", response_model=JobOut, status_code=202)
def sync_integration(iid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    i = get_scoped(db, Integration, iid, principal, "integration.write")
    job = enqueue_sync(db, i, principal.id)
    db.commit()
    db.refresh(job)
    return job


@router.get("/integrations/{iid}/runs", response_model=list[RunOut])
def integration_runs(iid: uuid.UUID, limit: int = Query(50, ge=1, le=200), principal: Principal = Depends(get_principal),
                     db: Session = Depends(get_db)):
    i = get_scoped(db, Integration, iid, principal, "integration.read")
    return db.scalars(select(IntegrationRun).where(IntegrationRun.integration_id == i.id)
                      .order_by(IntegrationRun.created_at.desc()).limit(limit)).all()


@router.delete("/integrations/{iid}", status_code=204)
def delete_integration(iid: uuid.UUID, request: Request, principal: Principal = Depends(get_principal),
                       db: Session = Depends(get_db)):
    i = get_scoped(db, Integration, iid, principal, "integration.write")
    if i.credential_secret_id:
        db.delete(db.get(Secret, i.credential_secret_id))
    audit(db, principal.id, "integration.delete", "integration", i.id, i.organisation_id, request=request)
    db.delete(i)
    db.commit()


# ------------------------------------------------------------------ inbound webhooks (HMAC verified)
@router.post("/webhooks/{iid}", status_code=202, tags=["webhooks"])
async def receive_webhook(iid: uuid.UUID, request: Request,
                          x_deploymind_signature: str | None = Header(None), db: Session = Depends(get_db)):
    body = await request.body()
    i = db.get(Integration, iid)
    if i is None or i.kind != "webhook" or i.status == "disabled":
        raise NotFound("Webhook not found")
    if not svc.verify_webhook(db, i, body, x_deploymind_signature):
        db.add(IntegrationRun(organisation_id=i.organisation_id, integration_id=i.id, kind="event", status="failed",
                              message="Rejected", error="Invalid signature"))
        db.commit()
        raise Unauthorized("Invalid webhook signature", code="invalid_signature")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        payload = {}
    db.add(IntegrationRun(organisation_id=i.organisation_id, integration_id=i.id, kind="event", status="succeeded",
                          records_processed=1, message=f"Event received: {str(payload.get('type', 'unknown'))[:80]}"))
    i.health, i.last_synced_at = "healthy", datetime.now(UTC)
    db.commit()
    return {"received": True}


# ------------------------------------------------------------------ mock external services (demo connectors)
MOCK_CONTACTS = [
    {"id": "c-101", "name": "Priya Raman", "email": "priya.raman@acme-ps.example", "title": "Head of Client Services"},
    {"id": "c-102", "name": "Tom Okafor", "email": "tom.okafor@acme-ps.example", "title": "IT Manager"},
    {"id": "c-103", "name": "Helen Grant", "email": "helen.grant@acme-ps.example", "title": "Operations Director"},
]
MOCK_TICKETS = [
    {"id": "T-5001", "subject": "Invoice query for March", "status": "open", "team": None},
    {"id": "T-5002", "subject": "Request access to client portal", "status": "open", "team": None},
    {"id": "T-5003", "subject": "Engagement letter template", "status": "closed", "team": "Legal"},
    {"id": "T-5004", "subject": "Timesheet system error", "status": "open", "team": None},
]
MOCK_DOCS = {
    "kb-1": {"filename": "remote-working-policy.txt", "title": "Remote Working Policy",
             "content": "Remote Working Policy\n\nEmployees may work remotely up to three days per week with manager "
                        "approval. Remote work requires a secure home network and use of the company VPN. Client "
                        "data must never be stored on personal devices. Equipment requests are raised through the "
                        "IT service desk and are fulfilled within five working days."},
}


def _mock_auth(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer dm_mock_"):
        raise Unauthorized("Mock service requires 'Authorization: Bearer dm_mock_...'", code="mock_auth_required")


@router.get("/mock-services/{service}/health", tags=["mock-services"])
def mock_health(service: str, authorization: str | None = Header(None)):
    _mock_auth(authorization)
    if service not in ("crm", "ticketing", "documents"):
        raise NotFound("Unknown mock service")
    return {"status": "ok", "service": f"mock-{service}", "note": "Mock service for demonstration connectors"}


@router.get("/mock-services/crm/contacts", tags=["mock-services"])
def mock_contacts(authorization: str | None = Header(None)):
    _mock_auth(authorization)
    return {"items": MOCK_CONTACTS}


@router.get("/mock-services/ticketing/tickets", tags=["mock-services"])
def mock_tickets(authorization: str | None = Header(None)):
    _mock_auth(authorization)
    return {"items": MOCK_TICKETS}


@router.get("/mock-services/documents/documents", tags=["mock-services"])
def mock_documents(authorization: str | None = Header(None)):
    _mock_auth(authorization)
    return {"items": [{"id": k, "filename": v["filename"], "title": v["title"]} for k, v in MOCK_DOCS.items()]}


@router.get("/mock-services/documents/documents/{doc_id}/content", tags=["mock-services"])
def mock_document_content(doc_id: str, authorization: str | None = Header(None)):
    from fastapi.responses import PlainTextResponse

    _mock_auth(authorization)
    if doc_id not in MOCK_DOCS:
        raise NotFound("Document not found")
    return PlainTextResponse(MOCK_DOCS[doc_id]["content"])
