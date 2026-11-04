from datetime import datetime, timezone

import pytest

from app.services.referral_lifecycle_service import (
    attribute_application,
    mark_application_referral_hired,
)
from tests.conftest import MockSupabase


REFERRAL = {
    "id": "ref-1", "link_token": "secure-token", "job_role_id": "job-1",
    "status": "PENDING", "application_id": None, "candidate_email": None,
    "program_id": "program-1", "reward_amount": 2000,
}


def test_attribute_application_links_secure_token():
    sb = MockSupabase().configure("referrals", [REFERRAL], [], [{**REFERRAL, "status": "APPLIED"}])
    result = attribute_application(
        sb, token="secure-token", job_role_id="job-1", application_id="app-1",
        candidate_email="Candidate@Example.com",
    )
    assert result["status"] == "APPLIED"


def test_attribute_application_rejects_reused_link():
    sb = MockSupabase().configure("referrals", [{**REFERRAL, "application_id": "app-old"}])
    with pytest.raises(ValueError, match="already been used"):
        attribute_application(sb, token="secure-token", job_role_id="job-1", application_id="app-new")


def test_attribute_application_rejects_duplicate_candidate_job():
    sb = MockSupabase().configure("referrals", [REFERRAL], [{"id": "ref-other"}])
    with pytest.raises(ValueError, match="active referral"):
        attribute_application(
            sb, token="secure-token", job_role_id="job-1", application_id="app-1",
            candidate_email="candidate@example.com",
        )


def test_hire_starts_program_retention_clock():
    hired_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sb = MockSupabase()
    sb.configure("referrals", [{**REFERRAL, "application_id": "app-1", "status": "SHORTLISTED"}], [{"id": "ref-1", "status": "HIRED"}])
    sb.configure("referral_programs", [{"retention_days": 90, "reward_on_hire": 2500}])
    result = mark_application_referral_hired(sb, "app-1", hired_at=hired_at)
    assert result["status"] == "HIRED"


def test_hire_is_idempotent_after_bonus_paid():
    paid = {**REFERRAL, "status": "BONUS_PAID", "application_id": "app-1"}
    sb = MockSupabase().configure("referrals", [paid])
    assert mark_application_referral_hired(sb, "app-1") == paid
