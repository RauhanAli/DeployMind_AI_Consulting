import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.agents.delivery import (
    ARCHITECT_AGENT,
    DISCOVERY_AGENT,
    PROPOSAL_AGENT,
    ArchitectAgentIn,
    DiscoveryAgentIn,
    ProposalAgentIn,
)
from app.ai.agents.framework import AgentRunner, provenance
from app.core.errors import AppError, InvalidTransition
from app.domain.workflow import LEAD_PIPELINE, PROPOSAL_FLOW, check_transition
from app.models import (
    ArchitectureDocument,
    DiscoverySession,
    Integration,
    Lead,
    Milestone,
    Opportunity,
    Organisation,
    PlatformSetting,
    Project,
    Proposal,
    ProposalVersion,
    Requirement,
    Stakeholder,
    Task,
)
from app.services.common import notify, record_activity


# ------------------------------------------------------------------ lead pipeline automation
def advance_lead(db: Session, org_id: uuid.UUID, target: str, actor_id: uuid.UUID | None, reason: str) -> None:
    """System-driven forward-only pipeline progression (manual changes go through check_lead_transition)."""
    lead = db.scalar(select(Lead).where(Lead.organisation_id == org_id, Lead.status != "lost")
                     .order_by(Lead.created_at.desc()).limit(1))
    if lead is None or LEAD_PIPELINE.index(target) <= LEAD_PIPELINE.index(lead.status):
        return
    old = lead.status
    lead.status = target
    lead.status_changed_at = datetime.now(UTC)
    record_activity(db, org_id, "lead", lead.id, "status_change", f"Pipeline moved {old} → {target}: {reason}",
                    actor_id, {"from": old, "to": target, "automatic": True})


# ------------------------------------------------------------------ discovery
def analyze_discovery(db: Session, session: DiscoverySession, provider: str | None = None) -> dict:
    org = db.get(Organisation, session.organisation_id)
    stakeholders = db.scalars(select(Stakeholder).where(Stakeholder.session_id == session.id)).all()
    existing = db.scalars(select(Requirement.title).where(Requirement.session_id == session.id)).all()
    outcome = AgentRunner(db, session.organisation_id, provider=provider).run(DISCOVERY_AGENT, DiscoveryAgentIn(
        organisation=org.name, answers={k: str(v or "") for k, v in session.answers.items()},
        technical_notes=session.technical_notes, meeting_notes=session.meeting_notes,
        stakeholders=[{"name": s.name, "role": s.role, "influence": s.influence} for s in stakeholders],
        existing_requirements=list(existing),
    ))
    session.ai_analysis = {**outcome.output.model_dump(), "provenance": provenance("discovery_agent", outcome),
                           "generated_at": datetime.now(UTC).isoformat()}
    db.flush()
    return session.ai_analysis


def next_requirement_code(db: Session, org_id: uuid.UUID) -> str:
    n = db.scalar(select(func.count()).select_from(Requirement).where(Requirement.organisation_id == org_id)) or 0
    return f"REQ-{n + 1:03d}"


def requirements_from_analysis(db: Session, session: DiscoverySession, indexes: list[int] | None) -> list[Requirement]:
    proposed = (session.ai_analysis or {}).get("proposed_requirements") or []
    if not proposed:
        raise AppError("Run the discovery assistant before importing requirements", code="no_analysis")
    chosen = [proposed[i] for i in (indexes if indexes is not None else range(len(proposed))) if 0 <= i < len(proposed)]
    rows = []
    for p in chosen:
        r = Requirement(organisation_id=session.organisation_id, session_id=session.id,
                        code=next_requirement_code(db, session.organisation_id), title=p["title"][:300],
                        description=p["description"], category=p["category"], priority=p["priority"],
                        acceptance_criteria=p["acceptance_criteria"], status="draft", source="ai")
        db.add(r)
        db.flush()
        rows.append(r)
    return rows


def import_suggested_integrations(db: Session, session: DiscoverySession) -> list[Integration]:
    existing = {(i.kind, i.name) for i in db.scalars(select(Integration).where(
        Integration.organisation_id == session.organisation_id)).all()}
    rows = []
    for s in (session.ai_analysis or {}).get("suggested_integrations") or []:
        if (s["kind"], s["name"]) in existing:
            continue
        row = Integration(organisation_id=session.organisation_id, session_id=session.id, name=s["name"],
                          kind=s["kind"], description=s["purpose"], status="inventory")
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


# ------------------------------------------------------------------ architecture
def generate_architecture(db: Session, session: DiscoverySession, actor_id: uuid.UUID | None,
                          provider: str | None = None) -> ArchitectureDocument:
    reqs = db.scalars(select(Requirement).where(Requirement.session_id == session.id,
                                                Requirement.status == "approved")).all()
    if not reqs:
        raise AppError("At least one approved requirement is needed before generating an architecture",
                       code="no_approved_requirements")
    integrations = db.scalars(select(Integration).where(Integration.organisation_id == session.organisation_id)).all()
    org = db.get(Organisation, session.organisation_id)
    a = session.answers
    outcome = AgentRunner(db, session.organisation_id, provider=provider).run(ARCHITECT_AGENT, ArchitectAgentIn(
        organisation=org.name, problem=str(a.get("business_problem") or session.title),
        requirements=[{"code": r.code, "title": r.title, "category": r.category, "priority": r.priority}
                      for r in reqs],
        integrations=[{"name": i.name, "kind": i.kind} for i in integrations],
        constraints={k: str(a.get(k) or "") for k in ("security_requirements", "compliance_constraints",
                                                       "performance_expectations", "budget", "timeline")},
    ))
    content = outcome.output.model_dump()
    mermaid = content.pop("mermaid")
    version = (db.scalar(select(func.max(ArchitectureDocument.version))
                         .where(ArchitectureDocument.session_id == session.id)) or 0) + 1
    doc = ArchitectureDocument(
        organisation_id=session.organisation_id, session_id=session.id, title=f"Solution architecture v{version}",
        version=version, status="draft", content={**content, "provenance": provenance("solution_architect_agent", outcome),
                                                  "requirement_codes": [r.code for r in reqs]},
        mermaid=mermaid, source="ai", generated_model=f"{outcome.provider}:{outcome.model}", created_by=actor_id,
    )
    db.add(doc)
    db.flush()
    return doc


# ------------------------------------------------------------------ proposal estimation (deterministic)
DEFAULT_RATE_CARD = {"currency": "GBP", "days_per_week": 5,
                     "roles": {"Forward Deployed Engineer (lead)": 1100, "AI Engineer": 950,
                               "Integration Engineer": 850, "Delivery Manager": 800},
                     "infrastructure_estimate": 1500, "support_monthly": 1500, "support_months": 3}

PHASES = [("Discovery & solution design", 0.15, "solution_design"), ("Core build", 0.35, "development"),
          ("Integrations", 0.20, "integration"), ("Testing & evaluation", 0.15, "testing"),
          ("Deployment & hypercare", 0.15, "deployment")]


def rate_card(db: Session) -> dict:
    row = db.get(PlatformSetting, "rate_card")
    return {**DEFAULT_RATE_CARD, **(row.value if row else {})}


def estimate_proposal(db: Session, org_id: uuid.UUID, requirements: list[Requirement]) -> dict:
    rc = rate_card(db)
    top = db.scalar(select(Opportunity).where(Opportunity.organisation_id == org_id).order_by(Opportunity.rank).limit(1))
    base = top.effort_weeks if top else 8
    n_int = sum(1 for r in requirements if r.category == "integration")
    n_sec = sum(1 for r in requirements if r.category == "security" and r.priority == "must")
    weeks = base + max(0, n_int - 2) + (1 if n_sec > 3 else 0)
    basis = [f"Base effort {base} weeks" + (f" from top opportunity '{top.title}'" if top else " (default)"),
             f"+{max(0, n_int - 2)} week(s) for {n_int} integration requirement(s) beyond two",
             f"+{1 if n_sec > 3 else 0} week for {n_sec} must-have security requirement(s)"]
    milestones, cursor = [], 0
    for title, share, stage in PHASES:
        w = max(1, round(weeks * share))
        milestones.append({"title": title, "start_week": cursor + 1, "weeks": w, "stage": stage})
        cursor += w
    total_weeks = cursor
    allocation = {"Forward Deployed Engineer (lead)": 1.0, "AI Engineer": 1.0,
                  "Integration Engineer": 0.5 if n_int else 0.0, "Delivery Manager": 0.3}
    team, costs = [], []
    for role, alloc in allocation.items():
        if not alloc:
            continue
        rate = rc["roles"][role]
        amount = round(total_weeks * rc["days_per_week"] * rate * alloc)
        team.append({"role": role, "allocation": alloc, "day_rate": rate})
        costs.append({"item": f"{role} ({alloc:.0%} x {total_weeks} weeks)", "amount": amount})
    costs.append({"item": "Cloud infrastructure during delivery (estimate)", "amount": rc["infrastructure_estimate"]})
    costs.append({"item": f"Post-go-live support ({rc['support_months']} months)",
                  "amount": rc["support_monthly"] * rc["support_months"]})
    return {"timeline_weeks": total_weeks, "milestones": milestones, "team": team, "costs": costs,
            "total": sum(c["amount"] for c in costs), "currency": rc["currency"], "basis": basis,
            "label": "Estimate based on the rate card and stated assumptions; excludes model usage costs."}


def generate_proposal(db: Session, session: DiscoverySession, architecture: ArchitectureDocument,
                      actor_id: uuid.UUID | None, provider: str | None = None) -> Proposal:
    reqs = db.scalars(select(Requirement).where(Requirement.session_id == session.id,
                                                Requirement.status == "approved").order_by(Requirement.code)).all()
    if not reqs:
        raise AppError("Approved requirements are required", code="no_approved_requirements")
    est = estimate_proposal(db, session.organisation_id, reqs)
    org = db.get(Organisation, session.organisation_id)
    outcome = AgentRunner(db, session.organisation_id, provider=provider).run(PROPOSAL_AGENT, ProposalAgentIn(
        organisation=org.name, problem=str(session.answers.get("business_problem") or session.title),
        architecture_overview=architecture.content.get("overview", ""),
        components=[c["name"] for c in architecture.content.get("components", [])],
        requirements=[{"code": r.code, "title": r.title, "priority": r.priority,
                       "acceptance_criteria": r.acceptance_criteria} for r in reqs],
        milestones=est["milestones"], team=est["team"], costs=est["costs"], total=est["total"],
        currency=est["currency"], timeline_weeks=est["timeline_weeks"],
    ))
    content = {**outcome.output.model_dump(), "milestones": est["milestones"], "team": est["team"],
               "costs": est["costs"], "total": est["total"], "currency": est["currency"],
               "timeline_weeks": est["timeline_weeks"], "estimate_basis": est["basis"], "estimate_label": est["label"],
               "requirement_codes": [r.code for r in reqs], "provenance": provenance("proposal_agent", outcome)}
    p = Proposal(organisation_id=session.organisation_id, session_id=session.id, architecture_id=architecture.id,
                 title=f"{org.name} — {session.title}"[:200], status="draft",
                 current_version=1, total_estimate=Decimal(est["total"]), currency=est["currency"], created_by=actor_id)
    db.add(p)
    db.flush()
    db.add(ProposalVersion(proposal_id=p.id, version=1, content=content, source="ai",
                           generated_model=f"{outcome.provider}:{outcome.model}", change_note="Generated draft",
                           author_id=actor_id))
    advance_lead(db, session.organisation_id, "proposal", actor_id, "proposal drafted")
    db.flush()
    return p


def current_content(db: Session, p: Proposal) -> dict:
    v = db.scalar(select(ProposalVersion).where(ProposalVersion.proposal_id == p.id,
                                                ProposalVersion.version == p.current_version))
    return v.content if v else {}


def edit_proposal(db: Session, p: Proposal, content: dict, note: str, actor_id: uuid.UUID) -> ProposalVersion:
    if p.status not in ("draft", "rejected"):
        raise InvalidTransition("Only draft or rejected proposals can be edited; move it back to draft first")
    merged = {**current_content(db, p), **content}
    merged["total"] = sum(float(c["amount"]) for c in merged.get("costs", []))
    p.current_version += 1
    p.total_estimate = Decimal(str(merged["total"]))
    if p.status == "rejected":
        p.status = "draft"
    v = ProposalVersion(proposal_id=p.id, version=p.current_version, content=merged, source="manual",
                        change_note=note or "Edited", author_id=actor_id)
    db.add(v)
    db.flush()
    return v


def transition_proposal(db: Session, p: Proposal, target: str, actor_id: uuid.UUID, comment: str | None = None) -> Proposal:
    check_transition(PROPOSAL_FLOW, p.status, target, "proposal")
    now = datetime.now(UTC)
    p.status = target
    if target == "approved":
        p.reviewed_by, p.reviewed_at = actor_id, now
    elif target == "sent":
        p.sent_at = now
        notify(db, p.organisation_id, "proposal.sent", f"Proposal ready for review: {p.title}",
               "A proposal is awaiting your decision in the DeployMind portal.", link=f"/portal/proposals/{p.id}")
    elif target in ("accepted", "rejected"):
        p.decided_by, p.decided_at, p.decision_comment = actor_id, now, comment
    record_activity(db, p.organisation_id, "proposal", p.id, "status_change", f"Proposal {target}", actor_id,
                    {"comment": comment}, customer_visible=target in ("sent", "accepted", "rejected"))
    db.flush()
    return p


def create_project_from_proposal(db: Session, p: Proposal, actor_id: uuid.UUID | None) -> Project:
    if p.status != "accepted":
        raise InvalidTransition("Projects can only be created from accepted proposals")
    existing = db.scalar(select(Project).where(Project.proposal_id == p.id))
    if existing:
        return existing
    content = current_content(db, p)
    start = date.today()
    weeks = int(content.get("timeline_weeks") or 8)
    session = db.get(DiscoverySession, p.session_id) if p.session_id else None
    project = Project(organisation_id=p.organisation_id, proposal_id=p.id,
                      name=(session.title if session else p.title)[:200],
                      description=content.get("proposed_solution", ""), stage="discovery", status="active",
                      owner_id=session.owner_id if session else actor_id, start_date=start,
                      target_date=start + timedelta(weeks=weeks))
    db.add(project)
    db.flush()
    for pos, m in enumerate(content.get("milestones", [])):
        due = start + timedelta(weeks=int(m["start_week"]) - 1 + int(m["weeks"]))
        ms = Milestone(organisation_id=p.organisation_id, project_id=project.id, title=m["title"], due_date=due,
                       position=pos, description=f"Stage: {m.get('stage', '')}")
        db.add(ms)
        db.flush()
        for tpos, t in enumerate(_default_tasks(m.get("stage", ""))):
            db.add(Task(organisation_id=p.organisation_id, project_id=project.id, milestone_id=ms.id, title=t,
                        status="todo", position=tpos, due_date=due, customer_visible=tpos == 0))
    for model in (Requirement,):
        for r in db.scalars(select(model).where(model.session_id == p.session_id)).all():
            r.project_id = project.id
    if p.architecture_id:
        db.get(ArchitectureDocument, p.architecture_id).project_id = project.id
    for integ in db.scalars(select(Integration).where(Integration.organisation_id == p.organisation_id,
                                                      Integration.project_id.is_(None))).all():
        integ.project_id = project.id
    advance_lead(db, p.organisation_id, "implementation", actor_id, "proposal accepted, project created")
    record_activity(db, p.organisation_id, "project", project.id, "system", "Project created from accepted proposal",
                    actor_id, {"proposal_id": str(p.id)}, customer_visible=True)
    notify(db, p.organisation_id, "project.created", f"Project started: {project.name}",
           "Your project has been created. Track progress in the portal.", link=f"/portal/projects/{project.id}")
    db.flush()
    return project


def _default_tasks(stage: str) -> list[str]:
    return {
        "solution_design": ["Confirm architecture with customer stakeholders", "Finalise data access and security plan"],
        "development": ["Implement document ingestion pipeline", "Implement grounded assistant API",
                        "Build assistant user interface"],
        "integration": ["Connect document repository", "Connect CRM and ticketing systems"],
        "testing": ["Build evaluation dataset", "Run security and tenant-isolation tests", "User acceptance testing"],
        "deployment": ["Deploy to staging", "Production release with approval", "Hypercare and handover"],
    }.get(stage, ["Plan work"])
