"""Authentication (JWT + rotating refresh tokens) and backend-enforced RBAC."""

from sqlalchemy import select

from app.models import Lead, RefreshToken
from tests.helpers import run_assessment, run_discovery_to_proposal

REG = {"full_name": "Dana Founder", "email": "dana@newco.example", "password": "Str0ng-password!",
       "organisation_name": "NewCo Ltd", "industry": "Legal", "company_size": "11-50"}


def test_register_creates_org_admin_lead_and_returns_tokens(client, db):
    r = client.post("/api/v1/auth/register", json=REG)
    assert r.status_code == 201, r.text
    assert "dm_refresh" in r.cookies
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["is_internal"] is False and me["memberships"][0]["role"] == "org_admin"
    assert "crm.read" not in me["memberships"][0]["permissions"]  # customer scope strips internal permissions
    assert db.scalar(select(Lead).where(Lead.source == "registration")).status == "new"


def test_register_rejects_weak_password_and_duplicates(client):
    assert client.post("/api/v1/auth/register", json={**REG, "password": "short"}).status_code == 422
    assert client.post("/api/v1/auth/register", json={**REG, "password": "longbutnodigits"}).status_code == 422
    assert client.post("/api/v1/auth/register", json=REG).status_code == 201
    r = client.post("/api/v1/auth/register", json=REG)
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


def test_login_failures_use_consistent_error(client, world):
    r = client.post("/api/v1/auth/login", json={"email": "eng@deploymind.example", "password": "wrong-password-1"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    r = client.post("/api/v1/auth/login", json={"email": "nobody@deploymind.example", "password": "wrong-password-1"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"


def test_protected_endpoints_require_valid_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_refresh_rotation_and_reuse_detection(client, db):
    r = client.post("/api/v1/auth/register?include_refresh=true", json=REG)
    t1 = r.json()["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh?include_refresh=true", json={"refresh_token": t1})
    assert r2.status_code == 200
    t2 = r2.json()["refresh_token"]
    assert t2 != t1
    # Re-using the rotated token revokes the whole family, including t2.
    r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": t1})
    assert r3.status_code == 401 and r3.json()["error"]["code"] == "refresh_reuse"
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": t2}).status_code == 401
    assert all(t.revoked_at for t in db.scalars(select(RefreshToken)).all())


def test_refresh_via_cookie_and_logout(client):
    client.post("/api/v1/auth/register", json=REG)
    assert client.post("/api/v1/auth/refresh").status_code == 200  # cookie jar carries dm_refresh
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_viewer_is_read_only(client, world):
    h = world["h"]["viewer"]
    assert client.get("/api/v1/crm/leads", headers=h).status_code == 200
    r = client.post("/api/v1/crm/leads", json={"organisation_name": "X Corp", "title": "Lead"}, headers=h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert client.get("/api/v1/audit-logs", headers=h).status_code == 403


def test_customer_cannot_use_internal_write_operations(client, world):
    h, a = world["h"]["admin_a"], str(world["a"].id)
    assert client.post("/api/v1/discovery/sessions", json={"organisation_id": a, "title": "Mine"}, headers=h).status_code == 403
    assert client.post("/api/v1/apps", json={"organisation_id": a, "name": "My app"}, headers=h).status_code == 403
    assert client.post("/api/v1/incidents", json={"organisation_id": a, "title": "Self-made", "severity": "sev1"},
                       headers=h).status_code == 403


def test_customer_org_admin_can_add_customer_but_not_staff_roles(client, world):
    h, a = world["h"]["admin_a"], str(world["a"].id)
    body = {"email": "new@alpha.example", "full_name": "New Person", "temporary_password": "Temp-pass-123"}
    assert client.post(f"/api/v1/organisations/{a}/members", json={**body, "role": "engineer"}, headers=h).status_code == 400
    assert client.post(f"/api/v1/organisations/{a}/members", json={**body, "role": "customer"}, headers=h).status_code == 201
    assert client.post(f"/api/v1/organisations/{a}/members", json={**body, "email": "x@alpha.example",
                                                                   "role": "customer"}, headers=world["h"]["cust_a"]
                       ).status_code == 403


def test_ai_proposal_requires_second_reviewer(client, world):
    h = world["h"]
    flow = run_discovery_to_proposal(client, h["engineer"], str(world["a"].id))
    pid = flow["proposal"]["id"]
    assert client.post(f"/api/v1/proposals/{pid}/transition", json={"status": "in_review"}, headers=h["engineer"]).status_code == 200
    # engineers lack proposal.approve entirely
    assert client.post(f"/api/v1/proposals/{pid}/transition", json={"status": "approved"}, headers=h["engineer"]).status_code == 403
    assert client.post(f"/api/v1/proposals/{pid}/transition", json={"status": "approved"}, headers=h["pm"]).status_code == 200
    # customer cannot see it until sent
    assert client.get(f"/api/v1/proposals/{pid}", headers=h["cust_a"]).status_code == 404
    assert client.post(f"/api/v1/proposals/{pid}/transition", json={"status": "sent"}, headers=h["pm"]).status_code == 200
    assert client.get(f"/api/v1/proposals/{pid}", headers=h["cust_a"]).status_code == 200


def test_invalid_state_transitions_rejected(client, world):
    h = world["h"]
    flow = run_discovery_to_proposal(client, h["engineer"], str(world["a"].id))
    pid = flow["proposal"]["id"]
    r = client.post(f"/api/v1/proposals/{pid}/transition", json={"status": "sent"}, headers=h["pm"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"
    r = client.post(f"/api/v1/proposals/{pid}/decision", json={"decision": "accepted"}, headers=h["cust_a"])
    assert r.status_code == 404  # not visible while draft


def test_lead_pipeline_cannot_skip_stages(client, world):
    h = world["h"]["engineer"]
    lead = client.post("/api/v1/crm/leads", json={"organisation_name": "Pipeline Co", "title": "Deal"}, headers=h).json()
    r = client.post(f"/api/v1/crm/leads/{lead['id']}/status", json={"status": "proposal"}, headers=h)
    assert r.status_code == 409
    assert client.post(f"/api/v1/crm/leads/{lead['id']}/status", json={"status": "qualified"}, headers=h).status_code == 200
    acts = client.get(f"/api/v1/crm/leads/{lead['id']}/activities", headers=h).json()
    assert any(a["kind"] == "status_change" for a in acts)


def test_assessment_submit_is_idempotent(client, world):
    h = world["h"]["cust_a"]
    a = client.post("/api/v1/assessments", json={}, headers=h).json()
    from tests.helpers import ANSWERS, PROFILE
    client.put(f"/api/v1/assessments/{a['id']}/progress", json={"answers": ANSWERS, "profile": PROFILE}, headers=h)
    key = {"Idempotency-Key": "submit-123", **h}
    r1 = client.post(f"/api/v1/assessments/{a['id']}/submit", headers=key)
    r2 = client.post(f"/api/v1/assessments/{a['id']}/submit", headers=key)
    assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json()
    r3 = client.post(f"/api/v1/assessments/{a['id']}/submit", headers=h)
    assert r3.status_code == 409


def test_audit_log_records_sensitive_actions(client, world):
    run_assessment(client, world["h"]["cust_a"])
    logs = client.get("/api/v1/audit-logs?action=assessment", headers=world["h"]["super"]).json()["items"]
    assert {l["action"] for l in logs} >= {"assessment.create", "assessment.submit"}
