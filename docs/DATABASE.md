# Database

PostgreSQL 16 with the `vector` extension (pgvector). Schema managed by Alembic
(`apps/api/alembic/versions/20261030_0001_initial_schema.py`). CI checks that migrations apply, downgrade and
match the models (`alembic check`).

## Conventions

* **UUID primary keys** on every table (`UUIDPk` mixin), `created_at` / `updated_at` timestamps with time zone.
* **Tenant scoping:** tenant-owned tables use the `TenantScoped` mixin, which adds a non-null, indexed
  `organisation_id` FK with `ON DELETE CASCADE`. Every read filters on it (see [SECURITY](SECURITY.md)).
* Named constraints (`fk_*`, `uq_*`, `ix_*`) for stable migrations.
* JSONB for semi-structured, versioned payloads (assessment findings, architecture content, proposal versions,
  agent provenance). Relational columns for everything that is filtered, joined or constrained.
* Status columns are validated by deterministic state machines in `app/domain/workflow.py`.

## Entity relationships (core)

```mermaid
erDiagram
  organisations ||--o{ memberships : has
  users ||--o{ memberships : has
  roles ||--o{ memberships : grants
  roles }o--o{ permissions : role_permissions
  users ||--o{ refresh_tokens : owns

  organisations ||--o{ leads : ""
  organisations ||--o{ contacts : ""
  organisations ||--o{ activities : timeline
  organisations ||--o{ assessments : ""
  assessments ||--o{ assessment_answers : ""
  assessment_questions ||--o{ assessment_answers : ""
  assessments ||--o{ assessment_scores : ""
  assessments ||--o{ opportunities : generates

  organisations ||--o{ discovery_sessions : ""
  discovery_sessions ||--o{ stakeholders : ""
  discovery_sessions ||--o{ action_items : ""
  discovery_sessions ||--o{ requirements : ""
  discovery_sessions ||--o{ architecture_documents : ""
  architecture_documents ||--o{ proposals : basis
  proposals ||--o{ proposal_versions : versions
  proposals ||--o| projects : "accepted → creates"
  projects ||--o{ milestones : ""
  projects ||--o{ tasks : ""
  tasks }o--o{ tasks : task_dependencies
  tasks ||--o{ task_comments : ""

  organisations ||--o{ integrations : ""
  integrations ||--o{ integration_runs : history
  secrets ||--o| integrations : credential

  projects ||--o{ ai_applications : ""
  ai_applications ||--o{ documents : ""
  documents ||--o{ document_chunks : "embedding vector(384) + tsv"
  documents }o--o{ users : document_permissions
  ai_applications ||--o{ conversations : ""
  conversations ||--o{ messages : ""

  ai_applications ||--o{ environments : "dev / staging / prod"
  environments ||--o{ deployments : releases
  deployments ||--o{ deployment_logs : ""
  ai_applications ||--o{ telemetry_events : ""
  organisations ||--o{ model_usage : ""
  organisations ||--o{ budgets : ""

  ai_applications ||--o{ evaluation_datasets : ""
  evaluation_datasets ||--o{ evaluation_cases : ""
  evaluation_datasets ||--o{ evaluation_runs : ""
  evaluation_runs ||--o{ evaluation_results : ""

  organisations ||--o{ incidents : ""
  incidents ||--o{ incident_updates : timeline
  organisations ||--o{ support_tickets : ""
  support_tickets ||--o{ ticket_comments : ""
```

Platform-wide tables (no tenant): `users`, `roles`, `permissions`, `assessment_questions`, `model_pricing`,
`platform_settings`, `idempotency_keys`. `audit_logs` and `jobs` carry an optional `organisation_id`.

## Table inventory (57)

| Area | Tables |
| --- | --- |
| Identity & access | organisations, users, memberships, roles, permissions, role_permissions, refresh_tokens |
| Platform | audit_logs, notifications, idempotency_keys, jobs, secrets, platform_settings |
| CRM | contacts, leads, activities, discovery_calls |
| Assess | assessment_questions, assessments, assessment_answers, assessment_scores, opportunities |
| Build | discovery_sessions, stakeholders, action_items, requirements, integrations, integration_runs, architecture_documents, proposals, proposal_versions, projects, milestones, tasks, task_dependencies, task_comments |
| Knowledge | ai_applications, documents, document_permissions, document_chunks, conversations, messages |
| Deploy | environments, deployments, deployment_logs |
| Run | telemetry_events, model_usage, model_pricing, budgets, evaluation_datasets, evaluation_cases, evaluation_runs, evaluation_results, incidents, incident_updates, support_tickets, ticket_comments |

## Vector and text indexes

```sql
-- document_chunks
embedding vector(384) NOT NULL
tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX ix_document_chunks_tsv ON document_chunks USING gin (tsv);
```

`EMBEDDING_DIMENSIONS` (default 384) is baked into the column type; changing it needs a migration and
re-ingestion.

Time-series access paths have composite indexes, `(organisation_id, created_at)` on `telemetry_events` and
`model_usage`. Monitoring percentiles use `percentile_cont` over a time-bounded subquery.

## Demo data

`python -m app.seed.demo --reset` drops the schema, re-runs migrations and seeds one complete journey for
**Acme Professional Services**. It also seeds a second tenant (Northwind Legal), staff accounts for every role,
six knowledge documents plus one restricted document, real conversations and evaluation runs, and 14 days of
telemetry labelled `demo_seed`. The seed refuses to run when `APP_ENV=production`.
