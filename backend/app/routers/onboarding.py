"""
Onboarding & compliance routes (Module 5).
Pain #5: Compliance/onboarding drag → automate workflow.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated, Optional
from app.core.security import get_current_user
from app.core.dependencies import SupabaseClient
from app.services.onboarding_service import OnboardingService
from app.repositories.onboarding_repo import OnboardingRepository
from datetime import datetime

router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.post("/{candidate_id}/{job_id}/init-flow")
async def init_onboarding_flow(
    candidate_id: str,
    job_id: str,
    job_role: str,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """
    Initialize onboarding workflow (Pain #5).
    Auto-populates compliance checklist: background check, ServSafe, food handler, etc.
    """
    onboarding_repo = OnboardingRepository(supabase)
    service = OnboardingService(onboarding_repo)

    result = await service.init_onboarding_flow(candidate_id, job_id, user["sub"], job_role)

    return result


@router.get("/{candidate_id}/status")
async def get_onboarding_status(
    candidate_id: str,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """
    Get onboarding status with all tasks (Pain #5, Pain #3).
    Managers track compliance, see bottlenecks.
    """
    onboarding_repo = OnboardingRepository(supabase)

    status = await onboarding_repo.get_onboarding_status(candidate_id, user["sub"])
    if not status:
        raise HTTPException(status_code=404, detail="No onboarding flow found")

    return status


@router.post("/task/{task_id}/complete")
async def mark_task_complete(
    task_id: str,
    user: CurrentUser,
    supabase: SupabaseClient,
    result: Optional[dict] = None,
):
    """
    Mark compliance task complete (Pain #5).
    Result payload varies by task type:
    - background_check: {verified: bool, report_url: str}
    - servsafe: {passed: bool, cert_date: str}
    - etc.
    """
    onboarding_repo = OnboardingRepository(supabase)

    updated = await onboarding_repo.update_task_status(
        task_id, "completed", result, user["sub"]
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")

    return updated


@router.get("/job/{job_id}/pending")
async def get_pending_tasks_dashboard(
    job_id: str,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """
    Dashboard: pending compliance tasks for a job (Pain #5, Pain #3).
    Helps managers track candidates at risk of delayed onboarding.
    """
    onboarding_repo = OnboardingRepository(supabase)

    tasks = await onboarding_repo.get_pending_tasks_for_job(job_id, user["sub"])

    overdue = [t for t in tasks if datetime.fromisoformat(t["due_date"]) < datetime.utcnow()]

    return {
        "job_id": job_id,
        "total_pending": len(tasks),
        "overdue_count": len(overdue),
        "tasks": tasks,
    }
