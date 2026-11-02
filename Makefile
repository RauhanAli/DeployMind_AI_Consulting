.PHONY: setup infra demo-reset start stop test test-api test-web test-e2e lint migrate build-web images

API=apps/api
PY=$(API)/.venv/bin

setup: infra ## Install all dependencies
	cd $(API) && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	pnpm install

infra: ## Start Postgres (pgvector) and Redis
	docker compose up -d postgres redis

migrate:
	cd $(API) && .venv/bin/alembic upgrade head

demo-reset: ## DEVELOPMENT ONLY: wipe the database, migrate and seed the full demo journey
	cd $(API) && .venv/bin/python -m app.seed.demo --reset

build-web:
	pnpm build:web

start: ## Run API, worker and web in the background
	./scripts/dev-start.sh

stop:
	./scripts/dev-stop.sh

test: test-api test-web ## Backend + frontend unit/integration tests

test-api:
	cd $(API) && .venv/bin/pytest

test-web:
	pnpm test:web

test-e2e: ## Requires a seeded, running stack started with AUTH_RATE_LIMIT_PER_MINUTE=500
	pnpm test:e2e

lint:
	cd $(API) && .venv/bin/ruff check app tests
	pnpm --filter @deploymind/web lint
	pnpm --filter @deploymind/web typecheck

images:
	docker build -f apps/api/Dockerfile -t deploymind/api:dev apps
	docker build -f apps/worker/Dockerfile -t deploymind/worker:dev apps
	docker build -f apps/web/Dockerfile -t deploymind/web:dev .
	docker build -t deploymind/assistant:dev apps/assistant-service
