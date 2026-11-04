"""
smart_recruitment.py — Smart Recruitment API for Indian hotel hiring.
Prefix: /api/v1/recruit

Public endpoints (no auth):
  POST /apply/otp/send        — send OTP to candidate's phone
  POST /apply/otp/verify      — verify OTP + create candidate
  GET  /apply/job/{job_id}    — public job detail for apply form
  POST /apply/qr-scan         — log a QR code scan

Protected endpoints (admin auth):
  POST   /jobs                — create job with bilingual JD
  GET    /jobs                — list jobs with filters
  GET    /jobs/{id}           — job detail
  PATCH  /jobs/{id}           — update job
  POST   /jobs/{id}/regenerate-jd — regenerate bilingual JD via AI
  POST   /jobs/{id}/qr-code   — generate/refresh QR code URL
  GET    /role-templates      — list all seeded role templates
  GET    /pipeline            — full pipeline (all jobs or filtered by job_id)
  PATCH  /candidates/{id}/stage — move candidate to new pipeline stage
  POST   /bulk-action         — bulk shortlist / reject / invite / stage
  GET    /candidates/{id}/profile — full candidate profile
  GET    /analytics/sources   — source breakdown
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.dependencies import SupabaseAdminClient, SupabaseClient
from app.core.config import settings
from app.core.security import get_current_user
from app.services.smart_recruitment_service import (
    CANDIDATE_SOURCES,
    PIPELINE_STAGES,
    bulk_action,
    build_apply_url,
    generate_jd_bilingual,
    generate_job_board_versions,
    get_pipeline,
    log_qr_scan,
    move_candidate_stage,
    send_apply_otp,
    check_apply_otp,
    verify_apply_otp,
)
from app.services.s3_service import S3Service

router  = APIRouter(tags=["Smart Recruitment"])
logger  = logging.getLogger(__name__)
CUser   = Annotated[dict, Depends(get_current_user)]


def _org(supabase, user: dict) -> str:
    res = supabase.table("users").select("org_id").eq("id", user["sub"]).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "User not found")
    return res.data[0]["org_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    title:               str = Field(..., min_length=2, max_length=255)
    property_id:         Optional[str] = None
    department_id:       Optional[str] = None
    role_template:       Optional[str] = None
    property_name:       Optional[str] = None
    department:          Optional[str] = None
    location_city:       Optional[str] = None
    location_state:      Optional[str] = None
    description:         Optional[str] = None
    required_qualifications: Optional[str] = None
    status:              str            = "draft"
    openings_count:      int            = Field(1, ge=1, le=10000)
    is_urgent:           bool           = False
    experience_min_years: int           = Field(0, ge=0, le=60)
    experience_max_years: Optional[int] = Field(None, ge=0, le=60)
    salary_min_inr:      Optional[int]  = Field(None, ge=0)
    salary_max_inr:      Optional[int]  = Field(None, ge=0)
    ctc_min_inr:         Optional[int]  = Field(None, ge=0)
    ctc_max_inr:         Optional[int]  = Field(None, ge=0)
    salary_period:       str = "MONTHLY"
    education_level:     Optional[str] = Field(None, max_length=50)
    required_skills:     List[str] = Field(default_factory=list, max_length=50)
    preferred_skills:    List[str] = Field(default_factory=list, max_length=50)
    required_languages:  List[str] = Field(default_factory=list, max_length=20)
    shift_requirements:  dict = Field(default_factory=dict)
    accommodation_provided: bool = False
    food_provided:       bool = False
    transportation_provided: bool = False
    urgency_level:       str = "NORMAL"
    hiring_manager_id:   Optional[str] = None
    recruiter_id:        Optional[str] = None
    generate_jd:         bool           = True   # auto-generate Hindi+English JD

    @field_validator("status")
    @classmethod
    def validate_initial_status(cls, value: str) -> str:
        value = value.lower()
        if value not in {"draft", "pending_approval"}:
            raise ValueError("New jobs must start as draft or pending_approval")
        return value

    @field_validator("salary_period")
    @classmethod
    def validate_salary_period(cls, value: str) -> str:
        value = value.upper()
        if value not in {"HOURLY", "DAILY", "MONTHLY", "ANNUAL"}:
            raise ValueError("Unsupported salary period")
        return value

    @field_validator("urgency_level")
    @classmethod
    def validate_urgency(cls, value: str) -> str:
        value = value.upper()
        if value not in {"NORMAL", "HIGH", "URGENT", "CRITICAL"}:
            raise ValueError("Unsupported urgency level")
        return value

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.salary_min_inr is not None and self.salary_max_inr is not None and self.salary_min_inr > self.salary_max_inr:
            raise ValueError("salary_min_inr cannot exceed salary_max_inr")
        if self.ctc_min_inr is not None and self.ctc_max_inr is not None and self.ctc_min_inr > self.ctc_max_inr:
            raise ValueError("ctc_min_inr cannot exceed ctc_max_inr")
        if self.experience_max_years is not None and self.experience_min_years > self.experience_max_years:
            raise ValueError("experience_min_years cannot exceed experience_max_years")
        return self


class UpdateJobRequest(BaseModel):
    title:               Optional[str]  = Field(None, min_length=2, max_length=255)
    is_urgent:           Optional[bool] = None
    openings_count:      Optional[int]  = Field(None, ge=1, le=10000)
    property_name:       Optional[str]  = None
    property_id:         Optional[str]  = None
    department_id:       Optional[str]  = None
    department:          Optional[str]  = None
    salary_min_inr:      Optional[int]  = Field(None, ge=0)
    salary_max_inr:      Optional[int]  = Field(None, ge=0)
    jd_english:          Optional[str]  = None
    jd_hindi:            Optional[str]  = None
    experience_min_years: Optional[int] = Field(None, ge=0, le=60)
    experience_max_years: Optional[int] = Field(None, ge=0, le=60)
    ctc_min_inr: Optional[int] = Field(None, ge=0)
    ctc_max_inr: Optional[int] = Field(None, ge=0)
    salary_period: Optional[str] = None
    education_level: Optional[str] = None
    required_skills: Optional[List[str]] = None
    preferred_skills: Optional[List[str]] = None
    required_languages: Optional[List[str]] = None
    shift_requirements: Optional[dict] = None
    accommodation_provided: Optional[bool] = None
    food_provided: Optional[bool] = None
    transportation_provided: Optional[bool] = None
    urgency_level: Optional[str] = None
    hiring_manager_id: Optional[str] = None
    recruiter_id: Optional[str] = None
    role_template: Optional[str] = None

    @field_validator("salary_period")
    @classmethod
    def validate_optional_salary_period(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.upper()
        if value not in {"HOURLY", "DAILY", "MONTHLY", "ANNUAL"}:
            raise ValueError("Unsupported salary period")
        return value

    @field_validator("urgency_level")
    @classmethod
    def validate_optional_urgency(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.upper()
        if value not in {"NORMAL", "HIGH", "URGENT", "CRITICAL"}:
            raise ValueError("Unsupported urgency level")
        return value


class ApprovalRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=2000)


class ApprovalDecision(BaseModel):
    decision: str
    notes: Optional[str] = Field(None, max_length=2000)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        value = value.upper()
        if value not in {"APPROVE", "REJECT"}:
            raise ValueError("decision must be APPROVE or REJECT")
        return value


class DuplicateJobRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    property_id: Optional[str] = None
    department_id: Optional[str] = None


class StageMoveRequest(BaseModel):
    new_stage:        str
    notes:            Optional[str] = None
    offer_salary_inr: Optional[int] = None
    rejection_reason: Optional[str] = None


class BulkActionRequest(BaseModel):
    candidate_ids:    List[str]
    action:           str          # shortlist | reject | invite | stage
    stage:            Optional[str] = None
    reason:           Optional[str] = None
    notes:            Optional[str] = None
    offer_salary:     Optional[int] = None
    job_id:           Optional[str] = None
    interview_date:   Optional[str] = None
    job_title:        Optional[str] = None
    property_name:    Optional[str] = None


class OtpSendRequest(BaseModel):
    phone:  str
    job_id: str
    org_id: str


class OtpVerifyRequest(BaseModel):
    phone:            str
    otp:              Optional[str] = None
    verification_token: Optional[str] = None
    job_id:           str
    org_id:           str
    # 5-field mobile form (Req 5)
    name:             str
    experience_years: int  = 0
    current_city:     str  = ""
    source:           str  = "other"
    source_detail:    Optional[str] = None
    via_qr:           bool = False
    distribution_token: Optional[str] = None
    completion_time_seconds: Optional[int] = Field(None, ge=0, le=86400)
    preferred_language: str = Field("hi", pattern="^(hi|en)$")
    low_bandwidth_mode: bool = False

    @model_validator(mode="after")
    def require_otp_or_token(self):
        if not self.otp and not self.verification_token:
            raise ValueError("OTP or verification token is required")
        return self


class OtpCheckRequest(BaseModel):
    phone: str
    otp: str = Field(..., pattern="^[0-9]{6}$")
    job_id: str
    org_id: str


class QrScanRequest(BaseModel):
    job_id: str
    org_id: str
    source: str = "qr_code"


def _first(result):
    data = getattr(result, "data", None) or []
    return data[0] if isinstance(data, list) and data else None


def _validate_job_links(supabase, user: dict, org_id: str, *, property_id=None, department_id=None,
                        role_template=None, hiring_manager_id=None, recruiter_id=None) -> dict:
    result = {}
    if property_id:
        from app.services.property_access_service import get_actor, require_property_access
        prop, _ = require_property_access(supabase, get_actor(supabase, user), property_id)
        result["property"] = prop
    if department_id:
        query = supabase.table("property_departments").select("id,name,property_id,org_id").eq("id", department_id).eq("org_id", org_id)
        if property_id:
            query = query.eq("property_id", property_id)
        department = _first(query.limit(1).execute())
        if not department:
            raise HTTPException(422, "Department does not belong to the selected property")
        result["department"] = department
        if not property_id and department.get("property_id"):
            from app.services.property_access_service import get_actor, require_property_access
            prop, _ = require_property_access(supabase, get_actor(supabase, user), department["property_id"])
            result["property"] = prop
    if role_template:
        role = _first(supabase.table("role_templates").select("id,role_key,display_name,department,required_skills").eq("role_key", role_template).limit(1).execute())
        if not role:
            raise HTTPException(422, "Unknown hospitality role template")
        result["role"] = role
    for field, user_id in (("hiring_manager", hiring_manager_id), ("recruiter", recruiter_id)):
        if user_id:
            linked_user = _first(supabase.table("users").select("id,org_id,role").eq("id", user_id).eq("org_id", org_id).limit(1).execute())
            if not linked_user:
                raise HTTPException(422, f"{field.replace('_', ' ').title()} is outside this hotel group")
            result[field] = linked_user
    return result


def _record_job_action(supabase, org_id: str, job_id: str, user_id: str, action: str,
                       to_status: str, from_status: Optional[str] = None, notes: Optional[str] = None):
    supabase.table("job_status_history").insert({
        "org_id": org_id, "job_id": job_id, "from_status": from_status,
        "to_status": to_status, "action": action, "notes": notes, "changed_by": user_id,
    }).execute()


# ─────────────────────────────────────────────────────────────────────────────
# Public — no auth
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/apply/otp/send")
async def send_otp(body: OtpSendRequest, supabase: SupabaseClient):
    """Send a 6-digit OTP to the candidate's phone for mobile apply."""
    result = send_apply_otp(supabase, body.phone, body.job_id, body.org_id)
    if not result.get("sent"):
        raise HTTPException(502, result.get("error", "OTP delivery failed"))
    return result


@router.post("/apply/otp/check")
async def check_otp(body: OtpCheckRequest, supabase: SupabaseClient):
    """Verify OTP before collecting application details."""
    result = check_apply_otp(supabase, body.phone, body.otp, body.job_id, body.org_id)
    if not result.get("verified"):
        raise HTTPException(400, result.get("error", "OTP verification failed"))
    return result


@router.post("/apply/otp/verify")
async def verify_otp(body: OtpVerifyRequest, supabase: SupabaseClient):
    """Verify OTP and create the candidate record (5-field form)."""
    form = {
        "name":             body.name,
        "experience_years": body.experience_years,
        "current_city":     body.current_city,
        "source":           body.source,
        "source_detail":    body.source_detail,
        "via_qr":           body.via_qr,
        "distribution_token": body.distribution_token,
        "verification_token": body.verification_token,
        "completion_time_seconds": body.completion_time_seconds,
        "preferred_language": body.preferred_language,
        "low_bandwidth_mode": body.low_bandwidth_mode,
    }
    result = verify_apply_otp(supabase, body.phone, body.otp, body.job_id, body.org_id, form)
    if not result.get("verified"):
        raise HTTPException(400, result.get("error", "OTP verification failed"))
    token = result.get("tracking_token")
    result["tracking_url"] = f"{settings.APP_BASE_URL}/track/{token}" if token else None
    return result


@router.get("/apply/job/{job_id}")
async def public_job_detail(job_id: str, supabase: SupabaseClient):
    """Public job detail for the mobile apply form — no auth required."""
    res = (
        supabase.table("jobs")
        .select(
            "id, title, property_name, department, location_city, location_state, "
            "jd_english, jd_hindi, salary_min_inr, salary_max_inr, "
            "ctc_min_inr, ctc_max_inr, salary_period, experience_min_years, "
            "experience_max_years, education_level, required_skills, preferred_skills, "
            "required_languages, shift_requirements, accommodation_provided, food_provided, "
            "transportation_provided, urgency_level, is_urgent, openings_count, status"
        )
        .eq("id", job_id)
        .eq("status", "open")
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "Job not found or no longer active")
    row = res.data[0]
    whatsapp_number = str(getattr(settings, "TWILIO_WHATSAPP_NUMBER", "") or "")
    whatsapp_number = whatsapp_number.replace("whatsapp:", "").replace("+", "")
    if whatsapp_number:
        from urllib.parse import quote
        message = quote(f"APPLY {job_id}")
        row["whatsapp_apply_url"] = f"https://wa.me/{whatsapp_number}?text={message}"
    return row


@router.post("/apply/documents/{tracking_token}")
async def upload_application_document(
    tracking_token: str,
    supabase: SupabaseAdminClient,
    application_id: str = Form(...),
    document_type: str = Form("RESUME"),
    file: UploadFile = File(...),
):
    """Optional post-submit upload authenticated by the candidate tracking token."""
    allowed_types = {"RESUME", "GOVERNMENT_ID", "CERTIFICATE", "OTHER"}
    document_type = document_type.upper()
    if document_type not in allowed_types:
        raise HTTPException(422, "Unsupported document type")
    allowed_mimes = {"application/pdf", "image/jpeg", "image/png",
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if file.content_type not in allowed_mimes:
        raise HTTPException(415, "Upload PDF, DOCX, JPG or PNG only")
    payload = await file.read()
    if not payload or len(payload) > 5 * 1024 * 1024:
        raise HTTPException(413, "File must be between 1 byte and 5 MB")
    candidate = (supabase.table("candidates").select("id,org_id").eq("tracking_token", tracking_token)
                 .limit(1).execute().data or [None])[0]
    if not candidate:
        raise HTTPException(404, "Invalid application tracking token")
    application = (supabase.table("applications").select("id").eq("id", application_id)
                   .eq("candidate_id", candidate["id"]).limit(1).execute().data or [None])[0]
    if not application:
        raise HTTPException(422, "Application does not belong to candidate")
    url = await S3Service().upload_resume(
        payload, file.filename or "document", file.content_type or "application/octet-stream",
        candidate_id=candidate["id"], org_id=candidate.get("org_id"), supabase=supabase,
    )
    try:
        result = supabase.rpc("register_candidate_application_document", {
            "p_tracking_token": tracking_token, "p_application_id": application_id,
            "p_document_type": document_type, "p_file_name": file.filename or "document",
            "p_file_url": url, "p_mime_type": file.content_type,
            "p_file_size_bytes": len(payload),
        }).execute()
    except Exception as exc:
        logger.warning("Candidate document registration failed: %s", exc)
        raise HTTPException(422, "Document could not be linked to this application")
    return {"uploaded": True, "document_id": getattr(result, "data", None), "file_url": url}


@router.post("/apply/qr-scan")
async def track_qr_scan(body: QrScanRequest, request: Request, supabase: SupabaseClient):
    """Log a QR code scan for analytics (public, called when QR link is opened)."""
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    log_qr_scan(supabase, body.job_id, body.org_id, body.source, ip, ua)
    return {"logged": True}


# ─────────────────────────────────────────────────────────────────────────────
# Role templates
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/role-templates")
async def list_role_templates(
    supabase:  SupabaseClient,
    user:      CUser,
    category:  Optional[str] = Query(None),
):
    """List seeded role templates with bilingual JDs. Use these to pre-fill job creation."""
    q = (
        supabase.table("role_templates")
        .select("*")
        .order("category")
        .order("display_name")
    )
    if category:
        q = q.eq("category", category)
    return q.execute().data or []


# ─────────────────────────────────────────────────────────────────────────────
# Job management (Req 1 + 2)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/jobs", status_code=201)
async def create_job(body: CreateJobRequest, request: Request, supabase: SupabaseClient, user: CUser):
    """
    Req 1: Create job per property, department, role.
    Req 2: Auto-generate bilingual JD (Hindi + English) from role template.
    Req 6: Generate QR apply URL.
    """
    org_id = _org(supabase, user)
    now    = datetime.utcnow().isoformat()

    property_id = body.property_id or request.headers.get("x-property-id")
    links = _validate_job_links(
        supabase, user, org_id, property_id=property_id, department_id=body.department_id,
        role_template=body.role_template, hiring_manager_id=body.hiring_manager_id,
        recruiter_id=body.recruiter_id,
    )
    property_row = links.get("property")
    if not property_id and property_row:
        property_id = property_row.get("id")

    # Determine role display name
    role_display = body.title
    if body.role_template:
        tmpl = (
            supabase.table("role_templates")
            .select("display_name, jd_english, jd_hindi")
            .eq("role_key", body.role_template)
            .limit(1)
            .execute()
        )
        if tmpl.data:
            role_display = tmpl.data[0]["display_name"]

    # Req 2: Generate bilingual JD
    jd_english = body.description or ""
    jd_hindi   = ""

    if body.generate_jd:
        from app.core.config import settings
        jd = generate_jd_bilingual(
            role_display  = role_display,
            property_name = body.property_name or (property_row or {}).get("name") or "our hotel",
            department    = body.department    or "our team",
            city          = body.location_city or "",
            salary_min    = body.salary_min_inr or 0,
            salary_max    = body.salary_max_inr or 0,
            experience_min= body.experience_min_years,
            requirements  = {
                "education": body.education_level, "skills": body.required_skills,
                "languages": body.required_languages, "shifts": body.shift_requirements,
                "accommodation_provided": body.accommodation_provided,
                "food_provided": body.food_provided,
                "transportation_provided": body.transportation_provided,
            },
        )
        jd_english = jd["english"] or jd_english
        jd_hindi   = jd["hindi"]

    payload = {
        "org_id":               org_id,
        "title":                body.title,
        "role_type":            body.role_template or "general",
        "description":          jd_english,
        "required_qualifications": body.required_qualifications,
        "status":               body.status,
        "positions_available":  body.openings_count,
        "property_id":          property_id,
        "department_id":        body.department_id,
        "property_name":        body.property_name or (property_row or {}).get("name"),
        "department":           body.department or (links.get("department") or {}).get("name"),
        "role_template":        body.role_template,
        "role_template_id":     (links.get("role") or {}).get("id"),
        "location_city":        body.location_city,
        "location_state":       body.location_state,
        "jd_english":           jd_english,
        "jd_hindi":             jd_hindi,
        "salary_min_inr":       body.salary_min_inr,
        "salary_max_inr":       body.salary_max_inr,
        "experience_min_years": body.experience_min_years,
        "experience_max_years": body.experience_max_years,
        "openings_count":       body.openings_count,
        "is_urgent":            body.is_urgent,
        "urgency_level":        "URGENT" if body.is_urgent and body.urgency_level == "NORMAL" else body.urgency_level,
        "ctc_min_inr":          body.ctc_min_inr,
        "ctc_max_inr":          body.ctc_max_inr,
        "salary_period":        body.salary_period,
        "education_level":      body.education_level,
        "required_skills":      body.required_skills or (links.get("role") or {}).get("required_skills") or [],
        "preferred_skills":     body.preferred_skills,
        "required_languages":   body.required_languages,
        "shift_requirements":   body.shift_requirements,
        "accommodation_provided": body.accommodation_provided,
        "food_provided":        body.food_provided,
        "transportation_provided": body.transportation_provided,
        "hiring_manager_id":    body.hiring_manager_id,
        "recruiter_id":         body.recruiter_id or user["sub"],
        "approval_status":      "PENDING_APPROVAL" if body.status == "pending_approval" else "DRAFT",
        "approval_requested_by": user["sub"] if body.status == "pending_approval" else None,
        "approval_requested_at": now if body.status == "pending_approval" else None,
        "source_stats":         {},
        "created_at":           now,
        "updated_at":           now,
    }

    res = supabase.table("jobs").insert(payload).execute()
    if not res.data:
        raise HTTPException(500, "Job creation failed")

    job = res.data[0]
    job_id = job["id"]

    # Req 6: Generate QR apply URL
    from app.core.config import settings
    base_url = settings.APP_BASE_URL
    qr_data  = build_apply_url(base_url, job_id, org_id)
    supabase.table("jobs").update({
        "apply_url": qr_data["apply_url"],
        "qr_url":    qr_data["qr_url"],
    }).eq("id", job_id).execute()

    job["apply_url"] = qr_data["apply_url"]
    job["qr_url"]    = qr_data["qr_url"]
    job["job_board_versions"] = generate_job_board_versions(job)
    supabase.table("jobs").update({"job_board_versions": job["job_board_versions"]}).eq("id", job_id).execute()
    _record_job_action(supabase, org_id, job_id, user["sub"], "CREATE", body.status)
    return job


@router.post("/jobs/preview-jd")
async def preview_job_jd(body: CreateJobRequest, request: Request, supabase: SupabaseClient, user: CUser):
    """Generate bilingual preview without creating a draft job."""
    org_id = _org(supabase, user)
    property_id = body.property_id or request.headers.get("x-property-id")
    links = _validate_job_links(
        supabase, user, org_id, property_id=property_id, department_id=body.department_id,
        role_template=body.role_template, hiring_manager_id=body.hiring_manager_id,
        recruiter_id=body.recruiter_id,
    )
    return generate_jd_bilingual(
        role_display=body.title,
        property_name=body.property_name or (links.get("property") or {}).get("name") or "our hotel",
        department=body.department or (links.get("department") or {}).get("name") or "our team",
        city=body.location_city or "", salary_min=body.salary_min_inr or 0,
        salary_max=body.salary_max_inr or 0, experience_min=body.experience_min_years,
        requirements={
            "education": body.education_level, "skills": body.required_skills,
            "languages": body.required_languages, "shifts": body.shift_requirements,
            "accommodation_provided": body.accommodation_provided,
            "food_provided": body.food_provided,
            "transportation_provided": body.transportation_provided,
        },
    )


@router.get("/jobs")
async def list_jobs(
    supabase:   SupabaseClient,
    user:       CUser,
    status:     Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    property_n: Optional[str] = Query(None, alias="property"),
    is_urgent:  Optional[bool] = Query(None),
    limit:      int            = Query(50, ge=1, le=200),
):
    """List jobs with optional filters. Returns jobs with pipeline counts."""
    org_id = _org(supabase, user)
    q = (
        supabase.table("jobs")
        .select(
            "id, title, role_template, property_name, department, "
            "location_city, location_state, status, is_urgent, openings_count, "
            "salary_min_inr, salary_max_inr, experience_min_years, "
            "approval_status, hiring_manager_id, recruiter_id, urgency_level, "
            "source_stats, apply_url, qr_url, created_at"
        )
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        q = q.eq("status", status)
    if department:
        q = q.eq("department", department)
    if property_n:
        q = q.eq("property_name", property_n)
    if is_urgent is not None:
        q = q.eq("is_urgent", is_urgent)

    jobs = q.execute().data or []

    # Attach pipeline counts per job
    for job in jobs:
        try:
            cnt = (
                supabase.table("candidates")
                .select("pipeline_stage", count="exact")
                .eq("applied_job_id", job["id"])
                .execute()
            )
            # Group counts
            stage_counts = {}
            for row in (cnt.data or []):
                s = row.get("pipeline_stage", "applied")
                stage_counts[s] = stage_counts.get(s, 0) + 1
            job["pipeline_counts"] = stage_counts
            job["total_applicants"] = sum(stage_counts.values())
        except Exception:
            job["pipeline_counts"] = {}
            job["total_applicants"] = 0

    return jobs


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, supabase: SupabaseClient, user: CUser):
    """Job detail including full JD, QR URL, and pipeline summary."""
    org_id = _org(supabase, user)
    res    = (
        supabase.table("jobs").select("*")
        .eq("id", job_id).eq("org_id", org_id)
        .limit(1).execute()
    )
    if not res.data:
        raise HTTPException(404, "Job not found")
    return res.data[0]


@router.patch("/jobs/{job_id}")
async def update_job(job_id: str, body: UpdateJobRequest, supabase: SupabaseClient, user: CUser):
    """Update job fields."""
    org_id  = _org(supabase, user)
    existing = _first(supabase.table("jobs").select("*").eq("id", job_id).eq("org_id", org_id).limit(1).execute())
    if not existing:
        raise HTTPException(404, "Job not found")
    property_id = body.property_id if body.property_id is not None else existing.get("property_id")
    selected_department_id = body.department_id
    if body.property_id is not None and body.department_id is None:
        # A department is property-owned. Do not silently retain one from another property.
        selected_department_id = None
    links = _validate_job_links(
        supabase, user, org_id, property_id=property_id,
        department_id=selected_department_id, role_template=body.role_template,
        hiring_manager_id=body.hiring_manager_id, recruiter_id=body.recruiter_id,
    )
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(400, "No fields to update")
    merged = {**existing, **payload}
    for low, high, label in (
        (merged.get("salary_min_inr"), merged.get("salary_max_inr"), "salary"),
        (merged.get("ctc_min_inr"), merged.get("ctc_max_inr"), "CTC"),
        (merged.get("experience_min_years"), merged.get("experience_max_years"), "experience"),
    ):
        if low is not None and high is not None and low > high:
            raise HTTPException(422, f"Minimum {label} cannot exceed maximum {label}")
    if body.openings_count is not None:
        payload["positions_available"] = body.openings_count
    if body.is_urgent is not None and body.urgency_level is None:
        payload["urgency_level"] = "URGENT" if body.is_urgent else "NORMAL"
    if body.urgency_level is not None:
        urgency = body.urgency_level.upper()
        if urgency not in {"NORMAL", "HIGH", "URGENT", "CRITICAL"}:
            raise HTTPException(422, "Unsupported urgency level")
        payload["urgency_level"] = urgency
        payload["is_urgent"] = urgency in {"URGENT", "CRITICAL"}
    if body.role_template:
        payload["role_template_id"] = (links.get("role") or {}).get("id")
    if body.property_id:
        payload["property_name"] = (links.get("property") or {}).get("name")
        if body.department_id is None:
            payload["department_id"] = None
            payload["department"] = None
    if body.department_id:
        payload["department"] = (links.get("department") or {}).get("name")
    payload["updated_at"] = datetime.utcnow().isoformat()
    supabase.table("jobs").update(payload).eq("id", job_id).eq("org_id", org_id).execute()
    _record_job_action(supabase, org_id, job_id, user["sub"], "EDIT", existing.get("status", "draft"), existing.get("status"))
    return {"updated": True}


@router.post("/jobs/{job_id}/regenerate-jd")
async def regenerate_jd(job_id: str, supabase: SupabaseClient, user: CUser):
    """Req 2: Re-generate bilingual JD via Claude AI."""
    org_id = _org(supabase, user)
    res    = (
        supabase.table("jobs").select("*")
        .eq("id", job_id).eq("org_id", org_id)
        .limit(1).execute()
    )
    if not res.data:
        raise HTTPException(404, "Job not found")

    job = res.data[0]
    jd  = generate_jd_bilingual(
        role_display  = job.get("title", "Staff"),
        property_name = job.get("property_name") or "our hotel",
        department    = job.get("department")    or "our team",
        city          = job.get("location_city") or "",
        salary_min    = job.get("salary_min_inr") or 0,
        salary_max    = job.get("salary_max_inr") or 0,
        experience_min= job.get("experience_min_years") or 0,
        requirements={
            "education": job.get("education_level"), "skills": job.get("required_skills"),
            "languages": job.get("required_languages"), "shifts": job.get("shift_requirements"),
            "accommodation_provided": job.get("accommodation_provided"),
            "food_provided": job.get("food_provided"),
            "transportation_provided": job.get("transportation_provided"),
        },
    )
    supabase.table("jobs").update({
        "jd_english": jd["english"],
        "jd_hindi":   jd["hindi"],
        "job_board_versions": generate_job_board_versions({**job, "jd_english": jd["english"], "jd_hindi": jd["hindi"]}),
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", job_id).execute()

    return {"regenerated": True, **jd}


@router.post("/jobs/{job_id}/submit-approval")
async def submit_job_approval(job_id: str, body: ApprovalRequest, supabase: SupabaseClient, user: CUser):
    org_id = _org(supabase, user)
    job = _first(supabase.table("jobs").select("*").eq("id", job_id).eq("org_id", org_id).limit(1).execute())
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("approval_status") not in {"DRAFT", "REJECTED"}:
        raise HTTPException(409, "Only draft or rejected jobs can be submitted")
    now = datetime.utcnow().isoformat()
    supabase.table("jobs").update({
        "status": "pending_approval", "approval_status": "PENDING_APPROVAL",
        "approval_requested_by": user["sub"], "approval_requested_at": now,
        "approval_notes": body.notes, "updated_at": now,
    }).eq("id", job_id).eq("org_id", org_id).execute()
    _record_job_action(supabase, org_id, job_id, user["sub"], "SUBMIT_APPROVAL", "pending_approval", job.get("status"), body.notes)
    return {"approval_status": "PENDING_APPROVAL", "status": "pending_approval"}


@router.post("/jobs/{job_id}/approval")
async def decide_job_approval(job_id: str, body: ApprovalDecision, supabase: SupabaseClient, user: CUser):
    from app.services.rbac_service import build_access_context
    context = build_access_context(supabase, user)
    if context.role not in {"OWNER", "GROUP_ADMIN_HR", "GENERAL_MANAGER", "HR_MANAGER"}:
        raise HTTPException(403, "Job approval requires HR Manager or management access")
    org_id = context.org_id
    job = _first(supabase.table("jobs").select("*").eq("id", job_id).eq("org_id", org_id).limit(1).execute())
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("approval_status") != "PENDING_APPROVAL":
        raise HTTPException(409, "Job is not pending approval")
    approved = body.decision == "APPROVE"
    now = datetime.utcnow().isoformat()
    values = {
        "status": "open" if approved else "draft",
        "approval_status": "APPROVED" if approved else "REJECTED",
        "approved_by": user["sub"] if approved else None,
        "approved_at": now if approved else None,
        "approval_notes": body.notes, "updated_at": now,
    }
    supabase.table("jobs").update(values).eq("id", job_id).eq("org_id", org_id).execute()
    _record_job_action(supabase, org_id, job_id, user["sub"], body.decision, values["status"], job.get("status"), body.notes)
    return values


@router.post("/jobs/{job_id}/close")
async def close_job(job_id: str, body: ApprovalRequest, supabase: SupabaseClient, user: CUser):
    org_id = _org(supabase, user)
    job = _first(supabase.table("jobs").select("id,status").eq("id", job_id).eq("org_id", org_id).limit(1).execute())
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") == "closed":
        raise HTTPException(409, "Job is already closed")
    now = datetime.utcnow().isoformat()
    supabase.table("jobs").update({"status": "closed", "closed_at": now, "closed_by": user["sub"], "updated_at": now}).eq("id", job_id).execute()
    _record_job_action(supabase, org_id, job_id, user["sub"], "CLOSE", "closed", job.get("status"), body.notes)
    return {"status": "closed", "closed_at": now}


@router.post("/jobs/{job_id}/reopen")
async def reopen_job(job_id: str, supabase: SupabaseClient, user: CUser):
    org_id = _org(supabase, user)
    job = _first(supabase.table("jobs").select("id,status,approval_status").eq("id", job_id).eq("org_id", org_id).limit(1).execute())
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "closed":
        raise HTTPException(409, "Only closed jobs can be reopened")
    if job.get("approval_status") != "APPROVED":
        raise HTTPException(409, "Job must be approved before reopening")
    now = datetime.utcnow().isoformat()
    supabase.table("jobs").update({"status": "open", "closed_at": None, "closed_by": None, "updated_at": now}).eq("id", job_id).execute()
    _record_job_action(supabase, org_id, job_id, user["sub"], "REOPEN", "open", "closed")
    return {"status": "open"}


@router.post("/jobs/{job_id}/duplicate", status_code=201)
async def duplicate_job(job_id: str, body: DuplicateJobRequest, request: Request, supabase: SupabaseClient, user: CUser):
    org_id = _org(supabase, user)
    source = _first(supabase.table("jobs").select("*").eq("id", job_id).eq("org_id", org_id).limit(1).execute())
    if not source:
        raise HTTPException(404, "Job not found")
    property_id = body.property_id or source.get("property_id")
    department_id = body.department_id or source.get("department_id")
    _validate_job_links(supabase, user, org_id, property_id=property_id, department_id=department_id)
    excluded = {"id", "created_at", "updated_at", "approved_by", "approved_at", "closed_by", "closed_at", "approval_requested_by", "approval_requested_at", "apply_url", "qr_url"}
    payload = {key: value for key, value in source.items() if key not in excluded}
    payload.update({
        "title": body.title or f"{source['title']} (Copy)", "property_id": property_id,
        "department_id": department_id, "status": "draft", "approval_status": "DRAFT",
        "approval_notes": None, "duplicated_from_job_id": job_id,
        "created_at": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat(),
    })
    created = _first(supabase.table("jobs").insert(payload).execute())
    if not created:
        raise HTTPException(500, "Job duplication failed")
    from app.core.config import settings
    qr = build_apply_url(settings.APP_BASE_URL, created["id"], org_id)
    supabase.table("jobs").update(qr).eq("id", created["id"]).execute()
    _record_job_action(supabase, org_id, created["id"], user["sub"], "DUPLICATE", "draft", notes=f"Copied from {job_id}")
    return {**created, **qr}


@router.post("/jobs/{job_id}/job-board-versions")
async def create_job_board_versions(job_id: str, supabase: SupabaseClient, user: CUser):
    org_id = _org(supabase, user)
    job = _first(supabase.table("jobs").select("*").eq("id", job_id).eq("org_id", org_id).limit(1).execute())
    if not job:
        raise HTTPException(404, "Job not found")
    versions = generate_job_board_versions(job)
    supabase.table("jobs").update({"job_board_versions": versions, "updated_at": datetime.utcnow().isoformat()}).eq("id", job_id).execute()
    return {"job_id": job_id, "versions": versions}


@router.post("/jobs/{job_id}/qr-code")
async def refresh_qr_code(job_id: str, supabase: SupabaseClient, user: CUser):
    """Req 6: Generate or refresh the QR code + apply URL for a job."""
    org_id   = _org(supabase, user)
    from app.core.config import settings
    qr_data  = build_apply_url(settings.APP_BASE_URL, job_id, org_id)
    supabase.table("jobs").update({
        "apply_url": qr_data["apply_url"],
        "qr_url":    qr_data["qr_url"],
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", job_id).eq("org_id", org_id).execute()
    return qr_data


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Kanban (Req 7)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/pipeline")
async def pipeline(
    supabase: SupabaseClient,
    user:     CUser,
    job_id:   Optional[str] = Query(None),
):
    """
    Req 7: Return full Kanban pipeline grouped by stage.
    If job_id given, filter to that job; otherwise returns all org candidates.
    """
    org_id = _org(supabase, user)
    return get_pipeline(supabase, org_id, job_id)


# ─────────────────────────────────────────────────────────────────────────────
# Candidate stage moves (Req 7 + 8)
# ─────────────────────────────────────────────────────────────────────────────

@router.patch("/candidates/{candidate_id}/stage")
async def update_candidate_stage(
    candidate_id: str,
    body:         StageMoveRequest,
    supabase:     SupabaseClient,
    user:         CUser,
):
    """Move a candidate to a new pipeline stage."""
    org_id = _org(supabase, user)
    result = move_candidate_stage(
        supabase, org_id, candidate_id,
        new_stage        = body.new_stage,
        notes            = body.notes,
        offer_salary     = body.offer_salary_inr,
        rejection_reason = body.rejection_reason,
    )
    try:
        application = _first(supabase.table("applications").select("*").eq("candidate_id", candidate_id)
            .eq("org_id", org_id).order("created_at", desc=True).limit(1).execute())
        if application:
            previous = (application.get("status") or "APPLIED").lower()
            supabase.table("applications").update({"status": body.new_stage.upper(),
                "stage_updated_at": datetime.utcnow().isoformat()}).eq("id", application["id"]).execute()
            supabase.table("application_stage_history").insert({"org_id": org_id,
                "application_id": application["id"], "candidate_id": candidate_id,
                "job_id": application.get("job_id"), "from_stage": previous,
                "to_stage": body.new_stage, "notes": body.notes, "changed_by": user["sub"]}).execute()
    except Exception as exc:
        logger.warning("application stage sync failed for candidate %s: %s", candidate_id, exc)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Bulk actions (Req 8)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/bulk-action")
async def perform_bulk_action(body: BulkActionRequest, supabase: SupabaseClient, user: CUser):
    """
    Req 8: Bulk shortlist, reject, WhatsApp invite, or stage update.
    action: shortlist | reject | invite | stage
    """
    org_id = _org(supabase, user)
    if body.action not in ("shortlist", "reject", "invite", "stage"):
        raise HTTPException(400, f"Unknown action: {body.action}")

    return bulk_action(
        supabase, org_id,
        candidate_ids = body.candidate_ids,
        action        = body.action,
        data          = {
            "stage":          body.stage,
            "reason":         body.reason,
            "notes":          body.notes,
            "offer_salary":   body.offer_salary,
            "job_id":         body.job_id,
            "interview_date": body.interview_date,
            "job_title":      body.job_title,
            "property_name":  body.property_name,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Candidate profile (Req 9)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/candidates/{candidate_id}/profile")
async def candidate_profile(candidate_id: str, supabase: SupabaseClient, user: CUser):
    """
    Req 9: Full candidate profile — source, resume, WhatsApp history,
    interview status, timeline.
    """
    org_id = _org(supabase, user)

    # Core record
    c_res = (
        supabase.table("candidates").select("*")
        .eq("id", candidate_id).eq("org_id", org_id)
        .limit(1).execute()
    )
    if not c_res.data:
        raise HTTPException(404, "Candidate not found")
    cand = c_res.data[0]

    # Job they applied for
    job = None
    if cand.get("applied_job_id"):
        j_res = (
            supabase.table("jobs")
            .select("id, title, property_name, department, location_city")
            .eq("id", cand["applied_job_id"]).limit(1).execute()
        )
        job = (j_res.data or [None])[0]

    # WhatsApp message history (if employee record exists)
    whatsapp = []
    if cand.get("phone"):
        wm_res = (
            supabase.table("whatsapp_messages")
            .select("direction, body, command, command_status, created_at")
            .eq("phone", cand["phone"])
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        whatsapp = wm_res.data or []

    # Build timeline
    timeline = []
    ts_map = [
        ("applied",   cand.get("created_at"),      "Application received"),
        ("screened",  cand.get("screened_at"),      "Screened / shortlisted"),
        ("interview", cand.get("interview_at"),     "Interview scheduled"),
        ("offer",     cand.get("offered_at"),       "Offer extended"),
        ("hired",     cand.get("hired_at"),         "Hired 🎉"),
    ]
    for stage, ts, label in ts_map:
        if ts:
            timeline.append({"stage": stage, "timestamp": ts, "label": label})

    return {
        "candidate":       cand,
        "job":             job,
        "whatsapp_history":whatsapp,
        "timeline":        timeline,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/analytics/sources")
async def source_analytics(
    supabase:  SupabaseClient,
    user:      CUser,
    job_id:    Optional[str] = Query(None),
):
    """Req 3: Source breakdown — which portal drives the most applicants."""
    org_id = _org(supabase, user)
    q      = (
        supabase.table("candidates")
        .select("source", count="exact")
        .eq("org_id", org_id)
    )
    if job_id:
        q = q.eq("applied_job_id", job_id)
    res = q.execute()

    from collections import Counter
    counts = Counter(c.get("source") or "other" for c in (res.data or []))
    total  = sum(counts.values())

    return {
        "total":   total,
        "sources": [
            {
                "source": src,
                "count":  cnt,
                "pct":    round(cnt / total * 100, 1) if total else 0,
            }
            for src, cnt in counts.most_common()
        ],
    }
