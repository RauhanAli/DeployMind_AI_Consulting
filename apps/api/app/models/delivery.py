import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScoped, Timestamps, UUIDPk


class DiscoverySession(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "discovery_sessions"

    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)  # in_progress|completed
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    session_date: Mapped[date | None] = mapped_column(Date)
    # Structured questionnaire: business_problem, current_workflow, existing_systems, data_sources, apis,
    # user_roles, security_requirements, compliance_constraints, performance_expectations,
    # expected_outcomes, budget, timeline, acceptance_criteria
    answers: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    technical_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    meeting_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ai_analysis: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Stakeholder(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "stakeholders"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    influence: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class ActionItem(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "action_items"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)


class Requirement(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "requirements"
    __table_args__ = (UniqueConstraint("organisation_id", "code"),)

    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="SET NULL"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)  # functional|non_functional|security|integration|data
    priority: Mapped[str] = mapped_column(String(10), default="should", nullable=False)  # must|should|could
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft|approved|rejected
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)  # manual|ai
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="", nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Integration(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "integrations"

    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # rest_api|webhook|postgres|crm|ticketing|document_store
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # non-secret settings only
    credential_secret_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("secrets.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="inventory", nullable=False)  # inventory|configured|active|disabled
    health: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)  # unknown|healthy|degraded|failing
    retry_policy: Mapped[dict] = mapped_column(
        JSONB, default=lambda: {"max_attempts": 3, "backoff_seconds": 2}, nullable=False
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntegrationRun(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "integration_runs"

    integration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # test|sync
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # succeeded|failed
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    records_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


class ArchitectureDocument(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "architecture_documents"

    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="SET NULL"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL", use_alter=True, name="fk_architecture_documents_project_id")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft|reviewed
    content: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    mermaid: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="ai", nullable=False)
    generated_model: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)


class Proposal(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "proposals"

    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="SET NULL"))
    architecture_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("architecture_documents.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # draft -> in_review -> approved (internal) -> sent -> accepted | rejected
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    total_estimate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="GBP", nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(Text)


class ProposalVersion(UUIDPk, Timestamps, Base):
    __tablename__ = "proposal_versions"
    __table_args__ = (UniqueConstraint("proposal_id", "version"),)

    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    generated_model: Mapped[str | None] = mapped_column(String(120))
    change_note: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Project(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "projects"

    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proposals.id", ondelete="SET NULL"), unique=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stage: Mapped[str] = mapped_column(String(30), default="discovery", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active|on_hold|completed
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    start_date: Mapped[date | None] = mapped_column(Date)
    target_date: Mapped[date | None] = mapped_column(Date)


class Milestone(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "milestones"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|in_progress|done
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    customer_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


task_dependencies = Table(
    "task_dependencies",
    Base.metadata,
    Column("task_id", UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("depends_on_id", UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
)


class Task(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "tasks"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("milestones.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="todo", nullable=False)  # backlog|todo|in_progress|review|done
    priority: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    due_date: Mapped[date | None] = mapped_column(Date)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    customer_visible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class TaskComment(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "task_comments"

    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    internal: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
