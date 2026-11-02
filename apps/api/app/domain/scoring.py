"""Deterministic, explainable AI-readiness scoring.

score(question)   = option score in [0, 4]  (multi-select: sum of selected option scores, capped at 4)
dimension score   = sum(weight_q * score_q) / sum(weight_q * 4) * 100, over applicable questions
overall score     = sum(dimension_weight * dimension_score) / sum(dimension_weight)
Conditional questions whose condition is not met are excluded from both numerator and denominator.

No language model is involved in any number produced here.
"""

from dataclasses import asdict, dataclass, field

from app.domain.question_bank import DIMENSIONS

MAX_OPTION_SCORE = 4

LEVELS = [(80, "Leading"), (65, "Established"), (45, "Developing"), (25, "Emerging"), (0, "Exploring")]

CLASSIFICATION_TEXT = {
    "Leading": "AI is embedded in strategy and operations; focus on scaling and differentiation.",
    "Established": "Strong foundations; ready to deliver production AI systems with measurable value.",
    "Developing": "Good building blocks with specific gaps; start with a focused, well-scoped pilot.",
    "Emerging": "Interest exists but foundations are thin; fix data and governance gaps alongside a small pilot.",
    "Exploring": "Early stage; invest in strategy, data foundations and literacy before building.",
}


class AnswerError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


@dataclass
class QuestionContribution:
    key: str
    text: str
    answer_label: str
    score: float
    max_score: int
    weight: float
    weighted: float


@dataclass
class DimensionResult:
    dimension: str
    label: str
    score: float
    weight: float
    level: str
    breakdown: list[QuestionContribution] = field(default_factory=list)


@dataclass
class ScoreResult:
    overall: float
    classification: str
    classification_text: str
    dimensions: dict[str, DimensionResult]

    def to_dict(self) -> dict:
        return asdict(self)


def level_for(score: float) -> str:
    for threshold, name in LEVELS:
        if score >= threshold:
            return name
    return "Exploring"


def is_applicable(question: dict, answers: dict) -> bool:
    cond = question.get("condition")
    if not cond:
        return True
    parent = answers.get(cond["question"])
    if parent is None:
        return False
    values = parent if isinstance(parent, list) else [parent]
    return any(v in cond["in"] for v in values)


def validate_answer(question: dict, value) -> str | None:
    valid = {o["value"] for o in question["options"]}
    if question["qtype"] == "multi":
        if not isinstance(value, list):
            return "expected a list of options"
        bad = [v for v in value if v not in valid]
        return f"invalid options {bad}" if bad else None
    if not isinstance(value, str) or value not in valid:
        return f"invalid option {value!r}"
    return None


def question_score(question: dict, value) -> tuple[float, str]:
    by_value = {o["value"]: o for o in question["options"]}
    if question["qtype"] == "multi":
        selected = [by_value[v] for v in value]
        total = min(MAX_OPTION_SCORE, sum(o["score"] for o in selected))
        return float(total), ", ".join(o["label"] for o in selected) or "None selected"
    opt = by_value[value]
    return float(opt["score"]), opt["label"]


def applicable_questions(questions: list[dict], answers: dict) -> list[dict]:
    return [q for q in questions if is_applicable(q, answers)]


def missing_answers(questions: list[dict], answers: dict) -> list[str]:
    return [q["key"] for q in applicable_questions(questions, answers) if q["key"] not in answers]


def score_assessment(questions: list[dict], answers: dict) -> ScoreResult:
    errors: dict[str, str] = {}
    for q in questions:
        if q["key"] in answers and is_applicable(q, answers):
            err = validate_answer(q, answers[q["key"]])
            if err:
                errors[q["key"]] = err
    for key in missing_answers(questions, answers):
        errors[key] = "answer required"
    if errors:
        raise AnswerError(errors)

    dims: dict[str, DimensionResult] = {}
    for dim, meta in DIMENSIONS.items():
        contributions: list[QuestionContribution] = []
        num = den = 0.0
        for q in questions:
            if q["dimension"] != dim or not is_applicable(q, answers):
                continue
            s, label = question_score(q, answers[q["key"]])
            w = float(q["weight"])
            num += w * s
            den += w * MAX_OPTION_SCORE
            contributions.append(QuestionContribution(q["key"], q["text"], label, s, MAX_OPTION_SCORE, w, round(w * s, 2)))
        score = round(num / den * 100, 1) if den else 0.0
        dims[dim] = DimensionResult(dim, meta["label"], score, meta["weight"], level_for(score), contributions)

    total_w = sum(d.weight for d in dims.values())
    overall = round(sum(d.weight * d.score for d in dims.values()) / total_w, 1)
    cls = level_for(overall)
    return ScoreResult(overall, cls, CLASSIFICATION_TEXT[cls], dims)


# ------------------------------------------------------------------ deterministic findings

DIMENSION_RECOMMENDATIONS = {
    "strategy": "Agree a one-page AI ambition with leadership, naming 2-3 target outcomes and an accountable sponsor.",
    "data": "Inventory the data behind the first use case, assign owners and fix the highest-impact quality issues.",
    "process": "Map the target workflow end to end, capture volumes and cycle times to create a measurable baseline.",
    "technology": "Expose the systems in scope through documented APIs and set up a CI/CD path for AI services.",
    "governance": "Publish an AI acceptable-use policy and define human-review checkpoints and data-handling rules.",
    "people": "Run role-based AI literacy sessions and appoint champions inside the teams adopting the first use case.",
}

CROSS_RULES = [
    (lambda d: d["strategy"] >= 65 and d["data"] < 45,
     "Ambition outpaces data foundations: early projects risk failing on data availability rather than AI capability."),
    (lambda d: d["technology"] >= 65 and d["governance"] < 45,
     "Technical capability exceeds governance maturity: shadow AI deployments may create compliance exposure."),
    (lambda d: d["people"] < 45 and d["strategy"] >= 45,
     "Strategy is ahead of skills and change readiness: plan adoption support from the start."),
    (lambda d: d["process"] < 45,
     "Without process baselines it will be hard to prove ROI; measure before automating."),
]


def build_findings(questions: list[dict], answers: dict, result: ScoreResult) -> dict:
    by_key = {q["key"]: q for q in questions}
    dim_scores = {k: v.score for k, v in result.dimensions.items()}
    ordered = sorted(result.dimensions.values(), key=lambda d: d.score, reverse=True)

    strengths, weaknesses, risks = [], [], []
    for d in ordered:
        if d.score >= 65:
            strengths.append({"dimension": d.dimension, "title": f"{d.label} is {d.level.lower()}",
                              "evidence": [c.text for c in d.breakdown if c.score >= 3][:3]})
        if d.score < 45:
            weaknesses.append({"dimension": d.dimension, "title": f"{d.label} needs attention ({d.score:.0f}/100)",
                               "evidence": [f"{c.text} - answered '{c.answer_label}'" for c in d.breakdown
                                            if c.score <= 1][:3]})
    if not strengths and ordered:
        top = ordered[0]
        strengths.append({"dimension": top.dimension, "title": f"{top.label} is your strongest dimension",
                          "evidence": [c.text for c in top.breakdown if c.score >= 2][:3]})
    if not weaknesses and ordered:
        low = ordered[-1]
        weaknesses.append({"dimension": low.dimension, "title": f"{low.label} is your weakest dimension",
                           "evidence": [f"{c.text} - answered '{c.answer_label}'" for c in low.breakdown
                                        if c.score <= 2][:3]})

    for d in result.dimensions.values():
        for c in d.breakdown:
            flag = by_key[c.key].get("risk_flag")
            if flag and c.score <= 1:
                risks.append({"dimension": d.dimension, "severity": "high" if c.score == 0 else "medium",
                              "risk": flag, "source": c.key})
    for rule, text in CROSS_RULES:
        if rule(dim_scores):
            risks.append({"dimension": "cross", "severity": "medium", "risk": text, "source": "cross_dimension_rule"})

    weakest = [d.dimension for d in sorted(result.dimensions.values(), key=lambda d: d.score)[:3]]
    recommendations = [{"dimension": dim, "label": DIMENSIONS[dim]["label"],
                        "recommendation": DIMENSION_RECOMMENDATIONS[dim]} for dim in weakest]
    return {"strengths": strengths, "weaknesses": weaknesses, "risks": risks,
            "recommendations": recommendations, "weakest_dimensions": weakest,
            "method": "Deterministic weighted scoring, question bank v1"}


def build_plans(result: ScoreResult, first_project: dict | None, weakest: list[str]) -> dict:
    project = first_project["title"] if first_project else "a focused AI pilot"
    foundation = [DIMENSION_RECOMMENDATIONS[w] for w in weakest[:2]]
    ready = result.overall >= 45
    plan_30_60_90 = [
        {"window": "First 30 days", "focus": "Align and baseline",
         "actions": ["Confirm executive sponsor and success metrics for " + project,
                     "Run a technical discovery covering data sources, integrations and security constraints",
                     foundation[0]]},
        {"window": "Days 31-60", "focus": "Prove value safely",
         "actions": [f"Build a working prototype of {project} on a representative data sample",
                     "Define an evaluation dataset and acceptance thresholds before user testing",
                     foundation[1] if len(foundation) > 1 else "Document data handling and human-review rules"]},
        {"window": "Days 61-90", "focus": "Production readiness" if ready else "Pilot and harden",
         "actions": ["Integrate with production systems behind access controls and audit logging",
                     "Deploy to a staging environment with monitoring, cost tracking and rollback",
                     "Pilot with a named user group and measure against the baseline"]},
    ]
    roadmap = [
        {"horizon": "3 months", "milestone": f"{project} live for a pilot group",
         "outcomes": ["Measured baseline vs. pilot metrics", "Governance policy in place", "Evaluation suite running"]},
        {"horizon": "6 months", "milestone": f"{project} in production; second use case in discovery",
         "outcomes": ["SLOs and incident process operating", "Adoption across target teams",
                      "Reusable retrieval/integration components"]},
        {"horizon": "12 months", "milestone": "Managed AI portfolio with shared platform capabilities",
         "outcomes": ["3+ use cases in production", "Quarterly value reviews", "Internal AI skills programme"]},
    ]
    return {"plan_30_60_90": plan_30_60_90, "roadmap": roadmap}
