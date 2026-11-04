"""
Tests for India KYC — Aadhaar OTP, PAN, DigiLocker, masking helpers.

Strategy
--------
All Supabase calls use MockSupabase from conftest.
All KYC provider calls run in SANDBOX mode (no SUREPASS_API_TOKEN set).
The tests validate:
  1. Pure masking / validation helpers
  2. Aadhaar OTP initiate endpoint (happy + sad paths)
  3. Aadhaar OTP verify endpoint (happy + wrong OTP + already-verified)
  4. PAN verify endpoint (happy + bad format + provider error)
  5. DigiLocker auth-url + callback
  6. KYC status summary
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import ADMIN_ID, EMPLOYEE_ID

# ─── IDs used across tests ────────────────────────────────────────────────────
ORG_ID       = "aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb"
CANDIDATE_ID = "ccccdddd-eeee-ffff-aaaa-bbbbccccdddd"
SESSION_ID   = "eeeeffff-aaaa-bbbb-cccc-ddddeeeeffff"
VERIF_ID     = "ffffaaaa-bbbb-cccc-dddd-eeeeffff1234"


# ═════════════════════════════════════════════════════════════════════════════
# 1. Pure helpers (no I/O)
# ═════════════════════════════════════════════════════════════════════════════

class TestMaskPAN:
    def test_standard_pan(self):
        from app.services.kyc_service import mask_pan
        assert mask_pan("ABCDE1234F") == "ABCDE****F"

    def test_lowercase_accepted(self):
        from app.services.kyc_service import mask_pan
        assert mask_pan("abcde1234f") == "ABCDE****F"

    def test_invalid_pan_raises(self):
        from app.services.kyc_service import mask_pan
        with pytest.raises(ValueError):
            mask_pan("INVALID")

    def test_pan_type_ends_P(self):
        from app.services.kyc_service import mask_pan
        assert mask_pan("BZBPK7190P") == "BZBPK****P"

    def test_mask_pan_from_compliance_service(self):
        from app.services.india_compliance_service import mask_pan
        assert mask_pan("ABCDE1234F") == "ABCDE****F"


class TestMaskAadhaar:
    def test_standard_12_digit(self):
        from app.services.kyc_service import mask_aadhaar
        assert mask_aadhaar("123456789012") == "XXXX XXXX 9012"

    def test_with_spaces(self):
        from app.services.kyc_service import mask_aadhaar
        assert mask_aadhaar("1234 5678 9012") == "XXXX XXXX 9012"

    def test_with_dashes(self):
        from app.services.kyc_service import mask_aadhaar
        assert mask_aadhaar("1234-5678-9012") == "XXXX XXXX 9012"

    def test_invalid_length_raises(self):
        from app.services.kyc_service import mask_aadhaar
        with pytest.raises(ValueError):
            mask_aadhaar("123456")  # only 6 digits

    def test_mask_aadhaar_from_compliance_service(self):
        from app.services.india_compliance_service import mask_aadhaar
        assert mask_aadhaar("987600001234") == "XXXX XXXX 1234"


class TestExtractLast4:
    def test_extracts_last4(self):
        from app.services.kyc_service import extract_aadhaar_last4
        assert extract_aadhaar_last4("234512349012") == "9012"

    def test_strips_spaces(self):
        from app.services.kyc_service import extract_aadhaar_last4
        assert extract_aadhaar_last4("2345 1234 9012") == "9012"


class TestValidateAadhaarNumber:
    def test_valid(self):
        from app.services.kyc_service import validate_aadhaar_number
        assert validate_aadhaar_number("234512349012") is True

    def test_starts_with_zero_invalid(self):
        from app.services.kyc_service import validate_aadhaar_number
        assert validate_aadhaar_number("034512349012") is False

    def test_11_digits_invalid(self):
        from app.services.kyc_service import validate_aadhaar_number
        assert validate_aadhaar_number("12345678901") is False

    def test_letters_invalid(self):
        from app.services.kyc_service import validate_aadhaar_number
        assert validate_aadhaar_number("1234567890AB") is False


# ═════════════════════════════════════════════════════════════════════════════
# 2. Aadhaar OTP — initiate
# ═════════════════════════════════════════════════════════════════════════════

_USER = {"sub": ADMIN_ID, "email": "admin@hotel.in"}

_ORG_ROW       = [{"org_id": ORG_ID}]
_SESSION_INSERT = [{"id": SESSION_ID, "request_id": "sandbox-req-00000000"}]


class TestAadhaarInitiate:
    def test_initiate_sandbox_happy(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                 _ORG_ROW)
        sb.configure("aadhaar_kyc_sessions",  _SESSION_INSERT)
        sb.configure("india_compliance_audit_logs", [])

        resp = client.post("/api/v1/kyc/aadhaar/initiate", json={
            "aadhaar_number": "234512349012",
            "candidate_id":   CANDIDATE_ID,
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["request_id"] == "sandbox-req-00000000"
        assert body["sandbox"] is True
        assert body["expires_in_seconds"] == 600

    def test_initiate_rejects_bad_aadhaar(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        resp = client.post("/api/v1/kyc/aadhaar/initiate", json={
            "aadhaar_number": "034512349012",   # starts with 0 → invalid
            "candidate_id":   CANDIDATE_ID,
        })
        assert resp.status_code == 422

    def test_initiate_rejects_11_digits(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        resp = client.post("/api/v1/kyc/aadhaar/initiate", json={
            "aadhaar_number": "12345678901",
            "candidate_id":   CANDIDATE_ID,
        })
        assert resp.status_code == 422

    def test_initiate_user_not_found(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", [])  # no user row → 404

        resp = client.post("/api/v1/kyc/aadhaar/initiate", json={
            "aadhaar_number": "234512349012",
            "candidate_id":   CANDIDATE_ID,
        })
        assert resp.status_code == 404


# ═════════════════════════════════════════════════════════════════════════════
# 3. Aadhaar OTP — verify
# ═════════════════════════════════════════════════════════════════════════════

_SESSION_OTP_SENT = [{
    "id":            SESSION_ID,
    "status":        "OTP_SENT",
    "otp_attempts":  0,
    "expires_at":    "2099-01-01T00:00:00",
    "provider":      "SANDBOX",
    "candidate_id":  CANDIDATE_ID,
}]

_SESSION_ALREADY_VERIFIED = [{
    "id":           SESSION_ID,
    "status":       "VERIFIED",
    "otp_attempts": 1,
    "expires_at":   "2099-01-01T00:00:00",
    "provider":     "SANDBOX",
    "candidate_id": CANDIDATE_ID,
}]

_SESSION_FAILED = [{
    "id":           SESSION_ID,
    "status":       "FAILED",
    "otp_attempts": 3,
    "expires_at":   "2099-01-01T00:00:00",
    "provider":     "SANDBOX",
    "candidate_id": CANDIDATE_ID,
}]

_SESSION_UPDATE = [{"id": SESSION_ID}]
_VERIF_INSERT   = [{"id": VERIF_ID}]
_CAND_UPDATE    = [{"id": CANDIDATE_ID}]


class TestAadhaarVerify:
    def _configure_happy(self, sb):
        sb.configure("users",                         _ORG_ROW)
        # All three aadhaar_kyc_sessions calls in one variadic configure:
        #   1st execute → SELECT session row
        #   2nd execute → UPDATE status=VERIFIED
        #   3rd execute → UPDATE identity_verification_id link
        sb.configure("aadhaar_kyc_sessions",
                     _SESSION_OTP_SENT, _SESSION_UPDATE, _SESSION_UPDATE)
        sb.configure("india_identity_verifications",  _VERIF_INSERT)
        sb.configure("candidates",                    _CAND_UPDATE)
        sb.configure("india_compliance_audit_logs",   [])

    def test_verify_sandbox_correct_otp(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        self._configure_happy(sb)

        resp = client.post("/api/v1/kyc/aadhaar/verify", json={
            "request_id":   "sandbox-req-00000000",
            "otp":          "123456",
            "candidate_id": CANDIDATE_ID,
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["verified"] is True
        assert body["aadhaar_last4"] == "9012"
        assert body["aadhaar_masked"] == "XXXX XXXX 9012"
        assert body["sandbox"] is True

    def test_verify_wrong_otp_returns_400(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        # Wrong OTP: SELECT session then UPDATE otp_attempts
        sb.configure("aadhaar_kyc_sessions", _SESSION_OTP_SENT, _SESSION_UPDATE)
        sb.configure("india_compliance_audit_logs", [])

        resp = client.post("/api/v1/kyc/aadhaar/verify", json={
            "request_id":   "sandbox-req-00000000",
            "otp":          "999999",   # wrong
            "candidate_id": CANDIDATE_ID,
        })
        assert resp.status_code == 400
        assert "OTP verification failed" in resp.json()["detail"]

    def test_verify_already_verified_returns_409(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",               _ORG_ROW)
        sb.configure("aadhaar_kyc_sessions", _SESSION_ALREADY_VERIFIED)

        resp = client.post("/api/v1/kyc/aadhaar/verify", json={
            "request_id":   "sandbox-req-00000000",
            "otp":          "123456",
            "candidate_id": CANDIDATE_ID,
        })
        assert resp.status_code == 409

    def test_verify_failed_session_returns_410(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",               _ORG_ROW)
        sb.configure("aadhaar_kyc_sessions", _SESSION_FAILED)

        resp = client.post("/api/v1/kyc/aadhaar/verify", json={
            "request_id":   "sandbox-req-00000000",
            "otp":          "123456",
            "candidate_id": CANDIDATE_ID,
        })
        assert resp.status_code == 410

    def test_verify_session_not_found_returns_404(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",               _ORG_ROW)
        sb.configure("aadhaar_kyc_sessions", [])  # empty

        resp = client.post("/api/v1/kyc/aadhaar/verify", json={
            "request_id":   "nonexistent",
            "otp":          "123456",
            "candidate_id": CANDIDATE_ID,
        })
        assert resp.status_code == 404

    def test_verify_response_has_no_full_aadhaar(self, client_as_admin, mock_supabase):
        """Full Aadhaar must never appear in any response field."""
        client, sb = client_as_admin
        self._configure_happy(sb)

        resp = client.post("/api/v1/kyc/aadhaar/verify", json={
            "request_id":   "sandbox-req-00000000",
            "otp":          "123456",
            "candidate_id": CANDIDATE_ID,
        })
        body_str = resp.text
        # Sandbox returns last4=9012, masked="XXXX XXXX 9012"
        # Ensure no 12-digit sequence appears in response
        import re
        assert not re.search(r"\b\d{12}\b", body_str), (
            "Full 12-digit Aadhaar must not appear in response"
        )


# ═════════════════════════════════════════════════════════════════════════════
# 4. PAN verification
# ═════════════════════════════════════════════════════════════════════════════

_PAN_VERIF_INSERT = [{"id": VERIF_ID}]


class TestPANVerify:
    def test_verify_happy_sandbox(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                         _ORG_ROW)
        sb.configure("india_identity_verifications",  _PAN_VERIF_INSERT)
        sb.configure("candidates",                    _CAND_UPDATE)
        sb.configure("india_compliance_audit_logs",   [])

        resp = client.post("/api/v1/kyc/pan/verify", json={
            "pan_number":   "ABCDE1234F",
            "candidate_id": CANDIDATE_ID,
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["verified"] is True
        assert body["pan_masked"] == "ABCDE****F"
        assert body["sandbox"] is True

    def test_verify_pan_with_name_match(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                         _ORG_ROW)
        sb.configure("india_identity_verifications",  _PAN_VERIF_INSERT)
        sb.configure("candidates",                    _CAND_UPDATE)
        sb.configure("india_compliance_audit_logs",   [])

        resp = client.post("/api/v1/kyc/pan/verify", json={
            "pan_number":    "ABCDE1234F",
            "candidate_id":  CANDIDATE_ID,
            "name_to_match": "SANDBOX USER",  # matches sandbox mock
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["name_match"] is True

    def test_verify_stores_masked_not_full_pan(self, client_as_admin, mock_supabase):
        """Full PAN must not appear in response body."""
        client, sb = client_as_admin
        sb.configure("users",                         _ORG_ROW)
        sb.configure("india_identity_verifications",  _PAN_VERIF_INSERT)
        sb.configure("candidates",                    _CAND_UPDATE)
        sb.configure("india_compliance_audit_logs",   [])

        resp = client.post("/api/v1/kyc/pan/verify", json={
            "pan_number":   "ABCDE1234F",
            "candidate_id": CANDIDATE_ID,
        })
        body = resp.json()
        assert "ABCDE1234F" not in resp.text, "Full PAN must not be in response"
        assert body["pan_masked"] == "ABCDE****F"

    def test_verify_rejects_invalid_pan_format(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        resp = client.post("/api/v1/kyc/pan/verify", json={
            "pan_number":   "INVALID",
            "candidate_id": CANDIDATE_ID,
        })
        assert resp.status_code == 422

    def test_verify_lowercase_pan_accepted(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                         _ORG_ROW)
        sb.configure("india_identity_verifications",  _PAN_VERIF_INSERT)
        sb.configure("candidates",                    _CAND_UPDATE)
        sb.configure("india_compliance_audit_logs",   [])

        resp = client.post("/api/v1/kyc/pan/verify", json={
            "pan_number":   "abcde1234f",   # lowercase
            "candidate_id": CANDIDATE_ID,
        })
        assert resp.status_code == 200
        assert resp.json()["pan_masked"] == "ABCDE****F"


# ═════════════════════════════════════════════════════════════════════════════
# 5. DigiLocker
# ═════════════════════════════════════════════════════════════════════════════

class TestDigiLockerAuthURL:
    def test_returns_auth_url(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        sb.configure("india_compliance_audit_logs", [])

        resp = client.get(f"/api/v1/kyc/digilocker/auth-url?candidate_id={CANDIDATE_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert "auth_url" in body
        assert "sandbox" in body
        assert body["sandbox"] is True  # no DIGILOCKER_CLIENT_ID set

    def test_auth_url_contains_candidate_in_state(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        sb.configure("india_compliance_audit_logs", [])

        resp = client.get(f"/api/v1/kyc/digilocker/auth-url?candidate_id={CANDIDATE_ID}")
        state = resp.json()["state"]
        assert state.startswith(CANDIDATE_ID)


_DIGILOCKER_VERIF_INSERT = [
    {"id": "dl-verif-1"},
    {"id": "dl-verif-2"},
]


class TestDigiLockerCallback:
    def test_callback_happy_sandbox(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        # Sandbox returns 2 docs; each needs its own INSERT result in one variadic configure
        sb.configure("india_identity_verifications",
                     [{"id": "dl-verif-1"}], [{"id": "dl-verif-2"}])
        sb.configure("india_compliance_audit_logs", [])

        resp = client.post("/api/v1/kyc/digilocker/callback", json={
            "code":         "sandbox-auth-code",
            "state":        f"{CANDIDATE_ID}:csrf-token",
            "candidate_id": CANDIDATE_ID,
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["verified"] is True
        assert body["doc_count"] == 2
        assert body["sandbox"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 6. KYC status summary
# ═════════════════════════════════════════════════════════════════════════════

_VERIF_LIST = [
    {
        "doc_type": "AADHAAR", "status": "VERIFIED",
        "pan_masked": None, "aadhaar_masked": "XXXX XXXX 9012",
        "verified_at": "2026-05-01T10:00:00", "kyc_provider": "SANDBOX",
    },
    {
        "doc_type": "PAN", "status": "VERIFIED",
        "pan_masked": "ABCDE****F", "aadhaar_masked": None,
        "verified_at": "2026-05-01T10:05:00", "kyc_provider": "SANDBOX",
    },
]

_CAND_KYC_ROW = [{"aadhaar_verified": True, "pan_verified": True}]


class TestKYCStatus:
    def test_status_complete(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                         _ORG_ROW)
        sb.configure("india_identity_verifications",  _VERIF_LIST)
        sb.configure("candidates",                    _CAND_KYC_ROW)

        resp = client.get(f"/api/v1/kyc/status/{CANDIDATE_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["aadhaar_verified"] is True
        assert body["pan_verified"] is True
        assert body["kyc_complete"] is True
        assert body["total_verified"] == 2

    def test_status_partial(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                         _ORG_ROW)
        sb.configure("india_identity_verifications",  _VERIF_LIST[:1])
        sb.configure("candidates",                    [{"aadhaar_verified": True, "pan_verified": False}])

        resp = client.get(f"/api/v1/kyc/status/{CANDIDATE_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["kyc_complete"] is False
        assert body["total_verified"] == 1
