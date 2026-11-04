"""
Analytics & Dashboard repository (Module 6).
Pain #3: Manager burnout → real-time visibility + automation.
"""

from supabase import Client
from typing import Optional
from datetime import datetime, timedelta


class AnalyticsRepository:
    """Repository for dashboard metrics and analytics."""

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def get_job_metrics(self, job_id: str, user_id: str) -> dict:
        """
        Get dashboard metrics for a job (Pain #3).
        Total apps, qualified, avg score, pipeline counts, fill rate.
        """
        candidates = (
            self.client.table("candidates")
            .select("*")
            .eq("job_id", job_id)
            .eq("org_id", user_id)
            .execute()
        ).data

        qualified = [c for c in candidates if c.get("qualified", False)]
        screens = [c.get("screening_result", {}) for c in candidates if c.get("screening_result")]
        avg_score = (
            sum(s.get("ai_score", 0) for s in screens) / len(screens)
            if screens
            else 0.0
        )

        return {
            "total_applications": len(candidates),
            "qualified_candidates": len(qualified),
            "avg_qualification_score": avg_score,
            "job_id": job_id,
        }

    async def get_pipeline_stages(self, job_id: str, user_id: str) -> list[dict]:
        """
        Get candidate counts by pipeline stage (Pain #3).
        Stages: applied, screened, interviewed, offered, accepted, filled.
        """
        response = (
            self.client.table("candidates")
            .select("pipeline_stage")
            .eq("job_id", job_id)
            .eq("org_id", user_id)
            .execute()
        )
        candidates = response.data

        stages = {}
        for c in candidates:
            stage = c.get("pipeline_stage", "applied")
            stages[stage] = stages.get(stage, 0) + 1

        return [{"stage": stage, "count": count} for stage, count in stages.items()]

    async def calculate_avg_fill_time(self, user_id: str, days: int = 30) -> float:
        """
        Calculate average days to fill (metric for Cost Per Hire - Pain #1).
        """
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        response = (
            self.client.table("candidates")
            .select("created_at, accepted_at")
            .eq("org_id", user_id)
            .gt("accepted_at", since)
            .execute()
        )
        candidates = response.data

        if not candidates:
            return 0.0

        total_days = 0
        for c in candidates:
            if c.get("accepted_at"):
                created = datetime.fromisoformat(c["created_at"])
                accepted = datetime.fromisoformat(c["accepted_at"])
                total_days += (accepted - created).days

        return total_days / len(candidates)

    async def get_no_show_rate(self, user_id: str, days: int = 30) -> float:
        """
        Calculate no-show rate (Pain #2: 70% no-show).
        """
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        response = (
            self.client.table("shift_matches")
            .select("*")
            .eq("org_id", user_id)
            .gt("created_at", since)
            .execute()
        )
        shifts = response.data

        if not shifts:
            return 0.0

        no_shows = sum(1 for s in shifts if s.get("status") == "no_show")
        return (no_shows / len(shifts)) * 100 if shifts else 0.0
