"""Authenticated RBAC introspection and authorization endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.rbac_service import (
    PERMISSION_MATRIX, authorize, build_access_context, serialize_context,
)

router = APIRouter()
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.get("/me")
def my_access(supabase: SupabaseClient, user: CurrentUser):
    return serialize_context(build_access_context(supabase, user))


@router.get("/roles")
def role_matrix(supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "properties.manage")
    return {role: sorted(permissions) for role, permissions in PERMISSION_MATRIX.items()}


@router.get("/check/{permission}")
def check_permission(
    permission: str,
    supabase: SupabaseClient,
    user: CurrentUser,
    property_id: str | None = Header(None, alias="X-Property-ID"),
    department_id: str | None = Header(None, alias="X-Department-ID"),
):
    context = build_access_context(supabase, user)
    authorize(context, permission, property_id=property_id, department_id=department_id)
    return {"allowed": True, "permission": permission}
