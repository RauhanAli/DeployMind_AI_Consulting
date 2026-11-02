"""Discovery Agent, Solution Architect Agent and Proposal Agent.

All outputs are drafts. Requirements are stored with status=draft and must be approved by an engineer;
architecture is stored as 'draft / unvalidated' until reviewed; proposals stay in draft until approved.
Commercial figures come from the deterministic estimator and the Proposal Agent may not change them.
"""

import json
import re

from pydantic import BaseModel, Field

from app.ai.agents.framework import AgentSpec, register

DISCOVERY_FIELDS = {
    "business_problem": "Business problem",
    "current_workflow": "Current workflow",
    "existing_systems": "Existing systems",
    "data_sources": "Data sources",
    "apis": "APIs",
    "user_roles": "User roles",
    "security_requirements": "Security requirements",
    "compliance_constraints": "Compliance constraints",
    "performance_expectations": "Performance expectations",
    "expected_outcomes": "Expected business outcomes",
    "budget": "Budget",
    "timeline": "Timeline",
    "acceptance_criteria": "Acceptance criteria",
}

FOLLOW_UPS = {
    "business_problem": "What specific problem costs the business most today, and how is it measured?",
    "current_workflow": "Can you walk through the current workflow step by step, including hand-offs?",
    "existing_systems": "Which systems are involved today and who owns each one?",
    "data_sources": "Where does the data needed for this workflow live, and how fresh is it?",
    "apis": "Do the systems in scope expose APIs? Are there rate limits or authentication constraints?",
    "user_roles": "Which user roles will use the solution and what may each role see or do?",
    "security_requirements": "What authentication, data residency and access-control requirements apply?",
    "compliance_constraints": "Which regulations or internal policies apply (e.g. GDPR, retention, audit)?",
    "performance_expectations": "What response time, availability and volume does the solution need to support?",
    "expected_outcomes": "Which measurable outcomes define success, and what are today's baselines?",
    "budget": "What budget range has been approved for this initiative?",
    "timeline": "Are there fixed dates or dependencies that constrain the timeline?",
    "acceptance_criteria": "How will the business decide the solution is ready to go live?",
}

INTEGRATION_NAMES = {"postgres": "PostgreSQL", "crm": "CRM", "ticketing": "Ticketing system",
                     "document_store": "Document repository", "rest_api": "Internal REST APIs", "webhook": "Event webhooks"}

INTEGRATION_KEYWORDS = [
    (r"postgres|mysql|sql server|database", "postgres", "Read structured operational data"),
    (r"\bcrm\b|salesforce|hubspot|dynamics", "crm", "Read customer and account context; write back outcomes"),
    (r"ticket|zendesk|jira|servicenow|freshdesk", "ticketing", "Create and route tickets"),
    (r"sharepoint|document|drive|confluence|repository", "document_store", "Ingest documents for retrieval"),
    (r"rest|api", "rest_api", "Call internal REST services"),
    (r"webhook|event", "webhook", "Receive events in real time"),
]


class DiscoveryAgentIn(BaseModel):
    organisation: str
    answers: dict[str, str]
    technical_notes: str = ""
    meeting_notes: str = ""
    stakeholders: list[dict] = []
    existing_requirements: list[str] = []


class TechnicalRisk(BaseModel):
    risk: str
    severity: str = Field(pattern="^(low|medium|high)$")
    mitigation: str


class SuggestedIntegration(BaseModel):
    name: str
    kind: str = Field(pattern="^(rest_api|webhook|postgres|crm|ticketing|document_store)$")
    purpose: str


class ProposedRequirement(BaseModel):
    title: str
    description: str
    category: str = Field(pattern="^(functional|non_functional|security|integration|data)$")
    priority: str = Field(pattern="^(must|should|could)$")
    acceptance_criteria: str


class DiscoveryAnalysis(BaseModel):
    summary: str
    missing_information: list[str]
    follow_up_questions: list[str]
    technical_risks: list[TechnicalRisk]
    suggested_integrations: list[SuggestedIntegration]
    proposed_requirements: list[ProposedRequirement]
    acceptance_criteria: list[str]


def _discovery_prompt(i: DiscoveryAgentIn, ctx: dict) -> str:
    return (
        "Analyse this discovery session for an enterprise AI implementation. Summarise it, list missing information, "
        "write follow-up questions, identify technical risks, suggest integrations, propose requirements and "
        "acceptance criteria. Only use facts present in the notes; flag assumptions explicitly.\n"
        f"Organisation: {i.organisation}\nQuestionnaire: {json.dumps(i.answers)}\n"
        f"Technical notes: {i.technical_notes}\nMeeting notes: {i.meeting_notes}\n"
        f"Stakeholders: {json.dumps(i.stakeholders)}\nAlready captured requirements: {json.dumps(i.existing_requirements)}\n"
        f"Known integration inventory: {json.dumps(ctx.get('org_integrations', []))}\n"
        f"Latest readiness assessment: {json.dumps(ctx.get('latest_assessment'))}"
    )


def _lines(text: str) -> list[str]:
    return [re.sub(r"^[\-\*\d\.\)\s]+", "", ln).strip() for ln in re.split(r"[\n;]", text or "") if ln.strip()]


def _discovery_mock(i: DiscoveryAgentIn, ctx: dict) -> DiscoveryAnalysis:
    a = {k: (i.answers.get(k) or "").strip() for k in DISCOVERY_FIELDS}
    missing = [DISCOVERY_FIELDS[k] for k, v in a.items() if not v]
    follow = [FOLLOW_UPS[k] for k, v in a.items() if not v or len(v) < 25][:8]
    corpus = " ".join([a["existing_systems"], a["data_sources"], a["apis"], i.technical_notes]).lower()

    integrations, seen = [], set()
    for pattern, kind, purpose in INTEGRATION_KEYWORDS:
        if re.search(pattern, corpus) and kind not in seen:
            seen.add(kind)
            integrations.append(SuggestedIntegration(name=INTEGRATION_NAMES[kind], kind=kind, purpose=purpose))

    risks = []
    comp = (a["compliance_constraints"] + " " + a["security_requirements"]).lower()
    if any(w in comp for w in ("gdpr", "personal", "pii", "confidential")):
        risks.append(TechnicalRisk(risk="Personal or confidential data will be processed by AI components",
                                   severity="high", mitigation="Document-level access control, PII redaction in logs, "
                                   "DPIA before go-live, provider data-retention controls"))
    if len(integrations) >= 3:
        risks.append(TechnicalRisk(risk=f"{len(integrations)} system integrations increase delivery and failure surface",
                                   severity="medium", mitigation="Adapter per system with contract tests, retries and "
                                   "health checks; phase integrations by value"))
    if "spreadsheet" in corpus or "manual" in a["current_workflow"].lower():
        risks.append(TechnicalRisk(risk="Source data quality and consistency is unproven",
                                   severity="medium", mitigation="Data profiling sprint and evaluation dataset built from "
                                   "real examples"))
    risks.append(TechnicalRisk(risk="LLM answers may be incorrect or ungrounded",
                               severity="high", mitigation="Grounded mode with citations, refusal on insufficient "
                               "evidence, offline evaluation gates in CI"))

    reqs: list[ProposedRequirement] = []
    if a["business_problem"]:
        reqs.append(ProposedRequirement(title="Answer staff questions from internal documents with citations",
                                        description=f"Addresses: {a['business_problem'][:300]}", category="functional",
                                        priority="must", acceptance_criteria="90% of evaluation questions answered "
                                        "correctly with at least one valid citation"))
    if "classif" in (a["business_problem"] + a["current_workflow"]).lower() or "rout" in a["current_workflow"].lower():
        reqs.append(ProposedRequirement(title="Classify and route incoming requests to the correct team",
                                        description="Automatic categorisation with confidence score and human override",
                                        category="functional", priority="must",
                                        acceptance_criteria="Routing accuracy >= 85% on a labelled sample of 200 requests"))
    if a["user_roles"]:
        reqs.append(ProposedRequirement(title="Role-based access control for all users",
                                        description=f"Roles: {a['user_roles'][:200]}", category="security",
                                        priority="must", acceptance_criteria="Users only retrieve documents permitted "
                                        "for their role; verified by automated tests"))
    for line in _lines(a["security_requirements"])[:3]:
        reqs.append(ProposedRequirement(title=line[:120], description=line, category="security", priority="must",
                                        acceptance_criteria="Verified in security review before production"))
    if a["performance_expectations"]:
        reqs.append(ProposedRequirement(title="Meet response-time and availability targets",
                                        description=a["performance_expectations"][:300], category="non_functional",
                                        priority="should", acceptance_criteria="P95 latency and availability targets "
                                        "met in staging load test"))
    for s in integrations:
        reqs.append(ProposedRequirement(title=f"Integrate with {s.name}", description=s.purpose,
                                        category="integration", priority="should",
                                        acceptance_criteria=f"{s.name} connector passes connection test and sync with "
                                        "retries and error logging"))
    reqs.append(ProposedRequirement(title="Audit log of AI-assisted actions", description="Record who asked what, "
                                    "which sources were used and which actions were taken", category="security",
                                    priority="must", acceptance_criteria="Every assistant answer is traceable to user, "
                                    "sources and model version"))
    existing = {r.lower() for r in i.existing_requirements}
    reqs = [r for r in reqs if r.title.lower() not in existing]

    acceptance = _lines(a["acceptance_criteria"]) or [
        "Evaluation suite passes agreed thresholds", "Security review signed off", "Pilot users trained"]
    summary = (f"{i.organisation} needs help with: {a['business_problem'] or 'problem not yet captured'}. "
               f"Today: {a['current_workflow'] or 'workflow not captured'}. Systems in scope: "
               f"{a['existing_systems'] or 'not captured'}. Desired outcomes: {a['expected_outcomes'] or 'not captured'}.")
    return DiscoveryAnalysis(summary=summary, missing_information=missing, follow_up_questions=follow,
                             technical_risks=risks, suggested_integrations=integrations, proposed_requirements=reqs,
                             acceptance_criteria=acceptance)


DISCOVERY_AGENT = register(AgentSpec(
    name="discovery_agent",
    responsibility="Summarise discovery, find gaps, propose requirements, risks and integrations (drafts only)",
    input_schema=DiscoveryAgentIn, output_schema=DiscoveryAnalysis,
    system_prompt=("You are a senior forward deployed engineer running technical discovery. Be specific and "
                   "factual; never invent customer facts. Everything you produce is a draft for engineer review."),
    build_prompt=_discovery_prompt, mock=_discovery_mock,
    tools=["org_integrations", "latest_assessment"],
    plan_tools=lambda _i: [("org_integrations", {}), ("latest_assessment", {})],
))


# ------------------------------------------------------------------ Solution Architect Agent
class ArchitectAgentIn(BaseModel):
    organisation: str
    problem: str
    requirements: list[dict]
    integrations: list[dict]
    constraints: dict[str, str] = {}


class Component(BaseModel):
    name: str
    responsibility: str
    technology: str


class TechChoice(BaseModel):
    area: str
    choice: str
    rationale: str


class Entity(BaseModel):
    entity: str
    fields: list[str]
    notes: str = ""


class ApiContract(BaseModel):
    method: str
    path: str
    purpose: str
    request: str = ""
    response: str = ""


class IntegrationStep(BaseModel):
    system: str
    method: str
    notes: str


class RiskItem(BaseModel):
    risk: str
    likelihood: str
    impact: str
    mitigation: str


class ArchitectureContent(BaseModel):
    overview: str
    description: str
    components: list[Component]
    technology_recommendations: list[TechChoice]
    database_design: list[Entity]
    api_contracts: list[ApiContract]
    integration_plan: list[IntegrationStep]
    security_design: list[str]
    data_flow: list[str]
    deployment_strategy: str
    risk_register: list[RiskItem]
    mermaid: str = Field(description="Mermaid flowchart (graph LR) of the components and integrations")


def _arch_prompt(i: ArchitectAgentIn, _ctx: dict) -> str:
    return (
        "Design a production architecture for this enterprise AI solution. Cover components, technology choices "
        "with rationale, database design, API contracts, integration plan, security, data flow, deployment strategy, "
        "and a risk register. Provide a valid Mermaid 'graph LR' diagram without styling directives.\n"
        f"Organisation: {i.organisation}\nProblem: {i.problem}\nApproved requirements: {json.dumps(i.requirements)}\n"
        f"Integrations: {json.dumps(i.integrations)}\nConstraints: {json.dumps(i.constraints)}"
    )


def _safe_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", name.title()) or "Node"


def _arch_mock(i: ArchitectAgentIn, _ctx: dict) -> ArchitectureContent:
    kinds = {x.get("kind") for x in i.integrations}
    comps = [
        Component(name="Web App", responsibility="Staff-facing assistant UI and request inbox", technology="Next.js"),
        Component(name="API Service", responsibility="AuthN/Z, tenancy, orchestration, audit logging",
                  technology="FastAPI (Python)"),
        Component(name="Retrieval Service", responsibility="Hybrid vector + keyword retrieval with ACL filtering",
                  technology="PostgreSQL + pgvector"),
        Component(name="LLM Gateway", responsibility="Provider abstraction, prompt versions, token & cost tracking",
                  technology="OpenAI / Anthropic via adapter"),
        Component(name="Ingestion Worker", responsibility="Parse, chunk, embed documents; scheduled syncs",
                  technology="Celery + Redis"),
        Component(name="Observability", responsibility="Metrics, traces, evaluation and alerting",
                  technology="OpenTelemetry + Prometheus"),
    ]
    if "ticketing" in kinds or any("rout" in (r.get("title", "") or "").lower() for r in i.requirements):
        comps.append(Component(name="Request Router", responsibility="Classify requests and route to team queues",
                               technology="Python service with rules + LLM classifier"))
    integ_nodes = [x.get("name", x.get("kind", "System")) for x in i.integrations]
    m = ["graph LR", "  U[Staff users] --> W[Web App]", "  W --> A[API Service]", "  A --> R[Retrieval Service]",
         "  A --> L[LLM Gateway]", "  R --> V[(PostgreSQL + pgvector)]", "  Q[Ingestion Worker] --> V",
         "  A --> O[Observability]"]
    if any(c.name == "Request Router" for c in comps):
        m.append("  A --> RR[Request Router]")
    for n in integ_nodes:
        sid = _safe_id(n)
        m.append(f"  Q --> {sid}[{n}]" if any(k in n.lower() for k in ("doc", "repository", "drive")) else f"  A --> {sid}[{n}]")
    reqs_must = [r["title"] for r in i.requirements if r.get("priority") == "must"]
    return ArchitectureContent(
        overview=f"Grounded AI assistant and request-routing platform for {i.organisation}.",
        description=(f"The solution addresses: {i.problem[:400]}. Users interact through a web app backed by an API "
                     "service that enforces tenancy and role-based access. Questions are answered by retrieving "
                     "permitted document chunks with hybrid search and generating grounded answers with citations. "
                     f"Must-have requirements covered: {', '.join(reqs_must[:6]) or 'n/a'}."),
        components=comps,
        technology_recommendations=[
            TechChoice(area="Vector store", choice="pgvector in existing PostgreSQL",
                       rationale="Reuses operational database skills, transactional ACL joins, no new vendor"),
            TechChoice(area="LLM provider", choice="Provider-agnostic gateway (OpenAI or Anthropic)",
                       rationale="Avoids lock-in; enables model comparison through evaluation runs"),
            TechChoice(area="Background jobs", choice="Celery + Redis",
                       rationale="Reliable retries for ingestion and integration syncs"),
            TechChoice(area="Hosting", choice="Containers on AWS ECS Fargate",
                       rationale="Managed runtime, per-environment isolation, simple rollbacks"),
        ],
        database_design=[
            Entity(entity="documents", fields=["id", "org_id", "title", "visibility", "sha256", "status"],
                   notes="Visibility drives retrieval ACL"),
            Entity(entity="document_chunks", fields=["id", "document_id", "content", "embedding vector", "tsv"],
                   notes="HNSW cosine index + GIN full-text index"),
            Entity(entity="requests", fields=["id", "channel", "category", "confidence", "routed_team", "status"]),
            Entity(entity="audit_logs", fields=["id", "actor", "action", "resource", "created_at"]),
        ],
        api_contracts=[
            ApiContract(method="POST", path="/v1/assistant/ask", purpose="Grounded question answering",
                        request="{question, conversation_id?}", response="{answer, citations[], insufficient_evidence}"),
            ApiContract(method="POST", path="/v1/documents", purpose="Upload document for ingestion",
                        request="multipart file + visibility", response="{id, status}"),
            ApiContract(method="POST", path="/v1/requests/classify", purpose="Classify and route a request",
                        request="{text, channel}", response="{category, team, confidence}"),
        ],
        integration_plan=[IntegrationStep(system=x.get("name", "System"), method=x.get("kind", "rest_api"),
                                          notes="Adapter with credential vault, retries (3x exponential) and health check")
                          for x in i.integrations] or [IntegrationStep(system="Document repository", method="document_store",
                                                                       notes="Scheduled sync")],
        security_design=["SSO/JWT authentication with short-lived access tokens and rotating refresh tokens",
                         "RBAC enforced in the API layer; document-level ACL applied inside retrieval SQL",
                         "Credentials encrypted at rest (Fernet / secrets manager); never returned by APIs",
                         "Audit log for every AI answer and administrative action",
                         "Prompt-injection mitigation: retrieved content treated as data; grounded-only mode"],
        data_flow=["Documents synced from repository -> parsed -> chunked -> embedded -> stored with ACL metadata",
                   "User question -> authZ -> hybrid retrieval over permitted chunks -> LLM -> answer with citations",
                   "Telemetry (latency, tokens, cost, retrieval scores) -> monitoring and evaluation"],
        deployment_strategy=("Docker images built in CI, promoted dev -> staging -> production with manual approval "
                             "before production, health-checked releases and one-click rollback to the previous image."),
        risk_register=[RiskItem(risk="Ungrounded or incorrect answers", likelihood="medium", impact="high",
                                mitigation="Grounded mode, citations, evaluation gates"),
                       RiskItem(risk="Integration API changes", likelihood="medium", impact="medium",
                                mitigation="Contract tests and connector health monitoring"),
                       RiskItem(risk="Cost overrun from token usage", likelihood="low", impact="medium",
                                mitigation="Budgets with alerts, model tiering")],
        mermaid="\n".join(m),
    )


def _arch_validate(_i: ArchitectAgentIn, o: ArchitectureContent) -> list[str]:
    errors = []
    if not o.mermaid.strip().startswith(("graph", "flowchart")):
        errors.append("mermaid must start with 'graph' or 'flowchart'")
    if len(o.components) < 3:
        errors.append("at least three components are required")
    return errors


ARCHITECT_AGENT = register(AgentSpec(
    name="solution_architect_agent",
    responsibility="Draft a solution architecture from approved requirements (unvalidated until reviewed)",
    input_schema=ArchitectAgentIn, output_schema=ArchitectureContent,
    system_prompt=("You are a principal solutions architect. Prefer simple, proven components that fit the "
                   "customer's existing systems. State trade-offs. Your design is a draft that engineers must review."),
    build_prompt=_arch_prompt, mock=_arch_mock, validate=_arch_validate, max_tokens=4000,
))


# ------------------------------------------------------------------ Proposal Agent
class ProposalAgentIn(BaseModel):
    organisation: str
    problem: str
    architecture_overview: str
    components: list[str]
    requirements: list[dict]
    milestones: list[dict]
    team: list[dict]
    costs: list[dict]
    total: float
    currency: str
    timeline_weeks: int


class ProposalNarrative(BaseModel):
    executive_summary: str
    business_problem: str
    proposed_solution: str
    technical_architecture: str
    deliverables: list[str]
    risks_and_assumptions: list[str]
    acceptance_criteria: list[str]
    support_agreement: str


def _proposal_prompt(i: ProposalAgentIn, _ctx: dict) -> str:
    return (
        "Write the narrative sections of a commercial and technical proposal. Milestones, team, costs and total were "
        "calculated by a deterministic estimator: reference them but do not change any figure.\n"
        f"{json.dumps(i.model_dump())}"
    )


def _proposal_mock(i: ProposalAgentIn, _ctx: dict) -> ProposalNarrative:
    musts = [r["title"] for r in i.requirements if r.get("priority") == "must"]
    return ProposalNarrative(
        executive_summary=(f"DeployMind proposes to design, build and operate a production AI solution for "
                           f"{i.organisation} over {i.timeline_weeks} weeks. The solution targets the problem below and "
                           f"is delivered in {len(i.milestones)} milestones with evaluation gates. The estimated "
                           f"investment is {i.currency} {i.total:,.0f} (estimate, subject to the assumptions listed)."),
        business_problem=i.problem,
        proposed_solution=(f"{i.architecture_overview} It comprises {', '.join(i.components[:6])}, integrated with the "
                           "customer's existing systems and operated with monitoring, evaluation and incident response."),
        technical_architecture=("See the attached solution architecture document. Key principles: grounded answers "
                                "with citations, role-based and document-level access control, provider-agnostic LLM "
                                "gateway, containerised deployment with staged promotion and rollback."),
        deliverables=[*[f"Implemented requirement: {m}" for m in musts[:6]],
                      "Production deployment with monitoring dashboards", "Evaluation suite and regression gates",
                      "Runbooks, handover documentation and training"],
        risks_and_assumptions=["Customer provides timely access to systems, data and stakeholders",
                               "Source documents are representative and permitted for AI processing",
                               "Third-party API rate limits allow the expected volume",
                               "Costs are estimates; changes in scope are handled through change control",
                               "Model provider usage costs are billed separately at actual usage"],
        acceptance_criteria=[r.get("acceptance_criteria") or r["title"] for r in i.requirements if r.get("priority") == "must"][:8]
        or ["All must-have requirements demonstrated in staging"],
        support_agreement=("Includes 3 months of post-go-live support: P1 response within 1 hour, P2 within 4 hours, "
                           "monthly evaluation and cost reviews, and incident post-mortems."),
    )


PROPOSAL_AGENT = register(AgentSpec(
    name="proposal_agent",
    responsibility="Write proposal narrative around deterministic milestones, team and cost estimates",
    input_schema=ProposalAgentIn, output_schema=ProposalNarrative,
    system_prompt=("You write clear, professional consulting proposals. Never alter commercial figures, never "
                   "guarantee outcomes, and keep claims verifiable."),
    build_prompt=_proposal_prompt, mock=_proposal_mock, max_tokens=3500,
))
