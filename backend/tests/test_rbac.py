from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.rbac_service import (
    AccessContext, authorize, canonical_role, has_permission, permissions_for,
)


def context(role: str, *, properties=("property-a",), departments=("dept-a",)) -> AccessContext:
    return AccessContext(
        user_id="user-a", org_id="org-a", role=role, department_id="dept-a",
        active_property_id="property-a", permissions=frozenset(permissions_for(role)),
        property_ids=frozenset(properties), department_ids=frozenset(departments),
    )


@pytest.mark.parametrize("legacy,expected", [
    ("admin", "GROUP_ADMIN_HR"), ("hiring_manager", "HR_MANAGER"),
    ("PROPERTY_RECRUITER", "RECRUITER"), ("gm", "GENERAL_MANAGER"),
    ("employee", "EMPLOYEE"), ("candidate", "CANDIDATE"),
])
def test_legacy_roles_are_canonicalized(legacy, expected):
    assert canonical_role(legacy) == expected


def test_owner_has_all_permissions():
    assert has_permission("OWNER", "financial.manage")
    assert has_permission("OWNER", "compliance.manage")


def test_recruiter_cannot_escalate_to_payroll():
    with pytest.raises(HTTPException) as exc:
        authorize(context("RECRUITER"), "payroll.read")
    assert exc.value.status_code == 403


def test_employee_cannot_read_another_employee_record():
    with pytest.raises(HTTPException) as exc:
        authorize(context("EMPLOYEE"), "payroll.read", owner_user_id="user-b")
    assert exc.value.status_code == 403


def test_cross_property_access_is_concealed():
    with pytest.raises(HTTPException) as exc:
        authorize(context("RECRUITER"), "candidates.read", property_id="property-b")
    assert exc.value.status_code == 404


def test_department_head_cannot_cross_department():
    with pytest.raises(HTTPException) as exc:
        authorize(context("DEPARTMENT_HEAD"), "applications.read", department_id="dept-b")
    assert exc.value.status_code == 404


def test_department_head_can_manage_own_department_applications():
    authorize(context("DEPARTMENT_HEAD"), "applications.manage", property_id="property-a", department_id="dept-a")


def test_group_admin_can_cross_properties_inside_tenant():
    authorize(context("GROUP_ADMIN_HR", properties=()), "employees.manage", property_id="property-b")


def test_candidate_cannot_read_candidate_directory():
    with pytest.raises(HTTPException) as exc:
        authorize(context("CANDIDATE"), "candidates.read")
    assert exc.value.status_code == 403
