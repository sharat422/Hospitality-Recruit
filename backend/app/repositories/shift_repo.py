"""
Shift & Shift Match repository (Module 2).
Pain #2: Seasonal chaos → accurate shift matching critical.
"""

from supabase import Client
from typing import Optional
from datetime import datetime


class ShiftRepository:
    """Repository for shifts and shift matches."""

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    def _org_id(self, user_id: str) -> str:
        response = self.client.table("users").select("org_id").eq("id", user_id).limit(1).execute()
        if not response.data or not response.data[0].get("org_id"):
            raise ValueError("User is not assigned to an organization")
        return response.data[0]["org_id"]

    async def create_shift(self, shift_data: dict, user_id: str) -> dict:
        """Create new shift (Pain #2: track seasonal demand)."""
        shift_data["org_id"] = self._org_id(user_id)
        response = self.client.table("shifts").insert(shift_data).execute()
        return response.data[0] if response.data else None

    async def get_open_shifts(self, user_id: str) -> list[dict]:
        """Fetch all open shifts for org."""
        response = (
            self.client.table("shifts")
            .select("*")
            .eq("org_id", self._org_id(user_id))
            .gt("end_date", datetime.utcnow().isoformat())
            .execute()
        )
        return response.data

    async def get_seasonal_shifts(self, season: str, user_id: str) -> list[dict]:
        """Fetch shifts for specific season (summer/holiday spike - Pain #2)."""
        response = (
            self.client.table("shifts")
            .select("*")
            .eq("org_id", self._org_id(user_id))
            .eq("season", season)
            .execute()
        )
        return response.data

    async def create_shift_match(
        self, candidate_id: str, shift_id: str, score: float, user_id: str
    ) -> dict:
        """
        Create candidate-to-shift match.
        Pain #2: 70% no-show rate → availability matching reduces this.
        """
        data = {
            "candidate_id": candidate_id,
            "shift_id": shift_id,
            "match_score": score,
            "org_id": self._org_id(user_id),
        }
        response = self.client.table("shift_matches").insert(data).execute()
        return response.data[0] if response.data else None

    async def get_candidate_shift_recommendations(
        self, candidate_id: str, user_id: str, limit: int = 10
    ) -> list[dict]:
        """Get best matching shifts for candidate (Pain #2)."""
        response = (
            self.client.table("shift_matches")
            .select("*")
            .eq("candidate_id", candidate_id)
            .eq("org_id", self._org_id(user_id))
            .order("match_score", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data
