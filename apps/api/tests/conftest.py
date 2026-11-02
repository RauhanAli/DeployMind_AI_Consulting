"""Test harness: real PostgreSQL + pgvector test database, migrated with Alembic, truncated between tests.

Background jobs run eagerly (CELERY_TASK_ALWAYS_EAGER) so end-to-end flows complete within a request.
"""

import os
import uuid

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://deploymind:deploymind@localhost:55432/deploymind_test")
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["AUTH_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["AI_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["APP_ENV"] = "test"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["STORAGE_LOCAL_PATH"] = "/tmp/deploymind-test-storage"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from alembic import command  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import Membership, Organisation, Role, User  # noqa: E402

PASSWORD = "Test-password-123"


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public; CREATE EXTENSION IF NOT EXISTS vector"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = os.environ["DATABASE_URL"]
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_db(migrated_db):
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as c:
        c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    from app.seed.bootstrap import bootstrap

    with SessionLocal() as db:
        bootstrap(db)
        db.commit()
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def make_org(db, name: str, kind: str = "customer") -> Organisation:
    org = db.scalar(select(Organisation).where(Organisation.slug == name.lower().replace(" ", "-")))
    if org:
        return org
    org = Organisation(name=name, slug=name.lower().replace(" ", "-"), kind=kind, industry="Professional Services",
                       size="201-500")
    db.add(org)
    db.flush()
    return org


def make_user(db, email: str, role: str, org: Organisation) -> User:
    u = User(email=email, full_name=email.split("@")[0].replace(".", " ").title(), password_hash=hash_password(PASSWORD))
    db.add(u)
    db.flush()
    db.add(Membership(user_id=u.id, organisation_id=org.id, role_id=db.scalar(select(Role.id).where(Role.key == role))))
    db.flush()
    return u


def login(client, email: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def world(db, client):
    """Provider staff + two isolated customer organisations."""
    provider = db.scalar(select(Organisation).where(Organisation.kind == "provider"))
    org_a, org_b = make_org(db, "Org Alpha"), make_org(db, "Org Beta")
    users = {
        "super": make_user(db, "super@deploymind.example", "super_admin", provider),
        "engineer": make_user(db, "eng@deploymind.example", "engineer", provider),
        "engineer2": make_user(db, "eng2@deploymind.example", "engineer", provider),
        "pm": make_user(db, "pm@deploymind.example", "project_manager", provider),
        "viewer": make_user(db, "viewer@deploymind.example", "viewer", provider),
        "cust_a": make_user(db, "alice@alpha.example", "customer", org_a),
        "admin_a": make_user(db, "admin@alpha.example", "org_admin", org_a),
        "cust_b": make_user(db, "bob@beta.example", "customer", org_b),
    }
    db.commit()
    headers = {k: login(client, u.email) for k, u in users.items()}
    return {"provider": provider, "a": org_a, "b": org_b, "users": users, "h": headers}


def uid() -> str:
    return str(uuid.uuid4())
