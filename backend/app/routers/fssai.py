"""
FSSAI Certificate Router — dedicated router for food safety certification tracking.
Prefix: /api/v1/fssai

Endpoints:
  POST   /certificates                     – Create cert record + get presigned S3 URL
  GET    /certificates                     – List certs (org, optional candidate filter)
  GET    /certificates/expiring            – Certs expiring within N days
  GET    /certificates/{id}                – Single cert details
  PATCH  /certificates/{id}/confirm-upload – Mark file uploaded; save doc_url
  GET    /certificates/{id}/download-url   – Get presigned download URL
  POST   /worker/run                       – Manually trigger expiry worker (admin)

Certificate types supported:
  BASIC_FOOD_HYGIENE    – Basic Food Hygiene training (individual)
  FOSTAC                – FoSTaC (Food Safety Training and Certification)
  FSSAI_LICENSE         – FSSAI establishment license (14-digit)
  ALCOHOL_LICENSE_FORM_FL – State Excise alcohol licence (Form FL-3/FL-11)

  Legacy (backward compat):
  ESTABLISHMENT_LICENSE, FOSTAC_TRAINING, FOOD_HANDLER
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, field_validator

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.fssai_s3_service import (
    FSSAIStorageService,
    get_fssai_storage,
    ALLOWED_CONTENT_TYPES,
    FSSAI_S3_REGION,
)
from app.services.data_localization import DataLocalizationGuard
from app.core.config import settings
from app.services.rbac_service import authorize, build_access_context
from app.services.india_compliance_service import (
    validate_fssai_license,
    log_india_compliance_audit,
)

router = APIRouter(tags=["FSSAI"])
logger = logging.getLogger(__name__)

CurrentUser = Annotated[dict, Depends(get_current_user)]

VALID_CERT_TYPES = {
    "BASIC_FOOD_HYGIENE",
    "FOSTAC",
    "FSSAI_LICENSE",
    "ALCOHOL_LICENSE_FORM_FL",
    # legacy
    "ESTABLISHMENT_LICENSE",
    "FOSTAC_TRAINING",
    "FOOD_HANDLER",
}

TRAINING_CERT_TYPES = {
    "BASIC_FOOD_HYGIENE", "FOSTAC", "FOSTAC_TRAINING", "FOOD_HANDLER",
}

LAW_REF = "Food Safety and Standards Act 2006 / FSSAI Regulations"


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class FSSAICertCreate(BaseModel):
    cert_type:           str
    candidate_id:        Optional[str] = None
    license_number:      Optional[str] = None   # 14-digit for FSSAI_LICENSE
    license_type:        Optional[str] = None   # BASIC | STATE | CENTRAL
    licensed_entity:     Optional[str] = None
    activity_category:   Optional[str] = None
    fostac_cert_number:  Optional[str] = None
    training_provider:   Optional[str] = None
    fostac_course:       Optional[str] = None
    alcohol_license_number: Optional[str] = None
    alcohol_license_form:   Optional[str] = None   # FL-3 | FL-11 | FL-12
    issuing_authority:   Optional[str] = None
    issue_date:          Optional[str] = None
    expiry_date:         str
    state_code:          Optional[str] = None
    candidate_phone:     Optional[str] = None   # E.164 or local Indian
    recruiter_email:     Optional[str] = None
    # Upload metadata
    filename:            Optional[str] = None   # triggers presigned URL generation
    content_type:        Optional[str] = "application/pdf"

    @field_validator("cert_type")
    @classmethod
    def check_cert_type(cls, v: str) -> str:
        if v not in VALID_CERT_TYPES:
            raise ValueError(
                f"cert_type must be one of: {sorted(VALID_CERT_TYPES)}"
            )
        return v

    @field_validator("license_number")
    @classmethod
    def check_license_number(cls, v: Optional[str]) -> Optional[str]:
        if v and not validate_fssai_license(v):
            raise ValueError("FSSAI license_number must be exactly 14 digits")
        return v

    @field_validator("content_type")
    @classmethod
    def check_content_type(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in ALLOWED_CONTENT_TYPES:
            raise ValueError(
                f"content_type must be one of: {sorted(ALLOWED_CONTENT_TYPES)}"
            )
        return v


class ConfirmUploadRequest(BaseModel):
    s3_key: str   # as returned by the create endpoint


class FSSAIVerifyRequest(BaseModel):
    status: str
    notes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        value = value.upper()
        if value not in {"ACTIVE", "REJECTED"}:
            raise ValueError("status must be ACTIVE or REJECTED")
        return value


class FSSAIRenewRequest(BaseModel):
    issue_date: Optional[str] = None
    expiry_date: str
    license_number: Optional[str] = None
    fostac_cert_number: Optional[str] = None
    filename: Optional[str] = None
    content_type: str = "application/pdf"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
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
        raise HTTPException(404, "User not found")
    return result.data[0]["org_id"]


# ─────────────────────────────────────────────────────────────────────────────
# POST /certificates — Create cert record (+ presigned upload URL if filename given)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/certificates", status_code=201)
async def create_fssai_cert(
    body: FSSAICertCreate,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Create an FSSAI certificate record.

    If `filename` and `content_type` are provided, also returns a presigned S3
    PUT URL so the frontend can upload the certificate file directly to S3
    (ap-south-1).  After upload, call PATCH /certificates/{id}/confirm-upload.
    """
    org_id = _get_org_id(supabase, user)
    now    = datetime.utcnow().isoformat()

    payload = {
        "org_id":                org_id,
        "candidate_id":          body.candidate_id,
        "cert_type":             body.cert_type,
        "license_number":        body.license_number,
        "license_type":          body.license_type,
        "licensed_entity":       body.licensed_entity,
        "activity_category":     body.activity_category,
        "fostac_cert_number":    body.fostac_cert_number,
        "training_provider":     body.training_provider,
        "fostac_course":         body.fostac_course,
        "alcohol_license_number": body.alcohol_license_number,
        "alcohol_license_form":  body.alcohol_license_form,
        "issuing_authority":     body.issuing_authority,
        "issue_date":            body.issue_date,
        "expiry_date":           body.expiry_date,
        "state_code":            body.state_code,
        "candidate_phone":       body.candidate_phone,
        "recruiter_email":       body.recruiter_email,
        "status":                "PENDING_VERIFICATION",
        "created_at":            now,
        "updated_at":            now,
    }

    result = supabase.table("fssai_certificates").insert(payload).execute()
    if not result.data:
        raise HTTPException(500, "Failed to create FSSAI certificate record")

    cert = result.data[0]
    cert_id = cert["id"]

    # Mark candidate fssai_trained for individual training certs
    if body.candidate_id and body.cert_type in TRAINING_CERT_TYPES:
        supabase.table("candidates").update(
            {"fssai_trained": True}
        ).eq("id", body.candidate_id).execute()

    log_india_compliance_audit(
        supabase, "FSSAI_CERT_ADDED",
        "fssai_certificates", cert_id, org_id,
        law_reference=LAW_REF,
    )

    # Optionally generate presigned upload URL
    upload_info: Optional[dict] = None
    if body.filename:
        try:
            storage = get_fssai_storage()
            upload_info = storage.generate_upload_url(
                cert_id=cert_id,
                cert_type=body.cert_type,
                original_filename=body.filename,
                content_type=body.content_type or "application/pdf",
            )
            # Persist the s3_key so confirm-upload can verify it
            supabase.table("fssai_certificates").update(
                {"s3_key": upload_info["s3_key"], "updated_at": now}
            ).eq("id", cert_id).execute()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            logger.warning("Presigned URL generation failed: %s", exc)
            # Don't fail the whole request — cert record is already saved

    response = {**cert}
    if upload_info:
        response["upload"] = upload_info

    return response


@router.patch("/certificates/{cert_id}/verify")
async def verify_fssai_certificate(
    cert_id: str, body: FSSAIVerifyRequest,
    supabase: SupabaseClient, user: CurrentUser,
):
    context = build_access_context(supabase, user)
    authorize(context, "compliance.manage")
    org_id = _get_org_id(supabase, user)
    update = {"status": body.status, "verification_notes": body.notes,
              "verified_by": user.get("sub"), "verified_at": datetime.utcnow().isoformat(),
              "updated_at": datetime.utcnow().isoformat()}
    rows = (supabase.table("fssai_certificates").update(update)
            .eq("id", cert_id).eq("org_id", org_id).execute().data or [])
    if not rows: raise HTTPException(404, "Certificate not found")
    log_india_compliance_audit(supabase, f"FSSAI_CERT_{body.status}",
        "fssai_certificates", cert_id, org_id, user.get("sub"), law_reference=LAW_REF)
    return rows[0]


@router.post("/certificates/{cert_id}/renew", status_code=201)
async def renew_fssai_certificate(
    cert_id: str, body: FSSAIRenewRequest,
    supabase: SupabaseClient, user: CurrentUser,
):
    context = build_access_context(supabase, user)
    authorize(context, "compliance.manage")
    org_id = _get_org_id(supabase, user)
    old_rows = (supabase.table("fssai_certificates").select("*")
                .eq("id", cert_id).eq("org_id", org_id).limit(1).execute().data or [])
    if not old_rows: raise HTTPException(404, "Certificate not found")
    old = old_rows[0]; now = datetime.utcnow().isoformat()
    copied = {key: old.get(key) for key in (
        "candidate_id","cert_type","license_type","licensed_entity","activity_category",
        "training_provider","fostac_course","state_code","candidate_phone","recruiter_email",
        "alcohol_license_number","alcohol_license_form","issuing_authority")}
    payload = {**copied, "org_id": org_id, "issue_date": body.issue_date,
               "expiry_date": body.expiry_date, "license_number": body.license_number or old.get("license_number"),
               "fostac_cert_number": body.fostac_cert_number or old.get("fostac_cert_number"),
               "renewal_of": cert_id, "status": "PENDING_VERIFICATION",
               "created_at": now, "updated_at": now}
    rows = supabase.table("fssai_certificates").insert(payload).execute().data or []
    if not rows: raise HTTPException(500, "Failed to create renewal certificate")
    renewed = rows[0]
    supabase.table("fssai_certificates").update({"status":"RENEWED","renewed_by":renewed["id"],"updated_at":now})\
        .eq("id", cert_id).eq("org_id", org_id).execute()
    upload = None
    if body.filename:
        upload = get_fssai_storage().generate_upload_url(renewed["id"], old["cert_type"], body.filename, body.content_type)
        supabase.table("fssai_certificates").update({"s3_key":upload["s3_key"]}).eq("id",renewed["id"]).execute()
    log_india_compliance_audit(supabase, "FSSAI_CERT_RENEWAL_CREATED",
        "fssai_certificates", renewed["id"], org_id, user.get("sub"),
        metadata={"renewal_of":cert_id}, law_reference=LAW_REF)
    return {**renewed, **({"upload":upload} if upload else {})}


# ─────────────────────────────────────────────────────────────────────────────
# GET /certificates — List all certs for org
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/certificates")
async def list_fssai_certs(
    supabase: SupabaseClient,
    user: CurrentUser,
    candidate_id: Optional[str] = Query(None),
    cert_type:    Optional[str] = Query(None),
    status:       Optional[str] = Query(None),
):
    """List FSSAI certificates for the org with optional filters."""
    org_id = _get_org_id(supabase, user)
    q = (
        supabase.table("fssai_certificates")
        .select("*")
        .eq("org_id", org_id)
        .order("expiry_date")
    )
    if candidate_id:
        q = q.eq("candidate_id", candidate_id)
    if cert_type:
        q = q.eq("cert_type", cert_type)
    if status:
        q = q.eq("status", status)
    return q.execute().data or []


# ─────────────────────────────────────────────────────────────────────────────
# GET /certificates/expiring — Certs expiring within N days
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/certificates/expiring")
async def get_expiring_certs(
    supabase: SupabaseClient,
    user: CurrentUser,
    days: int = Query(30, ge=1, le=180),
):
    """Return ACTIVE certs expiring within `days` days."""
    org_id = _get_org_id(supabase, user)
    from app.services.india_compliance_service import get_expiring_fssai_certs
    return get_expiring_fssai_certs(supabase, org_id, days)


# ─────────────────────────────────────────────────────────────────────────────
# GET /certificates/{id} — Single cert
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/certificates/{cert_id}")
async def get_fssai_cert(
    cert_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Get a single FSSAI certificate record."""
    org_id = _get_org_id(supabase, user)
    result = (
        supabase.table("fssai_certificates")
        .select("*")
        .eq("id", cert_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Certificate not found")
    return result.data[0]


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /certificates/{id}/confirm-upload — Confirm S3 upload
# ─────────────────────────────────────────────────────────────────────────────

@router.patch("/certificates/{cert_id}/confirm-upload", status_code=200)
async def confirm_upload(
    cert_id: str,
    body: ConfirmUploadRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Called after the frontend successfully PUTs the file to S3.
    Saves the doc_url and marks upload_confirmed_at.
    """
    org_id = _get_org_id(supabase, user)

    # Verify cert belongs to this org
    cert_res = (
        supabase.table("fssai_certificates")
        .select("id, s3_key, upload_token, cert_type")
        .eq("id", cert_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not cert_res.data:
        raise HTTPException(404, "Certificate not found")

    cert = cert_res.data[0]

    # Security: the s3_key must match what we generated — prevents pointing at arbitrary S3 paths
    if cert.get("s3_key") and cert["s3_key"] != body.s3_key:
        raise HTTPException(400, "s3_key does not match the one issued for this certificate")

    storage = get_fssai_storage()
    doc_url = storage.public_url(body.s3_key)
    now     = datetime.utcnow().isoformat()

    supabase.table("fssai_certificates").update({
        "s3_key":               body.s3_key,
        "doc_url":              doc_url,
        "upload_confirmed_at":  now,
        "updated_at":           now,
    }).eq("id", cert_id).execute()

    log_india_compliance_audit(
        supabase, "FSSAI_CERT_UPLOADED",
        "fssai_certificates", cert_id, org_id,
        law_reference=LAW_REF,
    )

    # Data localisation audit — every file upload must be logged
    guard = DataLocalizationGuard(settings, supabase=supabase)
    guard.log_file_upload(
        file_type      = "FSSAI_CERT",
        s3_key         = body.s3_key,
        s3_bucket      = getattr(settings, "AWS_S3_BUCKET", None),
        s3_region      = FSSAI_S3_REGION,
        content_type   = cert.get("cert_type"),
        candidate_id   = cert.get("candidate_id"),
        org_id         = org_id,
        uploader_type  = "RECRUITER",
        uploader_id    = user.get("sub"),
    )

    return {
        "confirmed":  True,
        "cert_id":    cert_id,
        "doc_url":    doc_url,
        "s3_key":     body.s3_key,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /certificates/{id}/download-url — Presigned download
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/certificates/{cert_id}/download-url")
async def get_download_url(
    cert_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Return a presigned GET URL valid for 1 hour (private bucket support)."""
    org_id = _get_org_id(supabase, user)

    cert_res = (
        supabase.table("fssai_certificates")
        .select("id, s3_key, upload_confirmed_at")
        .eq("id", cert_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not cert_res.data:
        raise HTTPException(404, "Certificate not found")

    cert = cert_res.data[0]
    if not cert.get("s3_key"):
        raise HTTPException(404, "No file uploaded for this certificate yet")

    storage = get_fssai_storage()
    return {
        "download_url": storage.generate_download_url(cert["s3_key"]),
        "expires_in":   3600,
        "sandbox":      storage._sandbox,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /worker/run — Manual trigger (admin / testing)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/worker/run", status_code=202)
async def trigger_expiry_worker(
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Manually trigger the FSSAI expiry check worker (useful for testing).
    Enqueues as a Celery task — returns job_id for status tracking.
    """
    _get_org_id(supabase, user)  # auth check

    try:
        from app.workers.fssai_expiry import check_fssai_expiry
        task = check_fssai_expiry.delay()
        return {
            "queued":   True,
            "job_id":   task.id,
            "message":  "FSSAI expiry worker enqueued",
        }
    except Exception as exc:
        # If Celery/Redis is not running, run synchronously as fallback
        logger.warning("Celery unavailable, running synchronously: %s", exc)
        from app.workers.fssai_expiry import scan_expiring_certs
        result = scan_expiring_certs(supabase)
        return {
            "queued":   False,
            "sync":     True,
            "result":   result,
            "message":  "Ran synchronously (Celery not available)",
        }
