from datetime import datetime, timedelta, timezone

from app.services.workforce_scheduling_service import validate_shift_assignment, whatsapp_shift_message

UTC = timezone.utc
MON = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)


def shift(start, hours=8, break_minutes=0, status="PUBLISHED", assignment_id="a1"):
    return {"assignment_id": assignment_id, "start_date": start.isoformat(),
            "end_date": (start + timedelta(hours=hours)).isoformat(),
            "break_minutes": break_minutes, "status": status}


def check(start=MON, end=None, **kwargs):
    return validate_shift_assignment(employee_id="employee-1", start=start, end=end or start + timedelta(hours=8), **kwargs)


def codes(result): return {x["code"] for x in result["conflicts"]}


def test_valid_assignment():
    assert check(existing_shifts=[], availability=[], weekly_offs=[], approved_leave_dates=[])["valid"]


def test_overlap_is_blocked():
    result = check(start=MON + timedelta(hours=2), existing_shifts=[shift(MON)], availability=[], weekly_offs=[], approved_leave_dates=[])
    assert not result["valid"] and "OVERLAP" in codes(result)


def test_twelve_hour_rest_is_enforced():
    result = check(start=MON + timedelta(hours=19), existing_shifts=[shift(MON, 8)], availability=[], weekly_offs=[], approved_leave_dates=[])
    assert "INSUFFICIENT_REST" in codes(result)


def test_exact_twelve_hour_rest_is_valid():
    result = check(start=MON + timedelta(hours=20), existing_shifts=[shift(MON, 8)], availability=[], weekly_offs=[], approved_leave_dates=[])
    assert result["valid"]


def test_more_than_48_weekly_hours_is_blocked():
    existing = [shift(MON + timedelta(days=i), 8, assignment_id=str(i)) for i in range(6)]
    result = check(start=MON + timedelta(days=6), existing_shifts=existing, availability=[], weekly_offs=[], approved_leave_dates=[])
    assert "EXCESSIVE_WEEKLY_HOURS" in codes(result)


def test_approved_leave_is_blocked():
    result = check(existing_shifts=[], availability=[], weekly_offs=[], approved_leave_dates=[MON.date()])
    assert "APPROVED_LEAVE" in codes(result)


def test_weekly_off_is_blocked():
    result = check(existing_shifts=[], availability=[], weekly_offs=[{"day_of_week": 1}], approved_leave_dates=[])
    assert "WEEKLY_OFF" in codes(result)


def test_outside_availability_is_blocked():
    result = check(existing_shifts=[], availability=[{"day_of_week": 1, "available_start": "10:00", "available_end": "18:00", "is_available": True}], weekly_offs=[], approved_leave_dates=[])
    assert "OUTSIDE_AVAILABILITY" in codes(result)


def test_excluded_assignment_supports_drag_move():
    result = check(existing_shifts=[shift(MON, assignment_id="moving")], availability=[], weekly_offs=[], approved_leave_dates=[], exclude_assignment_id="moving")
    assert result["valid"]


def test_whatsapp_message_has_roster_details():
    text = whatsapp_shift_message({"start_date": MON.isoformat(), "end_date": (MON+timedelta(hours=8)).isoformat(), "property_name": "Hotel Mumbai", "role": "Front Desk"})
    assert "Hotel Mumbai" in text and "Front Desk" in text and "SHIFT" in text


def test_assignment_without_id_still_blocks_overlap():
    existing = shift(MON)
    existing.pop("assignment_id")
    assert "OVERLAP" in codes(check(existing_shifts=[existing]))


def test_seventeen_hour_rest_is_valid():
    assert check(start=MON + timedelta(hours=25), existing_shifts=[shift(MON)])["valid"]
