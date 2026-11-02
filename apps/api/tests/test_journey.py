"""Section 15 acceptance scenario, end to end through the public API."""

import io

from tests.helpers import ANSWERS, DISCOVERY, POLICY_DOC, PROFILE
from tests.test_deploy import FakeAdapter, fake_adapter  # noqa: F401  (autouse fixture)


def test_full_customer_journey(client, world):
    staff = world["h"]

    # 1. Visitor registers an organisation
    reg = client.post("/api/v1/auth/register", json={
        "full_name": "Casey Customer", "email": "casey@journey.example", "password": "Journey-pass-1",
        "organisation_name": "Journey Partners", "industry": "Professional Services", "company_size": "201-500"})
    assert reg.status_code == 201
    cust = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    org_id = client.get("/api/v1/auth/me", headers=cust).json()["memberships"][0]["organisation_id"]

    # 2. Completes an AI readiness assessment with save-and-resume
    a = client.post("/api/v1/assessments", json={}, headers=cust).json()
    half = dict(list(ANSWERS.items())[:10])
    client.put(f"/api/v1/assessments/{a['id']}/progress", json={"answers": half, "profile": PROFILE, "current_step": 2},
               headers=cust)
    resumed = client.get(f"/api/v1/assessments/{a['id']}", headers=cust).json()
    assert resumed["current_step"] == 2 and len(resumed["answers"]) == 10
    incomplete = client.post(f"/api/v1/assessments/{a['id']}/submit", headers=cust)
    assert incomplete.status_code == 400 and incomplete.json()["error"]["code"] == "assessment_incomplete"
    client.put(f"/api/v1/assessments/{a['id']}/progress", json={"answers": ANSWERS, "current_step": 7}, headers=cust)
    submitted = client.post(f"/api/v1/assessments/{a['id']}/submit", headers=cust).json()

    # 3. Backend calculates the score deterministically; 4. AI writes the personalised report
    report = client.get(f"/api/v1/assessments/{a['id']}/report", headers=cust).json()
    assert submitted["overall_score"] == report["assessment"]["overall_score"] and 0 < submitted["overall_score"] < 100
    assert report["assessment"]["report_status"] == "ready" and report["report"]["executive_summary"]
    assert len(report["opportunities"]) == 7 and report["opportunities"][0]["rank"] == 1
    assert report["findings"]["plan_30_60_90"] and report["findings"]["roadmap"]
    pdf = client.get(f"/api/v1/assessments/{a['id']}/report.pdf", headers=cust)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # 5. Engineer sees the organisation in the CRM, pipeline advanced automatically
    leads = client.get("/api/v1/crm/leads?q=Journey", headers=staff["engineer"]).json()["items"]
    assert leads and leads[0]["status"] == "assessment"  # advanced automatically on submission
    lead_id = leads[0]["id"]

    # 6. Discovery session with requirements (AI drafts, engineer approves)
    s = client.post("/api/v1/discovery/sessions", json={"organisation_id": org_id, "title": "Enquiry assistant"},
                    headers=staff["engineer"]).json()
    client.patch(f"/api/v1/discovery/sessions/{s['id']}", json={"answers": DISCOVERY}, headers=staff["engineer"])
    analysed = client.post(f"/api/v1/discovery/sessions/{s['id']}/analyze", headers=staff["engineer"]).json()
    assert analysed["ai_analysis"]["proposed_requirements"] and analysed["ai_analysis"]["follow_up_questions"] is not None
    reqs = client.post(f"/api/v1/discovery/sessions/{s['id']}/import-requirements", json={},
                       headers=staff["engineer"]).json()
    no_arch = client.post("/api/v1/architecture/generate", json={"session_id": s["id"]}, headers=staff["engineer"])
    assert no_arch.status_code == 400  # requirements still drafts
    for r in reqs:
        client.post(f"/api/v1/requirements/{r['id']}/decision", json={"decision": "approved"}, headers=staff["engineer"])
    assert client.post(f"/api/v1/discovery/sessions/{s['id']}/complete", headers=staff["engineer"]).status_code == 200

    # 7. Solution architect generates (unvalidated) architecture, engineer edits and reviews
    arch = client.post("/api/v1/architecture/generate", json={"session_id": s["id"]}, headers=staff["engineer"]).json()
    assert arch["status"] == "draft" and arch["mermaid"].startswith("graph")
    client.put(f"/api/v1/architecture/{arch['id']}", json={"mermaid": arch["mermaid"] + "\n  A --> X[Audit store]"},
               headers=staff["engineer"])
    reviewed = client.post(f"/api/v1/architecture/{arch['id']}/review", json={"notes": "Reviewed with customer CTO"},
                           headers=staff["engineer"]).json()
    assert reviewed["status"] == "reviewed"

    # 8. Proposal agent drafts; edits create versions; PM approves and sends
    prop = client.post("/api/v1/proposals/generate", json={"session_id": s["id"], "architecture_id": arch["id"]},
                       headers=staff["engineer"]).json()
    assert prop["status"] == "draft" and prop["content"]["total"] == sum(c["amount"] for c in prop["content"]["costs"])
    edited = client.put(f"/api/v1/proposals/{prop['id']}", json={"content": {"executive_summary": "Revised summary"},
                                                                 "change_note": "Tone"}, headers=staff["engineer"]).json()
    assert edited["current_version"] == 2 and len(edited["versions"]) == 2
    for st, h in (("in_review", staff["engineer"]), ("approved", staff["pm"]), ("sent", staff["pm"])):
        assert client.post(f"/api/v1/proposals/{prop['id']}/transition", json={"status": st}, headers=h).status_code == 200

    # 9. Customer reviews and approves; 10. project is created automatically
    seen = client.get(f"/api/v1/proposals/{prop['id']}", headers=cust).json()
    assert "provenance" not in seen["content"] and seen["versions"] == []
    decided = client.post(f"/api/v1/proposals/{prop['id']}/decision", json={"decision": "accepted", "comment": "Go"},
                          headers={**cust, "Idempotency-Key": "accept-1"}).json()
    again = client.post(f"/api/v1/proposals/{prop['id']}/decision", json={"decision": "accepted", "comment": "Go"},
                        headers={**cust, "Idempotency-Key": "accept-1"})
    assert again.status_code == 200 and again.json()["project_id"] == decided["project_id"]
    project_id = decided["project_id"]
    project = client.get(f"/api/v1/projects/{project_id}", headers=staff["engineer"]).json()
    assert project["tasks_total"] > 0
    lead = client.get(f"/api/v1/crm/leads/{lead_id}", headers=staff["engineer"]).json()
    assert lead["status"] == "implementation"

    # Engineer drives the project through stages and tasks
    for stage in ("solution_design", "development", "integration"):
        assert client.post(f"/api/v1/projects/{project_id}/stage", json={"stage": stage},
                           headers=staff["engineer"]).status_code == 200
    tasks = client.get(f"/api/v1/projects/{project_id}/tasks", headers=staff["engineer"]).json()
    t1, t2 = tasks[0], tasks[1]
    client.post(f"/api/v1/tasks/{t2['id']}/dependencies", json={"depends_on_id": t1["id"]}, headers=staff["engineer"])
    blocked = client.patch(f"/api/v1/tasks/{t2['id']}", json={"status": "done"}, headers=staff["engineer"])
    assert blocked.status_code == 409
    client.patch(f"/api/v1/tasks/{t1['id']}", json={"status": "done"}, headers=staff["engineer"])
    assert client.patch(f"/api/v1/tasks/{t2['id']}", json={"status": "done"}, headers=staff["engineer"]).status_code == 200

    # 11. Engineer uploads documents and builds the RAG assistant; 12. answers with citations
    app = client.post("/api/v1/apps", json={"organisation_id": org_id, "project_id": project_id,
                                            "name": "Enquiry Assistant"}, headers=staff["engineer"]).json()
    client.patch(f"/api/v1/apps/{app['id']}", json={"status": "active"}, headers=staff["engineer"])
    up = client.post(f"/api/v1/apps/{app['id']}/documents",
                     files={"file": ("expense-policy.md", io.BytesIO(POLICY_DOC), "text/markdown")},
                     headers=staff["engineer"])
    assert up.status_code == 201
    chat = client.post(f"/api/v1/apps/{app['id']}/chat", json={"question": "Do claims above 500 pounds need approval?"},
                       headers=cust).json()
    assert chat["message"]["citations"] and "director" in chat["message"]["content"]

    # 13. Configure, build and deploy locally (adapter faked in tests; real Docker in the demo)
    envs = {e["name"]: e for e in client.get(f"/api/v1/apps/{app['id']}/environments", headers=staff["engineer"]).json()}
    client.patch(f"/api/v1/environments/{envs['development']['id']}", json={"variables": {"FEATURE_FLAGS": "citations"}},
                 headers=staff["engineer"])
    dep = client.post(f"/api/v1/environments/{envs['development']['id']}/deploy", headers=staff["engineer"]).json()
    dep = client.get(f"/api/v1/deployments/{dep['id']}", headers=staff["engineer"]).json()
    assert dep["status"] == "healthy"

    # 14. Deployment appears in monitoring; requests, latency, tokens, cost and evaluations recorded
    token = FakeAdapter.tokens[-1]
    client.post("/api/v1/runtime/ask", json={"question": "Are receipts mandatory for claims over 25 pounds?"},
                headers={"Authorization": f"Bearer {token}"})
    mon = client.get(f"/api/v1/monitoring/overview?app_id={app['id']}&hours=1", headers=staff["engineer"]).json()
    assert mon["requests"] >= 2 and mon["sources_present"]["deployment"] >= 1 and mon["uptime"]["checks"] >= 1
    assert "latency_ms" in mon and mon["tokens"]["total"] > 0 and "estimated_cost_usd" in mon
    ds = client.post("/api/v1/evaluations/datasets", json={"app_id": app["id"], "name": "Core"},
                     headers=staff["engineer"]).json()
    client.post(f"/api/v1/evaluations/datasets/{ds['id']}/cases", json={
        "question": "Within how many days must expense claims be submitted?", "expected_answer": "Within 30 days",
        "expected_sources": ["expense-policy.md"], "expected_keywords": ["30 days"]}, headers=staff["engineer"])
    client.post(f"/api/v1/evaluations/datasets/{ds['id']}/cases", json={
        "question": "What is the parental leave entitlement in Japan?", "must_refuse": True}, headers=staff["engineer"])
    run = client.post("/api/v1/evaluations/runs", json={"dataset_id": ds["id"], "label": "baseline"},
                      headers=staff["engineer"]).json()
    run = client.get(f"/api/v1/evaluations/runs/{run['id']}", headers=staff["engineer"]).json()
    assert run["run"]["status"] == "completed" and run["run"]["metrics"]["pass_rate"] == 1.0
    worse = client.post("/api/v1/evaluations/runs", json={"dataset_id": ds["id"], "label": "top_k=1 strict",
                                                           "retrieval": {"top_k": 1, "min_relevance": 0.95}},
                        headers=staff["engineer"]).json()
    worse = client.get(f"/api/v1/evaluations/runs/{worse['id']}", headers=staff["engineer"]).json()["run"]
    assert worse["regressions"], "a stricter retrieval config should register as a regression"
    cmp = client.get(f"/api/v1/evaluations/compare?run_ids={run['run']['id']},{worse['id']}", headers=staff["engineer"])
    assert cmp.status_code == 200 and len(cmp.json()["metrics"]["pass_rate"]) == 2

    # 15. Incident created, investigated, resolved and communicated to the customer
    inc = client.post("/api/v1/incidents", json={"organisation_id": org_id, "title": "Elevated latency", "severity": "sev2",
                                                 "app_id": app["id"], "environment_id": envs["development"]["id"]},
                      headers=staff["engineer"]).json()
    analysed = client.post(f"/api/v1/incidents/{inc['id']}/analyze", headers=staff["engineer"]).json()
    assert analysed["ai_analysis"]["suggested_actions"]
    client.post(f"/api/v1/incidents/{inc['id']}/status", json={"status": "investigating", "message": "Looking into it",
                                                               "notify_customer": True}, headers=staff["engineer"])
    early = client.post(f"/api/v1/incidents/{inc['id']}/status", json={"status": "resolved", "message": "Fixed"},
                        headers=staff["engineer"])
    assert early.status_code == 400  # resolution must be recorded first
    client.patch(f"/api/v1/incidents/{inc['id']}", json={"root_cause": "Connection pool exhaustion",
                                                         "resolution": "Raised pool size; added alert"},
                 headers=staff["engineer"])
    for st in ("identified", "resolved", "closed"):
        assert client.post(f"/api/v1/incidents/{inc['id']}/status", json={"status": st, "message": f"Now {st}",
                                                                          "notify_customer": st == "resolved"},
                           headers=staff["engineer"]).status_code == 200
    timeline = client.get(f"/api/v1/incidents/{inc['id']}/updates", headers=cust).json()
    assert [u["status"] for u in timeline] == ["investigating", "resolved"]  # customer sees public updates only
    notes = client.get("/api/v1/notifications", headers=cust).json()
    assert any(n["kind"] == "incident.update" for n in notes)

    # 16. Customer views the complete journey from their portal
    j = client.get(f"/api/v1/organisations/{org_id}/journey", headers=cust).json()
    assert {s["key"]: s["done"] for s in j["stages"]} == {"assess": True, "opportunities": True, "proposal": True,
                                                          "build": False, "deploy": True, "run": False}
    assert j["incidents"][0]["status"] == "closed" and j["projects"][0]["id"] == project_id
    ticket = client.post("/api/v1/support/tickets", json={"subject": "How do I add users?", "description": "Please help",
                                                           "priority": "high"}, headers=cust).json()
    assert ticket["sla_response"] == "on_track"
    client.post(f"/api/v1/support/tickets/{ticket['id']}/comments", json={"body": "Internal: check SSO", "internal": True},
                headers=staff["engineer"])
    client.post(f"/api/v1/support/tickets/{ticket['id']}/comments", json={"body": "Use the members page"},
                headers=staff["engineer"])
    seen = client.get(f"/api/v1/support/tickets/{ticket['id']}/comments", headers=cust).json()
    assert [c["body"] for c in seen] == ["Use the members page"]
    assert client.get(f"/api/v1/support/tickets/{ticket['id']}", headers=cust).json()["first_response_at"]
