# API

* Base path: `/api/v1` (versioned). OpenAPI: `GET /api/v1/openapi.json`. Interactive docs: `/docs` and `/redoc`.
* 191 operations across 149 paths.
* Auth: `Authorization: Bearer <access_token>`; refresh via the httpOnly cookie (`POST /auth/refresh`). Non-browser
  clients may pass `?include_refresh=true` to receive the refresh token in the body.

## Conventions

| Concern | Convention |
| --- | --- |
| Errors | `{"error": {"code": "invalid_transition", "message": "...", "details": {...}, "request_id": "..."}}` with appropriate status (400 business rule, 401, 403 missing permission, 404 not found **or out of tenant scope**, 409 conflict / invalid transition, 415 unsupported file, 422 validation, 429 rate limited, 503 AI provider error) |
| Pagination | `?page=1&page_size=20` (max 100) → `{items, total, page, page_size}` |
| Filtering | resource-specific query params, e.g. `/crm/leads?status=new,qualified&q=acme&owner_id=...` |
| Sorting | allow-listed `?sort=-created_at` |
| Idempotency | `Idempotency-Key` header on `POST /assessments/{id}/submit`, `POST /proposals/{id}/decision`, `POST /environments/{id}/deploy` |
| Tracing | every response carries `X-Request-ID` (send your own to correlate) |
| Long-running work | returns immediately with a status field (`report_status`, document `status`, run `status`, deployment `status`) or a `Job` (`GET /jobs/{id}`); deployments also stream logs over SSE |

## Resource map

| Area | Endpoints (abridged) |
| --- | --- |
| Auth | `POST /auth/register` · `POST /auth/login` · `POST /auth/refresh` · `POST /auth/logout` · `GET /auth/me` |
| Public | `POST /public/discovery-calls` (book a call / contact) · `GET /public/meta` · `GET /assessments/questions` |
| Organisations | `GET /organisations` · `GET/PATCH /organisations/{id}` · `GET/POST /organisations/{id}/members` · `GET /organisations/{id}/journey` · `GET /users/staff` |
| CRM | `GET /crm/pipeline` · `GET/POST /crm/leads` · `GET/PATCH /crm/leads/{id}` · `POST /crm/leads/{id}/status` · `POST /crm/leads/{id}/notes` · `GET /crm/leads/{id}/activities` · contacts CRUD · `GET/PATCH /crm/discovery-calls` |
| Assessments | `POST /assessments` · `GET /assessments` · `GET /assessments/{id}` · `PUT /assessments/{id}/progress` · `POST /assessments/{id}/submit` · `GET /assessments/{id}/report` · `POST .../report/regenerate` · `GET .../report.pdf` |
| Opportunities | `GET /opportunities` · `GET/PATCH /opportunities/{id}` · `POST /organisations/{id}/opportunities/rerank` · `PUT /settings/opportunity_weights` |
| Discovery | sessions CRUD · `POST /discovery/sessions/{id}/analyze` · `.../import-requirements` · `.../complete` · `.../reopen` · stakeholders · action items · `GET /discovery/fields` |
| Requirements | `GET/POST /requirements` · `PATCH/DELETE /requirements/{id}` · `POST /requirements/{id}/decision` |
| Architecture | `POST /architecture/generate` · `GET /architecture` · `GET/PUT /architecture/{id}` · `POST /architecture/{id}/review` |
| Proposals | `POST /proposals/generate` · `GET /proposals` · `GET/PUT /proposals/{id}` · `GET /proposals/{id}/versions/{v}` · `POST /proposals/{id}/transition` · `POST /proposals/{id}/decision` (customer) · `GET /proposals/{id}/pdf` |
| Projects | `GET/POST /projects` · `GET/PATCH /projects/{id}` · `POST /projects/{id}/stage` · `GET /projects/{id}/timeline` · milestones CRUD · tasks CRUD · `POST/DELETE /tasks/{id}/dependencies` · task comments · `POST /tasks/{id}/attachments` · `GET /attachments/{id}/download` |
| AI applications | `GET /ai/providers` · `GET/POST /apps` · `GET/PATCH /apps/{id}` · `GET/POST /apps/{id}/documents` · `PATCH/DELETE /documents/{id}` · `POST /documents/{id}/reprocess` · `GET /documents/{id}/chunks` · `GET /documents/{id}/download` |
| RAG chat | `POST /apps/{id}/chat` · `GET /apps/{id}/conversations` · `GET /conversations/{id}/messages` · `POST /messages/{id}/feedback` · `GET /apps/{id}/feedback` |
| Integrations | `GET /integrations/kinds` · CRUD · `PUT /integrations/{id}/credentials` (write-only) · `POST .../test` · `POST .../sync` · `GET .../runs` · `POST .../webhook-secret` · `POST /webhooks/{id}` (HMAC) · `/mock-services/*` |
| Deployments | `GET /apps/{id}/environments` · `GET /environments` · `PATCH /environments/{id}` · `PUT/DELETE /environments/{id}/secrets` · `POST /environments/{id}/deploy` · `.../rollback` · `.../health-check` · `.../stop` · `GET /deployments` · `GET /deployments/{id}` · `POST .../approve` · `POST .../reject` · `GET .../logs` · `GET .../logs/stream` (SSE) · `GET /deployments/adapters` |
| Runtime (deployed containers) | `GET /runtime/health` · `POST /runtime/ask` (deployment token) |
| Monitoring | `GET /monitoring/overview?hours=&source=real\|demo\|all&app_id=` · `GET /monitoring/stream` (SSE) · `GET /metrics` (Prometheus) |
| Evaluations | datasets & cases CRUD · `POST /evaluations/runs` · `GET /evaluations/runs` · `GET /evaluations/runs/{id}` · `GET /evaluations/compare?run_ids=` |
| Incidents | `GET/POST /incidents` · `GET/PATCH /incidents/{id}` · `POST /incidents/{id}/status` · `GET/POST /incidents/{id}/updates` · `POST /incidents/{id}/analyze` · `GET /incidents/meta` |
| Support | `GET/POST /support/tickets` · `GET/PATCH /support/tickets/{id}` · `GET/POST /support/tickets/{id}/comments` · `GET /support/meta` |
| Costs | `GET /costs/summary` · `GET/POST /costs/budgets` · `POST /costs/budgets/check` · `GET/POST /costs/pricing` |
| Platform | `GET /dashboard/overview` · `GET /audit-logs` · `GET /settings` · `PUT /settings/{key}` · `GET /notifications` · `POST /notifications/{id}/read` · `GET /jobs/{id}` · `GET /agents` · `GET /health` |

## Example: grounded question

```http
POST /api/v1/apps/6aa5…/chat
Authorization: Bearer eyJ…
Content-Type: application/json

{"question": "Who approves expense claims above 500 pounds?"}
```

```json
{
  "conversation_id": "9123…",
  "message": {
    "role": "assistant",
    "content": "Claims above 500 pounds require approval from a director before reimbursement. [1]",
    "citations": [{"index": 1, "filename": "expenses-and-travel-policy.md", "title": "Expenses And Travel Policy",
                   "chunk_id": "…", "ordinal": 0, "snippet": "…", "relevance": 0.71}],
    "insufficient_evidence": false, "provider": "mock", "model": "mock-deterministic-1",
    "input_tokens": 212, "output_tokens": 21, "latency_ms": 38
  },
  "retrieval": [{"title": "Expenses And Travel Policy", "relevance": 0.71, "vector_similarity": 0.43, "keyword_rank": 0.2}],
  "is_mock": true
}
```

## Example: error envelope

```json
{"error": {"code": "invalid_transition", "message": "Proposal cannot move from 'draft' to 'sent'",
           "details": {"allowed": ["in_review"]}, "request_id": "3a68bf4b…"}}
```
