"""
Onboarding & compliance service (Module 5).
Pain #5: Compliance/onboarding drag (ServSafe, background checks, uniforms, multi-state laws).
"""

from app.repositories.onboarding_repo import OnboardingRepository
from app.core.exceptions import ComplianceException
from datetime import datetime, timedelta
from typing import Optional
import asyncio


class OnboardingService:
    """Automate onboarding tasks + compliance workflows."""

    def __init__(self, onboarding_repo: OnboardingRepository):
        self.repo = onboarding_repo

    async def init_onboarding_flow(
        self, candidate_id: str, job_id: str, user_id: str, job_role: str
    ) -> dict:
        """
        Initialize onboarding (Pain #5).
        Auto-populate tasks based on role + jurisdiction compliance requirements.
        """
        # Create flow
        flow = await self.repo.create_onboarding_flow(candidate_id, job_id, user_id)

        # Generate task list based on role compliance matrix
        tasks = await self._generate_compliance_tasks(
            candidate_id, job_id, job_role, user_id
        )

        return {
            "flow_id": flow["id"],
            "candidate_id": candidate_id,
            "tasks": tasks,
            "estimated_days": 5,  # Typical time to complete (Pain #5 goal: reduce this)
        }

    async def _generate_compliance_tasks(
        self, candidate_id: str, job_id: str, job_role: str, user_id: str
    ) -> list[dict]:
        """
        Generate compliance task list (Pain #5).
        Matrix: role × state × company policy.
        """
        # Simplified matrix for hospitality
        task_types = [
            "background_check",
            "food_handler",  # Most hospitality roles require
            "reference_check",
        ]

        # Add ServSafe if applicable
        if "manager" in job_role.lower() or "supervisor" in job_role.lower():
            task_types.append("servsafe")

        # Generate tasks with due dates
        tasks = []
        due_base = datetime.utcnow() + timedelta(days=3)  # Pain #5: aggressive timeline

        for idx, task_type in enumerate(task_types):
            due_date = due_base + timedelta(days=idx)
            task = await self.repo.create_compliance_task(
                candidate_id, job_id, task_type, due_date, user_id
            )
            tasks.append(task)

        return tasks

    async def get_pending_compliance(self, user_id: str, days: int = 3) -> dict:
        """
        Dashboard view of overdue/pending compliance (Pain #5, Pain #3).
        Helps managers track compliance status (reduce burnout).
        """
        # In production, query all pending tasks, group by status
        return {
            "pending_count": 0,
            "overdue_count": 0,
            "at_risk_candidates": [],  # Candidates that may not onboard in time
        }

    async def automate_task_completion(
        self, task_id: str, task_type: str, user_id: str
    ) -> dict:
        """
        Attempt to auto-complete task via integration (Pain #5).
        Example: background check via third-party API.
        """
        # Placeholder for integrations to background check provider, etc
        result = {
            "status": "pending",
            "result": {"verified": False},
        }

        await self.repo.update_task_status(task_id, "in_progress", result, user_id)
        return result
