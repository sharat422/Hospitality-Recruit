"""
Talent pool repository (Module 7).
Pain #4: Talent evaporates between seasons → engagement campaigns.
"""

from supabase import Client
from datetime import datetime
from typing import Optional


class TalentPoolRepository:
    """Repository for talent pool cohorts + retention."""

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create_cohort(
        self, cohort_name: str, season: str, user_id: str
    ) -> dict:
        """
        Create talent pool cohort (Pain #4: seasonal hiring).
        E.g., "Summer 2026", "Holiday 2025".
        """
        data = {
            "cohort_name": cohort_name,
            "season": season,
            "org_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
        }
        response = self.client.table("talent_cohorts").insert(data).execute()
        return response.data[0] if response.data else None

    async def get_cohort_candidates(
        self, cohort_id: str, user_id: str
    ) -> list[dict]:
        """Get all candidates in a cohort (Pain #4)."""
        response = (
            self.client.table("candidates")
            .select("*")
            .eq("cohort_id", cohort_id)
            .eq("org_id", user_id)
            .execute()
        )
        return response.data

    async def create_engagement_campaign(
        self,
        cohort_id: str,
        message: str,
        channel: str,
        scheduled_date: datetime,
        user_id: str,
    ) -> dict:
        """
        Create off-season engagement campaign (Pain #4).
        Channel: SMS, email, push.
        """
        data = {
            "cohort_id": cohort_id,
            "message": message,
            "channel": channel,
            "scheduled_date": scheduled_date.isoformat(),
            "org_id": user_id,
            "status": "scheduled",
        }
        response = (
            self.client.table("engagement_campaigns").insert(data).execute()
        )
        return response.data[0] if response.data else None

    async def get_active_campaigns(self, user_id: str) -> list[dict]:
        """Fetch all active/scheduled engagement campaigns."""
        response = (
            self.client.table("engagement_campaigns")
            .select("*")
            .eq("org_id", user_id)
            .in_("status", ["scheduled", "in_progress"])
            .execute()
        )
        return response.data
