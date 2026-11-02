"""Reusable API flows for tests."""

ANSWERS = {
    "strategy_vision": "some_goals", "strategy_use_cases": "shortlist", "strategy_ai_in_production": "tools",
    "strategy_budget": "small",
    "data_location": "integrated", "data_quality": "mixed", "data_documents": "dms", "data_ownership": "some",
    "data_personal": "yes",
    "process_documented": "partial", "process_volume": "high", "process_metrics": "some", "process_exceptions": "escalation",
    "tech_cloud": "hybrid", "tech_integration": "some_apis", "tech_systems": ["crm", "database", "dms"],
    "tech_delivery": "some_ci", "tech_monitoring": "logs",
    "gov_policy": "drafting", "gov_security": "standard", "gov_regulation": "assessed", "gov_dpia": "sometimes",
    "gov_human_review": "informal",
    "people_literacy": "3", "people_skills": "engineers", "people_sponsor": "interested", "people_change": "mixed",
    "people_training": "adhoc",
}

PROFILE = {"company_name": "Org Alpha", "industry": "Professional Services", "company_size": "201-500",
           "objectives": ["reduce_operational_costs", "improve_employee_productivity"],
           "business_problem": "Hundreds of enquiries handled manually"}

DISCOVERY = {
    "business_problem": "Staff manually search documents to answer customer enquiries and classify internal requests.",
    "current_workflow": "Enquiries arrive by email; staff search the document repository manually and route requests "
                        "to teams by hand.",
    "existing_systems": "PostgreSQL, CRM, internal document repository, REST APIs",
    "data_sources": "Policy documents, procedures, CRM records",
    "apis": "Internal REST APIs for case management",
    "user_roles": "Client service agents, team leads, administrators",
    "security_requirements": "SSO for all users\nDocument-level access control\nAudit logging of AI answers",
    "compliance_constraints": "GDPR; client confidential data must not leave the UK",
    "performance_expectations": "Answers within 5 seconds at P95; 99.5% availability",
    "expected_outcomes": "Reduce time spent searching documents by 40%",
    "budget": "£80k-£120k",
    "timeline": "Pilot within 3 months",
    "acceptance_criteria": "90% of evaluation questions answered correctly with citations\nSecurity review passed",
}

POLICY_DOC = b"""# Expense Policy

Employees must submit expense claims within 30 days of the expense being incurred.
Claims above 500 pounds require approval from a director before reimbursement.
Receipts are mandatory for every claim over 25 pounds.

# Travel

Economy class travel is required for flights under six hours.
Hotel bookings must be made through the approved travel portal.
"""

SECRET_DOC = b"""# Board Remuneration

The chief executive bonus pool for this year is confidential and set at 14 percent of profit.
"""


def run_assessment(client, h, org_id=None) -> dict:
    body = {"organisation_id": org_id} if org_id else {}
    a = client.post("/api/v1/assessments", json=body, headers=h)
    assert a.status_code == 201, a.text
    aid = a.json()["id"]
    r = client.put(f"/api/v1/assessments/{aid}/progress", json={"answers": ANSWERS, "profile": PROFILE,
                                                                 "current_step": 7}, headers=h)
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/assessments/{aid}/submit", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def run_discovery_to_proposal(client, eng, org_id, approver=None) -> dict:
    s = client.post("/api/v1/discovery/sessions", json={"organisation_id": org_id, "title": "Knowledge assistant"},
                    headers=eng).json()
    r = client.patch(f"/api/v1/discovery/sessions/{s['id']}", json={"answers": DISCOVERY}, headers=eng)
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/discovery/sessions/{s['id']}/analyze", headers=eng)
    assert r.status_code == 200, r.text
    reqs = client.post(f"/api/v1/discovery/sessions/{s['id']}/import-requirements", json={}, headers=eng).json()
    assert reqs and all(x["status"] == "draft" for x in reqs)
    for req in reqs:
        assert client.post(f"/api/v1/requirements/{req['id']}/decision", json={"decision": "approved"},
                           headers=eng).status_code == 200
    arch = client.post("/api/v1/architecture/generate", json={"session_id": s["id"]}, headers=eng)
    assert arch.status_code == 201, arch.text
    prop = client.post("/api/v1/proposals/generate", json={"session_id": s["id"], "architecture_id": arch.json()["id"]},
                       headers=eng)
    assert prop.status_code == 201, prop.text
    return {"session": s, "architecture": arch.json(), "proposal": prop.json()}


def send_proposal(client, pid, author, approver):
    for status, h in (("in_review", author), ("approved", approver), ("sent", approver)):
        r = client.post(f"/api/v1/proposals/{pid}/transition", json={"status": status}, headers=h)
        assert r.status_code == 200, (status, r.text)
