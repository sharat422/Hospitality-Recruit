"""
Razorpay UPI Payout Service — Python / FastAPI backend.

Mirrors services/razorpayPayout.service.js so Python routes can initiate
payouts without calling out to a Node subprocess.

Security
--------
  Razorpay credentials are read from settings at call-site.
  This module never returns raw credentials to any caller.

Razorpay payout statuses → internal status:
  queued | pending | processing  → "PROCESSING"
  processed                      → "PAID"
  failed | reversed | cancelled  → "FAILED"
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

RAZORPAY_BASE = "https://api.razorpay.com/v1"

PAYOUT_STATUS_MAP: dict[str, str] = {
    "queued":     "PROCESSING",
    "pending":    "PROCESSING",
    "processing": "PROCESSING",
    "processed":  "PAID",
    "failed":     "FAILED",
    "reversed":   "FAILED",
    "cancelled":  "FAILED",
}


class RazorpayPayoutService:
    """
    Async Razorpay Payouts API client.

    Usage::

        svc = RazorpayPayoutService(
            key_id="rzp_live_xxx",
            key_secret="yyy",
            account_number="7894561230000012",
        )
        result = await svc.process_referral_payout(
            referral_id="uuid", upi_id="emp@okaxis", amount_inr=5000
        )
    """

    def __init__(self, key_id: str, key_secret: str, account_number: str) -> None:
        self.account_number = account_number
        # Encode once at construction — raw credentials are never stored as
        # instance attributes so they cannot be accidentally serialised or logged.
        _encoded = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
        self._auth_header = f"Basic {_encoded}"

    # ── Utilities ──────────────────────────────────────────────────────────────

    @staticmethod
    def inr_to_paise(inr: float) -> int:
        """Convert INR to integer paise.  1 INR = 100 paise."""
        if inr < 0 or not isinstance(inr, (int, float)):
            raise ValueError(f"inr_to_paise: invalid amount {inr!r}")
        return round(inr * 100)

    @staticmethod
    def map_status(razorpay_status: str) -> str:
        """Map a Razorpay payout status to an internal status string."""
        return PAYOUT_STATUS_MAP.get(razorpay_status, "UNKNOWN")

    # ── Low-level HTTP helpers ─────────────────────────────────────────────────

    async def _post(self, path: str, payload: dict, extra_headers: Optional[dict] = None) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Authorization": self._auth_header,
        }
        if extra_headers:
            headers.update(extra_headers)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{RAZORPAY_BASE}{path}", json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def _get(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{RAZORPAY_BASE}{path}",
                headers={"Authorization": self._auth_header},
            )
            resp.raise_for_status()
            return resp.json()

    # ── Razorpay API wrappers ──────────────────────────────────────────────────

    async def create_contact(
        self,
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        reference_id: Optional[str] = None,
    ) -> dict:
        """Create a Razorpay Contact for the employee (once per employee)."""
        payload: dict = {"name": name or "Employee", "type": "employee"}
        if email:        payload["email"]        = email
        if phone:        payload["contact"]      = phone
        if reference_id: payload["reference_id"] = reference_id
        return await self._post("/contacts", payload)

    async def create_fund_account(self, contact_id: str, upi_id: str) -> dict:
        """Create a UPI VPA fund account linked to a Contact."""
        return await self._post("/fund_accounts", {
            "contact_id":   contact_id,
            "account_type": "vpa",
            "vpa":          {"address": upi_id},
        })

    async def create_payout(
        self,
        fund_account_id: str,
        amount_inr: float,
        reference_id: str,
        notes: Optional[dict] = None,
    ) -> dict:
        """
        Create the payout.
        X-Payout-Idempotency is set to reference_id so retries are safe.
        """
        amount_paise = self.inr_to_paise(amount_inr)
        return await self._post(
            "/payouts",
            {
                "account_number":       self.account_number,
                "fund_account_id":      fund_account_id,
                "amount":               amount_paise,
                "currency":             "INR",
                "mode":                 "UPI",
                "purpose":              "payout",
                "queue_if_low_balance": True,
                "reference_id":         reference_id,
                "narration":            "HospRecruit referral bonus",
                "notes":                notes or {},
            },
            extra_headers={"X-Payout-Idempotency": reference_id},
        )

    async def fetch_payout(self, payout_id: str) -> dict:
        """Fetch payout details by Razorpay payout ID. Use to poll or refresh."""
        return await self._get(f"/payouts/{payout_id}")

    # ── High-level orchestration ───────────────────────────────────────────────

    async def process_referral_payout(
        self,
        referral_id: str,
        upi_id: str,
        amount_inr: float,
        employee_name: str = "Employee",
        employee_email: Optional[str] = None,
        existing_fund_account_id: Optional[str] = None,
    ) -> dict:
        """
        End-to-end referral bonus payout.

        Pass existing_fund_account_id to reuse a previously created fund account
        (avoids the Contact + FundAccount creation steps on subsequent payouts).

        Returns a dict with:
          payout_id, status, internal_status, amount_paise,
          fund_account_id, mock=False, raw
        """
        fund_account_id = existing_fund_account_id

        if not fund_account_id:
            contact = await self.create_contact(
                name=employee_name,
                email=employee_email,
                reference_id=f"emp-{referral_id}",
            )
            fa = await self.create_fund_account(contact["id"], upi_id)
            fund_account_id = fa["id"]

        payout = await self.create_payout(
            fund_account_id=fund_account_id,
            amount_inr=amount_inr,
            reference_id=referral_id,
            notes={"referral_id": referral_id, "upi_id": upi_id},
        )

        return {
            "payout_id":       payout["id"],
            "status":          payout["status"],
            "internal_status": self.map_status(payout["status"]),
            "amount_paise":    payout["amount"],
            "fund_account_id": fund_account_id,
            "mock":            False,
            "raw":             payout,
        }

    @staticmethod
    def parse_webhook_payload(payload: dict) -> dict:
        """
        Parse a Razorpay payout webhook payload (call after HMAC verification).

        Returns:
          { payout_id, internal_status, referral_id, amount_paise, raw_status }
        """
        entity = (payload.get("payload") or {}).get("payout", {}).get("entity")
        if not entity or not entity.get("id"):
            raise ValueError("Invalid Razorpay webhook payload: missing payout entity")
        return {
            "payout_id":       entity["id"],
            "internal_status": PAYOUT_STATUS_MAP.get(entity["status"], "UNKNOWN"),
            "referral_id":     (entity.get("notes") or {}).get("referral_id"),
            "amount_paise":    entity["amount"],
            "raw_status":      entity["status"],
        }


# ── Factory ────────────────────────────────────────────────────────────────────

def create_razorpay_payout_service(
    key_id: Optional[str],
    key_secret: Optional[str],
    account_number: Optional[str],
) -> Optional[RazorpayPayoutService]:
    """
    Build a service instance from settings.
    Returns None when any credential is missing (caller should use mock mode).
    Credentials are never returned or logged.
    """
    if not key_id or not key_secret or not account_number:
        logger.warning(
            "Razorpay payout credentials not configured — running in mock mode. "
            "Set RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_FUND_ACCOUNT."
        )
        return None
    return RazorpayPayoutService(key_id, key_secret, account_number)


def mock_payout_result(referral_id: str, amount_inr: float) -> dict:
    """Return a deterministic mock result for local / staging environments."""
    payout_id = f"MOCK-{referral_id[:8].upper()}"
    return {
        "payout_id":       payout_id,
        "status":          "processed",
        "internal_status": "PAID",
        "amount_paise":    RazorpayPayoutService.inr_to_paise(amount_inr),
        "fund_account_id": "fa_MOCK",
        "mock":            True,
        "raw":             {"id": payout_id, "status": "processed", "amount": RazorpayPayoutService.inr_to_paise(amount_inr)},
    }
