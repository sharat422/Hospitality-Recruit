"""
Tests for Indian Diversity Reporting.

Coverage:
  1. Pure service — blind screening, gender breakdown, PwD metrics, pay gap
  2. Religion prohibition — never collected
  3. Statutory gate — SC/ST/OBC only when org flag set
  4. Data collection validation
  5. API endpoints — collect, dashboard, gender-breakdown, pwd-metrics, pay-gap
  6. API endpoints — blind-screening single + batch, settings
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

# ─── IDs ─────────────────────────────────────────────────────────────────────
ORG_ID       = "aaaa1111-bbbb-cccc-dddd-eeeeffff0000"
CANDIDATE_ID = "bbbb2222-cccc-dddd-eeee-ffff00001111"

_ORG_ROW   = [{"org_id": ORG_ID}]
_AUDIT_ROW = []


# ═════════════════════════════════════════════════════════════════════════════
# 1. Blind screening — pure function
# ═════════════════════════════════════════════════════════════════════════════

_FULL_CANDIDATE = {
    "id":           CANDIDATE_ID,
    "first_name":   "Priya",
    "last_name":    "Sharma",
    "email":        "priya.sharma@gmail.com",
    "phone":        "+919876543210",
    "location":     "Mumbai, Maharashtra",
    "city":         "Mumbai",
    "state":        "Maharashtra",
    "hometown":     "Pune",
    "profile_photo":"https://cdn.example.com/photos/abc.jpg",
    "pipeline_stage":"screening",
    "parsed_skills":["hospitality", "F&B", "customer service"],
    "years_experience": 3,
}


class TestBlindScreening:
    def test_name_is_redacted(self):
        from app.services.diversity_service import apply_blind_screening
        b = apply_blind_screening(_FULL_CANDIDATE)
        assert b["first_name"] == "Candidate"
        assert "Priya" not in b["first_name"]
        assert "Sharma" not in b.get("last_name", "")

    def test_code_appended_to_last_name(self):
        from app.services.diversity_service import apply_blind_screening
        b = apply_blind_screening(_FULL_CANDIDATE)
        assert b["last_name"].startswith("#")

    def test_email_is_hashed(self):
        from app.services.diversity_service import apply_blind_screening
        b = apply_blind_screening(_FULL_CANDIDATE)
        assert "priya.sharma" not in b["email"]
        assert "blind-" in b["email"]

    def test_phone_is_none(self):
        from app.services.diversity_service import apply_blind_screening
        b = apply_blind_screening(_FULL_CANDIDATE)
        assert b["phone"] is None

    def test_location_is_none(self):
        from app.services.diversity_service import apply_blind_screening
        b = apply_blind_screening(_FULL_CANDIDATE)
        assert b["location"] is None
        assert b["city"]     is None
        assert b["state"]    is None
        assert b["hometown"] is None

    def test_photo_is_none(self):
        from app.services.diversity_service import apply_blind_screening
        b = apply_blind_screening(_FULL_CANDIDATE)
        assert b["profile_photo"] is None

    def test_skills_preserved(self):
        from app.services.diversity_service import apply_blind_screening
        b = apply_blind_screening(_FULL_CANDIDATE)
        assert b["parsed_skills"] == _FULL_CANDIDATE["parsed_skills"]

    def test_stage_preserved(self):
        from app.services.diversity_service import apply_blind_screening
        b = apply_blind_screening(_FULL_CANDIDATE)
        assert b["pipeline_stage"] == "screening"

    def test_blind_flag_added(self):
        from app.services.diversity_service import apply_blind_screening
        b = apply_blind_screening(_FULL_CANDIDATE)
        assert b["_blind_screening"] is True

    def test_does_not_mutate_original(self):
        from app.services.diversity_service import apply_blind_screening
        original = dict(_FULL_CANDIDATE)
        apply_blind_screening(_FULL_CANDIDATE)
        assert _FULL_CANDIDATE == original  # original unchanged

    def test_batch_blinds_all(self):
        from app.services.diversity_service import blind_screen_batch
        c2 = {**_FULL_CANDIDATE, "id": "bbbbcccc-0000-0000-0000-000000000001",
              "first_name": "Ravi", "email": "ravi@example.com"}
        results = blind_screen_batch([_FULL_CANDIDATE, c2])
        assert len(results) == 2
        for r in results:
            assert r["_blind_screening"] is True
            assert "Priya" not in r["first_name"]
            assert "Ravi"  not in r["first_name"]

    def test_blind_codes_differ_for_different_candidates(self):
        from app.services.diversity_service import apply_blind_screening
        c1 = {**_FULL_CANDIDATE, "id": "aaaa0000-1111-2222-3333-444455556666"}
        c2 = {**_FULL_CANDIDATE, "id": "bbbb1111-2222-3333-4444-555566667777"}
        b1 = apply_blind_screening(c1)
        b2 = apply_blind_screening(c2)
        assert b1["_blind_code"] != b2["_blind_code"]


# ═════════════════════════════════════════════════════════════════════════════
# 2. Religion — never collected (pure validation)
# ═════════════════════════════════════════════════════════════════════════════

class TestReligionProhibition:
    def test_collect_request_has_no_religion_field(self):
        """Pydantic model must have no religion field."""
        from app.routers.diversity import DiversityCollectRequest
        fields = DiversityCollectRequest.model_fields
        assert "religion" not in fields, "religion field must not exist in DiversityCollectRequest"

    def test_collect_request_with_religion_extra_ignored(self):
        """Pydantic v2 ignores extra fields — religion silently dropped."""
        from app.routers.diversity import DiversityCollectRequest
        req = DiversityCollectRequest(
            candidate_id="cand-1",
            dpdp_consent_id="consent-1",
            gender="FEMALE",
            religion="HINDU",   # extra field — must be ignored
        )
        assert not hasattr(req, "religion")


# ═════════════════════════════════════════════════════════════════════════════
# 3. Statutory gate — SC/ST/OBC/EWS collection
# ═════════════════════════════════════════════════════════════════════════════

class TestStatutoryGate:
    def _make_sb(self, statutory: bool):
        sb = MagicMock()
        chain = MagicMock()
        for m in ("select", "eq", "limit", "insert", "update", "order"):
            getattr(chain, m).return_value = chain
        res = MagicMock()
        res.data = [{"statutory_reporting_required": statutory}]
        chain.execute.return_value = res
        sb.table.return_value = chain
        return sb

    def test_social_category_blocked_without_statutory(self):
        from app.services.diversity_service import collect_diversity_data
        sb = self._make_sb(statutory=False)
        with pytest.raises(ValueError, match="statutory_reporting_required"):
            collect_diversity_data(
                sb, ORG_ID, CANDIDATE_ID,
                social_category="SC",
                dpdp_consent_id="consent-1",
            )

    def test_social_category_allowed_with_statutory(self):
        from app.services.diversity_service import collect_diversity_data

        # Mock: first call = org lookup (statutory=True), second = insert
        sb = MagicMock()
        calls = [
            [{"statutory_reporting_required": True}],    # organizations
            [{"id": "div-001", "social_category": "SC"}],  # insert
            [{"id": CANDIDATE_ID}],                        # candidates update
        ]
        call_idx = [0]

        def table_side(name):
            chain = MagicMock()
            for m in ("select","eq","limit","insert","update","order"):
                getattr(chain, m).return_value = chain
            res = MagicMock()
            res.data = calls[call_idx[0] % len(calls)]
            call_idx[0] += 1
            chain.execute.return_value = res
            return chain

        sb.table.side_effect = table_side
        rec = collect_diversity_data(
            sb, ORG_ID, CANDIDATE_ID,
            social_category="SC",
            dpdp_consent_id="consent-1",
        )
        assert rec["social_category"] == "SC"

    def test_gender_allowed_without_statutory(self):
        """Gender + PwD never require statutory gate."""
        from app.services.diversity_service import collect_diversity_data

        sb = MagicMock()
        calls = [
            [{"id": "div-001", "gender": "FEMALE"}],  # insert
            [{"id": CANDIDATE_ID}],                    # candidate update
        ]
        call_idx = [0]

        def table_side(name):
            chain = MagicMock()
            for m in ("select","eq","limit","insert","update","order"):
                getattr(chain, m).return_value = chain
            res = MagicMock()
            res.data = calls[call_idx[0] % len(calls)]
            call_idx[0] += 1
            chain.execute.return_value = res
            return chain

        sb.table.side_effect = table_side
        rec = collect_diversity_data(
            sb, ORG_ID, CANDIDATE_ID,
            gender="FEMALE",
            dpdp_consent_id="consent-1",
        )
        assert rec["gender"] == "FEMALE"


# ═════════════════════════════════════════════════════════════════════════════
# 4. Data collection — validation
# ═════════════════════════════════════════════════════════════════════════════

class TestCollectionValidation:
    def test_invalid_gender_raises(self):
        from app.routers.diversity import DiversityCollectRequest
        with pytest.raises(ValueError):
            DiversityCollectRequest(
                candidate_id="c1", dpdp_consent_id="con1",
                gender="UNKNOWN_GENDER"
            )

    def test_invalid_social_category_raises(self):
        from app.routers.diversity import DiversityCollectRequest
        with pytest.raises(ValueError):
            DiversityCollectRequest(
                candidate_id="c1", dpdp_consent_id="con1",
                social_category="BRAHMIN"   # not a valid RPWD/EEO category
            )

    def test_pwd_category_normalised_to_upper(self):
        from app.routers.diversity import DiversityCollectRequest
        req = DiversityCollectRequest(
            candidate_id="c1", dpdp_consent_id="con1",
            pwd_category="locomotor"
        )
        assert req.pwd_category == "LOCOMOTOR"

    def test_disability_pct_out_of_range_raises(self):
        from app.routers.diversity import DiversityCollectRequest
        with pytest.raises(ValueError):
            DiversityCollectRequest(
                candidate_id="c1", dpdp_consent_id="con1",
                pwd_disability_pct=150
            )

    def test_missing_dpdp_consent_raises_in_service(self):
        from app.services.diversity_service import collect_diversity_data
        sb = MagicMock()
        with pytest.raises(ValueError, match="dpdp_consent_id"):
            collect_diversity_data(sb, ORG_ID, CANDIDATE_ID, gender="MALE",
                                   dpdp_consent_id=None)


# ═════════════════════════════════════════════════════════════════════════════
# 5. Pure metric computation
# ═════════════════════════════════════════════════════════════════════════════

_CANDIDATES = [
    # MALE — 3 applied, 2 hired
    {"id": "c1", "gender": "MALE",   "is_pwd": False, "offered_salary_inr": 30000, "pipeline_stage": "hired"},
    {"id": "c2", "gender": "MALE",   "is_pwd": False, "offered_salary_inr": 32000, "pipeline_stage": "hired"},
    {"id": "c3", "gender": "MALE",   "is_pwd": False, "offered_salary_inr": 28000, "pipeline_stage": "screening"},
    # FEMALE — 3 applied, 1 hired
    {"id": "c4", "gender": "FEMALE", "is_pwd": False, "offered_salary_inr": 25000, "pipeline_stage": "hired"},
    {"id": "c5", "gender": "FEMALE", "is_pwd": True,  "offered_salary_inr": 24000, "pipeline_stage": "screening"},
    {"id": "c6", "gender": "FEMALE", "is_pwd": False, "offered_salary_inr": 26000, "pipeline_stage": "applied"},
    # PREFER_NOT_TO_SAY — 1 applied
    {"id": "c7", "gender": "PREFER_NOT_TO_SAY", "is_pwd": True, "offered_salary_inr": None, "pipeline_stage": "applied"},
]


class TestGenderBreakdown:
    def test_total_applications(self):
        from app.services.diversity_service import compute_gender_breakdown
        r = compute_gender_breakdown(_CANDIDATES)
        assert r["total_applications"] == 7

    def test_total_hires(self):
        from app.services.diversity_service import compute_gender_breakdown
        r = compute_gender_breakdown(_CANDIDATES)
        assert r["total_hires"] == 3   # c1, c2, c4

    def test_applications_by_gender(self):
        from app.services.diversity_service import compute_gender_breakdown
        r = compute_gender_breakdown(_CANDIDATES)
        assert r["applications_by_gender"]["MALE"]   == 3
        assert r["applications_by_gender"]["FEMALE"] == 3

    def test_hires_by_gender(self):
        from app.services.diversity_service import compute_gender_breakdown
        r = compute_gender_breakdown(_CANDIDATES)
        assert r["hires_by_gender"]["MALE"]   == 2
        assert r["hires_by_gender"]["FEMALE"] == 1

    def test_hire_rate_male(self):
        from app.services.diversity_service import compute_gender_breakdown
        r = compute_gender_breakdown(_CANDIDATES)
        assert r["hire_rate_by_gender"]["MALE"] == pytest.approx(66.7, abs=0.1)

    def test_empty_candidates(self):
        from app.services.diversity_service import compute_gender_breakdown
        r = compute_gender_breakdown([])
        assert r["total_applications"] == 0
        assert r["total_hires"] == 0


class TestPwDMetrics:
    def test_pwd_applications(self):
        from app.services.diversity_service import compute_pwd_metrics
        r = compute_pwd_metrics(_CANDIDATES)
        assert r["pwd_applications"] == 2   # c5, c7

    def test_pwd_hires(self):
        from app.services.diversity_service import compute_pwd_metrics
        r = compute_pwd_metrics(_CANDIDATES)
        assert r["pwd_hires"] == 0   # neither PwD candidate was hired

    def test_pwd_pct(self):
        from app.services.diversity_service import compute_pwd_metrics
        r = compute_pwd_metrics(_CANDIDATES)
        assert r["pwd_pct_of_applications"] == pytest.approx(28.6, abs=0.1)


class TestGenderPayGap:
    def test_insufficient_below_5(self):
        from app.services.diversity_service import compute_gender_pay_gap
        r = compute_gender_pay_gap(_CANDIDATES)  # only 2-3 per gender
        assert r["insufficient_data"] is True

    def test_sufficient_data_computes_gap(self):
        from app.services.diversity_service import compute_gender_pay_gap
        # Build 5+ per gender
        males   = [{"gender": "MALE",   "offered_salary_inr": 30000 + i * 1000, "pipeline_stage": "applied"} for i in range(6)]
        females = [{"gender": "FEMALE", "offered_salary_inr": 25000 + i * 1000, "pipeline_stage": "applied"} for i in range(6)]
        r = compute_gender_pay_gap(males + females)
        assert r["insufficient_data"] is False
        assert r["median_pay_gap_pct"] > 0   # males earn more
        assert r["direction"] == "men_earn_more"
        assert r["male_sample_size"] == 6
        assert r["female_sample_size"] == 6

    def test_no_salary_data(self):
        from app.services.diversity_service import compute_gender_pay_gap
        no_salary = [{"gender": "MALE", "offered_salary_inr": None, "pipeline_stage": "applied"} for _ in range(5)]
        r = compute_gender_pay_gap(no_salary)
        assert r["insufficient_data"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 6. API endpoints
# ═════════════════════════════════════════════════════════════════════════════

_CAND_ROWS = [
    {"id": "c1", "gender": "MALE",   "is_pwd": False, "offered_salary_inr": None, "pipeline_stage": "applied", "created_at": "2026-05-01"},
    {"id": "c2", "gender": "FEMALE", "is_pwd": True,  "offered_salary_inr": None, "pipeline_stage": "hired",   "created_at": "2026-05-02"},
]

_DIVERSITY_INSERT = [{"id": "div-001", "gender": "FEMALE", "is_pwd": False, "candidate_id": CANDIDATE_ID}]
_ORG_SETTINGS     = [{
    "id": ORG_ID, "name": "Test Hotel",
    "statutory_reporting_required": False,
    "statutory_employee_threshold": 500,
    "statutory_reporting_law": None,
}]


class TestDiversityEndpoints:
    def test_collect_happy(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                _ORG_ROW)
        # statutory lookup in collect_diversity_data
        sb.configure("organizations",        [{"statutory_reporting_required": False}])
        sb.configure("india_diversity_data", _DIVERSITY_INSERT)
        sb.configure("candidates",           [{"id": CANDIDATE_ID}])
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/diversity/collect", json={
            "candidate_id":   CANDIDATE_ID,
            "dpdp_consent_id": "consent-abc",
            "gender":         "FEMALE",
            "is_pwd":         False,
        })
        assert resp.status_code == 201
        assert resp.json()["gender"] == "FEMALE"

    def test_collect_invalid_gender_422(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.post("/api/v1/diversity/collect", json={
            "candidate_id":   CANDIDATE_ID,
            "dpdp_consent_id": "consent-abc",
            "gender":         "UNKNOWN",
        })
        assert resp.status_code == 422

    def test_collect_social_category_without_statutory_400(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",         _ORG_ROW)
        sb.configure("organizations", [{"statutory_reporting_required": False}])

        resp = client.post("/api/v1/diversity/collect", json={
            "candidate_id":   CANDIDATE_ID,
            "dpdp_consent_id":"consent-abc",
            "social_category":"SC",
        })
        assert resp.status_code == 400
        assert "statutory" in resp.json()["detail"].lower()

    def test_collect_missing_consent_422(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.post("/api/v1/diversity/collect", json={
            "candidate_id": CANDIDATE_ID,
            "gender":       "MALE",
            # dpdp_consent_id intentionally absent → 422
        })
        assert resp.status_code == 422

    def test_gender_breakdown_endpoint(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",      _ORG_ROW)
        sb.configure("candidates", _CAND_ROWS)

        resp = client.get("/api/v1/diversity/gender-breakdown")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_applications" in body
        assert "applications_by_gender" in body
        assert body["total_applications"] == 2

    def test_pwd_metrics_endpoint(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",      _ORG_ROW)
        sb.configure("candidates", _CAND_ROWS)

        resp = client.get("/api/v1/diversity/pwd-metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pwd_applications"] == 1
        assert body["total_applications"] == 2

    def test_pay_gap_insufficient_data(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",      _ORG_ROW)
        sb.configure("candidates", _CAND_ROWS)  # no salaries

        resp = client.get("/api/v1/diversity/pay-gap")
        assert resp.status_code == 200
        assert resp.json()["insufficient_data"] is True

    def test_dashboard_endpoint(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",            _ORG_ROW)
        sb.configure("candidates",       _CAND_ROWS)
        sb.configure("organizations",    _ORG_SETTINGS)   # statutory check

        resp = client.get("/api/v1/diversity/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert "gender_breakdown" in body
        assert "pwd_metrics" in body
        assert "gender_pay_gap" in body
        assert body["statutory_reporting"] is False

    def test_settings_get(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",         _ORG_ROW)
        sb.configure("organizations", _ORG_SETTINGS)

        resp = client.get("/api/v1/diversity/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["statutory_reporting_required"] is False
        assert body["social_category_collection_enabled"] is False
        assert "note" in body

    def test_settings_patch(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",         _ORG_ROW)
        sb.configure("organizations", [{"id": ORG_ID}])   # update result
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.patch("/api/v1/diversity/settings", json={
            "statutory_reporting_required": True,
            "statutory_reporting_law": "Factories Act 1948",
        })
        assert resp.status_code == 200
        assert resp.json()["statutory_reporting_required"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 7. Blind screening API endpoints
# ═════════════════════════════════════════════════════════════════════════════

_CAND_FULL = [{
    "id": CANDIDATE_ID, "org_id": ORG_ID,
    "first_name": "Priya", "last_name": "Sharma",
    "email": "priya@hotel.in", "phone": "+919876543210",
    "location": "Mumbai", "city": "Mumbai", "state": "MH",
    "pipeline_stage": "screening",
    "parsed_skills": ["hospitality"],
}]


class TestBlindScreeningEndpoints:
    def test_single_blind_screen(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",      _ORG_ROW)
        sb.configure("candidates", _CAND_FULL)

        resp = client.post(f"/api/v1/diversity/blind-screening/{CANDIDATE_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["_blind_screening"] is True
        assert "Priya" not in body["first_name"]
        assert body["phone"] is None
        assert body["location"] is None

    def test_blind_screen_not_found(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",      _ORG_ROW)
        sb.configure("candidates", [])   # not found

        resp = client.post(f"/api/v1/diversity/blind-screening/{CANDIDATE_ID}")
        assert resp.status_code == 404

    def test_batch_blind_screen(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",      _ORG_ROW)
        sb.configure("candidates", _CAND_FULL)

        resp = client.post("/api/v1/diversity/blind-screening/batch", json={
            "candidate_ids": [CANDIDATE_ID],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["blinded"][0]["_blind_screening"] is True
        assert "Priya" not in body["blinded"][0]["first_name"]
