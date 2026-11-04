"""Attendance codes: their effect on pay, leave balance and comp-off."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.attendance_codes_service import (
    DEFAULT_CODES,
    AttendanceCode,
    attendance_summary,
    available_comp_off,
    code_from_row,
    code_map,
    comp_off_earned,
    expired_comp_off,
    leave_consumption,
    lop_days,
    resolve_code,
    worked_days,
)


def days(*statuses: str) -> list[dict]:
    return [{"status": s, "attendance_date": f"2026-04-{i + 1:02d}", "worked_minutes": 480}
            for i, s in enumerate(statuses)]


class TestCodeDefinition:
    def test_lop_factor_bounds_enforced(self):
        with pytest.raises(ValueError, match="lop_factor"):
            AttendanceCode("X", "X", lop_factor=1.5)

    def test_unknown_leave_type_rejected(self):
        with pytest.raises(ValueError, match="unknown leave type"):
            AttendanceCode("X", "X", consumes_leave_type="HOLIDAY_LEAVE")

    def test_all_eleven_codes_present(self):
        assert set(code_map()) == {"P", "WO", "H", "CL", "SL", "EL", "CO", "HD", "OD", "LWP", "A"}

    def test_every_default_has_a_hindi_label(self):
        assert all(c.label_hi for c in DEFAULT_CODES)

    def test_half_day_is_the_only_fractional_code(self):
        fractional = [c.code for c in DEFAULT_CODES if 0 < c.lop_factor < 1]
        assert fractional == ["HD"]


class TestLossOfPay:
    def test_paid_codes_cost_nothing(self):
        assert lop_days(days("P", "WO", "H", "CL", "SL", "EL", "CO", "OD")) == 0.0

    def test_absent_and_lwp_are_full_unpaid_days(self):
        assert lop_days(days("A", "LWP")) == 2.0

    def test_half_day_costs_half(self):
        assert lop_days(days("HD")) == 0.5
        assert lop_days(days("HD", "HD")) == 1.0

    def test_half_day_does_not_consume_leave(self):
        # The rule chosen for this hotel: HD is 0.5 LOP, leave untouched.
        assert leave_consumption(days("HD")) == {}

    def test_realistic_month(self):
        # 20 present, 4 weekly offs, 2 casual leave, 1 absent, 1 half day
        month = days(*(["P"] * 20 + ["WO"] * 4 + ["CL"] * 2 + ["A"] + ["HD"]))
        assert lop_days(month) == 1.5

    def test_unrecognised_status_is_unpaid_not_free(self):
        # MISSING_PUNCH / INVALID must surface as a pay query, not silent pay.
        assert lop_days([{"status": "MISSING_PUNCH"}, {"status": "INVALID"}]) == 2.0

    def test_blank_status_is_unpaid(self):
        assert lop_days([{"status": None}, {}]) == 2.0

    def test_hotel_can_override_a_code(self):
        # A hotel that pays for authorised absence sets A to zero.
        custom = [AttendanceCode("A", "Absent", lop_factor=0.0)]
        assert lop_days(days("A"), custom) == 0.0


class TestLegacyStatuses:
    def test_old_statuses_still_cost_correctly(self):
        assert lop_days([{"status": "PRESENT"}]) == 0.0
        assert lop_days([{"status": "ABSENT"}]) == 1.0
        assert lop_days([{"status": "WEEKLY_OFF"}]) == 0.0

    def test_legacy_leave_maps_to_a_paid_code(self):
        assert lop_days([{"status": "LEAVE"}]) == 0.0

    def test_resolve_returns_none_for_junk(self):
        assert resolve_code("NONSENSE", code_map()) is None


class TestWorkedDays:
    def test_only_worked_codes_count(self):
        assert worked_days(days("P", "P", "WO", "CL")) == 2.0

    def test_half_day_counts_as_half(self):
        assert worked_days(days("HD")) == 0.5

    def test_on_duty_elsewhere_counts_as_worked(self):
        assert worked_days(days("OD")) == 1.0


class TestLeaveConsumption:
    def test_each_leave_code_draws_its_own_balance(self):
        assert leave_consumption(days("CL", "CL", "SL", "EL")) == {
            "CASUAL": 2.0, "SICK": 1.0, "EARNED": 1.0}

    def test_comp_off_draws_comp_off_balance(self):
        assert leave_consumption(days("CO")) == {"COMP_OFF": 1.0}

    def test_lwp_consumes_no_balance(self):
        assert leave_consumption(days("LWP")) == {}


class TestCompOffEarning:
    def test_working_a_weekly_off_earns_one_day(self):
        records = [{"status": "P", "rostered_status": "WO",
                    "attendance_date": "2026-04-05", "worked_minutes": 480}]
        earned = comp_off_earned(records, earned_on=date(2026, 4, 5))
        assert len(earned) == 1
        assert earned[0]["earned_for_date"] == "2026-04-05"

    def test_expires_after_thirty_days(self):
        records = [{"status": "P", "rostered_status": "WO",
                    "attendance_date": "2026-04-05", "worked_minutes": 480}]
        earned = comp_off_earned(records, earned_on=date(2026, 4, 5))
        assert earned[0]["expires_on"] == "2026-05-05"

    def test_working_a_holiday_also_earns(self):
        records = [{"status": "P", "rostered_status": "H",
                    "attendance_date": "2026-04-14", "worked_minutes": 480}]
        assert len(comp_off_earned(records)) == 1

    def test_an_ordinary_working_day_earns_nothing(self):
        records = [{"status": "P", "rostered_status": "P",
                    "attendance_date": "2026-04-06", "worked_minutes": 480}]
        assert comp_off_earned(records) == []

    def test_a_weekly_off_actually_taken_earns_nothing(self):
        records = [{"status": "WO", "rostered_status": "WO",
                    "attendance_date": "2026-04-05", "worked_minutes": 0}]
        assert comp_off_earned(records) == []

    def test_rest_day_with_no_minutes_worked_earns_nothing(self):
        records = [{"status": "P", "rostered_status": "WO",
                    "attendance_date": "2026-04-05", "worked_minutes": 0}]
        assert comp_off_earned(records) == []

    def test_expiry_window_is_configurable(self):
        codes = [c for c in DEFAULT_CODES if c.code != "CO"]
        codes.append(AttendanceCode("CO", "Comp Off", lop_factor=0.0,
                                    consumes_leave_type="COMP_OFF",
                                    rules={"earn_basis": "PER_OT_DAY", "expiry_days": 90}))
        records = [{"status": "P", "rostered_status": "WO",
                    "attendance_date": "2026-04-05", "worked_minutes": 480}]
        earned = comp_off_earned(records, codes, earned_on=date(2026, 4, 5))
        assert earned[0]["expires_on"] == "2026-07-04"


class TestCompOffBalance:
    LEDGER = [
        {"status": "AVAILABLE", "expires_on": "2026-05-05"},
        {"status": "AVAILABLE", "expires_on": "2026-04-20"},
        {"status": "CONSUMED",  "expires_on": "2026-05-10"},
        {"status": "AVAILABLE", "expires_on": "2026-03-30"},  # lapsed
    ]

    def test_available_excludes_consumed_and_lapsed(self):
        live = available_comp_off(self.LEDGER, as_of=date(2026, 4, 10))
        assert len(live) == 2

    def test_soonest_to_expire_first(self):
        live = available_comp_off(self.LEDGER, as_of=date(2026, 4, 10))
        assert live[0]["expires_on"] == "2026-04-20"

    def test_expiring_today_is_still_usable(self):
        assert len(available_comp_off(
            [{"status": "AVAILABLE", "expires_on": "2026-04-10"}], as_of=date(2026, 4, 10))) == 1

    def test_lapsed_entries_are_reported_for_sweeping(self):
        lapsed = expired_comp_off(self.LEDGER, as_of=date(2026, 4, 10))
        assert len(lapsed) == 1
        assert lapsed[0]["expires_on"] == "2026-03-30"


class TestAttendanceSummary:
    def test_month_end_payroll_input(self):
        month = days(*(["P"] * 20 + ["WO"] * 4 + ["CL"] * 2 + ["A"] + ["HD"]))
        summary = attendance_summary(month)
        assert summary["total_days"] == 28
        assert summary["lop_days"] == 1.5
        assert summary["worked_days"] == 20.5
        assert summary["leave_consumed"] == {"CASUAL": 2.0}
        assert summary["days_by_code"]["P"] == 20

    def test_unrecognised_days_are_counted_separately(self):
        summary = attendance_summary([{"status": "P"}, {"status": "GARBAGE"}])
        assert summary["unrecognised_days"] == 1

    def test_empty_month_is_safe(self):
        assert attendance_summary([])["lop_days"] == 0.0


class TestCodeFromRow:
    def test_builds_from_stored_row(self):
        code = code_from_row({"code": "HD", "label_en": "Half Day", "lop_factor": "0.5",
                              "counts_as_worked": True})
        assert code.lop_factor == 0.5
        assert code.counts_as_worked is True

    def test_defaults_fill_missing_columns(self):
        code = code_from_row({"code": "X"})
        assert code.label_en == "X"
        assert code.lop_factor == 0.0
        assert code.is_paid is True
