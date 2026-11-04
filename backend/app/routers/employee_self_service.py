"""Compact employee PWA API; delegates to the same domain services as WhatsApp."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import SupabaseAdminClient, SupabaseClient
from app.core.security import get_current_user
from app.services.employee_self_service import employee_dashboard, employee_shifts, submit_grievance, submit_salary_advance
from app.services.salary_advance_service import audit, eligibility, notify_payroll_team, review
from app.services.rbac_service import authorize, build_access_context

router = APIRouter(tags=["Employee Self Service"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


def _employee(supabase, context) -> dict:
    found = supabase.table("users").select(
        "id,org_id,full_name,phone,job_title,active_property_id,department_id,role"
    ).eq("id", context.user_id).eq("org_id", context.org_id).limit(1).execute().data or []
    if not found:
        raise HTTPException(404, "Employee profile not found")
    return found[0]


def _candidate_id(supabase, employee: dict) -> Optional[str]:
    found = supabase.table("candidates").select("id").eq("user_id", employee["id"]).limit(1).execute().data or []
    return found[0]["id"] if found else None


class SalaryAdvanceRequest(BaseModel):
    amount_inr: float = Field(gt=0, le=1_000_000)
    reason: str = Field(min_length=5, max_length=1000)
    repayment_months: int = Field(default=1, ge=1, le=12)


class SalaryAdvanceDecision(BaseModel):
    action: str = Field(pattern="^(APPROVE|REJECT)$")
    note: Optional[str] = Field(default=None, max_length=1000)
    approved_amount_inr: Optional[float] = Field(default=None, gt=0)
    repayment_months: Optional[int] = Field(default=None, ge=1, le=24)


class GrievanceRequest(BaseModel):
    text: str = Field(min_length=10, max_length=5000)
    category: str = "GENERAL"
    severity: str = "MEDIUM"
    anonymous: bool = False
    complaint_type: str = "GRIEVANCE"


class SupportProfileRequest(BaseModel):
    accommodation_available: bool = False
    accommodation_details: Optional[str] = None
    transport_available: bool = False
    transport_details: Optional[str] = None
    transport_contact: Optional[str] = None
    benefits: list[dict | str] = Field(default_factory=list)
    esic_clinic_name: Optional[str] = None
    esic_clinic_address: Optional[str] = None
    esic_clinic_phone: Optional[str] = None
    esic_clinic_maps_url: Optional[str] = None
    emergency_hr_phone: Optional[str] = None
    posh_ic_email: Optional[str] = None
    posh_ic_phone: Optional[str] = None


@router.get("/dashboard")
async def dashboard(supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "attendance.read", owner_user_id=context.user_id)
    employee = _employee(supabase, context)
    return employee_dashboard(supabase, employee=employee, candidate_id=_candidate_id(supabase, employee))


@router.get("/shifts")
async def my_shifts(supabase: SupabaseClient, user: CurrentUser, days: int = 7):
    context = build_access_context(supabase, user)
    authorize(context, "attendance.read", owner_user_id=context.user_id)
    return employee_shifts(supabase, context.user_id, days=days)


@router.get("/salary-advances")
async def list_salary_advances(supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "payroll.read", owner_user_id=context.user_id)
    return supabase.table("employee_salary_advance_requests").select("*").eq(
        "employee_id", context.user_id).order("created_at", desc=True).execute().data or []


@router.post("/salary-advances", status_code=201)
async def request_salary_advance(body: SalaryAdvanceRequest, supabase: SupabaseClient,
                                 admin: SupabaseAdminClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "payroll.read", owner_user_id=context.user_id)
    employee = _employee(supabase, context)
    check = eligibility(supabase, org_id=context.org_id,
        property_id=employee.get("active_property_id"), employee_id=context.user_id)
    if not check["eligible"]:
        raise HTTPException(422, {"message": "Employee is not eligible for a salary advance", "reasons": check["reasons"]})
    if body.amount_inr > check["maximum_eligible_amount_inr"]:
        raise HTTPException(422, f"Maximum eligible advance is INR {check['maximum_eligible_amount_inr']:.2f}")
    if body.repayment_months > check["maximum_repayment_months"]:
        raise HTTPException(422, "Requested repayment period exceeds property policy")
    created = submit_salary_advance(supabase, org_id=context.org_id,
        property_id=employee.get("active_property_id"), employee_id=context.user_id,
        amount_inr=body.amount_inr, reason=body.reason, repayment_months=body.repayment_months, source="PWA")
    audit(admin, org_id=context.org_id, advance_id=created["id"], actor_id=context.user_id,
          action="REQUESTED", after_status="PENDING", amount=body.amount_inr,
          metadata={"source": "PWA", "repayment_months": body.repayment_months})
    notify_payroll_team(admin, context.org_id, employee.get("active_property_id"),
        f"New salary advance request: INR {body.amount_inr:,.2f}. Review in Salary Advances.")
    return created


@router.patch("/salary-advances/{request_id}/review")
async def review_salary_advance(request_id: str, body: SalaryAdvanceDecision,
                                supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    found = supabase.table("employee_salary_advance_requests").select("*").eq(
        "id", request_id).eq("org_id", context.org_id).limit(1).execute().data or []
    if not found:
        raise HTTPException(404, "Salary advance request not found")
    item = found[0]
    authorize(context, "payroll.manage", property_id=item.get("property_id"))
    return review(supabase, item=item, actor_id=context.user_id, action=body.action,
                  note=body.note, approved_amount=body.approved_amount_inr,
                  repayment_months=body.repayment_months)


@router.post("/grievances", status_code=201)
async def create_grievance(body: GrievanceRequest, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "complaints.create", owner_user_id=context.user_id)
    employee = _employee(supabase, context)
    result = submit_grievance(supabase, org_id=context.org_id, employee_id=context.user_id,
        phone=employee.get("phone"), property_id=employee.get("active_property_id"), text=body.text,
        category=body.category, severity=body.severity, anonymous=body.anonymous,
        complaint_type=body.complaint_type, source="APP")
    return {"ticket_number": result.get("ticket_number"), "status": result.get("status"),
            "anonymous_token": result.get("anonymous_token"), "is_anonymous": result.get("is_anonymous")}


@router.get("/support")
async def get_support(supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    employee = _employee(supabase, context)
    property_id = employee.get("active_property_id")
    if not property_id:
        return None
    authorize(context, "properties.read", property_id=property_id)
    found = supabase.table("property_employee_support_profiles").select("*").eq(
        "org_id", context.org_id).eq("property_id", property_id).limit(1).execute().data or []
    return found[0] if found else None


@router.put("/support/{property_id}")
async def update_support(property_id: str, body: SupportProfileRequest,
                         supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "employees.manage", property_id=property_id)
    payload = {**body.model_dump(), "org_id": context.org_id, "property_id": property_id,
               "updated_by": context.user_id, "updated_at": datetime.now(timezone.utc).isoformat()}
    saved = supabase.table("property_employee_support_profiles").upsert(
        payload, on_conflict="property_id").execute().data or []
    return saved[0] if saved else payload
