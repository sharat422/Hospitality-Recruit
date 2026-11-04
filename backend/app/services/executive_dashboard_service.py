"""Pure executive KPI composition; unavailable data is never fabricated."""
from collections import defaultdict
from datetime import date
from typing import Any


DEFAULT_WIDGETS = [
    "attendance", "leave", "absence", "vacancies", "payroll", "compliance",
    "turnover_risk", "property_comparison", "labour_cost", "overtime",
    "revenue_per_employee", "source_performance", "alerts",
]


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def compose_executive_dashboard(*, workforce: dict, today_attendance: list[dict],
                                approved_leave: list[dict], compliance_tasks: list[dict],
                                expiring_certificates: list[dict], revenue_entries: list[dict],
                                applications: list[dict], financial_visible: bool) -> dict:
    summary = workforce["summary"]
    present = sum(str(row.get("status")).upper() == "PRESENT" for row in today_attendance)
    absent = sum(str(row.get("status")).upper() == "ABSENT" for row in today_attendance)
    missing = sum(str(row.get("status")).upper() == "MISSING_PUNCH" for row in today_attendance)
    on_leave = len({row.get("employee_id") for row in approved_leave})
    overdue = sum(row.get("due_date") and str(row["due_date"])[:10] < date.today().isoformat() for row in compliance_tasks)
    revenue = round(sum(_num(row.get("amount_inr")) for row in revenue_entries), 2) if financial_visible else None
    revenue_per_employee = round(revenue / summary["headcount"], 2) if revenue is not None and summary["headcount"] else None

    source = defaultdict(lambda: {"applications": 0, "hires": 0})
    for application in applications:
        key = str(application.get("source") or "UNKNOWN").upper()
        source[key]["applications"] += 1
        source[key]["hires"] += str(application.get("status")).upper() == "HIRED"
    source_rows = [{"source": key, **values,
                    "conversion_pct": round(values["hires"] * 100 / values["applications"], 1)}
                   for key, values in sorted(source.items(), key=lambda item: item[1]["applications"], reverse=True)]

    alerts = []
    if absent:
        alerts.append({"severity": "HIGH", "type": "ABSENCE", "message": f"{absent} employee(s) absent today"})
    if missing:
        alerts.append({"severity": "MEDIUM", "type": "ATTENDANCE", "message": f"{missing} missing punch record(s) today"})
    if summary["vacancies"]:
        alerts.append({"severity": "MEDIUM", "type": "VACANCY", "message": f"{summary['vacancies']} open position(s) remain unfilled"})
    if summary["high_turnover_risk"]:
        alerts.append({"severity": "HIGH", "type": "RETENTION", "message": f"{summary['high_turnover_risk']} employee(s) have high/critical turnover risk"})
    if overdue:
        alerts.append({"severity": "CRITICAL", "type": "COMPLIANCE", "message": f"{overdue} compliance task(s) overdue"})
    if expiring_certificates:
        alerts.append({"severity": "HIGH", "type": "CERTIFICATE", "message": f"{len(expiring_certificates)} certificate(s) expired or due within 30 days"})

    return {
        "today": {"attendance_records": len(today_attendance), "present": present, "absent": absent,
                  "on_leave": on_leave, "missing_punch": missing},
        "workforce": summary,
        "property_comparison": workforce.get("property_comparison", []),
        "payroll": summary.get("payroll") if financial_visible else None,
        "labour_cost_inr": summary.get("payroll", {}).get("employer_cost_inr") if financial_visible and summary.get("payroll") else None,
        "overtime": {"hours": summary["overtime_hours"],
                     "cost_inr": summary.get("payroll", {}).get("overtime_inr") if financial_visible and summary.get("payroll") else None},
        "revenue": {"total_inr": revenue, "per_employee_inr": revenue_per_employee,
                    "entries": len(revenue_entries) if financial_visible else None},
        "compliance": {"open_tasks": len(compliance_tasks), "overdue_tasks": overdue,
                       "certificates_due_30_days": len(expiring_certificates)},
        "source_performance": source_rows,
        "alerts": alerts,
        "financial_visible": financial_visible,
    }
