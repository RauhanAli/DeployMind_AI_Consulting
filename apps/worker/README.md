# Worker

The worker runs Celery tasks defined in `apps/api/app/workers/tasks.py` (it shares the API's domain and
infrastructure code rather than duplicating it):

| Task | Purpose |
| --- | --- |
| `deploymind.generate_assessment_report` | LLM narrative for a scored assessment |
| `deploymind.ingest_document` | Parse → chunk → embed → pgvector |
| `deploymind.run_evaluation` | Execute an evaluation run and detect regressions |
| `deploymind.run_deployment` | Build → test → release → health-check via a deployment adapter |
| `deploymind.sync_integration` | Integration sync with retry policy |
| `deploymind.health_check_environments` | Beat, every 5 min: probe live environments (uptime telemetry) |
| `deploymind.check_budgets` | Beat, every 15 min: budget threshold alerts |

Run locally: `cd apps/api && .venv/bin/celery -A app.workers.celery_app worker -B -l info`
