import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.ai.providers.base import ChatMessage, ProviderError
from app.ai.registry import PROVIDERS, provider_status
from app.api.deps import Principal, get_principal, get_scoped
from app.core.config import settings
from app.core.errors import AppError, NotFound, ServiceUnavailable
from app.db.session import get_db
from app.models import (
    AIApplication,
    Conversation,
    Document,
    DocumentChunk,
    Message,
    User,
    document_permissions,
)
from app.models.knowledge import DEFAULT_RETRIEVAL
from app.rag.assistant import DEFAULT_SYSTEM_PROMPT, answer_question
from app.rag.parsing import safe_filename, sniff
from app.rag.storage import get_storage, object_key
from app.schemas.common import ORM
from app.services.common import audit, org_name_map
from app.services.deployments import ensure_environments
from app.workers.tasks import enqueue_ingest

router = APIRouter(tags=["knowledge"])


class RetrievalConfig(BaseModel):
    top_k: int = Field(5, ge=1, le=20)
    vector_weight: float = Field(0.6, ge=0, le=1)
    keyword_weight: float = Field(0.4, ge=0, le=1)
    min_relevance: float = Field(0.2, ge=0, le=1)
    min_term_coverage: float = Field(0.34, ge=0, le=1)
    chunk_size: int = Field(800, ge=200, le=4000)
    chunk_overlap: int = Field(120, ge=0, le=1000)


class AppIn(BaseModel):
    organisation_id: uuid.UUID
    project_id: uuid.UUID | None = None
    name: str = Field(min_length=2, max_length=200)
    description: str = Field("", max_length=4000)
    provider: str = "mock"
    model: str = "mock-deterministic-1"
    temperature: float = Field(0.1, ge=0, le=1.5)
    max_output_tokens: int = Field(800, ge=64, le=4000)
    system_prompt: str = Field(DEFAULT_SYSTEM_PROMPT, max_length=8000)
    prompt_version: str = Field("v1", max_length=20)
    grounded_mode: bool = True
    retrieval_config: RetrievalConfig = RetrievalConfig()


class AppPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    description: str | None = Field(None, max_length=4000)
    provider: str | None = None
    model: str | None = Field(None, max_length=120)
    temperature: float | None = Field(None, ge=0, le=1.5)
    max_output_tokens: int | None = Field(None, ge=64, le=4000)
    system_prompt: str | None = Field(None, max_length=8000)
    prompt_version: str | None = Field(None, max_length=20)
    grounded_mode: bool | None = None
    retrieval_config: RetrievalConfig | None = None
    status: str | None = Field(None, pattern="^(draft|active|archived)$")


class AppOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    organisation_name: str | None = None
    project_id: uuid.UUID | None
    name: str
    description: str
    kind: str
    provider: str
    model: str
    temperature: float
    max_output_tokens: int
    system_prompt: str
    prompt_version: str
    grounded_mode: bool
    retrieval_config: dict
    status: str
    created_at: datetime
    updated_at: datetime


def _app_out(db: Session, a: AIApplication, principal: Principal) -> AppOut:
    out = AppOut.model_validate(a).model_copy(
        update={"organisation_name": org_name_map(db, [a.organisation_id]).get(a.organisation_id)})
    if not principal.is_internal:
        out = out.model_copy(update={"system_prompt": "(managed by DeployMind)"})
    return out


def _check_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise AppError(f"Unknown provider '{provider}'", code="invalid_provider")
    status = {p["provider"]: p["configured"] for p in provider_status()}
    if not status.get(provider):
        raise AppError(f"Provider '{provider}' has no API key configured on the server", code="provider_not_configured")


@router.get("/ai/providers")
def providers(principal: Principal = Depends(get_principal)):
    return {"active_default": settings.ai_provider, "mock_mode": settings.mock_ai, "providers": provider_status()}


@router.get("/apps", response_model=list[AppOut])
def list_apps(organisation_id: uuid.UUID | None = None, principal: Principal = Depends(get_principal),
              db: Session = Depends(get_db)):
    if not (principal.has("app.read") or principal.has("app.use")):
        raise NotFound("Not found")
    stmt = principal.scope_filter(select(AIApplication), AIApplication)
    if not principal.is_internal:
        stmt = stmt.where(AIApplication.status == "active")
    if organisation_id:
        stmt = stmt.where(AIApplication.organisation_id == organisation_id)
    return [_app_out(db, a, principal) for a in db.scalars(stmt.order_by(AIApplication.created_at.desc())).all()]


@router.post("/apps", response_model=AppOut, status_code=201)
def create_app(body: AppIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("app.write", body.organisation_id)
    _check_provider(body.provider)
    a = AIApplication(**body.model_dump(exclude={"retrieval_config"}), retrieval_config=body.retrieval_config.model_dump())
    db.add(a)
    db.flush()
    ensure_environments(db, a)
    audit(db, principal.id, "app.create", "ai_application", a.id, a.organisation_id, request=request)
    db.commit()
    return _app_out(db, a, principal)


def _get_app(db: Session, app_id: uuid.UUID, principal: Principal, write: bool = False) -> AIApplication:
    a = get_scoped(db, AIApplication, app_id, principal)
    if write:
        principal.require("app.write", a.organisation_id)
    elif not (principal.has("app.read", a.organisation_id) or principal.has("app.use", a.organisation_id)):
        raise NotFound("AIApplication not found")
    if not principal.is_internal and a.status != "active":
        raise NotFound("AIApplication not found")
    return a


@router.get("/apps/{app_id}", response_model=AppOut)
def get_app(app_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return _app_out(db, _get_app(db, app_id, principal), principal)


@router.patch("/apps/{app_id}", response_model=AppOut)
def patch_app(app_id: uuid.UUID, body: AppPatch, request: Request, principal: Principal = Depends(get_principal),
              db: Session = Depends(get_db)):
    a = _get_app(db, app_id, principal, write=True)
    changes = body.model_dump(exclude_unset=True)
    if "provider" in changes:
        _check_provider(changes["provider"])
    if "retrieval_config" in changes:
        changes["retrieval_config"] = body.retrieval_config.model_dump()
    for k, v in changes.items():
        setattr(a, k, v)
    audit(db, principal.id, "app.update", "ai_application", a.id, a.organisation_id,
          {k: v for k, v in changes.items() if k != "system_prompt"}, request)
    db.commit()
    return _app_out(db, a, principal)


# ------------------------------------------------------------------ documents
class DocumentOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    app_id: uuid.UUID | None
    kind: str
    filename: str
    title: str
    content_type: str
    size_bytes: int
    status: str
    error: str | None
    chunk_count: int
    visibility: str
    uploaded_by: uuid.UUID | None
    created_at: datetime
    allowed_user_ids: list[uuid.UUID] = []


def _doc_visible(d: Document, principal: Principal, db: Session) -> bool:
    if principal.is_internal or d.visibility == "organisation":
        return True
    if d.visibility == "restricted":
        return bool(db.scalar(select(document_permissions.c.user_id).where(
            document_permissions.c.document_id == d.id, document_permissions.c.user_id == principal.id)))
    return False


def _docs_out(db: Session, docs: list[Document]) -> list[DocumentOut]:
    ids = [d.id for d in docs]
    perms: dict[uuid.UUID, list[uuid.UUID]] = {}
    if ids:
        for did, uid in db.execute(select(document_permissions.c.document_id, document_permissions.c.user_id)
                                   .where(document_permissions.c.document_id.in_(ids))).all():
            perms.setdefault(did, []).append(uid)
    return [DocumentOut.model_validate(d).model_copy(update={"allowed_user_ids": perms.get(d.id, [])}) for d in docs]


@router.get("/apps/{app_id}/documents", response_model=list[DocumentOut])
def list_documents(app_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    a = _get_app(db, app_id, principal)
    principal.require("document.read", a.organisation_id)
    docs = db.scalars(select(Document).where(Document.app_id == a.id, Document.organisation_id == a.organisation_id)
                      .order_by(Document.created_at.desc())).all()
    return _docs_out(db, [d for d in docs if _doc_visible(d, principal, db)])


@router.post("/apps/{app_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(app_id: uuid.UUID, request: Request, file: UploadFile = File(...),
                          visibility: str = Form("organisation"), title: str | None = Form(None),
                          principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    a = _get_app(db, app_id, principal)
    principal.require("document.write", a.organisation_id)
    if visibility not in ("organisation", "internal", "restricted"):
        raise AppError("visibility must be organisation, internal or restricted", code="invalid_visibility")
    if visibility == "internal" and not principal.is_internal:
        raise AppError("Only DeployMind staff can upload internal-only documents", code="invalid_visibility")
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AppError(f"File exceeds {settings.max_upload_mb} MB", code="file_too_large")
    if not data:
        raise AppError("File is empty", code="empty_file")
    name = safe_filename(file.filename or "upload.txt")
    ctype = sniff(name, data)
    sha = hashlib.sha256(data).hexdigest()
    dup = db.scalar(select(Document).where(Document.app_id == a.id, Document.sha256 == sha))
    if dup:
        raise AppError(f"This file was already uploaded as '{dup.filename}'", code="duplicate_document")
    key = object_key(a.organisation_id, name)
    get_storage().put(key, data)
    d = Document(organisation_id=a.organisation_id, app_id=a.id, project_id=a.project_id,
                 kind="knowledge" if principal.is_internal else "upload", filename=name,
                 title=(title or name.rsplit(".", 1)[0]).strip()[:300], content_type=ctype, size_bytes=len(data),
                 sha256=sha, storage_key=key, status="uploaded", visibility=visibility, uploaded_by=principal.id)
    db.add(d)
    db.flush()
    if visibility == "restricted":
        db.execute(insert(document_permissions).values(document_id=d.id, user_id=principal.id))
    enqueue_ingest(db, d)
    audit(db, principal.id, "document.upload", "document", d.id, a.organisation_id,
          {"filename": name, "visibility": visibility, "size": len(data)}, request)
    db.commit()
    return _docs_out(db, [d])[0]


class DocPatch(BaseModel):
    title: str | None = Field(None, max_length=300)
    visibility: str | None = Field(None, pattern="^(organisation|internal|restricted)$")
    allowed_user_ids: list[uuid.UUID] | None = None


@router.patch("/documents/{doc_id}", response_model=DocumentOut)
def patch_document(doc_id: uuid.UUID, body: DocPatch, request: Request, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    d = get_scoped(db, Document, doc_id, principal, "document.write")
    if not _doc_visible(d, principal, db):
        raise NotFound("Document not found")
    if body.visibility == "internal" and not principal.is_internal:
        raise AppError("Only DeployMind staff can mark documents internal", code="invalid_visibility")
    if body.title is not None:
        d.title = body.title
    if body.visibility is not None:
        d.visibility = body.visibility
    if body.allowed_user_ids is not None:
        from app.models import Membership
        valid = set(db.scalars(select(Membership.user_id).where(Membership.organisation_id == d.organisation_id,
                                                               Membership.user_id.in_(body.allowed_user_ids))))
        if set(body.allowed_user_ids) - valid:
            raise AppError("Allowed users must be members of the document's organisation", code="invalid_users")
        db.execute(delete(document_permissions).where(document_permissions.c.document_id == d.id))
        for uid in valid:
            db.execute(insert(document_permissions).values(document_id=d.id, user_id=uid))
    audit(db, principal.id, "document.update", "document", d.id, d.organisation_id,
          body.model_dump(mode="json", exclude_unset=True), request)
    db.commit()
    return _docs_out(db, [d])[0]


@router.post("/documents/{doc_id}/reprocess", response_model=DocumentOut)
def reprocess(doc_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    d = get_scoped(db, Document, doc_id, principal, "document.write")
    d.status = "uploaded"
    enqueue_ingest(db, d)
    db.commit()
    return _docs_out(db, [d])[0]


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: uuid.UUID, request: Request, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)):
    d = get_scoped(db, Document, doc_id, principal, "document.write")
    if not _doc_visible(d, principal, db):
        raise NotFound("Document not found")
    get_storage().delete(d.storage_key)
    audit(db, principal.id, "document.delete", "document", d.id, d.organisation_id, {"filename": d.filename}, request)
    db.delete(d)
    db.commit()


@router.get("/documents/{doc_id}/chunks")
def document_chunks(doc_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    d = get_scoped(db, Document, doc_id, principal, "document.read")
    if not _doc_visible(d, principal, db):
        raise NotFound("Document not found")
    rows = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == d.id).order_by(DocumentChunk.ordinal)).all()
    return [{"ordinal": c.ordinal, "content": c.content, "token_count": c.token_count, "page": c.page} for c in rows]


@router.get("/documents/{doc_id}/download")
def download_document(doc_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    d = get_scoped(db, Document, doc_id, principal, "document.read")
    if not _doc_visible(d, principal, db):
        raise NotFound("Document not found")
    return Response(get_storage().get(d.storage_key), media_type=d.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{d.filename}"'})


# ------------------------------------------------------------------ chat
class ChatIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: uuid.UUID | None = None


class MessageOut(ORM):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    citations: list
    grounded: bool
    insufficient_evidence: bool
    provider: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: int | None
    feedback: int | None
    created_at: datetime


class ChatOut(BaseModel):
    conversation_id: uuid.UUID
    message: MessageOut
    retrieval: list[dict]
    is_mock: bool


class ConversationOut(ORM):
    id: uuid.UUID
    app_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


def chat_turn(db: Session, a: AIApplication, question: str, conversation_id: uuid.UUID | None, user_id: uuid.UUID | None,
              is_internal: bool, source: str = "platform", deployment_id=None, environment=None) -> ChatOut:
    if conversation_id:
        conv = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.app_id == a.id,
                                                    Conversation.organisation_id == a.organisation_id))
        if conv is None or conv.user_id != user_id:
            raise NotFound("Conversation not found")
    else:
        conv = Conversation(organisation_id=a.organisation_id, app_id=a.id, user_id=user_id, title=question[:80])
        db.add(conv)
        db.flush()
    history_rows = db.scalars(select(Message).where(Message.conversation_id == conv.id)
                              .order_by(Message.created_at.desc()).limit(6)).all()
    history = [ChatMessage(m.role, m.content) for m in reversed(history_rows)]
    now = datetime.now(UTC)
    db.add(Message(organisation_id=a.organisation_id, conversation_id=conv.id, role="user", content=question,
                   created_at=now))
    try:
        ans = answer_question(db, a, question, user_id=user_id, is_internal=is_internal, history=history,
                              source=source, deployment_id=deployment_id, environment=environment)
    except ProviderError as exc:
        db.commit()  # persist the failure telemetry
        raise ServiceUnavailable(f"The AI provider failed to respond: {exc}", code="ai_provider_error")
    msg = Message(organisation_id=a.organisation_id, conversation_id=conv.id, role="assistant", content=ans.answer,
                  citations=ans.citations, grounded=ans.grounded, insufficient_evidence=ans.insufficient_evidence,
                  provider=ans.provider, model=ans.model, input_tokens=ans.input_tokens, output_tokens=ans.output_tokens,
                  latency_ms=ans.latency_ms, created_at=datetime.now(UTC))
    db.add(msg)
    conv.updated_at = datetime.now(UTC)
    db.commit()
    return ChatOut(conversation_id=conv.id, message=MessageOut.model_validate(msg), is_mock=ans.is_mock,
                   retrieval=[{"title": c.title, "filename": c.filename, "ordinal": c.ordinal,
                               "relevance": c.relevance, "vector_similarity": c.vector_similarity,
                               "keyword_rank": c.keyword_rank} for c in ans.retrieved])


@router.post("/apps/{app_id}/chat", response_model=ChatOut)
def chat(app_id: uuid.UUID, body: ChatIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    a = _get_app(db, app_id, principal)
    principal.require("app.use", a.organisation_id)
    return chat_turn(db, a, body.question, body.conversation_id, principal.id, principal.is_internal)


@router.get("/apps/{app_id}/conversations", response_model=list[ConversationOut])
def list_conversations(app_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    a = _get_app(db, app_id, principal)
    principal.require("app.use", a.organisation_id)
    return db.scalars(select(Conversation).where(Conversation.app_id == a.id, Conversation.user_id == principal.id)
                      .order_by(Conversation.updated_at.desc()).limit(50)).all()


@router.get("/conversations/{cid}/messages", response_model=list[MessageOut])
def conversation_messages(cid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    c = get_scoped(db, Conversation, cid, principal, "app.use")
    # Conversations are private to their owner; only DeployMind staff may review them for support/quality.
    if c.user_id != principal.id and not (principal.is_internal and principal.has("app.read")):
        raise NotFound("Conversation not found")
    return db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at)).all()


class FeedbackIn(BaseModel):
    rating: int = Field(ge=-1, le=1)
    comment: str | None = Field(None, max_length=2000)


@router.post("/messages/{mid}/feedback", response_model=MessageOut)
def message_feedback(mid: uuid.UUID, body: FeedbackIn, principal: Principal = Depends(get_principal),
                     db: Session = Depends(get_db)):
    m = get_scoped(db, Message, mid, principal, "app.use")
    conv = db.get(Conversation, m.conversation_id)
    if conv.user_id != principal.id or m.role != "assistant":
        raise NotFound("Message not found")
    m.feedback = body.rating or None
    m.feedback_comment = body.comment
    db.commit()
    return m


@router.get("/apps/{app_id}/feedback")
def app_feedback(app_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    a = _get_app(db, app_id, principal)
    principal.require("app.read", a.organisation_id)
    rows = db.execute(select(Message, User.full_name).join(Conversation, Conversation.id == Message.conversation_id)
                      .outerjoin(User, User.id == Conversation.user_id)
                      .where(Conversation.app_id == a.id, Message.feedback.is_not(None))
                      .order_by(Message.created_at.desc()).limit(100)).all()
    up = sum(1 for m, _ in rows if m.feedback == 1)
    return {"positive": up, "negative": len(rows) - up,
            "items": [{"message_id": str(m.id), "rating": m.feedback, "comment": m.feedback_comment,
                       "answer": m.content[:300], "user": name, "created_at": m.created_at} for m, name in rows]}


@router.get("/apps/defaults/retrieval")
def retrieval_defaults():
    return DEFAULT_RETRIEVAL
