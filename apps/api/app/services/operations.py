"""Evaluation runs, monitoring aggregates, cost reporting and budget alerts."""

import logging
import statistics
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.ai.agents.framework import AgentError, AgentRunner
from app.ai.agents.run import EVALUATION_AGENT, JudgeIn
from app.ai.providers.base import ProviderError
from app.models import (
    AIApplication,
    Budget,
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
    ModelUsage,
    Organisation,
    Project,
    TelemetryEvent,
)
from app.rag.assistant import answer_question
from app.rag.text import support_ratio, token_f1
from app.services.common import notify

log = logging.getLogger("deploymind.ops")

METRIC_KEYS = ["correctness", "faithfulness", "context_relevance", "retrieval_precision", "retrieval_recall",
               "citation_quality", "tool_execution_success"]
REGRESSION_TOLERANCE = 0.05


# ------------------------------------------------------------------ evaluation
def score_case(case: EvaluationCase, answer, error: str | None) -> dict:
    if error:
        return {k: 0.0 for k in METRIC_KEYS} | {"latency_ms": 0, "cost_usd": 0.0, "error": error}
    retrieved = list(dict.fromkeys(c.filename for c in answer.retrieved))
    cited = list(dict.fromkeys(c["filename"] for c in answer.citations))
    expected = set(case.expected_sources)
    ctx = " ".join(c.content for c in answer.retrieved)
    m: dict = {}
    if case.must_refuse:
        m["correctness"] = 1.0 if answer.insufficient_evidence else 0.0
        m["citation_quality"] = 1.0 if not cited else 0.0
        m["faithfulness"] = 1.0 if answer.insufficient_evidence else support_ratio(answer.answer, ctx)
    else:
        kws = [k.lower() for k in case.expected_keywords]
        kw_cov = sum(1 for k in kws if k in answer.answer.lower()) / len(kws) if kws else None
        f1 = token_f1(answer.answer, case.expected_answer) if case.expected_answer else 0.0
        m["correctness"] = round(kw_cov if kw_cov is not None else f1, 3)
        m["citation_quality"] = round(len(set(cited) & expected) / len(cited), 3) if cited and expected else (
            0.0 if not cited else 1.0)
        m["faithfulness"] = 0.0 if answer.insufficient_evidence else round(support_ratio(answer.answer, ctx), 3)
    m["retrieval_precision"] = round(len(set(retrieved) & expected) / len(retrieved), 3) if retrieved and expected else (
        1.0 if not expected and not retrieved else 0.0)
    m["retrieval_recall"] = round(len(set(retrieved) & expected) / len(expected), 3) if expected else 1.0
    m["context_relevance"] = round(statistics.fmean([c.relevance for c in answer.retrieved]), 3) if answer.retrieved else 0.0
    m["tool_execution_success"] = 1.0
    m["latency_ms"] = answer.latency_ms
    m["cost_usd"] = float(answer.cost_usd)
    m["token_f1"] = round(token_f1(answer.answer, case.expected_answer), 3) if case.expected_answer else None
    return m


def passed(case: EvaluationCase, m: dict) -> bool:
    if m.get("error"):
        return False
    if case.must_refuse:
        return m["correctness"] == 1.0
    return m["correctness"] >= 0.5 and m["faithfulness"] >= 0.7 and m["citation_quality"] >= 0.5


def aggregate(results: list[EvaluationResult]) -> dict:
    if not results:
        return {}
    agg = {k: round(statistics.fmean(r.metrics.get(k, 0.0) or 0.0 for r in results), 3) for k in METRIC_KEYS}
    lat = sorted(r.metrics.get("latency_ms", 0) for r in results)
    agg["latency_p50_ms"] = lat[len(lat) // 2]
    agg["latency_p95_ms"] = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]
    agg["total_cost_usd"] = round(sum(r.metrics.get("cost_usd", 0.0) for r in results), 6)
    agg["pass_rate"] = round(sum(1 for r in results if r.passed) / len(results), 3)
    agg["cases"] = len(results)
    judged = [r.metrics["judge"] for r in results if r.metrics.get("judge")]
    if judged:
        for k in ("correctness", "faithfulness", "context_relevance"):
            agg[f"judge_{k}"] = round(statistics.fmean(j[k] for j in judged), 3)
    return agg


def detect_regressions(current: dict, baseline: dict) -> list[dict]:
    out = []
    for k in [*METRIC_KEYS, "pass_rate"]:
        if k in current and k in baseline and current[k] < baseline[k] - REGRESSION_TOLERANCE:
            out.append({"metric": k, "baseline": baseline[k], "current": current[k],
                        "delta": round(current[k] - baseline[k], 3)})
    if baseline.get("latency_p95_ms") and current.get("latency_p95_ms", 0) > baseline["latency_p95_ms"] * 1.5 + 50:
        out.append({"metric": "latency_p95_ms", "baseline": baseline["latency_p95_ms"],
                    "current": current["latency_p95_ms"], "delta": current["latency_p95_ms"] - baseline["latency_p95_ms"]})
    return out


def run_evaluation(db: Session, run_id: uuid.UUID) -> EvaluationRun:
    run = db.get(EvaluationRun, run_id)
    app = db.get(AIApplication, run.app_id)
    run.status = "running"
    db.commit()
    cfg = run.config
    cases = db.scalars(select(EvaluationCase).where(EvaluationCase.dataset_id == run.dataset_id)
                       .order_by(EvaluationCase.created_at)).all()
    use_judge = cfg.get("llm_judge") and cfg.get("provider", app.provider) != "mock"
    try:
        for case in cases:
            error, ans = None, None
            try:
                ans = answer_question(
                    db, app, case.question, user_id=None, is_internal=False, source="evaluation",
                    config_override=cfg.get("retrieval"), provider_override=cfg.get("provider"),
                    model_override=cfg.get("model"), system_prompt_override=cfg.get("system_prompt"),
                )
            except ProviderError as exc:
                error = str(exc)
            metrics = score_case(case, ans, error)
            if use_judge and ans and not case.must_refuse:
                try:
                    j = AgentRunner(db, app.organisation_id, provider=cfg.get("provider"), app_id=app.id).run(
                        EVALUATION_AGENT, JudgeIn(question=case.question, expected_answer=case.expected_answer,
                                                  answer=ans.answer, context=[c.content for c in ans.retrieved]))
                    metrics["judge"] = j.output.model_dump()
                except AgentError as exc:
                    metrics["judge_error"] = str(exc)[:300]
            db.add(EvaluationResult(run_id=run.id, case_id=case.id, answer=ans.answer if ans else "",
                                    retrieved_sources=list(dict.fromkeys(c.filename for c in ans.retrieved)) if ans else [],
                                    cited_sources=list(dict.fromkeys(c["filename"] for c in ans.citations)) if ans else [],
                                    metrics=metrics, passed=passed(case, metrics)))
            db.flush()
        results = db.scalars(select(EvaluationResult).where(EvaluationResult.run_id == run.id)).all()
        run.metrics = aggregate(list(results))
        run.judge = "llm+deterministic" if use_judge else "deterministic"
        baseline = db.get(EvaluationRun, run.baseline_run_id) if run.baseline_run_id else db.scalar(
            select(EvaluationRun).where(EvaluationRun.dataset_id == run.dataset_id, EvaluationRun.status == "completed",
                                        EvaluationRun.id != run.id).order_by(EvaluationRun.created_at.desc()).limit(1))
        if baseline:
            run.baseline_run_id = baseline.id
            run.regressions = detect_regressions(run.metrics, baseline.metrics)
            if run.regressions:
                from app.api.deps import provider_org
                notify(db, provider_org(db).id, "evaluation.regression", f"Evaluation regression: {app.name}",
                       f"Run '{run.label}' regressed on {[r['metric'] for r in run.regressions]} vs '{baseline.label}'.",
                       link=f"/app/evaluations/{run.id}", audience="internal")
        run.status, run.finished_at = "completed", datetime.now(UTC)
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(EvaluationRun, run_id)
        run.status, run.error, run.finished_at = "failed", str(exc)[:1000], datetime.now(UTC)
        db.commit()
        log.exception("evaluation_failed", extra={"run_id": str(run_id)})
    return run


# ------------------------------------------------------------------ monitoring
def _sources(source: str) -> list[str]:
    return {"real": ["platform", "deployment"], "demo": ["demo_seed"], "all": ["platform", "deployment", "demo_seed"]}[source]


def monitoring_overview(db: Session, org_ids: list[uuid.UUID] | None, *, app_id: uuid.UUID | None, hours: int,
                        source: str) -> dict:
    since = datetime.now(UTC) - timedelta(hours=hours)
    base = select(TelemetryEvent).where(TelemetryEvent.created_at >= since,
                                        TelemetryEvent.source.in_(_sources(source)))
    if org_ids is not None:
        base = base.where(TelemetryEvent.organisation_id.in_(org_ids))
    if app_id:
        base = base.where(TelemetryEvent.app_id == app_id)
    q = base.where(TelemetryEvent.kind == "rag_query").subquery()
    row = db.execute(select(
        func.count(), func.count().filter(q.c.status == "success"), func.count().filter(q.c.status == "error"),
        func.percentile_cont(0.5).within_group(q.c.latency_ms), func.percentile_cont(0.95).within_group(q.c.latency_ms),
        func.percentile_cont(0.99).within_group(q.c.latency_ms), func.coalesce(func.sum(q.c.input_tokens), 0),
        func.coalesce(func.sum(q.c.output_tokens), 0), func.coalesce(func.sum(q.c.cost_usd), 0),
        func.avg(q.c.retrieval_ms), func.avg(q.c.top_relevance), func.avg(q.c.retrieved_chunks),
    ).select_from(q)).one()
    total, ok, err, p50, p95, p99, tin, tout, cost, r_ms, rel, chunks = row
    bucket = "hour" if hours <= 48 else "day"
    ts_col = func.date_trunc(bucket, q.c.created_at)
    series = db.execute(select(ts_col.label("t"), func.count(), func.count().filter(q.c.status == "error"),
                               func.percentile_cont(0.95).within_group(q.c.latency_ms),
                               func.coalesce(func.sum(q.c.input_tokens + q.c.output_tokens), 0),
                               func.coalesce(func.sum(q.c.cost_usd), 0))
                        .select_from(q).group_by("t").order_by("t")).all()
    models = db.execute(select(q.c.provider, q.c.model, func.count(),
                               func.coalesce(func.sum(q.c.input_tokens + q.c.output_tokens), 0),
                               func.coalesce(func.sum(q.c.cost_usd), 0))
                        .select_from(q).group_by(q.c.provider, q.c.model).order_by(func.count().desc())).all()
    hc = base.where(TelemetryEvent.kind == "health_check").subquery()
    hc_total, hc_ok = db.execute(select(func.count(), func.count().filter(hc.c.status == "success")).select_from(hc)).one()
    by_source = dict(db.execute(select(q.c.source, func.count()).select_from(q).group_by(q.c.source)).all())
    return {
        "window_hours": hours, "source": source, "sources_present": by_source,
        "requests": total, "successful": ok, "failed": err,
        "error_rate": round(err / total, 4) if total else 0.0,
        "latency_ms": {"p50": round(p50 or 0), "p95": round(p95 or 0), "p99": round(p99 or 0)},
        "tokens": {"input": int(tin), "output": int(tout), "total": int(tin + tout)},
        "estimated_cost_usd": float(cost),
        "retrieval": {"avg_ms": round(float(r_ms or 0), 1), "avg_top_relevance": round(float(rel or 0), 3),
                      "avg_chunks": round(float(chunks or 0), 2)},
        "uptime": {"checks": hc_total, "successful": hc_ok,
                   "ratio": round(hc_ok / hc_total, 4) if hc_total else None},
        "series": [{"t": t.isoformat(), "requests": n, "errors": e, "p95_ms": round(p or 0), "tokens": int(tok),
                    "cost_usd": float(c)} for t, n, e, p, tok, c in series],
        "models": [{"provider": p, "model": m, "requests": n, "tokens": int(t), "cost_usd": float(c)}
                   for p, m, n, t, c in models],
    }


# ------------------------------------------------------------------ costs
def cost_summary(db: Session, org_ids: list[uuid.UUID] | None, days: int, include_demo: bool) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    q = select(ModelUsage).where(ModelUsage.created_at >= since)
    if org_ids is not None:
        q = q.where(ModelUsage.organisation_id.in_(org_ids))
    if not include_demo:
        q = q.where(ModelUsage.is_demo.is_(False))
    s = q.subquery()
    totals = db.execute(select(func.count(), func.coalesce(func.sum(s.c.input_tokens), 0),
                               func.coalesce(func.sum(s.c.output_tokens), 0), func.coalesce(func.sum(s.c.cost_usd), 0),
                               func.count().filter(s.c.is_mock)).select_from(s)).one()
    by_org = db.execute(select(s.c.organisation_id, Organisation.name, func.count(), func.sum(s.c.cost_usd),
                               func.sum(s.c.input_tokens + s.c.output_tokens))
                        .select_from(s).join(Organisation, Organisation.id == s.c.organisation_id)
                        .group_by(s.c.organisation_id, Organisation.name).order_by(func.sum(s.c.cost_usd).desc())).all()
    by_project = db.execute(select(s.c.project_id, Project.name, func.count(), func.sum(s.c.cost_usd))
                            .select_from(s).outerjoin(Project, Project.id == s.c.project_id)
                            .group_by(s.c.project_id, Project.name).order_by(func.sum(s.c.cost_usd).desc())).all()
    by_model = db.execute(select(s.c.provider, s.c.model, s.c.operation, func.count(), func.sum(s.c.input_tokens),
                                 func.sum(s.c.output_tokens), func.sum(s.c.cost_usd))
                          .select_from(s).group_by(s.c.provider, s.c.model, s.c.operation)
                          .order_by(func.sum(s.c.cost_usd).desc())).all()
    by_agent = db.execute(select(s.c.agent, func.count(), func.sum(s.c.cost_usd), func.sum(s.c.input_tokens + s.c.output_tokens))
                          .select_from(s).group_by(s.c.agent).order_by(func.count().desc())).all()
    daily = db.execute(select(cast(s.c.created_at, Date).label("d"), func.count(), func.sum(s.c.cost_usd),
                              func.sum(s.c.input_tokens), func.sum(s.c.output_tokens))
                       .select_from(s).group_by("d").order_by("d")).all()
    monthly = db.execute(select(func.to_char(s.c.created_at, "YYYY-MM").label("m"), func.count(), func.sum(s.c.cost_usd))
                         .select_from(s).group_by("m").order_by("m")).all()
    n, tin, tout, cost, mock_n = totals
    return {
        "days": days, "include_demo": include_demo, "label": "Estimated cost from configurable provider pricing",
        "totals": {"requests": n, "input_tokens": int(tin), "output_tokens": int(tout), "estimated_cost_usd": float(cost),
                   "mock_requests": mock_n},
        "by_organisation": [{"organisation_id": str(o), "name": nm, "requests": c, "cost_usd": float(v or 0),
                             "tokens": int(t or 0)} for o, nm, c, v, t in by_org],
        "by_project": [{"project_id": str(p) if p else None, "name": nm or "Platform (no project)", "requests": c,
                        "cost_usd": float(v or 0)} for p, nm, c, v in by_project],
        "by_model": [{"provider": p, "model": m, "operation": op, "requests": c, "input_tokens": int(i or 0),
                      "output_tokens": int(o or 0), "cost_usd": float(v or 0)} for p, m, op, c, i, o, v in by_model],
        "by_agent": [{"agent": a, "requests": c, "cost_usd": float(v or 0), "tokens": int(t or 0)} for a, c, v, t in by_agent],
        "daily": [{"date": d.isoformat(), "requests": c, "cost_usd": float(v or 0), "input_tokens": int(i or 0),
                   "output_tokens": int(o or 0)} for d, c, v, i, o in daily],
        "monthly": [{"month": m, "requests": c, "cost_usd": float(v or 0)} for m, c, v in monthly],
    }


def month_spend(db: Session, org_id: uuid.UUID, project_id: uuid.UUID | None) -> Decimal:
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = select(func.coalesce(func.sum(ModelUsage.cost_usd), 0)).where(ModelUsage.organisation_id == org_id,
                                                                     ModelUsage.created_at >= start)
    if project_id:
        q = q.where(ModelUsage.project_id == project_id)
    return Decimal(db.scalar(q) or 0)


def budget_status(db: Session, b: Budget) -> dict:
    spend = month_spend(db, b.organisation_id, b.project_id)
    pct = float(spend / b.monthly_limit_usd * 100) if b.monthly_limit_usd else 0.0
    state = "exceeded" if pct >= 100 else "warning" if pct >= b.alert_threshold_pct else "ok"
    return {"spend_usd": float(spend), "percent": round(pct, 1), "state": state}


def check_budgets(db: Session) -> int:
    """Raise at most one alert per threshold level per budget per month."""
    month = datetime.now(UTC).strftime("%Y-%m")
    alerts = 0
    for b in db.scalars(select(Budget)).all():
        st = budget_status(db, b)
        level = 100 if st["state"] == "exceeded" else b.alert_threshold_pct if st["state"] == "warning" else None
        if level is None:
            continue
        if b.last_alert_month == month and (b.last_alert_level or 0) >= level:
            continue
        b.last_alert_month, b.last_alert_level = month, level
        from app.api.deps import provider_org
        title = f"AI budget {'exceeded' if level == 100 else 'warning'}: {st['percent']}% of ${b.monthly_limit_usd}"
        notify(db, provider_org(db).id, "budget.alert", title, f"Organisation {b.organisation_id}", audience="internal")
        notify(db, b.organisation_id, "budget.alert", title, "Estimated AI usage cost this month.", audience="customer")
        alerts += 1
    db.commit()
    return alerts
