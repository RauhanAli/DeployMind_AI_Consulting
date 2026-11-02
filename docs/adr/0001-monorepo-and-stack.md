# ADR 0001: Monorepo with FastAPI, Next.js and PostgreSQL

* Status: accepted
* Date: 2026-10-30

## Context
The platform spans a public site, two authenticated UIs, an API with substantial domain logic, background jobs,
and a deliverable microservice. One engineer (or a small FDE team) must be able to change a feature end to end.

## Decision
* One repository: `apps/api`, `apps/web`, `apps/worker`, `apps/assistant-service`, `packages/shared`, `infrastructure`.
* **Python / FastAPI** for the API and worker. It has the best ecosystem for LLM, RAG and data work, Pydantic
  gives typed I/O for agents, and the worker reuses the API package instead of duplicating domain code.
* **Next.js App Router + TypeScript** for all UIs, deployed as one app with route groups. It proxies `/api/v1`
  same-origin so the refresh token can be an httpOnly cookie without cross-site cookie configuration.
* **PostgreSQL 16 + pgvector** as the single system of record, including vectors (ADR 0003).
* **Celery + Redis** for background work, because retries, scheduling (beat) and operational familiarity matter
  more than novelty.

## Consequences
* Two languages. Shared domain constants live in `packages/shared`, and the backend stays authoritative.
* pnpm workspace for JS and a venv for Python. `Makefile` and `scripts/` hide the difference.
