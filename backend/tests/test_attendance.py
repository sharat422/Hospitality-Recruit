from datetime import datetime, timezone

from app.services.attendance_service import attendance_date_for, calculate_daily_attendance, evaluate_geofence
from app.services.biometric_adapters import get_biometric_adapter


def p(kind: str, timestamp: str, geofence_status: str = "INSIDE") -> dict:
    return {"punch_type": kind, "punched_at": timestamp, "geofence_status": geofence_status}


POLICY = {"late_grace_minutes": 10, "early_departure_grace_minutes": 5, "overtime_after_minutes": 480}
START = "2026-06-10T09:00:00+00:00"
END = "2026-06-10T17:00:00+00:00"


def test_normal_day_is_present_but_not_payroll_validated():
    result = calculate_daily_attendance([p("IN", START), p("OUT", END)],
                                        scheduled_start=START, scheduled_end=END, policy=POLICY)
    assert result["status"] == "PRESENT"
    assert result["worked_minutes"] == 480
    assert result["validation_status"] == "PENDING"


def test_late_arrival_respects_grace_period():
    result = calculate_daily_attendance([p("IN", "2026-06-10T09:25:00+00:00"), p("OUT", END)],
                                        scheduled_start=START, scheduled_end=END, policy=POLICY)
    assert result["late_minutes"] == 15


def test_early_departure_respects_grace_period():
    result = calculate_daily_attendance([p("IN", START), p("OUT", "2026-06-10T16:30:00+00:00")],
                                        scheduled_start=START, scheduled_end=END, policy=POLICY)
    assert result["early_departure_minutes"] == 25


def test_overtime_after_configured_threshold():
    result = calculate_daily_attendance([p("IN", START), p("OUT", "2026-06-10T19:00:00+00:00")],
                                        scheduled_start=START, scheduled_end=END, policy=POLICY)
    assert result["worked_minutes"] == 600
    assert result["overtime_minutes"] == 120


def test_missing_punch_is_not_present():
    result = calculate_daily_attendance([p("IN", START)], scheduled_start=START, scheduled_end=END, policy=POLICY)
    assert result["status"] == "MISSING_PUNCH"
    assert "MISSING_OUT" in result["anomaly_codes"]


def test_double_punch_is_detected():
    result = calculate_daily_attendance([
        p("IN", START), p("IN", "2026-06-10T09:02:00+00:00"), p("OUT", END)
    ], scheduled_start=START, scheduled_end=END, policy=POLICY)
    assert result["status"] == "MISSING_PUNCH"
    assert "DOUBLE_IN" in result["anomaly_codes"]


def test_absence_and_weekly_off_are_distinct():
    assert calculate_daily_attendance([], policy=POLICY)["status"] == "ABSENT"
    assert calculate_daily_attendance([], policy=POLICY, weekly_off=True)["status"] == "WEEKLY_OFF"


def test_geofence_inside_and_outside():
    policy = {"require_geofence": True, "latitude": 19.076, "longitude": 72.8777, "geofence_radius_m": 150}
    assert evaluate_geofence(19.0761, 72.8777, policy)[0] == "INSIDE"
    assert evaluate_geofence(19.1, 72.9, policy)[0] == "OUTSIDE"


def test_attendance_date_uses_property_timezone():
    assert attendance_date_for("2026-06-09T19:30:00Z", "Asia/Kolkata").isoformat() == "2026-06-10"


def test_generic_biometric_adapter_normalizes_events():
    adapter = get_biometric_adapter("generic_json")
    assert adapter.verify_signature(b"{}", {"x-attendance-token": "secret"}, "secret")
    events = adapter.parse_events({"events": [{
        "event_id": "evt-1", "employee_id": "EMP-101", "punch_type": "in",
        "punched_at": "2026-06-10T09:00:00Z", "device_id": "gate-1",
    }]})
    assert events[0].employee_external_id == "EMP-101"
    assert events[0].punch_type == "IN"


def test_manager_approves_correction_and_validates_day(client_as_admin):
    client, sb = client_as_admin
    actor = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    employee = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    org = "11111111-1111-1111-1111-111111111111"
    prop = "22222222-2222-2222-2222-222222222222"
    correction = {
        "id": "33333333-3333-4333-8333-333333333333", "org_id": org,
        "employee_id": employee, "daily_record_id": "44444444-4444-4444-8444-444444444444",
        "status": "PENDING", "requested_in_at": START, "requested_out_at": END,
    }
    daily = {"id": correction["daily_record_id"], "property_id": prop, "source_version": 1,
             "scheduled_start": START, "scheduled_end": END}
    sb.configure("users",
                 [{"id": actor, "org_id": org, "role": "GENERAL_MANAGER", "department_id": None,
                   "active_property_id": prop}],
                 [{"id": employee, "org_id": org, "active_property_id": prop, "department_id": None}])
    sb.configure("property_memberships", [{"property_id": prop, "department_id": None, "is_active": True}])
    sb.configure("attendance_corrections", [correction], [{**correction, "status": "APPROVED"}])
    sb.configure("attendance_daily_records", [daily], [{**daily, "validation_status": "VALIDATED"}])
    sb.configure("attendance_policies", [POLICY])
    response = client.patch(f"/api/v1/attendance/corrections/{correction['id']}", json={"action": "APPROVE"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPROVED"
