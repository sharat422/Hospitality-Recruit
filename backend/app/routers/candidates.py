"""
Candidate routes (Module 1, 3, 7).
Pain #1: Handle 100-500 applications efficiently (bulk create, screen, list qualified).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import get_current_user
from app.core.dependencies import SupabaseClient
from app.schemas import CandidateCreate, CandidateRead
from app.repositories.candidate_repo import CandidateRepository
from typing import Optional, Annotated

router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.post("/", response_model=dict)
async def create_candidate(
    candidate: CandidateCreate,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """
    Create candidate from SMS/web form (Pain #1: bulk inbound).
    RLS ensures org isolation.
    """
    repo = CandidateRepository(supabase)
    result = await repo.create_candidate(candidate, user["sub"])
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create candidate")
    return result


@router.get("/{candidate_id}", response_model=dict)
async def get_candidate(
    candidate_id: str,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """Get candidate by ID."""
    repo = CandidateRepository(supabase)
    result = await repo.get_candidate(candidate_id, user["sub"])
    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return result


@router.get("/job/{job_id}")
async def list_candidates_for_job(
    job_id: str,
    user: CurrentUser,
    supabase: SupabaseClient,
    limit: int = 100,
    offset: int = 0,
):
    """
    List all candidates for a job (Pain #1: bulk screening prep).
    """
    repo = CandidateRepository(supabase)
    candidates = await repo.list_candidates_for_job(job_id, user["sub"], limit, offset)
    return {"count": len(candidates), "candidates": candidates}


@router.get("/job/{job_id}/qualified")
async def get_qualified_candidates(
    job_id: str,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """
    Get only qualified candidates (Pain #1: reduce 65% screening time).
    Pre-filtered by AI screening.
    """
    repo = CandidateRepository(supabase)
    candidates = await repo.get_qualified_candidates(job_id, user["sub"])
    return {"count": len(candidates), "candidates": candidates}


@router.put("/{candidate_id}/availability")
async def update_availability(
    candidate_id: str,
    availability: list,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """
    Update candidate availability from mobile portal (Pain #2).
    Data format: [{day: "Monday", start: "09:00", end: "17:00"}, ...]
    """
    repo = CandidateRepository(supabase)
    result = await repo.bulk_update_availability(candidate_id, availability, user["sub"])
    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return result
