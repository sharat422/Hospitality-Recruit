"""Canonical role and permission enforcement for staff and candidate APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from fastapi import HTTPException, status


ROLE_ALIASES = {
    "owner": "OWNER", "super_admin": "OWNER",
    "group_admin": "GROUP_ADMIN_HR", "admin": "GROUP_ADMIN_HR", "hr_admin": "GROUP_ADMIN_HR",
    "general_manager": "GENERAL_MANAGER", "gm": "GENERAL_MANAGER", "property_manager": "GENERAL_MANAGER",
    "hr_manager": "HR_MANAGER", "hiring_manager": "HR_MANAGER", "property_hr": "HR_MANAGER",
    "department_head": "DEPARTMENT_HEAD", "department_manager": "DEPARTMENT_HEAD",
    "supervisor": "SUPERVISOR", "shift_incharge": "SUPERVISOR", "captain": "SUPERVISOR",
    "floor_supervisor": "SUPERVISOR",
    "time_office": "TIME_OFFICE", "security": "TIME_OFFICE", "gate": "TIME_OFFICE",
    "security_desk": "TIME_OFFICE",
    "recruiter": "RECRUITER", "property_recruiter": "RECRUITER",
    "employee": "EMPLOYEE", "viewer": "EMPLOYEE",
    "candidate": "CANDIDATE",
}

ALL_PERMISSIONS = {
    "candidates.read", "candidates.manage", "employees.read", "employees.manage",
    "jobs.read", "jobs.manage", "applications.read", "applications.manage",
    "payroll.read", "payroll.manage", "attendance.read", "attendance.manage",
    "leave.read", "leave.manage", "compliance.read", "compliance.manage",
    "documents.read", "documents.manage", "reports.read", "reports.financial",
    "complaints.create", "complaints.read", "complaints.manage",
    "properties.read", "properties.manage", "financial.read", "financial.manage",
    "performance.read", "performance.manage", "training.read", "training.manage", "career.read", "career.manage",
}

PERMISSION_MATRIX: dict[str, set[str]] = {
    "OWNER": set(ALL_PERMISSIONS),
    "GROUP_ADMIN_HR": set(ALL_PERMISSIONS) - {"financial.manage"},
    "GENERAL_MANAGER": {
        "candidates.read", "employees.read", "employees.manage", "jobs.read", "jobs.manage",
        "applications.read", "applications.manage", "payroll.read", "attendance.read", "attendance.manage",
        "leave.read", "leave.manage", "compliance.read", "documents.read", "documents.manage",
        "reports.read", "reports.financial", "complaints.create", "complaints.read", "complaints.manage",
        "properties.read", "financial.read",
        "performance.read", "performance.manage", "training.read", "training.manage", "career.read", "career.manage",
    },
    "HR_MANAGER": {
        "candidates.read", "candidates.manage", "employees.read", "employees.manage", "jobs.read", "jobs.manage",
        "applications.read", "applications.manage", "payroll.read", "attendance.read", "leave.read", "leave.manage",
        "compliance.read", "compliance.manage", "documents.read", "documents.manage", "reports.read",
        "complaints.create", "complaints.read", "complaints.manage", "properties.read",
        "performance.read", "performance.manage", "training.read", "training.manage", "career.read", "career.manage",
    },
    "DEPARTMENT_HEAD": {
        "candidates.read", "employees.read", "jobs.read", "applications.read", "applications.manage",
        "attendance.read", "attendance.manage", "leave.read", "leave.manage", "documents.read", "reports.read",
        "complaints.create", "properties.read",
        "performance.read", "performance.manage", "training.read", "training.manage", "career.read", "career.manage",
    },
    # Runs a department's floor. May approve leave or pass it to the
    # Department Head (PLAN decision 2), but has no access to pay.
    "SUPERVISOR": {
        "employees.read", "attendance.read", "attendance.manage",
        "leave.read", "leave.manage", "documents.read", "reports.read",
        "complaints.create", "properties.read",
    },
    # The staff entrance desk. Records a manual punch when the biometric
    # device fails, marks late arrivals and flags no-shows (PLAN decision 3).
    # Deliberately has no leave, payroll or roster access.
    "TIME_OFFICE": {
        "employees.read", "attendance.read", "attendance.manage",
        "complaints.create", "properties.read",
    },
    "RECRUITER": {
        "candidates.read", "candidates.manage", "jobs.read", "jobs.manage", "applications.read",
        "applications.manage", "documents.read", "documents.manage", "reports.read", "complaints.create",
        "properties.read",
    },
    "EMPLOYEE": {
        "payroll.read", "attendance.read", "leave.read", "complaints.create", "documents.read", "properties.read",
        "performance.read", "training.read", "career.read",
    },
    "CANDIDATE": {"applications.read", "documents.read"},
}

# An employee who has left keeps NO operational access. The check lives in
# build_access_context, which re-reads the database on every request, so
# revocation takes effect on the next call rather than when a token expires.
#
# The vocabularies differ by design and both are honoured:
#   users.employment_status            -> 'ALUMNI' (set by the exit flow)
#   staff_ops_employee_profiles.status -> 'LEFT' | 'ABSCONDING'
# Migration 068 mirrors the Staff Ops status onto users.employment_status so
# the auth path needs only the users row it already loads.
#
# ON_NOTICE is deliberately absent: someone serving notice is still working
# and still needs their roster.
EXITED_EMPLOYMENT_STATUSES = frozenset({
    "ALUMNI", "LEFT", "ABSCONDING", "TERMINATED", "RESIGNED", "INACTIVE", "SUSPENDED",
})

# What an ex-employee may still reach. Indian employers must keep providing
# payslips, Form 16 and service documents after someone leaves, so cutting all
# access would break a statutory obligation. Combined with the self-only rule
# in authorize(), this is their own records and nothing else.
EXITED_PERMISSIONS = frozenset({"payroll.read", "documents.read"})


def canonical_role(role: str | None) -> str:
    raw = str(role or "candidate").strip()
    upper = raw.upper()
    if upper in PERMISSION_MATRIX:
        return upper
    return ROLE_ALIASES.get(raw.lower(), "CANDIDATE")


def permissions_for(role: str | None) -> set[str]:
    return set(PERMISSION_MATRIX[canonical_role(role)])


def has_permission(role: str | None, permission: str) -> bool:
    return permission in permissions_for(role)


def _rows(result: Any) -> list[dict]:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data
    return [data] if isinstance(data, dict) else []


@dataclass(frozen=True)
class AccessContext:
    user_id: str
    org_id: str
    role: str
    department_id: str | None
    active_property_id: str | None
    permissions: frozenset[str]
    property_ids: frozenset[str]
    department_ids: frozenset[str]
    # True once the person has left. Their role is kept for display and audit;
    # it is `permissions` that has been emptied out.
    is_exited: bool = False
    employment_status: str | None = None


def build_access_context(supabase: Any, claims: dict) -> AccessContext:
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user token")
    users = _rows(supabase.table("users").select(
        "id,org_id,role,department_id,active_property_id,employment_status"
    ).eq("id", user_id).limit(1).execute())
    if not users or not users[0].get("org_id"):
        raise HTTPException(status_code=403, detail="User is not assigned to an organization")
    actor = users[0]
    role = canonical_role(actor.get("role"))
    memberships = _rows(supabase.table("property_memberships").select(
        "property_id,department_id,is_active"
    ).eq("user_id", user_id).eq("is_active", True).execute())
    # Someone who has left keeps only their statutory self-service access,
    # whatever role they held. Evaluated per request, so marking an employee
    # LEFT takes effect on their very next call.
    employment_status = (actor.get("employment_status") or "").strip().upper() or None
    is_exited = employment_status in EXITED_EMPLOYMENT_STATUSES
    permissions = EXITED_PERMISSIONS if is_exited else frozenset(PERMISSION_MATRIX[role])

    return AccessContext(
        user_id=user_id,
        org_id=actor["org_id"],
        role=role,
        department_id=actor.get("department_id"),
        active_property_id=actor.get("active_property_id"),
        permissions=permissions,
        property_ids=frozenset(str(row["property_id"]) for row in memberships if row.get("property_id")),
        department_ids=frozenset(str(row["department_id"]) for row in memberships if row.get("department_id")),
        is_exited=is_exited,
        employment_status=employment_status,
    )


def authorize(
    context: AccessContext,
    permission: str,
    *,
    property_id: str | None = None,
    department_id: str | None = None,
    owner_user_id: str | None = None,
) -> None:
    if permission not in context.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {permission}")
    # An ex-employee is self-only regardless of the role they held, so a
    # departed Department Head cannot read their old team's records.
    if owner_user_id and (context.is_exited or context.role in {"EMPLOYEE", "CANDIDATE"}) \
            and owner_user_id != context.user_id:
        raise HTTPException(status_code=403, detail="You may only access your own record")
    # Exited users never get the org-wide bypass below, even as former OWNER.
    if context.is_exited:
        return
    if context.role in {"OWNER", "GROUP_ADMIN_HR"}:
        return
    if property_id and property_id not in context.property_ids:
        raise HTTPException(status_code=404, detail="Resource not found")
    # A supervisor is scoped to their own department exactly as a department
    # head is: they run a floor, not the hotel.
    if context.role in {"DEPARTMENT_HEAD", "SUPERVISOR"}:
        allowed_departments = set(context.department_ids)
        if context.department_id:
            allowed_departments.add(context.department_id)
        if department_id and department_id not in allowed_departments:
            raise HTTPException(status_code=404, detail="Resource not found")


def serialize_context(context: AccessContext) -> dict:
    return {
        "userId": context.user_id,
        "orgId": context.org_id,
        "role": context.role,
        "permissions": sorted(context.permissions),
        "activePropertyId": context.active_property_id,
        "propertyIds": sorted(context.property_ids),
        "departmentId": context.department_id,
        "departmentIds": sorted(context.department_ids),
        "isExited": context.is_exited,
        "employmentStatus": context.employment_status,
    }
