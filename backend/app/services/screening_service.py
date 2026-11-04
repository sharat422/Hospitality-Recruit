"""
Screening service: AI candidate qualification using Claude/GPT-4o (Module 1).
Pain #1: 100-500 unqualified apps/role, 65% admin screening time, 40% higher cost-per-hire.
"""

import json
from anthropic import Anthropic
from openai import OpenAI
from app.core.config import settings
from app.repositories.candidate_repo import CandidateRepository
from app.core.exceptions import ScreeningException
from datetime import datetime
from typing import Optional


class ScreeningService:
    """Orchestrate AI screening using Claude or GPT-4o."""

    def __init__(self, candidate_repo: CandidateRepository):
        self.candidate_repo = candidate_repo
        self.anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

    async def screen_candidate(
        self,
        candidate_id: str,
        job_requirements: str,
        use_claude: bool = True,
    ) -> dict:
        """
        Screen candidate against job requirements using AI (Pain #1).
        Returns: {ai_score, key_qualifications, red_flags, recommend_proceed}.
        """
        try:
            # Build screening prompt with pain points in context
            prompt = self._build_screening_prompt(job_requirements)

            if use_claude:
                response = self.anthropic_client.messages.create(
                    model=settings.ANTHROPIC_MODEL,
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}],
                )
                ai_response = response.content[0].text
            else:
                response = self.openai_client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500,
                    temperature=0.3,
                )
                ai_response = response.choices[0].message.content

            # Parse AI response
            result = self._parse_screening_response(ai_response, candidate_id)
            result["ai_model"] = settings.ANTHROPIC_MODEL if use_claude else settings.OPENAI_MODEL

            # Store in DB
            # Candidate would have been fetched earlier in router
            # Update with screening result
            return result

        except Exception as e:
            raise ScreeningException(
                f"Screening failed for candidate {candidate_id}: {str(e)}"
            )

    def _build_screening_prompt(self, job_requirements: str) -> str:
        """
        Build screening prompt with hospitality context (Pain #1).
        Reduce 65% admin time by automating initial filter.
        """
        return f"""
You are a hospitality recruiting AI screener. Evaluate candidate qualifications strictly.

JOB REQUIREMENTS:
{job_requirements}

PAIN POINT CONTEXT:
- We receive 100-500 applicants per role; only 20-30% are qualified
- 65% of recruiter time goes to manual screening
- Cost per hire is 40% higher than industry average
- Your screening should reduce unqualified apps by 70% with high precision

Analyze the candidate and return JSON:
{{
  "ai_score": <0-100, higher is better>,
  "key_qualifications": [<list of matched skills/experience>],
  "red_flags": [<list of concerns>],
  "recommend_proceed": <true/false>,
  "reasoning": <concise explanation>
}}

Be conservative: only recommend "proceed" if candidate is 70%+ match.
"""

    def _parse_screening_response(
        self, ai_response: str, candidate_id: str
    ) -> dict:
        """Parse AI response into structured result."""
        try:
            # Extract JSON from response (Claude may wrap in markdown)
            if "```json" in ai_response:
                json_str = ai_response.split("```json")[1].split("```")[0].strip()
            elif "```" in ai_response:
                json_str = ai_response.split("```")[1].split("```")[0].strip()
            else:
                json_str = ai_response

            result = json.loads(json_str)
            result["candidate_id"] = candidate_id
            result["screened_at"] = datetime.utcnow().isoformat()

            return result
        except Exception as e:
            raise ScreeningException(f"Failed to parse screening result: {str(e)}")

    async def bulk_screen_batch(
        self, candidate_ids: list[str], job_requirements: str, user_id: str
    ) -> list[dict]:
        """
        Screen multiple candidates in batch (Pain #1: efficiency at scale).
        Could be async/Celery job for larger batches.
        """
        results = []
        for cid in candidate_ids:
            result = await self.screen_candidate(cid, job_requirements)
            results.append(result)
        return results
