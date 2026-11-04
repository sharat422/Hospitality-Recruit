"""Shared employee exit rules, settlement snapshots and lifecycle writes."""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from html import escape
import json

DEFAULT_CLEARANCE = [
    ("DEPARTMENT","Department handover"),("IT","Devices and access"),("FINANCE","Loans and advances"),
    ("PAYROLL","Payroll verification"),("ACCOMMODATION","Accommodation handover"),("SECURITY","ID card and keys"),
    ("UNIFORM","Uniform return"),("DOCUMENTS","Document return"),
]

def money(value): return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def calculate_final_settlement(data: dict) -> dict:
    monthly = money(data.get("monthly_gross_inr")); days = max(0, min(31, int(data.get("payable_days") or 0)))
    earned_salary = (monthly / Decimal(30) * days).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    gross = earned_salary + money(data.get("leave_encashment_inr")) + money(data.get("gratuity_inr")) + money(data.get("bonus_inr")) + money(data.get("reimbursements_inr")) + money(data.get("other_earnings_inr"))
    deductions = money(data.get("notice_recovery_inr")) + money(data.get("loan_recovery_inr")) + money(data.get("asset_recovery_inr")) + money(data.get("tax_inr")) + money(data.get("other_deductions_inr"))
    snapshot = {**data,"earned_salary_inr":float(earned_salary),"gross_payable_inr":float(gross),"total_deductions_inr":float(deductions),"net_payable_inr":float(gross-deductions)}
    digest = sha256(json.dumps(snapshot,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    return {"settlement_snapshot":snapshot,"gross_payable_inr":float(gross),"total_deductions_inr":float(deductions),"net_payable_inr":float(gross-deductions),"snapshot_hash":digest}

def clearance_summary(items: list[dict]) -> dict:
    blockers=[x for x in items if x.get("status") not in {"CLEARED","NOT_APPLICABLE"}]
    return {"total":len(items),"cleared":len(items)-len(blockers),"blocked":len(blockers),"ready":not blockers,"amount_due_inr":float(sum(money(x.get("amount_due_inr")) for x in items))}

def experience_letter_html(employee: dict, case: dict, property_name: str) -> str:
    name=escape(str(employee.get("full_name") or "Employee")); role=escape(str(employee.get("job_title") or "Employee")); hotel=escape(property_name or "the organization")
    joined=escape(str(employee.get("joining_date") or "recorded joining date")); ended=escape(str(case.get("approved_last_working_date") or case.get("requested_last_working_date")))
    return f"<article><h1>Experience Letter</h1><p>To whom it may concern</p><p>This is to certify that <strong>{name}</strong> worked with <strong>{hotel}</strong> as <strong>{role}</strong> from {joined} to {ended}.</p><p>During this period, the employee performed assigned responsibilities in the hospitality operation. We wish them success in future endeavours.</p><p>Authorized Signatory<br>{hotel}</p></article>"

def append_lifecycle(db, *, org_id, employee, event_type, title, source_table, source_id, created_by, description=None, visibility="EMPLOYEE", metadata=None):
    db.table("employee_lifecycle_events").insert({"org_id":org_id,"employee_id":employee["id"],"property_id":employee.get("active_property_id"),"department_id":employee.get("department_id"),"event_type":event_type,"title":title,"description":description,"source_table":source_table,"source_id":source_id,"visibility":visibility,"created_by":created_by,"metadata":metadata or {}}).execute()
