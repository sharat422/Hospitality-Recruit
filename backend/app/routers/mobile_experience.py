"""
Mobile Experience Router — Feature 04.
Covers: Mobile Applications, Video Interviews, QR Codes, Translations.
"""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List, Annotated
from datetime import datetime
import uuid
import logging
import os
from fastapi import Depends

from app.core.dependencies import SupabaseClient, SupabaseAdminClient
from app.core.security import get_current_user
from app.core.config import settings
from app.services.qr_service import generate_short_code, generate_qr_image_base64
from app.services.translation_service import translate_text
from app.services.referral_lifecycle_service import attribute_application

CurrentUser = Annotated[dict, Depends(get_current_user)]

router = APIRouter(tags=["Mobile Experience"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class StartApplicationRequest(BaseModel):
    job_role_id: str
    source: Optional[str] = "DIRECT"
    source_ref: Optional[str] = None


class SaveProgressRequest(BaseModel):
    form_data: dict


class SubmitApplicationRequest(BaseModel):
    form_data: dict
    completion_time_seconds: Optional[int] = None


class CreateVideoInterviewRequest(BaseModel):
    application_id: Optional[str] = None
    candidate_id: str
    job_role_id: str
    interview_type: Optional[str] = "VIDEO"
    question_ids: Optional[List[str]] = None


class RateInterviewRequest(BaseModel):
    rating: int
    notes: Optional[str] = None


class GenerateQRRequest(BaseModel):
    type: str  # JOB_APPLY | REFERRAL | CAMPAIGN
    job_role_id: Optional[str] = None
    campaign_id: Optional[str] = None
    employee_id: Optional[str] = None


class TranslateJobRoleRequest(BaseModel):
    target_language: str


class LanguagePreferenceRequest(BaseModel):
    language_code: str


# ---------------------------------------------------------------------------
# Application Endpoints
# ---------------------------------------------------------------------------

TIER_FIELDS = {
    1: {
        "required_fields": ["full_name", "phone", "right_to_work", "start_availability"],
        "optional_fields": ["cv_url"],
    },
    2: {
        "required_fields": ["full_name", "phone", "right_to_work", "start_availability", "years_experience", "availability_shifts"],
        "optional_fields": ["cv_url", "salary_range"],
    },
    3: {
        "required_fields": ["full_name", "phone", "right_to_work", "start_availability", "years_experience", "availability_shifts", "cv_url", "current_employer", "linkedin_url"],
        "optional_fields": ["cover_note", "certifications", "salary_range"],
    },
}

SENIORITY_TIER = {
    "entry": 1,
    "junior": 1,
    "mid": 2,
    "intermediate": 2,
    "senior": 3,
    "lead": 3,
    "manager": 3,
    "director": 3,
}


@router.post("/applications/start")
async def start_application(
    body: StartApplicationRequest,
    supabase: SupabaseAdminClient,
):
    """PUBLIC: Start a new draft application for a job role."""
    # Fetch job role for tier determination
    role_resp = supabase.table("job_roles").select("*").eq("id", body.job_role_id).execute()
    if not role_resp.data:
        raise HTTPException(status_code=404, detail="Job role not found")

    role = role_resp.data[0]
    seniority = (role.get("seniority_level") or "entry").lower()
    tier = SENIORITY_TIER.get(seniority, 1)
    fields = TIER_FIELDS[tier]

    # Create draft application
    app_data = {
        "job_role_id": body.job_role_id,
        "org_id": role.get("org_id"),
        "property_id": role.get("property_id"),
        "source": body.source,
        "source_ref": body.source_ref,
        "status": "DRAFT",
        "applied_via": "MOBILE_WEB",
        "form_data": {},
    }

    insert_resp = supabase.table("applications").insert(app_data).execute()
    if not insert_resp.data:
        raise HTTPException(status_code=500, detail="Failed to create application")

    application = insert_resp.data[0]
    return {
        "application_id": application["id"],
        "tier": tier,
        "required_fields": fields["required_fields"],
        "optional_fields": fields["optional_fields"],
    }


@router.post("/applications/{application_id}/save-progress")
async def save_progress(
    application_id: str,
    body: SaveProgressRequest,
    supabase: SupabaseAdminClient,
):
    """PUBLIC: Auto-save application form progress."""
    resp = supabase.table("applications").update({
        "form_data": body.form_data,
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", application_id).execute()

    if not resp.data:
        raise HTTPException(status_code=404, detail="Application not found")

    return {"saved": True}


@router.post("/applications/{application_id}/submit")
async def submit_application(
    application_id: str,
    body: SubmitApplicationRequest,
    supabase: SupabaseAdminClient,
):
    """PUBLIC: Submit the application."""
    # Fetch application
    app_resp = supabase.table("applications").select("*").eq("id", application_id).execute()
    if not app_resp.data:
        raise HTTPException(status_code=404, detail="Application not found")

    app = app_resp.data[0]

    # Get tier from job role
    role_resp = supabase.table("job_roles").select("*").eq("id", app["job_role_id"]).execute()
    role = role_resp.data[0] if role_resp.data else {}
    seniority = (role.get("seniority_level") or "entry").lower()
    tier = SENIORITY_TIER.get(seniority, 1)
    required_fields = TIER_FIELDS[tier]["required_fields"]

    # Validate required fields
    form_data = body.form_data
    missing = [f for f in required_fields if not form_data.get(f)]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required fields: {', '.join(missing)}"
        )

    # Update application status
    tracking_token = str(uuid.uuid4())
    update_resp = supabase.table("applications").update({
        "form_data": form_data,
        "status": "SUBMITTED",
        "completion_time_seconds": body.completion_time_seconds,
        "updated_at": datetime.utcnow().isoformat(),
        "tracking_token": tracking_token,
    }).eq("id", application_id).execute()

    if not update_resp.data:
        raise HTTPException(status_code=500, detail="Failed to submit application")

    referral = None
    if app.get("source") == "REFERRAL_LINK" and app.get("source_ref"):
        try:
            referral = attribute_application(
                supabase,
                token=app["source_ref"],
                job_role_id=app["job_role_id"],
                application_id=application_id,
                candidate_email=form_data.get("email"),
                candidate_id=app.get("candidate_id"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    tracking_url = f"{settings.APP_BASE_URL}/track/{tracking_token}"
    return {
        "success": True,
        "application_id": application_id,
        "tracking_url": tracking_url,
        "referral_attributed": bool(referral),
    }


@router.get("/applications/{application_id}/resume")
async def resume_application(
    application_id: str,
    supabase: SupabaseAdminClient,
):
    """PUBLIC: Resume a draft application."""
    resp = supabase.table("applications").select("*").eq("id", application_id).eq("status", "DRAFT").execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Draft application not found")

    app = resp.data[0]
    return {"form_data": app.get("form_data", {})}


@router.get("/applications")
async def list_applications(
    supabase: SupabaseClient,
    current_user: CurrentUser,
    status: Optional[str] = Query(None),
):
    """AUTH: List applications with candidate and role info."""
    query = supabase.table("applications").select("*, job_roles(title, seniority_level)")
    if status:
        query = query.eq("status", status)
    resp = query.order("created_at", desc=True).execute()
    return {"applications": resp.data or []}


# ---------------------------------------------------------------------------
# Video Interview Endpoints
# ---------------------------------------------------------------------------

@router.post("/video-interviews/create")
async def create_video_interview(
    body: CreateVideoInterviewRequest,
    supabase: SupabaseClient,
    current_user: CurrentUser,
):
    """AUTH: Create a video interview and send SMS link to candidate."""
    access_token = str(uuid.uuid4())

    # Fetch question details if IDs provided
    questions = []
    if body.question_ids:
        q_resp = supabase.table("video_questions").select("*").in_("id", body.question_ids).execute()
        questions = q_resp.data or []
    else:
        # Fetch default general questions
        q_resp = supabase.table("video_questions").select("*").is_("job_role_id", "null").eq("category", "general").order("order_index").limit(3).execute()
        questions = q_resp.data or []

    interview_data = {
        "application_id": body.application_id,
        "candidate_id": body.candidate_id,
        "job_role_id": body.job_role_id,
        "interview_type": body.interview_type,
        "questions": questions,
        "access_token": access_token,
        "status": "PENDING",
    }

    insert_resp = supabase.table("video_interviews").insert(interview_data).execute()
    if not insert_resp.data:
        raise HTTPException(status_code=500, detail="Failed to create video interview")

    interview = insert_resp.data[0]
    candidate_link = f"{settings.APP_BASE_URL}/video-interview/{access_token}"

    # Try to send SMS to candidate
    try:
        cand_resp = supabase.table("candidates").select("phone, full_name").eq("id", body.candidate_id).execute()
        if cand_resp.data and cand_resp.data[0].get("phone"):
            candidate = cand_resp.data[0]
            from app.services.twilio_service import twilio_service
            role_resp = supabase.table("job_roles").select("title").eq("id", body.job_role_id).execute()
            role_title = role_resp.data[0]["title"] if role_resp.data else "this role"
            message = f"Hi {candidate['full_name']}, please complete your video interview for {role_title}: {candidate_link}"
            twilio_service.send_sms(candidate["phone"], message)
    except Exception as e:
        logger.warning(f"SMS send failed: {e}")

    return {
        "interview_id": interview["id"],
        "candidate_link": candidate_link,
    }


@router.get("/video-interviews/candidate/{token}")
async def get_interview_by_token(
    token: str,
    supabase: SupabaseClient,
):
    """PUBLIC: Fetch interview data by access token."""
    resp = supabase.table("video_interviews").select(
        "*, job_roles(title), candidates(full_name)"
    ).eq("access_token", token).execute()

    if not resp.data:
        raise HTTPException(status_code=404, detail="Interview not found")

    interview = resp.data[0]
    return {
        "interview_id": interview["id"],
        "interview_type": interview["interview_type"],
        "questions": interview["questions"],
        "candidate_name": interview.get("candidates", {}).get("full_name", "Candidate") if interview.get("candidates") else "Candidate",
        "role_name": interview.get("job_roles", {}).get("title", "Position") if interview.get("job_roles") else "Position",
        "status": interview["status"],
    }


@router.post("/video-interviews/{interview_id}/upload")
async def upload_video(
    interview_id: str,
    supabase: SupabaseClient,
    file: UploadFile = File(...),
):
    """PUBLIC: Upload video recording for an interview."""
    # Save locally as stub
    os.makedirs("uploads", exist_ok=True)
    file_ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "webm"
    file_path = f"uploads/{interview_id}.{file_ext}"

    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    # Estimate duration from file size (stub: ~1MB/min)
    duration_seconds = max(1, len(contents) // 16000)
    recording_url = f"{settings.APP_BASE_URL}/uploads/{interview_id}.{file_ext}"

    supabase.table("video_interviews").update({
        "recording_url": recording_url,
        "duration_seconds": duration_seconds,
    }).eq("id", interview_id).execute()

    return {"upload_url": recording_url}


@router.post("/video-interviews/{interview_id}/complete")
async def complete_interview(
    interview_id: str,
    supabase: SupabaseClient,
):
    """PUBLIC: Mark interview as RECORDED."""
    resp = supabase.table("video_interviews").update({
        "status": "RECORDED",
    }).eq("id", interview_id).execute()

    if not resp.data:
        raise HTTPException(status_code=404, detail="Interview not found")

    return {"status": "RECORDED"}


@router.get("/video-interviews/{interview_id}/review")
async def review_interview(
    interview_id: str,
    supabase: SupabaseClient,
    current_user: CurrentUser,
):
    """AUTH: Return full interview for recruiter review."""
    resp = supabase.table("video_interviews").select(
        "*, candidates(full_name, email, phone), job_roles(title)"
    ).eq("id", interview_id).execute()

    if not resp.data:
        raise HTTPException(status_code=404, detail="Interview not found")

    interview = resp.data[0]
    # Return recording URL directly (stub — no pre-signed URL logic needed)
    return interview


@router.patch("/video-interviews/{interview_id}/rate")
async def rate_interview(
    interview_id: str,
    body: RateInterviewRequest,
    supabase: SupabaseClient,
    current_user: CurrentUser,
):
    """AUTH: Rate a video interview."""
    if not 1 <= body.rating <= 5:
        raise HTTPException(status_code=422, detail="Rating must be between 1 and 5")

    resp = supabase.table("video_interviews").update({
        "recruiter_rating": body.rating,
        "recruiter_notes": body.notes,
        "status": "REVIEWED",
        "reviewed_at": datetime.utcnow().isoformat(),
    }).eq("id", interview_id).execute()

    if not resp.data:
        raise HTTPException(status_code=404, detail="Interview not found")

    return resp.data[0]


@router.get("/video-questions")
async def list_video_questions(
    supabase: SupabaseClient,
    current_user: CurrentUser,
    category: Optional[str] = Query(None),
):
    """AUTH: List video questions."""
    query = supabase.table("video_questions").select("*")
    if category:
        query = query.eq("category", category)
    resp = query.order("order_index").execute()
    return {"questions": resp.data or []}


# ---------------------------------------------------------------------------
# QR Code Endpoints
# ---------------------------------------------------------------------------

@router.post("/qr-codes/generate")
async def generate_qr_code(
    body: GenerateQRRequest,
    supabase: SupabaseClient,
    current_user: CurrentUser,
):
    """AUTH: Generate a new QR code."""
    # Generate unique short code
    max_attempts = 10
    short_code = None
    for _ in range(max_attempts):
        candidate_code = generate_short_code(8)
        existing = supabase.table("qr_codes").select("id").eq("short_code", candidate_code).execute()
        if not existing.data:
            short_code = candidate_code
            break

    if not short_code:
        raise HTTPException(status_code=500, detail="Failed to generate unique short code")

    # Build redirect URL
    if body.type == "JOB_APPLY" and body.job_role_id:
        redirect_url = f"{settings.APP_BASE_URL}/apply/{body.job_role_id}?ref={short_code}"
    elif body.type == "CAMPAIGN" and body.campaign_id:
        redirect_url = f"{settings.APP_BASE_URL}/campaign/{body.campaign_id}?ref={short_code}"
    elif body.type == "REFERRAL":
        redirect_url = f"{settings.APP_BASE_URL}/apply?ref={short_code}"
    else:
        redirect_url = f"{settings.APP_BASE_URL}?ref={short_code}"

    # Generate QR image
    scan_url = f"{settings.APP_BASE_URL}/api/v1/mobile/qr-codes/scan/{short_code}"
    qr_image_base64 = generate_qr_image_base64(scan_url)

    # Insert into DB
    qr_data = {
        "type": body.type,
        "job_role_id": body.job_role_id,
        "campaign_id": body.campaign_id,
        "employee_id": body.employee_id,
        "short_code": short_code,
        "redirect_url": redirect_url,
        "qr_image_url": None,
        "scan_count": 0,
        "application_count": 0,
        "is_active": True,
    }

    insert_resp = supabase.table("qr_codes").insert(qr_data).execute()
    if not insert_resp.data:
        raise HTTPException(status_code=500, detail="Failed to create QR code")

    qr_code = insert_resp.data[0]
    return {
        "qr_code_id": qr_code["id"],
        "short_code": short_code,
        "qr_image_base64": qr_image_base64,
        "redirect_url": redirect_url,
    }


@router.get("/qr-codes/scan/{short_code}")
async def scan_qr_code(
    short_code: str,
    supabase: SupabaseClient,
    user_agent: Optional[str] = None,
):
    """PUBLIC: Track QR scan and return redirect URL."""
    resp = supabase.table("qr_codes").select("*").eq("short_code", short_code).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="QR code not found")

    qr_code = resp.data[0]
    if not qr_code["is_active"]:
        raise HTTPException(status_code=404, detail="QR code is inactive")

    # Log the scan
    try:
        supabase.table("qr_scans").insert({
            "qr_code_id": qr_code["id"],
            "user_agent": user_agent,
            "converted": False,
        }).execute()

        # Increment scan count
        supabase.table("qr_codes").update({
            "scan_count": qr_code["scan_count"] + 1,
        }).eq("id", qr_code["id"]).execute()
    except Exception as e:
        logger.warning(f"Failed to log QR scan: {e}")

    return {"redirect_url": qr_code["redirect_url"]}


@router.get("/qr-codes")
async def list_qr_codes(
    supabase: SupabaseClient,
    current_user: CurrentUser,
):
    """AUTH: List all QR codes with stats."""
    resp = supabase.table("qr_codes").select(
        "*, job_roles(title), hiring_campaigns(name)"
    ).order("created_at", desc=True).execute()
    return {"qr_codes": resp.data or []}


@router.post("/qr-codes/{qr_code_id}/deactivate")
async def deactivate_qr_code(
    qr_code_id: str,
    supabase: SupabaseClient,
    current_user: CurrentUser,
):
    """AUTH: Deactivate a QR code."""
    resp = supabase.table("qr_codes").update({
        "is_active": False,
    }).eq("id", qr_code_id).execute()

    if not resp.data:
        raise HTTPException(status_code=404, detail="QR code not found")

    return {"deactivated": True}


# ---------------------------------------------------------------------------
# Translation Endpoints
# ---------------------------------------------------------------------------

@router.post("/translations/job-role/{job_role_id}")
async def translate_job_role(
    job_role_id: str,
    body: TranslateJobRoleRequest,
    supabase: SupabaseClient,
    current_user: CurrentUser,
):
    """AUTH: Translate a job role to target language."""
    target_lang = body.target_language

    # Check cache
    existing = supabase.table("job_role_translations").select("*").eq("job_role_id", job_role_id).eq("language_code", target_lang).execute()
    if existing.data:
        return existing.data[0]

    # Fetch job role
    role_resp = supabase.table("job_roles").select("*").eq("id", job_role_id).execute()
    if not role_resp.data:
        raise HTTPException(status_code=404, detail="Job role not found")

    role = role_resp.data[0]

    # Translate fields
    translated_title = translate_text(role.get("title", ""), target_lang)
    translated_description = translate_text(role.get("description", ""), target_lang)
    translated_requirements = translate_text(role.get("requirements", ""), target_lang)
    translated_benefits = translate_text(role.get("benefits", ""), target_lang)

    # Save to DB
    translation_data = {
        "job_role_id": job_role_id,
        "language_code": target_lang,
        "translated_title": translated_title,
        "translated_description": translated_description,
        "translated_requirements": translated_requirements,
        "translated_benefits": translated_benefits,
        "translated_by": "AI",
    }

    insert_resp = supabase.table("job_role_translations").insert(translation_data).execute()
    if not insert_resp.data:
        raise HTTPException(status_code=500, detail="Failed to save translation")

    return insert_resp.data[0]


@router.get("/jobs/{job_role_id}/translate")
async def get_job_translation(
    job_role_id: str,
    supabase: SupabaseClient,
    lang: str = Query("en"),
):
    """PUBLIC: Get job role in requested language."""
    # Fetch original role
    role_resp = supabase.table("job_roles").select("*").eq("id", job_role_id).execute()
    if not role_resp.data:
        raise HTTPException(status_code=404, detail="Job role not found")

    role = role_resp.data[0]

    if lang == "en":
        return role

    # Check translation cache
    trans_resp = supabase.table("job_role_translations").select("*").eq("job_role_id", job_role_id).eq("language_code", lang).execute()
    if trans_resp.data:
        t = trans_resp.data[0]
        return {
            **role,
            "title": t.get("translated_title") or role.get("title"),
            "description": t.get("translated_description") or role.get("description"),
            "requirements": t.get("translated_requirements") or role.get("requirements"),
            "benefits": t.get("translated_benefits") or role.get("benefits"),
            "language_code": lang,
        }

    # Fall back to English
    return {**role, "language_code": "en"}


@router.post("/candidates/{candidate_id}/language-preference")
async def set_language_preference(
    candidate_id: str,
    body: LanguagePreferenceRequest,
    supabase: SupabaseClient,
):
    """PUBLIC: Save candidate language preference."""
    # Upsert
    existing = supabase.table("language_preferences").select("id").eq("candidate_id", candidate_id).execute()

    if existing.data:
        supabase.table("language_preferences").update({
            "language_code": body.language_code,
        }).eq("candidate_id", candidate_id).execute()
    else:
        supabase.table("language_preferences").insert({
            "candidate_id": candidate_id,
            "language_code": body.language_code,
            "detected_from": "BROWSER",
        }).execute()

    return {"saved": True}
