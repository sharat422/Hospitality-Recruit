"""Employee attendance, corrections and biometric ingestion APIs."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.dependencies import SupabaseClient, get_supabase_admin_client
from app.core.security import get_current_user
from app.services.attendance_service import attendance_date_for, calculate_daily_attendance, record_punch
from app.services.biometric_adapters import get_biometric_adapter
from app.services.rbac_service import authorize, build_access_context

router = APIRouter()
CurrentUser = Annotated[dict, Depends(get_current_user)]


class PunchRequest(BaseModel):
    punch_type: Literal["IN", "OUT"]
    property_id: str | None = None
    punched_at: datetime | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    gps_accuracy_m: float | None = Field(None, ge=0)
    source: Literal["WEB", "MOBILE"] = "WEB"


class CorrectionRequest(BaseModel):
    daily_record_id: str
    requested_in_at: datetime | None = None
    requested_out_at: datetime | None = None
    reason: str = Field(min_length=5, max_length=1000)


class ReviewCorrectionRequest(BaseModel):
    action: Literal["APPROVE", "REJECT"]
    review_note: str | None = Field(None, max_length=1000)


class ValidateDayRequest(BaseModel):
    action: Literal["VALIDATE", "REJECT"]
    note: str | None = Field(None, max_length=1000)


class AttendancePolicyRequest(BaseModel):
    property_id: str
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    geofence_radius_m: int = Field(150, ge=25, le=5000)
    require_geofence: bool = False
    late_grace_minutes: int = Field(10, ge=0, le=120)
    early_departure_grace_minutes: int = Field(5, ge=0, le=120)
    overtime_after_minutes: int = Field(480, gt=0)
    weekly_off_days: list[int] = Field(default_factory=lambda: [7])


def _rows(result) -> list[dict]:
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


def _employee(supabase, org_id: str, employee_id: str) -> dict:
    rows = _rows(supabase.table("users").select("id,org_id,active_property_id,department_id,employee_code")
                 .eq("id", employee_id).eq("org_id", org_id).limit(1).execute())
    if not rows:
        raise HTTPException(404, "Employee not found")
    return rows[0]


def _policy(supabase, org_id: str, property_id: str) -> dict:
    rows = _rows(supabase.table("attendance_policies").select("*").eq("org_id", org_id)
                 .eq("property_id", property_id).eq("is_active", True).limit(1).execute())
    return rows[0] if rows else {"late_grace_minutes": 10, "early_departure_grace_minutes": 5,
                                 "overtime_after_minutes": 480, "weekly_off_days": [7]}


def _schedule(supabase, employee_id: str, target_date: date) -> tuple[str | None, str | None]:
    try:
        rows = _rows(supabase.table("v_workforce_schedule").select("*").eq("employee_id", employee_id)
                     .in_("assignment_status", ["PUBLISHED", "CONFIRMED"]).execute())
    except Exception:
        rows = []
    if not rows:
        rows = _rows(supabase.table("v_employee_shifts").select("*").eq("employee_id", employee_id).execute())
    for row in rows:
        start = row.get("start_date") or row.get("start_time")
        end = row.get("end_date") or row.get("end_time")
        try:
            if start and datetime.fromisoformat(str(start).replace("Z", "+00:00")).date() == target_date:
                return start, end
        except ValueError:
            continue
    return None, None


def _recalculate(supabase, *, org_id: str, employee_id: str, property_id: str, target_date: date) -> dict:
    policy = _policy(supabase, org_id, property_id)
    punches = _rows(supabase.table("attendance_punches").select("*").eq("org_id", org_id)
                    .eq("employee_id", employee_id).order("punched_at").execute())
    punches = [p for p in punches if attendance_date_for(p["punched_at"], policy.get("timezone", "Asia/Kolkata")) == target_date]
    scheduled_start, scheduled_end = _schedule(supabase, employee_id, target_date)
    leaves = _rows(supabase.table("leave_requests").select("id").eq("employee_id", employee_id)
                   .eq("leave_date", target_date.isoformat()).eq("status", "APPROVED").limit(1).execute())
    result = calculate_daily_attendance(
        punches, scheduled_start=scheduled_start, scheduled_end=scheduled_end, policy=policy,
        on_leave=bool(leaves), weekly_off=target_date.isoweekday() in policy.get("weekly_off_days", [7]),
    )
    row = {**result, "org_id": org_id, "employee_id": employee_id, "property_id": property_id,
           "attendance_date": target_date.isoformat(), "scheduled_start": scheduled_start,
           "scheduled_end": scheduled_end, "updated_at": datetime.now(timezone.utc).isoformat()}
    existing = _rows(supabase.table("attendance_daily_records").select("id,source_version")
                     .eq("org_id", org_id).eq("employee_id", employee_id)
                     .eq("attendance_date", target_date.isoformat()).limit(1).execute())
    if existing:
        row["source_version"] = int(existing[0].get("source_version", 1)) + 1
        saved = _rows(supabase.table("attendance_daily_records").update(row).eq("id", existing[0]["id"]).execute())
    else:
        saved = _rows(supabase.table("attendance_daily_records").insert(row).execute())
    return saved[0] if saved else row


@router.post("/punch", status_code=201)
async def punch(body: PunchRequest, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    employee = _employee(supabase, context.org_id, context.user_id)
    property_id = body.property_id or employee.get("active_property_id")
    if not property_id:
        raise HTTPException(422, "Employee has no active property")
    authorize(context, "attendance.read", property_id=property_id, owner_user_id=context.user_id)
    punched_at = body.punched_at or datetime.now(timezone.utc)
    saved = record_punch(
        supabase, org_id=context.org_id, employee_id=context.user_id, property_id=property_id,
        punch_type=body.punch_type, source=body.source, punched_at=punched_at,
        latitude=body.latitude, longitude=body.longitude, gps_accuracy_m=body.gps_accuracy_m,
        actor_id=context.user_id,
    )
    policy = _policy(supabase, context.org_id, property_id)
    target_date = attendance_date_for(punched_at, policy.get("timezone", "Asia/Kolkata"))
    daily = _recalculate(supabase, org_id=context.org_id, employee_id=context.user_id,
                         property_id=property_id, target_date=target_date)
    return {"punch": saved, "daily_record": daily, "payroll_ready": False}


@router.get("/me/history")
async def my_history(supabase: SupabaseClient, user: CurrentUser, date_from: date | None = None,
                     date_to: date | None = None):
    context = build_access_context(supabase, user)
    query = supabase.table("attendance_daily_records").select("*").eq("org_id", context.org_id)
    query = query.eq("employee_id", context.user_id)
    if date_from:
        query = query.gte("attendance_date", date_from.isoformat())
    if date_to:
        query = query.lte("attendance_date", date_to.isoformat())
    return {"records": _rows(query.order("attendance_date", desc=True).execute())}


@router.get("/employees/{employee_id}/history")
async def employee_history(employee_id: str, supabase: SupabaseClient, user: CurrentUser,
                           date_from: date | None = None, date_to: date | None = None):
    context = build_access_context(supabase, user)
    employee = _employee(supabase, context.org_id, employee_id)
    authorize(context, "attendance.read", property_id=employee.get("active_property_id"),
              department_id=employee.get("department_id"), owner_user_id=employee_id)
    query = supabase.table("attendance_daily_records").select("*").eq("org_id", context.org_id).eq("employee_id", employee_id)
    if date_from:
        query = query.gte("attendance_date", date_from.isoformat())
    if date_to:
        query = query.lte("attendance_date", date_to.isoformat())
    return {"records": _rows(query.order("attendance_date", desc=True).execute())}


@router.post("/corrections", status_code=201)
async def request_correction(body: CorrectionRequest, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    daily = _rows(supabase.table("attendance_daily_records").select("*").eq("id", body.daily_record_id)
                  .eq("org_id", context.org_id).limit(1).execute())
    if not daily or daily[0].get("employee_id") != context.user_id:
        raise HTTPException(404, "Attendance record not found")
    if not body.requested_in_at and not body.requested_out_at:
        raise HTTPException(422, "At least one corrected punch time is required")
    row = {"org_id": context.org_id, "daily_record_id": body.daily_record_id,
           "employee_id": context.user_id, "requested_in_at": body.requested_in_at.isoformat() if body.requested_in_at else None,
           "requested_out_at": body.requested_out_at.isoformat() if body.requested_out_at else None,
           "reason": body.reason, "requested_by": context.user_id, "status": "PENDING"}
    saved = _rows(supabase.table("attendance_corrections").insert(row).execute())
    if not saved:
        raise HTTPException(500, "Correction request could not be created")
    return saved[0]


@router.patch("/corrections/{correction_id}")
async def review_correction(correction_id: str, body: ReviewCorrectionRequest,
                            supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    rows = _rows(supabase.table("attendance_corrections").select("*").eq("id", correction_id)
                 .eq("org_id", context.org_id).limit(1).execute())
    if not rows:
        raise HTTPException(404, "Correction request not found")
    correction = rows[0]
    employee = _employee(supabase, context.org_id, correction["employee_id"])
    authorize(context, "attendance.manage", property_id=employee.get("active_property_id"),
              department_id=employee.get("department_id"))
    if correction.get("status") != "PENDING":
        raise HTTPException(409, "Correction request was already reviewed")
    now = datetime.now(timezone.utc).isoformat()
    status_value = "APPROVED" if body.action == "APPROVE" else "REJECTED"
    updated = _rows(supabase.table("attendance_corrections").update({
        "status": status_value, "reviewed_by": context.user_id, "reviewed_at": now,
        "review_note": body.review_note, "updated_at": now,
    }).eq("id", correction_id).execute())
    if body.action == "APPROVE":
        daily_rows = _rows(supabase.table("attendance_daily_records").select("*")
                           .eq("id", correction["daily_record_id"]).limit(1).execute())
        if not daily_rows:
            raise HTTPException(409, "Underlying attendance record no longer exists")
        daily = daily_rows[0]
        in_at = correction.get("requested_in_at") or daily.get("first_in_at")
        out_at = correction.get("requested_out_at") or daily.get("last_out_at")
        if not in_at or not out_at:
            raise HTTPException(422, "Approved correction must provide a complete IN/OUT pair")
        calculated = calculate_daily_attendance(
            [{"punch_type": "IN", "punched_at": in_at}, {"punch_type": "OUT", "punched_at": out_at}],
            scheduled_start=daily.get("scheduled_start"), scheduled_end=daily.get("scheduled_end"),
            policy=_policy(supabase, context.org_id, daily["property_id"]),
        )
        calculated.update({"validation_status": "VALIDATED", "validated_by": context.user_id,
                           "validated_at": now, "source_version": int(daily.get("source_version", 1)) + 1,
                           "updated_at": now})
        supabase.table("attendance_daily_records").update(calculated).eq("id", daily["id"]).execute()
    return updated[0] if updated else {"id": correction_id, "status": status_value}


@router.get("/corrections")
async def list_corrections(supabase: SupabaseClient, user: CurrentUser, status_filter: str | None = None):
    context = build_access_context(supabase, user)
    query = supabase.table("attendance_corrections").select("*").eq("org_id", context.org_id)
    if context.role in {"EMPLOYEE", "CANDIDATE"}:
        query = query.eq("employee_id", context.user_id)
    else:
        authorize(context, "attendance.read")
    if status_filter:
        query = query.eq("status", status_filter.upper())
    return {"corrections": _rows(query.order("created_at", desc=True).execute())}


@router.patch("/daily/{daily_record_id}/validate")
async def validate_daily_record(daily_record_id: str, body: ValidateDayRequest,
                                supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    rows = _rows(supabase.table("attendance_daily_records").select("*").eq("id", daily_record_id)
                 .eq("org_id", context.org_id).limit(1).execute())
    if not rows:
        raise HTTPException(404, "Attendance record not found")
    daily = rows[0]
    employee = _employee(supabase, context.org_id, daily["employee_id"])
    authorize(context, "attendance.manage", property_id=employee.get("active_property_id"),
              department_id=employee.get("department_id"))
    if daily.get("status") in {"MISSING_PUNCH", "INVALID"} and body.action == "VALIDATE":
        raise HTTPException(422, "Resolve attendance anomalies through a correction before validation")
    now = datetime.now(timezone.utc).isoformat()
    payload = {"validation_status": "VALIDATED" if body.action == "VALIDATE" else "REJECTED",
               "validated_by": context.user_id, "validated_at": now, "updated_at": now}
    saved = _rows(supabase.table("attendance_daily_records").update(payload).eq("id", daily_record_id).execute())
    return saved[0] if saved else {"id": daily_record_id, **payload}


@router.post("/policies")
async def save_policy(body: AttendancePolicyRequest, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "attendance.manage", property_id=body.property_id)
    if body.require_geofence and (body.latitude is None or body.longitude is None):
        raise HTTPException(422, "Property coordinates are required when geofencing is enabled")
    if any(day < 1 or day > 7 for day in body.weekly_off_days):
        raise HTTPException(422, "weekly_off_days must use ISO weekday numbers 1-7")
    row = {**body.model_dump(), "org_id": context.org_id, "created_by": context.user_id,
           "updated_at": datetime.now(timezone.utc).isoformat()}
    existing = _rows(supabase.table("attendance_policies").select("id").eq("org_id", context.org_id)
                     .eq("property_id", body.property_id).limit(1).execute())
    result = (supabase.table("attendance_policies").update(row).eq("id", existing[0]["id"]).execute()
              if existing else supabase.table("attendance_policies").insert(row).execute())
    saved = _rows(result)
    return saved[0] if saved else row


@router.post("/biometric/{provider_code}/webhook")
async def biometric_webhook(provider_code: str, request: Request,
                            x_attendance_token: str | None = Header(None),
                            supabase=Depends(get_supabase_admin_client)):
    """Canonical provider webhook; vendor adapters normalize payloads."""
    if not settings.BIOMETRIC_WEBHOOK_SECRET:
        raise HTTPException(503, "Biometric webhook is not configured")
    try:
        adapter = get_biometric_adapter(provider_code)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    raw = await request.body()
    if not adapter.verify_signature(raw, {"x-attendance-token": x_attendance_token or ""},
                                    settings.BIOMETRIC_WEBHOOK_SECRET):
        raise HTTPException(401, "Invalid biometric webhook signature")
    payload = await request.json()
    property_id, org_id = payload.get("property_id"), payload.get("org_id")
    if not property_id or not org_id:
        raise HTTPException(422, "org_id and property_id are required")
    accepted, failed = 0, []
    for event in adapter.parse_events(payload):
        sync_row = {"org_id": org_id, "property_id": property_id, "provider_code": provider_code.upper(),
                    "external_event_id": event.external_event_id,
                    "employee_external_id": event.employee_external_id, "event_payload": payload,
                    "status": "RECEIVED"}
        duplicate = _rows(supabase.table("biometric_sync_events").select("id").eq("org_id", org_id)
                          .eq("provider_code", provider_code.upper())
                          .eq("external_event_id", event.external_event_id).limit(1).execute())
        if duplicate:
            failed.append({"event_id": event.external_event_id, "error": "Duplicate event"})
            continue
        sync_rows = _rows(supabase.table("biometric_sync_events").insert(sync_row).execute())
        sync_id = sync_rows[0].get("id") if sync_rows else None
        employees = _rows(supabase.table("users").select("id").eq("org_id", org_id)
                          .eq("employee_code", event.employee_external_id).limit(1).execute())
        if not employees:
            if sync_id:
                supabase.table("biometric_sync_events").update({"status": "FAILED", "error_message": "Employee mapping not found",
                    "processed_at": datetime.now(timezone.utc).isoformat()}).eq("id", sync_id).execute()
            failed.append({"event_id": event.external_event_id, "error": "Employee mapping not found"})
            continue
        try:
            punch_row = record_punch(supabase, org_id=org_id, employee_id=employees[0]["id"], property_id=property_id,
                         punch_type=event.punch_type, source="BIOMETRIC", punched_at=event.punched_at,
                         latitude=event.latitude, longitude=event.longitude, gps_accuracy_m=None,
                         actor_id=employees[0]["id"], provider_code=provider_code.upper(),
                         provider_event_id=event.external_event_id, device_id=event.device_id)
            if sync_id:
                supabase.table("biometric_sync_events").update({"status": "PROCESSED",
                    "attendance_punch_id": punch_row.get("id"), "processed_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", sync_id).execute()
            accepted += 1
        except Exception as exc:
            if sync_id:
                supabase.table("biometric_sync_events").update({"status": "FAILED", "error_message": str(exc),
                    "processed_at": datetime.now(timezone.utc).isoformat()}).eq("id", sync_id).execute()
            failed.append({"event_id": event.external_event_id, "error": str(exc)})
    return {"accepted": accepted, "failed": failed}
