"""
India KYC Service — Surepass + DigiLocker integrations.

Providers:
  Aadhaar eKYC  → Surepass (https://kyc-api.surepass.io)
  PAN           → Surepass (same API key)
  DigiLocker    → NIC OAuth 2.0 (https://api.digitallocker.gov.in)

Security rules (hard-coded, not configuration):
  • Full Aadhaar number is NEVER stored anywhere — only last 4 digits.
  • PAN is stored in masked form only: ABCDE1234F → ABCDE****F
  • Sandbox mode (when SUREPASS_API_TOKEN is unset) returns deterministic
    mock data so the development stack works without real API keys.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SUREPASS_BASE = "https://kyc-api.surepass.io/api/v1"
DIGILOCKER_AUTH_BASE = "https://api.digitallocker.gov.in/public/oauth2/1/authorize"
DIGILOCKER_TOKEN_URL = "https://api.digitallocker.gov.in/public/oauth2/1/token"
DIGILOCKER_DOC_URL = "https://api.digitallocker.gov.in/public/oauth2/1/file/issued"

AADHAAR_RE = re.compile(r"^\d{12}$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


# ─────────────────────────────────────────────────────────────────────────────
# Masking helpers (pure, no I/O — safe to call anywhere)
# ─────────────────────────────────────────────────────────────────────────────

def mask_pan(pan: str) -> str:
    """
    ABCDE1234F → ABCDE****F
    First 5 chars + 4 stars + last char (always 10 total).
    """
    pan = pan.upper().strip()
    if not PAN_RE.match(pan):
        raise ValueError(f"Invalid PAN format: {pan!r}")
    return f"{pan[:5]}****{pan[-1]}"


def mask_aadhaar(aadhaar_digits: str) -> str:
    """
    123456789012 → XXXX XXXX 9012
    Accepts 12-digit string (spaces/dashes stripped first).
    """
    digits = re.sub(r"[\s\-]", "", aadhaar_digits)
    if len(digits) != 12 or not digits.isdigit():
        raise ValueError("Aadhaar must be exactly 12 digits")
    return f"XXXX XXXX {digits[-4:]}"


def extract_aadhaar_last4(aadhaar_digits: str) -> str:
    """Return last 4 digits of Aadhaar (the only part we store)."""
    digits = re.sub(r"[\s\-]", "", aadhaar_digits)
    if len(digits) != 12 or not digits.isdigit():
        raise ValueError("Aadhaar must be exactly 12 digits")
    return digits[-4:]


def validate_aadhaar_number(aadhaar: str) -> bool:
    """Validate 12-digit full Aadhaar format (server-side, pre-send to provider)."""
    digits = re.sub(r"[\s\-]", "", aadhaar or "")
    return bool(AADHAAR_RE.match(digits)) and digits[0] != "0"


# ─────────────────────────────────────────────────────────────────────────────
# Surepass client
# ─────────────────────────────────────────────────────────────────────────────

class SurepassClient:
    """
    Thin async HTTP client around the Surepass KYC API.
    Falls back to sandbox mode when SUREPASS_API_TOKEN is not set.
    """

    SANDBOX_REQUEST_ID = "sandbox-req-00000000"
    SANDBOX_PAN_NAME   = "SANDBOX USER"

    def __init__(self):
        self._token: Optional[str] = getattr(settings, "SUREPASS_API_TOKEN", None)
        self._sandbox = not bool(self._token)
        if self._sandbox:
            logger.warning(
                "KYC: SUREPASS_API_TOKEN not set — running in SANDBOX mode. "
                "All responses are mocked."
            )

    # ── Aadhaar OTP ──────────────────────────────────────────────────────────

    async def initiate_aadhaar_otp(self, aadhaar_number: str) -> dict:
        """
        Initiate Aadhaar eKYC OTP.
        Returns: {request_id, message, sandbox}
        IMPORTANT: aadhaar_number is used here but NEVER persisted.
        """
        if self._sandbox:
            return {
                "request_id": self.SANDBOX_REQUEST_ID,
                "message": "OTP sent to registered mobile (SANDBOX)",
                "sandbox": True,
            }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{SUREPASS_BASE}/aadhaar-v2/generate-otp",
                json={"id_number": aadhaar_number},
                headers={"Authorization": f"Bearer {self._token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            raise KYCProviderError(
                data.get("message", "OTP generation failed"),
                provider="SUREPASS",
                code=data.get("status_code"),
            )

        client_id = data["data"]["client_id"]
        return {
            "request_id": client_id,
            "message": data.get("message", "OTP sent successfully"),
            "sandbox": False,
        }

    async def verify_aadhaar_otp(self, request_id: str, otp: str) -> dict:
        """
        Verify Aadhaar OTP.
        Returns: {aadhaar_last4, aadhaar_masked, name, dob_year, gender,
                  address_state, sandbox}
        Full Aadhaar is extracted for masking then immediately discarded.
        """
        if self._sandbox:
            otp_ok = otp == "123456"
            if not otp_ok:
                raise KYCProviderError("Invalid OTP (sandbox: use 123456)", "SANDBOX")
            return {
                "aadhaar_last4":  "9012",
                "aadhaar_masked": "XXXX XXXX 9012",
                "name":           "Ravi Kumar (Sandbox)",
                "dob_year":       1992,
                "gender":         "M",
                "address_state":  "Maharashtra",
                "sandbox":        True,
            }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{SUREPASS_BASE}/aadhaar-v2/submit-otp",
                json={"client_id": request_id, "otp": otp},
                headers={"Authorization": f"Bearer {self._token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            raise KYCProviderError(
                data.get("message", "OTP verification failed"),
                provider="SUREPASS",
                code=data.get("status_code"),
            )

        uid_data = data["data"]
        # Extract Aadhaar last4 from the masked number returned by UIDAI
        # (Surepass returns e.g. "XXXX XXXX 9012" — we parse the last4)
        masked_str: str = uid_data.get("aadhaar_number", "XXXX XXXX 0000")
        last4 = masked_str.replace(" ", "")[-4:]

        dob_raw: str = uid_data.get("dob", "01-01-1990")
        try:
            dob_year = int(dob_raw.split("-")[-1])
        except (ValueError, IndexError):
            dob_year = None

        return {
            "aadhaar_last4":  last4,
            "aadhaar_masked": f"XXXX XXXX {last4}",
            "name":           uid_data.get("full_name", ""),
            "dob_year":       dob_year,
            "gender":         uid_data.get("gender", ""),
            "address_state":  uid_data.get("address", {}).get("state", ""),
            "sandbox":        False,
        }

    # ── PAN ──────────────────────────────────────────────────────────────────

    async def verify_pan(self, pan_number: str, name_to_match: Optional[str] = None) -> dict:
        """
        Verify PAN with Surepass.
        Returns: {pan_masked, name_on_pan, name_match, valid, sandbox}
        """
        pan_upper = pan_number.upper().strip()
        if self._sandbox:
            return {
                "pan_masked":   mask_pan(pan_upper),
                "name_on_pan":  self.SANDBOX_PAN_NAME,
                "name_match":   True,
                "valid":        True,
                "sandbox":      True,
            }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{SUREPASS_BASE}/pan",
                json={"id_number": pan_upper},
                headers={"Authorization": f"Bearer {self._token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            raise KYCProviderError(
                data.get("message", "PAN verification failed"),
                provider="SUREPASS",
                code=data.get("status_code"),
            )

        pan_data = data["data"]
        name_on_pan: str = pan_data.get("full_name", "")
        name_match = False
        if name_to_match and name_on_pan:
            # Normalise both strings: uppercase, collapse whitespace
            norm = lambda s: " ".join(s.upper().split())
            name_match = norm(name_on_pan) == norm(name_to_match)

        return {
            "pan_masked":  mask_pan(pan_upper),
            "name_on_pan": name_on_pan,
            "name_match":  name_match,
            "valid":       True,
            "sandbox":     False,
        }


# ─────────────────────────────────────────────────────────────────────────────
# DigiLocker OAuth service
# ─────────────────────────────────────────────────────────────────────────────

class DigiLockerService:
    """
    DigiLocker OAuth 2.0 integration (NIC / MeitY gateway).
    Placeholder implementation — real credentials required for production.

    Flow:
      1. get_auth_url()   → redirect user to DigiLocker consent screen
      2. exchange_code()  → swap auth code for access_token
      3. get_documents()  → list UIDAI-issued documents
    """

    def __init__(self):
        self._client_id: Optional[str] = getattr(settings, "DIGILOCKER_CLIENT_ID", None)
        self._client_secret: Optional[str] = getattr(settings, "DIGILOCKER_CLIENT_SECRET", None)
        _cfg_uri = getattr(settings, "DIGILOCKER_REDIRECT_URI", None)
        self._redirect_uri: str = _cfg_uri or f"{settings.APP_BASE_URL}/api/v1/kyc/digilocker/callback"
        self._sandbox = not (self._client_id and self._client_secret)

    def get_auth_url(self, state: str, code_challenge: Optional[str] = None) -> str:
        """
        Return the URL to redirect the user to DigiLocker.
        `state` should encode candidate_id + CSRF token (caller's responsibility).
        `code_challenge` for PKCE (recommended in production).
        """
        if self._sandbox:
            return (
                f"https://sandbox.digilocker.gov.in/oauth2/authorize"
                f"?client_id=sandbox&state={urllib.parse.quote(state)}"
                f"&redirect_uri={urllib.parse.quote(self._redirect_uri)}"
                f"&response_type=code&scope=files.issuedfiles.read"
            )

        params: dict = {
            "response_type": "code",
            "client_id":     self._client_id,
            "redirect_uri":  self._redirect_uri,
            "state":         state,
            "scope":         "files.issuedfiles.read",
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        return f"{DIGILOCKER_AUTH_BASE}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        """
        Exchange OAuth authorization code for access token.
        Returns: {access_token, name, dob, gender, digilocker_id, sandbox}
        """
        if self._sandbox:
            return {
                "access_token":  "sandbox-token-digilocker",
                "name":          "Sandbox User",
                "dob":           "01/01/1990",
                "gender":        "M",
                "digilocker_id": "sandbox@digitallocker",
                "sandbox":       True,
            }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                DIGILOCKER_TOKEN_URL,
                data={
                    "code":          code,
                    "grant_type":    "authorization_code",
                    "client_id":     self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri":  self._redirect_uri,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "access_token":  data["access_token"],
            "name":          data.get("name", ""),
            "dob":           data.get("dob", ""),
            "gender":        data.get("gender", ""),
            "digilocker_id": data.get("digilocker_id", ""),
            "sandbox":       False,
        }

    async def get_documents(self, access_token: str) -> list[dict]:
        """
        Fetch list of UIDAI-issued documents from DigiLocker.
        Returns list of {name, type, uri, date, issuer}.
        """
        if self._sandbox:
            return [
                {
                    "name":   "Aadhaar Card",
                    "type":   "ADHAR",
                    "uri":    "in.gov.uidai-ADHAR-123456789012-1234",
                    "date":   "2020-01-15",
                    "issuer": "UIDAI",
                    "sandbox": True,
                },
                {
                    "name":   "Driving Licence",
                    "type":   "DRVLC",
                    "uri":    "in.gov.tn.transport-DRVLC-TN0920200012345-1234",
                    "date":   "2020-03-10",
                    "issuer": "Transport Dept",
                    "sandbox": True,
                },
            ]

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                DIGILOCKER_DOC_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        docs = []
        for item in data.get("items", []):
            docs.append({
                "name":    item.get("name", ""),
                "type":    item.get("type", ""),
                "uri":     item.get("uri", ""),
                "date":    item.get("date", ""),
                "issuer":  item.get("issuer", {}).get("name", ""),
                "sandbox": False,
            })
        return docs


# ─────────────────────────────────────────────────────────────────────────────
# Error type
# ─────────────────────────────────────────────────────────────────────────────

class KYCProviderError(Exception):
    def __init__(self, message: str, provider: str = "UNKNOWN", code: Optional[str] = None):
        super().__init__(message)
        self.provider = provider
        self.code = code


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singletons (constructed lazily on first import)
# ─────────────────────────────────────────────────────────────────────────────

_surepass: Optional[SurepassClient] = None
_digilocker: Optional[DigiLockerService] = None


def get_surepass_client() -> SurepassClient:
    global _surepass
    if _surepass is None:
        _surepass = SurepassClient()
    return _surepass


def get_digilocker_service() -> DigiLockerService:
    global _digilocker
    if _digilocker is None:
        _digilocker = DigiLockerService()
    return _digilocker
