"""Hotel group and multi-property management APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.property_access_service import (
    get_actor,
    get_property,
    is_group_admin,
    require_group_admin,
    require_property_access,
    require_property_manager,
    result_rows,
)

router = APIRouter()
CurrentUser = Annotated[dict, Depends(get_current_user)]
now_iso = lambda: datetime.now(timezone.utc).isoformat()


PROPERTY_TYPES = {
    "HOTEL", "RESTAURANT", "RESORT", "EVENTS_VENUE", "CRUISE",
    "THEME_PARK", "HOSTEL", "SERVICED_APARTMENT", "CLOUD_KITCHEN", "OTHER",
}
SETTING_FIELDS = {
    "hr": "hr_settings",
    "payroll": "payroll_settings",
    "compliance": "compliance_settings",
    "branding": "branding_settings",
}


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    legal_name: Optional[str] = Field(None, max_length=255)
    group_code: Optional[str] = Field(None, max_length=40)
    registered_address: Optional[dict] = None
    contact_email: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=30)
    website_url: Optional[str] = None
    logo_url: Optional[str] = None
    brand_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class PropertyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    code: Optional[str] = Field(None, max_length=40)
    type: str = "HOTEL"
    description: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "India"
    region: Optional[str] = None
    timezone: str = "Asia/Kolkata"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    star_rating: Optional[float] = Field(None, ge=1, le=5)
    room_count: Optional[int] = Field(None, ge=0)
    employee_capacity: Optional[int] = Field(None, ge=0)
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    website_url: Optional[str] = None
    logo_url: Optional[str] = None
    brand_color: str = Field("#7C3AED", pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        value = value.upper()
        if value not in PROPERTY_TYPES:
            raise ValueError("Unsupported property type")
        return value


class PropertyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    code: Optional[str] = Field(None, max_length=40)
    type: Optional[str] = None
    description: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    timezone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    star_rating: Optional[float] = Field(None, ge=1, le=5)
    room_count: Optional[int] = Field(None, ge=0)
    employee_capacity: Optional[int] = Field(None, ge=0)
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    website_url: Optional[str] = None
    logo_url: Optional[str] = None
    brand_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_active: Optional[bool] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.upper()
        if value not in PROPERTY_TYPES:
            raise ValueError("Unsupported property type")
        return value


class DepartmentCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=2, max_length=120)
    head_user_id: Optional[str] = None
    budgeted_headcount: int = Field(0, ge=0)
    current_headcount: int = Field(0, ge=0)


class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    head_user_id: Optional[str] = None
    budgeted_headcount: Optional[int] = Field(None, ge=0)
    current_headcount: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class MembershipUpsert(BaseModel):
    user_id: str
    role: Literal[
        "PROPERTY_ADMIN", "PROPERTY_HR", "PROPERTY_RECRUITER", "PROPERTY_MANAGER",
        "PAYROLL_ADMIN", "COMPLIANCE_ADMIN", "VIEWER",
    ] = "PROPERTY_RECRUITER"
    is_default: bool = False
    is_active: bool = True


class SettingsUpdate(BaseModel):
    settings: dict[str, Any]


def _clean(model: BaseModel) -> dict:
    return model.model_dump(exclude_none=True)


@router.get("/group")
async def get_group(supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    rows = result_rows(supabase.table("organizations").select("*").eq("id", actor["org_id"]).limit(1).execute())
    if not rows:
        raise HTTPException(status_code=404, detail="Hotel group not found.")
    return {"group": rows[0], "can_manage": is_group_admin(actor)}


@router.patch("/group")
async def update_group(body: GroupUpdate, supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    require_group_admin(actor)
    payload = {**_clean(body), "updated_at": now_iso()}
    rows = result_rows(supabase.table("organizations").update(payload).eq("id", actor["org_id"]).execute())
    return {"group": rows[0] if rows else payload}


@router.get("/properties")
async def list_properties(
    supabase: SupabaseClient,
    user: CurrentUser,
    include_inactive: bool = Query(False),
):
    actor = get_actor(supabase, user)
    query = supabase.table("properties").select("*").eq("org_id", actor["org_id"])
    if not include_inactive:
        query = query.eq("is_active", True)
    properties = result_rows(query.order("name").execute())
    if not is_group_admin(actor):
        memberships = result_rows(
            supabase.table("property_memberships").select("property_id, role, is_default")
            .eq("org_id", actor["org_id"]).eq("user_id", actor["id"]).eq("is_active", True).execute()
        )
        roles = {m["property_id"]: m for m in memberships}
        properties = [{**p, "membership": roles[p["id"]]} for p in properties if p.get("id") in roles]
    return {"properties": properties, "active_property_id": actor.get("active_property_id")}


@router.post("/properties", status_code=status.HTTP_201_CREATED)
async def create_property(body: PropertyCreate, supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    require_group_admin(actor)
    payload = {
        **_clean(body), "org_id": actor["org_id"], "created_by": actor["id"],
        "location": ", ".join(filter(None, [body.city, body.state, body.country])),
    }
    rows = result_rows(supabase.table("properties").insert(payload).execute())
    if not rows:
        raise HTTPException(status_code=500, detail="Property could not be created.")
    prop = rows[0]
    supabase.table("property_memberships").insert({
        "org_id": actor["org_id"], "property_id": prop["id"], "user_id": actor["id"],
        "role": "PROPERTY_ADMIN", "is_default": not bool(actor.get("active_property_id")),
        "created_by": actor["id"],
    }).execute()
    return {"property": prop}


@router.get("/properties/{property_id}")
async def get_property_profile(property_id: str, supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    prop, membership = require_property_access(supabase, actor, property_id)
    departments = result_rows(
        supabase.table("property_departments").select("*").eq("org_id", actor["org_id"])
        .eq("property_id", property_id).order("name").execute()
    )
    return {"property": prop, "departments": departments, "membership": membership, "can_manage": is_group_admin(actor) or bool(membership and membership.get("role") in {"PROPERTY_ADMIN", "PROPERTY_HR", "PROPERTY_MANAGER"})}


@router.patch("/properties/{property_id}")
async def update_property(property_id: str, body: PropertyUpdate, supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    require_property_manager(supabase, actor, property_id)
    payload = {**_clean(body), "updated_at": now_iso()}
    rows = result_rows(
        supabase.table("properties").update(payload).eq("id", property_id)
        .eq("org_id", actor["org_id"]).execute()
    )
    return {"property": rows[0] if rows else {"id": property_id, **payload}}


@router.post("/properties/{property_id}/switch")
async def switch_property(property_id: str, supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    prop, _ = require_property_access(supabase, actor, property_id)
    supabase.table("users").update({"active_property_id": property_id, "updated_at": now_iso()}).eq("id", actor["id"]).eq("org_id", actor["org_id"]).execute()
    return {"active_property_id": property_id, "property": prop}


@router.get("/properties/{property_id}/departments")
async def list_departments(property_id: str, supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    require_property_access(supabase, actor, property_id)
    rows = result_rows(supabase.table("property_departments").select("*").eq("org_id", actor["org_id"]).eq("property_id", property_id).order("name").execute())
    return {"departments": rows}


@router.post("/properties/{property_id}/departments", status_code=201)
async def create_department(property_id: str, body: DepartmentCreate, supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    require_property_manager(supabase, actor, property_id)
    payload = {**_clean(body), "code": body.code.upper(), "org_id": actor["org_id"], "property_id": property_id}
    rows = result_rows(supabase.table("property_departments").insert(payload).execute())
    return {"department": rows[0] if rows else payload}


@router.patch("/properties/{property_id}/departments/{department_id}")
async def update_department(property_id: str, department_id: str, body: DepartmentUpdate, supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    require_property_manager(supabase, actor, property_id)
    payload = {**_clean(body), "updated_at": now_iso()}
    rows = result_rows(supabase.table("property_departments").update(payload).eq("id", department_id).eq("property_id", property_id).eq("org_id", actor["org_id"]).execute())
    if not rows:
        raise HTTPException(status_code=404, detail="Department not found.")
    return {"department": rows[0]}


@router.get("/properties/{property_id}/members")
async def list_members(property_id: str, supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    require_property_manager(supabase, actor, property_id)
    rows = result_rows(supabase.table("property_memberships").select("*").eq("org_id", actor["org_id"]).eq("property_id", property_id).execute())
    return {"members": rows}


@router.post("/properties/{property_id}/members")
async def upsert_member(property_id: str, body: MembershipUpsert, supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    require_group_admin(actor)
    get_property(supabase, actor, property_id)
    target = result_rows(supabase.table("users").select("id, org_id").eq("id", body.user_id).eq("org_id", actor["org_id"]).limit(1).execute())
    if not target:
        raise HTTPException(status_code=404, detail="User not found in this hotel group.")
    existing = result_rows(supabase.table("property_memberships").select("id").eq("property_id", property_id).eq("user_id", body.user_id).limit(1).execute())
    payload = {**_clean(body), "org_id": actor["org_id"], "property_id": property_id, "updated_at": now_iso()}
    if existing:
        rows = result_rows(supabase.table("property_memberships").update(payload).eq("id", existing[0]["id"]).execute())
    else:
        payload["created_by"] = actor["id"]
        rows = result_rows(supabase.table("property_memberships").insert(payload).execute())
    return {"membership": rows[0] if rows else payload}


@router.get("/properties/{property_id}/settings/{setting_type}")
async def get_settings(property_id: str, setting_type: str, supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    prop, _ = require_property_access(supabase, actor, property_id)
    field = SETTING_FIELDS.get(setting_type.lower())
    if not field:
        raise HTTPException(status_code=404, detail="Unknown settings type.")
    return {"property_id": property_id, "setting_type": setting_type.lower(), "settings": prop.get(field) or {}}


@router.patch("/properties/{property_id}/settings/{setting_type}")
async def update_settings(property_id: str, setting_type: str, body: SettingsUpdate, supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    require_property_manager(supabase, actor, property_id)
    field = SETTING_FIELDS.get(setting_type.lower())
    if not field:
        raise HTTPException(status_code=404, detail="Unknown settings type.")
    rows = result_rows(supabase.table("properties").update({field: body.settings, "updated_at": now_iso()}).eq("id", property_id).eq("org_id", actor["org_id"]).execute())
    return {"property_id": property_id, "setting_type": setting_type.lower(), "settings": (rows[0].get(field) if rows else body.settings)}


@router.get("/hospitality-roles")
async def list_hospitality_roles(supabase: SupabaseClient, user: CurrentUser, department: Optional[str] = Query(None)):
    get_actor(supabase, user)
    query = supabase.table("role_templates").select("*")
    if department:
        query = query.eq("department", department)
    return {"roles": result_rows(query.order("department").order("display_name").execute())}


@router.get("/reports/group")
async def group_report(supabase: SupabaseClient, user: CurrentUser):
    actor = get_actor(supabase, user)
    require_group_admin(actor)
    properties = result_rows(supabase.table("properties").select("id, name, type, city, state, is_active").eq("org_id", actor["org_id"]).execute())
    departments = result_rows(supabase.table("property_departments").select("property_id, budgeted_headcount, current_headcount").eq("org_id", actor["org_id"]).eq("is_active", True).execute())
    jobs = result_rows(supabase.table("jobs").select("id, property_id, status, openings_count").eq("org_id", actor["org_id"]).execute())
    campaigns = result_rows(supabase.table("hiring_campaigns").select("id, property_id, target_hire_count, current_hire_count, status").execute())
    by_property = []
    for prop in properties:
        pid = prop["id"]
        depts = [d for d in departments if d.get("property_id") == pid]
        pjobs = [j for j in jobs if j.get("property_id") == pid]
        pcamps = [c for c in campaigns if c.get("property_id") == pid]
        by_property.append({
            **prop,
            "department_count": len(depts),
            "budgeted_headcount": sum(int(d.get("budgeted_headcount") or 0) for d in depts),
            "current_headcount": sum(int(d.get("current_headcount") or 0) for d in depts),
            "open_jobs": sum(1 for j in pjobs if str(j.get("status")).lower() == "open"),
            "open_positions": sum(int(j.get("openings_count") or 1) for j in pjobs if str(j.get("status")).lower() == "open"),
            "active_campaigns": sum(1 for c in pcamps if str(c.get("status")).upper() == "ACTIVE"),
        })
    return {
        "summary": {
            "property_count": len(properties),
            "active_property_count": sum(1 for p in properties if p.get("is_active", True)),
            "department_count": len(departments),
            "budgeted_headcount": sum(int(d.get("budgeted_headcount") or 0) for d in departments),
            "current_headcount": sum(int(d.get("current_headcount") or 0) for d in departments),
        },
        "properties": by_property,
    }
