"""Unified hospitality employee certification management."""

from __future__ import annotations

from datetime import datetime, date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.certification_service import get_role_compliance, get_unified_employee_certifications
from app.services.rbac_service import authorize, build_access_context
from app.services.s3_service import S3Service
from app.services.data_localization import DataLocalizationGuard
from app.core.config import settings

router = APIRouter(tags=["Certifications"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


class RequirementCreate(BaseModel):
    role_title: str = Field(min_length=1, max_length=255)
    certification_code: str
    job_role_id: Optional[str] = None
    property_id: Optional[str] = None
    department_id: Optional[str] = None
    is_mandatory: bool = True
    required_before_start: bool = False
    validity_months_override: Optional[int] = Field(None, ge=1, le=120)
    grace_days: int = Field(0, ge=0, le=365)


class AlertSettingsUpdate(BaseModel):
    reminder_days: list[int] = Field(default_factory=lambda: [90, 60, 30, 7, 0])
    notify_employee: bool = True
    notify_manager: bool = True
    preferred_channel: str = "SMS"

    @field_validator("reminder_days")
    @classmethod
    def validate_days(cls, value: list[int]) -> list[int]:
        clean = sorted(set(value), reverse=True)
        if not clean or any(day < 0 or day > 365 for day in clean):
            raise ValueError("reminder_days must contain unique values from 0 to 365")
        return clean

    @field_validator("preferred_channel")
    @classmethod
    def validate_channel(cls, value: str) -> str:
        value = value.upper()
        if value not in {"SMS", "WHATSAPP", "BOTH"}:
            raise ValueError("preferred_channel must be SMS, WHATSAPP or BOTH")
        return value


class CertificateCreate(BaseModel):
    certification_code: str
    certificate_number: Optional[str] = Field(None, max_length=100)
    issuing_authority: Optional[str] = Field(None, max_length=500)
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    filename: Optional[str] = None
    content_type: str = "application/pdf"
    renewal_of: Optional[str] = None

    @field_validator("expiry_date")
    @classmethod
    def validate_expiry(cls, value: Optional[str]) -> Optional[str]:
        if value: date.fromisoformat(value)
        return value


class ConfirmUpload(BaseModel):
    storage_key: str
    file_name: str
    mime_type: str


class VerifyCertificate(BaseModel):
    status: str
    notes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = value.upper()
        if value not in {"VERIFIED", "REJECTED"}:
            raise ValueError("status must be VERIFIED or REJECTED")
        return value


def _rows(result):
    return getattr(result, "data", None) or []


def _employee(supabase, org_id: str, employee_id: str) -> dict:
    rows = _rows(supabase.table("users").select(
        "id,org_id,email,phone,full_name,job_title,active_property_id,department_id,manager_id"
    ).eq("id", employee_id).eq("org_id", org_id).limit(1).execute())
    if not rows: raise HTTPException(404, "Employee not found")
    return rows[0]


def _type(supabase, code: str) -> dict:
    rows = _rows(supabase.table("certification_types").select("*")
                 .eq("code", code.upper()).eq("is_active", True).limit(1).execute())
    if not rows: raise HTTPException(422, "Unknown certification code")
    return rows[0]


def _audit(supabase, org_id: str, actor_id: str, action: str, entity_id: str, metadata: dict | None = None):
    supabase.table("india_compliance_audit_logs").insert({
        "org_id": org_id, "actor_type": "RECRUITER", "actor_id": actor_id,
        "action": action, "entity_type": "employee_certification", "entity_id": entity_id,
        "law_reference": "Applicable hospitality safety/employment requirement",
        "metadata": metadata or {},
    }).execute()


@router.get("/types")
async def list_types(supabase: SupabaseClient, user: CurrentUser):
    build_access_context(supabase, user)
    return _rows(supabase.table("certification_types").select("*").eq("is_active", True).order("category").execute())


@router.get("/requirements")
async def list_requirements(
    supabase: SupabaseClient, user: CurrentUser,
    role_title: Optional[str] = Query(None), property_id: Optional[str] = Query(None),
):
    context = build_access_context(supabase, user); authorize(context, "compliance.read")
    q = supabase.table("role_certification_requirements").select("*,certification_types(code,name,category)").eq("org_id", context.org_id)
    if role_title: q = q.eq("role_title", role_title)
    if property_id: q = q.eq("property_id", property_id)
    return _rows(q.order("role_title").execute())


@router.post("/requirements", status_code=201)
async def create_requirement(body: RequirementCreate, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "compliance.manage", property_id=body.property_id)
    cert_type = _type(supabase, body.certification_code)
    payload = {**body.model_dump(exclude={"certification_code"}), "org_id": context.org_id,
               "certification_type_id": cert_type["id"], "created_by": context.user_id}
    try:
        rows = _rows(supabase.table("role_certification_requirements").insert(payload).execute())
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            raise HTTPException(409, "This certification is already required for the role and scope")
        raise
    return rows[0] if rows else payload


@router.get("/alert-settings")
async def get_alert_settings(supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "compliance.read")
    rows = _rows(supabase.table("certification_alert_settings").select("*").eq("org_id", context.org_id).limit(1).execute())
    return rows[0] if rows else {"org_id": context.org_id, "reminder_days": [90,60,30,7,0],
                                 "notify_employee": True, "notify_manager": True, "preferred_channel": "SMS"}


@router.put("/alert-settings")
async def update_alert_settings(body: AlertSettingsUpdate, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "compliance.manage")
    payload = {"org_id": context.org_id, **body.model_dump(), "updated_by": context.user_id,
               "updated_at": datetime.utcnow().isoformat()}
    rows = _rows(supabase.table("certification_alert_settings").upsert(payload, on_conflict="org_id").execute())
    return rows[0] if rows else payload


@router.post("/employees/{employee_id}", status_code=201)
async def create_certificate(employee_id: str, body: CertificateCreate, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "compliance.manage")
    employee = _employee(supabase, context.org_id, employee_id); cert_type = _type(supabase, body.certification_code)
    if cert_type.get("is_fssai_managed"):
        raise HTTPException(409, "Use /api/v1/fssai/certificates for this FSSAI-managed type")
    candidate_rows = _rows(supabase.table("candidates").select("id").eq("org_id", context.org_id)
                           .eq("user_id", employee_id).limit(1).execute())
    payload = {"org_id": context.org_id, "employee_id": employee_id,
               "candidate_id": candidate_rows[0]["id"] if candidate_rows else None,
               "certification_type_id": cert_type["id"], "certificate_number": body.certificate_number,
               "issuing_authority": body.issuing_authority or cert_type.get("issuing_authority"),
               "issue_date": body.issue_date, "expiry_date": body.expiry_date,
               "renewal_of": body.renewal_of, "created_by": context.user_id,
               "status": "PENDING_VERIFICATION"}
    rows = _rows(supabase.table("employee_certifications").insert(payload).execute())
    if not rows: raise HTTPException(500, "Failed to create certificate")
    cert = rows[0]
    if body.renewal_of:
        supabase.table("employee_certifications").update({"status":"RENEWED","renewed_by":cert["id"]})\
            .eq("id", body.renewal_of).eq("org_id", context.org_id).eq("employee_id", employee_id).execute()
    upload = None
    if body.filename:
        upload = S3Service().generate_employee_certificate_upload_url(
            context.org_id, employee_id, body.filename, body.content_type)
        supabase.table("employee_certifications").update({"storage_key": upload["storage_key"],
            "encryption_mode": "SSE-KMS" if upload["upload_headers"]["x-amz-server-side-encryption"] == "aws:kms" else "SSE-S3"})\
            .eq("id", cert["id"]).eq("org_id", context.org_id).execute()
    _audit(supabase, context.org_id, context.user_id, "CERTIFICATE_CREATED", cert["id"], {"code": body.certification_code})
    return {**cert, **({"upload": upload} if upload else {})}


@router.patch("/{certificate_id}/confirm-upload")
async def confirm_certificate_upload(certificate_id: str, body: ConfirmUpload, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "compliance.manage")
    rows = _rows(supabase.table("employee_certifications").select("id,employee_id,storage_key")
                 .eq("id", certificate_id).eq("org_id", context.org_id).limit(1).execute())
    if not rows: raise HTTPException(404, "Certificate not found")
    if rows[0].get("storage_key") != body.storage_key: raise HTTPException(400, "storage_key mismatch")
    update = {"file_name": body.file_name, "mime_type": body.mime_type,
              "upload_confirmed_at": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat()}
    supabase.table("employee_certifications").update(update).eq("id", certificate_id).eq("org_id", context.org_id).execute()
    DataLocalizationGuard(settings, supabase=supabase).log_file_upload(
        file_type="EMPLOYEE_CERTIFICATE", s3_key=body.storage_key,
        s3_region="ap-south-1", content_type=body.mime_type,
        org_id=context.org_id, uploader_type="RECRUITER", uploader_id=context.user_id,
        notes=f"Certificate {certificate_id} upload confirmed",
    )
    _audit(supabase, context.org_id, context.user_id, "CERTIFICATE_UPLOAD_CONFIRMED", certificate_id)
    return {"confirmed": True, "certificate_id": certificate_id}


@router.get("/{certificate_id}/download-url")
async def certificate_download_url(certificate_id: str, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    rows = _rows(supabase.table("employee_certifications").select("id,employee_id,storage_key")
                 .eq("id", certificate_id).eq("org_id", context.org_id).limit(1).execute())
    if not rows: raise HTTPException(404, "Certificate not found")
    if rows[0]["employee_id"] != context.user_id: authorize(context, "compliance.read")
    if not rows[0].get("storage_key"): raise HTTPException(404, "Certificate document not uploaded")
    return S3Service().generate_private_download_url(rows[0]["storage_key"])


@router.patch("/{certificate_id}/verify")
async def verify_certificate(certificate_id: str, body: VerifyCertificate, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "compliance.manage")
    update = {"status": body.status, "verification_notes": body.notes,
              "verified_by": context.user_id, "verified_at": datetime.utcnow().isoformat(),
              "updated_at": datetime.utcnow().isoformat()}
    rows = _rows(supabase.table("employee_certifications").update(update)
                 .eq("id", certificate_id).eq("org_id", context.org_id).execute())
    if not rows: raise HTTPException(404, "Certificate not found")
    _audit(supabase, context.org_id, context.user_id, f"CERTIFICATE_{body.status}", certificate_id)
    return rows[0]


@router.get("/employees/{employee_id}")
async def list_employee_certificates(employee_id: str, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    if employee_id != context.user_id: authorize(context, "compliance.read")
    employee = _employee(supabase, context.org_id, employee_id)
    return get_unified_employee_certifications(supabase, context.org_id, employee)


@router.get("/employees/{employee_id}/compliance")
async def employee_role_compliance(employee_id: str, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    if employee_id != context.user_id: authorize(context, "compliance.read")
    return get_role_compliance(supabase, context.org_id, _employee(supabase, context.org_id, employee_id))


@router.get("/expiring")
async def expiring_certificates(supabase: SupabaseClient, user: CurrentUser,
                                days: int = Query(90, ge=0, le=365)):
    context = build_access_context(supabase, user); authorize(context, "compliance.read")
    cutoff = date.today().toordinal() + days
    end = date.fromordinal(cutoff).isoformat()
    general = _rows(supabase.table("employee_certifications").select("*,certification_types(code,name)")
                    .eq("org_id", context.org_id).in_("status", ["VERIFIED","RENEWAL_DUE"])
                    .lte("expiry_date", end).order("expiry_date").execute())
    fssai = _rows(supabase.table("fssai_certificates").select("*").eq("org_id", context.org_id)
                  .eq("status", "ACTIVE").lte("expiry_date", end).order("expiry_date").execute())
    return {"employee_certifications": general, "fssai_certifications": fssai}
