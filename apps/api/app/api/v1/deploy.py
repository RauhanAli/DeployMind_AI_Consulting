import asyncio
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal, get_scoped, require
from app.api.v1.knowledge import ChatIn, chat_turn
from app.core.errors import AppError, Forbidden, NotFound, Unauthorized
from app.core.secrets import put_secret
from app.db.session import SessionLocal, get_db
from app.deploy.adapters import ADAPTERS, effective_adapter_status
from app.models import AIApplication, Deployment, DeploymentLog, Environment, Secret
from app.schemas.common import ORM, Page
from app.services import deployments as svc
from app.services.common import audit, org_name_map, paginate, user_name_map
from app.workers.tasks import enqueue_deployment

router = APIRouter(tags=["deployments"])

RESERVED_VARS = {"PLATFORM_URL", "DEPLOYMENT_TOKEN", "APP_ID", "APP_NAME", "ENVIRONMENT", "APP_VERSION"}


class EnvironmentOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    project_id: uuid.UUID | None
    app_id: uuid.UUID
    app_name: str | None = None
    name: str
    variables: dict
    secret_names: list[str] = []
    resources: dict
    adapter: str
    requires_approval: bool
    current_deployment_id: uuid.UUID | None
    current_version: str | None = None
    health_status: str
    last_health_check_at: datetime | None
    url: str | None


class EnvironmentPatch(BaseModel):
    variables: dict[str, str] | None = None
    resources: dict | None = None
    adapter: str | None = None
    requires_approval: bool | None = None


class EnvSecretIn(BaseModel):
    name: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    value: str = Field(min_length=1, max_length=8000)


class DeploymentOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    organisation_name: str | None = None
    environment_id: uuid.UUID
    environment: str | None = None
    app_name: str | None = None
    version: str
    image_tag: str | None
    adapter: str
    status: str
    stage: str | None
    triggered_by: uuid.UUID | None
    triggered_by_name: str | None = None
    approved_by: uuid.UUID | None
    approved_by_name: str | None = None
    rollback_of_id: uuid.UUID | None
    config_snapshot: dict
    url: str | None = None
    health_check: dict
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    is_demo: bool
    created_at: datetime


class LogOut(ORM):
    id: uuid.UUID
    stage: str
    level: str
    message: str
    created_at: datetime


def _env_out(db: Session, envs: list[Environment]) -> list[EnvironmentOut]:
    apps = dict(db.execute(select(AIApplication.id, AIApplication.name)
                           .where(AIApplication.id.in_([e.app_id for e in envs]))).all()) if envs else {}
    cur_ids = [e.current_deployment_id for e in envs if e.current_deployment_id]
    versions = dict(db.execute(select(Deployment.id, Deployment.version).where(Deployment.id.in_(cur_ids))).all()) if cur_ids else {}
    return [EnvironmentOut.model_validate(e).model_copy(update={
        "app_name": apps.get(e.app_id), "secret_names": sorted(e.secret_refs),
        "current_version": versions.get(e.current_deployment_id)}) for e in envs]


def _dep_out(db: Session, deps: list[Deployment]) -> list[DeploymentOut]:
    envs = {e.id: e for e in db.scalars(select(Environment).where(
        Environment.id.in_({d.environment_id for d in deps}))).all()} if deps else {}
    apps = dict(db.execute(select(AIApplication.id, AIApplication.name)
                           .where(AIApplication.id.in_({e.app_id for e in envs.values()}))).all()) if envs else {}
    users = user_name_map(db, [d.triggered_by for d in deps] + [d.approved_by for d in deps])
    orgs = org_name_map(db, [d.organisation_id for d in deps])
    out = []
    for d in deps:
        env = envs.get(d.environment_id)
        out.append(DeploymentOut.model_validate(d).model_copy(update={
            "environment": env.name if env else None, "app_name": apps.get(env.app_id) if env else None,
            "triggered_by_name": users.get(d.triggered_by), "approved_by_name": users.get(d.approved_by),
            "organisation_name": orgs.get(d.organisation_id), "url": d.runtime.get("url")}))
    return out


@router.get("/deployments/adapters")
def adapters(principal: Principal = Depends(require("deployment.read"))):
    return effective_adapter_status()


@router.get("/apps/{app_id}/environments", response_model=list[EnvironmentOut])
def list_environments(app_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    a = get_scoped(db, AIApplication, app_id, principal, "deployment.read")
    envs = svc.ensure_environments(db, a)
    db.commit()
    return _env_out(db, envs)


@router.get("/environments", response_model=list[EnvironmentOut])
def all_environments(organisation_id: uuid.UUID | None = None, principal: Principal = Depends(require("deployment.read")),
                     db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(Environment), Environment)
    if organisation_id:
        stmt = stmt.where(Environment.organisation_id == organisation_id)
    return _env_out(db, list(db.scalars(stmt.order_by(Environment.app_id, Environment.name)).all()))


@router.patch("/environments/{env_id}", response_model=EnvironmentOut)
def patch_environment(env_id: uuid.UUID, body: EnvironmentPatch, request: Request,
                      principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    env = get_scoped(db, Environment, env_id, principal, "deployment.write")
    changes = body.model_dump(exclude_unset=True)
    if "variables" in changes:
        bad = [k for k in changes["variables"] if k.upper() in RESERVED_VARS or any(
            s in k.upper() for s in ("SECRET", "PASSWORD", "TOKEN", "KEY"))]
        if bad:
            raise AppError(f"Use the secrets endpoint for sensitive or reserved variables: {bad}", code="secret_in_variables")
    if "adapter" in changes and changes["adapter"] not in ADAPTERS:
        raise AppError(f"Unknown adapter. Allowed: {list(ADAPTERS)}", code="invalid_adapter")
    if env.name == "production" and changes.get("requires_approval") is False and not principal.is_super_admin:
        raise Forbidden("Only a super admin can remove the production approval gate")
    for k, v in changes.items():
        setattr(env, k, v)
    audit(db, principal.id, "environment.update", "environment", env.id, env.organisation_id, changes, request)
    db.commit()
    return _env_out(db, [env])[0]


@router.put("/environments/{env_id}/secrets", response_model=EnvironmentOut)
def set_env_secret(env_id: uuid.UUID, body: EnvSecretIn, request: Request, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    """Write-only: stored encrypted, injected into the container at deploy time, never returned."""
    env = get_scoped(db, Environment, env_id, principal, "deployment.write")
    if body.name in RESERVED_VARS:
        raise AppError("Reserved variable name", code="reserved_variable")
    s = put_secret(db, env.organisation_id, f"env:{env.id}:{body.name}", body.value, principal.id)
    env.secret_refs = {**env.secret_refs, body.name: str(s.id)}
    audit(db, principal.id, "environment.secret_set", "environment", env.id, env.organisation_id, {"name": body.name}, request)
    db.commit()
    return _env_out(db, [env])[0]


@router.delete("/environments/{env_id}/secrets/{name}", response_model=EnvironmentOut)
def delete_env_secret(env_id: uuid.UUID, name: str, principal: Principal = Depends(get_principal),
                      db: Session = Depends(get_db)):
    env = get_scoped(db, Environment, env_id, principal, "deployment.write")
    sid = env.secret_refs.get(name)
    if sid is None:
        raise NotFound("Secret not found")
    db.delete(db.get(Secret, uuid.UUID(sid)))
    env.secret_refs = {k: v for k, v in env.secret_refs.items() if k != name}
    db.commit()
    return _env_out(db, [env])[0]


@router.post("/environments/{env_id}/deploy", response_model=DeploymentOut, status_code=202)
def deploy(env_id: uuid.UUID, request: Request, idempotency_key: str | None = Header(None),
           principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    from app.services.common import idempotent

    env = get_scoped(db, Environment, env_id, principal, "deployment.write")

    def compute():
        dep = svc.trigger(db, env, principal.id)
        if dep.status == "pending":
            enqueue_deployment(db, dep.id)
        audit(db, principal.id, "deployment.trigger", "deployment", dep.id, env.organisation_id,
              {"environment": env.name, "version": dep.version}, request)
        return _dep_out(db, [dep])[0]

    result = idempotent(db, principal.id, idempotency_key, f"deploy:{env_id}", {}, compute, 202)
    db.commit()
    return result


@router.post("/environments/{env_id}/rollback", response_model=DeploymentOut, status_code=202)
def rollback(env_id: uuid.UUID, request: Request, principal: Principal = Depends(get_principal),
             db: Session = Depends(get_db)):
    env = get_scoped(db, Environment, env_id, principal, "deployment.write")
    dep = svc.rollback(db, env, principal.id)
    enqueue_deployment(db, dep.id)
    audit(db, principal.id, "deployment.rollback", "deployment", dep.id, env.organisation_id, {"environment": env.name}, request)
    db.commit()
    return _dep_out(db, [dep])[0]


@router.post("/environments/{env_id}/health-check")
def env_health(env_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    env = get_scoped(db, Environment, env_id, principal, "deployment.read")
    result = svc.health_check(db, env)
    db.commit()
    return result


@router.post("/environments/{env_id}/stop", status_code=204)
def stop_env(env_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    env = get_scoped(db, Environment, env_id, principal, "deployment.write")
    svc.stop(db, env, principal.id)
    db.commit()


@router.get("/deployments", response_model=Page[DeploymentOut])
def list_deployments(organisation_id: uuid.UUID | None = None, environment_id: uuid.UUID | None = None,
                     app_id: uuid.UUID | None = None, status: str | None = None, page: int = Query(1, ge=1),
                     page_size: int = Query(20, ge=1, le=100), principal: Principal = Depends(require("deployment.read")),
                     db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(Deployment), Deployment)
    if organisation_id:
        stmt = stmt.where(Deployment.organisation_id == organisation_id)
    if environment_id:
        stmt = stmt.where(Deployment.environment_id == environment_id)
    if app_id:
        stmt = stmt.join(Environment, Environment.id == Deployment.environment_id).where(Environment.app_id == app_id)
    if status:
        stmt = stmt.where(Deployment.status == status)
    items, total = paginate(db, stmt.order_by(Deployment.created_at.desc()), page, page_size)
    return Page(items=_dep_out(db, items), total=total, page=page, page_size=page_size)


@router.get("/deployments/{dep_id}", response_model=DeploymentOut)
def get_deployment(dep_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return _dep_out(db, [get_scoped(db, Deployment, dep_id, principal, "deployment.read")])[0]


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/deployments/{dep_id}/approve", response_model=DeploymentOut)
def approve(dep_id: uuid.UUID, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    dep = get_scoped(db, Deployment, dep_id, principal, "deployment.approve")
    svc.approve(db, dep, principal.id, principal.is_super_admin)
    enqueue_deployment(db, dep.id)
    audit(db, principal.id, "deployment.approve", "deployment", dep.id, dep.organisation_id, request=request)
    db.commit()
    return _dep_out(db, [dep])[0]


@router.post("/deployments/{dep_id}/reject", response_model=DeploymentOut)
def reject(dep_id: uuid.UUID, body: RejectIn, request: Request, principal: Principal = Depends(get_principal),
           db: Session = Depends(get_db)):
    dep = get_scoped(db, Deployment, dep_id, principal, "deployment.approve")
    svc.reject(db, dep, principal.id, body.reason)
    audit(db, principal.id, "deployment.reject", "deployment", dep.id, dep.organisation_id, {"reason": body.reason}, request)
    db.commit()
    return _dep_out(db, [dep])[0]


@router.get("/deployments/{dep_id}/logs", response_model=list[LogOut])
def deployment_logs(dep_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    dep = get_scoped(db, Deployment, dep_id, principal, "deployment.read")
    return db.scalars(select(DeploymentLog).where(DeploymentLog.deployment_id == dep.id)
                      .order_by(DeploymentLog.created_at, DeploymentLog.id)).all()


@router.get("/deployments/{dep_id}/logs/stream")
async def stream_logs(dep_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    """Server-Sent Events: streams new log lines and status until the deployment finishes."""
    get_scoped(db, Deployment, dep_id, principal, "deployment.read")

    async def gen():
        seen: set[uuid.UUID] = set()
        terminal = {"healthy", "failed", "cancelled", "rolled_back", "superseded", "stopped", "awaiting_approval"}
        for _ in range(1200):
            with SessionLocal() as s:
                dep = s.get(Deployment, dep_id)
                rows = s.scalars(select(DeploymentLog).where(DeploymentLog.deployment_id == dep_id)
                                 .order_by(DeploymentLog.created_at, DeploymentLog.id)).all()
                for r in rows:
                    if r.id not in seen:
                        seen.add(r.id)
                        yield f"event: log\ndata: {json.dumps({'stage': r.stage, 'level': r.level, 'message': r.message, 'created_at': r.created_at.isoformat()})}\n\n"
                yield f"event: status\ndata: {json.dumps({'status': dep.status, 'stage': dep.stage})}\n\n"
                if dep.status in terminal:
                    return
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ runtime API for deployed containers
def _runtime_deployment(authorization: str | None, db: Session) -> Deployment:
    if not authorization or not authorization.startswith("Bearer "):
        raise Unauthorized("Deployment token required")
    dep = svc.deployment_for_token(db, authorization[7:])
    if dep is None:
        raise Unauthorized("Invalid or revoked deployment token", code="invalid_deployment_token")
    return dep


@router.get("/runtime/health", tags=["runtime"])
def runtime_health(authorization: str | None = Header(None), db: Session = Depends(get_db)):
    dep = _runtime_deployment(authorization, db)
    return {"status": "ok", "deployment": dep.version}


@router.post("/runtime/ask", tags=["runtime"])
def runtime_ask(body: ChatIn, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """End users of a deployed assistant are anonymous to the platform: they only see organisation-wide documents."""
    dep = _runtime_deployment(authorization, db)
    env = db.get(Environment, dep.environment_id)
    app = db.get(AIApplication, env.app_id)
    out = chat_turn(db, app, body.question, body.conversation_id, None, False, source="deployment",
                    deployment_id=dep.id, environment=env.name)
    return {"conversation_id": str(out.conversation_id), "answer": out.message.content,
            "citations": [{"index": c["index"], "title": c["title"], "filename": c["filename"]} for c in out.message.citations],
            "insufficient_evidence": out.message.insufficient_evidence, "version": dep.version}
