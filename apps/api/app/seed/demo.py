"""Seed a complete, self-consistent demo environment.

    python -m app.seed.demo           # seed (fails if demo data already exists)
    python -m app.seed.demo --reset   # wipe ALL data, re-migrate and seed

Everything is produced through the real application services (scoring, agents in mock mode, ingestion,
retrieval, evaluation), so the demo behaves exactly like live usage. Two things are synthetic and labelled:
- telemetry_events.source = 'demo_seed' (14 days of historical traffic) - shown as "Demo telemetry" in the UI
- deployments.is_demo = true (historical release records) - a real local Docker deploy is a one-click action

DEVELOPMENT ONLY: demo credentials are public and documented in README.md.
"""

import argparse
import math
import random
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.secrets import put_secret
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.domain.workflow import sla_deadlines
from app.models import (
    ActionItem,
    AIApplication,
    Budget,
    Contact,
    Conversation,
    Deployment,
    DeploymentLog,
    DiscoveryCall,
    DiscoverySession,
    Document,
    EvaluationCase,
    EvaluationDataset,
    EvaluationRun,
    Incident,
    IncidentUpdate,
    Integration,
    Lead,
    Membership,
    Message,
    Milestone,
    ModelUsage,
    Organisation,
    Role,
    Stakeholder,
    SupportTicket,
    Task,
    TelemetryEvent,
    TicketComment,
    User,
)
from app.models.crm import Activity
from app.rag.assistant import answer_question
from app.rag.ingest import ingest_document
from app.rag.storage import get_storage, object_key
from app.seed.bootstrap import bootstrap
from app.services import assessments as assess_svc
from app.services import delivery as delivery_svc
from app.services.deployments import ensure_environments
from app.services.operations import run_evaluation

DEMO_PASSWORD = "DeployMind-demo-2026"  # noqa: S105  (documented development-only demo credential)
DOCS_DIR = Path(__file__).parent / "documents"
NOW = datetime.now(UTC)
rng = random.Random(42)

STAFF = [
    ("admin@deploymind.example", "Sam Rivera", "super_admin"),
    ("ops.admin@deploymind.example", "Jordan Lee", "org_admin"),
    ("pm@deploymind.example", "Morgan Patel", "project_manager"),
    ("engineer@deploymind.example", "Alex Chen", "engineer"),
    ("engineer2@deploymind.example", "Riley Okoro", "engineer"),
    ("viewer@deploymind.example", "Taylor Brooks", "viewer"),
]
ACME_USERS = [
    ("customer@acme-ps.example", "Priya Raman", "customer"),
    ("it.admin@acme-ps.example", "Tom Okafor", "org_admin"),
    ("auditor@acme-ps.example", "Helen Grant", "viewer"),
]
NORTHWIND_USERS = [("customer@northwind-legal.example", "Chris Novak", "customer")]

ACME_ANSWERS = {
    "strategy_vision": "some_goals", "strategy_use_cases": "shortlist", "strategy_ai_in_production": "pilots",
    "strategy_value_measured": "anecdotal", "strategy_budget": "allocated",
    "data_location": "integrated", "data_quality": "mixed", "data_documents": "dms", "data_ownership": "some",
    "data_personal": "yes",
    "process_documented": "partial", "process_volume": "very_high", "process_metrics": "partial",
    "process_exceptions": "escalation",
    "tech_cloud": "hybrid", "tech_integration": "some_apis", "tech_systems": ["crm", "database", "dms", "ticketing", "sso"],
    "tech_delivery": "some_ci", "tech_monitoring": "logs",
    "gov_policy": "basic", "gov_security": "standard", "gov_regulation": "assessed", "gov_dpia": "sometimes",
    "gov_human_review": "informal",
    "people_literacy": "3", "people_skills": "engineers", "people_sponsor": "named", "people_change": "mixed",
    "people_training": "adhoc",
}

ACME_DISCOVERY = {
    "business_problem": "Acme receives hundreds of client enquiries and internal requests every week. Employees "
                        "manually search the document repository for answers, classify each request and route it to "
                        "the right team. Response times are inconsistent and senior staff spend hours on triage.",
    "current_workflow": "Enquiries arrive via the website form, shared inbox and client portal. A triage team reads "
                        "each one, searches SharePoint-style folders for the relevant policy, manually tags the "
                        "category in the CRM and forwards it by email to Finance, Tax, Payroll, IT or Partnerships.",
    "existing_systems": "PostgreSQL (case database), CRM, internal document repository, REST APIs for case management, "
                        "ticketing system for IT requests",
    "data_sources": "Policy and procedure documents, service catalogue, CRM client records, historical enquiries",
    "apis": "Internal REST API for cases (OAuth2 client credentials), CRM REST API, webhook events on new enquiries",
    "user_roles": "Client service agents, team leads, partners, IT administrators, compliance officers",
    "security_requirements": "SSO with MFA for all users\nDocument-level access control mirroring repository "
                             "permissions\nAudit logging of every AI answer and routing decision\nNo client data sent "
                             "to providers that retain or train on it",
    "compliance_constraints": "UK GDPR; client confidential data must remain in UK-hosted systems; seven-year "
                              "retention for engagement records; AML obligations for onboarding information",
    "performance_expectations": "P95 answer latency under 5 seconds; 99.5% availability in business hours; "
                                "about 600 enquiries per week growing 20% year on year",
    "expected_outcomes": "Reduce time spent searching documents by 40%; acknowledge 100% of enquiries within four "
                         "working hours; route at least 85% of enquiries automatically",
    "budget": "£90,000 - £130,000 for the first phase",
    "timeline": "Pilot within 10 weeks; production before the January self-assessment peak",
    "acceptance_criteria": "90% of evaluation questions answered correctly with citations\nRouting accuracy of 85% "
                           "on a labelled sample\nSecurity review and DPIA signed off\nPilot users trained",
}

EVAL_CASES = [
    ("Within how many days must expense claims be submitted?", "Within 30 days of the expense being incurred",
     ["expenses-and-travel-policy.md"], ["30 days"], False),
    ("Who must approve expense claims above 500 pounds?", "A director", ["expenses-and-travel-policy.md"], ["director"], False),
    ("Where are billing and invoice questions routed?", "To the Finance team", ["enquiry-routing-guide.md"], ["Finance"], False),
    ("How quickly must every enquiry be acknowledged?", "Within four working hours", ["enquiry-routing-guide.md"],
     ["four working hours"], False),
    ("Who handles payroll queries such as payslips?", "The Payroll Services team", ["enquiry-routing-guide.md"],
     ["Payroll Services"], False),
    ("How long are payroll records retained?", "Six years after the end of the tax year", ["data-retention-schedule.md"],
     ["six years"], False),
    ("When must suspected security incidents be reported?", "Within one hour of discovery to the IT Service Desk",
     ["information-security-policy.md"], ["one hour"], False),
    ("Can staff paste client confidential information into public AI tools?", "No",
     ["information-security-policy.md"], ["must not"], False),
    ("When are P60 forms issued?", "By 31 May each year", ["service-catalogue.md"], ["31 May"], False),
    ("What must new clients complete before work begins?", "Identity verification",
     ["client-onboarding-procedure.md"], ["identity verification"], False),
    ("What is the company's share price target for next year?", "", [], [], True),
    ("How many vacation days do employees in the Singapore office get?", "", [], [], True),
]


def _ago(days: float = 0, hours: float = 0) -> datetime:
    return NOW - timedelta(days=days, hours=hours)


def _user(db: Session, email: str, name: str, role: str, org: Organisation) -> User:
    u = User(email=email, full_name=name, password_hash=hash_password(DEMO_PASSWORD), last_login_at=_ago(1))
    db.add(u)
    db.flush()
    db.add(Membership(user_id=u.id, organisation_id=org.id, role_id=db.scalar(select(Role.id).where(Role.key == role))))
    return u


def _activity(db, org, entity_type, entity_id, kind, message, actor, when, visible=False):
    db.add(Activity(organisation_id=org.id, entity_type=entity_type, entity_id=entity_id, kind=kind, message=message,
                    actor_id=actor.id if actor else None, data={}, customer_visible=visible, created_at=when))


def reset_database() -> None:
    from alembic.config import Config

    from alembic import command

    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public; CREATE EXTENSION IF NOT EXISTS vector"))
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


def seed() -> dict:
    db = SessionLocal()
    try:
        provider = bootstrap(db)
        if db.scalar(select(Organisation).where(Organisation.slug == "acme-professional-services")):
            raise SystemExit("Demo data already present. Use --reset to wipe and reseed.")
        staff = {role: _user(db, e, n, role, provider) for e, n, role in STAFF}
        staff["engineer2"] = db.scalar(select(User).where(User.email == "engineer2@deploymind.example"))
        eng, pm, admin = staff["engineer"], staff["project_manager"], staff["super_admin"]

        # ---------------------------------------------------------------- organisations & CRM
        acme = Organisation(name="Acme Professional Services", slug="acme-professional-services", kind="customer",
                            industry="Professional Services", size="501-1000", website="https://acme-ps.example",
                            country="United Kingdom", is_demo=True,
                            description="Fictional accountancy and advisory firm used for the DeployMind demo.")
        northwind = Organisation(name="Northwind Legal", slug="northwind-legal", kind="customer", industry="Legal",
                                 size="51-200", website="https://northwind-legal.example", country="United Kingdom",
                                 is_demo=True, description="Second fictional tenant demonstrating isolation.")
        db.add_all([acme, northwind])
        db.flush()
        acme_users = {role: _user(db, e, n, role, acme) for e, n, role in ACME_USERS}
        _user(db, *NORTHWIND_USERS[0][:2], NORTHWIND_USERS[0][2], northwind)
        priya = acme_users["customer"]
        contacts = [Contact(organisation_id=acme.id, full_name=n, email=e, job_title=t, is_primary=p) for n, e, t, p in [
            ("Priya Raman", "customer@acme-ps.example", "Head of Client Services", True),
            ("Tom Okafor", "it.admin@acme-ps.example", "IT Manager", False),
            ("Helen Grant", "auditor@acme-ps.example", "Operations Director", False)]]
        db.add_all(contacts)
        db.add(Contact(organisation_id=northwind.id, full_name="Chris Novak", email="customer@northwind-legal.example",
                       job_title="Practice Manager", is_primary=True))
        db.flush()
        lead = Lead(organisation_id=acme.id, title="Acme - enquiry triage & knowledge assistant", status="new",
                    source="discovery_call", owner_id=eng.id, primary_contact_id=contacts[0].id,
                    estimated_value=Decimal("115000"), summary="Inbound via discovery call; manual triage of ~600 "
                    "enquiries/week.", status_changed_at=_ago(60))
        nw_lead = Lead(organisation_id=northwind.id, title="Northwind - contract review assistant", status="qualified",
                       source="website", owner_id=pm.id, estimated_value=Decimal("60000"), status_changed_at=_ago(5))
        db.add_all([lead, nw_lead])
        db.flush()
        lead.created_at = _ago(62)
        db.add(DiscoveryCall(organisation_id=acme.id, lead_id=lead.id, full_name="Priya Raman",
                             email="customer@acme-ps.example", company=acme.name, job_title="Head of Client Services",
                             topic="Enquiry automation", message="We spend too long triaging enquiries.",
                             preferred_slot=_ago(61), status="completed", assigned_to=eng.id))
        db.add(DiscoveryCall(full_name="Jamie Ortiz", email="jamie@fabrikam.example", company="Fabrikam Logistics",
                             topic="AI readiness", message="Interested in an AI readiness assessment.",
                             preferred_slot=NOW + timedelta(days=3), status="requested"))
        for days, kind, msg in [(62, "system", "Lead created from discovery call booking"),
                                (61, "call", "Discovery call held with Priya Raman and Tom Okafor. Pain: manual triage."),
                                (58, "note", "Customer agreed to complete the AI readiness assessment.")]:
            _activity(db, acme, "lead", lead.id, kind, msg, eng, _ago(days))
        db.commit()

        # ---------------------------------------------------------------- 1-2. assessment & report
        a = assess_svc.Assessment(organisation_id=acme.id, created_by=priya.id, question_version=1, profile={
            "company_name": acme.name, "industry": acme.industry, "company_size": acme.size, "website": acme.website,
            "contact_name": priya.full_name, "contact_email": priya.email, "employee_count": 650,
            "objectives": ["reduce_operational_costs", "improve_customer_experience", "improve_employee_productivity"],
            "business_problem": "Hundreds of enquiries and internal requests triaged and routed manually"})
        db.add(a)
        db.flush()
        assess_svc.save_progress(db, a, ACME_ANSWERS, None, 7)
        assess_svc.submit(db, a, priya.id)
        assess_svc.generate_report(db, a.id)
        a.created_at, a.submitted_at = _ago(58), _ago(57)
        delivery_svc.advance_lead(db, acme.id, "assessment", priya.id, "readiness assessment completed")
        db.commit()

        # 3. opportunities: keep top five shortlisted / selected, mark the rest
        opps = assess_svc.rerank(db, acme.id)
        for o in opps:
            o.status = "selected" if o.rank == 1 else "shortlisted" if o.rank <= 5 else "identified"

        # ---------------------------------------------------------------- 4-5. discovery & requirements
        session = DiscoverySession(organisation_id=acme.id, lead_id=lead.id, title="Enquiry triage & knowledge assistant",
                                   owner_id=eng.id, session_date=date.today() - timedelta(days=52),
                                   answers=ACME_DISCOVERY,
                                   technical_notes="Case DB is PostgreSQL 15 on-prem with read replica available. "
                                                   "Repository exports via REST. CRM exposes contacts and cases.",
                                   meeting_notes="Attendees: Priya (Client Services), Tom (IT), Helen (Ops). Agreed to "
                                                 "start with grounded Q&A over policies, then automate routing.")
        db.add(session)
        db.flush()
        for n, r, inf in [("Priya Raman", "Executive sponsor", "high"), ("Tom Okafor", "IT owner", "high"),
                          ("Helen Grant", "Operations stakeholder", "medium")]:
            db.add(Stakeholder(organisation_id=acme.id, session_id=session.id, name=n, role=r, influence=inf))
        for d, o, due, st in [("Provide read-only replica credentials", "Tom Okafor", 50, "done"),
                              ("Share 200 labelled historical enquiries", "Priya Raman", 48, "done"),
                              ("Confirm data residency with DPO", "Helen Grant", 45, "done")]:
            db.add(ActionItem(organisation_id=acme.id, session_id=session.id, description=d, owner=o,
                              due_date=date.today() - timedelta(days=due), status=st))
        delivery_svc.advance_lead(db, acme.id, "discovery", eng.id, "discovery session opened")
        delivery_svc.analyze_discovery(db, session)
        reqs = delivery_svc.requirements_from_analysis(db, session, None)
        delivery_svc.import_suggested_integrations(db, session)
        for r in reqs:
            r.status, r.approved_by, r.approved_at = "approved", eng.id, _ago(50)
        session.status, session.completed_at = "completed", _ago(50)
        db.commit()

        # ---------------------------------------------------------------- 6. architecture
        arch = delivery_svc.generate_architecture(db, session, eng.id)
        arch.status, arch.reviewed_by, arch.reviewed_at = "reviewed", staff["engineer2"].id, _ago(47)
        arch.review_notes = "Peer-reviewed: confirmed pgvector sizing and UK-region hosting. Walkthrough with Tom (IT)."
        arch.created_at = _ago(48)

        # ---------------------------------------------------------------- 7-8. proposal & approved project
        proposal = delivery_svc.generate_proposal(db, session, arch, eng.id)
        proposal.created_at = _ago(46)
        delivery_svc.transition_proposal(db, proposal, "in_review", eng.id)
        delivery_svc.transition_proposal(db, proposal, "approved", pm.id)
        delivery_svc.transition_proposal(db, proposal, "sent", pm.id)
        delivery_svc.transition_proposal(db, proposal, "accepted", priya.id, "Approved by the Acme leadership team.")
        proposal.reviewed_at, proposal.sent_at, proposal.decided_at = _ago(45), _ago(45), _ago(42)
        project = delivery_svc.create_project_from_proposal(db, proposal, priya.id)
        project.start_date = date.today() - timedelta(days=42)
        project.stage = "production"
        project.target_date = date.today() + timedelta(days=14)
        delivery_svc.advance_lead(db, acme.id, "approved", pm.id, "proposal accepted")
        delivery_svc.advance_lead(db, acme.id, "implementation", pm.id, "project started")
        db.flush()
        milestones = db.scalars(select(Milestone).where(Milestone.project_id == project.id).order_by(Milestone.position)).all()
        for i, m in enumerate(milestones):
            if i < len(milestones) - 1:
                m.status, m.completed_at = "done", _ago(40 - i * 8)
            else:
                m.status = "in_progress"
        tasks = db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.created_at)).all()
        assignees = [eng, staff["engineer2"], pm]
        for i, t in enumerate(tasks):
            t.assignee_id = assignees[i % 3].id
            t.status = "done" if i < len(tasks) - 2 else ("in_progress" if i == len(tasks) - 2 else "todo")
        for stage, days in [("solution_design", 40), ("development", 33), ("integration", 24), ("testing", 16),
                            ("deployment", 9), ("production", 6)]:
            _activity(db, acme, "project", project.id, "status_change",
                      f"Project moved to {stage.replace('_', ' ').title()}", pm, _ago(days), visible=True)
        db.commit()

        # ---------------------------------------------------------------- integrations (mock connectors)
        for integ in db.scalars(select(Integration).where(Integration.organisation_id == acme.id)).all():
            integ.project_id = project.id
            base = f"{settings.api_base_url}/api/v1/mock-services"
            if integ.kind == "crm":
                integ.config = {"base_url": f"{base}/crm", "health_path": "/health"}
            elif integ.kind == "ticketing":
                integ.config = {"base_url": f"{base}/ticketing", "health_path": "/health"}
            elif integ.kind == "document_store":
                integ.config = {"base_url": f"{base}/documents", "health_path": "/health"}
            elif integ.kind == "rest_api":
                integ.config = {"base_url": f"{base}/crm", "health_path": "/health"}
            elif integ.kind == "postgres":
                integ.config = {"host": "localhost", "port": 55432, "database": "deploymind", "user": "deploymind",
                                "query": "select count(*) from organisations"}
            if integ.kind != "webhook":
                secret_value = "deploymind" if integ.kind == "postgres" else f"dm_mock_{uuid.uuid4().hex[:16]}"
                integ.credential_secret_id = put_secret(db, acme.id, f"integration:{integ.id}", secret_value, eng.id).id
                integ.status, integ.health = "configured", "unknown"

        # ---------------------------------------------------------------- 9. knowledge assistant
        app = AIApplication(organisation_id=acme.id, project_id=project.id, name="Acme Enquiry Assistant",
                            description="Grounded answers over Acme policies and procedures, with citations.",
                            provider="mock", model="mock-deterministic-1", status="active", prompt_version="v2",
                            system_prompt=__import__("app.rag.assistant", fromlist=["DEFAULT_SYSTEM_PROMPT"]).DEFAULT_SYSTEM_PROMPT)
        db.add(app)
        db.flush()
        for integ in db.scalars(select(Integration).where(Integration.organisation_id == acme.id,
                                                          Integration.kind == "document_store")).all():
            integ.config = {**integ.config, "app_id": str(app.id)}
        storage = get_storage()
        doc_ids = []
        for path in sorted(DOCS_DIR.glob("*.md")):
            data = path.read_bytes()
            key = object_key(acme.id, path.name)
            storage.put(key, data)
            d = Document(organisation_id=acme.id, app_id=app.id, project_id=project.id, kind="knowledge",
                         filename=path.name, title=path.stem.replace("-", " ").title(), content_type="text/markdown",
                         size_bytes=len(data), sha256=__import__("hashlib").sha256(data).hexdigest(), storage_key=key,
                         status="uploaded", visibility="organisation", uploaded_by=eng.id)
            db.add(d)
            db.flush()
            doc_ids.append(d.id)
        board = b"# Partner Remuneration 2026\n\nThe partner profit share pool is confidential and set at 22 percent.\n"
        key = object_key(acme.id, "partner-remuneration.md")
        storage.put(key, board)
        restricted = Document(organisation_id=acme.id, app_id=app.id, kind="knowledge", filename="partner-remuneration.md",
                              title="Partner Remuneration", content_type="text/markdown", size_bytes=len(board),
                              sha256=__import__("hashlib").sha256(board).hexdigest(), storage_key=key,
                              status="uploaded", visibility="restricted", uploaded_by=eng.id)
        db.add(restricted)
        db.commit()
        for did in [*doc_ids, restricted.id]:
            ingest_document(db, did)
        envs = {e.name: e for e in ensure_environments(db, app)}
        db.commit()

        # real conversations through the assistant (source=platform) - these are genuine telemetry
        for q in ["How quickly must we acknowledge a client enquiry?", "Who approves expense claims above 500 pounds?",
                  "Where should payroll queries be routed?", "What is the share price target?"]:
            conv = Conversation(organisation_id=acme.id, app_id=app.id, user_id=priya.id, title=q[:80])
            db.add(conv)
            db.flush()
            ans = answer_question(db, app, q, user_id=priya.id, is_internal=False)
            db.add(Message(organisation_id=acme.id, conversation_id=conv.id, role="user", content=q, created_at=NOW))
            db.add(Message(organisation_id=acme.id, conversation_id=conv.id, role="assistant", content=ans.answer,
                           citations=ans.citations, grounded=True, insufficient_evidence=ans.insufficient_evidence,
                           provider=ans.provider, model=ans.model, input_tokens=ans.input_tokens,
                           output_tokens=ans.output_tokens, latency_ms=ans.latency_ms, feedback=None if
                           ans.insufficient_evidence else 1, created_at=NOW + timedelta(seconds=1)))
        db.commit()

        # ---------------------------------------------------------------- 10. sample deployments (labelled demo records)
        history = [("staging", "v1.0.1", 12, "superseded"), ("staging", "v1.0.2", 8, "superseded"),
                   ("production", "v1.0.1", 7, "superseded"), ("staging", "v1.0.3", 4, "healthy"),
                   ("production", "v1.0.2", 3, "healthy")]
        for env_name, version, days, status in history:
            env = envs[env_name]
            dep = Deployment(organisation_id=acme.id, environment_id=env.id, version=version, adapter="seed",
                             image_tag=f"deploymind/assistant-{str(app.id)[:8]}:{version}", status=status,
                             stage="complete", triggered_by=eng.id, approved_by=admin.id if env_name == "production" else None,
                             approved_at=_ago(days) if env_name == "production" else None, is_demo=True,
                             config_snapshot={"note": "Seeded historical release record"}, started_at=_ago(days),
                             finished_at=_ago(days) + timedelta(minutes=4), health_check={"status": "ok", "seeded": True},
                             runtime={"url": None, "note": "Seeded record - no container. Deploy for real from the UI."})
            db.add(dep)
            db.flush()
            dep.created_at = _ago(days)
            for stage, msg in [("queued", "Seeded demo record - this release was not executed on this machine"),
                               ("build", f"Built image {dep.image_tag}"), ("test", "Ran 4 unit tests: OK"),
                               ("release", "Released"), ("complete", f"{version} healthy")]:
                db.add(DeploymentLog(deployment_id=dep.id, stage=stage, message=msg, created_at=_ago(days)))
            if status == "healthy":
                env.current_deployment_id, env.health_status = dep.id, "demo"
        envs["staging"].variables = {**envs["staging"].variables, "FEATURE_ROUTING": "true"}
        envs["production"].secret_refs = {"CRM_API_KEY": str(put_secret(
            db, acme.id, f"env:{envs['production'].id}:CRM_API_KEY", "dm_mock_prod_crm_key_0001", eng.id).id)}
        db.commit()

        # ---------------------------------------------------------------- 11. demo telemetry (14 days, labelled)
        incident_at = _ago(5, 3)
        rows = []
        for hour in range(14 * 24, 0, -1):
            t = NOW - timedelta(hours=hour)
            business = 8 <= t.hour <= 18 and t.weekday() < 5
            n = rng.randint(6, 14) if business else rng.randint(0, 3)
            spike = abs((t - incident_at).total_seconds()) < 3 * 3600
            for _ in range(n):
                err = rng.random() < (0.18 if spike else 0.012)
                lat = int(rng.lognormvariate(math.log(4200 if spike else 1100), 0.35))
                tin, tout = rng.randint(900, 2200), rng.randint(120, 380)
                rows.append(TelemetryEvent(
                    organisation_id=acme.id, app_id=app.id, environment="production", source="demo_seed",
                    kind="rag_query", status="error" if err else "success", latency_ms=lat,
                    retrieval_ms=int(lat * rng.uniform(0.08, 0.2)), retrieved_chunks=5,
                    top_relevance=round(rng.uniform(0.35, 0.8), 3), provider="openai", model="gpt-4o-mini",
                    input_tokens=tin, output_tokens=tout,
                    cost_usd=Decimal(tin) * Decimal("0.15") / 1_000_000 + Decimal(tout) * Decimal("0.60") / 1_000_000,
                    error=("Provider timeout after 30s" if spike else "Retrieval DB connection reset") if err else None,
                    created_at=t + timedelta(minutes=rng.randint(0, 59))))
            if hour % 1 == 0:
                rows.append(TelemetryEvent(organisation_id=acme.id, app_id=app.id, environment="production",
                                           source="demo_seed", kind="health_check",
                                           status="error" if spike and rng.random() < 0.5 else "success",
                                           latency_ms=40, created_at=t))
        db.add_all(rows)
        for r in rows:
            if r.kind == "rag_query" and r.status == "success":
                db.add(ModelUsage(organisation_id=acme.id, project_id=project.id, app_id=app.id,
                                  agent="knowledge_assistant_agent", provider=r.provider, model=r.model,
                                  input_tokens=r.input_tokens, output_tokens=r.output_tokens, cost_usd=r.cost_usd,
                                  latency_ms=r.latency_ms, is_demo=True, created_at=r.created_at))
        db.add(Budget(organisation_id=acme.id, project_id=None, monthly_limit_usd=Decimal("25"), alert_threshold_pct=80))
        db.commit()

        # ---------------------------------------------------------------- 12. evaluation dataset & runs (real runs)
        ds = EvaluationDataset(organisation_id=acme.id, app_id=app.id, name="Acme policy Q&A v1",
                               description="Questions built from 200 labelled historical enquiries (subset).")
        db.add(ds)
        db.flush()
        for q, exp, src, kws, refuse in EVAL_CASES:
            db.add(EvaluationCase(organisation_id=acme.id, dataset_id=ds.id, question=q, expected_answer=exp,
                                  expected_sources=src, expected_keywords=kws, must_refuse=refuse,
                                  tags=["refusal"] if refuse else ["policy"]))
        db.commit()
        runs = []
        for label, retrieval in [("Baseline - hybrid top_k=5", None),
                                 ("Experiment - vector only top_k=3", {"keyword_weight": 0.0, "top_k": 3}),
                                 ("Release candidate v2 prompt", None)]:
            run = EvaluationRun(organisation_id=acme.id, app_id=app.id, dataset_id=ds.id, label=label,
                                config={"provider": "mock", "model": "mock-deterministic-1", "prompt_version":
                                        "v2" if "v2" in label else "v1",
                                        "retrieval": {**app.retrieval_config, **(retrieval or {})},
                                        "llm_judge": False, "grounded_mode": True}, triggered_by=eng.id)
            db.add(run)
            db.commit()
            runs.append(run_evaluation(db, run.id))

        # ---------------------------------------------------------------- 13. resolved incident
        inc = Incident(organisation_id=acme.id, project_id=project.id, app_id=app.id, environment_id=envs["production"].id,
                       code="INC-0001", title="Elevated latency and timeouts on Enquiry Assistant",
                       description="P95 latency exceeded 4s and ~18% of requests failed for about three hours.",
                       severity="sev2", status="closed", assignee_id=eng.id, reported_by=staff["engineer2"].id,
                       detected_at=incident_at - timedelta(hours=1), identified_at=incident_at,
                       resolved_at=incident_at + timedelta(hours=2), closed_at=incident_at + timedelta(days=1),
                       root_cause="LLM provider regional degradation combined with no client-side timeout budget; "
                                  "retries amplified load.",
                       resolution="Added 15s timeout with a single retry and circuit breaker; enabled fallback model; "
                                  "added latency SLO alert at P95 > 3s.",
                       customer_impact="Slower answers and some failed requests for client service agents.")
        db.add(inc)
        db.flush()
        for offset, st, msg, public in [
            (-1, "open", "Alert fired: P95 latency > 3s for 10 minutes", False),
            (-0.75, "investigating", "We are investigating slow responses from the Enquiry Assistant.", True),
            (0, "identified", "Cause identified: upstream AI provider degradation. Mitigation in progress.", True),
            (2, "resolved", "Mitigation deployed. Response times are back to normal.", True),
            (24, "closed", "Post-incident review completed; actions tracked in project board.", True)]:
            db.add(IncidentUpdate(organisation_id=acme.id, incident_id=inc.id, author_id=eng.id, kind="status_change",
                                  status=st, message=msg, public=public, created_at=incident_at + timedelta(hours=offset)))

        # ---------------------------------------------------------------- 14. support history
        tickets = [
            ("How do I give a new team lead access to the assistant?", "access", "medium", "resolved", 20,
             "Added via Organisation > Members with the customer role.", [
                 (False, priya, "We have a new team lead starting Monday."),
                 (False, eng, "You can add them under Organisation > Members. I have added a short guide."),
                 (True, eng, "Customer org_admin is Tom; confirm SSO group mapping.")]),
            ("Assistant cited an outdated travel policy", "bug", "high", "resolved", 9,
             "Re-synced document store and reprocessed the updated policy.", [
                 (False, priya, "An answer quoted the old hotel limit."),
                 (False, eng, "Thanks - the repository had an older copy. Re-synced and reprocessed.")]),
            ("Can the assistant draft replies to client emails?", "feature_request", "low", "in_progress", 2, None, [
                 (False, priya, "Would love draft replies, not just answers."),
                 (False, pm, "Great idea - we are scoping this for phase 2 and will share a proposal.")]),
        ]
        for i, (subj, cat, prio, status, days, notes, comments) in enumerate(tickets, start=1):
            opened = _ago(days)
            resp, res = sla_deadlines(prio, opened)
            t = SupportTicket(organisation_id=acme.id, project_id=project.id, code=f"SUP-{i:04d}", subject=subj,
                              description=comments[0][2], category=cat, priority=prio, status=status,
                              requester_id=priya.id, assignee_id=eng.id, response_due_at=resp, resolution_due_at=res,
                              first_response_at=opened + timedelta(hours=1),
                              resolved_at=opened + timedelta(hours=20) if status == "resolved" else None,
                              resolution_notes=notes)
            db.add(t)
            db.flush()
            t.created_at = opened
            for j, (internal, author, body) in enumerate(comments):
                c = TicketComment(organisation_id=acme.id, ticket_id=t.id, author_id=author.id, body=body, internal=internal)
                db.add(c)
                db.flush()
                c.created_at = opened + timedelta(hours=j)
        db.commit()
        return {"acme_id": str(acme.id), "app_id": str(app.id), "project_id": str(project.id),
                "overall_score": float(a.overall_score), "eval_pass_rates": [r.metrics.get("pass_rate") for r in runs]}
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the DeployMind demo environment (development only)")
    parser.add_argument("--reset", action="store_true", help="Drop ALL data, re-run migrations and seed")
    args = parser.parse_args()
    if settings.is_production:
        sys.exit("Refusing to seed demo data with APP_ENV=production")
    if args.reset:
        print("Resetting database ...")
        reset_database()
    info = seed()
    print("Demo environment ready:", info)
    print(f"All demo accounts use the password: {DEMO_PASSWORD}  (development only)")


if __name__ == "__main__":
    main()
