from datetime import date

from app.services.onboarding_orchestration_service import (
    calculate_onboarding_ghosting_risk,
    compute_onboarding_progress,
    select_most_specific_template,
)


def test_selects_property_department_role_template_over_defaults():
    templates = [
        {"id": "global", "org_id": None, "is_active": True},
        {"id": "org", "org_id": "o1", "is_active": True},
        {"id": "property", "org_id": "o1", "property_id": "p1", "is_active": True},
        {"id": "exact", "org_id": "o1", "property_id": "p1", "department_id": "d1",
         "role_template_id": "r1", "is_active": True},
    ]
    selected = select_most_specific_template(
        templates, org_id="o1", property_id="p1", department_id="d1", role_template_id="r1")
    assert selected["id"] == "exact"


def test_inactive_or_cross_tenant_template_is_not_selected():
    selected = select_most_specific_template([
        {"id": "other", "org_id": "o2", "is_active": True},
        {"id": "off", "org_id": "o1", "is_active": False},
        {"id": "fallback", "org_id": None, "is_active": True},
    ], org_id="o1", property_id=None, department_id=None, role_template_id=None)
    assert selected["id"] == "fallback"


def test_weighted_completion_and_current_stage():
    tasks = [
        {"stage": "documents", "status": "completed", "is_mandatory": True, "weight": 2},
        {"stage": "documents", "status": "waived", "is_mandatory": True, "weight": 1},
        {"stage": "kyc", "status": "pending", "is_mandatory": True, "weight": 1},
        {"stage": "kyc", "status": "pending", "is_mandatory": False, "weight": 100},
    ]
    result = compute_onboarding_progress(tasks)
    assert result["completion_pct"] == 75
    assert result["stage_completion"]["documents"] == 100
    assert result["current_stage"] == "kyc"
    assert result["completed"] is False


def test_ghosting_risk_is_capped_explainable_and_non_decisional():
    flow = {"joining_date": "2026-08-29", "offer_accepted_at": "2026-08-20T10:00:00+00:00",
            "manager_id": None, "appointment_signed": False}
    tasks = [
        {"stage": "documents", "task_type": "aadhaar_upload", "status": "pending",
         "is_mandatory": True, "due_date": "2026-08-24"},
        {"stage": "payroll", "task_type": "appointment_esign", "status": "pending",
         "is_mandatory": True, "due_date": "2026-08-25"},
    ]
    result = calculate_onboarding_ghosting_risk(flow, tasks, today=date(2026, 8, 28))
    assert result["ghosting_risk_score"] == 0.96
    assert result["ghosting_risk_level"] == "CRITICAL"
    assert {s["code"] for s in result["ghosting_risk_signals"]} == {
        "NO_ACTIVITY_3_DAYS", "OVERDUE_REQUIRED_TASKS", "JOINING_SOON_LOW_PROGRESS",
        "NO_MANAGER", "LETTER_NOT_SIGNED",
    }
    assert "decision" not in result and "rejected" not in result


def test_completed_onboarding_is_low_risk():
    tasks = [{"stage": stage, "status": "completed", "is_mandatory": True}
             for stage in ("documents", "kyc", "certifications", "payroll", "ready")]
    result = calculate_onboarding_ghosting_risk(
        {"joining_date": "2026-09-15", "last_candidate_activity_at": "2026-08-28",
         "manager_id": "u1", "appointment_signed": True}, tasks, today=date(2026, 8, 28))
    assert result["completion_pct"] == 100
    assert result["ghosting_risk_level"] == "LOW"
