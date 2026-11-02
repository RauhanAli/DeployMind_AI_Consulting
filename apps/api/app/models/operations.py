import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScoped, Timestamps, UUIDPk


class Environment(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "environments"
    __table_args__ = (UniqueConstraint("app_id", "name"),)

    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    app_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_applications.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(20), nullable=False)  # development|staging|production
    variables: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # non-secret env vars
    secret_refs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # ENV_NAME -> secret id
    resources: Mapped[dict] = mapped_column(
        JSONB, default=lambda: {"cpu": "0.5", "memory_mb": 512, "replicas": 1}, nullable=False
    )
    adapter: Mapped[str] = mapped_column(String(30), default="local_docker", nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="SET NULL", use_alter=True)
    )
    health_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    url: Mapped[str | None] = mapped_column(String(300))


class Deployment(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "deployments"

    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    image_tag: Mapped[str | None] = mapped_column(String(200))
    adapter: Mapped[str] = mapped_column(String(30), nullable=False)
    # pending|awaiting_approval|building|testing|releasing|healthy|unhealthy|failed|rolled_back|superseded|stopped
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    stage: Mapped[str | None] = mapped_column(String(30))
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rollback_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deployments.id", ondelete="SET NULL"))
    config_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    runtime: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # container id, port, url, run ids
    health_check: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DeploymentLog(UUIDPk, Base):
    __tablename__ = "deployment_logs"

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    level: Mapped[str] = mapped_column(String(10), default="info", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TelemetryEvent(UUIDPk, TenantScoped, Base):
    __tablename__ = "telemetry_events"
    __table_args__ = (Index("ix_telemetry_org_created", "organisation_id", "created_at"),)

    app_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_applications.id", ondelete="CASCADE"), index=True)
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deployments.id", ondelete="SET NULL"))
    environment: Mapped[str | None] = mapped_column(String(20))
    # platform = requests served by the DeployMind API itself, deployment = served via a deployed container,
    # demo_seed = synthetic data inserted by the demo seed (always labelled as such in the UI)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # rag_query|health_check|error
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # success|error
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retrieval_ms: Mapped[int | None] = mapped_column(Integer)
    retrieved_chunks: Mapped[int | None] = mapped_column(Integer)
    top_relevance: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str | None] = mapped_column(String(30))
    model: Mapped[str | None] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ModelUsage(UUIDPk, TenantScoped, Base):
    __tablename__ = "model_usage"
    __table_args__ = (Index("ix_model_usage_org_created", "organisation_id", "created_at"),)

    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    app_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_applications.id", ondelete="SET NULL"))
    agent: Mapped[str] = mapped_column(String(60), nullable=False)
    operation: Mapped[str] = mapped_column(String(30), default="chat", nullable=False)  # chat|embedding
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ModelPricing(UUIDPk, Timestamps, Base):
    __tablename__ = "model_pricing"
    __table_args__ = (UniqueConstraint("provider", "model", "effective_from"),)

    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_per_million: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    output_per_million: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str] = mapped_column(String(300), default="", nullable=False)


class Budget(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("organisation_id", "project_id"),)

    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    monthly_limit_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    alert_threshold_pct: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    last_alert_level: Mapped[int | None] = mapped_column(Integer)  # 80 / 100 for the current month
    last_alert_month: Mapped[str | None] = mapped_column(String(7))


class EvaluationDataset(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "evaluation_datasets"

    app_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_applications.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)


class EvaluationCase(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "evaluation_cases"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    expected_sources: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)  # document filenames
    expected_keywords: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    must_refuse: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class EvaluationRun(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "evaluation_runs"

    app_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)  # provider/model/prompt_version/retrieval snapshot
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    baseline_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="SET NULL"))
    regressions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    judge: Mapped[str] = mapped_column(String(30), default="deterministic", nullable=False)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class EvaluationResult(UUIDPk, Timestamps, Base):
    __tablename__ = "evaluation_results"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_cases.id", ondelete="CASCADE"), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_sources: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    cited_sources: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Incident(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "incidents"
    __table_args__ = (UniqueConstraint("organisation_id", "code"),)

    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    app_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_applications.id", ondelete="SET NULL"))
    environment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("environments.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # sev1..sev4
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reported_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    identified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    root_cause: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)
    customer_impact: Mapped[str | None] = mapped_column(Text)
    ai_analysis: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class IncidentUpdate(UUIDPk, TenantScoped, Base):
    __tablename__ = "incident_updates"

    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # status_change|note|customer_notification
    status: Mapped[str | None] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SupportTicket(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "support_tickets"
    __table_args__ = (UniqueConstraint("organisation_id", "code"),)

    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), default="general", nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)  # low|medium|high|urgent
    # open|in_progress|waiting_on_customer|resolved|closed
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    requester_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    response_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolution_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)


class TicketComment(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "ticket_comments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
