"""Secrets management abstraction.

Plaintext credentials are never written to the database. The default backend encrypts with Fernet
(AES-128-CBC + HMAC-SHA256) using SECRETS_ENCRYPTION_KEY. Other backends (e.g. AWS Secrets Manager)
implement the same SecretBackend protocol; see docs/SECURITY.md.
"""

import uuid
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, NotFound
from app.models import Secret


class SecretBackend(Protocol):
    name: str

    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, ciphertext: str) -> str: ...


class FernetBackend:
    name = "fernet"

    def __init__(self, key: str):
        self._f = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._f.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._f.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            raise AppError("Secret could not be decrypted with the configured key", code="secret_decrypt_failed")


def get_backend() -> SecretBackend:
    if settings.secrets_backend == "fernet":
        return FernetBackend(settings.secrets_encryption_key)
    raise AppError(f"Unsupported secrets backend: {settings.secrets_backend}")


def fingerprint(value: str) -> str:
    return "••••" + value[-4:] if len(value) >= 8 else "••••"


def put_secret(db: Session, org_id: uuid.UUID, name: str, value: str, actor_id: uuid.UUID | None) -> Secret:
    backend = get_backend()
    secret = db.scalar(select(Secret).where(Secret.organisation_id == org_id, Secret.name == name))
    if secret is None:
        secret = Secret(organisation_id=org_id, name=name, created_by=actor_id, ciphertext="", fingerprint="")
        db.add(secret)
    secret.ciphertext = backend.encrypt(value)
    secret.backend = backend.name
    secret.fingerprint = fingerprint(value)
    db.flush()
    return secret


def read_secret(db: Session, org_id: uuid.UUID, secret_id: uuid.UUID) -> str:
    """Server-side only. Never return the result through an API response."""
    secret = db.scalar(select(Secret).where(Secret.id == secret_id, Secret.organisation_id == org_id))
    if secret is None:
        raise NotFound("Secret not found")
    return get_backend().decrypt(secret.ciphertext)
