"""Deterministic state machines and business rules. LLMs never drive these transitions."""

from datetime import datetime, timedelta
from decimal import Decimal

from app.core.errors import InvalidTransition

LEAD_PIPELINE = ["new", "qualified", "discovery", "assessment", "proposal", "approved", "implementation", "completed"]
LEAD_TERMINAL_EXTRA = ["lost"]

PROJECT_STAGES = ["discovery", "solution_design", "development", "integration", "testing", "deployment",
                  "production", "handover"]

TASK_STATUSES = ["backlog", "todo", "in_progress", "review", "done"]

INCIDENT_FLOW = {
    "open": {"investigating", "resolved"},
    "investigating": {"identified", "resolved"},
    "identified": {"investigating", "resolved"},
    "resolved": {"closed", "investigating"},
    "closed": set(),
}
INCIDENT_SEVERITIES = {"sev1": "Critical - service down", "sev2": "Major - significant degradation",
                       "sev3": "Minor - limited impact", "sev4": "Low - cosmetic or informational"}

PROPOSAL_FLOW = {
    "draft": {"in_review"},
    "in_review": {"draft", "approved"},
    "approved": {"draft", "sent"},
    "sent": {"accepted", "rejected"},
    "rejected": {"draft"},
    "accepted": set(),
}

TICKET_FLOW = {
    "open": {"in_progress", "waiting_on_customer", "resolved", "closed"},
    "in_progress": {"waiting_on_customer", "resolved", "open"},
    "waiting_on_customer": {"in_progress", "resolved", "closed"},
    "resolved": {"closed", "in_progress"},
    "closed": set(),
}

# Response / resolution targets in business-agnostic hours.
SLA_HOURS = {
    "urgent": (1, 8),
    "high": (4, 24),
    "medium": (8, 72),
    "low": (24, 120),
}


def check_lead_transition(current: str, target: str) -> None:
    if target == current:
        raise InvalidTransition(f"Lead is already '{current}'")
    if target == "lost":
        if current == "completed":
            raise InvalidTransition("A completed engagement cannot be marked lost")
        return
    if target not in LEAD_PIPELINE:
        raise InvalidTransition(f"Unknown lead status '{target}'")
    if current == "lost":
        return  # re-opening a lost lead is allowed to any stage
    ci, ti = LEAD_PIPELINE.index(current), LEAD_PIPELINE.index(target)
    if ti > ci + 1:
        raise InvalidTransition(f"Cannot skip from '{current}' to '{target}'; next stage is '{LEAD_PIPELINE[ci + 1]}'")


def check_transition(flow: dict[str, set[str]], current: str, target: str, entity: str) -> None:
    if target not in flow:
        raise InvalidTransition(f"Unknown {entity} status '{target}'")
    if target not in flow.get(current, set()):
        allowed = sorted(flow.get(current, set()))
        raise InvalidTransition(f"{entity.capitalize()} cannot move from '{current}' to '{target}'",
                                details={"allowed": allowed})


def check_project_stage(current: str, target: str) -> None:
    if target not in PROJECT_STAGES:
        raise InvalidTransition(f"Unknown project stage '{target}'")
    ci, ti = PROJECT_STAGES.index(current), PROJECT_STAGES.index(target)
    if ti > ci + 1:
        raise InvalidTransition(f"Cannot skip from '{current}' to '{target}'")


def sla_deadlines(priority: str, opened_at: datetime) -> tuple[datetime, datetime]:
    resp, res = SLA_HOURS[priority]
    return opened_at + timedelta(hours=resp), opened_at + timedelta(hours=res)


def sla_state(due: datetime, met_at: datetime | None, now: datetime) -> str:
    if met_at is not None:
        return "met" if met_at <= due else "breached"
    if now > due:
        return "breached"
    if (due - now) < timedelta(hours=1):
        return "at_risk"
    return "on_track"


def estimate_cost(input_tokens: int, output_tokens: int, pricing: tuple[Decimal, Decimal] | None) -> Decimal:
    """pricing = (input per million, output per million) in USD. Unknown models cost 0 and are flagged upstream."""
    if pricing is None:
        return Decimal("0")
    inp, out = pricing
    return (Decimal(input_tokens) * inp + Decimal(output_tokens) * out) / Decimal(1_000_000)


def project_progress(stage: str, tasks_done: int, tasks_total: int) -> int:
    stage_pct = PROJECT_STAGES.index(stage) / (len(PROJECT_STAGES) - 1) * 100
    task_pct = (tasks_done / tasks_total * 100) if tasks_total else stage_pct
    return int(round(0.5 * stage_pct + 0.5 * task_pct))
