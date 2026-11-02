/* Marketing content for the public site. All examples and metrics are illustrative and labelled as such. */

export type Service = {
  slug: string;
  name: string;
  short: string;
  headline: string;
  intro: string;
  icon: string;
  outcomes: string[];
  deliverables: string[];
  approach: { title: string; body: string }[];
  fit: string[];
  cta: { label: string; href: string };
};

export const SERVICES: Service[] = [
  {
    slug: "ai-readiness", name: "AI Readiness Assessment", icon: "Gauge",
    short: "A scored, explainable view of where you are and what to build first.",
    headline: "Know exactly where you stand before you invest",
    intro: "A structured assessment across strategy, data, process, technology, governance and people. Scores are computed by a transparent weighted model, so every number can be traced back to an answer.",
    outcomes: ["Overall readiness score and classification", "Six dimension scores with evidence", "Risks surfaced from your answers", "A recommended first project and 30/60/90-day plan"],
    deliverables: ["Interactive results dashboard", "Downloadable PDF report", "Prioritised opportunity matrix", "3/6/12-month roadmap"],
    approach: [
      { title: "Answer 29 focused questions", body: "Conditional questions adapt to your situation. Save and resume at any time." },
      { title: "Deterministic scoring", body: "Weighted scores are calculated server-side. AI writes the explanation, never the score." },
      { title: "Prioritised opportunities", body: "Use cases ranked by impact, data availability, integration effort and risk." },
    ],
    fit: ["Leadership teams deciding where AI fits", "Organisations with scattered AI pilots", "Teams preparing an AI business case"],
    cta: { label: "Start the assessment", href: "/register?next=assessment" },
  },
  {
    slug: "ai-strategy", name: "AI Strategy Consulting", icon: "Compass",
    short: "Turn AI ambition into a funded, sequenced portfolio.",
    headline: "An AI strategy your engineers can actually build",
    intro: "We connect business objectives to concrete, feasible use cases, then sequence them by value and dependency so the first delivery proves the model for the rest.",
    outcomes: ["Agreed AI ambition and success metrics", "Ranked use-case portfolio", "Governance and operating model", "Investment case with explicit assumptions"],
    deliverables: ["Use-case portfolio and scoring model", "Target architecture principles", "Governance framework and policies", "Board-ready roadmap"],
    approach: [
      { title: "Discover", body: "Stakeholder interviews, process walkthroughs and a data landscape review." },
      { title: "Prioritise", body: "A configurable scoring model makes trade-offs explicit and repeatable." },
      { title: "Plan", body: "Sequenced roadmap with owners, budgets and evaluation gates." },
    ],
    fit: ["Executive teams setting AI direction", "Transformation and innovation leads", "Boards seeking assurance on AI plans"],
    cta: { label: "Book a strategy call", href: "/book-discovery-call?topic=AI%20strategy" },
  },
  {
    slug: "custom-ai-development", name: "Custom AI Development", icon: "Code2",
    short: "Production-grade AI systems built around your data and workflows.",
    headline: "Custom AI systems, engineered for production",
    intro: "Forward deployed engineers embed with your team to build AI that integrates with your systems, respects your permissions and is measurable from day one.",
    outcomes: ["Working software in weeks, not quarters", "Provider-agnostic LLM architecture", "Evaluation suites and quality gates", "Clear ownership and handover"],
    deliverables: ["Source code in your repositories", "Infrastructure as code", "Evaluation datasets and dashboards", "Runbooks and documentation"],
    approach: [
      { title: "Technical discovery", body: "Requirements, integrations, security and acceptance criteria captured and approved." },
      { title: "Iterative build", body: "Weekly demos against an agreed evaluation set, not opinions." },
      { title: "Production hardening", body: "Access control, observability, cost controls and incident response." },
    ],
    fit: ["Teams with a validated use case", "Organisations replacing brittle prototypes", "Regulated environments needing auditability"],
    cta: { label: "Discuss your build", href: "/book-discovery-call?topic=Custom%20AI%20development" },
  },
  {
    slug: "ai-automation", name: "AI Workflow Automation", icon: "Workflow",
    short: "Classify, route and action requests with humans in control.",
    headline: "Automate the busywork, keep people in the loop",
    intro: "From inbox triage to document extraction, we automate high-volume workflows with confidence thresholds, human review queues and full audit trails.",
    outcomes: ["Faster, consistent request handling", "Measured automation rate", "Exceptions routed to people", "Complete audit history"],
    deliverables: ["Classification and routing services", "Review queues and dashboards", "Integration adapters", "SLA and quality monitoring"],
    approach: [
      { title: "Baseline", body: "Measure today's volumes, cycle times and error rates." },
      { title: "Automate safely", body: "Confidence thresholds decide what is automated and what is reviewed." },
      { title: "Improve", body: "Feedback loops and evaluation runs drive accuracy up over time." },
    ],
    fit: ["Operations teams with high request volumes", "Service desks and shared services", "Back-office document processing"],
    cta: { label: "Explore automation", href: "/book-discovery-call?topic=Workflow%20automation" },
  },
  {
    slug: "knowledge-assistants", name: "Knowledge Assistants", icon: "BookOpenText",
    short: "Grounded answers from your documents, with citations and access control.",
    headline: "Answers your people can trust — with sources",
    intro: "Enterprise knowledge assistants that answer only from documents a user is allowed to see, cite every claim and say so when the evidence is not there.",
    outcomes: ["Less time searching for information", "Answers with verifiable citations", "Document-level access control", "Refusal when evidence is insufficient"],
    deliverables: ["Ingestion pipeline (PDF, DOCX, TXT)", "Hybrid semantic + keyword retrieval", "Assistant UI and API", "Evaluation and feedback analytics"],
    approach: [
      { title: "Curate", body: "Connect repositories, map permissions and define evaluation questions." },
      { title: "Ground", body: "Hybrid retrieval with permission filtering inside the database query." },
      { title: "Measure", body: "Faithfulness, citation quality and retrieval precision tracked per release." },
    ],
    fit: ["Policy-heavy organisations", "Client service and support teams", "Internal IT and HR help desks"],
    cta: { label: "See the demo assistant", href: "/login" },
  },
  {
    slug: "sales-revenue", name: "Sales & Revenue AI", icon: "TrendingUp",
    short: "Qualify leads, prepare proposals and surface account insight.",
    headline: "Give your revenue team back their selling time",
    intro: "Lead qualification, account research and proposal drafting that plug into your CRM — with expert review before anything reaches a customer.",
    outcomes: ["Faster response to inbound leads", "Consistent qualification", "Proposal drafts in minutes", "Insight from CRM history"],
    deliverables: ["Lead scoring and enrichment", "Proposal generation with review workflow", "CRM integration", "Pipeline analytics"],
    approach: [
      { title: "Connect", body: "Integrate CRM, templates and past proposals securely." },
      { title: "Assist", body: "AI drafts; your experts approve. Nothing is sent automatically." },
      { title: "Track", body: "Win-rate and cycle-time metrics against a clear baseline." },
    ],
    fit: ["B2B sales teams", "Professional services firms", "Bid and proposal teams"],
    cta: { label: "Talk to us", href: "/book-discovery-call?topic=Sales%20and%20revenue" },
  },
  {
    slug: "prototype-to-production", name: "Prototype to Production", icon: "Rocket",
    short: "Take a promising AI prototype and make it reliable, secure and observable.",
    headline: "Your prototype works. Now make it production-ready.",
    intro: "We harden AI prototypes into operated systems: authentication, tenancy, evaluation gates, CI/CD, monitoring, cost controls and incident response.",
    outcomes: ["Security and access control in place", "Automated evaluation in CI", "Staged releases with approvals and rollback", "Live monitoring of quality, latency and cost"],
    deliverables: ["Production architecture and IaC", "CI/CD pipelines with approval gates", "Observability dashboards", "Operational runbooks"],
    approach: [
      { title: "Assess", body: "A production-readiness review of the prototype's architecture, data and risks." },
      { title: "Harden", body: "Security, testing, evaluation and deployment pipelines added incrementally." },
      { title: "Operate", body: "Monitoring, incident management and continuous evaluation after go-live." },
    ],
    fit: ["Teams stuck after a successful pilot", "Start-ups preparing for enterprise customers", "Internal AI teams lacking platform support"],
    cta: { label: "Review my prototype", href: "/book-discovery-call?topic=Prototype%20to%20production" },
  },
];

export const USE_CASES = [
  { title: "Client enquiry triage", industry: "Professional services", body: "Classify incoming enquiries, route them to the right team and draft responses for review." },
  { title: "Policy & procedure assistant", industry: "Any regulated industry", body: "Grounded answers over policies with citations and document-level permissions." },
  { title: "Contract data extraction", industry: "Legal", body: "Extract clauses, dates and obligations into structured records with a review queue." },
  { title: "IT service desk deflection", industry: "Enterprise IT", body: "Resolve common requests from knowledge articles before a ticket is raised." },
  { title: "Proposal drafting", industry: "Consulting", body: "Draft proposals from templates, past work and CRM context for expert approval." },
  { title: "Claims intake", industry: "Insurance", body: "Summarise claim documents, check completeness and flag risk indicators." },
  { title: "Sales lead qualification", industry: "B2B SaaS", body: "Score and enrich inbound leads, summarise context and route to the right rep." },
  { title: "Engineering knowledge search", industry: "Manufacturing", body: "Hybrid search across manuals, maintenance logs and specifications." },
];

export const CASE_STUDIES = [
  {
    slug: "accountancy-enquiries", client: "Mid-size accountancy firm (synthetic example)", title: "Grounded enquiry assistant for client services",
    challenge: "Client service agents searched shared folders for policy answers and triaged ~600 enquiries a week by hand.",
    solution: "A knowledge assistant over policies and procedures with citations, plus automated routing suggestions integrated with the CRM.",
    results: [["40%", "less time spent searching (illustrative)"], ["< 5s", "P95 answer latency target"], ["100%", "answers traceable to sources"]],
  },
  {
    slug: "legal-contracts", client: "Regional law firm (synthetic example)", title: "Contract review accelerator",
    challenge: "Associates spent hours extracting key terms from inbound contracts.",
    solution: "Clause extraction with a human review queue and evaluation set built from 300 annotated contracts.",
    results: [["3x", "faster first-pass review (illustrative)"], ["92%", "field-level accuracy on eval set (illustrative)"], ["0", "auto-sent outputs: all reviewed"]],
  },
  {
    slug: "saas-support", client: "B2B software company (synthetic example)", title: "From prototype to production support copilot",
    challenge: "A promising support copilot prototype had no access control, monitoring or rollback.",
    solution: "Multi-tenant hardening, CI evaluation gates, staged deployments and cost budgets with alerts.",
    results: [["2", "environments with approval gates"], ["1-click", "rollback to previous release"], ["Daily", "evaluation runs in CI"]],
  },
];

export const ILLUSTRATIVE_METRICS = [
  { value: "6", label: "readiness dimensions, scored transparently" },
  { value: "8", label: "delivery stages from discovery to handover" },
  { value: "100%", label: "of assistant answers cite their sources" },
  { value: "3", label: "environments per application, with approval gates" },
];
