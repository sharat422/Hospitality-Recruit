"""
Tests for POST /api/v1/referrals/create.

Covers
------
  Service helpers     — generate_link_token, build_referral_link_v2, build_whatsapp_url
  Happy path          — creates row, returns all required fields
  Idempotent dup      — same referrer+candidate+job already active → existing returned
  Cross-referrer 409  — candidate in pipeline via different referrer → 409
  Inactive program    — 409 (program exists but is_active=False)
  Program not found   — 404
  Unauthorized        — non-admin calling for someone else → 403
  Admin override      — admin can create on behalf of any employee
  No candidate        — no candidateEmail/Id → always creates (no dup check)
  Return shape        — all 7 keys present with correct types
"""

from __future__ import annotations

import re
from unittest.mock import patch
from urllib.parse import unquote

import pytest

from app.services.referral_service import (
    generate_link_token,
    build_referral_link_v2,
    build_whatsapp_url,
)
from tests.conftest import EMPLOYEE_ID, ADMIN_ID, OTHER_ID

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

URL = "/api/v1/referrals/create"

JOB_ID      = "job-role-uuid-0001"
PROGRAM_ID  = "prog-uuid-0001"
CAND_EMAIL  = "candidate@hotel.in"
CAND_ID     = "cand-uuid-0001"
REFERRAL_ID = "ref-uuid-0001"

_PROGRAM_ACTIVE   = [{"id": PROGRAM_ID, "name": "Summer Hire", "reward_on_hire": 5000,
                       "currency": "INR", "is_active": True}]
_PROGRAM_INACTIVE = [{"id": PROGRAM_ID, "name": "Old Program",  "reward_on_hire": 1000,
                       "currency": "INR", "is_active": False}]
_CALLER_ROW       = [{"role": "hiring_manager"}]
_ADMIN_CALLER_ROW = [{"role": "admin"}]
_NO_EXISTING      = []
_INSERTED_ROW     = [{"id": REFERRAL_ID, "referral_code": "REF-TESTCODE01",
                       "link_token": "tok123", "status": "PENDING",
                       "reward_amount": 5000}]

_EXISTING_ACTIVE  = [{"id": REFERRAL_ID, "referral_code": "REF-EXIST001",
                       "link_token": "existtok", "status": "PENDING",
                       "reward_amount": 5000}]
_CONFLICT_ROW     = [{"id": "other-ref-id", "referrer_id": OTHER_ID}]

def _body(**overrides):
    """Build a minimal valid request body."""
    base = {
        "programId":          PROGRAM_ID,
        "referrerEmployeeId": EMPLOYEE_ID,
        "jobRoleId":          JOB_ID,
        "jobTitle":           "Front Desk Manager",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Service-level unit tests
# ---------------------------------------------------------------------------

def test_generate_link_token_is_url_safe():
    token = generate_link_token()
    # URL-safe base64: only alphanumeric, -, _
    assert re.fullmatch(r"[A-Za-z0-9_-]+", token), f"Not URL-safe: {token}"


def test_generate_link_token_length():
    # 24 raw bytes → 32-char base64url
    assert len(generate_link_token()) == 32


def test_generate_link_token_unique():
    tokens = {generate_link_token() for _ in range(100)}
    assert len(tokens) == 100, "Duplicate token generated in 100 calls"


def test_build_referral_link_v2():
    link = build_referral_link_v2("https://app.example.com", JOB_ID, "mytoken123")
    assert link == f"https://app.example.com/apply/{JOB_ID}?token=mytoken123"


def test_build_whatsapp_url_contains_link():
    link = "https://app.example.com/apply/job?token=abc"
    url  = build_whatsapp_url(link, "Chef", reward=0)
    assert url.startswith("https://wa.me/?text=")
    assert "app.example.com" in url


def test_build_whatsapp_url_mentions_reward_when_nonzero():
    link = "https://app.example.com/apply/job?token=abc"
    url  = build_whatsapp_url(link, "Chef", reward=5000, currency="₹")
    # wa.me text is percent-encoded; decode before checking the formatted amount
    assert "5,000" in unquote(url)


def test_build_whatsapp_url_no_reward_text_when_zero():
    link = "https://app.example.com/apply/job?token=abc"
    url  = build_whatsapp_url(link, "Chef", reward=0)
    assert "earn" not in url.lower()


# ---------------------------------------------------------------------------
# POST /referrals/create — integration tests (mocked DB)
# ---------------------------------------------------------------------------

def test_create_referral_success(client_as_employee):
    client, sb = client_as_employee
    sb.configure("referral_programs", _PROGRAM_ACTIVE)
    # No existing active referral, no conflict
    sb.configure("referrals",
                 _NO_EXISTING,     # exact dup check
                 _NO_EXISTING,     # conflict check
                 _NO_EXISTING,     # token collision check
                 _INSERTED_ROW)    # insert

    with patch("app.routers.referrals.generate_link_token", return_value="tok123"), \
         patch("app.routers.referrals.generate_referral_code", return_value="REF-TESTCODE01"):
        resp = client.post(URL, json=_body(candidateEmail=CAND_EMAIL))

    assert resp.status_code == 201
    data = resp.json()
    assert data["referralCode"] == "REF-TESTCODE01"
    assert "tok123" in data["referralLink"]
    assert data["linkToken"] == "tok123"
    assert data["whatsappUrl"].startswith("https://wa.me/")
    assert data["rewardAmount"] == 5000
    assert data["duplicate"] is False
    assert data["status"] == "PENDING"
    assert "referralId" in data


def test_create_referral_returns_all_required_fields(client_as_employee):
    client, sb = client_as_employee
    sb.configure("referral_programs", _PROGRAM_ACTIVE)
    # No candidateEmail → only 2 referral table calls: token collision check + insert
    sb.configure("referrals", _NO_EXISTING, _INSERTED_ROW)

    with patch("app.routers.referrals.generate_link_token", return_value="tok999"), \
         patch("app.routers.referrals.generate_referral_code", return_value="REF-ABC12345"):
        resp = client.post(URL, json=_body())

    assert resp.status_code == 201
    data = resp.json()
    required = {"referralId", "referralCode", "linkToken", "referralLink",
                "whatsappUrl", "rewardAmount", "duplicate"}
    assert required.issubset(data.keys())


def test_create_referral_no_candidate_skips_dup_checks(client_as_employee):
    """No candidateEmail → skip both duplicate checks; always insert."""
    client, sb = client_as_employee
    sb.configure("referral_programs", _PROGRAM_ACTIVE)
    # Only token check + insert (no dup or conflict selects)
    sb.configure("referrals", _NO_EXISTING, _INSERTED_ROW)

    with patch("app.routers.referrals.generate_link_token", return_value="tokNew"), \
         patch("app.routers.referrals.generate_referral_code", return_value="REF-NEW00001"):
        resp = client.post(URL, json=_body())  # no candidateEmail

    assert resp.status_code == 201
    assert resp.json()["duplicate"] is False


def test_create_referral_idempotent_duplicate(client_as_employee):
    """Same referrer+candidate+job already PENDING → return existing, 200."""
    client, sb = client_as_employee
    sb.configure("referral_programs", _PROGRAM_ACTIVE)
    sb.configure("referrals", _EXISTING_ACTIVE)  # exact dup check hits

    resp = client.post(URL, json=_body(candidateEmail=CAND_EMAIL))

    assert resp.status_code == 200
    data = resp.json()
    assert data["duplicate"] is True
    assert data["referralCode"] == "REF-EXIST001"
    assert "existtok" in data["referralLink"]
    assert "wa.me" in data["whatsappUrl"]


def test_create_referral_cross_referrer_conflict(client_as_employee):
    """Candidate already APPLIED via a different referrer → 409."""
    client, sb = client_as_employee
    sb.configure("referral_programs", _PROGRAM_ACTIVE)
    sb.configure("referrals",
                 _NO_EXISTING,    # exact dup (no match — different referrer)
                 _CONFLICT_ROW)   # conflict check finds another referrer

    resp = client.post(URL, json=_body(candidateEmail=CAND_EMAIL))

    assert resp.status_code == 409
    assert "first referrer" in resp.json()["detail"].lower()


def test_create_referral_program_not_found(client_as_employee):
    client, sb = client_as_employee
    sb.configure("referral_programs", [])  # program lookup returns nothing

    resp = client.post(URL, json=_body())

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_create_referral_inactive_program(client_as_employee):
    client, sb = client_as_employee
    sb.configure("referral_programs", _PROGRAM_INACTIVE)

    resp = client.post(URL, json=_body())

    assert resp.status_code == 409
    assert "not active" in resp.json()["detail"].lower()


def test_create_referral_unauthorized_other_user(client_as_other):
    """Caller is OTHER_ID but referrerEmployeeId is EMPLOYEE_ID → 403."""
    client, sb = client_as_other
    # Role check for OTHER_ID → hiring_manager (not admin)
    sb.configure("users", [{"role": "hiring_manager"}])

    resp = client.post(URL, json=_body())  # referrerEmployeeId=EMPLOYEE_ID, caller=OTHER_ID

    assert resp.status_code == 403
    assert "not authorized" in resp.json()["detail"].lower()


def test_create_referral_admin_can_create_for_any_employee(client_as_admin):
    """Admin caller creates on behalf of EMPLOYEE_ID → allowed."""
    client, sb = client_as_admin
    # Role check for ADMIN_ID → admin
    sb.configure("users", _ADMIN_CALLER_ROW)
    sb.configure("referral_programs", _PROGRAM_ACTIVE)
    sb.configure("referrals", _NO_EXISTING, _NO_EXISTING, _NO_EXISTING, _INSERTED_ROW)

    with patch("app.routers.referrals.generate_link_token", return_value="admintok"), \
         patch("app.routers.referrals.generate_referral_code", return_value="REF-ADMIN001"):
        resp = client.post(URL, json=_body(candidateEmail=CAND_EMAIL))

    assert resp.status_code == 201
    assert resp.json()["duplicate"] is False


def test_create_referral_self_no_role_check(client_as_employee):
    """When caller IS the referrerEmployeeId, no role DB lookup is made."""
    client, sb = client_as_employee
    sb.configure("referral_programs", _PROGRAM_ACTIVE)
    # No candidateEmail → 2 referral calls: token check + insert
    sb.configure("referrals", _NO_EXISTING, _INSERTED_ROW)

    with patch("app.routers.referrals.generate_link_token", return_value="selftok"), \
         patch("app.routers.referrals.generate_referral_code", return_value="REF-SELF0001"):
        resp = client.post(URL, json=_body())

    # If the users table were called it would return nothing → would 403.
    # Passing with 201 proves the role lookup was skipped.
    assert resp.status_code == 201


def test_create_referral_missing_required_fields(client_as_employee):
    """Missing programId / referrerEmployeeId / jobRoleId → 422."""
    client, _ = client_as_employee
    resp = client.post(URL, json={"jobRoleId": JOB_ID})
    assert resp.status_code == 422


def test_create_referral_whatsapp_url_shape(client_as_employee):
    """WhatsApp URL must be a valid wa.me deeplink with encoded text."""
    client, sb = client_as_employee
    sb.configure("referral_programs", _PROGRAM_ACTIVE)
    # No candidateEmail → 2 referral calls: token check + insert
    sb.configure("referrals", _NO_EXISTING, _INSERTED_ROW)

    with patch("app.routers.referrals.generate_link_token", return_value="watok"), \
         patch("app.routers.referrals.generate_referral_code", return_value="REF-WATEST01"):
        resp = client.post(URL, json=_body(jobTitle="Spa Manager"))

    assert resp.status_code == 201
    url = resp.json()["whatsappUrl"]
    assert url.startswith("https://wa.me/?text=")
    assert "Spa" in unquote(url)
