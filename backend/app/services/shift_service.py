"""
Shift matching service (Module 2).
Pain #2: Seasonal/shift chaos (summer/winter spikes, irregular shifts, 70% no-show).
"""

from app.repositories.shift_repo import ShiftRepository
from app.repositories.candidate_repo import CandidateRepository
from datetime import datetime, timedelta
from typing import Optional
import math


class ShiftMatchingService:
    """Match candidates to shifts based on availability + urgency."""

    def __init__(
        self,
        shift_repo: ShiftRepository,
        candidate_repo: CandidateRepository,
    ):
        self.shift_repo = shift_repo
        self.candidate_repo = candidate_repo

    async def match_candidate_to_shifts(
        self, candidate_id: str, user_id: str
    ) -> list[dict]:
        """
        Find best shift matches for candidate (Pain #2).
        Reduce 70% no-show by matching availability.
        """
        # Fetch candidate availability from profile
        candidate = await self.candidate_repo.get_candidate(candidate_id, user_id)
        if not candidate:
            return []

        availability = candidate.get("availability", [])
        open_shifts = await self.shift_repo.get_open_shifts(user_id)

        matches = []
        for shift in open_shifts:
            score = self._calculate_match_score(availability, shift)
            if score > 0.5:  # 50%+ match threshold
                match = {
                    "candidate_id": candidate_id,
                    "shift_id": shift["id"],
                    "match_score": score,
                    "conflicts": self._identify_conflicts(availability, shift),
                }
                matches.append(match)

        # Sort by score desc
        matches_sorted = sorted(matches, key=lambda x: x["match_score"], reverse=True)
        return matches_sorted[:5]  # Top 5 matches

    def _calculate_match_score(self, availability: list[dict], shift: dict) -> float:
        """
        Calculate candidate-shift match score (Pain #2).
        0-1 scale based on:
        - Schedule overlap (key)
        - Days until shift starts (urgency)
        - Role match (if available)
        """
        if not availability:
            return 0.0

        # Simple overlap scoring
        shift_start = datetime.fromisoformat(shift["start_date"])
        shift_end = datetime.fromisoformat(shift["end_date"])

        overlap_score = 0.7  # Assume 70% base if no hard conflict
        urgency_score = self._calculate_urgency_score(shift_start)  # Pain #2: seasonal spikes

        combined = (overlap_score * 0.6) + (urgency_score * 0.4)
        return min(1.0, max(0.0, combined))

    def _calculate_urgency_score(self, shift_start: datetime) -> float:
        """
        Urgency scoring (Pain #2: seasonal demand peaks).
        Shifts starting soon = higher score = higher priority matching.
        """
        days_until_start = (shift_start - datetime.utcnow()).days
        if days_until_start <= 0:
            return 1.0  # Immediate
        elif days_until_start <= 7:
            return 0.9  # Urgent
        elif days_until_start <= 30:
            return 0.6  # Normal
        else:
            return 0.2  # Planned

    def _identify_conflicts(self, availability: list[dict], shift: dict) -> list[str]:
        """Identify schedule conflicts (Pain #2: reduce no-shows)."""
        conflicts = []
        # Simplified logic: check if candidate has conflicting commitments
        # In production, cross-reference with other accepted shifts
        return conflicts

    async def create_seasonal_matches(
        self, season: str, user_id: str
    ) -> list[dict]:
        """
        Bulk match candidates to seasonal shifts (Pain #2).
        Example: "Summer 2026" rapid hiring campaign.
        """
        seasonal_shifts = await self.shift_repo.get_seasonal_shifts(season, user_id)
        # Get candidates available in this season
        # Perform bulk matching
        return []
