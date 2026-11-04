"""Tenant and property authorization helpers for hotel management."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


GROUP_ADMIN_ROLES = {"admin", "super_admin", "owner", "group_admin"}
PROPERTY_MANAGER_ROLES = {"PROPERTY_ADMIN", "PROPERTY_HR", "PROPERTY_MANAGER"}


def first_row(result: Any) -> dict | None:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    return data if isinstance(data, dict) else None


def result_rows(result: Any) -> list[dict]:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data
    return [data] if isinstance(data, dict) else []


def get_actor(supabase: Any, claims: dict) -> dict:
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user token.")
    actor = first_row(
        supabase.table("users")
        .select("id, org_id, email, full_name, role, active_property_id")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if not actor or not actor.get("org_id"):
        raise HTTPException(status_code=403, detail="User is not assigned to an organization.")
    return actor


def is_group_admin(actor: dict) -> bool:
    return str(actor.get("role") or "").lower() in GROUP_ADMIN_ROLES


def require_group_admin(actor: dict) -> None:
    if not is_group_admin(actor):
        raise HTTPException(status_code=403, detail="Group administrator access required.")


def get_property(supabase: Any, actor: dict, property_id: str) -> dict:
    prop = first_row(
        supabase.table("properties")
        .select("*")
        .eq("id", property_id)
        .eq("org_id", actor["org_id"])
        .limit(1)
        .execute()
    )
    if not prop:
        # Do not reveal whether a property exists in another tenant.
        raise HTTPException(status_code=404, detail="Property not found.")
    return prop


def get_membership(supabase: Any, actor: dict, property_id: str) -> dict | None:
    return first_row(
        supabase.table("property_memberships")
        .select("*")
        .eq("org_id", actor["org_id"])
        .eq("property_id", property_id)
        .eq("user_id", actor["id"])
        .eq("is_active", True)
        .limit(1)
        .execute()
    )


def require_property_access(supabase: Any, actor: dict, property_id: str) -> tuple[dict, dict | None]:
    prop = get_property(supabase, actor, property_id)
    membership = None if is_group_admin(actor) else get_membership(supabase, actor, property_id)
    if not is_group_admin(actor) and not membership:
        raise HTTPException(status_code=403, detail="You do not have access to this property.")
    return prop, membership


def require_property_manager(supabase: Any, actor: dict, property_id: str) -> dict:
    prop, membership = require_property_access(supabase, actor, property_id)
    if not is_group_admin(actor) and str((membership or {}).get("role")) not in PROPERTY_MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Property manager access required.")
    return prop
