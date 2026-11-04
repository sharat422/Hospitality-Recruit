"""Unified Employee 360 aggregation over existing HR and recruitment entities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.services.rbac_service import AccessContext, authorize


def _rows(result: Any) -> list[dict]:
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


def _safe_rows(query) -> list[dict]:
    try:
        return _rows(query.execute())
    except Exception:
        return []


def _mask(value: str | None, visible: int = 4) -> str | None:
    if not value:
        return None
    text = str(value)
    return "*" * max(4, len(text) - visible) + text[-visible:]


def redact_upi(row: dict, *, self_view: bool) -> dict:
    if not row:
        return {}
    allowed = {"id", "user_id", "upi_id", "is_verified", "verification_method", "created_at", "updated_at"}
    result = {k: v for k, v in row.items() if k in allowed}
    upi = str(row.get("upi_id") or "")
    if upi and not self_view and "@" in upi:
        name, handle = upi.split("@", 1)
        result["upi_id"] = f"{name[:2]}***@{handle}"
    return result


def redact_statutory(row: dict) -> dict:
    """Return display-safe statutory identifiers; full values never leave API."""
    if not row:
        return {}
    return {
        "status": row.get("status"),
        "epf_uan_masked": _mask(row.get("epf_uan")),
        "epf_member_id_masked": _mask(row.get("epf_member_id")),
        "esic_ip_number_masked": _mask(row.get("esic_ip_number")),
        "epf_joining_date": row.get("epf_joining_date"),
        "esic_eligible": row.get("esic_eligible"),
    }


def _candidate_for_employee(supabase, employee: dict) -> dict | None:
    rows = _safe_rows(supabase.table("candidates").select("*").eq("user_id", employee["id"]).limit(1))
    if not rows and employee.get("email"):
        rows = _safe_rows(supabase.table("candidates").select("*").eq("org_id", employee["org_id"])
                          .eq("email", employee["email"]).limit(1))
    return rows[0] if rows else None


def get_employee_360(supabase, context: AccessContext, employee_id: str) -> dict:
    employees = _safe_rows(supabase.table("users").select(
        "id,org_id,email,full_name,phone,role,department_id,active_property_id,employee_code,"
        "job_title,employment_type,employment_status,joining_date,manager_id,created_at"
    ).eq("id", employee_id).eq("org_id", context.org_id).limit(1))
    if not employees:
        raise HTTPException(404, "Employee not found")
    employee = employees[0]
    self_view = context.user_id == employee_id
    if not self_view:
        authorize(context, "employees.read", property_id=employee.get("active_property_id"),
                  department_id=employee.get("department_id"))

    candidate = _candidate_for_employee(supabase, employee)
    candidate_id = candidate.get("id") if candidate else None
    visible = {"personal", "employment", "performance", "attendance", "leave", "training", "career", "timeline"}
    if self_view or "documents.read" in context.permissions:
        visible |= {"documents", "certifications"}
    if self_view or "payroll.read" in context.permissions:
        visible.add("financial")
        visible.add("payroll")
    if self_view or "compliance.read" in context.permissions:
        visible.add("statutory")
    if "employees.manage" in context.permissions:
        visible.add("disciplinary")

    properties = _safe_rows(supabase.table("properties").select("id,name,location").eq(
        "id", employee.get("active_property_id")).limit(1)) if employee.get("active_property_id") else []
    departments = _safe_rows(supabase.table("property_departments").select("id,name,code").eq(
        "id", employee.get("department_id")).limit(1)) if employee.get("department_id") else []
    managers = _safe_rows(supabase.table("users").select("id,full_name,email").eq(
        "id", employee.get("manager_id")).limit(1)) if employee.get("manager_id") else []

    sections: dict[str, Any] = {
        "personal": {
            "id": employee["id"], "full_name": employee.get("full_name"), "email": employee.get("email"),
            "phone": employee.get("phone"), "preferred_language": candidate.get("preferred_language") if candidate else None,
            "location": (candidate.get("location") or candidate.get("city")) if candidate else None,
        },
        "employment": {
            "employee_code": employee.get("employee_code"), "job_title": employee.get("job_title"),
            "employment_type": employee.get("employment_type"), "employment_status": employee.get("employment_status"),
            "joining_date": employee.get("joining_date"), "role": employee.get("role"),
            "property": properties[0] if properties else None, "department": departments[0] if departments else None,
            "manager": managers[0] if managers else None,
        },
        "performance": _safe_rows(supabase.table("employee_performance_reviews").select("*")
                                  .eq("employee_id", employee_id).order("review_period_end", desc=True)),
        "training": _safe_rows(supabase.table("employee_training_records").select("*")
                               .eq("employee_id", employee_id).order("assigned_at", desc=True)),
        "attendance": {
            "daily_records": _safe_rows(supabase.table("attendance_daily_records").select("*")
                                        .eq("employee_id", employee_id).order("attendance_date", desc=True).limit(90)),
            "corrections": _safe_rows(supabase.table("attendance_corrections").select("*")
                                      .eq("employee_id", employee_id).order("created_at", desc=True).limit(30)),
            "working_hours": _safe_rows(supabase.table("working_hours_compliance").select("*")
                                        .eq("employee_id", employee_id).order("shift_date", desc=True).limit(90)),
            "shifts": _safe_rows(supabase.table("v_employee_shifts").select("*")
                                 .eq("employee_id", employee_id).order("start_date", desc=True).limit(30)),
        },
        "leave": {
            "balances": _safe_rows(supabase.table("leave_balances").select("*").eq("employee_id", employee_id)
                                   .order("year", desc=True).limit(2)),
            "requests": _safe_rows(supabase.table("leave_requests").select("*").eq("employee_id", employee_id)
                                   .order("leave_date", desc=True).limit(50)),
        },
        "career": {
            "applications": _safe_rows(supabase.table("applications").select("id,job_id,status,source,created_at")
                                       .eq("candidate_id", candidate_id).order("created_at", desc=True)) if candidate_id else [],
            "skills": candidate.get("parsed_skills") if candidate else {},
            "work_history": candidate.get("work_history") if candidate else [],
        },
    }

    if "financial" in visible:
        upi_rows = _safe_rows(supabase.table("employee_upi_details").select("*").eq("user_id", employee_id).limit(1))
        sections["financial"] = {
            "upi": redact_upi(upi_rows[0], self_view=self_view) if upi_rows else None,
            "current_ctc_inr": candidate.get("current_ctc") if candidate else None,
        }
        sections["payroll"] = _safe_rows(supabase.table("payslips").select("*").eq("employee_id", employee_id)
                                         .order("year", desc=True).order("month", desc=True).limit(24))
    if "statutory" in visible:
        registrations = _safe_rows(supabase.table("epf_esic_registrations").select("*")
                                   .eq("candidate_id", candidate_id).limit(1)) if candidate_id else []
        identities = _safe_rows(supabase.table("india_identity_verifications").select(
            "doc_type,status,aadhaar_last4,aadhaar_masked,pan_masked,pan_name_match,verified_at,doc_expiry_date"
        ).eq("candidate_id", candidate_id)) if candidate_id else []
        safe_identity = []
        for item in identities:
            safe_identity.append({
                "doc_type": item.get("doc_type"), "status": item.get("status"),
                "aadhaar_masked": item.get("aadhaar_masked") or (_mask(item.get("aadhaar_last4")) if item.get("aadhaar_last4") else None),
                "pan_masked": item.get("pan_masked"), "pan_name_match": item.get("pan_name_match"),
                "verified_at": item.get("verified_at"), "expiry_date": item.get("doc_expiry_date"),
            })
        sections["statutory"] = {"epf_esic": redact_statutory(registrations[0]) if registrations else None,
                                  "identity_verifications": safe_identity}
    if "documents" in visible:
        sections["documents"] = _safe_rows(supabase.table("candidate_documents").select(
            "id,document_type,file_name,file_url,mime_type,status,expiry_date,created_at"
        ).eq("candidate_id", candidate_id).order("created_at", desc=True)) if candidate_id else []
        from app.services.certification_service import get_unified_employee_certifications
        sections["certifications"] = get_unified_employee_certifications(
            supabase, context.org_id, employee
        )
    if "disciplinary" in visible:
        sections["disciplinary"] = _safe_rows(supabase.table("employee_hr_events").select("*")
                                             .eq("employee_id", employee_id).order("event_date", desc=True))

    lifecycle = _safe_rows(supabase.table("employee_lifecycle_events").select("*")
                           .eq("employee_id", employee_id).order("event_at", desc=True).limit(100))
    sections["timeline"] = lifecycle
    return {
        "employee_id": employee_id, "candidate_id": candidate_id, "self_view": self_view,
        "visible_sections": sorted(visible), "sections": sections,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def create_employee_record(supabase, context: AccessContext, employee_id: str, table: str,
                           payload: dict, *, event_type: str, title: str) -> dict:
    employee_rows = _safe_rows(supabase.table("users").select(
        "id,org_id,active_property_id,department_id"
    ).eq("id", employee_id).eq("org_id", context.org_id).limit(1))
    if not employee_rows:
        raise HTTPException(404, "Employee not found")
    employee = employee_rows[0]
    authorize(context, "employees.manage", property_id=employee.get("active_property_id"),
              department_id=employee.get("department_id"))
    row = {
        **payload, "org_id": context.org_id, "employee_id": employee_id,
        "property_id": employee.get("active_property_id"), "department_id": employee.get("department_id"),
        "created_by": context.user_id,
    }
    inserted = _rows(supabase.table(table).insert(row).execute())
    if not inserted:
        raise HTTPException(500, "Record could not be created")
    source = inserted[0]
    supabase.table("employee_lifecycle_events").insert({
        "org_id": context.org_id, "employee_id": employee_id,
        "property_id": employee.get("active_property_id"), "department_id": employee.get("department_id"),
        "event_type": event_type, "title": title, "source_table": table, "source_id": source.get("id"),
        "visibility": "HR_ONLY" if table == "employee_hr_events" else "EMPLOYEE",
        "created_by": context.user_id,
    }).execute()
    return source
