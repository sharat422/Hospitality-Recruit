"""Focused tests for the hardened 60-second candidate application flow."""

import uuid

from app.services.otp_service import hash_otp
from app.services.smart_recruitment_service import check_apply_otp
from app.services.whatsapp_apply_service import handle_whatsapp_application
from tests.conftest import MockSupabase


PHONE = "+919876543210"
JOB = "11111111-1111-1111-1111-111111111111"
ORG = "22222222-2222-2222-2222-222222222222"


def test_check_apply_otp_accepts_hash_and_returns_one_time_token():
    sb = MockSupabase().configure(
        "mobile_otp_sessions",
        [{"id": "s1", "otp": None, "otp_hash": hash_otp("123456"),
          "expires_at": "2099-01-01T00:00:00+00:00", "verified": False, "attempts": 0}],
        [{"id": "s1"}],
    )
    result = check_apply_otp(sb, PHONE, "123456", JOB, ORG)
    assert result["verified"] is True
    uuid.UUID(result["verification_token"])


def test_check_apply_otp_rejects_wrong_code():
    sb = MockSupabase().configure(
        "mobile_otp_sessions",
        [{"id": "s1", "otp": None, "otp_hash": hash_otp("123456"),
          "expires_at": "2099-01-01T00:00:00+00:00", "verified": False, "attempts": 0}],
        [{"id": "s1"}],
    )
    result = check_apply_otp(sb, PHONE, "654321", JOB, ORG)
    assert result == {"verified": False, "error": "Incorrect OTP"}


def test_whatsapp_apply_starts_only_for_open_job():
    sb = MockSupabase()
    sb.configure("jobs", [{"id": JOB, "org_id": ORG, "title": "Waiter", "property_name": "Hotel India"}])
    sb.configure("whatsapp_apply_sessions", [{"id": "session-1"}])
    reply = handle_whatsapp_application(sb, PHONE, f"APPLY {JOB}")
    assert "full name" in reply
    assert "Waiter" in reply


def test_non_application_whatsapp_message_falls_through():
    sb = MockSupabase().configure("whatsapp_apply_sessions", [])
    assert handle_whatsapp_application(sb, PHONE, "HELP") is None
