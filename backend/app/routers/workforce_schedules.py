"""Property-scoped workforce schedule, availability and shift-swap APIs."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.rbac_service import authorize, build_access_context
from app.services.workforce_scheduling_service import send_shift_whatsapp, validate_shift_assignment

router = APIRouter()
CurrentUser = Annotated[dict, Depends(get_current_user)]


def rows(result):
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


def now(): return datetime.now(timezone.utc).isoformat()


class TemplateBody(BaseModel):
    property_id: str; department_id: str | None = None; name: str = Field(min_length=2, max_length=120)
    role: str | None = None; shift_type: str | None = None; start_time: str; end_time: str
    break_minutes: int = Field(30, ge=0, le=240); color: str = Field("#2563EB", pattern=r"^#[0-9A-Fa-f]{6}$")


class ScheduleBody(BaseModel):
    property_id: str; department_id: str | None = None; name: str = Field(min_length=2)
    period_type: Literal["WEEKLY", "MONTHLY"]; period_start: date; period_end: date
    @model_validator(mode="after")
    def valid_period(self):
        if self.period_end < self.period_start: raise ValueError("period_end must be on or after period_start")
        return self


class ShiftBody(BaseModel):
    employee_id: str; start_date: datetime; end_date: datetime; template_id: str | None = None
    department_id: str | None = None; role: str | None = None; shift_type: str | None = None
    location: str | None = None; break_minutes: int = Field(30, ge=0, le=240)


class MoveBody(BaseModel):
    employee_id: str | None = None; start_date: datetime; end_date: datetime


class AvailabilityBody(BaseModel):
    property_id: str; day_of_week: int = Field(ge=1, le=7); available_start: str; available_end: str
    effective_from: date = Field(default_factory=date.today); effective_to: date | None = None
    is_available: bool = True; notes: str | None = None


class WeeklyOffBody(BaseModel):
    employee_id: str; property_id: str; day_of_week: int = Field(ge=1, le=7)
    effective_from: date = Field(default_factory=date.today); effective_to: date | None = None


class SwapBody(BaseModel):
    assignment_id: str; target_employee_id: str | None = None; reason: str = Field(min_length=5)


class DecisionBody(BaseModel):
    action: Literal["APPROVE", "REJECT"]; note: str | None = None


def _audit(sb, ctx, action, **ids):
    sb.table("shift_schedule_audit_logs").insert({"org_id": ctx.org_id, "actor_id": ctx.user_id,
        "action": action, **{k: v for k, v in ids.items() if v is not None}}).execute()


def _validation_data(sb, employee_id, property_id):
    shifts = rows(sb.table("v_workforce_schedule").select("*").eq("employee_id", employee_id).execute())
    availability = rows(sb.table("employee_availability_windows").select("*").eq("employee_id", employee_id).eq("property_id", property_id).execute())
    offs = rows(sb.table("employee_weekly_offs").select("*").eq("employee_id", employee_id).eq("property_id", property_id).execute())
    leaves = rows(sb.table("leave_requests").select("leave_date").eq("employee_id", employee_id).eq("status", "APPROVED").execute())
    return shifts, availability, offs, [x["leave_date"] for x in leaves]


@router.post("/templates", status_code=201)
async def create_template(body: TemplateBody, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user); authorize(ctx, "attendance.manage", property_id=body.property_id, department_id=body.department_id)
    saved = rows(supabase.table("shift_templates").insert({**body.model_dump(), "org_id": ctx.org_id, "created_by": ctx.user_id}).execute())
    return saved[0] if saved else body.model_dump()


@router.get("/templates")
async def list_templates(property_id: str, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user); authorize(ctx, "attendance.read", property_id=property_id)
    return rows(supabase.table("shift_templates").select("*").eq("org_id", ctx.org_id).eq("property_id", property_id).eq("is_active", True).execute())


@router.get("/employees")
async def schedule_employees(property_id: str, supabase: SupabaseClient, user: CurrentUser, department_id: str | None = None):
    ctx = build_access_context(supabase, user); authorize(ctx, "attendance.read", property_id=property_id, department_id=department_id)
    memberships = rows(supabase.table("property_memberships").select("user_id,department_id").eq("property_id", property_id).eq("is_active", True).execute())
    if department_id: memberships = [x for x in memberships if x.get("department_id") == department_id]
    ids = [x["user_id"] for x in memberships if x.get("user_id")]
    if not ids: return []
    people = rows(supabase.table("users").select("id,full_name,role,department_id").eq("org_id", ctx.org_id).in_("id", ids).execute())
    return [x for x in people if str(x.get("role", "")).upper() not in {"CANDIDATE"}]


@router.post("/schedules", status_code=201)
async def create_schedule(body: ScheduleBody, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user); authorize(ctx, "attendance.manage", property_id=body.property_id, department_id=body.department_id)
    payload = {**body.model_dump(mode="json"), "org_id": ctx.org_id, "created_by": ctx.user_id}
    saved = rows(supabase.table("workforce_schedules").insert(payload).execute()); return saved[0] if saved else payload


@router.get("/schedules")
async def list_schedules(property_id: str, supabase: SupabaseClient, user: CurrentUser, status: str | None = None):
    ctx = build_access_context(supabase, user); authorize(ctx, "attendance.read", property_id=property_id)
    q = supabase.table("workforce_schedules").select("*").eq("org_id", ctx.org_id).eq("property_id", property_id)
    if status: q = q.eq("status", status.upper())
    return rows(q.order("period_start", desc=True).execute())


@router.post("/schedules/{schedule_id}/shifts", status_code=201)
async def assign_shift(schedule_id: str, body: ShiftBody, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user)
    schedule = rows(supabase.table("workforce_schedules").select("*").eq("id", schedule_id).eq("org_id", ctx.org_id).limit(1).execute())
    if not schedule: raise HTTPException(404, "Schedule not found")
    schedule = schedule[0]; authorize(ctx, "attendance.manage", property_id=schedule["property_id"], department_id=schedule.get("department_id"))
    if schedule["status"] not in {"DRAFT", "PENDING_APPROVAL"}: raise HTTPException(409, "Only draft schedules can be edited")
    existing, availability, offs, leave_days = _validation_data(supabase, body.employee_id, schedule["property_id"])
    check = validate_shift_assignment(employee_id=body.employee_id, start=body.start_date, end=body.end_date,
        existing_shifts=existing, availability=availability, weekly_offs=offs, approved_leave_dates=leave_days,
        break_minutes=body.break_minutes)
    if not check["valid"]: raise HTTPException(409, detail={"message": "Shift conflict", **check})
    shift = rows(supabase.table("shifts").insert({"org_id": ctx.org_id, "property_id": schedule["property_id"],
        "department_id": body.department_id or schedule.get("department_id"), "schedule_id": schedule_id,
        "template_id": body.template_id, "role": body.role, "shift_type": body.shift_type,
        "start_date": body.start_date.isoformat(), "end_date": body.end_date.isoformat(), "location": body.location,
        "break_minutes": body.break_minutes, "urgency": "normal"}).execute())
    if not shift: raise HTTPException(500, "Unable to create shift")
    assignment = rows(supabase.table("employee_shift_assignments").insert({"org_id": ctx.org_id,
        "shift_id": shift[0]["id"], "employee_id": body.employee_id, "assigned_by": ctx.user_id}).execute())
    _audit(supabase, ctx, "SHIFT_ASSIGNED", schedule_id=schedule_id, shift_id=shift[0]["id"], assignment_id=assignment[0]["id"] if assignment else None)
    return {"shift": shift[0], "assignment": assignment[0] if assignment else None, "validation": check}


@router.get("/calendar")
async def calendar(date_from: date, date_to: date, property_id: str, supabase: SupabaseClient, user: CurrentUser, department_id: str | None = None):
    ctx = build_access_context(supabase, user); authorize(ctx, "attendance.read", property_id=property_id, department_id=department_id)
    q = supabase.table("v_workforce_schedule").select("*").eq("org_id", ctx.org_id).eq("property_id", property_id).gte("start_date", date_from.isoformat()).lte("start_date", date_to.isoformat())
    if department_id: q = q.eq("department_id", department_id)
    return rows(q.order("start_date").execute())


@router.patch("/assignments/{assignment_id}/move")
async def move_assignment(assignment_id: str, body: MoveBody, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user)
    current = rows(supabase.table("v_workforce_schedule").select("*").eq("assignment_id", assignment_id).limit(1).execute())
    if not current: raise HTTPException(404, "Assignment not found")
    current = current[0]; authorize(ctx, "attendance.manage", property_id=current["property_id"], department_id=current.get("department_id"))
    employee_id = body.employee_id or current["employee_id"]
    existing, availability, offs, leave_days = _validation_data(supabase, employee_id, current["property_id"])
    check = validate_shift_assignment(employee_id=employee_id, start=body.start_date, end=body.end_date,
        existing_shifts=existing, availability=availability, weekly_offs=offs, approved_leave_dates=leave_days,
        break_minutes=current.get("break_minutes", 0), exclude_assignment_id=assignment_id)
    if not check["valid"]: raise HTTPException(409, detail={"message": "Shift conflict", **check})
    supabase.table("shifts").update({"start_date": body.start_date.isoformat(), "end_date": body.end_date.isoformat()}).eq("id", current["shift_id"]).execute()
    saved = rows(supabase.table("employee_shift_assignments").update({"employee_id": employee_id, "updated_at": now()}).eq("id", assignment_id).execute())
    _audit(supabase, ctx, "SHIFT_MOVED", shift_id=current["shift_id"], assignment_id=assignment_id)
    return {"assignment": saved[0] if saved else {"id": assignment_id}, "validation": check}


@router.post("/availability/me", status_code=201)
async def set_availability(body: AvailabilityBody, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user); authorize(ctx, "attendance.read", property_id=body.property_id, owner_user_id=ctx.user_id)
    saved = rows(supabase.table("employee_availability_windows").insert({**body.model_dump(mode="json"), "org_id": ctx.org_id, "employee_id": ctx.user_id}).execute())
    return saved[0] if saved else body.model_dump(mode="json")


@router.get("/availability/{employee_id}")
async def get_availability(employee_id: str, property_id: str, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user)
    authorize(ctx, "attendance.read", property_id=property_id, owner_user_id=employee_id)
    return rows(supabase.table("employee_availability_windows").select("*").eq("org_id", ctx.org_id)
                .eq("employee_id", employee_id).eq("property_id", property_id).order("day_of_week").execute())


@router.post("/weekly-offs", status_code=201)
async def set_weekly_off(body: WeeklyOffBody, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user); authorize(ctx, "attendance.manage", property_id=body.property_id)
    saved = rows(supabase.table("employee_weekly_offs").insert({**body.model_dump(mode="json"), "org_id": ctx.org_id, "created_by": ctx.user_id}).execute())
    return saved[0] if saved else body.model_dump(mode="json")


@router.post("/schedules/{schedule_id}/submit")
async def submit_schedule(schedule_id: str, supabase: SupabaseClient, user: CurrentUser):
    return await _transition(schedule_id, "DRAFT", "PENDING_APPROVAL", supabase, user, "SCHEDULE_SUBMITTED", "submitted")


@router.post("/schedules/{schedule_id}/approve")
async def approve_schedule(schedule_id: str, supabase: SupabaseClient, user: CurrentUser):
    return await _transition(schedule_id, "PENDING_APPROVAL", "APPROVED", supabase, user, "SCHEDULE_APPROVED", "approved")


async def _transition(schedule_id, expected, target, sb, user, action, prefix):
    ctx = build_access_context(sb, user); found = rows(sb.table("workforce_schedules").select("*").eq("id", schedule_id).eq("org_id", ctx.org_id).limit(1).execute())
    if not found: raise HTTPException(404, "Schedule not found")
    item = found[0]; authorize(ctx, "attendance.manage", property_id=item["property_id"], department_id=item.get("department_id"))
    if item["status"] != expected: raise HTTPException(409, f"Schedule must be {expected}")
    payload = {"status": target, f"{prefix}_by": ctx.user_id, f"{prefix}_at": now(), "updated_at": now()}
    saved = rows(sb.table("workforce_schedules").update(payload).eq("id", schedule_id).execute()); _audit(sb, ctx, action, schedule_id=schedule_id)
    return saved[0] if saved else {**item, **payload}


@router.post("/schedules/{schedule_id}/publish")
async def publish_schedule(schedule_id: str, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user); found = rows(supabase.table("workforce_schedules").select("*").eq("id", schedule_id).eq("org_id", ctx.org_id).limit(1).execute())
    if not found: raise HTTPException(404, "Schedule not found")
    item = found[0]; authorize(ctx, "attendance.manage", property_id=item["property_id"], department_id=item.get("department_id"))
    if item["status"] != "APPROVED": raise HTTPException(409, "Schedule must be approved before publishing")
    roster = rows(supabase.table("v_workforce_schedule").select("*").eq("schedule_id", schedule_id).execute())
    stamp = now(); supabase.table("workforce_schedules").update({"status": "PUBLISHED", "published_by": ctx.user_id, "published_at": stamp}).eq("id", schedule_id).execute()
    sent = 0
    for shift in roster:
        supabase.table("employee_shift_assignments").update({"status": "PUBLISHED"}).eq("id", shift["assignment_id"]).execute()
        supabase.table("shifts").update({"published_at": stamp}).eq("id", shift["shift_id"]).execute()
        if shift.get("employee_phone"):
            result = send_shift_whatsapp(shift["employee_phone"], shift)
            supabase.table("shift_notification_logs").insert({"org_id": ctx.org_id, "employee_id": shift["employee_id"], "shift_id": shift["shift_id"], "event_type": "SHIFT_PUBLISHED", "delivery_status": str(result.get("status", "SENT")).upper(), "provider_message_id": result.get("sid"), "sent_at": stamp}).execute(); sent += 1
    _audit(supabase, ctx, "SCHEDULE_PUBLISHED", schedule_id=schedule_id)
    return {"status": "PUBLISHED", "assignments": len(roster), "whatsapp_notifications": sent}


@router.post("/swaps", status_code=201)
async def request_swap(body: SwapBody, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user); own = rows(supabase.table("employee_shift_assignments").select("*").eq("id", body.assignment_id).eq("employee_id", ctx.user_id).limit(1).execute())
    if not own: raise HTTPException(404, "Assignment not found")
    payload = {**body.model_dump(), "org_id": ctx.org_id, "requested_by": ctx.user_id, "status": "PENDING_PEER" if body.target_employee_id else "PENDING_MANAGER"}
    saved = rows(supabase.table("shift_swap_requests").insert(payload).execute()); return saved[0] if saved else payload


@router.patch("/swaps/{swap_id}/peer")
async def peer_swap(swap_id: str, body: DecisionBody, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user); found = rows(supabase.table("shift_swap_requests").select("*").eq("id", swap_id).eq("target_employee_id", ctx.user_id).limit(1).execute())
    if not found: raise HTTPException(404, "Swap request not found")
    status = "PENDING_MANAGER" if body.action == "APPROVE" else "REJECTED"
    saved = rows(supabase.table("shift_swap_requests").update({"status": status, "peer_responded_at": now(), "review_note": body.note}).eq("id", swap_id).execute()); return saved[0] if saved else {**found[0], "status": status}


@router.get("/swaps")
async def list_swaps(supabase: SupabaseClient, user: CurrentUser, status: str | None = None):
    ctx = build_access_context(supabase, user)
    q = supabase.table("shift_swap_requests").select("*").eq("org_id", ctx.org_id)
    if ctx.role in {"EMPLOYEE", "CANDIDATE"}:
        q = q.or_(f"requested_by.eq.{ctx.user_id},target_employee_id.eq.{ctx.user_id}")
    else:
        authorize(ctx, "attendance.read")
    if status: q = q.eq("status", status.upper())
    return rows(q.order("created_at", desc=True).execute())


@router.patch("/swaps/{swap_id}/review")
async def review_swap(swap_id: str, body: DecisionBody, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user); found = rows(supabase.table("shift_swap_requests").select("*").eq("id", swap_id).eq("status", "PENDING_MANAGER").limit(1).execute())
    if not found: raise HTTPException(404, "Pending swap request not found")
    swap = found[0]; assignment = rows(supabase.table("v_workforce_schedule").select("*").eq("assignment_id", swap["assignment_id"]).limit(1).execute())
    if not assignment: raise HTTPException(404, "Assignment not found")
    shift = assignment[0]; authorize(ctx, "attendance.manage", property_id=shift["property_id"], department_id=shift.get("department_id"))
    if body.action == "APPROVE":
        target = swap.get("target_employee_id")
        if not target: raise HTTPException(422, "A target employee is required")
        existing, availability, offs, leaves = _validation_data(supabase, target, shift["property_id"])
        check = validate_shift_assignment(employee_id=target, start=shift["start_date"], end=shift["end_date"], existing_shifts=existing, availability=availability, weekly_offs=offs, approved_leave_dates=leaves, break_minutes=shift.get("break_minutes", 0))
        if not check["valid"]: raise HTTPException(409, detail={"message": "Swap target has conflicts", **check})
        supabase.table("employee_shift_assignments").update({"employee_id": target, "updated_at": now()}).eq("id", swap["assignment_id"]).execute()
    status = "APPROVED" if body.action == "APPROVE" else "REJECTED"
    saved = rows(supabase.table("shift_swap_requests").update({"status": status, "reviewed_by": ctx.user_id, "reviewed_at": now(), "review_note": body.note}).eq("id", swap_id).execute())
    _audit(supabase, ctx, f"SWAP_{status}", assignment_id=swap["assignment_id"], swap_request_id=swap_id)
    return saved[0] if saved else {**swap, "status": status}
