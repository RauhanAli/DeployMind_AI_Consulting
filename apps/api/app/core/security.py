"""Password hashing, JWT access tokens and opaque refresh tokens."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id: uuid.UUID, extra: dict | None = None) -> tuple[str, int]:
    ttl = settings.access_token_ttl_minutes * 60
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        "type": "access",
        "jti": uuid.uuid4().hex,
        **(extra or {}),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), ttl


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def new_refresh_token() -> tuple[str, str]:
    """Returns (plaintext token for the client, sha256 hash for storage)."""
    token = secrets.token_urlsafe(48)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days)


def password_policy_errors(password: str) -> list[str]:
    errors = []
    if len(password) < 10:
        errors.append("must be at least 10 characters")
    if not any(c.isdigit() for c in password):
        errors.append("must contain a digit")
    if not any(c.isalpha() for c in password):
        errors.append("must contain a letter")
    return errors
