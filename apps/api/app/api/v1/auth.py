import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal, load_principal, provider_org
from app.core.config import settings
from app.core.errors import Conflict, Unauthorized
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    password_policy_errors,
    refresh_expiry,
    verify_password,
)
from app.db.session import get_db
from app.models import Contact, Lead, Membership, Organisation, RefreshToken, Role, User
from app.services.common import audit, notify, record_activity

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "dm_refresh"


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    organisation_name: str = Field(min_length=2, max_length=200)
    industry: str | None = Field(None, max_length=120)
    company_size: str | None = Field(None, max_length=40)
    website: str | None = Field(None, max_length=300)
    job_title: str | None = Field(None, max_length=120)

    @field_validator("password")
    @classmethod
    def _policy(cls, v: str) -> str:
        errs = password_policy_errors(v)
        if errs:
            raise ValueError("Password " + ", ".join(errs))
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105  (OAuth2 token type, not a secret)
    expires_in: int
    refresh_token: str | None = Field(
        None, description="Only returned to non-browser clients that pass ?include_refresh=true"
    )


class OrgMembershipOut(BaseModel):
    organisation_id: uuid.UUID
    organisation_name: str
    organisation_slug: str
    kind: str
    role: str
    permissions: list[str]


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_internal: bool
    internal_role: str | None
    memberships: list[OrgMembershipOut]
    mock_ai: bool
    ai_provider: str


def _slugify(name: str, db: Session) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:80] or "org"
    slug, i = base, 2
    while db.scalar(select(Organisation.id).where(Organisation.slug == slug)):
        slug, i = f"{base}-{i}", i + 1
    return slug


def _issue_tokens(db: Session, user: User, response: Response, request: Request,
                  family_id: uuid.UUID | None = None, include_refresh: bool = False) -> TokenOut:
    access, ttl = create_access_token(user.id)
    token, token_hash = new_refresh_token()
    db.add(RefreshToken(
        user_id=user.id, token_hash=token_hash, family_id=family_id or uuid.uuid4(),
        expires_at=refresh_expiry(), user_agent=(request.headers.get("user-agent") or "")[:300],
    ))
    response.set_cookie(
        REFRESH_COOKIE, token, httponly=True, secure=settings.cookie_secure, samesite="lax",
        max_age=settings.refresh_token_ttl_days * 86400, path="/api/v1/auth",
    )
    return TokenOut(access_token=access, expires_in=ttl, refresh_token=token if include_refresh else None)


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, response: Response, include_refresh: bool = False,
             db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise Conflict("An account with this email already exists", code="email_taken")
    org = Organisation(
        name=body.organisation_name, slug=_slugify(body.organisation_name, db), kind="customer",
        industry=body.industry, size=body.company_size, website=body.website,
    )
    user = User(email=email, full_name=body.full_name, password_hash=hash_password(body.password))
    db.add_all([org, user])
    db.flush()
    role = db.scalar(select(Role).where(Role.key == "org_admin"))
    db.add(Membership(user_id=user.id, organisation_id=org.id, role_id=role.id))
    contact = Contact(organisation_id=org.id, full_name=body.full_name, email=email, job_title=body.job_title,
                      is_primary=True)
    db.add(contact)
    db.flush()
    lead = Lead(organisation_id=org.id, title=f"{org.name} - inbound registration", status="new",
                source="registration", primary_contact_id=contact.id, status_changed_at=datetime.now(UTC))
    db.add(lead)
    db.flush()
    record_activity(db, org.id, "lead", lead.id, "system", "Organisation registered via website", user.id)
    notify(db, provider_org(db).id, "lead.created", f"New registration: {org.name}",
           f"{body.full_name} ({email}) registered {org.name}.", link=f"/app/crm/{lead.id}", audience="internal")
    audit(db, user.id, "auth.register", "organisation", org.id, org.id, request=request)
    tokens = _issue_tokens(db, user, response, request, include_refresh=include_refresh)
    db.commit()
    return tokens


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, response: Response, include_refresh: bool = False,
          db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        if user is not None:
            user.failed_logins += 1
            audit(db, user.id, "auth.login_failed", "user", user.id, request=request)
            db.commit()
        raise Unauthorized("Invalid email or password", code="invalid_credentials")
    if not user.is_active:
        raise Unauthorized("Account disabled", code="account_disabled")
    user.failed_logins = 0
    user.last_login_at = datetime.now(UTC)
    audit(db, user.id, "auth.login", "user", user.id, request=request)
    tokens = _issue_tokens(db, user, response, request, include_refresh=include_refresh)
    db.commit()
    return tokens


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, body: RefreshIn | None = None, include_refresh: bool = False,
            db: Session = Depends(get_db)):
    token = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise Unauthorized("No refresh token", code="no_refresh_token")
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(token)))
    now = datetime.now(UTC)
    if rt is None:
        raise Unauthorized("Invalid refresh token", code="invalid_refresh_token")
    if rt.revoked_at is not None:
        # Reuse of a rotated token: assume theft and revoke the entire token family.
        db.execute(update(RefreshToken).where(RefreshToken.family_id == rt.family_id, RefreshToken.revoked_at.is_(None))
                   .values(revoked_at=now))
        audit(db, rt.user_id, "auth.refresh_reuse_detected", "user", rt.user_id, request=request)
        db.commit()
        raise Unauthorized("Refresh token reuse detected; please sign in again", code="refresh_reuse")
    if rt.expires_at < now:
        raise Unauthorized("Refresh token expired", code="refresh_expired")
    user = db.get(User, rt.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Account disabled")
    rt.revoked_at = now
    tokens = _issue_tokens(db, user, response, request, family_id=rt.family_id, include_refresh=include_refresh)
    db.commit()
    return tokens


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(token)))
        if rt and rt.revoked_at is None:
            rt.revoked_at = datetime.now(UTC)
            audit(db, rt.user_id, "auth.logout", "user", rt.user_id, request=request)
            db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Membership, Organisation).join(Organisation).where(Membership.user_id == principal.id)
        .order_by(Organisation.kind.desc(), Organisation.name)
    ).all()
    p = load_principal(db, principal.user)
    memberships = []
    for m, org in rows:
        perms = sorted(p.internal_permissions) if org.kind == "provider" else sorted(
            perm for perm in p.customer_orgs.get(org.id, ("", set()))[1] if p.has(perm, org.id)
        )
        memberships.append(OrgMembershipOut(organisation_id=org.id, organisation_name=org.name,
                                            organisation_slug=org.slug, kind=org.kind, role=m.role.key,
                                            permissions=perms))
    return MeOut(id=principal.id, email=principal.user.email, full_name=principal.user.full_name,
                 is_internal=principal.is_internal, internal_role=principal.internal_role,
                 memberships=memberships, mock_ai=settings.mock_ai, ai_provider=settings.ai_provider)
