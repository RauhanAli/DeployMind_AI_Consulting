"""Deterministic scoring engine and opportunity prioritisation (pure unit tests, no database)."""

import pytest

from app.domain.opportunities import DEFAULT_WEIGHTS, evaluate
from app.domain.question_bank import DIMENSIONS, QUESTIONS
from app.domain.scoring import (
    AnswerError,
    build_findings,
    build_plans,
    is_applicable,
    level_for,
    score_assessment,
)
from tests.helpers import ANSWERS


def best_answers() -> dict:
    out = {}
    for q in QUESTIONS:
        if q["qtype"] == "multi":
            out[q["key"]] = [o["value"] for o in q["options"]]
        else:
            out[q["key"]] = max(q["options"], key=lambda o: o["score"])["value"]
    return out


def worst_answers() -> dict:
    return {q["key"]: ([] if q["qtype"] == "multi" else min(q["options"], key=lambda o: o["score"])["value"])
            for q in QUESTIONS}


def applicable(answers):
    return {k: v for k, v in answers.items() if is_applicable(next(q for q in QUESTIONS if q["key"] == k), answers)}


def test_perfect_answers_score_100():
    r = score_assessment(QUESTIONS, applicable(best_answers()))
    assert r.overall == 100.0
    assert r.classification == "Leading"
    assert all(d.score == 100.0 for d in r.dimensions.values())


def test_worst_answers_score_0():
    r = score_assessment(QUESTIONS, applicable(worst_answers()))
    assert r.overall == 0.0 and r.classification == "Exploring"


def test_scoring_is_deterministic_and_explainable():
    r1 = score_assessment(QUESTIONS, ANSWERS)
    r2 = score_assessment(QUESTIONS, dict(reversed(list(ANSWERS.items()))))
    assert r1.to_dict() == r2.to_dict()
    for d in r1.dimensions.values():
        num = sum(c.weight * c.score for c in d.breakdown)
        den = sum(c.weight * c.max_score for c in d.breakdown)
        assert d.score == round(num / den * 100, 1)
    total_w = sum(m["weight"] for m in DIMENSIONS.values())
    assert r1.overall == round(sum(DIMENSIONS[k]["weight"] * v.score for k, v in r1.dimensions.items()) / total_w, 1)


def test_known_value_for_reference_answers():
    # Locks the reference profile so any change to weights/options is a deliberate, versioned decision.
    r = score_assessment(QUESTIONS, ANSWERS)
    assert r.dimensions["strategy"].score == pytest.approx(44.7, abs=0.05)  # (1.5*2+1.2*2+1*1+1*2)/(4*4.7)
    assert 30 < r.overall < 60
    assert r.classification in ("Emerging", "Developing")


def test_conditional_question_excluded_when_not_applicable():
    answers = dict(ANSWERS)
    assert answers["strategy_ai_in_production"] == "tools"
    assert not is_applicable(next(q for q in QUESTIONS if q["key"] == "strategy_value_measured"), answers)
    r = score_assessment(QUESTIONS, answers)
    assert "strategy_value_measured" not in [c.key for c in r.dimensions["strategy"].breakdown]


def test_conditional_question_required_when_applicable():
    answers = {**ANSWERS, "strategy_ai_in_production": "pilots"}
    with pytest.raises(AnswerError) as exc:
        score_assessment(QUESTIONS, answers)
    assert "strategy_value_measured" in exc.value.errors


def test_invalid_option_rejected():
    with pytest.raises(AnswerError) as exc:
        score_assessment(QUESTIONS, {**ANSWERS, "data_quality": "amazing"})
    assert "data_quality" in exc.value.errors


def test_multi_select_capped_at_max_score():
    answers = {**ANSWERS, "tech_systems": [o["value"] for o in next(q for q in QUESTIONS if q["key"] == "tech_systems")["options"]]}
    r = score_assessment(QUESTIONS, answers)
    c = next(c for c in r.dimensions["technology"].breakdown if c.key == "tech_systems")
    assert c.score == 4


def test_levels():
    assert [level_for(s) for s in (0, 25, 45, 65, 80, 100)] == ["Exploring", "Emerging", "Developing", "Established",
                                                                 "Leading", "Leading"]


def test_findings_risks_and_plans():
    answers = applicable(worst_answers())
    r = score_assessment(QUESTIONS, answers)
    f = build_findings(QUESTIONS, answers, r)
    assert f["risks"] and all(x["risk"] for x in f["risks"])
    assert len(f["recommendations"]) == 3
    plans = build_plans(r, {"title": "Internal knowledge assistant"}, f["weakest_dimensions"])
    assert [p["window"] for p in plans["plan_30_60_90"]] == ["First 30 days", "Days 31-60", "Days 61-90"]
    assert [p["horizon"] for p in plans["roadmap"]] == ["3 months", "6 months", "12 months"]


def test_opportunity_ranking_is_deterministic_and_explained():
    r = score_assessment(QUESTIONS, ANSWERS)
    dims = {k: v.score for k, v in r.dimensions.items()}
    profile = {"company_size": "201-500", "objectives": ["improve_employee_productivity"]}
    a, b = evaluate(dims, profile, ANSWERS), evaluate(dims, profile, ANSWERS)
    assert [o.catalog_key for o in a] == [o.catalog_key for o in b]
    assert [o.rank for o in a] == list(range(1, len(a) + 1))
    assert a == sorted(a, key=lambda o: -o.priority_score) or a[0].priority_score >= a[-1].priority_score
    for o in a:
        assert o.reasoning["adjustments"] and o.reasoning["formula"]
        assert "not a guaranteed outcome" in o.roi_assumptions["label"]
        assert 0 <= o.priority_score <= 100


def test_configurable_weights_change_ranking():
    r = score_assessment(QUESTIONS, ANSWERS)
    dims = {k: v.score for k, v in r.dimensions.items()}
    impact_only = {k: 0.0 for k in DEFAULT_WEIGHTS} | {"business_impact": 1.0}
    speed_only = {k: 0.0 for k in DEFAULT_WEIGHTS} | {"time_to_value": 1.0}
    top_impact = evaluate(dims, {}, ANSWERS, impact_only)[0]
    top_speed = evaluate(dims, {}, ANSWERS, speed_only)[0]
    assert top_impact.business_impact >= top_speed.business_impact
    assert top_speed.effort_weeks <= top_impact.effort_weeks
