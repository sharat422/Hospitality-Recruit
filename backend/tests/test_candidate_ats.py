from __future__ import annotations

from app.services.candidate_ats_service import (
    PIPELINE_STAGES,
    duplicate_reasons,
    matches_candidate,
    normalize_phone,
    stage_update,
)

ORG_ID = "11111111-1111-1111-1111-111111111111"
CANDIDATE_ID = "22222222-2222-2222-2222-222222222222"
OTHER_CANDIDATE_ID = "33333333-3333-3333-3333-333333333333"
APPLICATION_ID = "44444444-4444-4444-4444-444444444444"
INTERVIEW_ID = "55555555-5555-5555-5555-555555555555"


def org_row():
    return [{"org_id": ORG_ID, "role": "OWNER"}]


def candidate_row(**overrides):
    row = {
        "id": CANDIDATE_ID,
        "org_id": ORG_ID,
        "first_name": "Asha",
        "last_name": "Rao",
        "email": "asha@example.com",
        "phone": "+91 98765 43210",
        "city": "Mumbai",
        "pipeline_stage": "screened",
        "years_experience": 4,
        "parsed_skills": ["Opera PMS", "Guest relations"],
        "languages": ["Hindi", "English"],
        "tags": ["night-shift"],
    }
    row.update(overrides)
    return row


def test_pipeline_has_required_order():
    assert PIPELINE_STAGES == [
        "applied", "screened", "shortlisted", "interview", "selected",
        "offer", "offer_accepted", "onboarding", "hired",
    ]


def test_duplicate_detection_normalizes_contact_fields():
    other = candidate_row(email=" ASHA@EXAMPLE.COM ", phone="9876543210")
    assert duplicate_reasons(candidate_row(), other) == ["email", "phone"]
    assert normalize_phone("+91-98765-43210") == "9876543210"


def test_candidate_filters_cover_profile_fields():
    row = candidate_row()
    assert matches_candidate(row, search="98765", location="mumbai", tags=["night-shift"],
                             skills=["opera pms"], languages=["hindi"], min_experience=3)
    assert not matches_candidate(row, skills=["HACCP"])
    assert not matches_candidate(row, min_experience=5)


def test_stage_update_sets_timestamp_and_qualification():
    values = stage_update("shortlisted")
    assert values["pipeline_stage"] == "shortlisted"
    assert values["qualified"] is True
    assert values["shortlisted_at"]


def test_search_candidates(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", org_row())
    sb.configure("candidates", [candidate_row(), candidate_row(id=OTHER_CANDIDATE_ID, first_name="Ravi", city="Delhi")])
    response = client.get("/api/v1/ats/candidates?search=Asha&location=Mumbai&skills=Opera%20PMS")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["candidates"][0]["id"] == CANDIDATE_ID


def test_duplicate_endpoint(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", org_row())
    sb.configure("candidates", [candidate_row()], [
        candidate_row(),
        candidate_row(id=OTHER_CANDIDATE_ID, email="ASHA@example.com", phone="9876543210"),
    ])
    response = client.get(f"/api/v1/ats/candidates/{CANDIDATE_ID}/duplicates")
    assert response.status_code == 200
    duplicate = response.json()["duplicates"][0]
    assert duplicate["candidate"]["id"] == OTHER_CANDIDATE_ID
    assert set(duplicate["matched_on"]) == {"email", "phone"}


def test_stage_change_updates_application_candidate_and_history(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", org_row())
    sb.configure("applications", [{
        "id": APPLICATION_ID, "org_id": ORG_ID, "candidate_id": CANDIDATE_ID,
        "job_id": None, "status": "SCREENED",
    }], [{"id": APPLICATION_ID}])
    sb.configure("candidates", [candidate_row()], [candidate_row(pipeline_stage="shortlisted")])
    sb.configure("application_stage_history", [{"id": "history-1"}])
    response = client.patch(f"/api/v1/ats/applications/{APPLICATION_ID}/stage", json={"stage": "shortlisted"})
    assert response.status_code == 200
    assert response.json()["from_stage"] == "screened"
    assert response.json()["to_stage"] == "shortlisted"


def test_invalid_stage_is_rejected(client_as_admin):
    client, sb = client_as_admin
    response = client.patch(f"/api/v1/ats/applications/{APPLICATION_ID}/stage", json={"stage": "unknown"})
    assert response.status_code == 422


def test_bulk_add_tag(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", org_row())
    sb.configure("candidates", [candidate_row()], [candidate_row(tags=["night-shift", "vip"])])
    response = client.post("/api/v1/ats/candidates/bulk-action", json={
        "candidate_ids": [CANDIDATE_ID], "action": "tag", "tags": ["vip"],
    })
    assert response.status_code == 200
    assert response.json() == {"processed": 1, "errors": []}


def test_bulk_stage_keeps_application_and_history_in_sync(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", org_row())
    sb.configure("candidates", [candidate_row()], [candidate_row(pipeline_stage="interview")])
    sb.configure("applications", [{
        "id": APPLICATION_ID, "org_id": ORG_ID, "candidate_id": CANDIDATE_ID,
        "job_id": None, "status": "SHORTLISTED",
    }], [{"id": APPLICATION_ID}])
    sb.configure("application_stage_history", [{"id": "history-1"}])
    response = client.post("/api/v1/ats/candidates/bulk-action", json={
        "candidate_ids": [CANDIDATE_ID], "action": "stage", "stage": "interview",
    })
    assert response.status_code == 200
    assert response.json() == {"processed": 1, "errors": []}


def test_feedback_updates_existing_interview(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", org_row())
    sb.configure("interviews", [{"id": INTERVIEW_ID, "candidate_id": CANDIDATE_ID, "org_id": ORG_ID}], [{"id": INTERVIEW_ID}])
    response = client.patch(f"/api/v1/ats/interviews/{INTERVIEW_ID}/feedback", json={
        "rating": 4.5, "notes": "Strong guest recovery example", "recommendation": "HIRE",
        "competencies": {"communication": 5},
    })
    assert response.status_code == 200
    assert response.json()["recommendation"] == "HIRE"
    assert response.json()["status"] == "completed"


def test_feedback_falls_back_to_engagement_slot(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", org_row())
    sb.configure("interviews", [])
    sb.configure("interview_slots", [{"id": INTERVIEW_ID, "candidate_id": CANDIDATE_ID}], [{"id": INTERVIEW_ID}])
    sb.configure("candidates", [candidate_row()])
    response = client.patch(f"/api/v1/ats/interviews/{INTERVIEW_ID}/feedback", json={
        "rating": 4, "notes": "Proceed to final round", "recommendation": "HIRE",
    })
    assert response.status_code == 200


def test_profile_is_tenant_scoped(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", org_row())
    sb.configure("candidates", [])
    response = client.get(f"/api/v1/ats/candidates/{CANDIDATE_ID}")
    assert response.status_code == 404
