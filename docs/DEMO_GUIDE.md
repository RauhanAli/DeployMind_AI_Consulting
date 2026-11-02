# Demo guide (≈15 minutes)

Prepare: `make demo-reset && make build-web && AUTH_RATE_LIMIT_PER_MINUTE=100 make start`, then open
http://localhost:3000. Password for every demo account: `DeployMind-demo-2026` (development only). The login page
has one-click buttons that fill in demo accounts.

The story: **Acme Professional Services** receives hundreds of enquiries and internal requests. Staff search
documents manually, classify requests and route them by hand. The demo follows Acme from first contact to a
monitored production assistant.

## 1. Public site and lead capture (2 min)
1. Home: value proposition, Assess → Build → Run, services, illustrative metrics (labelled), synthetic case studies.
2. **Book a discovery call**: submit the form (validated client- and server-side).
3. As `engineer@deploymind.example`: **Overview** shows "discovery call requests awaiting confirmation"; **CRM →
   Discovery calls** lists the booking.

## 2. Assess (3 min)
1. Open **Assessments → Acme**. Overall 54.3/100 *Developing*, radar, six dimension cards. Expand **How this was
   scored** on any card: every point traces to an answer × weight. The narrative is labelled an AI draft (mock).
2. Download the **PDF report**.
3. **Opportunities**: choose Acme, see the prioritisation matrix and the ranked list with reasoning and ROI
   *estimates* and their assumptions. As `admin@…`, change the weights and **Save & re-rank** to watch the order
   change deterministically.
4. Optional: register a brand-new organisation at `/register?next=assessment` and complete the wizard. Try
   answering "pilots" to *AI in production* to see a conditional follow-up appear.

## 3. Build (4 min)
1. **Discovery → Enquiry triage & knowledge assistant**: questionnaire, AI assistant tab (summary, gaps,
   follow-up questions, risks), requirements (AI-sourced, each approved by an engineer), stakeholders, actions.
2. **Solution Design**: Mermaid diagram rendered from editable source, components, API contracts, security,
   risk register, peer-review notes. Editing resets the review.
3. **Proposals**: deterministic cost table and timeline, version history, status *Accepted*. Try a new proposal:
   generate from the architecture page, then note that the engineer who generated it can't approve it (needs a PM).
4. **Projects**: Kanban board. Open a task, add a dependency, then try to complete the dependent task (blocked).
   Change the stage, add a milestone.

## 4. Deploy for real (3 min)
1. **AI Applications → Acme Enquiry Assistant → Playground**: ask *"Who approves expense claims above 500
   pounds?"* (cited answer, retrieval diagnostics), then *"What is the share price target for next year?"*
   (insufficient-evidence refusal).
2. **Environments & deploy → development → Deploy**. Open the deployment: the logs stream live while the image is
   built, unit tests run inside it, the container starts and health checks pass. Open the URL
   (`http://localhost:181xx`): the delivered assistant UI.
3. **production → Deploy** goes to *awaiting approval*. Sign in as `admin@…` (different person) and approve.
   Try **Rollback** on development.

## 5. Run (2 min)
1. **Monitoring**: default *Real telemetry* (your questions and the container's traffic). Switch to *Demo
   telemetry* (14 days, labelled synthetic) to see the incident spike on P95 latency.
2. **Evaluations**: dataset of 12 cases including refusal tests, three runs, select two and **compare**. Start a
   run with `min_relevance` 0.95 to trigger a **regression alert**.
3. **Incidents → INC-0001**: full timeline, root cause, resolution. Declare a new incident, run **AI analysis**
   (correlates telemetry and recent deployments), move it through the statuses with customer notifications.
4. **Cost Management**: spend by organisation, project, model and agent; budget at its threshold; configurable
   pricing.
5. **Audit Logs**: every action above, with actor, IP and request id.

## 6. Customer portal and isolation (1 min)
1. Sign in as `customer@acme-ps.example`: journey overview, report, proposal, project progress, the assistant
   (upload a document), support ticket SLAs, incident updates (public updates only, no AI analysis).
2. Copy a project URL, sign in as `customer@northwind-legal.example` and open it: **Could not load this data**
   (the API returns 404).

## Resetting
`make demo-reset` restores the seeded state. Containers started by real deployments are labelled
`deploymind.managed=true`. Remove them with `docker rm -f $(docker ps -aq --filter label=deploymind.managed=true)`.
