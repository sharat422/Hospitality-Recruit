"""
AI Matching Router — 6 AI-powered candidate matching & screening features.

Features exposed:
  1. POST /parse-resume       — AI resume parsing + fit scoring
  2. POST /rank-candidates    — Score & rank candidates against a job
  3. GET  /skill-taxonomy     — Full hospitality skill taxonomy (static)
  4. POST /generate-jd        — Bias-free JD generator
  5. POST /reactivation-candidates — Surface & re-engage past candidates
  6. POST /discover-passive   — Score passive candidates for engagement likelihood
"""

from typing import Annotated, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.dependencies import get_supabase_client, SupabaseClient
from app.core.security import get_current_user
from app.services.ai_matching_service import AIMatchingService, HOSPITALITY_TAXONOMY

router = APIRouter(tags=["AI Matching"])

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ParseResumeRequest(BaseModel):
    resume_text: str
    job_id: Optional[str] = None
    job_requirements: Optional[str] = None


class RankCandidatesRequest(BaseModel):
    job_requirements: str
    candidate_ids: list[str]
    use_ai: bool = True


class GenerateJDRequest(BaseModel):
    role: str
    location: str
    experience_level: str
    perks: Optional[list[str]] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None


class ReactivationRequest(BaseModel):
    job_requirements: str
    limit: Optional[int] = 20


class DiscoverPassiveRequest(BaseModel):
    role: str
    skills: list[str]


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

CurrentUser = Annotated[dict, Depends(get_current_user)]


def _get_service() -> AIMatchingService:
    return AIMatchingService()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/parse-resume")
async def parse_resume(
    request: ParseResumeRequest,
    user: CurrentUser,
    supabase: SupabaseClient,
) -> dict:
    """
    Parse CV text with Claude, extract structured profile & fit score.

    If job_id is provided the job's requirements are fetched from Supabase
    and used for scoring. Alternatively supply job_requirements directly.
    """
    service = _get_service()

    job_requirements = request.job_requirements

    # Optionally fetch job requirements from DB
    if request.job_id and not job_requirements:
        try:
            resp = supabase.table("jobs").select("title, requirements, description").eq(
                "id", request.job_id
            ).single().execute()
            if resp.data:
                j = resp.data
                job_requirements = f"{j.get('title', '')}\n{j.get('requirements', '')}\n{j.get('description', '')}"
        except Exception:
            pass  # Proceed without job context

    try:
        result = await service.parse_resume(request.resume_text, job_requirements)
        return {"status": "ok", "parsed_profile": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Resume parsing failed: {exc}")


@router.post("/rank-candidates")
async def rank_candidates(
    request: RankCandidatesRequest,
    user: CurrentUser,
    supabase: SupabaseClient,
) -> dict:
    """
    Fetch candidates from Supabase by IDs, rank them via Claude.

    Returns sorted list: rank, candidate_id, name, score, reasoning,
    strengths, gaps.
    """
    if not request.candidate_ids:
        raise HTTPException(status_code=400, detail="candidate_ids must not be empty")

    # Fetch candidate records from Supabase
    try:
        resp = supabase.table("candidates").select(
            "id, first_name, last_name, email, phone, pipeline_stage, "
            "extracted_data, location, source, created_at"
        ).in_("id", request.candidate_ids).execute()
        candidates = resp.data or []
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch candidates: {exc}")

    if not candidates:
        return {"status": "ok", "ranked_candidates": [], "total": 0}

    # Flatten candidate data for AI
    flattened = []
    for c in candidates:
        extracted = c.get("extracted_data") or {}
        flattened.append({
            "id": c["id"],
            "name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
            "email": c.get("email"),
            "location": c.get("location"),
            "pipeline_stage": c.get("pipeline_stage"),
            "source": c.get("source"),
            "skills": extracted.get("skills", []),
            "experience_years": extracted.get("experience_years"),
            "roles_held": extracted.get("roles_held", []),
            "hospitality_experience": extracted.get("hospitality_experience"),
        })

    service = _get_service()

    if request.use_ai:
        try:
            ranked = await service.rank_candidates(request.job_requirements, flattened)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"AI ranking failed: {exc}")
    else:
        # Simple keyword match fallback
        job_lower = request.job_requirements.lower()
        scored = []
        for c in flattened:
            skills = [s.lower() for s in c.get("skills", [])]
            matches = sum(1 for s in skills if s in job_lower)
            scored.append({**c, "score": min(matches * 10, 100), "reasoning": "Keyword match", "strengths": [], "gaps": []})
        ranked = sorted(scored, key=lambda x: x["score"], reverse=True)
        for i, r in enumerate(ranked, 1):
            r["rank"] = i
            r["candidate_id"] = r["id"]

    return {"status": "ok", "ranked_candidates": ranked, "total": len(ranked)}


@router.get("/skill-taxonomy")
async def get_skill_taxonomy() -> dict:
    """
    Return the full hospitality skill taxonomy (static data, no auth required
    for discovery but included in protected router for consistency).
    """
    return {
        "status": "ok",
        "taxonomy": HOSPITALITY_TAXONOMY,
        "roles": list(HOSPITALITY_TAXONOMY["roles"].keys()),
        "transferable_industries": list(HOSPITALITY_TAXONOMY["transferable_industries"].keys()),
    }


@router.post("/generate-jd")
async def generate_jd(
    request: GenerateJDRequest,
    user: CurrentUser,
) -> dict:
    """
    Generate a bias-free hospitality job description with Claude.
    """
    salary_range: Optional[str] = None
    if request.salary_min and request.salary_max:
        salary_range = f"${request.salary_min:,} – ${request.salary_max:,} per year"
    elif request.salary_min:
        salary_range = f"From ${request.salary_min:,} per year"
    elif request.salary_max:
        salary_range = f"Up to ${request.salary_max:,} per year"

    service = _get_service()
    try:
        jd = await service.generate_jd(
            role=request.role,
            location=request.location,
            experience_level=request.experience_level,
            perks=request.perks or [],
            salary_range=salary_range,
        )
        return {"status": "ok", "job_description": jd}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"JD generation failed: {exc}")


@router.post("/reactivation-candidates")
async def reactivation_candidates(
    request: ReactivationRequest,
    user: CurrentUser,
    supabase: SupabaseClient,
) -> dict:
    """
    Surface past candidates from Supabase and score them for re-engagement.

    Fetches candidates that are not in 'active' pipeline stages,
    scores each for reactivation fit, returns ranked list with
    personalized re-engagement message per candidate.
    """
    org_id = user.get("org_id")
    limit = min(request.limit or 20, 50)  # Cap at 50 for performance

    try:
        query = supabase.table("candidates").select(
            "id, first_name, last_name, email, phone, pipeline_stage, "
            "extracted_data, location, source, created_at, updated_at"
        ).not_.in_("pipeline_stage", ["active", "hired"])

        if org_id:
            query = query.eq("org_id", org_id)

        resp = query.order("updated_at", desc=False).limit(limit).execute()
        candidates = resp.data or []
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch candidates: {exc}")

    if not candidates:
        return {"status": "ok", "reactivation_candidates": [], "total": 0}

    service = _get_service()
    results = []
    for c in candidates:
        extracted = c.get("extracted_data") or {}
        candidate_payload = {
            "id": c["id"],
            "name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
            "email": c.get("email"),
            "location": c.get("location"),
            "pipeline_stage": c.get("pipeline_stage"),
            "skills": extracted.get("skills", []),
            "experience_years": extracted.get("experience_years"),
            "roles_held": extracted.get("roles_held", []),
            "last_active": c.get("updated_at") or c.get("created_at"),
        }
        try:
            scored = await service.score_for_reactivation(
                candidate_payload, request.job_requirements
            )
            scored["last_active"] = candidate_payload["last_active"]
            scored["name"] = candidate_payload["name"]
            scored["email"] = candidate_payload["email"]
            results.append(scored)
        except Exception:
            # Skip individual failures; don't crash the whole batch
            continue

    # Sort by reactivation_score descending
    results.sort(key=lambda x: x.get("reactivation_score", 0), reverse=True)

    return {
        "status": "ok",
        "reactivation_candidates": results,
        "total": len(results),
    }


@router.post("/discover-passive")
async def discover_passive(
    request: DiscoverPassiveRequest,
    user: CurrentUser,
    supabase: SupabaseClient,
) -> dict:
    """
    Discover and score passive candidates (status != 'active') for
    engagement likelihood based on role and skills.
    """
    org_id = user.get("org_id")

    try:
        query = supabase.table("candidates").select(
            "id, first_name, last_name, email, phone, pipeline_stage, "
            "extracted_data, location, source, created_at, updated_at"
        ).not_.in_("pipeline_stage", ["active", "hired"])

        if org_id:
            query = query.eq("org_id", org_id)

        resp = query.limit(30).execute()
        candidates = resp.data or []
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch passive candidates: {exc}")

    if not candidates:
        return {"status": "ok", "passive_candidates": [], "total": 0}

    service = _get_service()
    results = []
    for c in candidates:
        extracted = c.get("extracted_data") or {}
        candidate_payload = {
            "id": c["id"],
            "name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
            "location": c.get("location"),
            "pipeline_stage": c.get("pipeline_stage"),
            "skills": extracted.get("skills", []),
            "experience_years": extracted.get("experience_years"),
            "roles_held": extracted.get("roles_held", []),
            "last_active": c.get("updated_at") or c.get("created_at"),
        }
        try:
            scored = await service.score_passive_candidate(
                candidate_payload, request.role, request.skills
            )
            scored["name"] = candidate_payload["name"]
            scored["last_active"] = candidate_payload["last_active"]
            results.append(scored)
        except Exception:
            continue

    results.sort(key=lambda x: x.get("passive_score", 0), reverse=True)

    return {
        "status": "ok",
        "passive_candidates": results,
        "total": len(results),
    }
