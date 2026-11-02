import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base, TenantScoped, Timestamps, UUIDPk

DEFAULT_RETRIEVAL = {
    "top_k": 5,
    "vector_weight": 0.6,
    "keyword_weight": 0.4,
    "min_relevance": 0.2,
    "min_term_coverage": 0.34,
    "chunk_size": 800,
    "chunk_overlap": 120,
}


class AIApplication(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "ai_applications"

    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    kind: Mapped[str] = mapped_column(String(40), default="knowledge_assistant", nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="mock", nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="mock-grounded-1", nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.1, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=800, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), default="v1", nullable=False)
    grounded_mode: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    retrieval_config: Mapped[dict] = mapped_column(JSONB, default=lambda: dict(DEFAULT_RETRIEVAL), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft|active|archived


document_permissions = Table(
    "document_permissions",
    Base.metadata,
    Column("document_id", UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class Document(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "documents"

    app_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_applications.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="knowledge", nullable=False)  # knowledge|attachment|upload
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="uploaded", nullable=False)  # uploaded|processing|ready|failed
    error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # organisation = all members of the owning org; internal = provider staff only; restricted = listed users
    visibility: Mapped[str] = mapped_column(String(20), default="organisation", nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class DocumentChunk(UUIDPk, TenantScoped, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_document_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    app_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_applications.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    embedding = mapped_column(Vector(settings.embedding_dimensions), nullable=False)
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('english', content)", persisted=True))


class Conversation(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "conversations"

    app_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New conversation", nullable=False)


class Message(UUIDPk, TenantScoped, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user|assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    grounded: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    insufficient_evidence: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(30))
    model: Mapped[str | None] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[int | None] = mapped_column(Integer)  # 1 | -1
    feedback_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
