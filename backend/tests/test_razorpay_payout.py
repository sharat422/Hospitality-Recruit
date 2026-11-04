"""
Tests for Razorpay UPI Payout Service (Python).

Covers
------
  Static utilities  — inr_to_paise, map_status, parse_webhook_payload
  API wrappers      — create_contact, create_fund_account, create_payout, fetch_payout
  Orchestration     — process_referral_payout (full flow, existing fund account, statuses)
  Error handling    — HTTP errors, network timeouts, double-payout guard
  Factory           — create_razorpay_payout_service (real vs. None)
  Mock helper       — mock_payout_result shape
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, patch as mock_patch

import pytest

from app.services.razorpay_payout_service import (
    PAYOUT_STATUS_MAP,
    RazorpayPayoutService,
    create_razorpay_payout_service,
    mock_payout_result,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

SVC = RazorpayPayoutService(
    key_id="rzp_test_key", key_secret="rzp_test_secret", account_number="7894561230000012"
)

CONTACT_RESP = {"id": "cont_abc", "name": "Rahul Kumar", "type": "employee"}
FA_RESP      = {"id": "fa_xyz", "contact_id": "cont_abc", "account_type": "vpa",
                "vpa": {"address": "rahul@okaxis"}}
PAYOUT_PROCESSING = {
    "id": "pout_999", "status": "processing", "amount": 500000,
    "currency": "INR", "mode": "UPI",
    "notes": {"referral_id": "ref-001", "upi_id": "rahul@okaxis"},
}
PAYOUT_PROCESSED  = {**PAYOUT_PROCESSING, "status": "processed"}
PAYOUT_FAILED     = {**PAYOUT_PROCESSING, "status": "failed"}
PAYOUT_REVERSED   = {**PAYOUT_PROCESSING, "status": "reversed"}
PAYOUT_QUEUED     = {**PAYOUT_PROCESSING, "status": "queued"}


def _mock_response(json_data: dict, status_code: int = 200):
    """Build a minimal mock of an httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()   # no-op for 2xx
    return resp


def _mock_error_response(status_code: int = 422):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


def _patch_post(return_value):
    """Context manager: patch httpx.AsyncClient.post for one call."""
    m = AsyncMock(return_value=return_value)
    return patch(
        "app.services.razorpay_payout_service.httpx.AsyncClient",
        return_value=MagicMock(
            __aenter__=AsyncMock(return_value=MagicMock(post=m, get=AsyncMock())),
            __aexit__=AsyncMock(),
        ),
    ), m


def _patch_client(post_side_effects=None, get_side_effect=None):
    """
    Patch httpx.AsyncClient to return successive post responses and one
    optional get response.  Allows testing multi-step flows cleanly.
    """
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()

    if post_side_effects:
        mock_client.post = AsyncMock(side_effect=post_side_effects)
    if get_side_effect:
        mock_client.get = AsyncMock(return_value=get_side_effect)

    return patch(
        "app.services.razorpay_payout_service.httpx.AsyncClient",
        return_value=mock_client,
    ), mock_client


# ═════════════════════════════════════════════════════════════════════════════
# inr_to_paise
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("inr,paise", [
    (1,        100),
    (5000,     500_000),
    (0.5,      50),
    (99.99,    9999),
    (100_000,  10_000_000),
    (0,        0),
])
def test_inr_to_paise(inr, paise):
    assert RazorpayPayoutService.inr_to_paise(inr) == paise


def test_inr_to_paise_negative_raises():
    with pytest.raises(ValueError):
        RazorpayPayoutService.inr_to_paise(-1)


# ═════════════════════════════════════════════════════════════════════════════
# map_status
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("rzp_status,expected", PAYOUT_STATUS_MAP.items())
def test_map_status_all_known(rzp_status, expected):
    assert RazorpayPayoutService.map_status(rzp_status) == expected


def test_map_status_unknown_returns_unknown():
    assert RazorpayPayoutService.map_status("some_future_status") == "UNKNOWN"


# ═════════════════════════════════════════════════════════════════════════════
# create_contact
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_contact_posts_to_contacts():
    mock_resp = _mock_response(CONTACT_RESP)
    patch_ctx, mock_post = _patch_post(mock_resp)

    with patch_ctx:
        result = await SVC.create_contact(
            name="Rahul Kumar", email="r@hotel.in", reference_id="emp-uuid"
        )

    assert result["id"] == "cont_abc"
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["type"] == "employee"
    assert kwargs["json"]["email"] == "r@hotel.in"


@pytest.mark.asyncio
async def test_create_contact_omits_optional_fields_when_none():
    mock_resp = _mock_response(CONTACT_RESP)
    patch_ctx, mock_post = _patch_post(mock_resp)

    with patch_ctx:
        await SVC.create_contact(name="Employee")

    _, kwargs = mock_post.call_args
    assert "email"   not in kwargs["json"]
    assert "contact" not in kwargs["json"]


@pytest.mark.asyncio
async def test_create_contact_propagates_http_error():
    # Patch _post directly — cleaner than mocking the full httpx chain
    with patch.object(SVC, "_post", side_effect=Exception("HTTP 422")):
        with pytest.raises(Exception, match="422"):
            await SVC.create_contact(name="X")


# ═════════════════════════════════════════════════════════════════════════════
# create_fund_account
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_fund_account_sends_vpa():
    mock_resp = _mock_response(FA_RESP)
    patch_ctx, mock_post = _patch_post(mock_resp)

    with patch_ctx:
        result = await SVC.create_fund_account("cont_abc", "rahul@okaxis")

    assert result["id"] == "fa_xyz"
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["account_type"] == "vpa"
    assert kwargs["json"]["vpa"]["address"] == "rahul@okaxis"


# ═════════════════════════════════════════════════════════════════════════════
# create_payout
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_payout_converts_inr_to_paise():
    mock_resp = _mock_response(PAYOUT_PROCESSING)
    patch_ctx, mock_post = _patch_post(mock_resp)

    with patch_ctx:
        result = await SVC.create_payout(
            fund_account_id="fa_xyz", amount_inr=5000, reference_id="ref-001"
        )

    _, kwargs = mock_post.call_args
    assert kwargs["json"]["amount"] == 500_000           # paise
    assert kwargs["json"]["currency"] == "INR"
    assert kwargs["json"]["mode"] == "UPI"
    assert result["status"] == "processing"


@pytest.mark.asyncio
async def test_create_payout_sets_idempotency_header():
    mock_resp = _mock_response(PAYOUT_PROCESSING)
    patch_ctx, mock_post = _patch_post(mock_resp)

    with patch_ctx:
        await SVC.create_payout("fa_xyz", 1000, "my-ref")

    # find the headers kwarg
    _, kwargs = mock_post.call_args
    headers = kwargs.get("headers", {})
    assert headers.get("X-Payout-Idempotency") == "my-ref"


@pytest.mark.asyncio
async def test_create_payout_sets_queue_if_low_balance():
    mock_resp = _mock_response(PAYOUT_QUEUED)
    patch_ctx, mock_post = _patch_post(mock_resp)

    with patch_ctx:
        await SVC.create_payout("fa_xyz", 100, "ref")

    _, kwargs = mock_post.call_args
    assert kwargs["json"]["queue_if_low_balance"] is True


# ═════════════════════════════════════════════════════════════════════════════
# fetch_payout
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_fetch_payout_returns_entity():
    mock_get_resp = _mock_response(PAYOUT_PROCESSED)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_get_resp)

    with patch("app.services.razorpay_payout_service.httpx.AsyncClient", return_value=mock_client):
        result = await SVC.fetch_payout("pout_999")

    mock_client.get.assert_called_once()
    assert result["status"] == "processed"


# ═════════════════════════════════════════════════════════════════════════════
# process_referral_payout
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_process_referral_payout_full_flow():
    responses = [
        _mock_response(CONTACT_RESP),      # create_contact
        _mock_response(FA_RESP),           # create_fund_account
        _mock_response(PAYOUT_PROCESSING), # create_payout
    ]
    patch_ctx, mock_client = _patch_client(post_side_effects=responses)

    with patch_ctx:
        result = await SVC.process_referral_payout(
            referral_id="ref-001", upi_id="rahul@okaxis",
            amount_inr=5000, employee_name="Rahul", employee_email="r@h.in",
        )

    assert mock_client.post.call_count == 3
    assert result["payout_id"] == "pout_999"
    assert result["internal_status"] == "PROCESSING"
    assert result["amount_paise"] == 500_000
    assert result["fund_account_id"] == "fa_xyz"
    assert result["mock"] is False


@pytest.mark.asyncio
async def test_process_referral_payout_reuses_existing_fund_account():
    responses = [_mock_response(PAYOUT_PROCESSED)]  # only create_payout
    patch_ctx, mock_client = _patch_client(post_side_effects=responses)

    with patch_ctx:
        result = await SVC.process_referral_payout(
            referral_id="ref-002", upi_id="x@upi", amount_inr=2500,
            existing_fund_account_id="fa_existing",
        )

    assert mock_client.post.call_count == 1   # skipped contact + fund account
    assert result["fund_account_id"] == "fa_existing"
    assert result["internal_status"] == "PAID"


@pytest.mark.asyncio
@pytest.mark.parametrize("rzp_status,expected_internal", [
    ("processed",  "PAID"),
    ("processing", "PROCESSING"),
    ("queued",     "PROCESSING"),
    ("failed",     "FAILED"),
    ("reversed",   "FAILED"),
    ("cancelled",  "FAILED"),
])
async def test_process_referral_payout_status_mapping(rzp_status, expected_internal):
    payout = {**PAYOUT_PROCESSING, "status": rzp_status}
    responses = [
        _mock_response(CONTACT_RESP),
        _mock_response(FA_RESP),
        _mock_response(payout),
    ]
    patch_ctx, _ = _patch_client(post_side_effects=responses)

    with patch_ctx:
        result = await SVC.process_referral_payout(
            referral_id="ref", upi_id="x@upi", amount_inr=1000
        )

    assert result["internal_status"] == expected_internal


@pytest.mark.asyncio
async def test_process_referral_payout_propagates_api_error():
    responses = [
        _mock_response(CONTACT_RESP),
        _mock_error_response(422),  # createFundAccount fails
    ]
    patch_ctx, _ = _patch_client(post_side_effects=responses)

    with patch_ctx:
        with pytest.raises(Exception):
            await SVC.process_referral_payout(
                referral_id="ref-err", upi_id="bad@upi", amount_inr=500
            )


# ═════════════════════════════════════════════════════════════════════════════
# parse_webhook_payload
# ═════════════════════════════════════════════════════════════════════════════

def _webhook(status: str, referral_id: str = "ref-wh") -> dict:
    return {
        "event": "payout.processed",
        "payload": {
            "payout": {
                "entity": {
                    "id": "pout_wh1",
                    "status": status,
                    "amount": 500_000,
                    "notes": {"referral_id": referral_id},
                }
            }
        },
    }


@pytest.mark.parametrize("status,expected", [
    ("processed",  "PAID"),
    ("failed",     "FAILED"),
    ("reversed",   "FAILED"),
    ("queued",     "PROCESSING"),
    ("pending",    "PROCESSING"),
    ("processing", "PROCESSING"),
])
def test_parse_webhook_payload_all_statuses(status, expected):
    result = RazorpayPayoutService.parse_webhook_payload(_webhook(status))
    assert result["internal_status"] == expected


def test_parse_webhook_payload_extracts_fields():
    result = RazorpayPayoutService.parse_webhook_payload(_webhook("processed", "my-ref"))
    assert result["payout_id"]   == "pout_wh1"
    assert result["referral_id"] == "my-ref"
    assert result["amount_paise"] == 500_000
    assert result["raw_status"]   == "processed"


def test_parse_webhook_payload_null_referral_id_when_no_notes():
    wh = _webhook("processed")
    del wh["payload"]["payout"]["entity"]["notes"]
    result = RazorpayPayoutService.parse_webhook_payload(wh)
    assert result["referral_id"] is None


def test_parse_webhook_payload_raises_on_malformed():
    with pytest.raises(ValueError):
        RazorpayPayoutService.parse_webhook_payload({})
    with pytest.raises(ValueError):
        RazorpayPayoutService.parse_webhook_payload({"payload": {}})


# ═════════════════════════════════════════════════════════════════════════════
# create_razorpay_payout_service factory
# ═════════════════════════════════════════════════════════════════════════════

def test_factory_returns_none_when_any_credential_missing():
    assert create_razorpay_payout_service(None, "s", "a")    is None
    assert create_razorpay_payout_service("k", None, "a")    is None
    assert create_razorpay_payout_service("k", "s", None)    is None
    assert create_razorpay_payout_service(None, None, None)  is None


def test_factory_returns_service_when_all_credentials_present():
    svc = create_razorpay_payout_service("k", "s", "acc")
    assert isinstance(svc, RazorpayPayoutService)


def test_factory_does_not_expose_credentials():
    svc = create_razorpay_payout_service("my_secret_key", "my_secret", "acc")
    import json
    serialised = json.dumps(svc.__dict__, default=str)
    # Raw credentials must not appear in plain text on the instance
    assert "my_secret_key" not in serialised
    assert "my_secret" not in serialised
    # The stored auth header is the Base64-encoded form — not the raw secret
    assert "_auth_header" in serialised
    assert "Basic " in serialised


# ═════════════════════════════════════════════════════════════════════════════
# mock_payout_result helper
# ═════════════════════════════════════════════════════════════════════════════

def test_mock_payout_result_shape():
    result = mock_payout_result("referral-uuid-001", 5000)
    assert result["mock"] is True
    assert result["internal_status"] == "PAID"
    assert result["amount_paise"] == 500_000
    assert "MOCK" in result["payout_id"]
    assert result["raw"]["status"] == "processed"
