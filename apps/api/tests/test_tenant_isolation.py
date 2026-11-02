"""CRITICAL: a customer of Organisation A must never reach Organisation B's data, even with B's resource IDs."""

import io

import pytest

from tests.helpers import POLICY_DOC, run_assessment, run_discovery_to_proposal, send_proposal


@pytest.fixture
def org_b_estate(client, world):
    """Build a full estate for Org Beta: assessment, proposal (sent + accepted), project, app, document, chat."""
    h, b = world["h"], world["b"]
    assessment = run_assessment(client, h["cust_b"])
    flow = run_discovery_to_proposal(client, h["engineer"], str(b.id))
    pid = flow["proposal"]["id"]
    send_proposal(client, pid, h["engineer"], h["pm"])
    r = client.post(f"/api/v1/proposals/{pid}/decision", json={"decision": "accepted"}, headers=h["cust_b"])
    assert r.status_code == 200, r.text
    project_id = r.json()["project_id"]
    app = client.post("/api/v1/apps", json={"organisation_id": str(b.id), "project_id": project_id,
                                            "name": "Beta Assistant"}, headers=h["engineer"]).json()
    client.patch(f"/api/v1/apps/{app['id']}", json={"status": "active"}, headers=h["engineer"])
    doc = client.post(f"/api/v1/apps/{app['id']}/documents", files={"file": ("policy.txt", io.BytesIO(POLICY_DOC),
                                                                             "text/plain")},
                      data={"visibility": "organisation"}, headers=h["engineer"]).json()
    chat = client.post(f"/api/v1/apps/{app['id']}/chat", json={"question": "When must expense claims be submitted?"},
                       headers=h["cust_b"]).json()
    ticket = client.post("/api/v1/support/tickets", json={"subject": "Beta issue", "description": "Something broke"},
                         headers=h["cust_b"]).json()
    tasks = client.get(f"/api/v1/projects/{project_id}/tasks", headers=h["engineer"]).json()
    return {"assessment": assessment, "proposal_id": pid, "project_id": project_id, "app_id": app["id"],
            "document_id": doc["id"], "conversation_id": chat["conversation_id"],
            "message_id": chat["message"]["id"], "ticket_id": ticket["id"], "task_id": tasks[0]["id"],
            "architecture_id": flow["architecture"]["id"], "session_id": flow["session"]["id"]}


def test_customer_a_cannot_read_org_b_resources_by_id(client, world, org_b_estate):
    h, e = world["h"]["cust_a"], org_b_estate
    b = str(world["b"].id)
    reads = [
        f"/api/v1/organisations/{b}", f"/api/v1/organisations/{b}/journey", f"/api/v1/organisations/{b}/members",
        f"/api/v1/assessments/{e['assessment']['id']}", f"/api/v1/assessments/{e['assessment']['id']}/report",
        f"/api/v1/assessments/{e['assessment']['id']}/report.pdf",
        f"/api/v1/proposals/{e['proposal_id']}", f"/api/v1/proposals/{e['proposal_id']}/pdf",
        f"/api/v1/projects/{e['project_id']}", f"/api/v1/projects/{e['project_id']}/tasks",
        f"/api/v1/projects/{e['project_id']}/milestones", f"/api/v1/projects/{e['project_id']}/timeline",
        f"/api/v1/apps/{e['app_id']}", f"/api/v1/apps/{e['app_id']}/documents",
        f"/api/v1/documents/{e['document_id']}/download", f"/api/v1/documents/{e['document_id']}/chunks",
        f"/api/v1/conversations/{e['conversation_id']}/messages",
        f"/api/v1/support/tickets/{e['ticket_id']}", f"/api/v1/support/tickets/{e['ticket_id']}/comments",
        f"/api/v1/tasks/{e['task_id']}/comments",
    ]
    for url in reads:
        r = client.get(url, headers=h)
        assert r.status_code in (403, 404), f"{url} leaked: {r.status_code} {r.text[:200]}"
        assert "Beta" not in r.text and "expense" not in r.text.lower(), f"{url} leaked content"


def test_customer_a_cannot_write_to_org_b(client, world, org_b_estate):
    h, e = world["h"]["cust_a"], org_b_estate
    writes = [
        ("post", f"/api/v1/proposals/{e['proposal_id']}/decision", {"decision": "rejected"}),
        ("post", f"/api/v1/apps/{e['app_id']}/chat", {"question": "When must expense claims be submitted?"}),
        ("post", f"/api/v1/apps/{e['app_id']}/chat",
         {"question": "When must expense claims be submitted?", "conversation_id": e["conversation_id"]}),
        ("post", f"/api/v1/support/tickets/{e['ticket_id']}/comments", {"body": "hijack"}),
        ("post", f"/api/v1/messages/{e['message_id']}/feedback", {"rating": -1}),
        ("patch", f"/api/v1/support/tickets/{e['ticket_id']}", {"status": "closed"}),
        ("post", "/api/v1/support/tickets", {"organisation_id": str(world["b"].id), "subject": "x" * 5,
                                             "description": "spoofed org"}),
        ("post", "/api/v1/assessments", {"organisation_id": str(world["b"].id)}),
        ("delete", f"/api/v1/documents/{e['document_id']}", None),
    ]
    for method, url, body in writes:
        r = getattr(client, method)(url, json=body, headers=h) if body is not None else getattr(client, method)(url, headers=h)
        assert r.status_code in (403, 404), f"{method.upper()} {url} allowed: {r.status_code} {r.text[:200]}"


def test_customer_a_upload_to_org_b_app_rejected(client, world, org_b_estate):
    r = client.post(f"/api/v1/apps/{org_b_estate['app_id']}/documents",
                    files={"file": ("x.txt", io.BytesIO(b"injected content here"), "text/plain")},
                    headers=world["h"]["cust_a"])
    assert r.status_code == 404


def test_customer_listings_never_include_other_tenants(client, world, org_b_estate):
    h = world["h"]["cust_a"]
    for url in ["/api/v1/organisations", "/api/v1/assessments", "/api/v1/proposals", "/api/v1/projects",
                "/api/v1/apps", "/api/v1/support/tickets", "/api/v1/incidents", "/api/v1/opportunities"]:
        r = client.get(url, headers=h)
        assert r.status_code in (200, 403), url
        if r.status_code == 200:
            body = r.json()
            items = body["items"] if isinstance(body, dict) and "items" in body else body
            for item in items:
                assert item.get("organisation_id", str(world["a"].id)) == str(world["a"].id) or \
                    item.get("id") == str(world["a"].id), f"{url} returned foreign row {item}"


def test_customer_cannot_access_internal_endpoints(client, world):
    h = world["h"]["cust_a"]
    for url in ["/api/v1/crm/leads", "/api/v1/crm/pipeline", "/api/v1/dashboard/overview", "/api/v1/audit-logs",
                "/api/v1/discovery/sessions", "/api/v1/integrations", "/api/v1/settings", "/api/v1/users/staff",
                "/api/v1/evaluations/runs", "/api/v1/costs/summary", "/api/v1/crm/discovery-calls"]:
        assert client.get(url, headers=h).status_code in (403, 404), url


def test_retrieval_never_crosses_tenants(client, world, org_b_estate):
    """Org A's assistant must not retrieve Org B's chunks even for a question matching B's content exactly."""
    h, a = world["h"], world["a"]
    app_a = client.post("/api/v1/apps", json={"organisation_id": str(a.id), "name": "Alpha Assistant"},
                        headers=h["engineer"]).json()
    client.patch(f"/api/v1/apps/{app_a['id']}", json={"status": "active"}, headers=h["engineer"])
    r = client.post(f"/api/v1/apps/{app_a['id']}/chat", json={"question": "When must expense claims be submitted?"},
                    headers=h["cust_a"])
    assert r.status_code == 200
    body = r.json()
    assert body["message"]["insufficient_evidence"] is True
    assert body["message"]["citations"] == [] and body["retrieval"] == []
