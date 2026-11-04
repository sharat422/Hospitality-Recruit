"""Per-hotel attendance codes, comp-off ledger and month-end payroll input."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.attendance_codes_service import (
    DEFAULT_CODES,
    attendance_summary,
    available_comp_off,
    code_from_row,
    comp_off_earned,
    expired_comp_off,
)
from app.services.rbac_service import authorize, build_access_context

router = APIRouter()
CurrentUser = Annotated[dict, Depends(get_current_user)]


def rows(result):
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_rows() -> list[dict]:
    return [{"code": c.code, "label_en": c.label_en, "label_hi": c.label_hi,
             "lop_factor": c.lop_factor, "counts_as_worked": c.counts_as_worked,
             "consumes_leave_type": c.consumes_leave_type,
             "requires_approval": c.requires_approval, "rules": c.rules,
             "display_order": c.display_order, "is_active": True}
            for c in DEFAULT_CODES]


def _codes_for(supabase, ctx, property_id: str):
    """Stored codes for a hotel, or the hospitality defaults if none set."""
    stored = rows(supabase.table("attendance_codes").select("*")
                  .eq("org_id", ctx.org_id).eq("property_id", property_id)
                  .eq("is_active", True).order("display_order").execute())
    source = stored or _default_rows()
    return [code_from_row(r) for r in source], ("PROPERTY" if stored else "DEFAULT")


class CodeBody(BaseModel):
    property_id: str
    code: str = Field(min_length=1, max_length=8, pattern=r"^[A-Z][A-Z_]{0,7}$")
    label_en: str = Field(min_length=1, max_length=60)
    label_hi: str | None = Field(None, max_length=60)
    lop_factor: float = Field(0, ge=0, le=1)
    counts_as_worked: bool = False
    consumes_leave_type: Literal["CASUAL", "SICK", "EARNED", "COMP_OFF",
                                 "MATERNITY", "PATERNITY"] | None = None
    requires_approval: bool = False
    rules: dict = Field(default_factory=dict)
    display_order: int = Field(100, ge=0, le=9999)
    is_active: bool = True


@router.get("/codes")
async def list_codes(property_id: str, supabase: SupabaseClient, user: CurrentUser):
    """Attendance codes for a hotel, falling back to hospitality defaults."""
    ctx = build_access_context(supabase, user)
    authorize(ctx, "attendance.read", property_id=property_id)
    codes, source = _codes_for(supabase, ctx, property_id)
    return {"source": source, "codes": [
        {"code": c.code, "label_en": c.label_en, "label_hi": c.label_hi,
         "lop_factor": c.lop_factor, "counts_as_worked": c.counts_as_worked,
         "consumes_leave_type": c.consumes_leave_type,
         "requires_approval": c.requires_approval, "rules": c.rules,
         "display_order": c.display_order} for c in codes]}


@router.post("/codes/seed", status_code=201)
async def seed_codes(property_id: str, supabase: SupabaseClient, user: CurrentUser):
    """Copy the defaults into this hotel so they can be edited."""
    ctx = build_access_context(supabase, user)
    authorize(ctx, "attendance.manage", property_id=property_id)
    existing = rows(supabase.table("attendance_codes").select("id")
                    .eq("org_id", ctx.org_id).eq("property_id", property_id).execute())
    if existing:
        raise HTTPException(409, "This property already has attendance codes")
    payload = [{**row, "org_id": ctx.org_id, "property_id": property_id}
               for row in _default_rows()]
    saved = rows(supabase.table("attendance_codes").insert(payload).execute())
    return {"seeded": len(saved)}


@router.put("/codes")
async def upsert_code(body: CodeBody, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user)
    authorize(ctx, "attendance.manage", property_id=body.property_id)
    payload = {**body.model_dump(), "org_id": ctx.org_id, "updated_at": now()}
    saved = rows(supabase.table("attendance_codes")
                 .upsert(payload, on_conflict="property_id,code").execute())
    if not saved:
        raise HTTPException(500, "Failed to save attendance code")
    return saved[0]


@router.get("/summary")
async def month_summary(
    property_id: str,
    employee_id: str,
    year: int,
    month: int,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Month-end attendance figures for one employee — the payroll input."""
    ctx = build_access_context(supabase, user)
    authorize(ctx, "attendance.read", property_id=property_id)
    if not 1 <= month <= 12:
        raise HTTPException(422, "month must be between 1 and 12")

    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1)
    records = rows(supabase.table("attendance_daily_records").select("*")
                   .eq("org_id", ctx.org_id).eq("property_id", property_id)
                   .eq("employee_id", employee_id)
                   .gte("attendance_date", start.isoformat())
                   .lt("attendance_date", end.isoformat()).execute())
    codes, source = _codes_for(supabase, ctx, property_id)
    return {**attendance_summary(records, codes), "code_source": source,
            "year": year, "month": month, "employee_id": employee_id}


@router.get("/comp-off")
async def comp_off_balance(
    property_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
    employee_id: str | None = None,
):
    """Live comp-off balance, soonest to expire first."""
    ctx = build_access_context(supabase, user)
    target = employee_id or ctx.user_id
    if target != ctx.user_id:
        authorize(ctx, "attendance.read", property_id=property_id)
    ledger = rows(supabase.table("comp_off_ledger").select("*")
                  .eq("org_id", ctx.org_id).eq("property_id", property_id)
                  .eq("employee_id", target).execute())
    live = available_comp_off(ledger)
    return {"employee_id": target, "available_days": len(live),
            "entries": live, "expired_pending_sweep": len(expired_comp_off(ledger))}


@router.post("/comp-off/accrue", status_code=201)
async def accrue_comp_off(
    property_id: str,
    employee_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
    date_from: date = Query(...),
    date_to: date = Query(...),
):
    """Grant comp-off for rostered rest days the employee actually worked."""
    ctx = build_access_context(supabase, user)
    authorize(ctx, "attendance.manage", property_id=property_id)
    if date_to < date_from:
        raise HTTPException(422, "date_to must be on or after date_from")

    records = rows(supabase.table("attendance_daily_records").select("*")
                   .eq("org_id", ctx.org_id).eq("property_id", property_id)
                   .eq("employee_id", employee_id)
                   .gte("attendance_date", date_from.isoformat())
                   .lte("attendance_date", date_to.isoformat()).execute())
    codes, _ = _codes_for(supabase, ctx, property_id)
    entitlements = comp_off_earned(records, codes)
    if not entitlements:
        return {"granted": 0, "entries": []}

    payload = [{**e, "org_id": ctx.org_id, "property_id": property_id,
                "employee_id": employee_id} for e in entitlements]
    # The ledger is unique on (employee, earned_for_date), so re-running a
    # range tops up newly worked rest days without duplicating old ones.
    saved = rows(supabase.table("comp_off_ledger")
                 .upsert(payload, on_conflict="employee_id,earned_for_date").execute())
    return {"granted": len(saved), "entries": saved}


@router.post("/comp-off/sweep-expired")
async def sweep_expired(property_id: str, supabase: SupabaseClient, user: CurrentUser):
    """Mark lapsed comp-off as EXPIRED so balances stay honest."""
    ctx = build_access_context(supabase, user)
    authorize(ctx, "attendance.manage", property_id=property_id)
    ledger = rows(supabase.table("comp_off_ledger").select("*")
                  .eq("org_id", ctx.org_id).eq("property_id", property_id)
                  .eq("status", "AVAILABLE").execute())
    lapsed = expired_comp_off(ledger)
    for entry in lapsed:
        supabase.table("comp_off_ledger").update(
            {"status": "EXPIRED"}).eq("id", entry["id"]).execute()
    return {"expired": len(lapsed)}
