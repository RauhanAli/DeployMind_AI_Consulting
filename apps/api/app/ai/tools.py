"""Read-only tools that agents may be authorised to call. Every tool is scoped to the caller's organisation."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.agents.framework import tool
from app.models import Assessment, Deployment, Environment, Integration, TelemetryEvent


@tool("org_integrations")
def org_integrations(db: Session, org_id: uuid.UUID) -> list[dict]:
    rows = db.scalars(select(Integration).where(Integration.organisation_id == org_id)).all()
    return [{"name": r.name, "kind": r.kind, "status": r.status, "health": r.health} for r in rows]


@tool("latest_assessment")
def latest_assessment(db: Session, org_id: uuid.UUID) -> dict | None:
    a = db.scalar(select(Assessment).where(Assessment.organisation_id == org_id, Assessment.status == "scored")
                  .order_by(Assessment.submitted_at.desc()).limit(1))
    if a is None:
        return None
    return {"overall": float(a.overall_score or 0), "classification": a.classification,
            "weakest": a.findings.get("weakest_dimensions", [])}


@tool("telemetry_window")
def telemetry_window(db: Session, org_id: uuid.UUID, app_id: str | None, start: str, end: str) -> dict:
    s, e = datetime.fromisoformat(start), datetime.fromisoformat(end)
    base = select(TelemetryEvent).where(TelemetryEvent.organisation_id == org_id,
                                        TelemetryEvent.created_at.between(s, e),
                                        TelemetryEvent.kind == "rag_query")
    if app_id:
        base = base.where(TelemetryEvent.app_id == uuid.UUID(app_id))
    sub = base.subquery()
    total, errors, p95 = db.execute(select(
        func.count(), func.count().filter(sub.c.status == "error"),
        func.percentile_cont(0.95).within_group(sub.c.latency_ms),
    ).select_from(sub)).one()
    top_errors = db.execute(select(sub.c.error, func.count()).select_from(sub).where(sub.c.error.is_not(None))
                            .group_by(sub.c.error).order_by(func.count().desc()).limit(3)).all()
    return {"requests": total, "errors": errors, "error_rate": round(errors / total, 3) if total else 0.0,
            "p95_latency_ms": round(p95 or 0), "top_errors": [{"error": er, "count": c} for er, c in top_errors]}


@tool("recent_deployments")
def recent_deployments(db: Session, org_id: uuid.UUID, app_id: str | None, before: str) -> list[dict]:
    b = datetime.fromisoformat(before)
    stmt = (select(Deployment, Environment.name).join(Environment, Environment.id == Deployment.environment_id)
            .where(Deployment.organisation_id == org_id, Deployment.created_at <= b,
                   Deployment.created_at >= b - timedelta(days=3))
            .order_by(Deployment.created_at.desc()).limit(5))
    if app_id:
        stmt = stmt.where(Environment.app_id == uuid.UUID(app_id))
    return [{"version": d.version, "environment": env, "status": d.status, "created_at": d.created_at.isoformat()}
            for d, env in db.execute(stmt).all()]
