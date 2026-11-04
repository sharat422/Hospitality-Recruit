from datetime import datetime, timedelta, timezone

from app.services.job_distribution_service import CHANNELS, export_csv, platform_content
from app.services.smart_recruitment_service import move_candidate_stage, verify_apply_otp
from tests.conftest import ADMIN_ID, MockSupabase

BASE = "/api/v1/distribution"
ORG = "11111111-1111-1111-1111-111111111111"
JOB = "22222222-2222-2222-2222-222222222222"
DIST = "33333333-3333-3333-3333-333333333333"
TOKEN = "44444444-4444-4444-4444-444444444444"
CAND = "55555555-5555-5555-5555-555555555555"
APP = "66666666-6666-6666-6666-666666666666"


def test_external_boards_are_manual_export_not_fake_api():
    for key in ("naukri", "apna", "workindia", "shine", "indeed", "linkedin", "hospitality_board"):
        assert CHANNELS[key][1] == "MANUAL_EXPORT"


def test_platform_content_and_csv_export():
    job = {"id": JOB, "title": "Waiter", "property_name": "Hotel A", "location_city": "Pune",
           "salary_min_inr": 15000, "salary_max_inr": 20000, "openings_count": 4,
           "jd_english": "Serve guests", "jd_hindi": "अतिथियों की सेवा करें"}
    english, hindi = platform_content(job, "workindia")
    assert "Serve guests" in english and "अतिथियों" in hindi
    data = export_csv([{"job_id": JOB, "channel_key": "workindia", "content_english": english,
                        "content_hindi": hindi, "posting_url": "https://track.test/x"}], {JOB: job})
    assert "workindia" in data and "15000" in data and "Hotel A" in data


def test_prepare_rejects_unknown_channel(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", [{"id": ADMIN_ID, "org_id": ORG}])
    sb.configure("jobs", [{"id": JOB, "org_id": ORG, "title": "Waiter"}])
    response = client.post(f"{BASE}/jobs/{JOB}/prepare", json={"channels": ["imaginary_board"]})
    assert response.status_code == 422


def test_publish_requires_open_approved_job(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", [{"id": ADMIN_ID, "org_id": ORG}])
    sb.configure("job_distributions", [{"id": DIST, "org_id": ORG, "job_id": JOB,
        "delivery_mode": "MANUAL_EXPORT", "attribution_token": TOKEN}])
    sb.configure("jobs", [{"id": JOB, "status": "draft", "approval_status": "DRAFT"}])
    response = client.post(f"{BASE}/{DIST}/publish", json={})
    assert response.status_code == 409


def test_click_to_application_to_hire_attribution(client_as_admin):
    client, sb = client_as_admin
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    distribution = {"id": DIST, "org_id": ORG, "job_id": JOB, "channel_key": "naukri",
                    "attribution_token": TOKEN, "status": "PUBLISHED", "expires_at": future,
                    "click_count": 0, "application_count": 0, "hire_count": 0}
    sb.configure("job_distributions", [distribution], [{"id": DIST}])
    sb.configure("job_distribution_events", [{"id": "click-event"}])
    click = client.get(f"{BASE}/t/{TOKEN}", follow_redirects=False)
    assert click.status_code == 302
    assert "src=naukri" in click.headers["location"] and f"dist={TOKEN}" in click.headers["location"]

    apply_db = MockSupabase()
    apply_db.configure("mobile_otp_sessions",
        [{"id": "otp", "otp": "123456", "expires_at": future, "verified": False, "attempts": 0}],
        [{"id": "otp"}], [{"id": "otp"}])
    apply_db.configure("job_distributions", [distribution], [{"id": DIST}])
    apply_db.configure("candidates", [], [{"id": CAND, "source": "naukri"}], [{"source": "naukri"}])
    apply_db.configure("jobs", [{"property_id": None, "department_id": None}], [{"id": JOB}])
    apply_db.configure("applications", [{"id": APP}])
    apply_db.configure("job_distribution_events", [{"id": "application-event"}])
    applied = verify_apply_otp(apply_db, "+919999999999", "123456", JOB, ORG,
        {"name": "Test Worker", "source": "other", "distribution_token": TOKEN})
    assert applied["verified"] is True
    assert applied["application_id"] == APP
    assert applied["source"] == "naukri"

    hire_db = MockSupabase()
    hire_db.configure("candidates", [{"id": CAND, "org_id": ORG, "applied_job_id": JOB, "distribution_id": DIST}])
    hire_db.configure("applications", [{"id": APP}])
    hire_db.configure("job_distributions", [{"hire_count": 0}], [{"id": DIST}])
    hire_db.configure("job_distribution_events", [{"id": "hire-event"}])
    result = move_candidate_stage(hire_db, ORG, CAND, "hired")
    assert result == {"updated": True, "new_stage": "hired"}
