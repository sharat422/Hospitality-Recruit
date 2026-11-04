"""
Repository pattern for Supabase data access.
All queries include RLS context (user_id from JWT).
"""

from supabase import Client
from typing import Optional, Any
from app.schemas import CandidateCreate, CandidateScreening


class CandidateRepository:
    """Repository for candidate table (module 1 + 3 + 7)."""

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create_candidate(
        self, candidate_data: CandidateCreate, user_id: str
    ) -> dict:
        """
        Create candidate from SMS/web form (Pain #1: bulk inbound).
        RLS ensures user only sees org candidates.
        """
        data = {
            "first_name": candidate_data.first_name,
            "last_name": candidate_data.last_name,
            "email": candidate_data.email,
            "phone": candidate_data.phone,
            "location": candidate_data.location,
            "job_id": candidate_data.job_id,
            "source": candidate_data.source,
            "raw_data": candidate_data.raw_data or {},
            "org_id": user_id,  # RLS: enforce org boundary
        }
        response = self.client.table("candidates").insert(data).execute()
        return response.data[0] if response.data else None

    async def get_candidate(self, candidate_id: str, user_id: str) -> Optional[dict]:
        """
        Fetch candidate by ID.
        RLS filters automatically by org_id.
        """
        response = (
            self.client.table("candidates")
            .select("*")
            .eq("id", candidate_id)
            .eq("org_id", user_id)
            .single()
            .execute()
        )
        return response.data

    async def list_candidates_for_job(
        self, job_id: str, user_id: str, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        """
        List candidates for a job (Pain #1: bulk screening).
        Multiple candidates per role.
        """
        response = (
            self.client.table("candidates")
            .select("*")
            .eq("job_id", job_id)
            .eq("org_id", user_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return response.data

    async def get_qualified_candidates(
        self, job_id: str, user_id: str
    ) -> list[dict]:
        """Fetch pre-qualified candidates only (Pain #1: fast pipeline)."""
        response = (
            self.client.table("candidates")
            .select("*")
            .eq("job_id", job_id)
            .eq("org_id", user_id)
            .eq("qualified", True)
            .execute()
        )
        return response.data

    async def update_candidate_qualification(
        self, candidate_id: str, qualified: bool, screening_data: dict, user_id: str
    ) -> dict:
        """Update candidate with screening result."""
        data = {
            "qualified": qualified,
            "screening_result": screening_data,
            "screened_at": "now()",
        }
        response = (
            self.client.table("candidates")
            .update(data)
            .eq("id", candidate_id)
            .eq("org_id", user_id)
            .execute()
        )
        return response.data[0] if response.data else None

    async def bulk_update_availability(
        self, candidate_id: str, availability: list[dict], user_id: str
    ) -> dict:
        """Update availability from mobile portal (Pain #2)."""
        response = (
            self.client.table("candidates")
            .update({"availability": availability})
            .eq("id", candidate_id)
            .eq("org_id", user_id)
            .execute()
        )
        return response.data[0] if response.data else None
