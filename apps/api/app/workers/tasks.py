"""Background jobs. Enqueue only after the surrounding transaction commits so workers never see stale rows."""

import logging
import uuid
from datetime import UTC, datetime

from celery.signals import worker_ready
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Document, Environment, Integration, Job
from app.workers.celery_app import celery_app

log = logging.getLogger("deploymind.worker")


def after_commit(db: Session, fn) -> None:
    event.listen(db, "after_commit", lambda _s: fn(), once=True)


def _session():
    return SessionLocal()


@celery_app.task(name="deploymind.generate_assessment_report", bind=True, max_retries=2)
def generate_assessment_report(self, assessment_id: str) -> None:
    from app.services.assessments import generate_report

    with _session() as db:
        generate_report(db, uuid.UUID(assessment_id))
        db.commit()


@celery_app.task(name="deploymind.ingest_document")
def ingest_document(document_id: str) -> None:
    from app.rag.ingest import ingest_document as ingest

    with _session() as db:
        ingest(db, uuid.UUID(document_id))


@celery_app.task(name="deploymind.run_evaluation")
def run_evaluation(run_id: str) -> None:
    from app.services.operations import run_evaluation as run

    with _session() as db:
        run(db, uuid.UUID(run_id))


@celery_app.task(name="deploymind.run_deployment")
def run_deployment(deployment_id: str) -> None:
    from app.services.deployments import run_pipeline

    run_pipeline(uuid.UUID(deployment_id))


@celery_app.task(name="deploymind.stop_runtime")
def stop_runtime(adapter_name: str, runtime: dict, deployment_id: str) -> None:
    from app.deploy.adapters import get_adapter
    from app.models import DeploymentLog

    with _session() as db:
        try:
            get_adapter(adapter_name).stop(runtime)
            message, level = "Runtime stopped and removed", "info"
        except Exception as exc:
            message, level = f"Failed to stop runtime: {exc}", "error"
            log.exception("stop_runtime_failed", extra={"deployment_id": deployment_id})
        db.add(DeploymentLog(deployment_id=uuid.UUID(deployment_id), stage="stop", level=level, message=message[:2000],
                             created_at=datetime.now(UTC)))
        db.commit()


@celery_app.task(name="deploymind.sync_integration")
def sync_integration(integration_id: str, job_id: str) -> None:
    from app.services.integrations import execute

    with _session() as db:
        job = db.get(Job, uuid.UUID(job_id))
        job.status = "running"
        db.commit()
        integ = db.get(Integration, uuid.UUID(integration_id))
        try:
            run = execute(db, integ, "sync")
            job.status = "succeeded" if run.status == "succeeded" else "failed"
            job.result = {"run_id": str(run.id), "message": run.message, "records": run.records_processed}
            job.error = run.error
            job.progress = 100
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(Job, uuid.UUID(job_id))
            job.status, job.error = "failed", str(exc)[:1000]
            db.commit()
            log.exception("integration_sync_failed")


@celery_app.task(name="deploymind.health_check_environments")
def health_check_environments() -> int:
    from app.services.deployments import health_check

    n = 0
    with _session() as db:
        for env in db.scalars(select(Environment).where(Environment.current_deployment_id.is_not(None))).all():
            health_check(db, env)
            n += 1
        db.commit()
    return n


@celery_app.task(name="deploymind.report_adapter_status")
def report_adapter_status() -> list[dict]:
    from app.deploy.adapters import publish_worker_status

    return publish_worker_status()


@worker_ready.connect
def _on_worker_ready(**_kwargs) -> None:
    report_adapter_status.delay()


@celery_app.task(name="deploymind.check_budgets")
def check_budgets() -> int:
    from app.services.operations import check_budgets as check

    with _session() as db:
        return check(db)


# ------------------------------------------------------------------ enqueue helpers used by API/services
def enqueue_ingest(db: Session, doc: Document) -> None:
    doc_id = str(doc.id)
    after_commit(db, lambda: ingest_document.delay(doc_id))


def enqueue_report(db: Session, assessment_id: uuid.UUID) -> None:
    after_commit(db, lambda: generate_assessment_report.delay(str(assessment_id)))


def enqueue_evaluation(db: Session, run_id: uuid.UUID) -> None:
    after_commit(db, lambda: run_evaluation.delay(str(run_id)))


def enqueue_deployment(db: Session, deployment_id: uuid.UUID) -> None:
    after_commit(db, lambda: run_deployment.delay(str(deployment_id)))


def enqueue_stop(db: Session, adapter: str, runtime: dict, deployment_id: uuid.UUID) -> None:
    dep_id = str(deployment_id)
    after_commit(db, lambda: stop_runtime.delay(adapter, runtime, dep_id))


def enqueue_sync(db: Session, integ: Integration, user_id: uuid.UUID) -> Job:
    job = Job(organisation_id=integ.organisation_id, kind="integration.sync", status="queued",
              payload={"integration_id": str(integ.id)}, created_by=user_id, created_at=datetime.now(UTC))
    db.add(job)
    db.flush()
    jid, iid = str(job.id), str(integ.id)
    after_commit(db, lambda: sync_integration.delay(iid, jid))
    return job
