"""Opportunity catalogue and configurable prioritisation.

Each catalogue entry has baseline attributes (1-5 scales) which are adjusted deterministically by the
assessment results and stated business objectives. Priority is a weighted sum normalised to 0-100.
All financial values are illustrative estimates derived from explicit assumptions that are stored
alongside each opportunity.
"""

from dataclasses import dataclass

from app.domain.question_bank import COMPANY_SIZES

DEFAULT_WEIGHTS = {
    "business_impact": 0.30,
    "data_availability": 0.20,
    "feasibility": 0.15,          # inverse of implementation complexity
    "integration_ease": 0.15,     # inverse of integration complexity
    "security": 0.10,             # inverse of security risk
    "time_to_value": 0.10,        # inverse of effort
}

DEFAULT_FINANCIAL_ASSUMPTIONS = {
    "loaded_hourly_cost": 45.0,       # GBP per employee hour
    "weekly_delivery_rate": 6500.0,   # GBP per week of delivery effort
    "working_weeks": 46,
    "currency": "GBP",
}

CATALOG: dict[str, dict] = {
    "support_automation": {
        "title": "Customer support automation",
        "description": "Classify, route and draft responses to inbound customer enquiries with human approval.",
        "impact": 4, "complexity": 3, "effort_weeks": 8, "data_need": "data", "integration": 3, "security": 3,
        "objectives": ["improve_customer_experience", "reduce_operational_costs"],
        "affected_share": 0.08, "hours_per_week": 10, "automation_rate": 0.35, "systems": ["ticketing", "crm"]},
    "sales_qualification": {
        "title": "Sales lead qualification",
        "description": "Score and enrich inbound leads, summarise context and route to the right salesperson.",
        "impact": 3, "complexity": 2, "effort_weeks": 6, "data_need": "data", "integration": 3, "security": 2,
        "objectives": ["increase_revenue"],
        "affected_share": 0.05, "hours_per_week": 6, "automation_rate": 0.30, "systems": ["crm"]},
    "knowledge_assistant": {
        "title": "Internal knowledge assistant",
        "description": "Grounded question answering over internal policies and documents with source citations.",
        "impact": 4, "complexity": 2, "effort_weeks": 6, "data_need": "documents", "integration": 2, "security": 3,
        "objectives": ["improve_employee_productivity", "improve_customer_experience"],
        "affected_share": 0.40, "hours_per_week": 3, "automation_rate": 0.40, "systems": ["dms"]},
    "document_processing": {
        "title": "Intelligent document processing",
        "description": "Extract structured data from contracts, forms and invoices with validation and review queues.",
        "impact": 4, "complexity": 3, "effort_weeks": 9, "data_need": "documents", "integration": 3, "security": 4,
        "objectives": ["reduce_operational_costs", "risk_compliance"],
        "affected_share": 0.10, "hours_per_week": 8, "automation_rate": 0.50, "systems": ["dms", "erp"]},
    "proposal_generation": {
        "title": "Proposal and report generation",
        "description": "Draft proposals and client reports from templates, past work and CRM context for expert review.",
        "impact": 3, "complexity": 2, "effort_weeks": 5, "data_need": "documents", "integration": 2, "security": 2,
        "objectives": ["increase_revenue", "improve_employee_productivity"],
        "affected_share": 0.06, "hours_per_week": 6, "automation_rate": 0.40, "systems": ["crm", "dms"]},
    "workflow_automation": {
        "title": "Request triage and workflow automation",
        "description": "Classify internal requests and route tasks to the right team with SLAs and audit trails.",
        "impact": 4, "complexity": 3, "effort_weeks": 8, "data_need": "process", "integration": 4, "security": 3,
        "objectives": ["reduce_operational_costs", "improve_employee_productivity"],
        "affected_share": 0.15, "hours_per_week": 4, "automation_rate": 0.45, "systems": ["ticketing", "database"]},
    "intelligent_search": {
        "title": "Enterprise intelligent search",
        "description": "Hybrid semantic and keyword search across systems, respecting existing permissions.",
        "impact": 3, "complexity": 3, "effort_weeks": 7, "data_need": "documents", "integration": 4, "security": 3,
        "objectives": ["improve_employee_productivity", "better_decision_making"],
        "affected_share": 0.35, "hours_per_week": 1.5, "automation_rate": 0.30, "systems": ["dms", "database"]},
}


def _clamp(v: float) -> int:
    return int(max(1, min(5, round(v))))


@dataclass
class ScoredOpportunity:
    catalog_key: str
    title: str
    description: str
    business_impact: int
    implementation_complexity: int
    effort_weeks: int
    data_availability: int
    integration_complexity: int
    security_risk: int
    roi_assumptions: dict
    priority_score: float
    reasoning: dict
    rank: int = 0


def _band(score: float) -> int:
    """Map a 0-100 dimension score onto a 1-5 scale."""
    return _clamp(1 + score / 25)


def evaluate(dim_scores: dict[str, float], profile: dict, answers: dict,
             weights: dict | None = None, assumptions: dict | None = None) -> list[ScoredOpportunity]:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    fin = {**DEFAULT_FINANCIAL_ASSUMPTIONS, **(assumptions or {})}
    objectives = set(profile.get("objectives") or [])
    employees = profile.get("employee_count") or COMPANY_SIZES.get(profile.get("company_size", ""), 50)
    systems = set(answers.get("tech_systems") or [])
    docs_score = {"none": 0, "shared_drives": 1, "dms": 2, "structured": 3, "curated": 4}.get(
        answers.get("data_documents", ""), 1)

    results: list[ScoredOpportunity] = []
    for key, c in CATALOG.items():
        reasons: list[str] = []
        impact = c["impact"]
        matched = objectives & set(c["objectives"])
        if matched:
            impact += 1
            reasons.append(f"Impact +1: aligns with stated objective(s) {sorted(matched)}")
        if answers.get("process_volume") in ("high", "very_high") and key in ("support_automation", "workflow_automation",
                                                                              "document_processing"):
            impact += 1
            reasons.append("Impact +1: target workflows are high volume")

        if c["data_need"] == "documents":
            data_av = _clamp(1 + docs_score)
            reasons.append(f"Data availability {data_av}/5 from document management maturity")
        elif c["data_need"] == "process":
            data_av = _band((dim_scores["data"] + dim_scores["process"]) / 2)
            reasons.append(f"Data availability {data_av}/5 from data and process readiness")
        else:
            data_av = _band(dim_scores["data"])
            reasons.append(f"Data availability {data_av}/5 from data readiness score {dim_scores['data']:.0f}")

        integ = c["integration"]
        tech_band = _band(dim_scores["technology"])
        if tech_band >= 4:
            integ -= 1
            reasons.append("Integration complexity -1: mature integration capability")
        elif tech_band <= 2:
            integ += 1
            reasons.append("Integration complexity +1: limited APIs / integration tooling")
        have = systems & set(c["systems"])
        if have:
            reasons.append(f"Existing systems in place: {sorted(have)}")
        elif c["systems"]:
            integ += 1
            reasons.append(f"Integration complexity +1: required systems not reported ({c['systems']})")

        sec = c["security"]
        gov_band = _band(dim_scores["governance"])
        if gov_band <= 2:
            sec += 1
            reasons.append("Security risk +1: governance controls are immature")
        if answers.get("data_personal") in ("yes", "unsure") and key in ("support_automation", "document_processing"):
            sec += 1
            reasons.append("Security risk +1: personal data likely in scope")

        complexity = c["complexity"] + (1 if dim_scores["technology"] < 40 else 0)
        effort = int(round(c["effort_weeks"] * (1.25 if dim_scores["technology"] < 40 else 1.0)))

        impact, data_av, integ, sec, complexity = map(_clamp, (impact, data_av, integ, sec, complexity))
        effort_score = _clamp(6 - effort / 2.5)
        factors = {
            "business_impact": impact,
            "data_availability": data_av,
            "feasibility": 6 - complexity,
            "integration_ease": 6 - integ,
            "security": 6 - sec,
            "time_to_value": effort_score,
        }
        weighted = {k: round(w[k] * v, 3) for k, v in factors.items()}
        priority = round(sum(weighted.values()) / (5 * sum(w.values())) * 100, 1)

        affected = max(1, round(employees * c["affected_share"]))
        hours_saved = round(affected * c["hours_per_week"] * c["automation_rate"] * fin["working_weeks"])
        annual_value = round(hours_saved * fin["loaded_hourly_cost"])
        build_cost = round(effort * fin["weekly_delivery_rate"])
        payback = round(build_cost / (annual_value / 12), 1) if annual_value else None
        roi = {
            "label": "Illustrative estimate - not a guaranteed outcome",
            "currency": fin["currency"],
            "assumptions": {
                "employees_affected": affected,
                "hours_per_person_per_week_in_scope": c["hours_per_week"],
                "automation_or_time_saving_rate": c["automation_rate"],
                "loaded_hourly_cost": fin["loaded_hourly_cost"],
                "working_weeks_per_year": fin["working_weeks"],
                "weekly_delivery_rate": fin["weekly_delivery_rate"],
            },
            "estimated_hours_saved_per_year": hours_saved,
            "estimated_annual_value_low": round(annual_value * 0.6),
            "estimated_annual_value_high": annual_value,
            "estimated_build_cost": build_cost,
            "estimated_payback_months": payback,
        }
        results.append(ScoredOpportunity(
            catalog_key=key, title=c["title"], description=c["description"], business_impact=impact,
            implementation_complexity=complexity, effort_weeks=effort, data_availability=data_av,
            integration_complexity=integ, security_risk=sec, roi_assumptions=roi, priority_score=priority,
            reasoning={"factors": factors, "weights": w, "weighted": weighted, "adjustments": reasons,
                       "formula": "priority = sum(weight_i * factor_i) / (5 * sum(weights)) * 100"},
        ))
    results.sort(key=lambda o: (-o.priority_score, o.effort_weeks, o.catalog_key))
    for i, o in enumerate(results, start=1):
        o.rank = i
    return results
