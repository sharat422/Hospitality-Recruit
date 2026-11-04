from app.services.executive_dashboard_service import compose_executive_dashboard


def workforce(financial=True):
    payroll = {"gross_inr": 100000, "net_inr": 85000, "employer_cost_inr": 110000, "lop_inr": 2000, "overtime_inr": 3000} if financial else None
    return {"summary": {"headcount": 10, "vacancies": 3, "high_turnover_risk": 2, "overtime_hours": 20, "payroll": payroll}, "property_comparison": [{"id": "p1", "name": "Hotel A", "headcount": 10, "vacancies": 3}]}


def test_executive_kpis_and_alerts_are_composed_from_rows():
    result = compose_executive_dashboard(
        workforce=workforce(),
        today_attendance=[{"status": "PRESENT"}, {"status": "ABSENT"}, {"status": "MISSING_PUNCH"}],
        approved_leave=[{"employee_id": "e4"}],
        compliance_tasks=[{"due_date": "2020-01-01"}],
        expiring_certificates=[{"id": "cert"}],
        revenue_entries=[{"amount_inr": 500000}],
        applications=[{"source": "NAUKRI", "status": "HIRED"}, {"source": "NAUKRI", "status": "INTERVIEW"}],
        financial_visible=True,
    )
    assert result["today"] == {"attendance_records": 3, "present": 1, "absent": 1, "on_leave": 1, "missing_punch": 1}
    assert result["labour_cost_inr"] == 110000
    assert result["revenue"] == {"total_inr": 500000.0, "per_employee_inr": 50000.0, "entries": 1}
    assert result["source_performance"][0]["conversion_pct"] == 50
    assert {item["type"] for item in result["alerts"]} == {"ABSENCE", "ATTENDANCE", "VACANCY", "RETENTION", "COMPLIANCE", "CERTIFICATE"}


def test_financial_values_are_redacted_server_side():
    result = compose_executive_dashboard(
        workforce=workforce(False), today_attendance=[], approved_leave=[], compliance_tasks=[],
        expiring_certificates=[], revenue_entries=[{"amount_inr": 999999}], applications=[],
        financial_visible=False,
    )
    assert result["payroll"] is None
    assert result["labour_cost_inr"] is None
    assert result["revenue"] == {"total_inr": None, "per_employee_inr": None, "entries": None}


def test_revenue_per_employee_is_unavailable_without_headcount():
    base = workforce()
    base["summary"]["headcount"] = 0
    result = compose_executive_dashboard(workforce=base, today_attendance=[], approved_leave=[], compliance_tasks=[], expiring_certificates=[], revenue_entries=[{"amount_inr": 100}], applications=[], financial_visible=True)
    assert result["revenue"]["per_employee_inr"] is None
