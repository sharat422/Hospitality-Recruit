"""
Shift & matching routes (Module 2).
Pain #2: Seasonal chaos + 70% no-show → availability-based matching.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated
from app.core.security import get_current_user
from app.core.dependencies import SupabaseClient
from app.services.shift_service import ShiftMatchingService
from app.repositories.shift_repo import ShiftRepository
from app.repositories.candidate_repo import CandidateRepository
from datetime import datetime
from typing import Optional

router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.post("/create")
async def create_shift(
    job_id: str,
    role: str,
    shift_type: str,
    start_date: str,
    end_date: str,
    hours_per_week: float,
    user: CurrentUser,
    supabase: SupabaseClient,
    urgency: str = "normal",
):
    """Create a new shift (Pain #2: track seasonal demand)."""
    shift_repo = ShiftRepository(supabase)

    shift_data = {
        "job_id": job_id,
        "role": role,
        "shift_type": shift_type,
        "start_date": start_date,
        "end_date": end_date,
        "hours_per_week": hours_per_week,
        "urgency": urgency,
    }

    result = await shift_repo.create_shift(shift_data, user["sub"])
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create shift")
    return result


@router.get("/open")
async def list_open_shifts(
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """Get all open shifts (Pain #2: urgent fills)."""
    shift_repo = ShiftRepository(supabase)
    shifts = await shift_repo.get_open_shifts(user["sub"])
    return {"count": len(shifts), "shifts": shifts}


@router.post("/{candidate_id}/match")
async def get_shift_matches(
    candidate_id: str,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """
    Find best shift matches for candidate (Pain #2).
    Considers availability, role match, geography, urgency.
    """
    shift_repo = ShiftRepository(supabase)
    candidate_repo = CandidateRepository(supabase)
    matching_service = ShiftMatchingService(shift_repo, candidate_repo)

    matches = await matching_service.match_candidate_to_shifts(candidate_id, user["sub"])

    return {
        "candidate_id": candidate_id,
        "match_count": len(matches),
        "matches": matches,
    }


@router.get("/season/{season}")
async def get_seasonal_shifts(
    season: str,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """
    Get shifts for specific season (Pain #2).
    Example: "summer_2026", "holiday_2025".
    Helps track seasonal spikes.
    """
    shift_repo = ShiftRepository(supabase)
    shifts = await shift_repo.get_seasonal_shifts(season, user["sub"])

    return {
        "season": season,
        "shift_count": len(shifts),
        "total_positions": sum(s.get("positions_available", 1) for s in shifts),
        "shifts": shifts,
    }


@router.post("/bulk-match")
async def bulk_match_candidates_to_shifts(
    shift_id: str,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """
    Bulk match all qualified candidates to a shift (Pain #2).
    Returns top N matches ranked by score.
    """
    shift_repo = ShiftRepository(supabase)
    candidate_repo = CandidateRepository(supabase)
    matching_service = ShiftMatchingService(shift_repo, candidate_repo)

    # In production: get shift, find all qualified, match all
    # Simplified for now

    return {
        "shift_id": shift_id,
        "matches_found": 0,
    }
