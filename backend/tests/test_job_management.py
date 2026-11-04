from __future__ import annotations

from app.services.smart_recruitment_service import generate_job_board_versions
from tests.conftest import ADMIN_ID, EMPLOYEE_ID


BASE = "/api/v1/recruit"
ORG = "11111111-1111-1111-1111-111111111111"
JOB = "22222222-2222-2222-2222-222222222222"
PROPERTY = "33333333-3333-3333-3333-333333333333"


def test_salary_range_validation_happens_before_database(client_as_admin):
    client, _ = client_as_admin
    response = client.post(f"{BASE}/jobs", json={
        "title": "Waiter", "salary_min_inr": 30000, "salary_max_inr": 20000,
    })
    assert response.status_code == 422


def test_experience_range_validation(client_as_admin):
    client, _ = client_as_admin
    response = client.post(f"{BASE}/jobs", json={
        "title": "Chef", "experience_min_years": 5, "experience_max_years": 2,
    })
    assert response.status_code == 422


def test_close_job_records_history(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", [{"id": ADMIN_ID, "org_id": ORG}])
    sb.configure("jobs", [{"id": JOB, "status": "open"}], [{"id": JOB}])
    sb.configure("job_status_history", [{"id": "history-1"}])
    response = client.post(f"{BASE}/jobs/{JOB}/close", json={"notes": "Filled"})
    assert response.status_code == 200
    assert response.json()["status"] == "closed"


def test_reopen_requires_approved_job(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", [{"id": ADMIN_ID, "org_id": ORG}])
    sb.configure("jobs", [{"id": JOB, "status": "closed", "approval_status": "REJECTED"}])
    response = client.post(f"{BASE}/jobs/{JOB}/reopen")
    assert response.status_code == 409


def test_recruiter_cannot_approve_job(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", [{
        "id": EMPLOYEE_ID, "org_id": ORG, "role": "recruiter",
        "department_id": None, "active_property_id": PROPERTY,
    }])
    sb.configure("property_memberships", [{"property_id": PROPERTY, "department_id": None, "is_active": True}])
    response = client.post(f"{BASE}/jobs/{JOB}/approval", json={"decision": "APPROVE"})
    assert response.status_code == 403


def test_hr_manager_can_approve_pending_job(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", [{
        "id": EMPLOYEE_ID, "org_id": ORG, "role": "hr_manager",
        "department_id": None, "active_property_id": PROPERTY,
    }])
    sb.configure("property_memberships", [{"property_id": PROPERTY, "department_id": None, "is_active": True}])
    sb.configure("jobs", [{"id": JOB, "status": "pending_approval", "approval_status": "PENDING_APPROVAL"}], [{"id": JOB}])
    sb.configure("job_status_history", [{"id": "history-2"}])
    response = client.post(f"{BASE}/jobs/{JOB}/approval", json={"decision": "APPROVE"})
    assert response.status_code == 200
    assert response.json()["approval_status"] == "APPROVED"
    assert response.json()["status"] == "open"


def test_duplicate_is_draft_and_has_source_link(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", [{"id": ADMIN_ID, "org_id": ORG}], [{"id": ADMIN_ID, "org_id": ORG, "role": "admin", "active_property_id": PROPERTY}])
    sb.configure("jobs", [{"id": JOB, "org_id": ORG, "title": "Waiter", "property_id": PROPERTY, "department_id": None, "status": "open"}], [{"id": "copy-job", "title": "Waiter (Copy)", "status": "draft", "duplicated_from_job_id": JOB}], [{"id": "copy-job"}])
    sb.configure("properties", [{"id": PROPERTY, "org_id": ORG, "name": "Mumbai Hotel"}])
    sb.configure("job_status_history", [{"id": "history-3"}])
    response = client.post(f"{BASE}/jobs/{JOB}/duplicate", json={})
    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    assert response.json()["duplicated_from_job_id"] == JOB


def test_job_board_versions_include_india_channels_and_bilingual_copy():
    versions = generate_job_board_versions({
        "title": "Front Office Executive", "location_city": "Mumbai",
        "salary_min_inr": 20000, "salary_max_inr": 30000,
        "jd_english": "Welcome guests and manage check-in.",
        "jd_hindi": "अतिथियों का स्वागत करें और चेक-इन संभालें।",
        "apply_url": "https://example.test/apply/job-1",
    })
    assert {"naukri", "apna", "indeed_india", "linkedin", "whatsapp"} <= versions.keys()
    assert "अतिथियों" in versions["apna"]["hindi"]
    assert "₹20,000-₹30,000" in versions["whatsapp"]["english"]
