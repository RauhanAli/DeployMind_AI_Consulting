"""Integrations (credentials, connectors, retries, webhooks) and cross-cutting security controls."""

import hashlib
import hmac
import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.middleware import RateLimiter
from app.models import Contact, Secret
from app.services import integrations as integ_svc


@pytest.fixture
def mock_http(monkeypatch):
    """Route connector HTTP calls into the in-process mock services instead of the network."""
    from app.main import app

    def fake_http(db, integ):
        token = integ_svc._secret(db, integ)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return TestClient(app, base_url=integ.config["base_url"], headers=headers)

    monkeypatch.setattr(integ_svc, "_http", fake_http)


def _create(client, h, org, **kw):
    body = {"organisation_id": org, "name": kw.pop("name", "CRM"), "kind": kw.pop("kind", "crm"),
            "retry_policy": {"max_attempts": 2, "backoff_seconds": 0}, **kw}
    r = client.post("/api/v1/integrations", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_credentials_encrypted_never_returned(client, world, db):
    h, org = world["h"]["engineer"], str(world["a"].id)
    i = _create(client, h, org, config={"base_url": "http://testserver/api/v1/mock-services/crm"})
    r = client.put(f"/api/v1/integrations/{i['id']}/credentials", json={"value": "dm_mock_supersecret1234"}, headers=h)
    assert r.status_code == 200 and r.json()["has_credentials"] and r.json()["credential_hint"] == "••••1234"
    assert "supersecret" not in r.text and "supersecret" not in client.get("/api/v1/integrations", headers=h).text
    assert "supersecret" not in db.scalar(select(Secret)).ciphertext


def test_secrets_rejected_in_plain_config(client, world):
    r = client.post("/api/v1/integrations", json={"organisation_id": str(world["a"].id), "name": "Bad", "kind": "rest_api",
                                                  "config": {"base_url": "http://x", "api_key": "123"}},
                    headers=world["h"]["engineer"])
    assert r.status_code == 400 and r.json()["error"]["code"] == "secret_in_config"


def test_crm_connector_test_and_sync(client, world, db, mock_http):
    h, org = world["h"]["engineer"], str(world["a"].id)
    i = _create(client, h, org, config={"base_url": "http://testserver/api/v1/mock-services/crm"})
    # without credentials the mock service rejects, retries are exhausted, health becomes failing
    r = client.post(f"/api/v1/integrations/{i['id']}/test", headers=h).json()
    assert r["status"] == "failed" and r["attempts"] == 2
    assert client.get(f"/api/v1/integrations/{i['id']}", headers=h).json()["health"] == "failing"
    client.put(f"/api/v1/integrations/{i['id']}/credentials", json={"value": "dm_mock_token_abcd"}, headers=h)
    assert client.post(f"/api/v1/integrations/{i['id']}/test", headers=h).json()["status"] == "succeeded"
    job = client.post(f"/api/v1/integrations/{i['id']}/sync", headers=h).json()
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=h).json()["status"] == "succeeded"
    assert len(db.scalars(select(Contact).where(Contact.organisation_id == world["a"].id)).all()) == 3
    runs = client.get(f"/api/v1/integrations/{i['id']}/runs", headers=h).json()
    assert [r["kind"] for r in runs][:2] == ["sync", "test"]


def test_postgres_connector_real_connection(client, world):
    h, org = world["h"]["engineer"], str(world["a"].id)
    i = _create(client, h, org, name="Ops DB", kind="postgres",
                config={"host": "localhost", "port": 55432, "database": "deploymind_test", "user": "deploymind",
                        "query": "select id from organisations"})
    client.put(f"/api/v1/integrations/{i['id']}/credentials", json={"value": "deploymind"}, headers=h)
    r = client.post(f"/api/v1/integrations/{i['id']}/test", headers=h).json()
    assert r["status"] == "succeeded", r
    assert "public tables" in r["message"]


def test_webhook_signature_verification(client, world):
    h, org = world["h"]["engineer"], str(world["a"].id)
    i = _create(client, h, org, name="Events", kind="webhook")
    secret = client.post(f"/api/v1/integrations/{i['id']}/webhook-secret", headers=h).json()["secret"]
    body = json.dumps({"type": "ticket.created"}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert client.post(f"/api/v1/webhooks/{i['id']}", content=body, headers={"X-DeployMind-Signature": "sha256=bad"}).status_code == 401
    assert client.post(f"/api/v1/webhooks/{i['id']}", content=body, headers={"X-DeployMind-Signature": sig}).status_code == 202


def test_ssrf_metadata_address_blocked():
    with pytest.raises(integ_svc.ConnectorError):
        integ_svc.check_url("http://169.254.169.254/latest/meta-data")


def test_security_headers_and_error_envelope(client):
    r = client.get("/api/v1/projects")
    assert r.status_code == 401
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY"
    body = r.json()["error"]
    assert body["code"] == "unauthorized" and body["request_id"] == r.headers["X-Request-ID"]
    r = client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_cors_allows_only_configured_origin(client):
    ok = client.options("/api/v1/auth/login", headers={"Origin": "http://localhost:3000",
                                                       "Access-Control-Request-Method": "POST"})
    bad = client.options("/api/v1/auth/login", headers={"Origin": "https://evil.example",
                                                        "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in bad.headers


def test_production_refuses_development_secrets():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="Unsafe production configuration"):
        Settings(app_env="production")
    ok = Settings(app_env="production", jwt_secret="x" * 48, cookie_secure=True, ai_provider="openai",
                  secrets_encryption_key="T3v1Yxk0p3w7cH0mO2Yk6wH5bqJj0n5n2JtWm2nq9eE=")
    assert ok.is_production


def test_rate_limiter_blocks_after_limit():
    rl = RateLimiter()
    key = f"test-{__import__('uuid').uuid4()}"
    assert all(rl.hit(key, 3) for _ in range(3))
    assert rl.hit(key, 3) is False


def test_attachment_upload_rejects_mismatched_magic(client, world):
    from tests.helpers import run_discovery_to_proposal, send_proposal

    h = world["h"]
    flow = run_discovery_to_proposal(client, h["engineer"], str(world["a"].id))
    send_proposal(client, flow["proposal"]["id"], h["engineer"], h["pm"])
    project_id = client.post(f"/api/v1/proposals/{flow['proposal']['id']}/decision", json={"decision": "accepted"},
                             headers=h["cust_a"]).json()["project_id"]
    task = client.get(f"/api/v1/projects/{project_id}/tasks", headers=h["engineer"]).json()[0]
    r = client.post(f"/api/v1/tasks/{task['id']}/attachments", files={"file": ("x.pdf", io.BytesIO(b"<script>"),
                                                                              "application/pdf")}, headers=h["engineer"])
    assert r.status_code == 400
    r = client.post(f"/api/v1/tasks/{task['id']}/attachments", files={"file": ("notes.txt", io.BytesIO(b"hello"),
                                                                              "text/plain")}, headers=h["engineer"])
    assert r.status_code == 201
