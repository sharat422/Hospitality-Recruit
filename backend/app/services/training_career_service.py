"""Deterministic training progress, quiz scoring and promotion readiness."""
from __future__ import annotations

from datetime import date


def score_quiz(questions: list[dict], answers: dict[str, str]) -> dict:
    if not questions:
        return {"score": 0.0, "correct": 0, "total": 0}
    correct = sum(1 for q in questions if str(answers.get(str(q["id"]), "")) == str(q["correct_option"]))
    return {"score": round(correct * 100 / len(questions), 2), "correct": correct, "total": len(questions)}


def calculate_promotion_readiness(*, step: dict, employee_skills: list[dict],
                                  completed_course_ids: set[str], performance_score: float | None,
                                  joining_date: str | None = None) -> dict:
    required = step.get("required_skills") or []
    if isinstance(required, dict):
        required = [{"skill_id": key, "min_proficiency": value} for key, value in required.items()]
    owned: dict[str, int] = {}
    for row in employee_skills:
        level = int(row.get("proficiency") or 0)
        definition = row.get("skill_definitions") or {}
        for key in (row.get("skill_id"), definition.get("code"), definition.get("name")):
            if key: owned[str(key).strip().lower()] = max(level, owned.get(str(key).strip().lower(), 0))
    def skill_key(item): return str(item.get("skill_id") or item.get("code") or item.get("name") or "").strip().lower()
    missing_skills = [item for item in required if owned.get(skill_key(item), 0) < int(item.get("min_proficiency", 1))]
    required_courses = {str(value) for value in (step.get("required_course_ids") or [])}
    missing_courses = sorted(required_courses - completed_course_ids)
    threshold = float(step.get("minimum_performance_score") or 0)
    performance_met = performance_score is not None and float(performance_score) >= threshold
    tenure_required = int(step.get("minimum_tenure_months") or 0)
    tenure_months = 0
    if joining_date:
        joined = date.fromisoformat(str(joining_date)[:10]); today = date.today()
        tenure_months = max(0, (today.year-joined.year)*12 + today.month-joined.month - (today.day < joined.day))
    tenure_met = tenure_months >= tenure_required
    components = [100 * (len(required)-len(missing_skills))/len(required) if required else 100,
                  100 * (len(required_courses)-len(missing_courses))/len(required_courses) if required_courses else 100,
                  min(100, float(performance_score or 0)), 100 if tenure_met else (100*tenure_months/tenure_required if tenure_required else 100)]
    readiness = round(sum(components) / 4, 2)
    return {"readiness_score": readiness, "ready": not missing_skills and not missing_courses and performance_met and tenure_met,
            "performance_score": performance_score, "performance_met": performance_met, "tenure_months": tenure_months,
            "tenure_met": tenure_met, "missing_skills": missing_skills, "missing_course_ids": missing_courses,
            "advisory": "Readiness is advisory. Promotion requires an approved performance outcome and manager action."}
