"""
Onboarding & Compliance repository (Module 5).
Pain #5: Compliance/onboarding drag → automate + track.
"""

from supabase import Client
from datetime import datetime
from typing import Optional


class OnboardingRepository:
    """Repository for tasks, flows, compliance checks."""

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create_onboarding_flow(
        self, candidate_id: str, job_id: str, user_id: str
    ) -> dict:
        """
        Initiate onboarding workflow (Pain #5).
        Pre-populate tasks based on job requirements.
        """
        data = {
            "candidate_id": candidate_id,
            "job_id": job_id,
            "org_id": user_id,
            "status": "not_started",
            "progress_percent": 0.0,
        }
        response = self.client.table("onboarding_flows").insert(data).execute()
        return response.data[0] if response.data else None

    async def create_compliance_task(
        self,
        candidate_id: str,
        job_id: str,
        task_type: str,
        due_date: datetime,
        user_id: str,
    ) -> dict:
        """
        Create compliance task (Pain #5).
        Tasks: background check, ServSafe, food handler, DUI, references.
        """
        data = {
            "candidate_id": candidate_id,
            "job_id": job_id,
            "task_type": task_type,
            "status": "pending",
            "due_date": due_date.isoformat(),
            "org_id": user_id,
        }
        response = self.client.table("compliance_tasks").insert(data).execute()
        return response.data[0] if response.data else None

    async def get_onboarding_status(
        self, candidate_id: str, user_id: str
    ) -> Optional[dict]:
        """Fetch onboarding flow with all tasks."""
        response = (
            self.client.table("onboarding_flows")
            .select("*, compliance_tasks(*)")
            .eq("candidate_id", candidate_id)
            .eq("org_id", user_id)
            .single()
            .execute()
        )
        return response.data

    async def update_task_status(
        self, task_id: str, status: str, result: Optional[dict], user_id: str
    ) -> dict:
        """Update compliance task status (Pain #5)."""
        data = {"status": status, "result": result}
        response = (
            self.client.table("compliance_tasks")
            .update(data)
            .eq("id", task_id)
            .eq("org_id", user_id)
            .execute()
        )
        return response.data[0] if response.data else None

    async def get_pending_tasks_for_job(
        self, job_id: str, user_id: str
    ) -> list[dict]:
        """
        Get all pending compliance tasks for a job
        (Pain #5: manager dashboard visibility).
        """
        response = (
            self.client.table("compliance_tasks")
            .select("*")
            .eq("job_id", job_id)
            .eq("org_id", user_id)
            .eq("status", "pending")
            .order("due_date", desc=False)
            .execute()
        )
        return response.data
