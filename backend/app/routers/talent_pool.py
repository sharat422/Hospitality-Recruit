"""
Talent pool & retention routes (Module 7).
Pain #4: Talent pool evaporates between seasons → engagement campaigns.
"""

from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.core.dependencies import SupabaseClient
from app.services.talent_pool_service import TalentPoolService
from app.services.sms_service import SMSService
from app.repositories.talent_pool_repo import TalentPoolRepository

router = APIRouter()


@router.post("/cohort/create")
async def create_talent_cohort(
    cohort_name: str,
    season: str,
    supabase: SupabaseClient,
    user: dict = Depends(get_current_user),
):
    """
    Create talent pool cohort (Pain #4).
    Example: "Summer 2026" - track and re-engage this seasonal group.
    """
    talent_repo = TalentPoolRepository(supabase)
    sms_service = SMSService()
    service = TalentPoolService(talent_repo, sms_service)
    
    cohort = await service.create_seasonal_cohort(cohort_name, season, user["sub"])
    
    return cohort


@router.get("/cohort/{cohort_id}/candidates")
async def get_cohort_candidates(
    cohort_id: str,
    supabase: SupabaseClient,
    user: dict = Depends(get_current_user),
):
    """Get all candidates in a talent cohort (Pain #4)."""
    talent_repo = TalentPoolRepository(supabase)
    
    candidates = await talent_repo.get_cohort_candidates(cohort_id, user["sub"])
    
    return {
        "cohort_id": cohort_id,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


@router.post("/campaign/launch")
async def launch_engagement_campaign(
    cohort_id: str,
    campaign_name: str,
    message: str,
    channel: str,  # sms, email, push
    supabase: SupabaseClient,
    user: dict = Depends(get_current_user),
):
    """
    Launch off-season engagement campaign (Pain #4).
    Goal: keep candidates warm, increase re-hire rate between seasons.
    """
    talent_repo = TalentPoolRepository(supabase)
    sms_service = SMSService()
    service = TalentPoolService(talent_repo, sms_service)
    
    result = await service.launch_engagement_campaign(
        cohort_id, campaign_name, message, channel, user["sub"]
    )
    
    return result


@router.get("/retention-metrics")
async def get_retention_metrics(
    season: str,
    supabase: SupabaseClient,
    user: dict = Depends(get_current_user),
):
    """
    Retention metrics for season (Pain #4).
    Tracks: total candidates, re-hire rate, time since last engagement.
    """
    talent_repo = TalentPoolRepository(supabase)
    sms_service = SMSService()
    service = TalentPoolService(talent_repo, sms_service)
    
    metrics = await service.get_retention_metrics(season, user["sub"])
    
    return metrics
