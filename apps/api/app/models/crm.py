import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScoped, Timestamps, UUIDPk


class Contact(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "contacts"

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(60))
    job_title: Mapped[str | None] = mapped_column(String(120))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class Lead(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "leads"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="new", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(60), default="website", nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    primary_contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    summary: Mapped[str | None] = mapped_column(Text)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Activity(UUIDPk, TenantScoped, Base):
    """Generic activity timeline entry (CRM notes, status changes, project logs)."""

    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_entity", "entity_type", "entity_id"),)

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # note|status_change|call|email|assignment|system
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    customer_visible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class DiscoveryCall(UUIDPk, Timestamps, Base):
    """Discovery-call bookings. May arrive from anonymous website visitors before an organisation exists."""

    __tablename__ = "discovery_calls"

    organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(60))
    topic: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    preferred_slot: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(60), default="UTC", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="requested", nullable=False)  # requested|confirmed|completed|cancelled
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), default="discovery", nullable=False)  # discovery | contact


class AssessmentQuestion(UUIDPk, Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (UniqueConstraint("key", "version"),)

    key: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    dimension: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    help_text: Mapped[str | None] = mapped_column(Text)
    qtype: Mapped[str] = mapped_column(String(20), nullable=False)  # single | multi | scale
    options: Mapped[list] = mapped_column(JSONB, nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    condition: Mapped[dict | None] = mapped_column(JSONB)  # {"question": key, "in": [values]}
    risk_flag: Mapped[str | None] = mapped_column(String(200))  # risk raised if the answer scores <= 1


class Assessment(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "assessments"

    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft|submitted|scored
    current_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    question_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    profile: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    classification: Mapped[str | None] = mapped_column(String(40))
    findings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # deterministic analysis
    report: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # LLM narrative
    report_status: Mapped[str] = mapped_column(String(20), default="none", nullable=False)  # none|pending|ready|failed
    report_model: Mapped[str | None] = mapped_column(String(120))


class AssessmentAnswer(UUIDPk, Timestamps, Base):
    __tablename__ = "assessment_answers"
    __table_args__ = (UniqueConstraint("assessment_id", "question_id"),)

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessment_questions.id"), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {"v": "x"} or {"v": ["a","b"]}


class AssessmentScore(UUIDPk, Base):
    __tablename__ = "assessment_scores"
    __table_args__ = (UniqueConstraint("assessment_id", "dimension"),)

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dimension: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    level: Mapped[str] = mapped_column(String(30), nullable=False)
    breakdown: Mapped[list] = mapped_column(JSONB, nullable=False)  # per-question contribution


class Opportunity(UUIDPk, Timestamps, TenantScoped, Base):
    __tablename__ = "opportunities"

    assessment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessments.id", ondelete="SET NULL"))
    catalog_key: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    business_impact: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..5
    implementation_complexity: Mapped[int] = mapped_column(Integer, nullable=False)
    effort_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    data_availability: Mapped[int] = mapped_column(Integer, nullable=False)
    integration_complexity: Mapped[int] = mapped_column(Integer, nullable=False)
    security_risk: Mapped[int] = mapped_column(Integer, nullable=False)
    roi_assumptions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    priority_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    reasoning: Mapped[dict] = mapped_column(JSONB, nullable=False)
    narrative: Mapped[str | None] = mapped_column(Text)  # AI-written explanation
    status: Mapped[str] = mapped_column(String(20), default="identified", nullable=False)
