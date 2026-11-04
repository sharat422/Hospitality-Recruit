"""
Tests for DPDP Act 2023 Privacy Centre implementation.

Coverage:
  1. Pure service helpers — token generation, WhatsApp message, legal retention
  2. Purpose definitions — all 7 codes present, required flag correct
  3. Single-consent enforcement — no bundling, required consent protection
  4. Erasure request + WhatsApp ack (mocked Twilio)
  5. API endpoints — JWT-authenticated recruiter surface
  6. API endpoints — token-authenticated candidate Privacy Centre
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

# ─── Fixed test IDs ───────────────────────────────────────────────────────────
ORG_ID       = "aaaa1111-bbbb-cccc-dddd-eeeeffff1111"
CANDIDATE_ID = "bbbbcccc-dddd-eeee-ffff-aaaa22223333"
REQUEST_ID   = "ccccdddd-eeee-ffff-aaaa-bbbb33334444"
SESSION_ID   = "ddddeeee-ffff-aaaa-bbbb-cccc44445555"

_ORG_ROW   = [{"org_id": ORG_ID}]
_AUDIT_ROW = []

VALID_TOKEN  = "valid-privacy-token-aabbccddeeff"

_SESSION_ROW = [{
    "id":           SESSION_ID,
    "candidate_id": CANDIDATE_ID,
    "token":        VALID_TOKEN,
    "expires_at":   (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
    "used_at":      None,
}]

_CAND_ORG_ROW = [{"org_id": ORG_ID}]


# ═════════════════════════════════════════════════════════════════════════════
# 1. Pure helpers
# ═════════════════════════════════════════════════════════════════════════════

class TestTokenGeneration:
    def test_token_is_32_chars(self):
        from app.services.dpdp_service import generate_privacy_token
        tok = generate_privacy_token()
        assert len(tok) >= 32

    def test_tokens_are_unique(self):
        from app.services.dpdp_service import generate_privacy_token
        tokens = {generate_privacy_token() for _ in range(100)}
        assert len(tokens) == 100   # all distinct


class TestWhatsAppMessage:
    def test_message_contains_request_id(self):
        from app.services.dpdp_service import build_whatsapp_erasure_ack
        msg = build_whatsapp_erasure_ack("Ravi Kumar", REQUEST_ID,
                                          "ERASURE", "2026-05-18T10:00:00",
                                          "2026-06-17T10:00:00")
        assert REQUEST_ID[:8].upper() in msg

    def test_message_contains_due_date(self):
        from app.services.dpdp_service import build_whatsapp_erasure_ack
        msg = build_whatsapp_erasure_ack("Priya", REQUEST_ID, "ACCESS",
                                          "2026-05-01", "2026-05-31")
        assert "2026-05-31" in msg

    def test_message_bilingual(self):
        from app.services.dpdp_service import build_whatsapp_erasure_ack
        msg = build_whatsapp_erasure_ack("Amit", REQUEST_ID, "ERASURE",
                                          "2026-05-01", "2026-05-31")
        # Must have both Hindi and English text
        assert "DPDP Act" in msg
        assert "Section 13" in msg
        assert "नमस्ते" in msg    # Hindi greeting

    def test_message_contains_org_name(self):
        from app.services.dpdp_service import build_whatsapp_erasure_ack
        msg = build_whatsapp_erasure_ack("Test", REQUEST_ID, "ERASURE",
                                          "2026-05-01", "2026-05-31",
                                          org_name="Grand Hotel HR")
        assert "Grand Hotel HR" in msg


class TestLegalRetention:
    def test_all_purposes_have_retention_info(self):
        from app.services.dpdp_service import check_legal_retention, PURPOSE_DEFINITIONS
        for code in PURPOSE_DEFINITIONS:
            result = check_legal_retention(code)
            assert result["found"] is True

    def test_recruitment_data_has_statutory_retention(self):
        from app.services.dpdp_service import check_legal_retention
        result = check_legal_retention("RECRUITMENT_DATA")
        assert "statutory_retention" in result
        # EPF, PAN, ESIC records must be kept 8 years
        assert len(result["statutory_retention"]) >= 1
        assert result["can_fully_erase"] is False   # statutory records exempt

    def test_marketing_fully_erasable(self):
        from app.services.dpdp_service import check_legal_retention
        result = check_legal_retention("MARKETING")
        assert result["can_fully_erase"] is True
        assert result["retention_years"] == 0   # erase on withdrawal

    def test_sensitive_data_may_have_medical_retention(self):
        from app.services.dpdp_service import check_legal_retention
        result = check_legal_retention("SENSITIVE_DATA")
        assert result["found"] is True
        assert "statutory_retention" in result


# ═════════════════════════════════════════════════════════════════════════════
# 2. Purpose definitions completeness
# ═════════════════════════════════════════════════════════════════════════════

class TestPurposeDefinitions:
    def test_all_7_purposes_exist(self):
        from app.services.dpdp_service import PURPOSE_DEFINITIONS
        expected = {
            "RECRUITMENT_DATA", "BACKGROUND_CHECK", "SENSITIVE_DATA",
            "MARKETING", "THIRD_PARTY_SHARE", "AI_PROFILING", "CROSS_BORDER",
        }
        assert set(PURPOSE_DEFINITIONS.keys()) == expected

    def test_only_recruitment_data_is_required(self):
        from app.services.dpdp_service import PURPOSE_DEFINITIONS
        required_codes = {k for k, v in PURPOSE_DEFINITIONS.items() if v["required"]}
        assert required_codes == {"RECRUITMENT_DATA"}

    def test_each_purpose_has_hindi_description(self):
        from app.services.dpdp_service import PURPOSE_DEFINITIONS
        for code, defn in PURPOSE_DEFINITIONS.items():
            assert defn.get("description_hi"), f"{code} missing Hindi description"

    def test_each_purpose_has_icon(self):
        from app.services.dpdp_service import PURPOSE_DEFINITIONS
        for code, defn in PURPOSE_DEFINITIONS.items():
            assert defn.get("icon"), f"{code} missing icon"


# ═════════════════════════════════════════════════════════════════════════════
# 3. No-bundling enforcement (single consent service)
# ═════════════════════════════════════════════════════════════════════════════

class TestNoBundledConsent:
    def _make_sb(self, insert_result=None):
        sb = MagicMock()
        chain = MagicMock()
        for m in ("select","eq","limit","order","insert"):
            getattr(chain, m).return_value = chain
        res = MagicMock()
        res.data = insert_result or [{"id": "rec-001", "purpose_code": "MARKETING",
                                      "consented": True, "consented_at": "2026-05-18T10:00:00",
                                      "consent_text_version": "v2.0"}]
        chain.execute.return_value = res
        sb.table.return_value = chain
        return sb

    def test_valid_single_consent_recorded(self):
        from app.services.dpdp_service import record_single_consent
        sb = self._make_sb()
        rec = record_single_consent(sb, ORG_ID, CANDIDATE_ID, "MARKETING", True)
        assert rec["purpose_code"] == "MARKETING"

    def test_invalid_purpose_raises(self):
        from app.services.dpdp_service import record_single_consent
        sb = self._make_sb()
        with pytest.raises(ValueError, match="Unknown purpose_code"):
            record_single_consent(sb, ORG_ID, CANDIDATE_ID, "BUNDLED_ALL", True)

    def test_cannot_withdraw_required_consent(self):
        from app.services.dpdp_service import record_single_consent
        sb = self._make_sb()
        with pytest.raises(ValueError, match="required"):
            record_single_consent(sb, ORG_ID, CANDIDATE_ID, "RECRUITMENT_DATA", False)

    def test_granting_required_consent_allowed(self):
        from app.services.dpdp_service import record_single_consent
        sb = self._make_sb([{"id": "rec-002", "purpose_code": "RECRUITMENT_DATA",
                              "consented": True, "consented_at": "2026-05-18T10:00:00",
                              "consent_text_version": "v2.0"}])
        rec = record_single_consent(sb, ORG_ID, CANDIDATE_ID, "RECRUITMENT_DATA", True)
        assert rec["consented"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 4. Erasure request + WhatsApp ack
# ═════════════════════════════════════════════════════════════════════════════

_ERASURE_ROW = [{
    "id": REQUEST_ID, "org_id": ORG_ID, "candidate_id": CANDIDATE_ID,
    "request_type": "ERASURE", "status": "PENDING",
    "requested_at": "2026-05-18T10:00:00",
    "response_due_at": "2026-06-17T10:00:00",
    "candidate_phone": "+919876543210",
}]


class TestErasureWithWhatsApp:
    def _make_sb(self):
        sb = MagicMock()
        chain = MagicMock()
        for m in ("select","eq","limit","order","insert","update"):
            getattr(chain, m).return_value = chain
        res = MagicMock()
        res.data = _ERASURE_ROW
        chain.execute.return_value = res
        sb.table.return_value = chain
        return sb

    def test_erasure_request_created(self):
        from app.services.dpdp_service import create_erasure_request_with_ack
        sb = self._make_sb()
        result = create_erasure_request_with_ack(
            sb, ORG_ID, CANDIDATE_ID, "ERASURE", "Test reason",
            candidate_phone="+919876543210",
            candidate_name="Ravi Kumar",
            twilio=None, whatsapp_from=None,
        )
        assert result["id"] == REQUEST_ID
        assert result["whatsapp_ack_sent"] is False  # twilio=None

    def test_whatsapp_sent_when_twilio_available(self):
        from app.services.dpdp_service import create_erasure_request_with_ack
        sb = self._make_sb()

        twilio_mock = MagicMock()
        twilio_mock.messages.create.return_value = MagicMock(sid="WA-SID-12345")

        result = create_erasure_request_with_ack(
            sb, ORG_ID, CANDIDATE_ID, "ERASURE", None,
            candidate_phone="+919876543210",
            candidate_name="Priya Singh",
            twilio=twilio_mock,
            whatsapp_from="+14155238886",
        )
        assert result["whatsapp_ack_sent"] is True
        assert result["whatsapp_sid"] == "WA-SID-12345"
        twilio_mock.messages.create.assert_called_once()

    def test_whatsapp_failure_does_not_raise(self):
        from app.services.dpdp_service import create_erasure_request_with_ack
        sb = self._make_sb()

        twilio_mock = MagicMock()
        twilio_mock.messages.create.side_effect = Exception("Twilio connection error")

        result = create_erasure_request_with_ack(
            sb, ORG_ID, CANDIDATE_ID, "ERASURE", None,
            candidate_phone="+919999988888",
            candidate_name="Amit Sharma",
            twilio=twilio_mock,
            whatsapp_from="+14155238886",
        )
        # Must not raise — WhatsApp ack is best-effort
        assert result["whatsapp_ack_sent"] is False

    def test_no_phone_no_whatsapp(self):
        from app.services.dpdp_service import create_erasure_request_with_ack
        sb = self._make_sb()

        twilio_mock = MagicMock()
        result = create_erasure_request_with_ack(
            sb, ORG_ID, CANDIDATE_ID, "ACCESS", None,
            candidate_phone=None,   # no phone → no WA
            twilio=twilio_mock,
            whatsapp_from="+14155238886",
        )
        assert result["whatsapp_ack_sent"] is False
        twilio_mock.messages.create.assert_not_called()


# ═════════════════════════════════════════════════════════════════════════════
# 5. Recruiter API endpoints (JWT auth)
# ═════════════════════════════════════════════════════════════════════════════

_CONSENT_INSERT = [{"id": "con-001", "purpose_code": "MARKETING",
                    "consented": True, "consented_at": "2026-05-18T10:00:00",
                    "consent_text_version": "v2.0"}]


class TestRecruiterEndpoints:
    def test_list_purposes_no_auth(self, client_as_admin, mock_supabase):
        """Purposes endpoint is public — no auth headers needed."""
        client, _ = client_as_admin
        resp = client.get("/api/v1/dpdp/purposes")
        assert resp.status_code == 200
        body = resp.json()
        codes = [p["code"] for p in body]
        assert "MARKETING" in codes
        assert "RECRUITMENT_DATA" in codes
        assert len(body) == 7

    def test_retention_schedule_public(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.get("/api/v1/dpdp/retention-schedule")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) == 7

    def test_data_localisation_public(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.get("/api/v1/dpdp/data-localisation")
        assert resp.status_code == 200
        body = resp.json()
        assert body["compliant"] is True
        assert "ap-south-1" in body["pii_storage_region"]

    def test_record_single_consent_happy(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",               _ORG_ROW)
        sb.configure("dpdp_consent_records", _CONSENT_INSERT)
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/dpdp/consent", json={
            "candidate_id": CANDIDATE_ID,
            "purpose_code": "MARKETING",
            "consented":    True,
        })
        assert resp.status_code == 201
        assert resp.json()["purpose_code"] == "MARKETING"

    def test_record_consent_invalid_purpose(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)

        resp = client.post("/api/v1/dpdp/consent", json={
            "candidate_id": CANDIDATE_ID,
            "purpose_code": "ALL_PURPOSES",   # bundled — rejected
            "consented":    True,
        })
        assert resp.status_code == 422

    def test_cannot_withdraw_required_consent_via_api(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)

        resp = client.post("/api/v1/dpdp/consent", json={
            "candidate_id": CANDIDATE_ID,
            "purpose_code": "RECRUITMENT_DATA",
            "consented":    False,   # withdrawal of required consent
        })
        assert resp.status_code == 400
        assert "required" in resp.json()["detail"].lower()

    def test_consent_summary_all_purposes(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",               _ORG_ROW)
        sb.configure("dpdp_consent_records", _CONSENT_INSERT)

        resp = client.get(f"/api/v1/dpdp/consent/{CANDIDATE_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["purposes"]) == 7   # all 7 purposes always shown

    def test_create_erasure_request(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                _ORG_ROW)
        sb.configure("dpdp_erasure_requests", _ERASURE_ROW)
        sb.configure("dpdp_erasure_requests", [{"id": REQUEST_ID}])  # update WA ack
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/dpdp/erasure-request", json={
            "candidate_id":   CANDIDATE_ID,
            "request_type":   "ERASURE",
            "candidate_name": "Test Candidate",
            "candidate_phone": "+919876543210",
        })
        assert resp.status_code == 201
        assert resp.json()["id"] == REQUEST_ID

    def test_list_erasure_requests(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                _ORG_ROW)
        sb.configure("dpdp_erasure_requests", _ERASURE_ROW)

        resp = client.get("/api/v1/dpdp/erasure-requests")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_issue_privacy_token(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                 _ORG_ROW)
        sb.configure("privacy_center_sessions", [{
            "id": SESSION_ID, "token": VALID_TOKEN,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        }])

        resp = client.post("/api/v1/dpdp/privacy-centre/token", json={
            "candidate_id": CANDIDATE_ID,
        })
        assert resp.status_code == 201
        body = resp.json()
        assert "token" in body
        assert "/privacy-centre/" in body["url_hint"]


# ═════════════════════════════════════════════════════════════════════════════
# 6. Candidate Privacy Centre (token auth, no JWT)
# ═════════════════════════════════════════════════════════════════════════════

_CONSENT_ROWS = [
    {"purpose_code": "MARKETING", "consented": True,
     "consented_at": "2026-05-10T09:00:00", "consent_text_version": "v2.0",
     "ip_address": "1.2.3.4", "consent_mechanism": "PRIVACY_CENTRE",
     "legal_retention_basis": None},
]

_REQUESTS_ROWS = []


class TestCandidatePrivacyCentre:
    def _configure_token_valid(self, sb, extra_calls=None):
        """Configure MockSupabase for: session lookup + update + consents + requests."""
        sb.configure("privacy_center_sessions", _SESSION_ROW, [{"id": SESSION_ID}])
        # GET /privacy-centre/{token} also fetches consents and erasure requests
        sb.configure("dpdp_consent_records",    _CONSENT_ROWS)
        sb.configure("dpdp_erasure_requests",   _REQUESTS_ROWS)

    def test_get_privacy_centre_valid_token(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        self._configure_token_valid(sb)

        resp = client.get(f"/api/v1/dpdp/privacy-centre/{VALID_TOKEN}")
        assert resp.status_code == 200
        body = resp.json()
        assert "consents" in body
        assert len(body["consents"]) == 7   # all 7 purposes shown
        assert body["data_region"] == "ap-south-1"
        assert "grievance_officer" in body

    def test_invalid_token_returns_401(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("privacy_center_sessions", [])   # not found

        resp = client.get("/api/v1/dpdp/privacy-centre/bad-token-xyz")
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        expired_session = [{
            **_SESSION_ROW[0],
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        }]
        sb.configure("privacy_center_sessions", expired_session)

        resp = client.get(f"/api/v1/dpdp/privacy-centre/{VALID_TOKEN}")
        assert resp.status_code == 401

    def test_candidate_toggles_marketing_consent(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        # session validate + update
        sb.configure("privacy_center_sessions", _SESSION_ROW, [{"id": SESSION_ID}])
        # candidate org lookup
        sb.configure("candidates",              _CAND_ORG_ROW)
        # consent insert + audit log
        sb.configure("dpdp_consent_records",    _CONSENT_INSERT)
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post(f"/api/v1/dpdp/privacy-centre/{VALID_TOKEN}/consent", json={
            "purpose_code": "MARKETING",
            "consented":    False,   # withdrawal
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["recorded"] is True
        assert body["purpose_code"] == "MARKETING"
        assert body["consented"] is False

    def test_candidate_cannot_withdraw_required_consent(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("privacy_center_sessions", _SESSION_ROW, [{"id": SESSION_ID}])
        sb.configure("candidates",              _CAND_ORG_ROW)

        resp = client.post(f"/api/v1/dpdp/privacy-centre/{VALID_TOKEN}/consent", json={
            "purpose_code": "RECRUITMENT_DATA",
            "consented":    False,
        })
        assert resp.status_code == 400

    def test_candidate_submits_erasure_from_privacy_centre(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("privacy_center_sessions", _SESSION_ROW, [{"id": SESSION_ID}])
        sb.configure("candidates",              _CAND_ORG_ROW)
        # variadic: INSERT returns _ERASURE_ROW, UPDATE (WA ack) returns update row
        sb.configure("dpdp_erasure_requests",   _ERASURE_ROW, [{"id": REQUEST_ID}])
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post(f"/api/v1/dpdp/privacy-centre/{VALID_TOKEN}/erasure", json={
            "request_type": "ACCESS",
            "name":         "Ravi Kumar",
            "phone":        "+919876543210",
        })
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "ERASURE"   # DB row has ERASURE

    def test_retention_info_for_candidate(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("privacy_center_sessions", _SESSION_ROW, [{"id": SESSION_ID}])

        resp = client.get(f"/api/v1/dpdp/privacy-centre/{VALID_TOKEN}/retention")
        assert resp.status_code == 200
        body = resp.json()
        assert "retention_schedule" in body
        assert "statutory_retention" in body
        assert "dpbi_url" in body
