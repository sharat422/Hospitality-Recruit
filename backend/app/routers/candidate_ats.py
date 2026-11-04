from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.candidate_ats_service import ALL_STAGES, PIPELINE_STAGES, duplicate_reasons, matches_candidate, stage_update
from app.services.smart_recruitment_service import move_candidate_stage
from app.services.rbac_service import authorize, build_access_context
from app.services.referral_lifecycle_service import mark_application_referral_hired

router = APIRouter(tags=["Candidate ATS"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


def _first(result):
    rows = getattr(result, "data", None) or []
    return rows[0] if rows else None


def _org(supabase, user: dict) -> str:
    row = _first(supabase.table("users").select("org_id").eq("id", user["sub"]).limit(1).execute())
    if not row: raise HTTPException(404, "User not found")
    return row["org_id"]


def _candidate(supabase, org_id: str, candidate_id: str) -> dict:
    row = _first(supabase.table("candidates").select("*").eq("id", candidate_id).eq("org_id", org_id).limit(1).execute())
    if not row: raise HTTPException(404, "Candidate not found")
    return row


class CandidateUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=255)
    last_name: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    years_experience: Optional[int] = Field(None, ge=0, le=70)
    parsed_skills: Optional[list[str] | dict] = None
    languages: Optional[list[str]] = None
    current_ctc: Optional[float] = Field(None, ge=0)
    expected_ctc: Optional[float] = Field(None, ge=0)
    expected_salary_inr: Optional[int] = Field(None, ge=0)
    notice_period: Optional[str] = None
    availability: Optional[list | dict] = None
    profile_summary: Optional[str] = Field(None, max_length=5000)
    tags: Optional[list[str]] = Field(None, max_length=50)


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    application_id: Optional[str] = None
    is_private: bool = False


class DocumentCreate(BaseModel):
    document_type: str = Field(min_length=2, max_length=50)
    file_name: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=1000)
    file_url: Optional[str] = None
    mime_type: Optional[str] = None
    expiry_date: Optional[str] = None
    application_id: Optional[str] = None
    data_category: str = "RECRUITMENT_DOCUMENT"
    retention_until: Optional[str] = None


class DocumentUploadRequest(BaseModel):
    document_type: str = Field(min_length=2, max_length=50)
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str


class StageChange(BaseModel):
    stage: str
    notes: Optional[str] = Field(None, max_length=5000)
    offer_salary_inr: Optional[int] = Field(None, ge=0)

    @field_validator("stage")
    @classmethod
    def valid_stage(cls, value: str) -> str:
        value = value.lower()
        if value not in ALL_STAGES: raise ValueError("Unsupported pipeline stage")
        return value


class BulkCandidateAction(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=200)
    action: str
    stage: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    note: Optional[str] = None


class InterviewFeedback(BaseModel):
    rating: float = Field(ge=1, le=5)
    notes: str = Field(min_length=1, max_length=10000)
    recommendation: str = "NO_DECISION"
    competencies: dict = Field(default_factory=dict)

    @field_validator("recommendation")
    @classmethod
    def valid_recommendation(cls, value: str) -> str:
        value = value.upper()
        if value not in {"STRONG_HIRE","HIRE","NO_DECISION","NO_HIRE","STRONG_NO_HIRE"}: raise ValueError("Invalid recommendation")
        return value


@router.get("/candidates")
async def search_candidates(supabase: SupabaseClient, user: CurrentUser, search: Optional[str] = None,
    job_id: Optional[str] = None, stage: Optional[str] = None, source: Optional[str] = None,
    location: Optional[str] = None, tags: list[str] = Query(default=[]), skills: list[str] = Query(default=[]),
    languages: list[str] = Query(default=[]), min_experience: Optional[int] = Query(None, ge=0), limit: int = Query(100, ge=1, le=500)):
    org_id = _org(supabase, user)
    query = supabase.table("candidates").select("*").eq("org_id", org_id).order("created_at", desc=True).limit(500)
    if job_id: query = query.eq("applied_job_id", job_id)
    if stage: query = query.eq("pipeline_stage", stage.lower())
    if source: query = query.eq("source", source)
    rows = query.execute().data or []
    filtered = [row for row in rows if matches_candidate(row, search=search, location=location, tags=tags,
        skills=skills, languages=languages, min_experience=min_experience)]
    return {"total": len(filtered), "candidates": filtered[:limit]}


@router.get("/pipeline")
async def ats_pipeline(supabase: SupabaseClient, user: CurrentUser, job_id: Optional[str] = None):
    org_id = _org(supabase, user)
    query = supabase.table("candidates").select("*").eq("org_id", org_id).in_("pipeline_stage", PIPELINE_STAGES).order("created_at", desc=True)
    if job_id: query = query.eq("applied_job_id", job_id)
    rows = query.execute().data or []
    result = {stage: [] for stage in PIPELINE_STAGES}
    for row in rows: result.setdefault((row.get("pipeline_stage") or "applied").lower(), []).append(row)
    return result


@router.get("/candidates/{candidate_id}")
async def candidate_profile(candidate_id: str, supabase: SupabaseClient, user: CurrentUser):
    org_id = _org(supabase, user); candidate = _candidate(supabase, org_id, candidate_id)
    applications = supabase.table("applications").select("*").eq("candidate_id", candidate_id).eq("org_id", org_id).order("created_at", desc=True).execute().data or []
    notes = supabase.table("candidate_notes").select("*").eq("candidate_id", candidate_id).eq("org_id", org_id).order("created_at", desc=True).execute().data or []
    documents = supabase.table("candidate_documents").select("*").eq("candidate_id", candidate_id).eq("org_id", org_id).order("created_at", desc=True).execute().data or []
    history = supabase.table("application_stage_history").select("*").eq("candidate_id", candidate_id).eq("org_id", org_id).order("changed_at").execute().data or []
    referrals = supabase.table("referrals").select("id,referral_code,status,referrer_id,created_at").eq("candidate_id", candidate_id).execute().data or []
    try: interviews = supabase.table("interviews").select("*").eq("candidate_id", candidate_id).eq("org_id", org_id).order("scheduled_at", desc=True).execute().data or []
    except Exception: interviews = []
    try:
        slots = supabase.table("interview_slots").select("*").eq("candidate_id", candidate_id).order("start_time", desc=True).execute().data or []
        interviews += [{**row, "scheduled_at": row.get("start_time"), "interview_source": "engagement_slot"} for row in slots]
    except Exception:
        try:
            slots = supabase.table("interview_slots").select("*").eq("booked_by_candidate_id", candidate_id).eq("org_id", org_id).order("start_time", desc=True).execute().data or []
            interviews += [{**row, "scheduled_at": row.get("start_time"), "interview_source": "scheduler_slot"} for row in slots]
        except Exception: pass
    try: video = supabase.table("video_interviews").select("*").eq("candidate_id", candidate_id).order("created_at", desc=True).execute().data or []
    except Exception: video = []
    timeline = [{"type": "stage", "at": row.get("changed_at"), "data": row} for row in history]
    timeline += [{"type": "interview", "at": row.get("scheduled_at") or row.get("created_at"), "data": row} for row in interviews]
    timeline += [{"type": "note", "at": row.get("created_at"), "data": row} for row in notes]
    timeline.sort(key=lambda row: row.get("at") or "")
    return {"candidate": candidate, "applications": applications, "notes": notes, "documents": documents,
            "referrals": referrals, "interviews": interviews, "video_interviews": video, "timeline": timeline}


@router.patch("/candidates/{candidate_id}")
async def update_candidate(candidate_id: str, body: CandidateUpdate, supabase: SupabaseClient, user: CurrentUser):
    org_id = _org(supabase, user); _candidate(supabase, org_id, candidate_id)
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    if not values: raise HTTPException(400, "No candidate fields to update")
    values["updated_at"] = datetime.now(timezone.utc).isoformat()
    row = _first(supabase.table("candidates").update(values).eq("id", candidate_id).eq("org_id", org_id).execute())
    return row or {"id": candidate_id, **values}


@router.post("/candidates/{candidate_id}/notes", status_code=201)
async def add_note(candidate_id: str, body: NoteCreate, supabase: SupabaseClient, user: CurrentUser):
    org_id = _org(supabase, user); _candidate(supabase, org_id, candidate_id)
    values = {"org_id": org_id, "candidate_id": candidate_id, "created_by": user["sub"], **body.model_dump()}
    return _first(supabase.table("candidate_notes").insert(values).execute()) or values


@router.post("/candidates/{candidate_id}/documents", status_code=201)
async def add_document(candidate_id: str, body: DocumentCreate, supabase: SupabaseClient, user: CurrentUser):
    org_id = _org(supabase, user); _candidate(supabase, org_id, candidate_id)
    required_prefix = f"candidate-documents/{org_id}/{candidate_id}/"
    if not body.storage_key.startswith(required_prefix):
        raise HTTPException(400, "storage_key was not issued for this organisation and candidate")
    if body.file_url:
        raise HTTPException(400, "External/public document URLs are not allowed; use private storage_key")
    from app.core.config import settings
    from app.services.data_localization import DataLocalizationGuard
    values = {"org_id": org_id, "candidate_id": candidate_id, "uploaded_by": user["sub"],
              **body.model_dump(), "file_url": None, "storage_region": "ap-south-1",
              "encryption_mode": "SSE-KMS" if settings.AWS_KMS_KEY_ID else "SSE-S3"}
    row = _first(supabase.table("candidate_documents").insert(values).execute()) or values
    DataLocalizationGuard(settings, supabase=supabase).log_file_upload(
        file_type=body.document_type, s3_key=body.storage_key,
        s3_bucket=settings.AWS_S3_BUCKET, s3_region="ap-south-1",
        content_type=body.mime_type, candidate_id=candidate_id, org_id=org_id,
        uploader_type="RECRUITER", uploader_id=user["sub"],
    )
    return row


@router.post("/candidates/{candidate_id}/documents/upload-url")
async def create_document_upload_url(
    candidate_id: str, body: DocumentUploadRequest,
    supabase: SupabaseClient, user: CurrentUser,
):
    org_id = _org(supabase, user); _candidate(supabase, org_id, candidate_id)
    from app.services.s3_service import S3Service
    try:
        return S3Service().generate_document_upload_url(
            org_id, candidate_id, body.file_name, body.content_type,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/candidates/{candidate_id}/duplicates")
async def detect_duplicates(candidate_id: str, supabase: SupabaseClient, user: CurrentUser):
    org_id = _org(supabase, user); candidate = _candidate(supabase, org_id, candidate_id)
    rows = supabase.table("candidates").select("id,first_name,last_name,email,phone,created_at").eq("org_id", org_id).execute().data or []
    matches = [{"candidate": row, "matched_on": reasons} for row in rows if row.get("id") != candidate_id and (reasons := duplicate_reasons(candidate, row))]
    return {"candidate_id": candidate_id, "duplicates": matches}


@router.patch("/applications/{application_id}/stage")
async def change_stage(application_id: str, body: StageChange, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "applications.manage")
    org_id = context.org_id
    application = _first(supabase.table("applications").select("*").eq("id", application_id).eq("org_id", org_id).limit(1).execute())
    if not application: raise HTTPException(404, "Application not found")
    candidate = _candidate(supabase, org_id, application["candidate_id"])
    previous = (application.get("status") or candidate.get("pipeline_stage") or "applied").lower()
    values = {"status": body.stage.upper(), "stage_updated_at": datetime.now(timezone.utc).isoformat()}
    timestamp = stage_update(body.stage)
    for field in ("selected_at", "offer_accepted_at", "onboarding_at", "hired_at"):
        if field in timestamp: values[field] = timestamp[field]
    supabase.table("applications").update(values).eq("id", application_id).eq("org_id", org_id).execute()
    move_candidate_stage(supabase, org_id, candidate["id"], body.stage, notes=body.notes, offer_salary=body.offer_salary_inr)
    history = {"org_id": org_id, "application_id": application_id, "candidate_id": candidate["id"],
               "job_id": application.get("job_id"), "from_stage": previous, "to_stage": body.stage,
               "notes": body.notes, "changed_by": user["sub"]}
    supabase.table("application_stage_history").insert(history).execute()
    if body.stage == "hired":
        mark_application_referral_hired(supabase, application_id)
    return {"application_id": application_id, "from_stage": previous, "to_stage": body.stage}


@router.post("/candidates/bulk-action")
async def bulk_candidate_action(body: BulkCandidateAction, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "applications.manage")
    org_id = context.org_id; processed = 0; errors = []
    for candidate_id in body.candidate_ids:
        try:
            candidate = _candidate(supabase, org_id, candidate_id)
            if body.action == "stage" and body.stage:
                target = body.stage.lower()
                if target not in ALL_STAGES: raise ValueError("Unsupported pipeline stage")
                move_candidate_stage(supabase, org_id, candidate_id, target)
                application = _first(supabase.table("applications").select("*").eq("candidate_id", candidate_id).eq("org_id", org_id).order("created_at", desc=True).limit(1).execute())
                if application:
                    previous = (application.get("status") or candidate.get("pipeline_stage") or "applied").lower()
                    app_values = {"status": target.upper(), "stage_updated_at": datetime.now(timezone.utc).isoformat()}
                    timestamp = stage_update(target)
                    for field in ("selected_at", "offer_accepted_at", "onboarding_at", "hired_at"):
                        if field in timestamp: app_values[field] = timestamp[field]
                    supabase.table("applications").update(app_values).eq("id", application["id"]).eq("org_id", org_id).execute()
                    supabase.table("application_stage_history").insert({
                        "org_id": org_id, "application_id": application["id"], "candidate_id": candidate_id,
                        "job_id": application.get("job_id"), "from_stage": previous, "to_stage": target,
                        "changed_by": user["sub"],
                    }).execute()
                    if target == "hired":
                        mark_application_referral_hired(supabase, application["id"])
            elif body.action == "tag":
                merged = sorted(set(candidate.get("tags") or []) | set(body.tags))
                supabase.table("candidates").update({"tags": merged}).eq("id", candidate_id).eq("org_id", org_id).execute()
            elif body.action == "note" and body.note:
                supabase.table("candidate_notes").insert({"org_id": org_id, "candidate_id": candidate_id, "body": body.note, "created_by": user["sub"]}).execute()
            else: raise ValueError("Unsupported or incomplete bulk action")
            processed += 1
        except Exception as exc: errors.append({"candidate_id": candidate_id, "error": str(exc)})
    return {"processed": processed, "errors": errors}


@router.patch("/interviews/{interview_id}/feedback")
async def save_interview_feedback(interview_id: str, body: InterviewFeedback, supabase: SupabaseClient, user: CurrentUser):
    org_id = _org(supabase, user)
    interview = _first(supabase.table("interviews").select("id,candidate_id,org_id").eq("id", interview_id).eq("org_id", org_id).limit(1).execute())
    table = "interviews"
    if not interview:
        interview = _first(supabase.table("interview_slots").select("*").eq("id", interview_id).limit(1).execute())
        slot_candidate_id = (interview or {}).get("candidate_id") or (interview or {}).get("booked_by_candidate_id")
        if interview and (not slot_candidate_id or not _candidate(supabase, org_id, slot_candidate_id)):
            interview = None
        table = "interview_slots"
    if not interview: raise HTTPException(404, "Interview not found")
    values = {"interview_rating": body.rating, "interview_notes": body.notes,
              "recommendation": body.recommendation, "feedback": body.competencies,
              "status": "completed", "completed_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
    query = supabase.table(table).update(values).eq("id", interview_id)
    if table == "interviews": query = query.eq("org_id", org_id)
    query.execute()
    return {"interview_id": interview_id, **values}
