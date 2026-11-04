"""Canonical employee self-service operations shared by PWA and WhatsApp."""
from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException


def rows(result) -> list[dict]:
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


def employee_shifts(supabase, employee_id: str, *, days: int = 7) -> list[dict]:
    start = datetime.now(timezone.utc).date()
    end = start + timedelta(days=max(1, min(days, 31)))
    try:
        found = rows(supabase.table("v_workforce_schedule").select(
            "assignment_id,employee_id,assignment_status,shift_id,start_date,end_date,role,shift_type,"
            "property_name,department,location,manager_id"
        ).eq("employee_id", employee_id).in_("assignment_status", ["PUBLISHED", "CONFIRMED"])
          .gte("start_date", start.isoformat()).lte("start_date", end.isoformat())
          .order("start_date").limit(40).execute())
        if found:
            return found
    except Exception:
        pass
    try:
        return rows(supabase.table("v_employee_shifts").select("*").eq("employee_id", employee_id)
                    .gte("start_date", start.isoformat()).lte("start_date", end.isoformat())
                    .order("start_date").limit(40).execute())
    except Exception:
        return []


def leave_snapshot(supabase, employee_id: str) -> dict:
    year = datetime.now(timezone.utc).year
    balance = rows(supabase.table("leave_balances").select("*").eq("employee_id", employee_id)
                   .eq("year", year).limit(1).execute())
    requests = rows(supabase.table("leave_requests").select(
        "id,ticket_number,start_date,end_date,total_days,leave_type,reason,status,manager_status,hr_status,source,created_at"
    ).eq("employee_id", employee_id).order("created_at", desc=True).limit(10).execute())
    return {"balance": balance[0] if balance else None, "requests": requests}


def payroll_snapshot(supabase, employee_id: str) -> dict:
    payslips = rows(supabase.table("payslips").select(
        "id,month,year,gross_salary_inr,net_salary_inr,epf_deduction_inr,esic_deduction_inr,"
        "professional_tax_inr,status,paid_at"
    ).eq("employee_id", employee_id).eq("status", "FINALIZED")
      .order("year", desc=True).order("month", desc=True).limit(6).execute())
    compensation = rows(supabase.table("employee_compensation_structures").select(
        "annual_ctc_inr,monthly_gross_inr,basic_inr,hra_inr,allowances,epf_applicable,esic_applicable,effective_from"
    ).eq("employee_id", employee_id).order("effective_from", desc=True).limit(1).execute())
    return {"payslips": payslips, "compensation": compensation[0] if compensation else None}


def statutory_snapshot(supabase, candidate_id: str | None) -> dict:
    if not candidate_id:
        return {"epf": None, "esic": None}
    registrations = rows(supabase.table("epf_esic_registrations").select(
        "status,epf_uan,epf_member_id,esic_ip_number,epf_joining_date,esic_eligible"
    ).eq("candidate_id", candidate_id).limit(1).execute())
    item = registrations[0] if registrations else {}
    mask = lambda value: ("****" + str(value)[-4:]) if value else None
    return {"status": item.get("status"), "epf_uan": mask(item.get("epf_uan")),
            "epf_member_id": mask(item.get("epf_member_id")),
            "esic_ip_number": mask(item.get("esic_ip_number")),
            "esic_eligible": item.get("esic_eligible"), "epf_joining_date": item.get("epf_joining_date")}


def employee_support(supabase, org_id: str, property_id: str | None) -> dict | None:
    if not property_id:
        return None
    found = rows(supabase.table("property_employee_support_profiles").select("*")
                 .eq("org_id", org_id).eq("property_id", property_id).limit(1).execute())
    return found[0] if found else None


def submit_salary_advance(supabase, *, org_id: str, property_id: str | None, employee_id: str,
                          amount_inr: float, reason: str, repayment_months: int, source: str = "PWA") -> dict:
    if amount_inr <= 0:
        raise HTTPException(422, "Advance amount must be greater than zero")
    if len(reason.strip()) < 5:
        raise HTTPException(422, "Please provide a reason")
    active = rows(supabase.table("employee_salary_advance_requests").select("id")
                  .eq("employee_id", employee_id).in_("status", ["PENDING", "APPROVED"]).limit(1).execute())
    if active:
        raise HTTPException(409, "An active salary advance request already exists")
    payload = {"org_id": org_id, "property_id": property_id, "employee_id": employee_id,
               "amount_inr": round(amount_inr, 2), "reason": reason.strip(),
               "requested_repayment_months": repayment_months, "status": "PENDING", "source": source.upper()}
    saved = rows(supabase.table("employee_salary_advance_requests").insert(payload).execute())
    return {**payload, **saved[0]} if saved else payload


def submit_grievance(supabase, *, org_id: str, employee_id: str, phone: str | None,
                     text: str, category: str = "GENERAL", severity: str = "MEDIUM",
                     anonymous: bool = False, complaint_type: str = "GRIEVANCE",
                     property_id: str | None = None, source: str = "APP",
                     whatsapp_message_id: str | None = None) -> dict:
    if len(text.strip()) < 10:
        raise HTTPException(422, "Complaint must contain at least 10 characters")
    category, severity, complaint_type = category.upper(), severity.upper(), complaint_type.upper()
    if category not in {"GENERAL","HARASSMENT","SAFETY","PAYROLL","DISCRIMINATION","WORKPLACE","FACILITIES"}:
        raise HTTPException(422, "Unsupported complaint category")
    if severity not in {"LOW","MEDIUM","HIGH","CRITICAL"} or complaint_type not in {"GRIEVANCE","POSH"}:
        raise HTTPException(422, "Unsupported complaint classification")
    if complaint_type == "POSH":
        category = "HARASSMENT"
        severity = "HIGH" if severity in {"LOW", "MEDIUM"} else severity
    payload = {
        "org_id": org_id, "property_id": property_id,
        "employee_id": None if anonymous else employee_id, "phone": None if anonymous else phone,
        "is_anonymous": anonymous, "anonymous_token": secrets.token_hex(20) if anonymous else None,
        "complaint_text": text.strip(), "category": category, "severity": severity,
        "complaint_type": complaint_type, "confidentiality_level": "RESTRICTED" if complaint_type == "POSH" else "CONFIDENTIAL", "ticket_number": f"HR-{datetime.now():%Y%m%d}-{uuid4().hex[:6].upper()}",
        "status": "OPEN", "source": source.upper(), "whatsapp_message_id": whatsapp_message_id,
    }
    saved = rows(supabase.table("hr_complaints").insert(payload).execute())
    return {**payload, **saved[0]} if saved else payload


def employee_dashboard(supabase, *, employee: dict, candidate_id: str | None = None) -> dict:
    employee_id, org_id, property_id = employee["id"], employee["org_id"], employee.get("active_property_id")
    advances = rows(supabase.table("employee_salary_advance_requests").select("*")
                    .eq("employee_id", employee_id).order("created_at", desc=True).limit(10).execute())
    complaints = rows(supabase.table("hr_complaints").select(
        "id,ticket_number,complaint_type,category,severity,status,created_at,resolved_at"
    ).eq("employee_id", employee_id).order("created_at", desc=True).limit(10).execute())
    accommodation = rows(supabase.table("accommodation_allocations").select(
        "id,status,check_in_at,expected_check_out,deposit_inr,bed_id"
    ).eq("employee_id", employee_id).in_("status", ["ALLOCATED", "CHECKED_IN"]).limit(1).execute())
    transport = rows(supabase.table("employee_transport_assignments").select(
        "id,status,schedule_id,pickup_point_id,boarded_at"
    ).eq("employee_id", employee_id).in_("status", ["ASSIGNED", "BOARDED"]).limit(20).execute())
    return {
        "employee": {"id": employee_id, "full_name": employee.get("full_name"), "job_title": employee.get("job_title"),
                     "property_id": property_id, "preferred_language": employee.get("preferred_language") or "en"},
        "shifts": employee_shifts(supabase, employee_id), "leave": leave_snapshot(supabase, employee_id),
        "payroll": payroll_snapshot(supabase, employee_id), "statutory": statutory_snapshot(supabase, candidate_id),
        "support": employee_support(supabase, org_id, property_id), "salary_advances": advances,
        "grievances": complaints, "generated_at": datetime.now(timezone.utc).isoformat(),
        "accommodation": accommodation[0] if accommodation else None, "transport_assignments": transport,
    }
