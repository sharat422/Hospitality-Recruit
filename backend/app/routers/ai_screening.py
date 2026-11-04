"""
AI Screening Router — AI-powered candidate matching & screening.

Endpoints:
  POST /upload-resume
  GET  /candidates/{candidate_id}/parsed
  POST /candidates/{candidate_id}/match-jobs
  GET  /job-roles
  POST /job-roles
  POST /generate-jd
  GET  /passive-discovery
  POST /reactivation/send
  GET  /taxonomy
  POST /taxonomy/suggest-skills
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Optional
from fastapi import APIRouter, HTTPException, File, UploadFile, Query, Depends
from pydantic import BaseModel, Field, model_validator

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.ai_matching_service import (
    AIMatchingService,
    HOSPITALITY_TAXONOMY,
    CROSS_INDUSTRY_MAP,
)
from app.services.s3_service import S3Service
from app.services.resume_parser_service import extract_text_from_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI Screening"])

# CurrentUser type alias following the pattern in the codebase
CurrentUser = Annotated[dict, Depends(get_current_user)]

# ──────────────────────────────────────────────────────────────────────────────
# Request models
# ──────────────────────────────────────────────────────────────────────────────


class CreateJobRoleRequest(BaseModel):
    title: str
    property_type: str = "hotel"
    department: Optional[str] = None
    location: Optional[str] = None
    required_skills: list = []
    preferred_skills: list = []
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    seniority_level: str = "mid"
    work_pattern: str = "full-time"
    description: Optional[str] = None
    employer_values: list = []


class GenerateJDRequest(BaseModel):
    job_role_id: Optional[str] = None
    role: str
    property_type: str = "hotel"
    location: str = ""
    seniority_level: str = "mid"
    responsibilities: list = []
    certifications: list = []
    work_pattern: str = "full-time"
    employer_values: list = []
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None


class ReactivationSendRequest(BaseModel):
    candidate_ids: list[str]
    job_role_id: str
    channel: str = "sms"


class SuggestSkillsRequest(BaseModel):
    job_title: str
    property_type: str = "hotel"


class ScreeningWeightsRequest(BaseModel):
    skill: float = Field(0.30, ge=0, le=1)
    experience: float = Field(0.25, ge=0, le=1)
    language: float = Field(0.10, ge=0, le=1)
    location: float = Field(0.15, ge=0, le=1)
    salary: float = Field(0.10, ge=0, le=1)
    availability: float = Field(0.10, ge=0, le=1)
    shortlist_threshold: float = Field(75, ge=0, le=100)
    reject_threshold: float = Field(45, ge=0, le=100)

    @model_validator(mode="after")
    def validate_config(self):
        if abs(sum(getattr(self, key) for key in ("skill", "experience", "language", "location", "salary", "availability")) - 1) > 0.0001:
            raise ValueError("Scoring weights must sum to 1.0")
        if self.reject_threshold >= self.shortlist_threshold:
            raise ValueError("Reject threshold must be lower than shortlist threshold")
        return self


class ScreeningOverrideRequest(BaseModel):
    recommendation: Optional[str] = None
    reason: str = Field(min_length=5, max_length=2000)

    @model_validator(mode="after")
    def validate_recommendation(self):
        if self.recommendation is not None:
            self.recommendation = self.recommendation.lower()
            if self.recommendation not in {"shortlist", "consider", "reject"}:
                raise ValueError("Invalid recommendation override")
        return self


def _screening_org(db, current_user: dict) -> str:
    try:
        result = db.table("users").select("org_id").eq("id", current_user.get("sub", "")).single().execute()
        org_id = (result.data or {}).get("org_id")
    except Exception:
        org_id = None
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation access required")
    return org_id


# ──────────────────────────────────────────────────────────────────────────────
# POST /upload-resume
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/upload-resume")
async def upload_resume(
    file: UploadFile = File(...),
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Upload a resume file, parse it with AI, and upsert candidate."""
    file_bytes = await file.read()
    filename = file.filename or "resume.pdf"
    content_type = file.content_type or "application/octet-stream"

    # Extract text
    resume_text = extract_text_from_file(file_bytes, filename)
    if not resume_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from uploaded file.")

    # Upload to S3 (or local fallback)
    s3 = S3Service()
    resume_url = await s3.upload_resume(file_bytes, filename, content_type)

    # Parse with AI
    svc = AIMatchingService()
    parsed = await svc.parse_resume(resume_text)

    # Determine org_id from user
    user_id = current_user.get("sub", "")
    org_id = current_user.get("org_id", None)
    if not org_id:
        try:
            user_row = db.table("users").select("org_id").eq("id", user_id).single().execute()
            org_id = user_row.data.get("org_id") if user_row.data else None
        except Exception:
            org_id = None

    # Build candidate payload
    name_parts = (parsed.get("name") or "Unknown").split(" ", 1)
    candidate_payload = {
        "first_name": name_parts[0],
        "last_name": name_parts[1] if len(name_parts) > 1 else "",
        "email": parsed.get("email") or f"upload_{user_id[:8]}@placeholder.com",
        "resume_url": resume_url,
        "parsed_skills": parsed.get("skills", []),
        "work_history": parsed.get("work_history", []),
        "soft_skills_score": float(len(parsed.get("soft_skills", [])) * 10),
        "years_experience": parsed.get("years_total_experience", 0),
        "languages": parsed.get("languages", []),
        "certifications": parsed.get("certifications", []),
        "source": "UPLOAD",
        "last_active_at": datetime.now(timezone.utc).isoformat(),
    }
    if org_id:
        candidate_payload["org_id"] = org_id

    # Upsert candidate
    try:
        result = db.table("candidates").upsert(
            candidate_payload,
            on_conflict="email",
        ).execute()
        candidate_id = result.data[0]["id"] if result.data else None
    except Exception as e:
        logger.error(f"Candidate upsert failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save candidate: {str(e)}")

    return {
        "candidate_id": candidate_id,
        "status": "parsed",
        "parsed_profile": parsed,
        "resume_url": resume_url,
    }


# ──────────────────────────────────────────────────────────────────────────────
# GET /candidates/{candidate_id}/parsed
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/candidates/{candidate_id}/parsed")
async def get_parsed_candidate(
    candidate_id: str,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Fetch a candidate and return their parsed profile."""
    try:
        result = db.table("candidates").select("*").eq("id", candidate_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not result.data:
        raise HTTPException(status_code=404, detail="Candidate not found")

    c = result.data
    return {
        "candidate_id": c["id"],
        "name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
        "email": c.get("email"),
        "skills": c.get("parsed_skills", []),
        "work_history": c.get("work_history", []),
        "years_experience": c.get("years_experience", 0),
        "languages": c.get("languages", []),
        "certifications": c.get("certifications", []),
        "resume_url": c.get("resume_url"),
        "source": c.get("source"),
        "last_active_at": c.get("last_active_at"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# POST /candidates/{candidate_id}/match-jobs
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/candidates/{candidate_id}/match-jobs")
async def match_candidate_to_jobs(
    candidate_id: str,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Match a candidate against all active job roles and upsert scores."""
    # Fetch candidate
    try:
        cand_result = db.table("candidates").select("*").eq("id", candidate_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate = cand_result.data

    # Fetch org active job roles
    user_id = current_user.get("sub", "")
    try:
        user_row = db.table("users").select("org_id").eq("id", user_id).single().execute()
        org_id = user_row.data.get("org_id") if user_row.data else None
    except Exception:
        org_id = None

    try:
        roles_query = db.table("job_roles").select("*").eq("is_active", True)
        if org_id:
            roles_query = roles_query.eq("org_id", org_id)
        roles_result = roles_query.execute()
        job_roles = roles_result.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch job roles: {str(e)}")

    if not job_roles:
        return {"matches": [], "message": "No active job roles found for this organisation"}

    svc = AIMatchingService()
    matches = []
    for role in job_roles:
        try:
            scores = await svc.score_match(candidate, role)
        except Exception as e:
            logger.error(f"score_match error for role {role.get('id')}: {e}")
            scores = {
                "overall_score": 0,
                "skill_match_score": 0,
                "soft_skill_score": 0,
                "experience_score": 0,
                "cross_industry_score": 0,
                "availability_score": 0,
                "match_reasoning": "Scoring failed",
            }

        match_payload = {
            "candidate_id": candidate_id,
            "job_role_id": role["id"],
            "overall_score": scores.get("overall_score", 0),
            "skill_match_score": scores.get("skill_match_score", 0),
            "soft_skill_score": scores.get("soft_skill_score", 0),
            "experience_score": scores.get("experience_score", 0),
            "cross_industry_score": scores.get("cross_industry_score", 0),
            "availability_score": scores.get("availability_score", 0),
            "match_reasoning": scores.get("match_reasoning", ""),
        }

        try:
            db.table("candidate_matches").upsert(
                match_payload,
                on_conflict="candidate_id,job_role_id",
            ).execute()
        except Exception as e:
            logger.error(f"Match upsert error: {e}")

        matches.append({
            "job_role_id": role["id"],
            "job_title": role.get("title"),
            "location": role.get("location"),
            **scores,
        })

    # Sort by overall_score desc
    matches.sort(key=lambda x: x.get("overall_score", 0), reverse=True)
    return {"candidate_id": candidate_id, "matches": matches}


# ──────────────────────────────────────────────────────────────────────────────
# GET /job-roles
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/job-roles")
async def list_job_roles(
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """List all active job roles for the current org."""
    user_id = current_user.get("sub", "")
    try:
        user_row = db.table("users").select("org_id").eq("id", user_id).single().execute()
        org_id = user_row.data.get("org_id") if user_row.data else None
    except Exception:
        org_id = None

    try:
        query = db.table("job_roles").select("*").eq("is_active", True).order("created_at", desc=True)
        if org_id:
            query = query.eq("org_id", org_id)
        result = query.execute()
        return {"job_roles": result.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch job roles: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# POST /job-roles
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/job-roles")
async def create_job_role(
    body: CreateJobRoleRequest,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Create a new job role."""
    user_id = current_user.get("sub", "")
    try:
        user_row = db.table("users").select("org_id").eq("id", user_id).single().execute()
        org_id = user_row.data.get("org_id") if user_row.data else None
    except Exception:
        org_id = None

    payload = {
        "title": body.title,
        "property_type": body.property_type,
        "department": body.department,
        "location": body.location,
        "required_skills": body.required_skills,
        "preferred_skills": body.preferred_skills,
        "salary_min": body.salary_min,
        "salary_max": body.salary_max,
        "seniority_level": body.seniority_level,
        "work_pattern": body.work_pattern,
        "description": body.description,
        "is_active": True,
    }
    if org_id:
        payload["org_id"] = org_id

    try:
        result = db.table("job_roles").insert(payload).execute()
        return {"job_role": result.data[0] if result.data else payload}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create job role: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# POST /generate-jd
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/generate-jd")
async def generate_jd(
    body: GenerateJDRequest,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Generate a job description using AI and save it."""
    svc = AIMatchingService()
    jd = await svc.generate_jd(
        role=body.role,
        property_type=body.property_type,
        location=body.location,
        seniority_level=body.seniority_level,
        responsibilities=body.responsibilities,
        certifications=body.certifications,
        work_pattern=body.work_pattern,
        employer_values=body.employer_values,
        salary_min=body.salary_min,
        salary_max=body.salary_max,
    )

    # Save to DB
    save_payload = {
        "prompt_inputs": body.model_dump(),
        "generated_jd": jd.get("full_text", ""),
        "salary_suggestion_min": body.salary_min,
        "salary_suggestion_max": body.salary_max,
    }
    if body.job_role_id:
        save_payload["job_role_id"] = body.job_role_id

    try:
        db.table("job_descriptions_generated").insert(save_payload).execute()
    except Exception as e:
        logger.error(f"Failed to save generated JD: {e}")

    return {"job_description": jd}


# ──────────────────────────────────────────────────────────────────────────────
# GET /passive-discovery
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/passive-discovery")
async def passive_discovery(
    job_role_id: str = Query(...),
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Discover passive candidates for a job role."""
    # Fetch job role
    try:
        role_result = db.table("job_roles").select("*").eq("id", job_role_id).single().execute()
        job_role = role_result.data
    except Exception:
        raise HTTPException(status_code=404, detail="Job role not found")

    # Fetch candidates sorted by least recently active
    try:
        cands_result = (
            db.table("candidates")
            .select("*")
            .order("last_active_at", desc=False)
            .limit(100)
            .execute()
        )
        candidates = cands_result.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch candidates: {str(e)}")

    svc = AIMatchingService()
    scored = []
    for c in candidates:
        # Compute days since active
        last_active = c.get("last_active_at")
        if last_active:
            try:
                if isinstance(last_active, str):
                    last_dt = datetime.fromisoformat(last_active.replace("Z", "+00:00"))
                else:
                    last_dt = last_active
                days_since = (datetime.now(timezone.utc) - last_dt).days
            except Exception:
                days_since = 365
        else:
            days_since = 365

        passive_score = svc.compute_passive_score(
            days_since_active=days_since,
            tenure_months=c.get("years_experience", 1) * 12,
            portal_logins=0,
        )

        # Get match score from candidate_matches if exists
        match_score = 0
        try:
            match_row = (
                db.table("candidate_matches")
                .select("overall_score")
                .eq("candidate_id", c["id"])
                .eq("job_role_id", job_role_id)
                .single()
                .execute()
            )
            if match_row.data:
                match_score = match_row.data.get("overall_score", 0)
        except Exception:
            pass

        # Generate outreach message
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or "Candidate"
        skills = c.get("parsed_skills", [])
        top_skill = skills[0] if skills else "hospitality experience"
        msg = await svc.generate_reactivation_message(
            candidate_name=name,
            past_role=c.get("current_position", "your previous role"),
            months_ago=days_since // 30,
            new_role=job_role.get("title", "a new position"),
            location=job_role.get("location", "our location"),
            top_skill=top_skill if isinstance(top_skill, str) else str(top_skill),
        )

        scored.append({
            "candidate_id": c["id"],
            "name": name,
            "email": c.get("email"),
            "days_since_active": days_since,
            "passive_score": passive_score,
            "match_score": match_score,
            "combined_score": round(passive_score * 0.4 + match_score * 0.6, 2),
            "suggested_outreach_message": msg,
        })

    # Sort by combined score, take top 20
    scored.sort(key=lambda x: x["combined_score"], reverse=True)
    return {"passive_candidates": scored[:20], "job_role": job_role}


# ──────────────────────────────────────────────────────────────────────────────
# POST /reactivation/send
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/reactivation/send")
async def send_reactivation(
    body: ReactivationSendRequest,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Generate and mark reactivation messages for candidates."""
    # Fetch job role
    try:
        role_result = db.table("job_roles").select("*").eq("id", body.job_role_id).single().execute()
        job_role = role_result.data
    except Exception:
        raise HTTPException(status_code=404, detail="Job role not found")

    svc = AIMatchingService()
    sent_count = 0
    results = []

    for candidate_id in body.candidate_ids:
        try:
            cand_result = db.table("candidates").select("*").eq("id", candidate_id).single().execute()
            c = cand_result.data
        except Exception:
            results.append({"candidate_id": candidate_id, "status": "not_found"})
            continue

        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or "Candidate"
        skills = c.get("parsed_skills", [])
        top_skill = skills[0] if skills else "hospitality experience"
        last_active = c.get("last_active_at")
        days_since = 180
        if last_active:
            try:
                if isinstance(last_active, str):
                    last_dt = datetime.fromisoformat(last_active.replace("Z", "+00:00"))
                else:
                    last_dt = last_active
                days_since = (datetime.now(timezone.utc) - last_dt).days
            except Exception:
                pass

        msg = await svc.generate_reactivation_message(
            candidate_name=name,
            past_role=c.get("current_position", "your previous role"),
            months_ago=days_since // 30,
            new_role=job_role.get("title", "a new position"),
            location=job_role.get("location", "our location"),
            top_skill=top_skill if isinstance(top_skill, str) else str(top_skill),
        )

        # Update match record
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            db.table("candidate_matches").upsert(
                {
                    "candidate_id": candidate_id,
                    "job_role_id": body.job_role_id,
                    "reactivation_sent": True,
                    "reactivation_sent_at": now_iso,
                },
                on_conflict="candidate_id,job_role_id",
            ).execute()
        except Exception as e:
            logger.error(f"Failed to update reactivation status: {e}")

        sent_count += 1
        results.append({
            "candidate_id": candidate_id,
            "name": name,
            "message": msg,
            "channel": body.channel,
            "status": "sent",
        })

    return {"sent_count": sent_count, "results": results}


# ──────────────────────────────────────────────────────────────────────────────
# GET /taxonomy
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/taxonomy")
async def get_taxonomy(
    current_user: CurrentUser = None,
):
    """Return full skill taxonomy and cross-industry map."""
    return {
        "hospitality_taxonomy": HOSPITALITY_TAXONOMY,
        "cross_industry_map": CROSS_INDUSTRY_MAP,
    }


# ──────────────────────────────────────────────────────────────────────────────
# POST /taxonomy/suggest-skills
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/taxonomy/suggest-skills")
async def suggest_skills(
    body: SuggestSkillsRequest,
    current_user: CurrentUser = None,
):
    """Get Claude-suggested skills for a job title and property type."""
    svc = AIMatchingService()
    skills = await svc.suggest_skills(body.job_title, body.property_type)
    return {"suggested_skills": skills}


# ──────────────────────────────────────────────────────────────────────────────
# Screening V2 — 6-dimension scoring, blind mode, auto-shortlist
# ──────────────────────────────────────────────────────────────────────────────

from app.services.candidate_screening_service import (  # noqa: E402
    screen_job_candidates,
    auto_shortlist as _auto_shortlist,
    get_blind_profile,
    INDIA_CROSS_INDUSTRY_MAP,
)


class ScreenJobRequest(BaseModel):
    blind_mode: bool = False
    screen_all: bool = False  # if True, screen all org candidates against this job


@router.post("/screen/job/{job_id}")
async def screen_job(
    job_id: str,
    body: ScreenJobRequest,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """
    Run AI screening for all candidates who applied to a job.
    Scores across 6 dimensions, saves results, returns ranked list.
    Set blind_mode=true to hide candidate name/photo/address during scoring.
    """
    user_id = current_user.get("sub", "")
    try:
        user_row = db.table("users").select("org_id").eq("id", user_id).single().execute()
        org_id = user_row.data.get("org_id") if user_row.data else None
    except Exception:
        org_id = None

    if not org_id:
        raise HTTPException(status_code=400, detail="Could not determine organisation for this user.")

    result = await screen_job_candidates(
        supabase=db,
        job_id=job_id,
        job_role_id=None,
        org_id=org_id,
        blind_mode=body.blind_mode,
        screen_all=body.screen_all,
        triggered_by=user_id,
    )
    return result


@router.post("/screen/job-role/{job_role_id}")
async def screen_job_role(
    job_role_id: str,
    body: ScreenJobRequest,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Screen candidates against a legacy job_role (existing AI matching flow)."""
    user_id = current_user.get("sub", "")
    try:
        user_row = db.table("users").select("org_id").eq("id", user_id).single().execute()
        org_id = user_row.data.get("org_id") if user_row.data else None
    except Exception:
        org_id = None

    result = await screen_job_candidates(
        supabase=db,
        job_id=None,
        job_role_id=job_role_id,
        org_id=org_id,
        blind_mode=body.blind_mode,
        screen_all=body.screen_all,
        triggered_by=user_id,
    )
    return result


@router.get("/screen/job/{job_id}/results")
async def get_screening_results(
    job_id: str,
    blind_mode: bool = Query(False),
    min_score: float = Query(0),
    recommendation: Optional[str] = Query(None),
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """
    Retrieve saved screening results for a job, sorted by rank.
    Use blind_mode=true to redact candidate identity fields.
    """
    org_id = _screening_org(db, current_user)
    try:
        q = (
            db.table("v_screening_leaderboard")
            .select("*")
            .eq("job_id", job_id)
            .eq("org_id", org_id)
            .gte("total_score", min_score)
            .order("rank", desc=False)
        )
        if recommendation:
            q = q.eq("overall_recommendation", recommendation)
        result = q.execute()
        rows = result.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch results: {str(e)}")

    if blind_mode:
        _REDACT = ["first_name", "last_name", "email", "phone"]
        rows = [{k: v for k, v in r.items() if k not in _REDACT} for r in rows]

    return {"job_id": job_id, "total": len(rows), "results": rows}


@router.get("/screen/weights")
async def get_screening_weights(db: SupabaseClient = None, current_user: CurrentUser = None,
                                job_id: Optional[str] = Query(None)):
    """Return job-specific weights, organization defaults, or system defaults."""
    from app.services.candidate_screening_service import DEFAULT_WEIGHTS
    org_id = _screening_org(db, current_user)
    rows = []
    if job_id:
        rows = (db.table("screening_weight_configs").select("*").eq("org_id", org_id)
                .eq("job_id", job_id).limit(1).execute()).data or []
    if not rows:
        try:
            rows = (db.table("screening_weight_configs").select("*").eq("org_id", org_id)
                    .is_("job_id", "null").limit(1).execute()).data or []
        except Exception:
            rows = []
    if rows:
        row = rows[0]
        return {"source": "job" if row.get("job_id") else "organization", "job_id": row.get("job_id"),
                "weights": {key: float(row[f"{key}_weight"]) for key in DEFAULT_WEIGHTS},
                "shortlist_threshold": float(row["shortlist_threshold"]),
                "reject_threshold": float(row["reject_threshold"])}
    return {"source": "system", "job_id": job_id, "weights": DEFAULT_WEIGHTS,
            "shortlist_threshold": 75, "reject_threshold": 45}


@router.put("/screen/weights")
async def save_screening_weights(body: ScreeningWeightsRequest, db: SupabaseClient = None,
                                 current_user: CurrentUser = None, job_id: Optional[str] = Query(None)):
    """Save auditable organization or job-specific deterministic scoring weights."""
    org_id = _screening_org(db, current_user)
    values = {"org_id": org_id, "job_id": job_id, "updated_by": current_user["sub"],
              **{f"{key}_weight": getattr(body, key) for key in ("skill", "experience", "language", "location", "salary", "availability")},
              "shortlist_threshold": body.shortlist_threshold, "reject_threshold": body.reject_threshold,
              "updated_at": datetime.now(timezone.utc).isoformat()}
    query = db.table("screening_weight_configs").select("id").eq("org_id", org_id)
    query = query.eq("job_id", job_id) if job_id else query.is_("job_id", "null")
    existing = query.limit(1).execute().data or []
    if existing:
        result = db.table("screening_weight_configs").update(values).eq("id", existing[0]["id"]).execute()
    else:
        result = db.table("screening_weight_configs").insert(values).execute()
    db.table("screening_decision_audit").insert({
        "org_id": org_id,
        "job_id": job_id, "action": "WEIGHTS_CHANGED", "new_value": values,
        "reason": "Recruiter updated deterministic scoring configuration", "actor_id": current_user["sub"],
    }).execute()
    return (result.data or [values])[0]


@router.patch("/screen/results/{result_id}/override")
async def override_screening_recommendation(result_id: str, body: ScreeningOverrideRequest,
                                            db: SupabaseClient = None, current_user: CurrentUser = None):
    """Record a reversible recruiter recommendation override; never changes deterministic score."""
    org_id = _screening_org(db, current_user)
    rows = (db.table("candidate_screening_results").select("*").eq("id", result_id)
            .eq("org_id", org_id).limit(1).execute()).data or []
    if not rows: raise HTTPException(status_code=404, detail="Screening result not found")
    previous = rows[0]
    now = datetime.now(timezone.utc).isoformat()
    values = {"recruiter_override": body.recommendation, "override_reason": body.reason,
              "overridden_by": current_user["sub"], "overridden_at": now,
              "recruiter_decision": "OVERRIDE_RECORDED" if body.recommendation else "OVERRIDE_CLEARED",
              "decision_by": current_user["sub"], "decision_at": now}
    db.table("candidate_screening_results").update(values).eq("id", result_id).eq("org_id", org_id).execute()
    db.table("screening_decision_audit").insert({
        "org_id": org_id, "screening_result_id": result_id, "candidate_id": previous["candidate_id"],
        "job_id": previous.get("job_id"), "action": "RECRUITER_OVERRIDE" if body.recommendation else "OVERRIDE_CLEARED",
        "previous_value": {"recommendation": previous.get("recruiter_override") or previous.get("overall_recommendation")},
        "new_value": {"recommendation": body.recommendation}, "reason": body.reason,
        "actor_id": current_user["sub"],
    }).execute()
    return {"result_id": result_id, "deterministic_score": previous.get("deterministic_score") or previous.get("total_score"), **values}


@router.get("/screen/audit")
async def get_screening_audit(db: SupabaseClient = None, current_user: CurrentUser = None,
                              candidate_id: Optional[str] = Query(None), job_id: Optional[str] = Query(None)):
    org_id = _screening_org(db, current_user)
    query = db.table("screening_decision_audit").select("*").eq("org_id", org_id).order("created_at", desc=True).limit(500)
    if candidate_id: query = query.eq("candidate_id", candidate_id)
    if job_id: query = query.eq("job_id", job_id)
    return {"audit": query.execute().data or []}


@router.post("/screen/job/{job_id}/shortlist")
async def shortlist_top_candidates(
    job_id: str,
    top_n: int = Query(10, ge=1, le=50),
    confirmed: bool = Query(False),
    reason: Optional[str] = Query(None, min_length=5, max_length=500),
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """
    Confirm top recommendations. Explicit recruiter confirmation and reason are mandatory.
    """
    user_id = current_user.get("sub", "")
    try:
        user_row = db.table("users").select("org_id").eq("id", user_id).single().execute()
        org_id = user_row.data.get("org_id") if user_row.data else None
    except Exception:
        org_id = None

    result = _auto_shortlist(
        supabase=db,
        job_id=job_id,
        job_role_id=None,
        org_id=org_id,
        top_n=top_n,
        confirmed_by=user_id if confirmed else None,
        reason=reason,
    )
    if result.get("requires_confirmation"):
        raise HTTPException(status_code=409, detail=result["message"])
    return result


@router.get("/screen/candidate/{candidate_id}/blind")
async def get_candidate_blind_profile(
    candidate_id: str,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Return a PII-stripped blind profile for a candidate."""
    org_id = _screening_org(db, current_user)
    try:
        row = db.table("candidates").select("*").eq("id", candidate_id).eq("org_id", org_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not row.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return get_blind_profile(row.data)


@router.get("/screen/cross-industry-map")
async def get_cross_industry_map(current_user: CurrentUser = None):
    """Return the India-specific cross-industry mapping table."""
    return {
        "cross_industry_map": {
            industry: {
                "maps_to":  data["maps_to"],
                "boost":    data["boost"],
                "note":     data["note"],
            }
            for industry, data in INDIA_CROSS_INDUSTRY_MAP.items()
        }
    }
