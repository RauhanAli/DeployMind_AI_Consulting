import logging
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, Forbidden, InvalidTransition
from app.core.secrets import read_secret
from app.core.security import hash_token
from app.db.session import SessionLocal
from app.deploy.adapters import AdapterError, AdapterNotConfigured, DeployContext, get_adapter
from app.models import AIApplication, Deployment, DeploymentLog, Environment, TelemetryEvent
from app.services.common import audit, record_activity

log = logging.getLogger("deploymind.deploy")

ACTIVE = ("pending", "awaiting_approval", "building", "testing", "releasing")
ENV_NAMES = ("development", "staging", "production")


def ensure_environments(db: Session, app: AIApplication) -> list[Environment]:
    existing = {e.name: e for e in db.scalars(select(Environment).where(Environment.app_id == app.id)).all()}
    for name in ENV_NAMES:
        if name not in existing:
            env = Environment(organisation_id=app.organisation_id, project_id=app.project_id, app_id=app.id, name=name,
                              adapter=settings.deploy_adapter, requires_approval=name == "production",
                              variables={"LOG_LEVEL": "info" if name == "production" else "debug"},
                              resources={"cpu": "1" if name == "production" else "0.5",
                                         "memory_mb": 1024 if name == "production" else 512,
                                         "replicas": 2 if name == "production" else 1})
            db.add(env)
            existing[name] = env
    db.flush()
    return [existing[n] for n in ENV_NAMES]


def next_version(db: Session, env: Environment) -> str:
    n = db.scalar(select(func.count()).select_from(Deployment).where(Deployment.environment_id == env.id)) or 0
    return f"v1.0.{n + 1}"


def trigger(db: Session, env: Environment, actor_id: uuid.UUID, *, rollback_of: Deployment | None = None) -> Deployment:
    busy = db.scalar(select(Deployment).where(Deployment.environment_id == env.id, Deployment.status.in_(ACTIVE)))
    if busy:
        raise InvalidTransition(f"Deployment {busy.version} is already in progress for {env.name}")
    app = db.get(AIApplication, env.app_id)
    dep = Deployment(
        organisation_id=env.organisation_id, environment_id=env.id, version=next_version(db, env),
        adapter=env.adapter, status="awaiting_approval" if env.requires_approval else "pending",
        triggered_by=actor_id, rollback_of_id=rollback_of.id if rollback_of else None,
        image_tag=rollback_of.image_tag if rollback_of else None,
        config_snapshot={"variables": env.variables, "secret_names": sorted(env.secret_refs), "resources": env.resources,
                         "app": {"provider": app.provider, "model": app.model, "prompt_version": app.prompt_version,
                                 "grounded_mode": app.grounded_mode, "retrieval": app.retrieval_config}},
    )
    db.add(dep)
    db.flush()
    _log(db, dep.id, "queued", "Rollback requested" if rollback_of else "Deployment requested")
    if dep.status == "awaiting_approval":
        _log(db, dep.id, "approval", f"{env.name} requires approval from a user with deployment.approve")
    return dep


def approve(db: Session, dep: Deployment, actor_id: uuid.UUID, is_super_admin: bool) -> Deployment:
    if dep.status != "awaiting_approval":
        raise InvalidTransition("Deployment is not awaiting approval")
    if dep.triggered_by == actor_id and not is_super_admin:
        raise Forbidden("Production deployments require approval by a different person (four-eyes rule)")
    dep.status, dep.approved_by, dep.approved_at = "pending", actor_id, datetime.now(UTC)
    _log(db, dep.id, "approval", "Approved")
    return dep


def reject(db: Session, dep: Deployment, actor_id: uuid.UUID, reason: str) -> Deployment:
    if dep.status != "awaiting_approval":
        raise InvalidTransition("Deployment is not awaiting approval")
    dep.status, dep.error, dep.finished_at = "cancelled", f"Rejected: {reason}", datetime.now(UTC)
    _log(db, dep.id, "approval", f"Rejected by approver: {reason}", "warning")
    return dep


def _log(db: Session, dep_id: uuid.UUID, stage: str, message: str, level: str = "info") -> None:
    db.add(DeploymentLog(deployment_id=dep_id, stage=stage, level=level, message=message[:4000],
                         created_at=datetime.now(UTC)))


def _env_vars(db: Session, env: Environment, app: AIApplication, dep: Deployment, token: str) -> dict:
    out = {k: str(v) for k, v in env.variables.items()}
    for name, secret_id in env.secret_refs.items():
        out[name] = read_secret(db, env.organisation_id, uuid.UUID(secret_id))
    out.update({"PLATFORM_URL": settings.platform_url_from_container, "DEPLOYMENT_TOKEN": token,
                "APP_ID": str(app.id), "APP_NAME": app.name, "ENVIRONMENT": env.name, "APP_VERSION": dep.version})
    return out


def run_pipeline(deployment_id: uuid.UUID) -> None:
    """Executed by a Celery worker. Uses its own sessions and commits logs as it goes so the UI can stream them."""
    db = SessionLocal()
    try:
        dep = db.get(Deployment, deployment_id)
        if dep is None or dep.status != "pending":
            return
        env = db.get(Environment, dep.environment_id)
        app = db.get(AIApplication, env.app_id)
        previous = db.get(Deployment, env.current_deployment_id) if env.current_deployment_id else None

        def logf(stage: str, message: str, level: str = "info") -> None:
            _log(db, dep.id, stage, message, level)
            db.commit()

        def set_stage(status: str) -> None:
            dep.status = dep.stage = status
            db.commit()

        dep.started_at = datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        try:
            adapter = get_adapter(dep.adapter)
            logf("queued", f"Adapter: {adapter.honest_label}")
            ctx = DeployContext(
                deployment_id=str(dep.id), environment_id=str(env.id), environment=env.name, app_id=str(app.id),
                version=dep.version, image_tag=dep.image_tag, env_vars=_env_vars(db, env, app, dep, token),
                resources=env.resources, previous_runtime=(previous.runtime if previous else {}),
            )
            if dep.image_tag:
                logf("build", f"Re-using image {dep.image_tag} (rollback) - build and test skipped")
                image = dep.image_tag
            else:
                set_stage("building")
                image = adapter.build(ctx, logf)
                dep.image_tag = image
                set_stage("testing")
                adapter.test(ctx, image, logf)
            set_stage("releasing")
            # The token must be valid before the health check calls back into the platform.
            dep.runtime = {"token_hash": hash_token(token)}
            db.commit()
            runtime = adapter.release(ctx, image, logf)
            dep.runtime = {**runtime, "token_hash": hash_token(token)}
            dep.health_check = runtime.pop("health", {}) or {}
            dep.status, dep.stage, dep.finished_at = "healthy", "complete", datetime.now(UTC)
            if previous and previous.id != dep.id:
                previous.status = "rolled_back" if dep.rollback_of_id else "superseded"
                previous.runtime = {k: v for k, v in previous.runtime.items() if k != "token_hash"}
            env.current_deployment_id = dep.id
            env.health_status = "healthy"
            env.url = dep.runtime.get("url")
            env.last_health_check_at = datetime.now(UTC)
            db.add(TelemetryEvent(organisation_id=env.organisation_id, app_id=app.id, deployment_id=dep.id,
                                  environment=env.name, source="deployment", kind="health_check", status="success",
                                  latency_ms=0, created_at=datetime.now(UTC)))
            record_activity(db, env.organisation_id, "project", app.project_id or app.id, "system",
                            f"{app.name} {dep.version} deployed to {env.name}", None,
                            {"deployment_id": str(dep.id)}, customer_visible=env.name == "production")
            logf("complete", f"Deployment {dep.version} is live at {env.url}")
        except (AdapterError, AdapterNotConfigured, AppError) as exc:
            db.rollback()
            dep = db.get(Deployment, deployment_id)
            dep.status, dep.error, dep.finished_at = "failed", str(exc)[:2000], datetime.now(UTC)
            dep.runtime = {}
            _log(db, dep.id, dep.stage or "pipeline", f"FAILED: {exc}", "error")
            db.commit()
            log.warning("deployment_failed", extra={"deployment_id": str(deployment_id), "error": str(exc)[:300]})
            return
        db.commit()
    except Exception:
        db.rollback()
        dep = db.get(Deployment, deployment_id)
        if dep:
            dep.status, dep.error, dep.finished_at = "failed", "Internal pipeline error", datetime.now(UTC)
            dep.runtime = {}
            _log(db, dep.id, "pipeline", "FAILED: internal pipeline error (see worker logs)", "error")
            db.commit()
        log.exception("deployment_pipeline_crashed", extra={"deployment_id": str(deployment_id)})
    finally:
        db.close()


def rollback(db: Session, env: Environment, actor_id: uuid.UUID) -> Deployment:
    current = db.get(Deployment, env.current_deployment_id) if env.current_deployment_id else None
    target = db.scalar(
        select(Deployment).where(Deployment.environment_id == env.id, Deployment.image_tag.is_not(None),
                                 Deployment.status.in_(["superseded", "rolled_back"]),
                                 Deployment.id != (current.id if current else None), Deployment.is_demo.is_(False))
        .order_by(Deployment.created_at.desc()).limit(1)
    )
    if target is None:
        raise AppError("No previous successful release is available to roll back to", code="no_rollback_target")
    dep = trigger(db, env, actor_id, rollback_of=target)
    dep.status = "pending"  # rollbacks are an emergency action and skip the approval gate
    _log(db, dep.id, "approval", f"Rollback to {target.version} ({target.image_tag}) - approval gate bypassed")
    return dep


def health_check(db: Session, env: Environment) -> dict:
    dep = db.get(Deployment, env.current_deployment_id) if env.current_deployment_id else None
    if dep is None or not dep.runtime.get("url") and dep.adapter != "aws_ecs":
        env.health_status = "not_deployed"
        return {"status": "not_deployed"}
    if dep.is_demo:
        return {"status": env.health_status, "note": "Seeded demo deployment; no live runtime to probe"}
    try:
        ok, details = get_adapter(dep.adapter).health(dep.runtime)
    except AdapterNotConfigured as exc:
        ok, details = False, {"error": str(exc)}
    env.health_status = "healthy" if ok else "unhealthy"
    env.last_health_check_at = datetime.now(UTC)
    dep.health_check = details
    if dep.status in ("healthy", "unhealthy"):
        dep.status = "healthy" if ok else "unhealthy"
    db.add(TelemetryEvent(organisation_id=env.organisation_id, app_id=env.app_id, deployment_id=dep.id,
                          environment=env.name, source="deployment", kind="health_check",
                          status="success" if ok else "error", latency_ms=0,
                          error=None if ok else str(details)[:300], created_at=datetime.now(UTC)))
    return {"status": env.health_status, "details": details}


def stop(db: Session, env: Environment, actor_id: uuid.UUID) -> None:
    dep = db.get(Deployment, env.current_deployment_id) if env.current_deployment_id else None
    if dep is None:
        raise AppError("Nothing is deployed to this environment", code="not_deployed")
    if not dep.is_demo and (dep.runtime.get("container_id") or dep.runtime.get("service")):
        # Container removal runs on the worker, which owns the Docker socket / cloud credentials.
        from app.workers.tasks import enqueue_stop

        enqueue_stop(db, dep.adapter, {k: v for k, v in dep.runtime.items() if k != "token_hash"}, dep.id)
    dep.status = "stopped"
    dep.runtime = {k: v for k, v in dep.runtime.items() if k != "token_hash"}
    env.current_deployment_id, env.health_status, env.url = None, "stopped", None
    _log(db, dep.id, "stop", "Stopped by operator")
    audit(db, actor_id, "deployment.stop", "deployment", dep.id, env.organisation_id)


def deployment_for_token(db: Session, token: str) -> Deployment | None:
    return db.scalar(select(Deployment).where(Deployment.runtime["token_hash"].astext == hash_token(token),
                                              Deployment.status.in_(["releasing", "healthy", "unhealthy"])))
