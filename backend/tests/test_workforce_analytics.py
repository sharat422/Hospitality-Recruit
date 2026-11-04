from app.services.workforce_analytics_service import aggregate_workforce


BASE = dict(properties=[{"id": "p1", "name": "Hotel A"}], departments=[{"id": "d1", "name": "F&B", "property_id": "p1"}])


def test_workforce_metrics_use_authoritative_records():
    result = aggregate_workforce(
        employees=[
            {"id": "e1", "role": "EMPLOYEE", "employment_status": "ACTIVE", "active_property_id": "p1", "department_id": "d1", "job_title": "Server"},
            {"id": "e2", "role": "EMPLOYEE", "employment_status": "ACTIVE", "active_property_id": "p1", "department_id": "d1", "job_title": "Server"},
            {"id": "owner", "role": "OWNER", "employment_status": "ACTIVE", "active_property_id": "p1"},
        ],
        jobs=[{"id": "j1", "status": "open", "openings_count": 3, "property_id": "p1", "department_id": "d1", "title": "Server"}],
        applications=[{"job_id": "j1", "status": "HIRED"}],
        attendance=[
            {"employee_id": "e1", "status": "ABSENT", "validation_status": "VALIDATED", "overtime_minutes": 0},
            {"employee_id": "e2", "status": "PRESENT", "validation_status": "VALIDATED", "overtime_minutes": 120},
            {"employee_id": "e2", "status": "ABSENT", "validation_status": "PENDING", "overtime_minutes": 999},
        ],
        payroll_items=[{"employee_id": "e1", "status": "FINALIZED", "gross_inr": 30000, "net_inr": 26000, "employer_cost_inr": 34000, "lop_inr": 1000, "overtime_inr": 0}],
        turnover=[{"employee_id": "e1", "event_type": "RESIGNED"}],
        engagement=[{"employee_id": "e1", "engagement_score": 60}, {"employee_id": "e2", "engagement_score": 80}],
        risks=[{"employee_id": "e1", "risk_level": "HIGH"}, {"employee_id": "e2", "risk_level": "LOW"}],
        performance=[{"employee_id": "e1", "overall_score": 70}, {"employee_id": "e2", "rating": 4}],
        include_financial=True, **BASE,
    )
    summary = result["summary"]
    assert summary["headcount"] == 2
    assert summary["vacancies"] == 2
    assert summary["absence_days"] == 1
    assert summary["absence_rate_pct"] == 50
    assert summary["overtime_hours"] == 2
    assert summary["engagement_score"] == 70
    assert summary["high_turnover_risk"] == 1
    assert summary["productivity_score"] == 75
    assert summary["payroll"]["net_inr"] == 26000


def test_financial_metrics_are_not_returned_without_permission():
    result = aggregate_workforce(
        employees=[{"id": "e1", "role": "EMPLOYEE", "employment_status": "ACTIVE", "active_property_id": "p1", "department_id": "d1"}],
        jobs=[], applications=[], attendance=[], payroll_items=[{"employee_id": "e1", "status": "FINALIZED", "net_inr": 999999}],
        turnover=[], engagement=[], risks=[], performance=[], include_financial=False, **BASE,
    )
    assert result["summary"]["payroll"] is None


def test_drilldown_scopes_role_and_employee():
    employees = [
        {"id": "e1", "role": "EMPLOYEE", "employment_status": "ACTIVE", "active_property_id": "p1", "department_id": "d1", "job_title": "Server"},
        {"id": "e2", "role": "EMPLOYEE", "employment_status": "ACTIVE", "active_property_id": "p1", "department_id": "d1", "job_title": "Chef"},
    ]
    common = dict(employees=employees, jobs=[], applications=[], attendance=[], payroll_items=[], turnover=[], engagement=[], risks=[], performance=[], include_financial=True, **BASE)
    assert aggregate_workforce(**common, role="Chef")["summary"]["headcount"] == 1
    assert aggregate_workforce(**common, employee_id="e1")["employees"][0]["id"] == "e1"


def test_missing_samples_are_unavailable_not_zero():
    result = aggregate_workforce(employees=[], jobs=[], applications=[], attendance=[], payroll_items=[], turnover=[], engagement=[], risks=[], performance=[], include_financial=True, **BASE)
    assert result["summary"]["absence_rate_pct"] is None
    assert result["summary"]["attrition_rate_pct"] is None
    assert result["summary"]["engagement_score"] is None
    assert result["summary"]["productivity_score"] is None
