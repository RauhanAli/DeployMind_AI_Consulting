"""Cross-cutting application services: auditing, activities, notifications, pagination, idempotency."""

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict
from app.core.logging import request_id_var
from app.models import Activity, AuditLog, IdempotencyKey, Membership, Notification, Organisation, Role, User

log = logging.getLogger("deploymind.audit")


def now() -> datetime:
    return datetime.now(UTC)


def audit(
    db: Session,
    actor_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: Any = None,
    org_id: uuid.UUID | None = None,
    details: dict | None = None,
    request: Request | None = None,
) -> None:
    ip = None
    if request is not None and request.client:
        ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
    db.add(
        AuditLog(
            organisation_id=org_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=jsonable_encoder(details or {}),
            ip_address=ip,
            request_id=request_id_var.get(),
            created_at=now(),
        )
    )
    log.info("audit", extra={"action": action, "resource_type": resource_type, "resource_id": str(resource_id)})


def record_activity(
    db: Session,
    org_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    kind: str,
    message: str,
    actor_id: uuid.UUID | None = None,
    data: dict | None = None,
    customer_visible: bool = False,
) -> Activity:
    act = Activity(
        organisation_id=org_id,
        entity_type=entity_type,
        entity_id=entity_id,
        kind=kind,
        message=message,
        actor_id=actor_id,
        data=jsonable_encoder(data or {}),
        customer_visible=customer_visible,
        created_at=now(),
    )
    db.add(act)
    return act


def notify(
    db: Session,
    org_id: uuid.UUID,
    kind: str,
    title: str,
    body: str = "",
    link: str | None = None,
    audience: str = "customer",
    user_id: uuid.UUID | None = None,
) -> Notification:
    from app.services.email import send_email

    n = Notification(
        organisation_id=org_id, kind=kind, title=title, body=body, link=link, audience=audience, user_id=user_id
    )
    db.add(n)
    if audience == "customer":
        recipients = db.scalars(
            select(User.email).join(Membership, Membership.user_id == User.id)
            .join(Role, Role.id == Membership.role_id)
            .where(Membership.organisation_id == org_id, Role.key.in_(["customer", "org_admin"]), User.is_active)
        ).all()
        if recipients:
            send_email(list(recipients), title, body)
            n.emailed = True
    return n


def paginate(db: Session, stmt, page: int, page_size: int) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).all()
    return list(items), total


def apply_sort(stmt, model, sort: str | None, allowed: set[str], default: str = "-created_at"):
    key = sort or default
    desc = key.startswith("-")
    name = key.lstrip("-")
    if name not in allowed:
        raise AppError(f"Cannot sort by '{name}'. Allowed: {sorted(allowed)}", code="invalid_sort")
    col = getattr(model, name)
    return stmt.order_by(col.desc() if desc else col.asc(), model.id)


def org_name_map(db: Session, ids) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict(db.execute(select(Organisation.id, Organisation.name).where(Organisation.id.in_(ids))).all())


def user_name_map(db: Session, ids) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all())


def idempotent(
    db: Session,
    user_id: uuid.UUID,
    key: str | None,
    endpoint: str,
    payload: Any,
    compute: Callable[[], Any],
    status_code: int = 200,
) -> Any:
    """Run `compute` at most once per (user, Idempotency-Key, endpoint); replay the stored response afterwards.

    The caller is responsible for committing the session; the stored key is committed with the result.
    """
    if not key:
        return compute()
    request_hash = hashlib.sha256(json.dumps(jsonable_encoder(payload), sort_keys=True).encode()).hexdigest()
    existing = db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id, IdempotencyKey.key == key, IdempotencyKey.endpoint == endpoint
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            raise Conflict("Idempotency-Key was reused with a different request body", code="idempotency_mismatch")
        return existing.response_body
    result = jsonable_encoder(compute())
    db.add(
        IdempotencyKey(
            user_id=user_id, key=key, endpoint=endpoint, request_hash=request_hash,
            status_code=status_code, response_body=result,
        )
    )
    return result


def next_code(db: Session, model, org_id: uuid.UUID, prefix: str) -> str:
    count = db.scalar(select(func.count()).select_from(model).where(model.organisation_id == org_id)) or 0
    return f"{prefix}-{count + 1:04d}"
