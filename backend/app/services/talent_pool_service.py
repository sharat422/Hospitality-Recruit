"""
Talent pool retention service (Module 7).
Pain #4: Talent pool evaporates between seasons → engagement campaigns.
"""

from app.repositories.talent_pool_repo import TalentPoolRepository
from app.services.sms_service import SMSService
from datetime import datetime, timedelta
from typing import Optional


class TalentPoolService:
    """Off-season engagement + cohort retention (Pain #4)."""

    def __init__(
        self, talent_repo: TalentPoolRepository, sms_service: SMSService
    ):
        self.repo = talent_repo
        self.sms_service = sms_service

    async def create_seasonal_cohort(
        self, cohort_name: str, season: str, user_id: str
    ) -> dict:
        """
        Create talent pool cohort for season (Pain #4).
        Example: "Summer 2026" - track and re-engage this group.
        """
        cohort = await self.repo.create_cohort(cohort_name, season, user_id)
        return cohort

    async def launch_engagement_campaign(
        self,
        cohort_id: str,
        campaign_name: str,
        message: str,
        channel: str,
        user_id: str,
    ) -> dict:
        """
        Launch off-season engagement (Pain #4).
        Goals: stay top-of-mind, re-engage for next season.
        """
        # Get candidates in cohort
        candidates = await self.repo.get_cohort_candidates(cohort_id, user_id)

        # Create campaign
        campaign = await self.repo.create_engagement_campaign(
            cohort_id,
            message,
            channel,
            datetime.utcnow() + timedelta(hours=1),  # Send soon
            user_id,
        )

        # Send messages (Celery job for scale)
        sent_count = 0
        if channel == "sms":
            for candidate in candidates:
                try:
                    await self.sms_service.send_sms(
                        candidate["phone"], message
                    )
                    sent_count += 1
                except:
                    pass

        return {
            "campaign_id": campaign["id"],
            "sent_count": sent_count,
            "cohort_size": len(candidates),
        }

    async def get_retention_metrics(
        self, season: str, user_id: str
    ) -> dict:
        """
        Retention metrics for a season (Pain #4).
        Track: active candidates, re-hire rate, time since last engagement.
        """
        # Simplified
        return {
            "season": season,
            "total_candidates": 0,
            "re_hired_percent": 0.0,
            "avg_days_since_engagement": 0,
        }
