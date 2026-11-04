"""Deterministic performance scoring and RBAC tests."""

import pytest

from app.services.performance_service import calculate_overall_score, eligibility, normalize_kpi_score
from app.services.rbac_service import has_permission


@pytest.mark.parametrize("actual,expected", [(0, 100), (5, 50), (10, 0)])
def test_lower_is_better_guest_complaints(actual, expected):
    kpi = {"direction":"LOWER_BETTER","target_value":0,"min_value":0,"max_value":10}
    assert normalize_kpi_score(kpi, actual) == expected


@pytest.mark.parametrize("actual,expected", [(30,100),(0,0),(100,0)])
def test_target_food_cost_uses_configured_range(actual, expected):
    kpi = {"direction":"TARGET","target_value":30,"min_value":0,"max_value":100}
    assert normalize_kpi_score(kpi, actual) == expected


def test_higher_is_better_room_quality():
    kpi = {"direction":"HIGHER_BETTER","target_value":95,"min_value":0,"max_value":100}
    assert normalize_kpi_score(kpi, 95) == 100
    assert normalize_kpi_score(kpi, 47.5) == 50


def test_peer_count_does_not_increase_peer_weight():
    kpis = [{"id":"k1","name":"Guest rating","weight":100}]
    scores = [
        {"cycle_kpi_id":"k1","reviewer_type":"MANAGER","normalized_score":100},
        {"cycle_kpi_id":"k1","reviewer_type":"SELF","normalized_score":100},
        {"cycle_kpi_id":"k1","reviewer_type":"PEER","normalized_score":0},
        {"cycle_kpi_id":"k1","reviewer_type":"PEER","normalized_score":0},
    ]
    # Category weights remain manager 60%, peer 25%, self 15% regardless of peer count.
    assert calculate_overall_score(kpis, scores)["overall_score"] == 75


def test_configurable_kpi_weights_drive_overall_score():
    kpis = [{"id":"quality","name":"Quality","weight":70},
            {"id":"speed","name":"Speed","weight":30}]
    scores = [{"cycle_kpi_id":"quality","reviewer_type":"MANAGER","normalized_score":90},
              {"cycle_kpi_id":"speed","reviewer_type":"MANAGER","normalized_score":50}]
    assert calculate_overall_score(kpis, scores)["overall_score"] == 78


def test_unscored_review_has_no_eligibility():
    assert eligibility(None, 80, 70) == {"promotion_eligible":False,"increment_eligible":False}


def test_threshold_eligibility_is_advisory_result():
    assert eligibility(82, 80, 70) == {"promotion_eligible":True,"increment_eligible":True}
    assert eligibility(75, 80, 70) == {"promotion_eligible":False,"increment_eligible":True}


def test_performance_permissions_are_narrow():
    assert has_permission("employee", "performance.read")
    assert not has_permission("employee", "performance.manage")
    assert has_permission("department_head", "performance.manage")
    assert not has_permission("recruiter", "performance.read")
