"""
Employees router — UPI ID collection.

GET  /api/v1/employees/{employee_id}/upi
POST /api/v1/employees/{employee_id}/upi

Authorization rules:
  - An employee may only read/write their own record.
  - A user whose `role` column in the `users` table equals "admin"
    may read/write any employee's record.
"""

import re
import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.upi_validation_service import validate_upi_format, validate_vpa_razorpay
from app.services.employee_360_service import create_employee_record, get_employee_360
from app.services.rbac_service import authorize, build_access_context

router = APIRouter(tags=["Employees"])
logger = logging.getLogger(__name__)

CurrentUser = Annotated[dict, Depends(get_current_user)]

# Kept here as a belt-and-suspenders guard; primary validation is in the service.
_UPI_RE = re.compile(r"^[a-zA-Z0-9._-]+@[a-zA-Z]+$")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class UPIRequest(BaseModel):
    upi_id: str

    @field_validator("upi_id")
    @classmethod
    def validate_upi(cls, v: str) -> str:
        v = v.strip()
        if not _UPI_RE.fullmatch(v):
            raise ValueError(
                "Invalid UPI ID. Format must be <username>@<bankhandle> "
                "(e.g. john@okaxis, 9999@ybl, name.s@paytm)."
            )
        return v


class PerformanceReviewRequest(BaseModel):
    review_period_start: str
    review_period_end: str
    rating: Optional[float] = None
    goals: list[dict] = Field(default_factory=list)
    strengths: Optional[str] = None
    development_areas: Optional[str] = None
    manager_comments: Optional[str] = None
    status: str = "DRAFT"


class TrainingRecordRequest(BaseModel):
    training_name: str
    provider: Optional[str] = None
    category: str = "ROLE_SKILL"
    status: str = "ASSIGNED"
    due_date: Optional[str] = None
    completed_at: Optional[str] = None
    score: Optional[float] = None
    certificate_url: Optional[str] = None


class HREventRequest(BaseModel):
    event_type: str
    event_date: Optional[str] = None
    title: str
    description: Optional[str] = None
    severity: str = "INFO"
    status: str = "OPEN"
    is_confidential: bool = True


class EmploymentUpdateRequest(BaseModel):
    employee_code: Optional[str] = None
    job_title: Optional[str] = None
    employment_type: Optional[str] = None
    employment_status: Optional[str] = None
    joining_date: Optional[str] = None
    manager_id: Optional[str] = None
    department_id: Optional[str] = None
    active_property_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_employee_exists(supabase, employee_id: str) -> dict:
    """Raise 404 if the employee row is absent from the users table."""
    try:
        res = (
            supabase.table("users")
            .select("id, email, role")
            .eq("id", employee_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.error("DB error looking up employee %s: %s", employee_id, exc)
        raise HTTPException(status_code=500, detail="Database error")

    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{employee_id}' not found.",
        )
    return res.data[0]


def _require_authorized(current_user: dict, employee_id: str, supabase) -> None:
    """
    Raise 403 unless the caller is the employee themselves OR an admin.
    Admin = any user whose `role` is 'admin' in the users table.
    """
    caller_id = current_user.get("sub", "")

    if caller_id == employee_id:
        return  # employee accessing their own record — always allowed

    # Check caller's role
    try:
        res = (
            supabase.table("users")
            .select("role")
            .eq("id", caller_id)
            .limit(1)
            .execute()
        )
        if res.data and res.data[0].get("role") == "admin":
            return
    except Exception as exc:
        logger.warning("Role lookup failed for caller %s: %s", caller_id, exc)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not authorized. You may only view your own UPI details unless you are an admin.",
    )


def _mask_account_number(details: dict) -> dict:
    """Replace all-but-last-4 digits of bank account number with ****."""
    acct = details.get("bank_account_number") or ""
    if len(acct) > 4:
        details = {**details, "bank_account_number": "****" + acct[-4:]}
    return details


# ---------------------------------------------------------------------------
# Employee 360 aggregate and missing HR records
# ---------------------------------------------------------------------------

@router.get("/employees/me/360")
async def get_my_employee_360(supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    return get_employee_360(supabase, context, context.user_id)


@router.get("/employees/{employee_id}/360")
async def get_employee_360_profile(employee_id: str, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    return get_employee_360(supabase, context, employee_id)


@router.patch("/employees/{employee_id}/employment")
async def update_employee_employment(
    employee_id: str, body: EmploymentUpdateRequest, supabase: SupabaseClient, user: CurrentUser,
):
    context = build_access_context(supabase, user)
    existing = (supabase.table("users").select("id,org_id,active_property_id,department_id")
                .eq("id", employee_id).eq("org_id", context.org_id).limit(1).execute().data or [])
    if not existing:
        raise HTTPException(404, "Employee not found")
    authorize(context, "employees.manage", property_id=existing[0].get("active_property_id"),
              department_id=existing[0].get("department_id"))
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(422, "No employment fields supplied")
    result = supabase.table("users").update(payload).eq("id", employee_id).eq("org_id", context.org_id).execute()
    rows = getattr(result, "data", None) or []
    if not rows:
        raise HTTPException(500, "Employment details could not be updated")
    supabase.table("employee_lifecycle_events").insert({
        "org_id": context.org_id, "employee_id": employee_id,
        "property_id": payload.get("active_property_id", existing[0].get("active_property_id")),
        "department_id": payload.get("department_id", existing[0].get("department_id")),
        "event_type": "EMPLOYMENT_UPDATED", "title": "Employment details updated",
        "visibility": "EMPLOYEE", "created_by": context.user_id, "metadata": payload,
    }).execute()
    return rows[0]


@router.post("/employees/{employee_id}/performance", status_code=201)
async def add_performance_review(
    employee_id: str, body: PerformanceReviewRequest, supabase: SupabaseClient, user: CurrentUser,
):
    context = build_access_context(supabase, user)
    payload = body.model_dump()
    payload["reviewed_by"] = context.user_id
    return create_employee_record(supabase, context, employee_id, "employee_performance_reviews", payload,
                                  event_type="PERFORMANCE_REVIEW", title="Performance review added")


@router.post("/employees/{employee_id}/training", status_code=201)
async def add_training_record(
    employee_id: str, body: TrainingRecordRequest, supabase: SupabaseClient, user: CurrentUser,
):
    context = build_access_context(supabase, user)
    return create_employee_record(supabase, context, employee_id, "employee_training_records", body.model_dump(),
                                  event_type="TRAINING_ASSIGNED", title=f"Training: {body.training_name}")


@router.post("/employees/{employee_id}/hr-events", status_code=201)
async def add_hr_event(
    employee_id: str, body: HREventRequest, supabase: SupabaseClient, user: CurrentUser,
):
    context = build_access_context(supabase, user)
    payload = body.model_dump(exclude_none=True)
    return create_employee_record(supabase, context, employee_id, "employee_hr_events", payload,
                                  event_type=body.event_type, title=body.title)


# ---------------------------------------------------------------------------
# GET /employees/{employee_id}/upi
# ---------------------------------------------------------------------------

@router.get("/employees/{employee_id}/upi")
async def get_employee_upi(
    employee_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Return the saved UPI / bank details for an employee.
    Bank account number is masked (only last 4 digits shown).
    Returns {"upi_details": null} when no record has been saved yet.
    """
    _require_authorized(user, employee_id, supabase)
    _require_employee_exists(supabase, employee_id)

    try:
        res = (
            supabase.table("employee_upi_details")
            .select("*")
            .eq("user_id", employee_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.error("DB error fetching UPI for %s: %s", employee_id, exc)
        raise HTTPException(status_code=500, detail="Database error")

    if not res.data:
        return {"upi_details": None}

    return {"upi_details": _mask_account_number(res.data[0])}


# ---------------------------------------------------------------------------
# POST /employees/{employee_id}/upi
# ---------------------------------------------------------------------------

@router.post("/employees/{employee_id}/upi", status_code=status.HTTP_200_OK)
async def set_employee_upi(
    employee_id: str,
    body: UPIRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Create or replace UPI details for an employee.

    The UPI ID is first validated by regex (enforced by the request model)
    and then passed to the Razorpay Validate VPA API when credentials are
    configured.  If Razorpay is unavailable or unconfigured the ID is accepted
    with verification_method='REGEX_ONLY' and is_verified=False.

    Raises 422 only when Razorpay explicitly rejects the VPA as non-existent.
    """
    _require_authorized(user, employee_id, supabase)
    _require_employee_exists(supabase, employee_id)

    # Razorpay VPA check
    key_id = getattr(settings, "RAZORPAY_KEY_ID", None)
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", None)
    validation = await validate_vpa_razorpay(body.upi_id, key_id, key_secret)

    if not validation["valid"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "field": "upi_id",
                "message": validation.get("error", "UPI ID validation failed."),
                "upi_id": body.upi_id,
            },
        )

    now = datetime.utcnow().isoformat()
    # is_verified only if Razorpay explicitly confirmed the VPA
    is_verified = validation.get("method") == "RAZORPAY_VPA" and validation.get("valid")

    payload = {
        "user_id": employee_id,
        "upi_id": body.upi_id,
        "is_verified": is_verified,
        "verification_method": validation["method"],
        "updated_at": now,
    }

    try:
        existing = (
            supabase.table("employee_upi_details")
            .select("id")
            .eq("user_id", employee_id)
            .limit(1)
            .execute()
        )

        if existing.data:
            res = (
                supabase.table("employee_upi_details")
                .update(payload)
                .eq("user_id", employee_id)
                .execute()
            )
        else:
            payload["created_at"] = now
            res = supabase.table("employee_upi_details").insert(payload).execute()

    except Exception as exc:
        logger.error("DB error saving UPI for %s: %s", employee_id, exc)
        raise HTTPException(status_code=500, detail="Failed to save UPI details.")

    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to save UPI details.")

    return {
        "saved": True,
        "upi_id": body.upi_id,
        "is_verified": is_verified,
        "verification_method": validation["method"],
        "validation": validation,
    }
