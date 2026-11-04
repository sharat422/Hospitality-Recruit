"""
AI Matching Service — Hospitality candidate matching & screening features.

Features:
  1. Resume parsing & smart ranking
  2. Skill taxonomy engine (static data)
  3. AI job description generation
  4. Explainable match scores
  5. Passive candidate discovery scoring
  6. Talent database reactivation scoring
"""

import anthropic
import json
import re
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"

HOSPITALITY_TAXONOMY = {
    "front_of_house": [
        "table service", "reservation management", "POS systems",
        "upselling", "customer complaint handling", "menu knowledge",
    ],
    "back_of_house": [
        "food prep", "HACCP", "allergen awareness", "plating",
        "stock control", "kitchen safety",
    ],
    "housekeeping": [
        "room turnover", "linen management", "deep cleaning",
        "chemical handling", "laundry operations",
    ],
    "front_desk": [
        "check-in/check-out", "Opera PMS", "Mews", "guest relations",
        "upselling rooms", "OTA management",
    ],
    "food_beverage_management": [
        "rota management", "P&L responsibility", "supplier negotiation",
        "staff training", "revenue management",
    ],
}

CROSS_INDUSTRY_MAP = {
    "retail": {
        "skills": ["customer service", "cash handling", "upselling", "stock management"],
        "weight": 0.7,
        "maps_to": ["front_of_house", "front_desk"],
    },
    "healthcare": {
        "skills": ["empathy", "patience", "shift work", "team coordination"],
        "weight": 0.65,
        "maps_to": ["front_of_house", "front_desk", "housekeeping"],
    },
    "events": {
        "skills": [
            "event coordination", "guest management", "vendor liaison",
            "problem solving under pressure",
        ],
        "weight": 0.75,
        "maps_to": ["food_beverage_management", "front_of_house"],
    },
}


class AIMatchingService:
    """AI-powered candidate matching service using Claude."""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = CLAUDE_MODEL

    # -----------------------------------------------------------------------
    # 1. Parse resume
    # -----------------------------------------------------------------------

    async def parse_resume(
        self,
        resume_text: str,
        job_requirements: str = "",
    ) -> dict:
        """Extract structured profile from CV text."""
        job_context = ""
        if job_requirements:
            job_context = f"\n\nJOB REQUIREMENTS (score fit against these):\n{job_requirements}"

        prompt = f"""You are an expert hospitality recruiter. Parse the following resume and return a JSON object.

RESUME TEXT:
{resume_text}{job_context}

Return ONLY a JSON object with these exact keys:
{{
  "name": "candidate full name or 'Unknown'",
  "email": "email address or null",
  "phone": "phone number or null",
  "skills": ["list", "of", "skills"],
  "soft_skills": ["list", "of", "soft skills"],
  "work_history": [
    {{"title": "job title", "company": "company name", "duration_months": 12, "industry": "hospitality"}}
  ],
  "years_total_experience": <integer>,
  "hospitality_experience_years": <integer>,
  "languages": ["English"],
  "certifications": ["list of certifications"],
  "fit_score": <integer 0-100>,
  "reasoning": "2-3 sentence explanation",
  "strengths": ["strength 1", "strength 2"],
  "gaps": ["gap 1", "gap 2"]
}}

Rules:
- fit_score must be 0-100
- skills should be specific (e.g. "POS systems", "HACCP", "guest relations")
- Do NOT include markdown or extra text outside the JSON
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._extract_json(response.content[0].text)
        except Exception as e:
            logger.error(f"Claude parse_resume failed: {e}")
            # Keyword fallback
            skills = []
            for category_skills in HOSPITALITY_TAXONOMY.values():
                for skill in category_skills:
                    if skill.lower() in resume_text.lower():
                        skills.append(skill)
            return {
                "name": "Unknown",
                "email": None,
                "phone": None,
                "skills": skills,
                "soft_skills": [],
                "work_history": [],
                "years_total_experience": 0,
                "hospitality_experience_years": 0,
                "languages": ["English"],
                "certifications": [],
                "fit_score": 0,
                "reasoning": "Parsed via keyword fallback due to AI error.",
                "strengths": skills[:3],
                "gaps": [],
            }

    # -----------------------------------------------------------------------
    # 2. Rank candidates
    # -----------------------------------------------------------------------

    async def rank_candidates(
        self,
        job_requirements: str,
        candidates: list,
    ) -> list:
        """Score and rank a list of candidates against job requirements."""
        candidates_json = json.dumps(candidates, indent=2)

        prompt = f"""You are an expert hospitality recruiter. Rank the following candidates for a position.

JOB REQUIREMENTS:
{job_requirements}

CANDIDATES (JSON):
{candidates_json}

For each candidate produce a ranking entry. Return ONLY a JSON array sorted by score descending:
[
  {{
    "candidate_id": "<id from input>",
    "name": "<candidate name>",
    "overall_score": <integer 0-100>,
    "skill_match_score": <integer 0-100>,
    "soft_skill_score": <integer 0-100>,
    "experience_score": <integer 0-100>,
    "cross_industry_score": <integer 0-100>,
    "reasoning": "2-3 sentences explaining the score",
    "strengths": ["key strength 1", "key strength 2"],
    "gaps": ["gap 1", "gap 2"]
  }}
]

Rules:
- score 0-100; be accurate and differentiating
- Sort by overall_score descending (highest first)
- Do NOT include markdown or extra text outside the JSON array
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            ranked = self._extract_json(response.content[0].text)
            for i, item in enumerate(ranked, 1):
                item["rank"] = i
            return ranked
        except Exception as e:
            logger.error(f"Claude rank_candidates failed: {e}")
            return [
                {
                    "candidate_id": c.get("id", ""),
                    "name": c.get("name", "Unknown"),
                    "overall_score": 0,
                    "skill_match_score": 0,
                    "soft_skill_score": 0,
                    "experience_score": 0,
                    "cross_industry_score": 0,
                    "reasoning": "Ranking unavailable (AI error).",
                    "strengths": [],
                    "gaps": [],
                    "rank": i + 1,
                }
                for i, c in enumerate(candidates)
            ]

    # -----------------------------------------------------------------------
    # 3. Generate job description
    # -----------------------------------------------------------------------

    async def generate_jd(
        self,
        role: str,
        property_type: str,
        location: str,
        seniority_level: str,
        responsibilities: list,
        certifications: list,
        work_pattern: str,
        employer_values: list,
        salary_min: Optional[int] = None,
        salary_max: Optional[int] = None,
    ) -> dict:
        """Generate a bias-free hospitality job description."""
        salary_str = ""
        if salary_min and salary_max:
            salary_str = f"${salary_min:,} - ${salary_max:,} per year"
        elif salary_min:
            salary_str = f"From ${salary_min:,} per year"
        else:
            salary_str = "Competitive compensation commensurate with experience"

        responsibilities_str = "\n".join(f"- {r}" for r in responsibilities) if responsibilities else "Standard role responsibilities"
        certs_str = ", ".join(certifications) if certifications else "None required"
        values_str = ", ".join(employer_values) if employer_values else "Excellence, teamwork, guest satisfaction"

        prompt = f"""You are an expert hospitality HR writer. Create a bias-free, inclusive, engaging job description.

ROLE: {role}
PROPERTY TYPE: {property_type}
LOCATION: {location}
SENIORITY LEVEL: {seniority_level}
WORK PATTERN: {work_pattern}
KEY RESPONSIBILITIES: {responsibilities_str}
REQUIRED CERTIFICATIONS: {certs_str}
EMPLOYER VALUES: {values_str}
COMPENSATION: {salary_str}

Return ONLY a JSON object:
{{
  "title": "Job title string",
  "intro_paragraph": "2-3 sentence engaging introduction",
  "responsibilities": ["responsibility 1", "responsibility 2"],
  "requirements": ["requirement 1", "requirement 2"],
  "nice_to_have": ["nice to have 1"],
  "benefits": ["benefit 1"],
  "salary_range": "{salary_str}",
  "cta_paragraph": "Call to action paragraph",
  "full_text": "Complete formatted job description as a single string with newlines"
}}

Bias-free guidelines:
- Use gender-neutral language
- Focus on skills and outcomes, not credentials alone
- Avoid adjectives like 'rockstar', 'ninja', 'aggressive'
- Include a diversity statement in the full_text
- Do NOT include markdown or extra text outside the JSON
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._extract_json(response.content[0].text)
        except Exception as e:
            logger.error(f"Claude generate_jd failed: {e}")
            return {
                "title": f"{seniority_level.capitalize()} {role}",
                "intro_paragraph": f"We are hiring a {role} at our {property_type} in {location}.",
                "responsibilities": responsibilities or [],
                "requirements": certifications or [],
                "nice_to_have": [],
                "benefits": [],
                "salary_range": salary_str,
                "cta_paragraph": "Apply today to join our team!",
                "full_text": f"{role} position at {location}. {salary_str}.",
            }

    # -----------------------------------------------------------------------
    # 4. Score candidate-job match
    # -----------------------------------------------------------------------

    async def score_match(
        self,
        candidate: dict,
        job_role: dict,
    ) -> dict:
        """Compute weighted match score between candidate and job role."""
        prompt = f"""You are an expert hospitality recruiter. Score how well this candidate matches the job role.

JOB ROLE:
{json.dumps(job_role, indent=2)}

CANDIDATE:
{json.dumps(candidate, indent=2)}

Return ONLY a JSON object:
{{
  "skill_match_score": <0-100, how well candidate skills match required_skills>,
  "soft_skill_score": <0-100, soft skills fit>,
  "experience_score": <0-100, years and type of experience fit>,
  "cross_industry_score": <0-100, transferable skills from other industries>,
  "availability_score": <0-100, location/work pattern fit>,
  "match_reasoning": "2-3 sentences explaining the overall match",
  "strengths": ["matched skill 1", "matched skill 2"],
  "gaps": ["missing requirement 1"]
}}
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            scores = self._extract_json(response.content[0].text)
        except Exception as e:
            logger.error(f"Claude score_match failed: {e}")
            # Keyword fallback
            required = job_role.get("required_skills", [])
            if isinstance(required, str):
                try:
                    required = json.loads(required)
                except Exception:
                    required = []
            cand_skills = candidate.get("parsed_skills", {})
            if isinstance(cand_skills, dict):
                cand_skill_list = list(cand_skills.keys())
            else:
                cand_skill_list = cand_skills if isinstance(cand_skills, list) else []
            matched = [s for s in required if any(s.lower() in cs.lower() for cs in cand_skill_list)]
            skill_pct = int(len(matched) / max(len(required), 1) * 100)
            scores = {
                "skill_match_score": skill_pct,
                "soft_skill_score": 50,
                "experience_score": 50,
                "cross_industry_score": 50,
                "availability_score": 80,
                "match_reasoning": "Scored via keyword fallback.",
                "strengths": matched[:3],
                "gaps": [s for s in required if s not in matched][:3],
            }

        overall = (
            scores.get("skill_match_score", 0) * 0.35
            + scores.get("soft_skill_score", 0) * 0.20
            + scores.get("experience_score", 0) * 0.25
            + scores.get("cross_industry_score", 0) * 0.15
            + scores.get("availability_score", 0) * 0.05
        )
        scores["overall_score"] = round(overall, 2)
        return scores

    # -----------------------------------------------------------------------
    # 5. Generate reactivation SMS
    # -----------------------------------------------------------------------

    async def generate_reactivation_message(
        self,
        candidate_name: str,
        past_role: str,
        months_ago: int,
        new_role: str,
        location: str,
        top_skill: str,
    ) -> str:
        """Generate a max 160 char SMS for talent reactivation."""
        prompt = f"""Write a warm, personalized SMS re-engagement message for a hospitality candidate.
Candidate: {candidate_name}
Last role: {past_role} ({months_ago} months ago)
New opportunity: {new_role} in {location}
Their top skill: {top_skill}

Rules:
- Max 160 characters
- Friendly and personal tone
- Mention the role and location
- Include a call to action
- Return ONLY the message text, no JSON, no quotes
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            msg = response.content[0].text.strip()
            return msg[:160]
        except Exception as e:
            logger.error(f"Claude reactivation_message failed: {e}")
            return f"Hi {candidate_name}! A new {new_role} role in {location} matches your {top_skill} experience. Interested? Reply YES."[:160]

    # -----------------------------------------------------------------------
    # 6. Suggest skills
    # -----------------------------------------------------------------------

    async def suggest_skills(
        self,
        job_title: str,
        property_type: str,
    ) -> list:
        """Suggest relevant skills for a job title and property type."""
        prompt = f"""You are a hospitality skills expert.
Suggest the most important skills for a {job_title} working at a {property_type}.

Return ONLY a JSON array of skill strings (max 20 skills):
["skill 1", "skill 2", ...]

Do NOT include markdown or extra text outside the JSON array.
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._extract_json(response.content[0].text)
        except Exception as e:
            logger.error(f"Claude suggest_skills failed: {e}")
            all_skills = []
            for skills in HOSPITALITY_TAXONOMY.values():
                all_skills.extend(skills)
            return all_skills[:15]

    # -----------------------------------------------------------------------
    # 7. Map cross-industry skills (sync)
    # -----------------------------------------------------------------------

    def map_cross_industry_skills(
        self,
        candidate_skills: list,
        work_history: list,
    ) -> list:
        """Map cross-industry skills to hospitality equivalents with weights."""
        mapped = []
        candidate_skills_lower = [s.lower() for s in candidate_skills]

        for industry, data in CROSS_INDUSTRY_MAP.items():
            industry_skills = [s.lower() for s in data["skills"]]
            matched = [s for s in industry_skills if any(s in cs for cs in candidate_skills_lower)]
            if matched:
                for skill in matched:
                    mapped.append({
                        "original_skill": skill,
                        "industry_source": industry,
                        "maps_to_categories": data["maps_to"],
                        "weight": data["weight"],
                    })

        # Also check work history industries
        for job in work_history:
            industry = job.get("industry", "").lower()
            if industry in CROSS_INDUSTRY_MAP:
                data = CROSS_INDUSTRY_MAP[industry]
                for skill in data["skills"]:
                    if not any(m["original_skill"] == skill for m in mapped):
                        mapped.append({
                            "original_skill": skill,
                            "industry_source": industry,
                            "maps_to_categories": data["maps_to"],
                            "weight": data["weight"] * 0.8,
                        })
        return mapped

    # -----------------------------------------------------------------------
    # 8. Compute passive score (sync)
    # -----------------------------------------------------------------------

    def compute_passive_score(
        self,
        days_since_active: int,
        tenure_months: int,
        portal_logins: int,
    ) -> float:
        """Compute passive openness score (0-100)."""
        # Recency: less active = more passive/open (higher score)
        if days_since_active <= 30:
            recency_score = 20
        elif days_since_active <= 90:
            recency_score = 40
        elif days_since_active <= 180:
            recency_score = 60
        elif days_since_active <= 365:
            recency_score = 75
        else:
            recency_score = 90

        # Tenure: shorter tenure = more likely to move
        if tenure_months <= 6:
            tenure_score = 80
        elif tenure_months <= 12:
            tenure_score = 65
        elif tenure_months <= 24:
            tenure_score = 50
        elif tenure_months <= 36:
            tenure_score = 35
        else:
            tenure_score = 20

        # Portal logins: more logins = still active/interested
        login_score = min(portal_logins * 10, 80)

        # Weighted: recency 40%, tenure 35%, logins 25%
        score = recency_score * 0.40 + tenure_score * 0.35 + login_score * 0.25
        return round(score, 2)

    # -----------------------------------------------------------------------
    # Helper
    # -----------------------------------------------------------------------

    def _extract_json(self, text: str) -> dict:
        """Strip markdown fences and parse JSON from Claude output."""
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e} | text: {text[:200]}")
            raise ValueError(f"Failed to parse Claude JSON response: {e}")

    # -----------------------------------------------------------------------
    # Legacy compatibility: keep old methods
    # -----------------------------------------------------------------------

    async def score_for_reactivation(
        self,
        candidate: dict,
        job_requirements: str,
    ) -> dict:
        """Score a past/inactive candidate for re-engagement fit."""
        candidate_json = json.dumps(candidate, indent=2)
        prompt = f"""You are an expert hospitality talent re-engagement specialist.

Evaluate this past candidate for reactivation against a new open role.

JOB REQUIREMENTS:
{job_requirements}

CANDIDATE DATA:
{candidate_json}

Return ONLY a JSON object:
{{
  "candidate_id": "<from input>",
  "reactivation_score": <integer 0-100>,
  "fit_reasoning": "2-3 sentences on how well they fit the role",
  "engagement_likelihood": "high",
  "personalized_message": "A warm, personalized re-engagement message. Under 150 words.",
  "strengths": ["relevant strength 1"],
  "gaps": ["potential gap 1"]
}}

Do NOT include markdown or extra text outside the JSON.
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._extract_json(response.content[0].text)
        except Exception as e:
            logger.error(f"Claude score_for_reactivation failed: {e}")
            return {
                "candidate_id": candidate.get("id", ""),
                "reactivation_score": 0,
                "fit_reasoning": "Scoring unavailable.",
                "engagement_likelihood": "low",
                "personalized_message": "Hi! We have a new opportunity that may interest you.",
                "strengths": [],
                "gaps": [],
            }

    async def score_passive_candidate(
        self,
        candidate: dict,
        target_role: str,
        target_skills: list,
    ) -> dict:
        """Score an inactive/passive candidate for likelihood to engage."""
        candidate_json = json.dumps(candidate, indent=2)
        skills_str = ", ".join(target_skills)
        prompt = f"""You are a passive talent sourcing expert in hospitality recruiting.

Evaluate this candidate's likelihood to engage with a new opportunity.

TARGET ROLE: {target_role}
TARGET SKILLS: {skills_str}

CANDIDATE DATA:
{candidate_json}

Return ONLY a JSON object:
{{
  "candidate_id": "<from input>",
  "passive_score": <integer 0-100>,
  "engagement_signals": ["signal 1"],
  "skill_match_score": <integer 0-100>,
  "recommended_approach": "sms",
  "reasoning": "2-3 sentences",
  "best_pitch": "One compelling sentence"
}}

Do NOT include markdown or extra text outside the JSON.
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._extract_json(response.content[0].text)
        except Exception as e:
            logger.error(f"Claude score_passive_candidate failed: {e}")
            return {
                "candidate_id": candidate.get("id", ""),
                "passive_score": 0,
                "engagement_signals": [],
                "skill_match_score": 0,
                "recommended_approach": "sms",
                "reasoning": "Scoring unavailable.",
                "best_pitch": "We have an exciting opportunity for you!",
            }
