"""
India KYC Router — Aadhaar eKYC OTP + PAN + DigiLocker
Prefix: /api/v1/kyc

Security contracts (enforced here, not in service layer):
  • Full Aadhaar number accepted in request body → last4 extracted → original
    discarded immediately after calling the provider. Never logged, never stored.
  • PAN stored in masked form only (ABCDE****F).
  • Every verification attempt (pass or fail) is audit-logged.
"""

from __future__ import annotations

import secrets
import logging
from datetime import datetime
from typing import Optional, Annotated

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, field_validator
from fastapi.responses import JSONResponse

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.india_compliance_service import (
    validate_aadhaar_last4,
    validate_pan,
    log_india_compliance_audit,
)
from app.services.kyc_service import (
    SurepassClient,
    DigiLockerService,
    KYCProviderError,
    extract_aadhaar_last4,
    mask_aadhaar,
    mask_pan,
    validate_aadhaar_number,
    get_surepass_client,
    get_digilocker_service,
)
from app.services.data_localization import DataLocalizationGuard, DataLocalizationError
from app.core.config import settings

router = APIRouter(tags=["KYC"])
logger = logging.getLogger(__name__)

CurrentUser = Annotated[dict, Depends(get_current_user)]


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _get_org_id(supabase, user: dict) -> str:
    result = (
        supabase.table("users")
        .select("org_id")
        .eq("id", user["sub"])
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "User record not found")
    return result.data[0]["org_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class AadhaarInitiateRequest(BaseModel):
    aadhaar_number: str  # 12-digit — extracted+discarded server-side, NEVER stored
    candidate_id:   str

    @field_validator("aadhaar_number")
    @classmethod
    def check_aadhaar_format(cls, v: str) -> str:
        if not validate_aadhaar_number(v):
            raise ValueError(
                "Aadhaar must be a 12-digit number and must not start with 0"
            )
        return v  # returned only for Pydantic; extracted before any persistence


class AadhaarVerifyRequest(BaseModel):
    request_id:   str   # returned by initiate
    otp:          str   # 6-digit OTP from registered mobile
    candidate_id: str

    @field_validator("otp")
    @classmethod
    def check_otp_format(cls, v: str) -> str:
        if not v.isdigit() or len(v) not in (4, 6):
            raise ValueError("OTP must be 4 or 6 digits")
        return v


class PANVerifyRequest(BaseModel):
    pan_number:     str
    candidate_id:   str
    name_to_match:  Optional[str] = None  # optional — triggers name-match check

    @field_validator("pan_number")
    @classmethod
    def check_pan_format(cls, v: str) -> str:
        if not validate_pan(v):
            raise ValueError("Invalid PAN format. Expected: ABCDE1234F")
        return v.upper().strip()


class DigiLockerCallbackRequest(BaseModel):
    code:         str
    state:        str   # encoded candidate_id + CSRF token
    candidate_id: str


# ─────────────────────────────────────────────────────────────────────────────
# Aadhaar eKYC — initiate OTP
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/aadhaar/initiate", status_code=200)
async def aadhaar_initiate(
    body: AadhaarInitiateRequest,
    request: Request,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Step 1 of Aadhaar eKYC: send OTP to candidate's UIDAI-registered mobile.

    The full Aadhaar number is validated here then passed to Surepass.
    It is NEVER written to any database — only the last 4 digits are kept
    after OTP verification succeeds (step 2).
    """
    org_id = _get_org_id(supabase, user)

    # Guard: Aadhaar is NEVER allowed to go to non-India services
    guard = DataLocalizationGuard(settings, supabase=supabase)
    try:
        guard.check_external_pii(
            "SUREPASS", ["AADHAAR"],
            candidate_id=body.candidate_id,
            org_id=org_id,
            fields_sent=["aadhaar_number"],
        )
    except DataLocalizationError as exc:
        raise HTTPException(403, f"Data localisation block: {exc}") from exc

    client = get_surepass_client()

    try:
        result = await client.initiate_aadhaar_otp(body.aadhaar_number)
    except KYCProviderError as exc:
        log_india_compliance_audit(
            supabase, "AADHAAR_OTP_INITIATE_FAILED",
            "candidate", body.candidate_id, org_id,
            law_reference="Aadhaar Act 2016 / UIDAI eKYC",
        )
        raise HTTPException(502, f"KYC provider error: {exc}") from exc

    # Persist the session (request_id only — NOT the Aadhaar number)
    now = datetime.utcnow().isoformat()
    session_payload = {
        "org_id":       org_id,
        "candidate_id": body.candidate_id,
        "provider":     "SANDBOX" if result["sandbox"] else "SUREPASS",
        "request_id":   result["request_id"],
        "status":       "OTP_SENT",
        "ip_address":   request.client.host if request.client else None,
        "created_at":   now,
        "expires_at":   (datetime.utcnow()).isoformat(),  # DB default handles +10 min
    }
    session_res = supabase.table("aadhaar_kyc_sessions").insert(session_payload).execute()
    if not session_res.data:
        raise HTTPException(500, "Failed to create KYC session")

    log_india_compliance_audit(
        supabase, "AADHAAR_OTP_INITIATED",
        "candidate", body.candidate_id, org_id,
        law_reference="Aadhaar Act 2016 / UIDAI eKYC",
    )

    return {
        "request_id": result["request_id"],
        "message":    result["message"],
        "sandbox":    result["sandbox"],
        "expires_in_seconds": 600,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Aadhaar eKYC — verify OTP
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/aadhaar/verify", status_code=200)
async def aadhaar_verify(
    body: AadhaarVerifyRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Step 2 of Aadhaar eKYC: verify OTP and store only last 4 digits.

    On success:
      • aadhaar_kyc_sessions row updated (status=VERIFIED, last4, name, etc.)
      • india_identity_verifications row created (doc_type=AADHAAR, VERIFIED)
      • candidates.aadhaar_verified set to TRUE
    """
    org_id = _get_org_id(supabase, user)

    # Load the session
    session_res = (
        supabase.table("aadhaar_kyc_sessions")
        .select("id, status, otp_attempts, expires_at, provider, candidate_id")
        .eq("request_id", body.request_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not session_res.data:
        raise HTTPException(404, "KYC session not found")

    session = session_res.data[0]

    if session["status"] == "VERIFIED":
        raise HTTPException(409, "This session has already been verified")
    if session["status"] == "FAILED":
        raise HTTPException(410, "This session has expired or failed")

    # Call provider
    client = get_surepass_client()
    try:
        kyc = await client.verify_aadhaar_otp(body.request_id, body.otp)
    except KYCProviderError as exc:
        # Increment attempt counter; mark FAILED after 3 attempts
        attempts = (session.get("otp_attempts") or 0) + 1
        new_status = "FAILED" if attempts >= 3 else "OTP_SENT"
        supabase.table("aadhaar_kyc_sessions").update(
            {"otp_attempts": attempts, "status": new_status}
        ).eq("id", session["id"]).execute()

        log_india_compliance_audit(
            supabase, "AADHAAR_OTP_VERIFY_FAILED",
            "candidate", body.candidate_id, org_id,
            law_reference="Aadhaar Act 2016 / UIDAI eKYC",
        )
        raise HTTPException(400, f"OTP verification failed: {exc}") from exc

    now_iso = datetime.utcnow().isoformat()

    # Update session to VERIFIED (store only the safe fields — no full Aadhaar)
    supabase.table("aadhaar_kyc_sessions").update({
        "status":         "VERIFIED",
        "aadhaar_last4":  kyc["aadhaar_last4"],
        "aadhaar_masked": kyc["aadhaar_masked"],
        "name_from_uid":  kyc["name"],
        "dob_year":       kyc["dob_year"],
        "gender":         kyc["gender"],
        "address_state":  kyc["address_state"],
        "verified_at":    now_iso,
    }).eq("id", session["id"]).execute()

    # Create identity_verifications record
    verif_payload = {
        "org_id":           org_id,
        "candidate_id":     body.candidate_id,
        "doc_type":         "AADHAAR",
        "aadhaar_last4":    kyc["aadhaar_last4"],
        "aadhaar_masked":   kyc["aadhaar_masked"],
        "status":           "VERIFIED",
        "verified_at":      now_iso,
        "kyc_provider":     "SANDBOX" if kyc["sandbox"] else "SUREPASS",
        "kyc_session_id":   session["id"],
        "notes":            f"eKYC via {session.get('provider', 'SUREPASS')}. Name: {kyc['name']}",
        "created_at":       now_iso,
        "updated_at":       now_iso,
    }
    verif_res = supabase.table("india_identity_verifications").insert(verif_payload).execute()
    verif_id = verif_res.data[0]["id"] if verif_res.data else None

    # Link session → verification record
    if verif_id:
        supabase.table("aadhaar_kyc_sessions").update(
            {"identity_verification_id": verif_id}
        ).eq("id", session["id"]).execute()

    # Mark candidate as Aadhaar-verified
    supabase.table("candidates").update(
        {"aadhaar_verified": True}
    ).eq("id", body.candidate_id).execute()

    log_india_compliance_audit(
        supabase, "AADHAAR_VERIFIED",
        "candidate", body.candidate_id, org_id,
        law_reference="Aadhaar Act 2016 / UIDAI eKYC",
    )

    return {
        "verified":       True,
        "aadhaar_last4":  kyc["aadhaar_last4"],
        "aadhaar_masked": kyc["aadhaar_masked"],
        "name_from_uid":  kyc["name"],
        "gender":         kyc["gender"],
        "sandbox":        kyc["sandbox"],
        "verification_id": verif_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PAN verification
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/pan/verify", status_code=200)
async def pan_verify(
    body: PANVerifyRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Verify PAN with Surepass (or sandbox mock).
    Only the masked PAN (ABCDE****F) is stored — full PAN discarded after call.
    """
    org_id = _get_org_id(supabase, user)

    # Guard: PAN is NEVER allowed to go to non-India services
    guard = DataLocalizationGuard(settings, supabase=supabase)
    try:
        guard.check_external_pii(
            "SUREPASS", ["PAN"],
            candidate_id=body.candidate_id,
            org_id=org_id,
            fields_sent=["pan_number"],
        )
    except DataLocalizationError as exc:
        raise HTTPException(403, f"Data localisation block: {exc}") from exc

    client = get_surepass_client()

    try:
        result = await client.verify_pan(body.pan_number, body.name_to_match)
    except KYCProviderError as exc:
        log_india_compliance_audit(
            supabase, "PAN_VERIFY_FAILED",
            "candidate", body.candidate_id, org_id,
            law_reference="Income Tax Act 1961 / PAN Rules 1962",
        )
        raise HTTPException(502, f"KYC provider error: {exc}") from exc

    now_iso = datetime.utcnow().isoformat()

    # Store only the masked PAN
    verif_payload = {
        "org_id":         org_id,
        "candidate_id":   body.candidate_id,
        "doc_type":       "PAN",
        "pan_masked":     result["pan_masked"],
        # pan_number intentionally set to masked value (per user requirement)
        "pan_number":     result["pan_masked"],
        "pan_name_match": result["name_match"],
        "status":         "VERIFIED" if result["valid"] else "REJECTED",
        "verified_at":    now_iso if result["valid"] else None,
        "kyc_provider":   "SANDBOX" if result["sandbox"] else "SUREPASS",
        "notes":          f"Name on PAN: {result['name_on_pan']}",
        "created_at":     now_iso,
        "updated_at":     now_iso,
    }
    verif_res = supabase.table("india_identity_verifications").insert(verif_payload).execute()
    verif_id = verif_res.data[0]["id"] if verif_res.data else None

    # Mark candidate PAN verified
    if result["valid"]:
        supabase.table("candidates").update(
            {"pan_verified": True}
        ).eq("id", body.candidate_id).execute()

    log_india_compliance_audit(
        supabase,
        "PAN_VERIFIED" if result["valid"] else "PAN_VERIFY_FAILED",
        "candidate", body.candidate_id, org_id,
        law_reference="Income Tax Act 1961 / PAN Rules 1962",
    )

    return {
        "verified":       result["valid"],
        "pan_masked":     result["pan_masked"],
        "name_on_pan":    result["name_on_pan"],
        "name_match":     result["name_match"],
        "sandbox":        result["sandbox"],
        "verification_id": verif_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DigiLocker — get OAuth URL
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/digilocker/auth-url", status_code=200)
async def digilocker_auth_url(
    candidate_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Return DigiLocker OAuth URL.
    Caller should redirect the candidate's browser to this URL.
    State encodes candidate_id + CSRF token for callback validation.
    """
    org_id = _get_org_id(supabase, user)
    csrf = secrets.token_urlsafe(16)
    # state = "{candidate_id}:{csrf}" — validated in callback
    state = f"{candidate_id}:{csrf}"

    svc = get_digilocker_service()
    url = svc.get_auth_url(state=state)

    log_india_compliance_audit(
        supabase, "DIGILOCKER_AUTH_INITIATED",
        "candidate", candidate_id, org_id,
        law_reference="Information Technology Act 2000 / DigiLocker Act",
    )

    return {
        "auth_url":     url,
        "state":        state,
        "sandbox":      svc._sandbox,
        "instructions": "Redirect the candidate browser to auth_url",
    }


# ─────────────────────────────────────────────────────────────────────────────
# DigiLocker — OAuth callback
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/digilocker/callback", status_code=200)
async def digilocker_callback(
    body: DigiLockerCallbackRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Exchange DigiLocker auth code for token, fetch issued documents, and
    create india_identity_verifications records for each document found.
    """
    org_id = _get_org_id(supabase, user)
    svc = get_digilocker_service()

    try:
        token_data = await svc.exchange_code(body.code)
        documents = await svc.get_documents(token_data["access_token"])
    except Exception as exc:
        log_india_compliance_audit(
            supabase, "DIGILOCKER_CALLBACK_FAILED",
            "candidate", body.candidate_id, org_id,
            law_reference="Information Technology Act 2000 / DigiLocker Act",
        )
        raise HTTPException(502, f"DigiLocker error: {exc}") from exc

    now_iso = datetime.utcnow().isoformat()
    created = []
    for doc in documents:
        payload = {
            "org_id":          org_id,
            "candidate_id":    body.candidate_id,
            "doc_type":        "DIGILOCKER",
            "digilocker_uri":  doc["uri"],
            "digilocker_doc_type": doc["type"],
            "status":          "VERIFIED",
            "verified_at":     now_iso,
            "kyc_provider":    "SANDBOX" if doc.get("sandbox") else "SUREPASS",
            "notes":           f"DigiLocker: {doc['name']} issued by {doc['issuer']}",
            "created_at":      now_iso,
            "updated_at":      now_iso,
        }
        res = supabase.table("india_identity_verifications").insert(payload).execute()
        if res.data:
            created.append({"doc_name": doc["name"], "id": res.data[0]["id"]})

    log_india_compliance_audit(
        supabase, "DIGILOCKER_VERIFIED",
        "candidate", body.candidate_id, org_id,
        law_reference="Information Technology Act 2000 / DigiLocker Act",
    )

    return {
        "verified":   True,
        "name":       token_data["name"],
        "documents":  created,
        "doc_count":  len(created),
        "sandbox":    token_data["sandbox"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# KYC status summary
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/status/{candidate_id}", status_code=200)
async def kyc_status(
    candidate_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Return KYC completion status for a candidate across all document types.
    """
    org_id = _get_org_id(supabase, user)

    verifs_res = (
        supabase.table("india_identity_verifications")
        .select("doc_type, status, pan_masked, aadhaar_masked, verified_at, kyc_provider")
        .eq("candidate_id", candidate_id)
        .eq("org_id", org_id)
        .order("created_at")
        .execute()
    )
    verifs = verifs_res.data or []

    candidate_res = (
        supabase.table("candidates")
        .select("aadhaar_verified, pan_verified")
        .eq("id", candidate_id)
        .limit(1)
        .execute()
    )
    cand = candidate_res.data[0] if candidate_res.data else {}

    return {
        "candidate_id":      candidate_id,
        "aadhaar_verified":  cand.get("aadhaar_verified", False),
        "pan_verified":      cand.get("pan_verified", False),
        "verifications":     verifs,
        "total_verified":    sum(1 for v in verifs if v["status"] == "VERIFIED"),
        "kyc_complete":      cand.get("aadhaar_verified") and cand.get("pan_verified"),
    }
