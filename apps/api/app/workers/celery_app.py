from celery import Celery

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

celery_app = Celery("deploymind", broker=settings.celery_broker_url, backend=settings.celery_result_backend,
                    include=["app.workers.tasks"])
celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=False,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=5,
    timezone="UTC",
    beat_schedule={
        "environment-health-checks": {"task": "deploymind.health_check_environments", "schedule": 300.0},
        "budget-alerts": {"task": "deploymind.check_budgets", "schedule": 900.0},
        "adapter-status": {"task": "deploymind.report_adapter_status", "schedule": 60.0},
    },
)
