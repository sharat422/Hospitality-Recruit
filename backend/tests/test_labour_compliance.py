"""
Tests for Indian Labour Compliance Engine.

Coverage:
  1. Pure function tests (no DB): EPF, ESIC, gratuity, working hours, rest period
  2. API endpoint tests (MockSupabase): all labour router endpoints
  3. Edge cases: wage ceilings, OT caps, national floor, ineligible gratuity

Fixture IDs are hex-safe (no 12-digit runs) to avoid false Aadhaar detection.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

# ─── IDs ─────────────────────────────────────────────────────────────────────
ORG_ID       = "aaaa1111-bbbb-cccc-dddd-eeeeaaaa1111"
CANDIDATE_ID = "bbbbcccc-dddd-eeee-ffff-aaaabbbbcccc"

_ORG_ROW   = [{"org_id": ORG_ID}]
_AUDIT_ROW = []


# ═════════════════════════════════════════════════════════════════════════════
# 1. EPF Calculator — pure functions
# ═════════════════════════════════════════════════════════════════════════════

class TestEPFCalculator:
    def test_basic_below_ceiling(self):
        from app.services.labour_compliance_service import calculate_epf
        r = calculate_epf(12000)
        assert r["applicable"] is True
        assert r["employee_epf_inr"] == pytest.approx(1440.0)         # 12%
        assert r["employer_eps_inr"]  == pytest.approx(999.6)          # 8.33%
        assert r["employer_epf_inr"]  == pytest.approx(440.4)          # 3.67%
        assert r["wage_ceiling_applied"] is False

    def test_eps_capped_at_15000(self):
        from app.services.labour_compliance_service import calculate_epf
        r = calculate_epf(25000)
        # EPS is 8.33% of 15000 only (ceiling)
        assert r["employer_eps_inr"] == pytest.approx(15000 * 8.33 / 100, abs=0.1)
        assert r["wage_ceiling_applied"] is True

    def test_employee_contribution_always_on_actual_salary(self):
        from app.services.labour_compliance_service import calculate_epf
        r = calculate_epf(25000)
        # Employee EPF is 12% of actual salary (no ceiling for employee)
        assert r["employee_epf_inr"] == pytest.approx(3000.0)

    def test_annual_is_12x_monthly(self):
        from app.services.labour_compliance_service import calculate_epf
        r = calculate_epf(10000)
        assert r["total_annual_inr"] == pytest.approx(r["total_monthly_inr"] * 12, abs=1)

    def test_exact_at_ceiling(self):
        from app.services.labour_compliance_service import calculate_epf
        r = calculate_epf(15000)
        assert r["wage_ceiling_applied"] is False  # exactly at ceiling, not above
        assert r["employee_epf_inr"] == pytest.approx(1800.0)


# ═════════════════════════════════════════════════════════════════════════════
# 2. ESIC Calculator — pure functions
# ═════════════════════════════════════════════════════════════════════════════

class TestESICCalculator:
    def test_eligible_below_ceiling(self):
        from app.services.labour_compliance_service import calculate_esic
        r = calculate_esic(18000)
        assert r["applicable"] is True
        assert r["employee_esic_inr"] == pytest.approx(135.0)    # 0.75%
        assert r["employer_esic_inr"] == pytest.approx(585.0)    # 3.25%
        assert r["total_monthly_inr"] == pytest.approx(720.0)

    def test_not_eligible_above_ceiling(self):
        from app.services.labour_compliance_service import calculate_esic
        r = calculate_esic(25000)
        assert r["applicable"] is False
        assert "reason" in r

    def test_exactly_at_ceiling_eligible(self):
        from app.services.labour_compliance_service import calculate_esic
        r = calculate_esic(21000)
        assert r["applicable"] is True

    def test_just_above_ceiling_not_eligible(self):
        from app.services.labour_compliance_service import calculate_esic
        r = calculate_esic(21001)
        assert r["applicable"] is False

    def test_annual_is_12x_monthly(self):
        from app.services.labour_compliance_service import calculate_esic
        r = calculate_esic(15000)
        assert r["total_annual_inr"] == pytest.approx(r["total_monthly_inr"] * 12, abs=1)


# ═════════════════════════════════════════════════════════════════════════════
# 3. Full social security — pure function
# ═════════════════════════════════════════════════════════════════════════════

class TestFullSocialSecurity:
    def test_combined_calculation(self):
        from app.services.labour_compliance_service import calculate_full_social_security
        r = calculate_full_social_security(12000, 18000)
        assert "epf"  in r
        assert "esic" in r
        assert r["epf"]["applicable"]  is True
        assert r["esic"]["applicable"] is True
        assert r["total_compliance_cost"] > 0

    def test_esic_not_applicable_above_ceiling(self):
        from app.services.labour_compliance_service import calculate_full_social_security
        r = calculate_full_social_security(30000, 35000)
        assert r["esic"]["applicable"] is False
        # Total cost still includes EPF
        assert r["total_compliance_cost"] > 0

    def test_take_home_reduction_equals_employee_deductions(self):
        from app.services.labour_compliance_service import calculate_full_social_security
        r = calculate_full_social_security(12000, 15000)
        expected = r["epf"]["employee_epf_inr"] + r["esic"].get("employee_esic_inr", 0)
        assert r["take_home_reduction"] == pytest.approx(expected, abs=0.1)


# ═════════════════════════════════════════════════════════════════════════════
# 4. Gratuity — pure function
# ═════════════════════════════════════════════════════════════════════════════

class TestGratuity:
    def test_eligible_5_years(self):
        from app.services.labour_compliance_service import calculate_gratuity
        r = calculate_gratuity(30000, 5)
        assert r["eligible"] is True
        expected = (15 / 26) * 30000 * 5
        assert r["gratuity_inr"] == pytest.approx(expected, abs=1)

    def test_ineligible_below_5_years(self):
        from app.services.labour_compliance_service import calculate_gratuity
        r = calculate_gratuity(30000, 4.9)
        assert r["eligible"] is False
        assert "reason" in r

    def test_cap_applied_at_20_lakh(self):
        from app.services.labour_compliance_service import calculate_gratuity
        r = calculate_gratuity(100000, 40)
        assert r["cap_applied"] is True
        assert r["gratuity_inr"] == 2_000_000

    def test_partial_year_ignored(self):
        from app.services.labour_compliance_service import calculate_gratuity
        # 7.9 years → 7 completed years used
        r7_9 = calculate_gratuity(30000, 7.9)
        r7_0 = calculate_gratuity(30000, 7.0)
        assert r7_9["gratuity_inr"] == r7_0["gratuity_inr"]

    def test_formula_string_present(self):
        from app.services.labour_compliance_service import calculate_gratuity
        r = calculate_gratuity(25000, 6)
        assert "formula" in r
        assert "15/26" in r["formula"]


# ═════════════════════════════════════════════════════════════════════════════
# 5. Working hours — pure functions
# ═════════════════════════════════════════════════════════════════════════════

class TestShiftHoursChecker:
    def _shift(self, hours: float, break_h: float = 0.5):
        start = datetime(2026, 6, 1, 9, 0)
        end   = start + timedelta(hours=hours + break_h)
        return start, end

    def test_normal_8h_shift_no_violation(self):
        from app.services.labour_compliance_service import check_shift_hours
        start, end = self._shift(8)
        r = check_shift_hours(start, end)
        assert r["compliant"] is True
        assert r["actual_hours"] == pytest.approx(8.0)
        assert r["violations"] == []

    def test_overtime_starts_after_8h(self):
        from app.services.labour_compliance_service import check_shift_hours
        start, end = self._shift(9)
        r = check_shift_hours(start, end)
        assert r["is_overtime"] is True
        assert r["overtime_hours"] == pytest.approx(1.0)

    def test_violation_at_10h(self):
        from app.services.labour_compliance_service import check_shift_hours
        start, end = self._shift(10)
        r = check_shift_hours(start, end)
        assert r["compliant"] is False
        types = [v["type"] for v in r["violations"]]
        assert "EXCESS_DAILY_HOURS" in types

    def test_overtime_pay_calculated(self):
        from app.services.labour_compliance_service import check_shift_hours
        start, end = self._shift(10)
        r = check_shift_hours(start, end, hourly_rate_inr=100)
        assert r["overtime_inr"] > 0
        # 2h OT at 2× = 2 × 100 × 2 = 400
        assert r["overtime_inr"] == pytest.approx(400.0)

    def test_night_shift_detected(self):
        from app.services.labour_compliance_service import check_shift_hours
        start = datetime(2026, 6, 1, 22, 0)
        end   = datetime(2026, 6, 2, 6, 30)
        r = check_shift_hours(start, end)
        assert r["is_night_shift"] is True


class TestRestPeriodChecker:
    def test_12h_rest_compliant(self):
        from app.services.labour_compliance_service import check_rest_period
        prev_end   = datetime(2026, 6, 1, 20, 0)
        curr_start = datetime(2026, 6, 2, 8, 0)   # 12h gap
        r = check_rest_period(prev_end, curr_start)
        assert r["compliant"] is True
        assert r["rest_hours"] == pytest.approx(12.0)

    def test_8h_rest_violation(self):
        from app.services.labour_compliance_service import check_rest_period
        prev_end   = datetime(2026, 6, 1, 22, 0)
        curr_start = datetime(2026, 6, 2, 6, 0)   # only 8h gap
        r = check_rest_period(prev_end, curr_start)
        assert r["compliant"] is False
        assert r["rest_hours"] == pytest.approx(8.0)
        assert r["violation"]["type"] == "INSUFFICIENT_REST"
        assert r["violation"]["severity"] == "HIGH"

    def test_exactly_12h_is_compliant(self):
        from app.services.labour_compliance_service import check_rest_period
        prev_end   = datetime(2026, 6, 1, 18, 0)
        curr_start = datetime(2026, 6, 2, 6, 0)   # exactly 12h
        r = check_rest_period(prev_end, curr_start)
        assert r["compliant"] is True


class TestWeeklyHoursChecker:
    def test_48h_week_compliant(self):
        from app.services.labour_compliance_service import check_weekly_hours
        r = check_weekly_hours(48.0)
        assert r["compliant"] is True
        assert r["overtime_hours"] == 0

    def test_50h_week_violation(self):
        from app.services.labour_compliance_service import check_weekly_hours
        r = check_weekly_hours(50.0)
        assert r["compliant"] is False
        assert r["overtime_hours"] == pytest.approx(2.0)
        assert r["violation"]["type"] == "EXCESS_WEEKLY_HOURS"

    def test_40h_flagged_as_overtime(self):
        from app.services.labour_compliance_service import check_weekly_hours
        r = check_weekly_hours(42.0)
        assert r["is_overtime"] is True
        assert r["compliant"] is True  # 42h < 48h limit — compliant but flagged


class TestNightShiftCompliance:
    def test_male_worker_night_shift_ok(self):
        from app.services.labour_compliance_service import check_night_shift_compliance
        r = check_night_shift_compliance(is_female_worker=False)
        assert r["compliant"] is True

    def test_female_no_consent_violation(self):
        from app.services.labour_compliance_service import check_night_shift_compliance
        r = check_night_shift_compliance(is_female_worker=True, night_shift_consent=False)
        assert r["compliant"] is False
        types = [v["type"] for v in r["violations"]]
        assert "NIGHT_SHIFT_NO_CONSENT" in types

    def test_female_with_consent_no_transport_violation(self):
        from app.services.labour_compliance_service import check_night_shift_compliance
        r = check_night_shift_compliance(is_female_worker=True,
                                         night_shift_consent=True,
                                         transport_arranged=False)
        assert r["compliant"] is False
        types = [v["type"] for v in r["violations"]]
        assert "NIGHT_SHIFT_NO_TRANSPORT" in types

    def test_female_consent_and_transport_compliant(self):
        from app.services.labour_compliance_service import check_night_shift_compliance
        r = check_night_shift_compliance(is_female_worker=True,
                                         night_shift_consent=True,
                                         transport_arranged=True)
        assert r["compliant"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 6. Salary compliance — with mocked DB
# ═════════════════════════════════════════════════════════════════════════════

_MH_UNSKILLED_ROW = [{
    "state_code": "MH", "state_name": "Maharashtra", "zone": "A",
    "skill_category": "UNSKILLED", "industry": "HOSPITALITY",
    "daily_wage_inr": 467, "monthly_wage_inr": 12144,
    "effective_from": "2024-01-01", "source": "MH Gazette 2024", "is_current": True,
}]


class TestSalaryCompliance:
    def _make_sb(self, wage_row=None, fallback_row=None):
        """Supabase mock that returns wage_row on first .execute(), fallback_row on second."""
        sb = MagicMock()
        results = [wage_row if wage_row is not None else [],
                   fallback_row if fallback_row is not None else []]
        call_idx = [0]

        def table_side(name):
            chain = MagicMock()
            for m in ("select", "eq", "limit", "order"):
                getattr(chain, m).return_value = chain
            res = MagicMock()
            res.data = results[call_idx[0] % len(results)]
            call_idx[0] += 1
            chain.execute.return_value = res
            return chain

        sb.table.side_effect = table_side
        return sb

    def test_compliant_salary(self):
        from app.services.labour_compliance_service import check_salary_compliance
        sb = self._make_sb(_MH_UNSKILLED_ROW)
        r = check_salary_compliance(sb, "MH", "UNSKILLED", 15000, "HOSPITALITY")
        assert r["checked"] is True
        assert r["state_compliant"] is True
        assert r["shortfall_inr"] == 0

    def test_below_minimum_wage(self):
        from app.services.labour_compliance_service import check_salary_compliance
        sb = self._make_sb(_MH_UNSKILLED_ROW)
        r = check_salary_compliance(sb, "MH", "UNSKILLED", 10000, "HOSPITALITY")
        assert r["state_compliant"] is False
        assert r["shortfall_inr"] == pytest.approx(2144.0)

    def test_national_floor_checked(self):
        from app.services.labour_compliance_service import check_salary_compliance
        # Offer 100 per month — below even the national floor
        sb = self._make_sb(_MH_UNSKILLED_ROW)
        r = check_salary_compliance(sb, "MH", "UNSKILLED", 100, "HOSPITALITY")
        assert r["floor_compliant"] is False
        assert r["compliant"] is False

    def test_no_wage_data_returns_unchecked(self):
        from app.services.labour_compliance_service import check_salary_compliance
        sb = self._make_sb([], [])   # no rows for either industry or ALL
        r = check_salary_compliance(sb, "XX", "UNSKILLED", 15000, "HOSPITALITY")
        assert r["checked"] is False


# ═════════════════════════════════════════════════════════════════════════════
# 7. API endpoint tests — minimum wages
# ═════════════════════════════════════════════════════════════════════════════

_WAGE_ROWS = [
    {"state_code": "MH", "state_name": "Maharashtra", "zone": "A",
     "skill_category": "UNSKILLED", "industry": "HOSPITALITY",
     "daily_wage_inr": 467, "monthly_wage_inr": 12144,
     "effective_from": "2024-01-01", "source": "MH Gazette 2024"},
]


class TestWageEndpoints:
    def test_list_wages_happy(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",              _ORG_ROW)
        sb.configure("india_minimum_wages", _WAGE_ROWS)

        resp = client.get("/api/v1/labour/minimum-wages?state_code=MH")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert resp.json()[0]["state_code"] == "MH"

    def test_list_wages_not_found(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",              _ORG_ROW)
        sb.configure("india_minimum_wages", [])   # empty

        resp = client.get("/api/v1/labour/minimum-wages?state_code=XX")
        assert resp.status_code == 404

    def test_wage_lookup_happy(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",              _ORG_ROW)
        sb.configure("india_minimum_wages", _WAGE_ROWS)

        resp = client.post("/api/v1/labour/minimum-wages/lookup", json={
            "state_code": "MH", "skill_category": "UNSKILLED", "industry": "HOSPITALITY",
        })
        assert resp.status_code == 200
        assert resp.json()["monthly_wage_inr"] == 12144

    def test_wage_lookup_invalid_skill(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.post("/api/v1/labour/minimum-wages/lookup", json={
            "state_code": "MH", "skill_category": "EXPERT",
        })
        assert resp.status_code == 422

    def test_salary_compliance_check_endpoint(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",               _ORG_ROW)
        sb.configure("india_minimum_wages", _WAGE_ROWS)   # primary industry match
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/labour/minimum-wages/check", json={
            "state_code":          "MH",
            "skill_category":      "UNSKILLED",
            "offered_monthly_inr": 15000,
            "industry":            "HOSPITALITY",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["checked"] is True
        assert body["state_compliant"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 8. API endpoint tests — working hours
# ═════════════════════════════════════════════════════════════════════════════

class TestWorkingHoursEndpoints:
    def test_check_shift_no_violation(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        # 09:00–18:00 = 9h total, minus 0.5h break = 8.5h actual (within 9h daily max)
        resp = client.post("/api/v1/labour/working-hours/check", json={
            "shift_start": "2026-06-01T09:00:00",
            "shift_end":   "2026-06-01T18:00:00",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["compliant"] is True
        assert body["actual_hours"] == pytest.approx(8.5)

    def test_check_shift_violation(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/labour/working-hours/check", json={
            "shift_start": "2026-06-01T08:00:00",
            "shift_end":   "2026-06-01T20:00:00",  # 11.5h actual → violation
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["compliant"] is False
        assert any(v["type"] == "EXCESS_DAILY_HOURS" for v in body["violations"])

    def test_check_shift_invalid_times(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)

        resp = client.post("/api/v1/labour/working-hours/check", json={
            "shift_start": "2026-06-01T18:00:00",
            "shift_end":   "2026-06-01T08:00:00",  # end before start
        })
        assert resp.status_code == 422

    def test_check_rest_compliant(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)

        resp = client.post("/api/v1/labour/working-hours/check-rest", json={
            "previous_shift_end":  "2026-06-01T22:00:00",
            "current_shift_start": "2026-06-02T10:00:00",  # 12h gap
        })
        assert resp.status_code == 200
        assert resp.json()["compliant"] is True
        assert resp.json()["rest_hours"] == pytest.approx(12.0)

    def test_check_rest_violation(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)

        resp = client.post("/api/v1/labour/working-hours/check-rest", json={
            "previous_shift_end":  "2026-06-01T22:00:00",
            "current_shift_start": "2026-06-02T06:00:00",  # only 8h
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["compliant"] is False
        assert body["violation"]["type"] == "INSUFFICIENT_REST"

    def test_check_weekly_hours_over_limit(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)

        resp = client.post("/api/v1/labour/working-hours/check-weekly", json={
            "weekly_actual_hours": 52.0,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["compliant"] is False
        assert body["overtime_hours"] == pytest.approx(4.0)

    def test_log_shift_persisted(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                      _ORG_ROW)
        sb.configure("working_hours_compliance",   [{"id": "wh-rec-1234-abcd"}])
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/labour/working-hours/log", json={
            "shift_start":       "2026-06-01T09:00:00",
            "shift_end":         "2026-06-01T18:00:00",
            "candidate_id":      CANDIDATE_ID,
            "state_code":        "MH",
            "hourly_rate_inr":   150.0,
            "weekly_hours_so_far": 32.0,
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["record_id"] == "wh-rec-1234-abcd"
        assert body["compliant"] is True

    def test_log_rest_persisted(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",         _ORG_ROW)
        sb.configure("shift_rest_log", [{"id": "rest-rec-abcd-1234"}])
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/labour/working-hours/log-rest", json={
            "previous_shift_end":  "2026-06-01T20:00:00",
            "current_shift_start": "2026-06-02T09:00:00",  # 13h rest
            "candidate_id":        CANDIDATE_ID,
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["compliant"] is True
        assert body["record_id"] == "rest-rec-abcd-1234"


# ═════════════════════════════════════════════════════════════════════════════
# 9. API endpoint tests — EPF / ESIC
# ═════════════════════════════════════════════════════════════════════════════

class TestEPFESICEndpoints:
    def test_epf_calculate_endpoint(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/labour/epf-esic/calculate", json={
            "monthly_basic_da_inr": 12000,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["applicable"] is True
        assert body["employee_epf_inr"] == pytest.approx(1440.0)

    def test_esic_calculate_endpoint(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/labour/epf-esic/esic-calculate", json={
            "monthly_gross_inr": 18000,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["applicable"] is True
        assert body["employee_esic_inr"] == pytest.approx(135.0)

    def test_esic_not_applicable_above_ceiling(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/labour/epf-esic/esic-calculate", json={
            "monthly_gross_inr": 30000,
        })
        assert resp.status_code == 200
        assert resp.json()["applicable"] is False

    def test_full_social_security_endpoint(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/labour/epf-esic/full", json={
            "monthly_basic_da_inr": 12000,
            "monthly_gross_inr":    18000,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "epf"  in body
        assert "esic" in body
        assert body["total_compliance_cost"] > 0

    def test_thresholds_endpoint(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)

        resp = client.get("/api/v1/labour/epf-esic/thresholds")
        assert resp.status_code == 200
        body = resp.json()
        assert body["epf"]["wage_ceiling_inr"]  == 15000
        assert body["esic"]["wage_ceiling_inr"] == 21000
        assert body["working_hours"]["min_rest_hours"] == 12

    def test_zero_salary_rejected(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.post("/api/v1/labour/epf-esic/calculate", json={
            "monthly_basic_da_inr": 0,
        })
        assert resp.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# 10. Gratuity endpoint
# ═════════════════════════════════════════════════════════════════════════════

class TestGratuityEndpoint:
    def test_gratuity_eligible(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/labour/gratuity/calculate", json={
            "monthly_last_drawn_inr": 30000,
            "years_of_service":       7,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["eligible"] is True
        assert body["gratuity_inr"] == pytest.approx((15/26) * 30000 * 7, abs=1)

    def test_gratuity_ineligible(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/labour/gratuity/calculate", json={
            "monthly_last_drawn_inr": 30000,
            "years_of_service":       3,
        })
        assert resp.status_code == 200
        assert resp.json()["eligible"] is False

    def test_negative_years_rejected(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.post("/api/v1/labour/gratuity/calculate", json={
            "monthly_last_drawn_inr": 30000,
            "years_of_service":       -1,
        })
        assert resp.status_code == 422
