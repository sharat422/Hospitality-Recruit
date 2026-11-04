"""Employee 360 aggregation and sensitive-field authorization tests."""

import pytest
from fastapi import HTTPException

from app.services.employee_360_service import get_employee_360, redact_statutory, redact_upi
from app.services.rbac_service import AccessContext, permissions_for
from tests.conftest import MockSupabase


EMPLOYEE = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
OTHER = "ffffffff-ffff-ffff-ffff-ffffffffffff"
ORG = "11111111-1111-1111-1111-111111111111"
PROPERTY = "22222222-2222-2222-2222-222222222222"
DEPARTMENT = "33333333-3333-3333-3333-333333333333"


def context(user_id=EMPLOYEE, role="EMPLOYEE", properties=(), departments=()):
    return AccessContext(
        user_id=user_id, org_id=ORG, role=role, department_id=None, active_property_id=None,
        permissions=frozenset(permissions_for(role)), property_ids=frozenset(properties),
        department_ids=frozenset(departments),
    )


def employee_row(employee_id=EMPLOYEE):
    return {"id": employee_id, "org_id": ORG, "email": "employee@hotel.in", "full_name": "Asha Rao",
            "phone": "+919999999999", "role": "employee", "department_id": DEPARTMENT,
            "active_property_id": PROPERTY, "employee_code": "EMP-1", "job_title": "Front Desk Agent",
            "employment_type": "FULL_TIME", "employment_status": "ACTIVE"}


def test_self_view_contains_permitted_sections_but_not_disciplinary():
    sb = MockSupabase().configure("users", [employee_row()])
    sb.configure("candidates", [{"id": "c1", "user_id": EMPLOYEE, "preferred_language": "hi"}])
    sb.configure("properties", [{"id": PROPERTY, "name": "Hotel India"}])
    sb.configure("property_departments", [{"id": DEPARTMENT, "name": "Front Office"}])
    result = get_employee_360(sb, context(), EMPLOYEE)
    assert result["self_view"] is True
    assert "payroll" in result["visible_sections"]
    assert "statutory" in result["visible_sections"]
    assert "disciplinary" not in result["visible_sections"]
    assert "disciplinary" not in result["sections"]


def test_employee_cannot_read_another_employee():
    sb = MockSupabase().configure("users", [employee_row(OTHER)])
    with pytest.raises(HTTPException) as exc:
        get_employee_360(sb, context(), OTHER)
    assert exc.value.status_code == 403


def test_department_head_cannot_cross_property_scope():
    sb = MockSupabase().configure("users", [employee_row(OTHER)])
    with pytest.raises(HTTPException) as exc:
        get_employee_360(sb, context(user_id="manager", role="DEPARTMENT_HEAD",
                                     properties=(), departments=(DEPARTMENT,)), OTHER)
    assert exc.value.status_code == 404


def test_statutory_values_are_always_masked():
    result = redact_statutory({"epf_uan": "100200300400", "epf_member_id": "MH12345678",
                               "esic_ip_number": "1234567890", "status": "ACTIVE"})
    assert result["epf_uan_masked"].endswith("0400")
    assert "100200300400" not in str(result)
    assert "1234567890" not in str(result)


def test_manager_upi_is_masked_and_bank_fields_never_returned():
    result = redact_upi({"upi_id": "asha.rao@okaxis", "bank_account_number": "1234567890",
                         "ifsc_code": "HDFC0001", "is_verified": True}, self_view=False)
    assert result["upi_id"] == "as***@okaxis"
    assert "bank_account_number" not in result
    assert "ifsc_code" not in result
