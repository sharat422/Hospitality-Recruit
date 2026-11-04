"""
Tests for UPI ID collection.

Covers:
  Service layer  — validate_upi_format, validate_vpa_razorpay
  GET  /api/v1/employees/{id}/upi
  POST /api/v1/employees/{id}/upi
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.upi_validation_service import validate_upi_format, validate_vpa_razorpay
from tests.conftest import EMPLOYEE_ID, ADMIN_ID, OTHER_ID

BASE = f"/api/v1/employees/{EMPLOYEE_ID}/upi"

# Rows reused across tests
_EMPLOYEE_ROW = [{"id": EMPLOYEE_ID, "email": "emp@hotel.in", "role": "hiring_manager"}]
_ADMIN_ROW    = [{"id": ADMIN_ID,    "email": "admin@hotel.in", "role": "admin"}]
_OTHER_ROW    = [{"id": OTHER_ID,    "email": "other@hotel.in", "role": "hiring_manager"}]
_UPI_ROW      = [{"id": "upi-row-1", "user_id": EMPLOYEE_ID, "upi_id": "emp@okaxis",
                   "is_verified": False, "verification_method": "REGEX_ONLY",
                   "bank_account_number": "123456789012"}]
_SAVED_ROW    = [{"id": "upi-row-1", "user_id": EMPLOYEE_ID, "upi_id": "new@ybl",
                   "is_verified": False, "verification_method": "REGEX_ONLY",
                   "bank_account_number": None}]


# ===========================================================================
# Service — validate_upi_format
# ===========================================================================

@pytest.mark.parametrize("upi_id", [
    "john@okaxis",
    "john.doe@upi",
    "john_doe@paytm",
    "john-doe@ybl",
    "9999999999@upi",
    "a@b",
    "A.B_C-D@BANKHANDLE",
])
def test_valid_upi_format(upi_id):
    assert validate_upi_format(upi_id) is True


@pytest.mark.parametrize("upi_id", [
    "john@",                 # empty bank handle
    "@okaxis",               # empty username
    "john@ok axis",          # space in handle
    "john@okaxis123",        # digits in handle
    "john@ok.axis",          # dot in handle
    "john @okaxis",          # space in username
    "john",                  # no @ at all
    "",                      # empty string
    "john@@okaxis",          # double @
    "john@ok@axis",          # two @
])
def test_invalid_upi_format(upi_id):
    assert validate_upi_format(upi_id) is False


# ===========================================================================
# Service — validate_vpa_razorpay
# ===========================================================================

@pytest.mark.asyncio
async def test_vpa_invalid_format_returns_false():
    result = await validate_vpa_razorpay("not-a-upi")
    assert result["valid"] is False
    assert result["method"] == "REGEX"


@pytest.mark.asyncio
async def test_vpa_no_credentials_returns_regex_only():
    result = await validate_vpa_razorpay("john@okaxis", key_id=None, key_secret=None)
    assert result["valid"] is True
    assert result["method"] == "REGEX_ONLY"
    assert "note" in result


@pytest.mark.asyncio
async def test_vpa_razorpay_success():
    # Use MagicMock (not AsyncMock) — the response object itself is synchronous;
    # only the .post() call needs to be awaited.
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True, "vpa": "john@okaxis", "customer_name": "John"}

    with patch("app.services.upi_validation_service.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        result = await validate_vpa_razorpay("john@okaxis", key_id="rzp_id", key_secret="rzp_secret")

    assert result["valid"] is True
    assert result["method"] == "RAZORPAY_VPA"


@pytest.mark.asyncio
async def test_vpa_razorpay_rejects_vpa():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": False,
        "error": {"description": "The VPA is invalid."},
    }

    with patch("app.services.upi_validation_service.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        result = await validate_vpa_razorpay("bad@noexist", key_id="rzp_id", key_secret="rzp_secret")

    assert result["valid"] is False
    assert "invalid" in result["error"].lower()


@pytest.mark.asyncio
async def test_vpa_razorpay_timeout_falls_back():
    import httpx as _httpx

    with patch("app.services.upi_validation_service.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=_httpx.TimeoutException("timed out")
        )
        result = await validate_vpa_razorpay("john@okaxis", key_id="rzp_id", key_secret="rzp_secret")

    assert result["valid"] is True
    assert result["method"] == "REGEX_ONLY"


@pytest.mark.asyncio
async def test_vpa_razorpay_non200_falls_back():
    mock_resp = AsyncMock()
    mock_resp.status_code = 503
    mock_resp.text = "Service unavailable"

    with patch("app.services.upi_validation_service.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        result = await validate_vpa_razorpay("john@okaxis", key_id="rzp_id", key_secret="rzp_secret")

    assert result["valid"] is True
    assert result["method"] == "REGEX_ONLY"


# ===========================================================================
# GET /api/v1/employees/{id}/upi
# ===========================================================================

def test_get_upi_own_record_returns_data(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", _EMPLOYEE_ROW)          # _require_authorized role check (skipped — same user)
    sb.configure("users", _EMPLOYEE_ROW)          # _require_employee_exists
    sb.configure("employee_upi_details", _UPI_ROW)

    resp = client.get(BASE)

    assert resp.status_code == 200
    data = resp.json()
    assert data["upi_details"]["upi_id"] == "emp@okaxis"
    # Account number masked
    acct = data["upi_details"]["bank_account_number"]
    assert acct.startswith("****")
    assert acct.endswith("9012")


def test_get_upi_no_record_returns_null(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", _EMPLOYEE_ROW)
    sb.configure("employee_upi_details", [])

    resp = client.get(BASE)

    assert resp.status_code == 200
    assert resp.json()["upi_details"] is None


def test_get_upi_employee_not_found_returns_404(client_as_employee):
    client, sb = client_as_employee
    # _require_employee_exists returns empty → 404
    sb.configure("users", [])

    resp = client.get(BASE)

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_upi_other_employee_returns_403(client_as_other):
    client, sb = client_as_other
    # caller (OTHER_ID) is not EMPLOYEE_ID and not admin
    sb.configure("users", _OTHER_ROW)             # role lookup for caller

    resp = client.get(BASE)

    assert resp.status_code == 403
    assert "not authorized" in resp.json()["detail"].lower()


def test_get_upi_admin_can_access_any_employee(client_as_admin):
    client, sb = client_as_admin
    # Two successive .execute() calls on "users": first is the role lookup
    # for the admin caller, second is the employee-exists check.
    sb.configure("users", _ADMIN_ROW, _EMPLOYEE_ROW)
    sb.configure("employee_upi_details", _UPI_ROW)

    resp = client.get(BASE)

    assert resp.status_code == 200
    assert resp.json()["upi_details"]["upi_id"] == "emp@okaxis"


# ===========================================================================
# POST /api/v1/employees/{id}/upi
# ===========================================================================

def _post(client, upi_id: str):
    return client.post(BASE, json={"upi_id": upi_id})


def test_post_upi_invalid_format_returns_422(client_as_employee):
    client, sb = client_as_employee
    # Pydantic validation fires before any DB call
    resp = _post(client, "@badformat")

    assert resp.status_code == 422


def test_post_upi_other_employee_returns_403(client_as_other):
    client, sb = client_as_other
    sb.configure("users", _OTHER_ROW)  # role lookup → not admin

    resp = _post(client, "other@okaxis")

    assert resp.status_code == 403


def test_post_upi_employee_not_found_returns_404(client_as_employee):
    client, sb = client_as_employee
    # _require_employee_exists → empty
    sb.configure("users", [])

    resp = _post(client, "emp@okaxis")

    assert resp.status_code == 404


def test_post_upi_creates_new_record(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", _EMPLOYEE_ROW)                  # exists check
    sb.configure("employee_upi_details", [], _SAVED_ROW)  # select → no existing; insert → saved

    with patch(
        "app.routers.employees.validate_vpa_razorpay",
        new=AsyncMock(return_value={"valid": True, "method": "REGEX_ONLY", "upi_id": "new@ybl"}),
    ):
        resp = _post(client, "new@ybl")

    assert resp.status_code == 200
    body = resp.json()
    assert body["saved"] is True
    assert body["upi_id"] == "new@ybl"
    assert body["is_verified"] is False
    assert body["verification_method"] == "REGEX_ONLY"


def test_post_upi_updates_existing_record(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", _EMPLOYEE_ROW)
    # select → existing row found; update → returns updated row
    sb.configure("employee_upi_details",
                  [{"id": "upi-row-1"}],   # existing
                  _SAVED_ROW)              # after update

    with patch(
        "app.routers.employees.validate_vpa_razorpay",
        new=AsyncMock(return_value={"valid": True, "method": "REGEX_ONLY", "upi_id": "new@ybl"}),
    ):
        resp = _post(client, "new@ybl")

    assert resp.status_code == 200
    assert resp.json()["saved"] is True


def test_post_upi_razorpay_rejection_returns_422(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", _EMPLOYEE_ROW)

    with patch(
        "app.routers.employees.validate_vpa_razorpay",
        new=AsyncMock(return_value={
            "valid": False,
            "method": "RAZORPAY_VPA",
            "upi_id": "ghost@noexist",
            "error": "The VPA is invalid.",
        }),
    ):
        resp = _post(client, "ghost@noexist")

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["field"] == "upi_id"
    assert "invalid" in detail["message"].lower()


def test_post_upi_razorpay_verified_sets_flag(client_as_employee):
    client, sb = client_as_employee
    sb.configure("users", _EMPLOYEE_ROW)
    sb.configure("employee_upi_details", [], _SAVED_ROW)

    with patch(
        "app.routers.employees.validate_vpa_razorpay",
        new=AsyncMock(return_value={
            "valid": True,
            "method": "RAZORPAY_VPA",
            "upi_id": "john@okaxis",
        }),
    ):
        resp = _post(client, "john@okaxis")

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_verified"] is True
    assert body["verification_method"] == "RAZORPAY_VPA"


def test_post_upi_admin_can_set_any_employee(client_as_admin):
    client, sb = client_as_admin
    # role lookup → admin, then employee-exists check: two successive calls on "users"
    sb.configure("users", _ADMIN_ROW, _EMPLOYEE_ROW)
    sb.configure("employee_upi_details", [], _SAVED_ROW)

    with patch(
        "app.routers.employees.validate_vpa_razorpay",
        new=AsyncMock(return_value={"valid": True, "method": "REGEX_ONLY", "upi_id": "new@ybl"}),
    ):
        resp = _post(client, "new@ybl")

    assert resp.status_code == 200
    assert resp.json()["saved"] is True
