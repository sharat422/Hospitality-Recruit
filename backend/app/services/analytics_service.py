"""
Analytics & dashboard service (Module 6).
Pain #3: Manager burnout & slow fills → real-time visibility + KPIs.
"""

from app.repositories.analytics_repo import AnalyticsRepository
from typing import Optional


class AnalyticsService:
    """Dashboard metrics + real-time KPI tracking (Pain #3, Pain #1)."""

    def __init__(self, analytics_repo: AnalyticsRepository):
        self.repo = analytics_repo

    async def get_manager_dashboard(self, user_id: str) -> dict:
        """
        Manager dashboard (Pain #3: reduce burnout via visibility).
        High-level KPIs: applications, qualified, avg time-to-fill, no-show rate.
        """
        # In production, get recent job_ids for manager
        # For now, return sample structure

        return {
            "total_active_jobs": 0,
            "total_applications": 0,
            "total_qualified": 0,
            "avg_qualification_score": 0.0,
            "avg_fill_time_days": 0.0,
            "no_show_rate_percent": 0.0,
            "pipeline_summary": [],  # breakdown by stage
            "alerts": [],  # e.g., "Shift on 2026-04-20 unfilled"
        }

    async def get_job_pipeline(self, job_id: str, user_id: str) -> dict:
        """
        Pipeline breakdown for a specific job (Pain #3).
        Stages: applied → screened → interviewed → offered → accepted → filled.
        """
        stages = await self.repo.get_pipeline_stages(job_id, user_id)

        return {
            "job_id": job_id,
            "stages": stages,
            "total_candidates": sum(s["count"] for s in stages),
            "bottleneck_stage": self._identify_bottleneck(stages),
        }

    def _identify_bottleneck(self, stages: list[dict]) -> Optional[str]:
        """Find slowest pipeline stage (Pain #3)."""
        if not stages:
            return None
        slowest = max(stages, key=lambda s: s.get("avg_days_in_stage", 0))
        return slowest.get("stage")

    async def calculate_cost_per_hire(self, org_id: str, days: int = 90) -> dict:
        """
        Calculate cost-per-hire metric (Pain #1: 40% higher than industry avg).
        Formula: (recruiter costs + tools + compliance) / (successful hires)
        """
        avg_fill_time = await self.repo.calculate_avg_fill_time(org_id, days)

        # Simplified: assume industry avg = 18 days, our target = 12 days
        industry_avg = 18.0
        efficiency_ratio = industry_avg / max(avg_fill_time, 1.0)

        return {
            "avg_fill_time_days": avg_fill_time,
            "industry_average_days": industry_avg,
            "efficiency_ratio": efficiency_ratio,  # >1.0 = beating industry
            "estimated_cost_per_hire": 1200.0 * (1.0 / efficiency_ratio),  # Placeholder
        }

    async def get_no_show_analysis(self, org_id: str, days: int = 30) -> dict:
        """
        Analyze no-show rate (Pain #2: 70% no-show).
        Track correlation with matching quality, SMS engagement, etc.
        """
        no_show_rate = await self.repo.get_no_show_rate(org_id, days)

        return {
            "no_show_rate_percent": no_show_rate,
            "industry_average_percent": 70.0,  # Current benchm
            "goal_percent": 40.0,  # Target for HospRecruit
            "estimated_lost_productivity": f"${no_show_rate * 150}",  # Rough cost
        }
