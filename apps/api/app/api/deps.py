"""Authentication, authorisation and tenant-scoping dependencies.

Every tenant-owned query must go through `Principal.scope_filter` / `get_scoped` so that a user can only
ever reach rows belonging to organisations they are entitled to. Out-of-scope IDs return 404 (not 403)
so that resource existence is not leaked across tenants.
"""

import uuid
from dataclasses import dataclass, field

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import Forbidden, NotFound, Unauthorized
from app.core.rbac import CUSTOMER_FORBIDDEN
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Membership, Organisation, User

bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    user: User
    internal_role: str | None = None
    internal_permissions: set[str] = field(default_factory=set)
    # customer organisation id -> (role key, permissions)
    customer_orgs: dict[uuid.UUID, tuple[str, set[str]]] = field(default_factory=dict)
    provider_org_id: uuid.UUID | None = None

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    @property
    def is_internal(self) -> bool:
        return self.internal_role is not None

    @property
    def is_super_admin(self) -> bool:
        return self.internal_role == "super_admin"

    def org_ids(self) -> list[uuid.UUID] | None:
        """None means unrestricted (internal staff)."""
        return None if self.is_internal else list(self.customer_orgs)

    def can_access_org(self, org_id: uuid.UUID) -> bool:
        return self.is_internal or org_id in self.customer_orgs

    def has(self, permission: str, org_id: uuid.UUID | None = None) -> bool:
        if self.is_internal:
            return permission in self.internal_permissions
        if permission in CUSTOMER_FORBIDDEN:
            return False
        if org_id is not None:
            entry = self.customer_orgs.get(org_id)
            return bool(entry and permission in entry[1])
        return any(permission in perms for _, perms in self.customer_orgs.values())

    def require(self, permission: str, org_id: uuid.UUID | None = None) -> None:
        if org_id is not None and not self.can_access_org(org_id):
            raise NotFound("Resource not found")
        if not self.has(permission, org_id):
            raise Forbidden(f"Missing permission: {permission}")

    def scope_filter(self, stmt, model):
        ids = self.org_ids()
        if ids is None:
            return stmt
        return stmt.where(model.organisation_id.in_(ids))

    def role_label(self) -> str:
        if self.internal_role:
            return self.internal_role
        roles = {r for r, _ in self.customer_orgs.values()}
        return ",".join(sorted(roles)) or "none"


def load_principal(db: Session, user: User) -> Principal:
    rows = db.execute(
        select(Membership, Organisation).join(Organisation, Organisation.id == Membership.organisation_id)
        .where(Membership.user_id == user.id)
    ).all()
    p = Principal(user=user)
    for membership, org in rows:
        perms = {perm.key for perm in membership.role.permissions}
        if org.kind == "provider":
            p.internal_role = membership.role.key
            p.internal_permissions = perms
            p.provider_org_id = org.id
        else:
            p.customer_orgs[org.id] = (membership.role.key, perms)
    return p


def get_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized("Authentication required")
    try:
        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise Unauthorized("Invalid or expired token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Account disabled or not found")
    principal = load_principal(db, user)
    request.state.principal = principal
    return principal


def get_optional_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Principal | None:
    if creds is None:
        return None
    return get_principal(request, creds, db)


def require(permission: str):
    """Dependency factory for coarse-grained permission checks; resource-level checks happen in handlers."""

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(permission):
            raise Forbidden(f"Missing permission: {permission}")
        return principal

    return _dep


def require_internal(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.is_internal:
        raise Forbidden("Internal staff only")
    return principal


def get_scoped(db: Session, model, obj_id: uuid.UUID, principal: Principal, permission: str | None = None):
    """Fetch a tenant-owned row by id, enforcing organisation scope and (optionally) a permission."""
    stmt = principal.scope_filter(select(model).where(model.id == obj_id), model)
    obj = db.scalar(stmt)
    if obj is None:
        raise NotFound(f"{model.__name__} not found")
    if permission:
        principal.require(permission, obj.organisation_id)
    return obj


def provider_org(db: Session) -> Organisation:
    org = db.scalar(select(Organisation).where(Organisation.slug == settings.provider_org_slug))
    if org is None:
        raise NotFound("Provider organisation not initialised; run the bootstrap/seed command")
    return org
