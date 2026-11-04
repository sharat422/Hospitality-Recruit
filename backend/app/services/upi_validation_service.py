"""
UPI ID validation service.
Validates format with regex then optionally confirms VPA existence
via the Razorpay Validate VPA API.
"""

import re
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# UPI VPA regex per NPCI spec:
# handle part  : one or more alphanumeric / dot / underscore / hyphen chars
# separator    : literal @
# bank handle  : one or more alpha-only chars  (e.g. okaxis, ybl, paytm, upi)
UPI_REGEX = re.compile(r"^[a-zA-Z0-9._-]+@[a-zA-Z]+$")

RAZORPAY_VPA_URL = "https://api.razorpay.com/v1/payments/validate/vpa"
# Razorpay sandbox returns {"success": true, "vpa": "...", "customer_name": "..."}
# on success and {"success": false, "error": {...}} on invalid VPA.


def validate_upi_format(upi_id: str) -> bool:
    """Return True if upi_id matches the UPI regex, False otherwise."""
    return bool(UPI_REGEX.fullmatch(upi_id.strip()))


async def validate_vpa_razorpay(
    upi_id: str,
    key_id: Optional[str] = None,
    key_secret: Optional[str] = None,
) -> dict:
    """
    Validate a UPI VPA.

    Flow:
      1. Regex check — fast fail for obviously wrong formats.
      2. If Razorpay credentials are configured, call the Validate VPA API
         and treat only an API-confirmed "success: true" as verified.
      3. If credentials are absent or the API is unreachable, accept the
         format-validated ID as REGEX_ONLY (unverified but not rejected).

    Returns a dict with keys:
      valid (bool), method (str), upi_id (str | None), error (str | None)
    """
    upi_id = upi_id.strip()

    if not validate_upi_format(upi_id):
        return {
            "valid": False,
            "method": "REGEX",
            "upi_id": upi_id,
            "error": (
                "Invalid UPI ID format. "
                "Expected <username>@<bankhandle>  (e.g. john@okaxis, 9999@ybl)."
            ),
        }

    if not key_id or not key_secret:
        return {
            "valid": True,
            "method": "REGEX_ONLY",
            "upi_id": upi_id,
            "note": (
                "Razorpay credentials not configured — "
                "UPI ID accepted on format validation only."
            ),
        }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                RAZORPAY_VPA_URL,
                json={"vpa": upi_id},
                auth=(key_id, key_secret),
            )

        if resp.status_code == 200:
            data = resp.json()
            is_valid = bool(data.get("success"))
            result = {
                "valid": is_valid,
                "method": "RAZORPAY_VPA",
                "upi_id": upi_id,
                "razorpay_response": data,
            }
            if not is_valid:
                err = data.get("error", {})
                result["error"] = err.get("description") or "Razorpay rejected this VPA."
            return result

        # Non-200 from Razorpay — don't block, fall back gracefully
        logger.warning(
            "Razorpay VPA API returned %s for %s — falling back to REGEX_ONLY",
            resp.status_code, upi_id,
        )
        return {
            "valid": True,
            "method": "REGEX_ONLY",
            "upi_id": upi_id,
            "note": f"Razorpay returned HTTP {resp.status_code} — format accepted.",
        }

    except httpx.TimeoutException:
        logger.warning("Razorpay VPA validation timed out for %s", upi_id)
        return {
            "valid": True,
            "method": "REGEX_ONLY",
            "upi_id": upi_id,
            "note": "Razorpay timed out — format accepted.",
        }
    except Exception as exc:
        logger.warning("Razorpay VPA call failed for %s: %s", upi_id, exc)
        return {
            "valid": True,
            "method": "REGEX_ONLY",
            "upi_id": upi_id,
            "note": f"Razorpay unavailable ({exc}) — format accepted.",
        }
