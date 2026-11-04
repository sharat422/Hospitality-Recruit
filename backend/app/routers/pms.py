"""Hotel PMS connection, occupancy sync and occupancy-driven staffing demand."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.pms_adapters import (
    OccupancyDay,
    get_pms_adapter,
    provider_catalog,
    resolve_config,
)
from app.services.pms_staffing_service import (
    DEFAULT_RATIOS,
    hiring_signal,
    plan_summary,
    ratio_from_row,
    staffing_plan,
)
from app.services.rbac_service import authorize, build_access_context

router = APIRouter()
CurrentUser = Annotated[dict, Depends(get_current_user)]

MAX_SYNC_DAYS = 120


def rows(result):
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public(connection: dict) -> dict:
    """Strip anything secret before a connection leaves the API.

    `credential_env_var` names the variable; the value is resolved at sync time
    and never stored or returned. A caller that has written an `api_key` into
    `config` by hand still must not get it back out.
    """
    config = {k: v for k, v in (connection.get("config") or {}).items()
              if k not in {"api_key", "password", "secret", "token"}}
    return {**connection, "config": config,
            "credential_configured": bool(
                connection.get("credential_env_var")
                and os.environ.get(connection["credential_env_var"]))}


class ConnectionBody(BaseModel):
    property_id: str
    provider_code: Literal["MOCK", "IDS_NEXT", "EZEE", "HOTELOGIX"]
    base_url: str | None = None
    property_ref: str | None = Field(None, max_length=120)
    rooms_available: int | None = Field(None, gt=0, le=10000)
    credential_env_var: str | None = Field(None, max_length=80, pattern=r"^[A-Z0-9_]+$")
    config: dict = Field(default_factory=dict)
    is_active: bool = True

    @model_validator(mode="after")
    def rest_needs_endpoint(self):
        if self.provider_code != "MOCK" and not self.base_url:
            raise ValueError("base_url is required for a REST PMS provider")
        return self


class RatioBody(BaseModel):
    property_id: str
    department_code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z0-9_]+$")
    department_name: str = Field(min_length=2, max_length=120)
    driver: Literal["OCCUPIED_ROOMS", "ARRIVALS", "DEPARTURES", "COVERS", "FIXED"] = "OCCUPIED_ROOMS"
    units_per_staff: float = Field(1, gt=0, le=10000)
    min_staff: int = Field(0, ge=0, le=500)
    covers_per_room: float = Field(1.6, gt=0, le=10)


@router.get("/providers")
async def list_providers(user: CurrentUser):
    """Supported PMS products. `verified` is false where the field map is untested."""
    return provider_catalog()


@router.get("/connections")
async def get_connection(property_id: str, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user)
    authorize(ctx, "properties.read", property_id=property_id)
    found = rows(supabase.table("pms_connections").select("*")
                 .eq("org_id", ctx.org_id).eq("property_id", property_id).limit(1).execute())
    return _public(found[0]) if found else None


@router.put("/connections")
async def upsert_connection(body: ConnectionBody, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user)
    authorize(ctx, "properties.manage", property_id=body.property_id)
    payload = {**body.model_dump(), "org_id": ctx.org_id,
               "created_by": ctx.user_id, "updated_at": now()}
    saved = rows(supabase.table("pms_connections")
                 .upsert(payload, on_conflict="property_id").execute())
    if not saved:
        raise HTTPException(500, "Failed to save PMS connection")
    return _public(saved[0])


@router.post("/connections/{connection_id}/sync")
async def sync_occupancy(
    connection_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
    days_ahead: int = Query(30, ge=1, le=MAX_SYNC_DAYS),
):
    """Pull the occupancy forecast from the PMS and store it."""
    ctx = build_access_context(supabase, user)
    found = rows(supabase.table("pms_connections").select("*")
                 .eq("id", connection_id).eq("org_id", ctx.org_id).limit(1).execute())
    if not found:
        raise HTTPException(404, "PMS connection not found")
    connection = found[0]
    authorize(ctx, "properties.manage", property_id=connection["property_id"])
    if not connection.get("is_active"):
        raise HTTPException(409, "PMS connection is inactive")

    config = resolve_config(connection["provider_code"], connection)
    if env_var := connection.get("credential_env_var"):
        api_key = os.environ.get(env_var)
        if not api_key and connection["provider_code"] != "MOCK":
            raise HTTPException(400, f"Credential env var {env_var} is not set on the server")
        config["api_key"] = api_key

    date_from = date.today()
    date_to = date_from + timedelta(days=days_ahead - 1)
    try:
        days = get_pms_adapter(connection["provider_code"]).fetch_occupancy(
            config, date_from, date_to)
    except Exception as exc:  # vendor outage, bad field map, auth failure
        supabase.table("pms_connections").update({
            "last_sync_at": now(), "last_sync_status": "FAILED",
            "last_sync_error": str(exc)[:500]}).eq("id", connection_id).execute()
        raise HTTPException(502, f"PMS sync failed: {exc}")

    if days:
        supabase.table("pms_occupancy_forecasts").upsert(
            [{**day.as_row(), "org_id": ctx.org_id,
              "property_id": connection["property_id"],
              "source": connection["provider_code"], "synced_at": now()}
             for day in days],
            on_conflict="property_id,business_date").execute()

    supabase.table("pms_connections").update({
        "last_sync_at": now(), "last_sync_status": "OK",
        "last_sync_error": None}).eq("id", connection_id).execute()
    return {"synced_days": len(days), "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(), "provider": connection["provider_code"]}


@router.get("/ratios")
async def list_ratios(property_id: str, supabase: SupabaseClient, user: CurrentUser):
    """Staffing ratios for a property, falling back to hospitality defaults."""
    ctx = build_access_context(supabase, user)
    authorize(ctx, "properties.read", property_id=property_id)
    stored = rows(supabase.table("department_staffing_ratios").select("*")
                  .eq("org_id", ctx.org_id).eq("property_id", property_id)
                  .eq("is_active", True).execute())
    if stored:
        return {"source": "PROPERTY", "ratios": stored}
    return {"source": "DEFAULT", "ratios": [
        {"department_code": r.department_code, "department_name": r.department_name,
         "driver": r.driver, "units_per_staff": r.units_per_staff,
         "min_staff": r.min_staff, "covers_per_room": r.covers_per_room}
        for r in DEFAULT_RATIOS]}


@router.put("/ratios")
async def upsert_ratio(body: RatioBody, supabase: SupabaseClient, user: CurrentUser):
    ctx = build_access_context(supabase, user)
    authorize(ctx, "properties.manage", property_id=body.property_id)
    payload = {**body.model_dump(), "org_id": ctx.org_id, "updated_at": now()}
    saved = rows(supabase.table("department_staffing_ratios")
                 .upsert(payload, on_conflict="property_id,department_code").execute())
    if not saved:
        raise HTTPException(500, "Failed to save staffing ratio")
    return saved[0]


def _scheduled_headcount(supabase, ctx, property_id: str,
                         date_from: date, date_to: date) -> dict[tuple[str, date], int]:
    """Rostered headcount keyed by (department_code, business_date).

    The schedule view carries department_id and department *name*; ratios are
    keyed by department *code*, so map through property_departments.
    """
    departments = rows(supabase.table("property_departments").select("id,code")
                       .eq("org_id", ctx.org_id).eq("property_id", property_id).execute())
    code_by_id = {d["id"]: d["code"] for d in departments}

    assignments = rows(supabase.table("v_workforce_schedule")
                       .select("department_id,start_date,employee_id")
                       .eq("org_id", ctx.org_id).eq("property_id", property_id)
                       .gte("start_date", date_from.isoformat())
                       .lte("start_date", f"{date_to.isoformat()}T23:59:59").execute())

    counts: dict[tuple[str, date], set] = {}
    for row in assignments:
        code = code_by_id.get(row.get("department_id"))
        raw_date = row.get("start_date")
        if not code or not raw_date:
            continue
        key = (code, date.fromisoformat(str(raw_date)[:10]))
        # One person working two shifts in a day is one head, not two.
        counts.setdefault(key, set()).add(row.get("employee_id"))
    return {key: len(employees) for key, employees in counts.items()}


@router.get("/staffing-plan")
async def get_staffing_plan(
    property_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None,
    min_short_days: int = Query(3, ge=1, le=30),
):
    """Required vs rostered headcount per department per day, plus hiring signals."""
    ctx = build_access_context(supabase, user)
    authorize(ctx, "properties.read", property_id=property_id)

    date_from = date_from or date.today()
    date_to = date_to or date_from + timedelta(days=13)
    if date_to < date_from:
        raise HTTPException(422, "date_to must be on or after date_from")
    if (date_to - date_from).days >= MAX_SYNC_DAYS:
        raise HTTPException(422, f"Horizon cannot exceed {MAX_SYNC_DAYS} days")

    forecasts = rows(supabase.table("pms_occupancy_forecasts").select("*")
                     .eq("org_id", ctx.org_id).eq("property_id", property_id)
                     .gte("business_date", date_from.isoformat())
                     .lte("business_date", date_to.isoformat())
                     .order("business_date").execute())
    if not forecasts:
        return {"summary": plan_summary([]), "plan": [], "hiring_signals": [],
                "message": "No occupancy forecast for this range. Sync the PMS connection first."}

    days = [OccupancyDay(
        business_date=date.fromisoformat(str(f["business_date"])[:10]),
        rooms_available=int(f["rooms_available"]), rooms_sold=int(f["rooms_sold"]),
        arrivals=int(f.get("arrivals") or 0), departures=int(f.get("departures") or 0),
    ) for f in forecasts]

    stored = rows(supabase.table("department_staffing_ratios").select("*")
                  .eq("org_id", ctx.org_id).eq("property_id", property_id)
                  .eq("is_active", True).execute())
    ratios = [ratio_from_row(r) for r in stored] if stored else list(DEFAULT_RATIOS)

    plan = staffing_plan(days, ratios, _scheduled_headcount(
        supabase, ctx, property_id, date_from, date_to))
    return {"summary": plan_summary(plan), "plan": plan,
            "hiring_signals": hiring_signal(plan, min_short_days=min_short_days),
            "ratio_source": "PROPERTY" if stored else "DEFAULT"}
