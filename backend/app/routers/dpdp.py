"""
DPDP Act 2023 Privacy Router
Prefix: /api/v1/dpdp

Two authentication surfaces:
  • JWT-authenticated (org users / recruiters) — standard protected endpoints
  • Token-authenticated (candidates) — public Privacy Centre endpoints

No bundled consent: every consent endpoint accepts exactly one purpose_code.

Endpoints:
  GET  /purposes                           – All purpose codes with full metadata
  GET  /retention-schedule                 – Legal retention periods by purpose
  GET  /data-localisation                  – India data residency status

  — Recruiter (JWT auth) —
  POST /consent                            – Record single-purpose consent (org context)
  GET  /consent/{candidate_id}             – Candidate's consent summary
  POST /erasure-request                    – Create erasure request + WhatsApp ack
  GET  /erasure-requests                   – List requests (admin)
  POST /erasure-requests/{id}/process      – Complete or reject (admin)
  POST /privacy-centre/token               – Generate candidate Privacy Centre token

  — Candidate (token auth, no JWT) —
  GET  /privacy-centre/{token}             – Candidate's full consent + request status
  POST /privacy-centre/{token}/consent     – Candidate toggles a single purpose
  POST /privacy-centre/{token}/erasure     – Candidate submits erasure request
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Optional, List

from fastapi import APIRouter, HTTPException, Query, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.dpdp_service import (
    PURPOSE_DEFINITIONS,
    STATUTORY_RETENTION,
    CONSENT_TEXT_VERSION,
    ERASURE_SLA_DAYS,
    DATA_REGION,
    create_privacy_session,
    validate_privacy_token,
    get_latest_consents,
    record_single_consent,
    create_erasure_request_with_ack,
    check_legal_retention,
    build_candidate_retention_plan,
    get_data_localisation_status,
)

router = APIRouter(tags=["DPDP Privacy"])
logger = logging.getLogger(__name__)

CurrentUser = Annotated[dict, Depends(get_current_user)]

LAW_REF_CONSENT  = "DPDP Act 2023 Section 6"
LAW_REF_ERASURE  = "DPDP Act 2023 Section 13"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_org_id(supabase, user: dict) -> str:
    res = (
        supabase.table("users").select("org_id")
        .eq("id", user["sub"]).limit(1).execute()
    )
    if not res.data:
        raise HTTPException(404, "User not found")
    return res.data[0]["org_id"]


def _get_twilio():
    try:
        from app.core.config import settings
        from twilio.rest import Client
        return (
            Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            settings.TWILIO_WHATSAPP_NUMBER,
        )
    except Exception:
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class SingleConsentRequest(BaseModel):
    """One purpose → one consent decision. No bundling allowed."""
    candidate_id:       str
    purpose_code:       str
    consented:          bool
    ip_address:         Optional[str] = None
    user_agent:         Optional[str] = None
    consent_mechanism:  str = "DIGITAL_FORM"

    @field_validator("purpose_code")
    @classmethod
    def validate_purpose(cls, v: str) -> str:
        if v not in PURPOSE_DEFINITIONS:
            raise ValueError(
                f"purpose_code must be one of: {list(PURPOSE_DEFINITIONS.keys())}"
            )
        return v


class ErasureRequestBody(BaseModel):
    candidate_id:     str
    request_type:     str = "ERASURE"   # ERASURE | CORRECTION | ACCESS
    reason:           Optional[str] = None
    specific_fields:  Optional[List[str]] = None
    candidate_phone:  Optional[str] = None
    candidate_name:   str = "Candidate"

    @field_validator("request_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid = {"ERASURE", "CORRECTION", "ACCESS", "NOMINATION"}
        if v not in valid:
            raise ValueError(f"request_type must be one of: {sorted(valid)}")
        return v


class CandidateConsentToggle(BaseModel):
    """Candidate toggles a single consent from Privacy Centre (token-authenticated)."""
    purpose_code: str
    consented:    bool

    @field_validator("purpose_code")
    @classmethod
    def validate_purpose(cls, v: str) -> str:
        if v not in PURPOSE_DEFINITIONS:
            raise ValueError(f"Unknown purpose_code: {v!r}")
        return v


class CandidateErasureRequest(BaseModel):
    request_type:  str = "ERASURE"
    reason:        Optional[str] = None
    specific_fields: Optional[List[str]] = None
    phone:         Optional[str] = None   # WhatsApp number for ack
    name:          str = "Candidate"      # for personalised WhatsApp message


class PrivacyTokenRequest(BaseModel):
    candidate_id: str
    purpose:      str = "GENERAL"


class LegalHoldRequest(BaseModel):
    active: bool
    legal_basis: Optional[str] = None
    retention_until: Optional[str] = None

    @field_validator("legal_basis")
    @classmethod
    def require_hold_basis(cls, v: Optional[str], info):
        if info.data.get("active") and not (v or "").strip():
            raise ValueError("legal_basis is required when activating a legal hold")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Public reference endpoints (no auth required)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/purposes")
async def list_purposes():
    """
    Return all DPDP purpose codes with full metadata.
    No auth required — publicly accessible for transparency.
    """
    return [
        {
            "code":            code,
            "description_en":  defn["description_en"],
            "description_hi":  defn["description_hi"],
            "required":        defn["required"],
            "legal_basis":     defn["legal_basis"],
            "retention_years": defn["retention_years"],
            "icon":            defn["icon"],
        }
        for code, defn in PURPOSE_DEFINITIONS.items()
    ]


@router.get("/retention-schedule")
async def get_retention_schedule():
    """Return legal retention periods for all purpose codes."""
    return [
        check_legal_retention(code)
        for code in PURPOSE_DEFINITIONS
    ]


@router.get("/retention-plan/{candidate_id}")
async def get_retention_plan(candidate_id: str, supabase: SupabaseClient, user: CurrentUser):
    """Preview exactly which documents an erasure would retain or delete."""
    return build_candidate_retention_plan(supabase, candidate_id, _get_org_id(supabase, user))


@router.patch("/documents/{document_id}/legal-hold")
async def set_document_legal_hold(
    document_id: str, body: LegalHoldRequest,
    supabase: SupabaseClient, user: CurrentUser,
):
    """Set or release a statutory/legal hold and preserve the evidence trail."""
    org_id = _get_org_id(supabase, user)
    rows = (supabase.table("candidate_documents").select("id,candidate_id")
            .eq("id", document_id).eq("org_id", org_id).limit(1).execute().data or [])
    if not rows:
        raise HTTPException(404, "Document not found")
    update = {"legal_hold": body.active,
              "legal_hold_basis": body.legal_basis if body.active else None,
              "retention_until": body.retention_until if body.active else None}
    supabase.table("candidate_documents").update(update).eq("id", document_id).eq("org_id", org_id).execute()
    supabase.table("dpdp_retention_actions").insert({
        "org_id": org_id, "candidate_id": rows[0].get("candidate_id"), "document_id": document_id,
        "data_category": "CANDIDATE_DOCUMENT",
        "action": "LEGAL_HOLD" if body.active else "RELEASE_HOLD",
        "status": "COMPLETED", "completed_at": datetime.utcnow().isoformat(),
        "legal_basis": body.legal_basis,
    }).execute()
    supabase.table("india_compliance_audit_logs").insert({
        "org_id": org_id, "actor_type": "RECRUITER", "actor_id": user.get("sub"),
        "action": "DPDP_DOCUMENT_LEGAL_HOLD_SET" if body.active else "DPDP_DOCUMENT_LEGAL_HOLD_RELEASED",
        "entity_type": "candidate_document", "entity_id": document_id,
        "law_reference": "DPDP Act 2023 Section 8(7)",
        "metadata": {"legal_basis": body.legal_basis, "retention_until": body.retention_until},
    }).execute()
    return {"document_id": document_id, **update}


@router.get("/data-localisation")
async def data_localisation_status():
    """Confirm India data residency compliance (DPDP Act 2023 s.16)."""
    return get_data_localisation_status()


# ─────────────────────────────────────────────────────────────────────────────
# Recruiter endpoints (JWT auth)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/consent", status_code=201)
async def record_consent(
    body: SingleConsentRequest,
    request: Request,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Record a single-purpose DPDP consent for a candidate.
    No bundled consent: exactly one purpose_code per request.
    """
    org_id     = _get_org_id(supabase, user)
    ip_address = body.ip_address or (request.client.host if request.client else None)

    try:
        rec = record_single_consent(
            supabase, org_id, body.candidate_id,
            body.purpose_code, body.consented,
            ip_address, body.user_agent, body.consent_mechanism,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return rec


@router.get("/consent/{candidate_id}")
async def get_consent_summary(
    candidate_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Return the current consent state for each purpose for a candidate.
    Shows latest record per purpose — immutable history preserved in DB.
    """
    org_id = _get_org_id(supabase, user)
    latest = get_latest_consents(supabase, candidate_id, org_id)

    # Build full summary including purposes with no record yet
    summary = []
    for code, defn in PURPOSE_DEFINITIONS.items():
        row = latest.get(code)
        summary.append({
            "purpose_code":    code,
            "description_en":  defn["description_en"],
            "description_hi":  defn["description_hi"],
            "icon":            defn["icon"],
            "required":        defn["required"],
            "consented":       row.get("consented") if row else None,
            "consented_at":    row.get("consented_at") if row else None,
            "version":         row.get("consent_text_version") if row else None,
            "mechanism":       row.get("consent_mechanism") if row else None,
        })

    return {
        "candidate_id":       candidate_id,
        "consent_version":    CONSENT_TEXT_VERSION,
        "purposes":           summary,
        "law":                LAW_REF_CONSENT,
    }


@router.post("/erasure-request", status_code=201)
async def create_erasure_request(
    body: ErasureRequestBody,
    request: Request,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Create a DPDP erasure / correction / access request.
    Automatically sends WhatsApp acknowledgment to candidate if phone provided.
    30-day SLA (response_due_at) generated by DB.
    """
    org_id = _get_org_id(supabase, user)
    twilio, wa_from = _get_twilio()

    try:
        result = create_erasure_request_with_ack(
            supabase, org_id, body.candidate_id,
            body.request_type, body.reason, body.specific_fields,
            body.candidate_phone, body.candidate_name,
            twilio=twilio, whatsapp_from=wa_from,
        )
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc

    return result


@router.get("/erasure-requests")
async def list_erasure_requests(
    supabase: SupabaseClient,
    user: CurrentUser,
    status:       Optional[str] = Query(None),
    overdue_only: bool          = Query(False),
):
    """List erasure requests for the org. Filter by status or overdue flag."""
    org_id = _get_org_id(supabase, user)

    q = (
        supabase.table("dpdp_erasure_requests")
        .select("*")
        .eq("org_id", org_id)
        .order("requested_at", desc=True)
    )
    if status:
        q = q.eq("status", status)

    rows = q.execute().data or []

    if overdue_only:
        now = datetime.utcnow().isoformat()
        rows = [
            r for r in rows
            if r.get("response_due_at") and r["response_due_at"] < now
            and r.get("status") not in ("COMPLETED", "REJECTED")
        ]

    # Annotate each row with days_remaining and is_overdue
    now_dt = datetime.utcnow()
    for row in rows:
        due_str = row.get("response_due_at")
        if due_str:
            try:
                due_dt = datetime.fromisoformat(due_str)
                days_remaining = (due_dt - now_dt).days
                row["days_remaining"] = days_remaining
                row["is_overdue"] = days_remaining < 0 and row.get("status") not in (
                    "COMPLETED", "REJECTED"
                )
            except ValueError:
                pass

    return rows


@router.post("/erasure-requests/{request_id}/process")
async def process_erasure_request(
    request_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
    action:        str           = Query(..., description="COMPLETE | REJECT"),
    denial_reason: Optional[str] = Query(None),
):
    """
    Process an erasure request.
    COMPLETE → anonymize candidate data per DPDP Act 2023 s.13.
    REJECT   → record denial reason (must state legal retention basis).
    """
    from app.services.india_compliance_service import (
        anonymize_candidate_dpdp, log_india_compliance_audit
    )

    org_id  = _get_org_id(supabase, user)
    user_id = user.get("sub")

    req_res = (
        supabase.table("dpdp_erasure_requests")
        .select("*")
        .eq("id", request_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not req_res.data:
        raise HTTPException(404, "Erasure request not found")

    req = req_res.data[0]
    if req["status"] in ("COMPLETED", "REJECTED"):
        raise HTTPException(409, f"Request already {req['status'].lower()}")

    now = datetime.utcnow().isoformat()

    if action == "COMPLETE":
        manifest = anonymize_candidate_dpdp(supabase, req["candidate_id"], org_id)
        supabase.table("dpdp_erasure_requests").update({
            "status":       "COMPLETED",
            "completed_at": now,
            "processed_by": user_id,
            "erasure_manifest": manifest,
            "storage_deletion_status": manifest.get("storage_deletion_status", "COMPLETED"),
            "storage_deleted_at": now if manifest.get("storage_deletion_status") == "COMPLETED" else None,
        }).eq("id", request_id).execute()

        log_india_compliance_audit(
            supabase, "DPDP_ERASURE_COMPLETED",
            "candidate", req["candidate_id"], org_id, user_id,
            law_reference=LAW_REF_ERASURE,
        )
        return {"processed": True, "action": "COMPLETED", "anonymised": True, "manifest": manifest}

    if action == "REJECT":
        if not denial_reason:
            raise HTTPException(422, "denial_reason required when rejecting — state legal retention basis")
        supabase.table("dpdp_erasure_requests").update({
            "status":                 "REJECTED",
            "denial_reason":          denial_reason,
            "retention_legal_basis":  denial_reason,
            "completed_at":           now,
            "processed_by":           user_id,
        }).eq("id", request_id).execute()

        log_india_compliance_audit(
            supabase, "DPDP_ERASURE_REJECTED",
            "candidate", req["candidate_id"], org_id, user_id,
            metadata={"denial_reason": denial_reason},
            law_reference=LAW_REF_ERASURE,
        )
        return {"processed": True, "action": "REJECTED", "denial_reason": denial_reason}

    raise HTTPException(422, "action must be COMPLETE or REJECT")


@router.post("/privacy-centre/token", status_code=201)
async def issue_privacy_token(
    body: PrivacyTokenRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Issue a 7-day Privacy Centre access token for a candidate.
    Token can be embedded in an SMS or WhatsApp link.
    """
    _get_org_id(supabase, user)
    session = create_privacy_session(supabase, body.candidate_id, body.purpose)
    return {
        "token":      session["token"],
        "expires_at": session["expires_at"],
        "url_hint":   f"/privacy-centre/{session['token']}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Candidate Privacy Centre — token-authenticated (no JWT required)
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_candidate(supabase, token: str) -> str:
    """Resolve token → candidate_id or raise 401."""
    try:
        return validate_privacy_token(supabase, token)
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc


@router.get("/privacy-centre/{token}")
async def get_privacy_centre(token: str, supabase: SupabaseClient):
    """
    Candidate's Privacy Centre dashboard.
    No JWT required — authenticated via secure token.
    Returns consent state, pending requests, and data inventory.
    """
    candidate_id = _resolve_candidate(supabase, token)

    # Consent summary
    latest = get_latest_consents(supabase, candidate_id)
    consent_summary = []
    for code, defn in PURPOSE_DEFINITIONS.items():
        row = latest.get(code)
        retention = check_legal_retention(code)
        consent_summary.append({
            "purpose_code":    code,
            "description_en":  defn["description_en"],
            "description_hi":  defn["description_hi"],
            "icon":            defn["icon"],
            "required":        defn["required"],
            "consented":       row["consented"] if row else None,
            "consented_at":    row["consented_at"] if row else None,
            "can_withdraw":    not defn["required"],
            "retention_years": defn["retention_years"],
            "legal_basis":     defn["legal_basis"],
            "can_fully_erase": retention["can_fully_erase"],
        })

    # Pending erasure/access requests
    requests_res = (
        supabase.table("dpdp_erasure_requests")
        .select("id, request_type, status, requested_at, response_due_at, "
                "denial_reason, completed_at")
        .eq("candidate_id", candidate_id)
        .order("requested_at", desc=True)
        .limit(10)
        .execute()
    )
    requests = requests_res.data or []

    now_dt = datetime.utcnow()
    for r in requests:
        due = r.get("response_due_at")
        if due:
            try:
                r["days_remaining"] = (datetime.fromisoformat(due) - now_dt).days
            except ValueError:
                pass

    return {
        "candidate_id":         candidate_id,
        "consent_version":      CONSENT_TEXT_VERSION,
        "consents":             consent_summary,
        "requests":             requests,
        "data_region":          DATA_REGION,
        "data_fiduciary":       "HospRecruit AI Pvt Ltd",
        "grievance_officer":    "privacy@hosprecruit.ai",
        "dpbi_url":             "https://www.meity.gov.in/dpdp",
        "law":                  "DPDP Act 2023",
    }


@router.post("/privacy-centre/{token}/consent", status_code=201)
async def candidate_toggle_consent(
    token: str,
    body: CandidateConsentToggle,
    request: Request,
    supabase: SupabaseClient,
):
    """
    Candidate toggles a single consent purpose from the Privacy Centre.
    No JWT — authenticated by token. No bundling: one purpose per request.
    """
    candidate_id = _resolve_candidate(supabase, token)
    ip_address   = request.client.host if request.client else None

    # Resolve org_id for the candidate
    cand_res = (
        supabase.table("candidates")
        .select("org_id")
        .eq("id", candidate_id)
        .limit(1)
        .execute()
    )
    org_id = cand_res.data[0]["org_id"] if cand_res.data else None

    try:
        rec = record_single_consent(
            supabase, org_id, candidate_id,
            body.purpose_code, body.consented,
            ip_address=ip_address,
            consent_mechanism="PRIVACY_CENTRE",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "recorded":     True,
        "purpose_code": body.purpose_code,
        "consented":    body.consented,
        "version":      CONSENT_TEXT_VERSION,
        "record_id":    rec.get("id"),
    }


@router.post("/privacy-centre/{token}/erasure", status_code=201)
async def candidate_erasure_request(
    token: str,
    body: CandidateErasureRequest,
    request: Request,
    supabase: SupabaseClient,
):
    """
    Candidate submits an erasure / correction / access request from Privacy Centre.
    WhatsApp acknowledgment is sent if phone is provided.
    """
    candidate_id = _resolve_candidate(supabase, token)

    cand_res = (
        supabase.table("candidates")
        .select("org_id")
        .eq("id", candidate_id)
        .limit(1)
        .execute()
    )
    org_id = cand_res.data[0]["org_id"] if cand_res.data else None

    twilio, wa_from = _get_twilio()

    try:
        result = create_erasure_request_with_ack(
            supabase, org_id, candidate_id,
            body.request_type, body.reason, body.specific_fields,
            body.phone, body.name,
            twilio=twilio, whatsapp_from=wa_from,
        )
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc

    return result


@router.get("/privacy-centre/{token}/retention")
async def candidate_retention_info(token: str, supabase: SupabaseClient):
    """
    Explain to the candidate which of their data must be retained and why.
    Helps candidates understand why some erasure requests may be partially honoured.
    """
    _resolve_candidate(supabase, token)
    return {
        "retention_schedule": [check_legal_retention(c) for c in PURPOSE_DEFINITIONS],
        "statutory_retention": STATUTORY_RETENTION,
        "note": (
            "Data marked exempts_erasure=true must be retained under Indian law "
            "regardless of your erasure request. You may appeal to the "
            "Data Protection Board of India (DPBI)."
        ),
        "dpbi_url": "https://www.meity.gov.in/dpdp",
        "law":      "DPDP Act 2023 Section 8(7)",
    }


@router.get("/privacy-centre/{token}/data-access")
async def candidate_data_access(token: str, supabase: SupabaseClient):
    """Candidate-readable data package; identifiers remain masked and storage keys are excluded."""
    candidate_id = _resolve_candidate(supabase, token)
    candidates = (supabase.table("candidates")
                  .select("id,org_id,first_name,last_name,email,phone,location,state,city,source,status,pipeline_stage,created_at,updated_at")
                  .eq("id", candidate_id).limit(1).execute().data or [])
    applications = (supabase.table("applications")
                    .select("id,job_role_id,campaign_id,source,status,applied_via,form_data,created_at,updated_at")
                    .eq("candidate_id", candidate_id).execute().data or [])
    documents = (supabase.table("candidate_documents")
                 .select("id,document_type,file_name,mime_type,status,expiry_date,retention_until,legal_hold,created_at")
                 .eq("candidate_id", candidate_id).execute().data or [])
    identity = (supabase.table("india_identity_verifications")
                .select("id,doc_type,aadhaar_masked,pan_masked,status,verified_at,doc_expiry_date,created_at")
                .eq("candidate_id", candidate_id).execute().data or [])
    candidate = dict(candidates[0]) if candidates else None
    org_id = candidate.pop("org_id", None) if candidate else None
    try:
        supabase.table("india_compliance_audit_logs").insert({
            "org_id": org_id, "actor_type": "CANDIDATE", "action": "DPDP_DATA_ACCESS_PACKAGE_VIEWED",
            "entity_type": "candidate", "entity_id": candidate_id,
            "law_reference": "DPDP Act 2023 Section 11/13",
            "metadata": {"surface": "PRIVACY_CENTRE"},
        }).execute()
    except Exception:
        logger.exception("Failed to audit DPDP data access for candidate %s", candidate_id)
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "candidate": candidate,
        "applications": applications,
        "documents": documents,
        "identity_verifications": identity,
        "consents": get_latest_consents(supabase, candidate_id),
        "data_region": DATA_REGION,
        "notice": "Aadhaar and PAN are masked. Storage keys and provider secrets are excluded.",
    }
