"""
Tests for WhatsApp referral sharing.

Covers
------
  Service layer  — format_salary_inr, format_salary_range, render_template, build_wa_url
  POST /api/v1/referrals/{id}/share/whatsapp
    - Happy path English
    - Happy path Hindi
    - Unknown lang falls back to English
    - 404 when referral not found
    - 403 when caller does not own the referral and is not admin
    - Admin can share any referral
    - Salary range included in message
    - Message preview is plain text (not URL-encoded)
    - whatsapp_url starts with wa.me
    - tracked=True in response
    - role looked up from job_roles when not in request
    - role_title override skips job_roles lookup
"""

from __future__ import annotations

from urllib.parse import unquote

import pytest

from app.services.whatsapp_template_service import (
    SUPPORTED_LANGS,
    build_wa_url,
    format_salary_inr,
    format_salary_range,
    render_template,
)
from tests.conftest import EMPLOYEE_ID, ADMIN_ID, OTHER_ID

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

URL = "/api/v1/referrals/{id}/share/whatsapp"
REFERRAL_ID = "ref-wa-uuid-0001"
JOB_ROLE_ID = "job-role-uuid-0001"


def share_url(rid: str = REFERRAL_ID) -> str:
    return f"/api/v1/referrals/{rid}/share/whatsapp"


_REFERRAL_ROW = [{
    "id": REFERRAL_ID,
    "referrer_id": EMPLOYEE_ID,
    "job_role_id": JOB_ROLE_ID,
    "referral_code": "REF-TEST0001",
    "link_token": "securetok123",
    "reward_amount": 5000,
}]
_JOB_ROLE_ROW  = [{"title": "Front Desk Manager"}]
_NO_JOB_ROLE   = []
_TRACK_ROW     = [{"id": REFERRAL_ID, "whatsapp_shared": True}]
_CALLER_ROW    = [{"role": "hiring_manager"}]
_ADMIN_ROW     = [{"role": "admin"}]

_DEFAULT_BODY = {
    "lang": "en",
    "property_name": "Taj Hotel Mumbai",
    "salary_min": 35_000,
    "salary_max": 50_000,
}


# ===========================================================================
# Service — format_salary_inr
# ===========================================================================

@pytest.mark.parametrize("val,expected", [
    (None,     "Negotiable"),
    (0,        "Negotiable"),
    (500,      "500"),
    (5_000,    "5K"),
    (35_000,   "35K"),
    (35_500,   "35.5K"),
    (100_000,  "1L"),
    (150_000,  "1.5L"),
    (2_500_000,"25L"),
])
def test_format_salary_inr(val, expected):
    assert format_salary_inr(val) == expected


@pytest.mark.parametrize("lo,hi,expected", [
    (35_000, 50_000,  "35K–50K"),
    (35_000, None,    "35K"),
    (None,   50_000,  "50K"),
    (None,   None,    "Negotiable"),
    (100_000,100_000, "1L"),          # same value — no dash
])
def test_format_salary_range(lo, hi, expected):
    assert format_salary_range(lo, hi) == expected


# ===========================================================================
# Service — render_template
# ===========================================================================

def test_render_template_english_contains_fields():
    msg = render_template(
        lang="en",
        property_name="Oberoi Delhi",
        role="Housekeeping Supervisor",
        apply_link="https://app.test/apply/job?token=abc",
        referral_code="REF-XYZ",
        salary_min=25_000,
        salary_max=40_000,
        reward=5000,
    )
    assert "Oberoi Delhi" in msg
    assert "Housekeeping Supervisor" in msg
    assert "25K" in msg
    assert "40K" in msg
    assert "https://app.test/apply/job?token=abc" in msg
    assert "REF-XYZ" in msg
    assert "5,000" in msg          # reward amount


def test_render_template_hindi_contains_hindi_text():
    msg = render_template(
        lang="hi",
        property_name="ताज होटल",
        role="Front Desk",
        apply_link="https://app.test/apply",
        referral_code="REF-HI",
    )
    assert "नमस्ते" in msg
    assert "ताज होटल" in msg
    assert "Front Desk" in msg
    assert "माह" in msg            # Hindi word for "month"


def test_render_template_unknown_lang_falls_back_to_english():
    msg = render_template(
        lang="fr",       # French — not supported
        property_name="Paris Resort",
        role="Chef",
        apply_link="https://app.test",
        referral_code="REF-FR",
    )
    assert "Hi!" in msg            # English opener


def test_render_template_no_reward_omits_reward_line():
    msg = render_template(
        lang="en",
        property_name="Hilton",
        role="Bellboy",
        apply_link="https://app.test",
        referral_code="REF-HB",
        reward=0,
    )
    assert "earn" not in msg.lower()


def test_render_template_negotiable_salary_when_none():
    msg = render_template(
        lang="en",
        property_name="ITC Hotels",
        role="Steward",
        apply_link="https://app.test",
        referral_code="REF-ST",
    )
    assert "Negotiable" in msg


def test_supported_langs_contains_en_and_hi():
    assert "en" in SUPPORTED_LANGS
    assert "hi" in SUPPORTED_LANGS


def test_build_wa_url_structure():
    url = build_wa_url("Hello World!\nSecond line")
    assert url.startswith("https://wa.me/?text=")
    assert "Hello" in unquote(url)
    assert "Second" in unquote(url)


# ===========================================================================
# POST /referrals/{id}/share/whatsapp
# ===========================================================================

def test_share_whatsapp_english_happy_path(client_as_employee):
    client, sb = client_as_employee
    # Two successive referrals calls: fetch → update; must be in one configure
    sb.configure("referrals",  _REFERRAL_ROW, _TRACK_ROW)
    sb.configure("job_roles",  _JOB_ROLE_ROW)

    resp = client.post(share_url(), json=_DEFAULT_BODY)

    assert resp.status_code == 200
    data = resp.json()
    assert data["whatsapp_url"].startswith("https://wa.me/?text=")
    assert data["tracked"] is True
    assert data["lang"] == "en"
    assert data["referral_code"] == "REF-TEST0001"
    # Preview is plain text — must contain the property name
    assert "Taj Hotel Mumbai" in data["message_preview"]
    assert "Front Desk Manager" in data["message_preview"]


def test_share_whatsapp_hindi(client_as_employee):
    client, sb = client_as_employee
    sb.configure("referrals",  _REFERRAL_ROW, _TRACK_ROW)
    sb.configure("job_roles",  _JOB_ROLE_ROW)

    resp = client.post(share_url(), json={**_DEFAULT_BODY, "lang": "hi"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["lang"] == "hi"
    assert "नमस्ते" in data["message_preview"]


def test_share_whatsapp_unknown_lang_falls_back(client_as_employee):
    client, sb = client_as_employee
    sb.configure("referrals", _REFERRAL_ROW, _TRACK_ROW)
    sb.configure("job_roles", _JOB_ROLE_ROW)

    resp = client.post(share_url(), json={**_DEFAULT_BODY, "lang": "te"})  # Telugu

    assert resp.status_code == 200
    assert resp.json()["lang"] == "en"    # normalized to fallback


def test_share_whatsapp_referral_not_found(client_as_employee):
    client, sb = client_as_employee
    sb.configure("referrals", [])         # not found

    resp = client.post(share_url("non-existent-id"), json=_DEFAULT_BODY)

    assert resp.status_code == 404


def test_share_whatsapp_unauthorized(client_as_other):
    client, sb = client_as_other
    sb.configure("referrals", _REFERRAL_ROW)          # referrer_id = EMPLOYEE_ID
    sb.configure("users",     _CALLER_ROW)             # role = hiring_manager (not admin)

    resp = client.post(share_url(), json=_DEFAULT_BODY)

    assert resp.status_code == 403
    assert "not authorized" in resp.json()["detail"].lower()


def test_share_whatsapp_admin_can_share_any(client_as_admin):
    client, sb = client_as_admin
    sb.configure("referrals", _REFERRAL_ROW)           # referrer_id = EMPLOYEE_ID ≠ ADMIN_ID
    sb.configure("users",     _ADMIN_ROW)              # caller is admin
    sb.configure("job_roles", _JOB_ROLE_ROW)
    sb.configure("referrals", _TRACK_ROW)

    resp = client.post(share_url(), json=_DEFAULT_BODY)

    assert resp.status_code == 200
    assert resp.json()["tracked"] is True


def test_share_whatsapp_salary_in_message(client_as_employee):
    client, sb = client_as_employee
    sb.configure("referrals", _REFERRAL_ROW, _TRACK_ROW)
    sb.configure("job_roles", _JOB_ROLE_ROW)

    resp = client.post(share_url(), json={
        **_DEFAULT_BODY,
        "salary_min": 35_000,
        "salary_max": 50_000,
    })

    assert resp.status_code == 200
    preview = resp.json()["message_preview"]
    assert "35K" in preview
    assert "50K" in preview


def test_share_whatsapp_role_title_override_skips_db(client_as_employee):
    """Providing role_title must NOT trigger a job_roles lookup."""
    client, sb = client_as_employee
    # job_roles NOT configured — proves the lookup was skipped (no query issued)
    sb.configure("referrals", _REFERRAL_ROW, _TRACK_ROW)

    resp = client.post(share_url(), json={
        **_DEFAULT_BODY,
        "role_title": "Executive Chef",
    })

    assert resp.status_code == 200
    assert "Executive Chef" in resp.json()["message_preview"]


def test_share_whatsapp_role_from_job_roles_db(client_as_employee):
    """Without role_title the endpoint looks up job_roles and uses the title."""
    client, sb = client_as_employee
    sb.configure("referrals", _REFERRAL_ROW, _TRACK_ROW)
    sb.configure("job_roles", [{"title": "Spa Manager"}])

    resp = client.post(share_url(), json={
        "lang": "en",
        "property_name": "Leela Palace",
    })

    assert resp.status_code == 200
    assert "Spa Manager" in resp.json()["message_preview"]


def test_share_whatsapp_default_role_fallback(client_as_employee):
    """If job_roles has no match, role falls back to 'Hospitality Role'."""
    client, sb = client_as_employee
    sb.configure("referrals", _REFERRAL_ROW, _TRACK_ROW)
    sb.configure("job_roles", _NO_JOB_ROLE)   # not found in DB

    resp = client.post(share_url(), json={"lang": "en", "property_name": "ITC"})

    assert resp.status_code == 200
    assert "Hospitality Role" in resp.json()["message_preview"]


def test_share_whatsapp_apply_link_in_message(client_as_employee):
    client, sb = client_as_employee
    sb.configure("referrals", _REFERRAL_ROW, _TRACK_ROW)
    sb.configure("job_roles", _JOB_ROLE_ROW)

    resp = client.post(share_url(), json=_DEFAULT_BODY)

    assert resp.status_code == 200
    data = resp.json()
    # Apply link must appear in both the preview and as apply_link field
    assert data["apply_link"] in data["message_preview"]
    assert "securetok123" in data["apply_link"]   # link_token from DB row
