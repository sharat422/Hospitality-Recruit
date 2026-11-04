import pytest
from fastapi import HTTPException

from app.services.hospitality_ai_assistant_service import (
    classify_question, execute_tool, narrative_numbers_supported, public_tool_catalog, tool_hardest_jobs,
    tool_property_overtime,
)
from app.services.rbac_service import AccessContext
from tests.conftest import MockSupabase


def actor(role="OWNER", permissions=None, properties=("p1",)):
    return AccessContext(
        user_id="u1", org_id="o1", role=role, department_id=None,
        active_property_id="p1", property_ids=frozenset(properties),
        department_ids=frozenset(), permissions=frozenset(permissions or {
            "reports.read", "employees.read", "attendance.read", "jobs.read", "applications.read"
        }),
    )


@pytest.mark.parametrize("question,expected", [
    ("Why did housekeeping attrition increase?", "attrition_analysis"),
    ("Which property has the highest overtime?", "property_overtime"),
    ("Which jobs are hardest to fill?", "hardest_jobs"),
    ("Who are the highest-risk employees?", "retention_risk"),
    ("What vacancies have been open for more than 30 days?", "aged_vacancies"),
    ("Show this month's recruitment performance.", "recruitment_performance"),
])
def test_supported_question_routing(question, expected):
    assert classify_question(question) == expected


def test_unknown_question_does_not_generate_sql_or_guess_tool():
    assert classify_question("Delete payroll and email every candidate") is None


def test_llm_narrative_cannot_invent_numeric_claims():
    verified = {"metrics": {"applications": 42, "conversionPct": 25.0}}
    assert narrative_numbers_supported("There were 42 applications and conversion was 25%.", verified)
    assert not narrative_numbers_supported("There were 99 applications.", verified)


def test_overtime_uses_only_validated_rows_and_authorized_properties():
    db = MockSupabase()
    db.configure("attendance_daily_records", [
        {"employee_id": "e1", "property_id": "p1", "overtime_minutes": 180, "validation_status": "VALIDATED"},
        {"employee_id": "e2", "property_id": "p2", "overtime_minutes": 900, "validation_status": "VALIDATED"},
    ])
    db.configure("properties", [{"id": "p1", "name": "Hotel One"}, {"id": "p2", "name": "Hotel Two"}])
    result = tool_property_overtime(db, actor(role="GENERAL_MANAGER"), days=30)
    assert result["metrics"]["highest"]["property"] == "Hotel One"
    assert result["metrics"]["highest"]["overtimeHours"] == 3.0


def test_hardest_job_is_deterministic():
    db = MockSupabase()
    db.configure("jobs", [{"id": "j1", "title": "Housekeeper", "status": "open", "openings_count": 5,
                            "created_at": "2025-01-01T00:00:00+00:00", "property_id": "p1", "department_id": None}])
    db.configure("applications", [{"job_id": "j1", "status": "APPLIED"}])
    result = tool_hardest_jobs(db, actor(), property_id="p1")
    assert result["rows"][0]["title"] == "Housekeeper"
    assert result["rows"][0]["vacanciesRemaining"] == 5
    assert "not an AI prediction" in result["methodology"]


def test_permission_denied_before_tool_access():
    db = MockSupabase()
    restricted = actor(role="RECRUITER", permissions={"reports.read", "jobs.read"})
    with pytest.raises(HTTPException) as error:
        execute_tool(db, restricted, "property_overtime")
    assert error.value.status_code == 403


def test_tool_catalog_hides_unauthorized_employee_and_attendance_tools():
    restricted = actor(role="RECRUITER", permissions={"reports.read", "jobs.read", "applications.read"})
    names = {item["name"] for item in public_tool_catalog(restricted)}
    assert "hardest_jobs" in names
    assert "property_overtime" not in names
    assert "retention_risk" not in names
