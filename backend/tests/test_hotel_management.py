"""Hotel and multi-property management API tests."""

from tests.conftest import ADMIN_ID, EMPLOYEE_ID


BASE = "/api/v1/hotels"
ORG_ID = "11111111-1111-1111-1111-111111111111"
PROPERTY_A = "22222222-2222-2222-2222-222222222222"
PROPERTY_B = "33333333-3333-3333-3333-333333333333"
OTHER_PROPERTY = "44444444-4444-4444-4444-444444444444"

ADMIN = [{"id": ADMIN_ID, "org_id": ORG_ID, "role": "admin", "active_property_id": PROPERTY_A}]
EMPLOYEE = [{"id": EMPLOYEE_ID, "org_id": ORG_ID, "role": "hiring_manager", "active_property_id": PROPERTY_A}]
PROP_A = [{"id": PROPERTY_A, "org_id": ORG_ID, "name": "Mumbai Grand", "type": "HOTEL", "is_active": True}]
PROP_B = [{"id": PROPERTY_B, "org_id": ORG_ID, "name": "Goa Resort", "type": "RESORT", "is_active": True}]


def test_group_profile_is_tenant_scoped(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", ADMIN)
    sb.configure("organizations", [{"id": ORG_ID, "name": "Acme Hotels"}])
    response = client.get(f"{BASE}/group")
    assert response.status_code == 200
    assert response.json()["group"]["id"] == ORG_ID
    assert response.json()["can_manage"] is True


def test_non_admin_cannot_update_group(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", EMPLOYEE)
    response = client.patch(f"{BASE}/group", json={"name": "Changed Group"})
    assert response.status_code == 403


def test_admin_lists_all_properties_in_organization(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", ADMIN)
    sb.configure("properties", PROP_A + PROP_B)
    response = client.get(f"{BASE}/properties")
    assert response.status_code == 200
    assert {row["id"] for row in response.json()["properties"]} == {PROPERTY_A, PROPERTY_B}


def test_property_user_only_sees_assigned_property(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", EMPLOYEE)
    sb.configure("properties", PROP_A + PROP_B)
    sb.configure("property_memberships", [{"property_id": PROPERTY_A, "role": "PROPERTY_RECRUITER", "is_default": True}])
    response = client.get(f"{BASE}/properties")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["properties"]] == [PROPERTY_A]


def test_cross_tenant_property_is_not_disclosed(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", EMPLOYEE)
    # The org-scoped property query returns no row for another tenant.
    sb.configure("properties", [])
    response = client.get(f"{BASE}/properties/{OTHER_PROPERTY}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Property not found."


def test_switch_property_requires_membership(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", EMPLOYEE)
    sb.configure("properties", PROP_B)
    sb.configure("property_memberships", [])
    response = client.post(f"{BASE}/properties/{PROPERTY_B}/switch")
    assert response.status_code == 403


def test_switch_property_persists_authorized_selection(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", EMPLOYEE, [{"id": EMPLOYEE_ID, "active_property_id": PROPERTY_B}])
    sb.configure("properties", PROP_B)
    sb.configure("property_memberships", [{"property_id": PROPERTY_B, "user_id": EMPLOYEE_ID, "role": "PROPERTY_RECRUITER"}])
    response = client.post(f"{BASE}/properties/{PROPERTY_B}/switch")
    assert response.status_code == 200
    assert response.json()["active_property_id"] == PROPERTY_B


def test_admin_creates_property_and_membership(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", ADMIN)
    sb.configure("properties", PROP_B)
    sb.configure("property_memberships", [{"id": "membership-1"}])
    response = client.post(f"{BASE}/properties", json={
        "name": "Goa Resort", "code": "GOA01", "type": "RESORT",
        "city": "Panaji", "state": "Goa", "star_rating": 5,
    })
    assert response.status_code == 201
    assert response.json()["property"]["id"] == PROPERTY_B


def test_property_recruiter_cannot_change_settings(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", EMPLOYEE)
    sb.configure("properties", PROP_A)
    sb.configure("property_memberships", [{"property_id": PROPERTY_A, "role": "PROPERTY_RECRUITER"}])
    response = client.patch(f"{BASE}/properties/{PROPERTY_A}/settings/payroll", json={"settings": {"pay_cycle": "MONTHLY"}})
    assert response.status_code == 403


def test_property_manager_can_create_department(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", EMPLOYEE)
    sb.configure("properties", PROP_A)
    sb.configure("property_memberships", [{"property_id": PROPERTY_A, "role": "PROPERTY_HR"}])
    sb.configure("property_departments", [{
        "id": "dept-1", "property_id": PROPERTY_A, "org_id": ORG_ID,
        "code": "FNB", "name": "Food & Beverage", "budgeted_headcount": 30,
    }])
    response = client.post(f"{BASE}/properties/{PROPERTY_A}/departments", json={
        "code": "fnb", "name": "Food & Beverage", "budgeted_headcount": 30,
    })
    assert response.status_code == 201
    assert response.json()["department"]["name"] == "Food & Beverage"


def test_group_report_is_admin_only(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", EMPLOYEE)
    response = client.get(f"{BASE}/reports/group")
    assert response.status_code == 403


def test_group_report_aggregates_each_property(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", ADMIN)
    sb.configure("properties", PROP_A + PROP_B)
    sb.configure("property_departments", [
        {"property_id": PROPERTY_A, "budgeted_headcount": 20, "current_headcount": 15},
        {"property_id": PROPERTY_B, "budgeted_headcount": 30, "current_headcount": 28},
    ])
    sb.configure("jobs", [
        {"id": "job-a", "property_id": PROPERTY_A, "status": "open", "openings_count": 3},
        {"id": "job-b", "property_id": PROPERTY_B, "status": "closed", "openings_count": 1},
    ])
    sb.configure("hiring_campaigns", [])
    response = client.get(f"{BASE}/reports/group")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["property_count"] == 2
    assert data["summary"]["budgeted_headcount"] == 50
    assert data["properties"][0]["open_positions"] == 3
