"""Occupancy-driven staffing arithmetic and PMS payload normalization."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.pms_adapters import (
    GenericRestPMSAdapter,
    MockPMSAdapter,
    OccupancyDay,
    get_pms_adapter,
    provider_catalog,
    resolve_config,
)
from app.services.pms_staffing_service import (
    DEFAULT_RATIOS,
    StaffingRatio,
    hiring_signal,
    plan_summary,
    ratio_from_row,
    staffing_plan,
)


def day(sold: int, available: int = 100, arrivals: int = 0, departures: int = 0) -> OccupancyDay:
    return OccupancyDay(date(2026, 3, 10), available, sold, arrivals, departures)


class TestOccupancyDay:
    def test_occupancy_pct(self):
        assert day(75).occupancy_pct == 75.0

    def test_zero_rooms_does_not_divide_by_zero(self):
        assert OccupancyDay(date(2026, 3, 10), 0, 0).occupancy_pct == 0.0

    def test_oversold_rejected(self):
        with pytest.raises(ValueError, match="exceeds rooms_available"):
            OccupancyDay(date(2026, 3, 10), 10, 11)

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="negative"):
            OccupancyDay(date(2026, 3, 10), -1, 0)


class TestRequiredHeadcount:
    def test_rounds_up_partial_staff(self):
        # 80 rooms / 16 per attendant = 5.0 exactly
        assert StaffingRatio("HK", "HK", "OCCUPIED_ROOMS", 16).required_headcount(day(80)) == 5
        # 81 rooms needs a sixth attendant, not 5.06 of one
        assert StaffingRatio("HK", "HK", "OCCUPIED_ROOMS", 16).required_headcount(day(81)) == 6

    def test_min_staff_is_a_floor_at_low_occupancy(self):
        ratio = StaffingRatio("FO", "Front Office", "ARRIVALS", 40, min_staff=3)
        assert ratio.required_headcount(day(0, arrivals=0)) == 3

    def test_scales_above_the_floor(self):
        ratio = StaffingRatio("FO", "Front Office", "ARRIVALS", 40, min_staff=3)
        assert ratio.required_headcount(day(200, 300, arrivals=200)) == 5

    def test_covers_driver_uses_covers_per_room(self):
        # 50 rooms * 1.6 covers = 80 covers / 20 per steward = 4
        ratio = StaffingRatio("FB", "F&B", "COVERS", 20, covers_per_room=1.6)
        assert ratio.required_headcount(day(50)) == 4

    def test_fixed_driver_ignores_occupancy(self):
        ratio = StaffingRatio("SEC", "Security", "FIXED", 1, min_staff=3)
        assert ratio.required_headcount(day(0)) == 3
        assert ratio.required_headcount(day(100)) == 3

    def test_unknown_driver_rejected(self):
        with pytest.raises(ValueError, match="Unknown staffing driver"):
            StaffingRatio("X", "X", "VIBES", 10)

    def test_zero_units_per_staff_rejected(self):
        with pytest.raises(ValueError, match="units_per_staff"):
            StaffingRatio("X", "X", "OCCUPIED_ROOMS", 0)


class TestStaffingPlan:
    def test_gap_is_required_minus_scheduled(self):
        ratios = [StaffingRatio("HK", "Housekeeping", "OCCUPIED_ROOMS", 16)]
        plan = staffing_plan([day(80)], ratios, {("HK", date(2026, 3, 10)): 2})
        assert plan[0]["required_headcount"] == 5
        assert plan[0]["scheduled_headcount"] == 2
        assert plan[0]["gap"] == 3
        assert plan[0]["status"] == "SHORT"

    def test_missing_roster_entry_counts_as_zero_not_balanced(self):
        ratios = [StaffingRatio("HK", "Housekeeping", "OCCUPIED_ROOMS", 16)]
        plan = staffing_plan([day(80)], ratios, {})
        assert plan[0]["scheduled_headcount"] == 0
        assert plan[0]["status"] == "SHORT"

    def test_overstaffed_is_flagged(self):
        ratios = [StaffingRatio("HK", "Housekeeping", "OCCUPIED_ROOMS", 16)]
        plan = staffing_plan([day(16)], ratios, {("HK", date(2026, 3, 10)): 4})
        assert plan[0]["gap"] == -3
        assert plan[0]["status"] == "OVER"

    def test_one_row_per_day_per_department(self):
        days = [OccupancyDay(date(2026, 3, d), 100, 50) for d in (10, 11, 12)]
        plan = staffing_plan(days, DEFAULT_RATIOS)
        assert len(plan) == 3 * len(DEFAULT_RATIOS)


class TestHiringSignal:
    @staticmethod
    def _plan(short_days: int):
        ratios = [StaffingRatio("HK", "Housekeeping", "OCCUPIED_ROOMS", 16)]
        days = [OccupancyDay(date(2026, 3, 10 + i), 100, 80) for i in range(short_days)]
        return staffing_plan(days, ratios, {})

    def test_single_short_day_is_not_a_hiring_signal(self):
        assert hiring_signal(self._plan(1)) == []

    def test_sustained_shortfall_raises_a_signal(self):
        signals = hiring_signal(self._plan(5))
        assert len(signals) == 1
        assert signals[0]["department_code"] == "HK"
        assert signals[0]["short_days"] == 5

    def test_recommends_median_not_peak(self):
        # Four comfortable days and one festival spike must not drive a
        # permanent hire sized for the spike.
        ratios = [StaffingRatio("HK", "Housekeeping", "OCCUPIED_ROOMS", 16)]
        days = [OccupancyDay(date(2026, 3, 10 + i), 200, 32) for i in range(4)]
        days.append(OccupancyDay(date(2026, 3, 14), 200, 200))
        plan = staffing_plan(days, ratios, {})
        signal = hiring_signal(plan)[0]
        assert signal["peak_gap"] == 13
        assert signal["recommended_hires"] == 2

    def test_urgency_escalates_past_a_week(self):
        assert hiring_signal(self._plan(5))[0]["urgency"] == "MEDIUM"
        assert hiring_signal(self._plan(8))[0]["urgency"] == "HIGH"

    def test_threshold_is_configurable(self):
        assert hiring_signal(self._plan(2), min_short_days=2)
        assert hiring_signal(self._plan(2), min_short_days=3) == []


class TestPlanSummary:
    def test_empty_plan_is_safe(self):
        assert plan_summary([])["days"] == 0

    def test_counts_distinct_days_not_rows(self):
        days = [OccupancyDay(date(2026, 3, d), 100, 50) for d in (10, 11)]
        summary = plan_summary(staffing_plan(days, DEFAULT_RATIOS))
        assert summary["days"] == 2
        assert summary["avg_occupancy_pct"] == 50.0

    def test_total_gap_counts_shortfalls_only(self):
        ratios = [StaffingRatio("HK", "Housekeeping", "OCCUPIED_ROOMS", 16)]
        days = [OccupancyDay(date(2026, 3, 10), 100, 80),   # needs 5
                OccupancyDay(date(2026, 3, 11), 100, 16)]   # needs 1
        scheduled = {("HK", date(2026, 3, 10)): 1, ("HK", date(2026, 3, 11)): 6}
        summary = plan_summary(staffing_plan(days, ratios, scheduled))
        assert summary["total_gap"] == 4  # +4 short; the -5 overstaff is not netted off


class TestMockAdapter:
    def test_is_deterministic(self):
        adapter = MockPMSAdapter()
        args = ({"property_ref": "goa-01", "rooms_available": 80}, date(2026, 3, 1), date(2026, 3, 7))
        assert [d.as_row() for d in adapter.fetch_occupancy(*args)] == \
               [d.as_row() for d in adapter.fetch_occupancy(*args)]

    def test_covers_the_inclusive_range(self):
        days = MockPMSAdapter().fetch_occupancy({}, date(2026, 3, 1), date(2026, 3, 7))
        assert len(days) == 7
        assert days[0].business_date == date(2026, 3, 1)
        assert days[-1].business_date == date(2026, 3, 7)

    def test_never_oversells(self):
        days = MockPMSAdapter().fetch_occupancy({"rooms_available": 60}, date(2026, 3, 1), date(2026, 4, 30))
        assert all(d.rooms_sold <= d.rooms_available for d in days)

    def test_different_properties_differ(self):
        a = MockPMSAdapter().fetch_occupancy({"property_ref": "goa"}, date(2026, 3, 1), date(2026, 3, 14))
        b = MockPMSAdapter().fetch_occupancy({"property_ref": "delhi"}, date(2026, 3, 1), date(2026, 3, 14))
        assert [d.rooms_sold for d in a] != [d.rooms_sold for d in b]


class TestRestNormalization:
    def test_maps_vendor_fields_to_canonical(self):
        payload = {"data": [
            {"BusinessDate": "2026-03-11T00:00:00", "TotalRooms": "100",
             "OccupiedRooms": "72", "ExpectedArrivals": 30, "ExpectedDepartures": 25},
        ]}
        field_map = {"business_date": "BusinessDate", "rooms_available": "TotalRooms",
                     "rooms_sold": "OccupiedRooms", "arrivals": "ExpectedArrivals",
                     "departures": "ExpectedDepartures"}
        days = GenericRestPMSAdapter._normalize(payload, field_map, {})
        assert days[0].business_date == date(2026, 3, 11)
        assert days[0].rooms_sold == 72
        assert days[0].occupancy_pct == 72.0

    def test_oversold_row_is_clamped_not_rejected(self):
        payload = [{"date": "2026-03-11", "rooms_available": 100, "rooms_sold": 105}]
        days = GenericRestPMSAdapter._normalize(
            payload, {"business_date": "date", "rooms_available": "rooms_available",
                      "rooms_sold": "rooms_sold", "arrivals": "a", "departures": "d"}, {})
        assert days[0].rooms_sold == 100

    def test_rows_without_a_date_are_skipped(self):
        payload = [{"rooms_sold": 10}, {"date": "2026-03-11", "rooms_available": 50, "rooms_sold": 10}]
        days = GenericRestPMSAdapter._normalize(
            payload, {"business_date": "date", "rooms_available": "rooms_available",
                      "rooms_sold": "rooms_sold", "arrivals": "a", "departures": "d"}, {})
        assert len(days) == 1

    def test_output_is_date_sorted(self):
        payload = [{"date": "2026-03-12", "rooms_available": 50, "rooms_sold": 10},
                   {"date": "2026-03-11", "rooms_available": 50, "rooms_sold": 10}]
        days = GenericRestPMSAdapter._normalize(
            payload, {"business_date": "date", "rooms_available": "rooms_available",
                      "rooms_sold": "rooms_sold", "arrivals": "a", "departures": "d"}, {})
        assert [d.business_date.day for d in days] == [11, 12]

    def test_non_list_payload_rejected(self):
        with pytest.raises(ValueError, match="list of occupancy rows"):
            GenericRestPMSAdapter._normalize({"error": "nope"}, {"business_date": "date"}, {})


class TestRegistry:
    def test_known_providers_resolve(self):
        for entry in provider_catalog():
            assert get_pms_adapter(entry["provider_code"]) is not None

    def test_unknown_provider_rejected(self):
        with pytest.raises(ValueError, match="Unsupported PMS provider"):
            get_pms_adapter("FAKE_PMS")

    def test_only_sandbox_is_marked_verified(self):
        verified = [e["provider_code"] for e in provider_catalog() if e["verified"]]
        assert verified == ["MOCK"]

    def test_connection_overrides_beat_profile_defaults(self):
        config = resolve_config("IDS_NEXT", {"config": {"field_map": {"rooms_sold": "MyRooms"}}})
        assert config["field_map"]["rooms_sold"] == "MyRooms"          # override wins
        assert config["field_map"]["rooms_available"] == "TotalRooms"  # default kept


class TestRatioFromRow:
    def test_builds_from_stored_row(self):
        ratio = ratio_from_row({"department_code": "HK", "department_name": "Housekeeping",
                                "driver": "OCCUPIED_ROOMS", "units_per_staff": 16, "min_staff": 2})
        assert ratio.required_headcount(day(80)) == 5

    def test_defaults_fill_missing_columns(self):
        ratio = ratio_from_row({"department_code": "HK"})
        assert ratio.driver == "OCCUPIED_ROOMS"
        assert ratio.department_name == "HK"
