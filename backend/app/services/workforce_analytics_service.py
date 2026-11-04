"""Deterministic workforce analytics over authoritative HR domain rows."""

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any


ACTIVE_EMPLOYMENT = {"ACTIVE", "PROBATION", "NOTICE_PERIOD"}
EXIT_EVENTS = {"RESIGNED", "TERMINATED", "ABSCONDED", "RETIREMENT", "TRANSFERRED_OUT"}


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _percent(numerator: float, denominator: float) -> float | None:
    return round(numerator * 100 / denominator, 1) if denominator else None


def _employee_scope(employees: list[dict], property_id=None, department_id=None, role=None, employee_id=None):
    output = []
    for employee in employees:
        account_role = str(employee.get("role") or "EMPLOYEE").upper()
        if account_role in {"OWNER", "GROUP_ADMIN_HR", "CANDIDATE"} or not employee.get("active_property_id"):
            continue
        if property_id and employee.get("active_property_id") != property_id:
            continue
        if department_id and employee.get("department_id") != department_id:
            continue
        if role and str(employee.get("job_title") or "Unassigned") != role:
            continue
        if employee_id and employee.get("id") != employee_id:
            continue
        output.append(employee)
    return output


def aggregate_workforce(
    *, employees: list[dict], jobs: list[dict], applications: list[dict],
    attendance: list[dict], payroll_items: list[dict], turnover: list[dict],
    engagement: list[dict], risks: list[dict], performance: list[dict],
    properties: list[dict], departments: list[dict], include_financial: bool,
    property_id: str | None = None, department_id: str | None = None,
    role: str | None = None, employee_id: str | None = None,
) -> dict:
    scoped = _employee_scope(employees, property_id, department_id, role, employee_id)
    employee_ids = {item["id"] for item in scoped}
    active = [item for item in scoped if str(item.get("employment_status") or "ACTIVE").upper() in ACTIVE_EMPLOYMENT]
    active_ids = {item["id"] for item in active}

    scoped_attendance = [item for item in attendance if item.get("employee_id") in employee_ids and item.get("validation_status") == "VALIDATED"]
    absence_days = sum(str(item.get("status")).upper() == "ABSENT" for item in scoped_attendance)
    expected_days = sum(str(item.get("status")).upper() not in {"WEEKLY_OFF", "LEAVE"} for item in scoped_attendance)
    overtime_minutes = sum(int(item.get("overtime_minutes") or 0) for item in scoped_attendance)

    scoped_turnover = [item for item in turnover if item.get("employee_id") in employee_ids and str(item.get("event_type")).upper() in EXIT_EVENTS]
    average_headcount = len(active) + len(scoped_turnover) / 2

    scoped_engagement = [item for item in engagement if item.get("employee_id") in active_ids]
    engagement_values = [_number(item.get("engagement_score")) for item in scoped_engagement]
    scoped_risks = [item for item in risks if item.get("employee_id") in active_ids]
    high_risk = sum(str(item.get("risk_level")).upper() in {"HIGH", "CRITICAL"} for item in scoped_risks)

    latest_performance: dict[str, dict] = {}
    for item in performance:
        employee = item.get("employee_id")
        if employee in active_ids and employee not in latest_performance:
            latest_performance[employee] = item
    performance_values = [
        _number(item.get("overall_score")) if item.get("overall_score") is not None else _number(item.get("rating")) * 20
        for item in latest_performance.values() if item.get("overall_score") is not None or item.get("rating") is not None
    ]

    scoped_payroll = [item for item in payroll_items if item.get("employee_id") in employee_ids and str(item.get("status")).upper() == "FINALIZED"]
    payroll = None
    if include_financial:
        payroll = {
            "gross_inr": round(sum(_number(item.get("gross_inr")) for item in scoped_payroll), 2),
            "net_inr": round(sum(_number(item.get("net_inr")) for item in scoped_payroll), 2),
            "employer_cost_inr": round(sum(_number(item.get("employer_cost_inr")) for item in scoped_payroll), 2),
            "lop_inr": round(sum(_number(item.get("lop_inr")) for item in scoped_payroll), 2),
            "overtime_inr": round(sum(_number(item.get("overtime_inr")) for item in scoped_payroll), 2),
            "employees_paid": len({item.get("employee_id") for item in scoped_payroll}),
            "snapshots": len(scoped_payroll),
        }

    scoped_jobs = [item for item in jobs if (not property_id or item.get("property_id") == property_id)
                   and (not department_id or item.get("department_id") == department_id)]
    if role:
        scoped_jobs = [item for item in scoped_jobs if str(item.get("title") or item.get("role_type")) == role]
    hired_by_job = defaultdict(int)
    for application in applications:
        if str(application.get("status")).upper() == "HIRED":
            hired_by_job[application.get("job_id")] += 1
    open_jobs = [item for item in scoped_jobs if str(item.get("status")).lower() in {"open", "active"}]
    vacancies = sum(max(0, int(item.get("openings_count") or item.get("positions_available") or 1) - hired_by_job[item.get("id")]) for item in open_jobs)

    property_names = {item["id"]: item.get("name") or item["id"] for item in properties}
    department_names = {item["id"]: item.get("name") or item["id"] for item in departments}

    def comparison(field: str, names: dict[str, str]) -> list[dict]:
        identifiers = sorted({item.get(field) for item in scoped if item.get(field)})
        result = []
        for identifier in identifiers:
            child = aggregate_workforce(
                employees=scoped, jobs=scoped_jobs, applications=applications, attendance=attendance,
                payroll_items=payroll_items, turnover=turnover, engagement=engagement, risks=risks,
                performance=performance, properties=properties, departments=departments,
                include_financial=include_financial,
                property_id=identifier if field == "active_property_id" else property_id,
                department_id=identifier if field == "department_id" else department_id,
                role=role, employee_id=employee_id,
            )
            result.append({"id": identifier, "name": names.get(identifier, identifier), **child["summary"]})
        return result

    summary = {
        "headcount": len(active), "vacancies": vacancies, "open_jobs": len(open_jobs),
        "absence_days": absence_days, "absence_rate_pct": _percent(absence_days, expected_days),
        "overtime_hours": round(overtime_minutes / 60, 1), "turnover_count": len(scoped_turnover),
        "attrition_rate_pct": _percent(len(scoped_turnover), average_headcount),
        "engagement_score": round(sum(engagement_values) / len(engagement_values), 1) if engagement_values else None,
        "engagement_sample": len(engagement_values), "high_turnover_risk": high_risk,
        "turnover_risk_assessed": len(scoped_risks),
        "productivity_score": round(sum(performance_values) / len(performance_values), 1) if performance_values else None,
        "productivity_sample": len(performance_values), "payroll": payroll,
    }
    response = {"summary": summary}
    if not property_id and not department_id and not role and not employee_id:
        response["property_comparison"] = comparison("active_property_id", property_names)
    if not department_id and not role and not employee_id:
        response["department_comparison"] = comparison("department_id", department_names)
    response["roles"] = sorted({str(item.get("job_title") or "Unassigned") for item in active})
    response["employees"] = [{
        "id": item["id"], "employee_code": item.get("employee_code"), "name": item.get("full_name"),
        "role": item.get("job_title") or "Unassigned", "property_id": item.get("active_property_id"),
        "department_id": item.get("department_id"), "employment_status": item.get("employment_status") or "ACTIVE",
    } for item in active]
    response["methodology"] = {
        "headcount": "active users employment records",
        "attendance": "validated attendance_daily_records only",
        "payroll": "immutable FINALIZED payroll_run_items only",
        "attrition": "exit events / average headcount for selected period",
        "engagement": "current persisted employee engagement scores",
        "turnover_risk": "current transparent retention risk scores",
        "productivity": "latest completed performance/KPI score; unavailable without reviews",
    }
    return response
