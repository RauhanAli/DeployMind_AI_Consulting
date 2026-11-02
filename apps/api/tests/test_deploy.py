"""Deployment pipeline, approval gates, rollback, runtime tokens, secrets handling."""

import pytest
from sqlalchemy import select

from app.deploy.adapters import AdapterError, register_adapter_override
from app.models import Secret


class FakeAdapter:
    """Records calls; behaves like a real adapter without touching Docker."""

    name = "local_docker"
    honest_label = "Fake adapter (tests)"
    calls: list = []
    tokens: list = []
    fail_health = False
    env_seen: dict = {}

    def build(self, ctx, log):
        FakeAdapter.calls.append(("build", ctx.version))
        log("build", "fake build", "info")
        return f"fake/assistant:{ctx.version}"

    def test(self, ctx, image, log):
        FakeAdapter.calls.append(("test", image))

    def release(self, ctx, image, log):
        FakeAdapter.calls.append(("release", image))
        FakeAdapter.tokens.append(ctx.env_vars["DEPLOYMENT_TOKEN"])
        FakeAdapter.env_seen = dict(ctx.env_vars)
        if FakeAdapter.fail_health:
            raise AdapterError("New container failed health checks: fake")
        return {"container_id": f"c-{ctx.version}", "url": f"http://fake-{ctx.version}", "image_tag": image,
                "health": {"status": "ok"}}

    def health(self, runtime):
        return True, {"status": "ok"}

    def stop(self, runtime, log=None):
        FakeAdapter.calls.append(("stop", runtime.get("container_id")))


@pytest.fixture(autouse=True)
def fake_adapter():
    FakeAdapter.calls, FakeAdapter.tokens, FakeAdapter.fail_health = [], [], False
    register_adapter_override("local_docker", FakeAdapter)
    yield


@pytest.fixture
def envs(client, world):
    h = world["h"]["engineer"]
    app = client.post("/api/v1/apps", json={"organisation_id": str(world["a"].id), "name": "Deployable"}, headers=h).json()
    client.patch(f"/api/v1/apps/{app['id']}", json={"status": "active"}, headers=h)
    envs = {e["name"]: e for e in client.get(f"/api/v1/apps/{app['id']}/environments", headers=h).json()}
    return {"app": app, **envs}


def test_environments_created_with_production_gate(envs):
    assert envs["production"]["requires_approval"] is True
    assert envs["development"]["requires_approval"] is False


def test_dev_deploy_runs_pipeline_and_records_logs(client, world, envs):
    h = world["h"]["engineer"]
    r = client.post(f"/api/v1/environments/{envs['development']['id']}/deploy", headers=h)
    assert r.status_code == 202, r.text
    dep = client.get(f"/api/v1/deployments/{r.json()['id']}", headers=h).json()
    assert dep["status"] == "healthy" and dep["image_tag"] == "fake/assistant:v1.0.1"
    assert [c[0] for c in FakeAdapter.calls] == ["build", "test", "release"]
    stages = {l["stage"] for l in client.get(f"/api/v1/deployments/{dep['id']}/logs", headers=h).json()}
    assert {"queued", "build", "complete"} <= stages
    env = client.get(f"/api/v1/apps/{envs['app']['id']}/environments", headers=h).json()
    assert next(e for e in env if e["name"] == "development")["current_version"] == "v1.0.1"


def test_production_requires_four_eyes_approval(client, world, envs):
    h = world["h"]
    r = client.post(f"/api/v1/environments/{envs['production']['id']}/deploy", headers=h["engineer"])
    dep = r.json()
    assert dep["status"] == "awaiting_approval" and FakeAdapter.calls == []
    # engineer lacks deployment.approve; PM has it via... no - only org_admin/super_admin hold approve
    assert client.post(f"/api/v1/deployments/{dep['id']}/approve", headers=h["engineer"]).status_code == 403
    r = client.post(f"/api/v1/deployments/{dep['id']}/approve", headers=h["super"])
    assert r.status_code == 200
    assert client.get(f"/api/v1/deployments/{dep['id']}", headers=h["engineer"]).json()["status"] == "healthy"


def test_concurrent_deploy_blocked(client, world, envs):
    h = world["h"]["engineer"]
    client.post(f"/api/v1/environments/{envs['production']['id']}/deploy", headers=h)
    r = client.post(f"/api/v1/environments/{envs['production']['id']}/deploy", headers=h)
    assert r.status_code == 409


def test_failed_health_check_keeps_previous_release(client, world, envs):
    h = world["h"]["engineer"]
    url = f"/api/v1/environments/{envs['staging']['id']}/deploy"
    first = client.post(url, headers=h).json()
    FakeAdapter.fail_health = True
    second = client.post(url, headers=h).json()
    second = client.get(f"/api/v1/deployments/{second['id']}", headers=h).json()
    assert second["status"] == "failed" and "health" in second["error"]
    env = next(e for e in client.get(f"/api/v1/apps/{envs['app']['id']}/environments", headers=h).json()
               if e["name"] == "staging")
    assert env["current_deployment_id"] == first["id"]


def test_rollback_reuses_previous_image(client, world, envs):
    h = world["h"]["engineer"]
    url = f"/api/v1/environments/{envs['development']['id']}/deploy"
    client.post(url, headers=h)
    client.post(url, headers=h)
    FakeAdapter.calls = []
    r = client.post(f"/api/v1/environments/{envs['development']['id']}/rollback", headers=h)
    assert r.status_code == 202, r.text
    rb = client.get(f"/api/v1/deployments/{r.json()['id']}", headers=h).json()
    assert rb["status"] == "healthy" and rb["image_tag"] == "fake/assistant:v1.0.1"
    assert "build" not in [c[0] for c in FakeAdapter.calls]
    deps = client.get(f"/api/v1/deployments?environment_id={envs['development']['id']}", headers=h).json()["items"]
    assert {d["version"]: d["status"] for d in deps}["v1.0.2"] == "rolled_back"


def test_runtime_api_authenticates_with_deployment_token_and_records_telemetry(client, world, envs):
    h = world["h"]["engineer"]
    client.post(f"/api/v1/environments/{envs['development']['id']}/deploy", headers=h)
    token = FakeAdapter.tokens[-1]
    assert client.get("/api/v1/runtime/health", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/v1/runtime/health", headers={"Authorization": f"Bearer {token}"}).json()["status"] == "ok"
    r = client.post("/api/v1/runtime/ask", json={"question": "anything documented?"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["insufficient_evidence"] is True
    m = client.get("/api/v1/monitoring/overview?hours=1", headers=h).json()
    assert m["sources_present"].get("deployment", 0) >= 1
    # superseded deployments lose their token
    client.post(f"/api/v1/environments/{envs['development']['id']}/deploy", headers=h)
    assert client.get("/api/v1/runtime/health", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_environment_secrets_are_encrypted_and_write_only(client, world, envs, db):
    h = world["h"]["engineer"]
    eid = envs["development"]["id"]
    r = client.put(f"/api/v1/environments/{eid}/secrets", json={"name": "CRM_API_KEY", "value": "sk-live-very-secret-9999"},
                   headers=h)
    assert r.status_code == 200 and r.json()["secret_names"] == ["CRM_API_KEY"]
    assert "sk-live" not in r.text
    row = db.scalar(select(Secret).where(Secret.name.like("env:%")))
    assert "sk-live" not in row.ciphertext and row.fingerprint.endswith("9999")
    bad = client.patch(f"/api/v1/environments/{eid}", json={"variables": {"DB_PASSWORD": "x"}}, headers=h)
    assert bad.status_code == 400
    client.post(f"/api/v1/environments/{eid}/deploy", headers=h)
    assert FakeAdapter.env_seen["CRM_API_KEY"] == "sk-live-very-secret-9999"  # injected at deploy time only
    listing = client.get("/api/v1/environments", headers=h).text
    assert "sk-live" not in listing


def test_stop_marks_environment_and_removes_runtime_via_worker(client, world, envs):
    h = world["h"]["engineer"]
    eid = envs["development"]["id"]
    dep = client.post(f"/api/v1/environments/{eid}/deploy", headers=h).json()
    FakeAdapter.calls = []
    assert client.post(f"/api/v1/environments/{eid}/stop", headers=h).status_code == 204
    assert ("stop", f"c-{dep['version']}") in FakeAdapter.calls
    env = next(e for e in client.get(f"/api/v1/apps/{envs['app']['id']}/environments", headers=h).json() if e["id"] == eid)
    assert env["health_status"] == "stopped" and env["current_deployment_id"] is None
    stages = [l["stage"] for l in client.get(f"/api/v1/deployments/{dep['id']}/logs", headers=h).json()]
    assert stages.count("stop") == 2  # operator action + worker confirmation


def test_customer_cannot_deploy(client, world, envs):
    r = client.post(f"/api/v1/environments/{envs['development']['id']}/deploy", headers=world["h"]["admin_a"])
    assert r.status_code == 403
