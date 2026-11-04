"""Deterministic, configurable hospitality performance scoring."""

from __future__ import annotations

from decimal import Decimal


REVIEWER_WEIGHTS = {"SELF": 0.15, "PEER": 0.25, "MANAGER": 0.60, "SYSTEM": 0.60}


def clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def normalize_kpi_score(kpi: dict, actual_value: float) -> float:
    """Normalize a measured KPI to 0-100 using its configured direction and range."""
    direction = str(kpi.get("direction") or "HIGHER_BETTER").upper()
    target = float(kpi.get("target_value") or 0)
    minimum = float(kpi.get("min_value") or 0)
    maximum = float(kpi.get("max_value") or 100)
    actual = float(actual_value)
    if direction == "LOWER_BETTER":
        if actual <= target:
            return 100.0
        span = maximum - target
        return round(clamp(100 * (maximum - actual) / span), 2) if span > 0 else 0.0
    if direction == "TARGET":
        span = (target - minimum) if actual < target else (maximum - target)
        return round(clamp(100 - (abs(actual - target) / span * 100)), 2) if span > 0 else 100.0
    if actual >= target:
        return 100.0
    span = target - minimum
    return round(clamp(100 * (actual - minimum) / span), 2) if span > 0 else 0.0


def calculate_overall_score(kpis: list[dict], scores: list[dict]) -> dict:
    """Aggregate reviewer scores by KPI, then apply configurable KPI weights."""
    score_by_kpi: dict[str, list[dict]] = {}
    for score in scores:
        score_by_kpi.setdefault(str(score["cycle_kpi_id"]), []).append(score)
    breakdown = []
    weighted_total = 0.0
    applied_weight = 0.0
    for kpi in kpis:
        rows = score_by_kpi.get(str(kpi["id"]), [])
        if not rows:
            continue
        groups: dict[str, list[float]] = {}
        for row in rows:
            groups.setdefault(str(row.get("reviewer_type")).upper(), []).append(float(row["normalized_score"]))
        group_scores = {kind: sum(values) / len(values) for kind, values in groups.items()}
        reviewer_total = sum(REVIEWER_WEIGHTS.get(kind, 0.25) for kind in group_scores)
        value = sum(score * REVIEWER_WEIGHTS.get(kind, 0.25)
                    for kind, score in group_scores.items()) / reviewer_total
        weight = float(kpi.get("weight") or 0)
        weighted_total += value * weight
        applied_weight += weight
        breakdown.append({"kpi_id": kpi["id"], "name": kpi.get("name"),
                          "score": round(value, 2), "weight": weight})
    overall = round(weighted_total / applied_weight, 2) if applied_weight else None
    return {"overall_score": overall, "breakdown": breakdown,
            "scored_kpis": len(breakdown), "total_kpis": len(kpis)}


def eligibility(overall_score: float | None, promotion_threshold: float,
                increment_threshold: float) -> dict:
    """Eligibility is advisory only; approval remains a human action."""
    if overall_score is None:
        return {"promotion_eligible": False, "increment_eligible": False}
    return {"promotion_eligible": overall_score >= promotion_threshold,
            "increment_eligible": overall_score >= increment_threshold}


def json_number(value):
    return float(value) if isinstance(value, Decimal) else value
