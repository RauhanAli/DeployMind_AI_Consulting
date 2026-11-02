# Contributing

## Setup
`make setup && make infra && make demo-reset`. See the README for running the stack.

## Workflow
1. Branch from `main` (`feature/…`, `fix/…`).
2. Keep changes focused; update docs when behaviour changes.
3. `make lint test` must pass locally; CI runs the same checks plus security scans, image builds and Playwright.
4. Open a pull request describing the change, the risk and how it was tested.

## Backend conventions
* **Layering:** routers (HTTP, auth, audit) → services (transactions, orchestration) → domain (pure logic). Domain
  code has no I/O.
* **Tenancy:** never query a tenant-owned model without `get_scoped` or `principal.scope_filter`. Add the
  endpoint to `tests/test_tenant_isolation.py`.
* **Permissions:** add new permissions to `app/core/rbac.py` (and to `CUSTOMER_FORBIDDEN` if internal-only).
  Check them in the API, not just the UI.
* **AI:** add agents with `AgentSpec` (typed I/O, deterministic mock builder, validation, explicit tools). Never let
  an agent produce numbers that drive decisions. Compute them deterministically and pass them in.
* **Migrations:** `alembic revision --autogenerate -m "…"`, review the file, then `alembic upgrade head` and
  `alembic check`. Note that `use_alter` foreign keys need manual `create_foreign_key` calls.
* **Background work:** enqueue with the helpers in `app/workers/tasks.py` (after-commit).
* **Errors:** raise `AppError` subclasses; never swallow exceptions silently.
* **Style:** ruff (`make lint`). mypy runs advisory in CI. Optional narrowing after scoped ORM lookups is the
  known source of findings; please don't add new categories.

## Frontend conventions
* App Router; data fetching with TanStack Query; forms with React Hook Form + Zod.
* Page files only export the default component (and `metadata`). Shared components live in `src/components`.
* Use `QueryView` for loading, error and empty states, and `errorMessage()` for API errors (shows the envelope's
  message and details).
* Recharts colours must be literal values (`CHART` in `components/domain/charts.tsx`). SVG presentation
  attributes don't resolve CSS variables.
* Effects must not return values other than cleanup functions (`scrollIntoView` returns a Promise in recent
  browsers).
* Strict TypeScript; `pnpm --filter @deploymind/web lint typecheck test` before pushing.

## Tests
* Backend tests use a real Postgres test database (`deploymind_test`), migrated with Alembic and truncated per
  test. Celery runs eagerly. Deployment adapters are faked via `register_adapter_override`.
* End-to-end tests expect a seeded, running stack. Run the API with `AUTH_RATE_LIMIT_PER_MINUTE=500`, because
  the suite signs in many times.

## Commit messages
Imperative mood, short subject, body explaining *why*.
