"""
Candidate Screening & Ranking Service

6-dimension scoring per candidate-job pair:
  1. Skill match         (weight 0.30)
  2. Hospitality experience (weight 0.25)
  3. Language fit        (weight 0.10)
  4. Location fit        (weight 0.15)
  5. Salary fit          (weight 0.10)
  6. Availability        (weight 0.10)

Features:
  - Claude-powered scoring with HR-readable explanations
  - Rule-based fallback when Claude is unavailable
  - Blind mode: strips name/photo/address/gender from candidate before scoring
  - Cross-industry matching: retail/call-center → front desk, domestic → housekeeping, etc.
  - Auto-shortlist top N candidates per job
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"

# Score weights — must sum to 1.0
DEFAULT_WEIGHTS = {
    "skill":        0.30,
    "experience":   0.25,
    "location":     0.15,
    "language":     0.10,
    "salary":       0.10,
    "availability": 0.10,
}
WEIGHTS = DEFAULT_WEIGHTS  # Backward-compatible export.
SCORING_VERSION = "deterministic-v2"


def validate_weights(weights: Optional[dict] = None) -> dict:
    """Return a complete normalized weight set; reject silent score distortion."""
    values = {**DEFAULT_WEIGHTS, **(weights or {})}
    if set(values) != set(DEFAULT_WEIGHTS):
        raise ValueError(f"Weights must contain only: {', '.join(DEFAULT_WEIGHTS)}")
    values = {key: float(value) for key, value in values.items()}
    if any(value < 0 or value > 1 for value in values.values()):
        raise ValueError("Every scoring weight must be between 0 and 1")
    if abs(sum(values.values()) - 1.0) > 0.0001:
        raise ValueError("Scoring weights must sum to 1.0")
    return values

# ─────────────────────────────────────────────────────────────────────────────
# India-focused cross-industry map
# Each entry: which candidate industries map to which hospitality roles,
# with a score boost (0–1) and an HR-readable note.
# ─────────────────────────────────────────────────────────────────────────────

INDIA_CROSS_INDUSTRY_MAP = {
    "retail": {
        "keywords":    ["retail", "supermarket", "store", "shop", "sales", "billing counter", "kirana"],
        "maps_to":     ["front_desk", "front_of_house", "cashier"],
        "boost":       0.75,
        "note": (
            "Retail experience transfers well to front desk and F&B roles — "
            "billing, customer handling, and upselling are directly applicable."
        ),
    },
    "call_center": {
        "keywords":    ["bpo", "call centre", "call center", "customer support", "helpdesk",
                        "tele-caller", "telecaller", "inbound", "outbound"],
        "maps_to":     ["front_desk", "reservations", "guest_services"],
        "boost":       0.70,
        "note": (
            "Call centre experience maps to hotel reservations and guest services — "
            "phone etiquette, complaint handling, and CRM skills are all transferable."
        ),
    },
    "housekeeping": {
        "keywords":    ["housekeeping", "cleaner", "cleaning", "sanitation", "janitorial",
                        "sweeper", "safai"],
        "maps_to":     ["housekeeping", "room_attendant"],
        "boost":       0.90,
        "note": (
            "Housekeeping experience is a near-direct match for hotel room attendant roles — "
            "cleaning standards, chemical handling, and linen management apply immediately."
        ),
    },
    "domestic_work": {
        "keywords":    ["domestic", "maid", "nanny", "cook", "household", "ghar ka kaam",
                        "bai", "home help"],
        "maps_to":     ["housekeeping", "room_attendant"],
        "boost":       0.82,
        "note": (
            "Domestic work experience demonstrates cleaning discipline and household management, "
            "translating well to hotel housekeeping and room attendant positions."
        ),
    },
    "restaurant": {
        "keywords":    ["restaurant", "dhaba", "cafe", "cafeteria", "eatery", "waiter",
                        "food service", "table boy", "steward", "server"],
        "maps_to":     ["front_of_house", "f&b", "banquet", "waiter"],
        "boost":       0.88,
        "note": (
            "Restaurant experience transfers directly to hotel F&B, banquet, and waiter roles — "
            "table service, menu knowledge, and guest interaction are core shared skills."
        ),
    },
    "security": {
        "keywords":    ["security guard", "security", "watchman", "bouncer", "access control",
                        "cctv", "surveillance"],
        "maps_to":     ["hotel_security"],
        "boost":       0.83,
        "note": (
            "Security experience maps directly to hotel security guard roles — "
            "access control, emergency response, and patrol routines are directly applicable."
        ),
    },
    "healthcare": {
        "keywords":    ["hospital", "clinic", "nursing", "ward boy", "attendant", "caregiver",
                        "pharmacy", "health"],
        "maps_to":     ["housekeeping", "front_desk"],
        "boost":       0.62,
        "note": (
            "Healthcare experience demonstrates hygiene discipline and patient-care empathy, "
            "valued in hotel housekeeping and front desk roles."
        ),
    },
    "manufacturing": {
        "keywords":    ["factory", "plant", "assembly", "production", "warehouse", "godown",
                        "labour", "manufacturing"],
        "maps_to":     ["housekeeping", "kitchen_helper"],
        "boost":       0.50,
        "note": (
            "Manufacturing experience shows shift-work discipline and physical endurance, "
            "applicable to back-of-house and housekeeping roles."
        ),
    },
    "driver": {
        "keywords":    ["driver", "chauffeur", "cab", "taxi", "auto", "delivery"],
        "maps_to":     ["valet", "transportation"],
        "boost":       0.72,
        "note": (
            "Driving experience is directly applicable to hotel valet and transportation roles."
        ),
    },
}

# Fields stripped in blind mode
_BLIND_STRIP_FIELDS = [
    "first_name", "last_name", "full_name", "name",
    "email", "phone", "photo_url", "photo", "profile_photo",
    "location", "city", "state", "hometown", "current_location", "preferred_location",
    "address", "home_address", "residential_address",
    "gender", "sex", "dob", "date_of_birth", "age",
    "father_name", "mother_name", "marital_status",
    "religion", "caste",
]


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DimensionScore:
    score: float          # 0-100
    explanation: str      # HR-readable


@dataclass
class ScreeningResult:
    candidate_id: str
    blind_id: str
    display_name: str     # empty string in blind mode

    total_score: float

    skill:        DimensionScore
    experience:   DimensionScore
    language:     DimensionScore
    location:     DimensionScore
    salary:       DimensionScore
    availability: DimensionScore

    cross_industry_match:  bool   = False
    cross_industry_source: str    = ""
    cross_industry_target: str    = ""
    cross_industry_note:   str    = ""
    cross_industry_boost:  float  = 0.0

    strengths:              list  = field(default_factory=list)
    gaps:                   list  = field(default_factory=list)
    overall_recommendation: str   = "consider"   # shortlist | consider | reject
    recommendation_reasons: list = field(default_factory=list)
    scoring_weights: dict = field(default_factory=dict)
    scoring_version: str = SCORING_VERSION
    explanation_source: str = "DETERMINISTIC"
    screening_result_id: Optional[str] = None

    rank: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_blind_id(candidate_id: str) -> str:
    """Deterministic, non-reversible blind ID from candidate UUID."""
    digest = hashlib.sha256(candidate_id.encode()).hexdigest()[:8].upper()
    return f"C-{digest}"


def apply_blind_mode(candidate: dict) -> dict:
    """Return a copy of candidate with all PII fields removed."""
    c = {k: v for k, v in candidate.items() if k not in _BLIND_STRIP_FIELDS}
    # Also strip gender indicators from free-text fields
    for field_name in ("resume_text", "cover_letter", "notes"):
        if field_name in c and isinstance(c[field_name], str):
            c[field_name] = _strip_gender_language(c[field_name])
    # Strip company names and exact dates from work history
    if "work_history" in c and isinstance(c["work_history"], list):
        c["work_history"] = [
            {
                "title":            w.get("title", ""),
                "industry":         w.get("industry", ""),
                "duration_months":  w.get("duration_months", 0),
            }
            for w in c["work_history"]
        ]
    return c


def _strip_gender_language(text: str) -> str:
    """Remove common gender pronouns and indicators from free text."""
    patterns = [
        r"\bhe\b", r"\bhim\b", r"\bhis\b",
        r"\bshe\b", r"\bher\b", r"\bhers\b",
        r"\bMr\.?\b", r"\bMrs\.?\b", r"\bMs\.?\b",
    ]
    for pat in patterns:
        text = re.sub(pat, "[name]", text, flags=re.IGNORECASE)
    return text


def detect_cross_industry(candidate: dict) -> Optional[dict]:
    """
    Detect if candidate comes from a cross-industry background.
    Returns the best-matching industry entry or None.
    """
    # Build text blob from work history + job titles + resume
    work_text = " ".join(
        f"{w.get('title', '')} {w.get('company', '')} {w.get('industry', '')}"
        for w in (candidate.get("work_history") or [])
    ).lower()
    resume_text = (candidate.get("resume_text") or "").lower()
    combined = f"{work_text} {resume_text}"

    best_match = None
    best_boost = 0.0
    for industry, data in INDIA_CROSS_INDUSTRY_MAP.items():
        for kw in data["keywords"]:
            if kw in combined:
                if data["boost"] > best_boost:
                    best_boost = data["boost"]
                    best_match = {
                        "industry": industry,
                        "maps_to":  data["maps_to"],
                        "boost":    data["boost"],
                        "note":     data["note"],
                    }
                break  # one keyword match per industry is enough

    return best_match


def cross_industry_applies(cross: Optional[dict], job: dict) -> bool:
    if not cross:
        return False
    role_text = " ".join(str(job.get(key) or "") for key in ("title", "role", "department")).lower().replace(" ", "_")
    return any(
        target.lower().replace(" ", "_") in role_text or role_text in target.lower().replace(" ", "_")
        for target in cross["maps_to"] if target
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based scoring fallbacks (used when Claude is unavailable)
# ─────────────────────────────────────────────────────────────────────────────

HOSPITALITY_SKILL_KEYWORDS = [
    "table service", "guest relations", "check-in", "check-out", "pos",
    "room service", "housekeeping", "food & beverage", "f&b",
    "menu knowledge", "upselling", "complaint handling", "reservation",
    "opera pms", "front desk", "banquet", "bar", "kitchen",
    "haccp", "food safety", "linen", "room turnover",
]


def _rule_skill_score(candidate: dict, job: dict) -> DimensionScore:
    required = job.get("required_skills") or []
    if isinstance(required, str):
        try:
            required = json.loads(required)
        except Exception:
            required = [s.strip() for s in required.split(",")]

    cand_skills = candidate.get("parsed_skills") or []
    if isinstance(cand_skills, dict):
        cand_skills = list(cand_skills.keys())

    cand_text = " ".join(str(s) for s in cand_skills).lower()
    if not required:
        return DimensionScore(score=70.0, explanation="No required skill list was configured; neutral score used for recruiter review.")
    matched = [r for r in required if r.lower() in cand_text]
    pct = int(len(matched) / max(len(required), 1) * 100)

    # Also scan for generic hospitality keywords
    hosp_matched = [k for k in HOSPITALITY_SKILL_KEYWORDS if k in cand_text]
    bonus = min(len(hosp_matched) * 5, 20)
    score = min(pct + bonus, 100)

    if score >= 80:
        expl = f"Strong skill match — {len(matched)} of {len(required)} required skills found."
    elif score >= 60:
        expl = f"Moderate match — {len(matched)} of {len(required)} required skills. Some gaps."
    else:
        expl = f"Weak skill match — only {len(matched)} of {len(required)} required skills found."
    if required and len(matched) < len(required):
        missing = [r for r in required if r.lower() not in cand_text]
        expl += f" Missing: {', '.join(missing[:3])}."
    return DimensionScore(score=float(score), explanation=expl)


def _rule_experience_score(candidate: dict, job: dict) -> DimensionScore:
    years = candidate.get("years_experience") or 0
    min_exp = job.get("min_experience_years") or job.get("experience_min_years") or 0

    if years >= min_exp * 2 and years >= 4:
        score = 95
        expl = f"{years} years experience — well above the {min_exp}-year requirement."
    elif years >= min_exp:
        score = 78
        expl = f"{years} years experience meets the {min_exp}-year minimum."
    elif years >= max(min_exp - 1, 0):
        score = 55
        expl = f"{years} years experience — slightly below the {min_exp}-year requirement."
    else:
        score = 30
        expl = f"Only {years} years experience; {min_exp} years required."

    # Direct hospitality experience bonus
    hosp_years = candidate.get("hospitality_experience_years") or sum(
        float(w.get("duration_months") or 0) / 12
        for w in (candidate.get("work_history") or [])
        if any(term in str(w.get("industry") or "").lower() for term in ("hospitality", "hotel", "restaurant", "resort"))
    )
    if hosp_years and hosp_years >= min_exp:
        score = min(score + 10, 100)
        expl += f" {hosp_years} years are in hospitality specifically."
    return DimensionScore(score=float(score), explanation=expl)


def _rule_language_score(candidate: dict, job: dict) -> DimensionScore:
    cand_langs = [l.lower() for l in (candidate.get("languages_spoken") or candidate.get("languages") or [])]
    job_langs = [l.lower() for l in (job.get("required_languages") or ["hindi", "english"])]

    matched = [l for l in job_langs if any(l in cl for cl in cand_langs)]
    pct = int(len(matched) / max(len(job_langs), 1) * 100)

    if pct == 100:
        expl = f"Fluent in all required languages: {', '.join(matched)}."
    elif pct >= 50:
        expl = f"Speaks {len(matched)} of {len(job_langs)} required languages."
    else:
        expl = f"Language gap — required: {', '.join(job_langs)}; candidate has: {', '.join(cand_langs) or 'none listed'}."
    return DimensionScore(score=float(pct), explanation=expl)


def _rule_location_score(candidate: dict, job: dict) -> DimensionScore:
    cand_loc = (candidate.get("current_location") or candidate.get("city") or "").lower()
    job_loc = (job.get("location") or job.get("location_city") or job.get("city") or job.get("property_name") or "").lower()

    if not cand_loc or not job_loc:
        return DimensionScore(score=70.0, explanation="Location not specified — assuming flexible.")

    if cand_loc in job_loc or job_loc in cand_loc:
        return DimensionScore(score=100.0, explanation=f"Candidate is in {cand_loc} — same city as the property.")

    # Extract city names (simple heuristic)
    job_city = job_loc.split(",")[0].strip()
    cand_city = cand_loc.split(",")[0].strip()
    if cand_city == job_city:
        return DimensionScore(score=100.0, explanation=f"Candidate lives in {cand_city} — same city.")

    willing = candidate.get("willing_to_relocate", False)
    if willing:
        return DimensionScore(score=65.0, explanation=f"Candidate is in {cand_loc}, willing to relocate to {job_loc}.")
    return DimensionScore(score=40.0, explanation=f"Candidate in {cand_loc}; job in {job_loc}. Relocation needed.")


def _rule_salary_score(candidate: dict, job: dict) -> DimensionScore:
    expected = candidate.get("expected_salary_inr") or candidate.get("expected_ctc") or 0
    min_sal = job.get("salary_min") or job.get("salary_min_inr") or 0
    max_sal = job.get("salary_max") or job.get("salary_max_inr") or 0

    if not expected or not max_sal:
        return DimensionScore(score=70.0, explanation="Salary expectation not specified — assumed negotiable.")

    if min_sal <= expected <= max_sal:
        return DimensionScore(
            score=90.0,
            explanation=f"Expected ₹{expected:,}/month fits within the ₹{min_sal:,}–₹{max_sal:,} range.",
        )
    if expected < min_sal:
        return DimensionScore(
            score=85.0,
            explanation=f"Expected ₹{expected:,} is below the minimum ₹{min_sal:,} — easy to accommodate.",
        )
    over_pct = int((expected - max_sal) / max(max_sal, 1) * 100)
    if over_pct <= 15:
        return DimensionScore(
            score=65.0,
            explanation=f"Expected ₹{expected:,} is {over_pct}% above the ₹{max_sal:,} ceiling — may need negotiation.",
        )
    return DimensionScore(
        score=30.0,
        explanation=f"Expected ₹{expected:,} significantly exceeds the ₹{max_sal:,} maximum.",
    )


def _rule_availability_score(candidate: dict, job: dict) -> DimensionScore:
    notice = candidate.get("notice_period_days")
    if notice is None:
        notice_text = str(candidate.get("notice_period") or "").lower()
        match = re.search(r"\d+", notice_text)
        notice = int(match.group()) if match else (0 if "immediate" in notice_text else 0)
    urgency_days = job.get("urgency_days") or 30  # default: need someone in 30 days

    if notice == 0:
        score, explanation = 100.0, "Immediate joiner — no notice period."
    elif notice <= urgency_days:
        score, explanation = 85.0, f"{notice}-day notice period fits the {urgency_days}-day hiring window."
    elif notice - urgency_days <= 15:
        score, explanation = 65.0, f"{notice}-day notice is {notice - urgency_days} days longer than ideal — manageable with planning."
    else:
        score, explanation = 40.0, f"{notice}-day notice period creates a significant delay for this urgent role."
    required_shifts = {str(v).lower() for v in (job.get("shift_requirements") or [])}
    availability = candidate.get("availability") or candidate.get("shift_preference") or []
    if isinstance(availability, str):
        availability = [availability]
    candidate_shifts = {str(v).lower() for v in availability}
    if required_shifts and candidate_shifts:
        matched = required_shifts & candidate_shifts
        if not matched:
            score = min(score, 35.0)
            explanation += " Listed shift availability does not match the job requirement."
        elif required_shifts.issubset(candidate_shifts):
            explanation += " All required shifts are available."
        else:
            score = min(score, 70.0)
            explanation += f" Available for {len(matched)} of {len(required_shifts)} required shifts."
    return DimensionScore(score=score, explanation=explanation)


def _compute_total(result_dict: dict, weights: Optional[dict] = None) -> float:
    weights = validate_weights(weights)
    return round(
        result_dict["skill_score"]        * weights["skill"]
        + result_dict["experience_score"] * weights["experience"]
        + result_dict["language_score"]   * weights["language"]
        + result_dict["location_score"]   * weights["location"]
        + result_dict["salary_score"]     * weights["salary"]
        + result_dict["availability_score"] * weights["availability"],
        2,
    )


def deterministic_score_candidate(candidate: dict, job: dict, weights: Optional[dict] = None,
                                  shortlist_threshold: float = 75, reject_threshold: float = 45) -> dict:
    """Full rule-based 6-dimension score. Returns raw score dict."""
    skill        = _rule_skill_score(candidate, job)
    experience   = _rule_experience_score(candidate, job)
    language     = _rule_language_score(candidate, job)
    location     = _rule_location_score(candidate, job)
    salary       = _rule_salary_score(candidate, job)
    availability = _rule_availability_score(candidate, job)

    raw = {
        "skill_score":               skill.score,
        "skill_explanation":         skill.explanation,
        "experience_score":          experience.score,
        "experience_explanation":    experience.explanation,
        "language_score":            language.score,
        "language_explanation":      language.explanation,
        "location_score":            location.score,
        "location_explanation":      location.explanation,
        "salary_score":              salary.score,
        "salary_explanation":        salary.explanation,
        "availability_score":        availability.score,
        "availability_explanation":  availability.explanation,
        "cross_industry_match":      False,
        "cross_industry_source":     None,
        "strengths":                 [],
        "gaps":                      [],
        "overall_recommendation":    "consider",
    }
    weights = validate_weights(weights)
    total = _compute_total(raw, weights)
    raw["total_score"] = total
    if total >= shortlist_threshold:
        raw["overall_recommendation"] = "shortlist"
    elif total < reject_threshold:
        raw["overall_recommendation"] = "reject"
    raw["recommendation_reasons"] = [
        f"Deterministic total {total:.1f}/100 using configured weights.",
        raw["skill_explanation"],
        raw["experience_explanation"],
    ]
    raw["scoring_weights"] = weights
    return raw


_rule_score_candidate = deterministic_score_candidate  # Backward compatibility for existing imports.


# ─────────────────────────────────────────────────────────────────────────────
# Claude-powered scoring
# ─────────────────────────────────────────────────────────────────────────────

def _build_job_context(job: dict) -> dict:
    return {
        "title":              job.get("title") or job.get("role") or "Hotel Role",
        "department":         job.get("department", ""),
        "property_name":      job.get("property_name") or job.get("location", ""),
        "city":               job.get("city") or job.get("location", ""),
        "required_skills":    job.get("required_skills") or [],
        "preferred_skills":   job.get("preferred_skills") or [],
        "min_experience_years": job.get("min_experience_years") or job.get("experience_min_years") or 0,
        "required_languages": job.get("required_languages") or ["Hindi", "English"],
        "salary_min":         job.get("salary_min") or job.get("salary_min_inr") or 0,
        "salary_max":         job.get("salary_max") or job.get("salary_max_inr") or 0,
        "urgency_days":       job.get("urgency_days") or 30,
        "description":        (job.get("jd_english") or job.get("description") or "")[:500],
    }


def _build_candidate_context(candidate: dict) -> dict:
    return {
        "years_experience":         candidate.get("years_experience") or 0,
        "hospitality_experience_years": candidate.get("hospitality_experience_years") or 0,
        "skills":                   candidate.get("parsed_skills") or [],
        "work_history":             (candidate.get("work_history") or [])[:5],
        "languages":                candidate.get("languages_spoken") or candidate.get("languages") or [],
        "certifications":           candidate.get("certifications") or [],
        "current_location":         candidate.get("current_location") or candidate.get("city") or "",
        "expected_salary_inr":      candidate.get("expected_salary_inr") or 0,
        "notice_period_days":       candidate.get("notice_period_days") or 0,
        "willing_to_relocate":      candidate.get("willing_to_relocate", False),
        "source":                   candidate.get("source", ""),
    }


async def _claude_score_candidate(candidate: dict, job: dict) -> Optional[dict]:
    """
    Ask Claude to score a candidate across all 6 dimensions in one call.
    Returns a raw score dict or None on failure.
    """
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        job_ctx = _build_job_context(job)
        cand_ctx = _build_candidate_context(candidate)

        prompt = f"""You are an expert hospitality recruiter in India. Score this candidate for the hotel job.

JOB:
{json.dumps(job_ctx, indent=2)}

CANDIDATE:
{json.dumps(cand_ctx, indent=2)}

Score each dimension 0-100. Write the explanation in plain HR language (1-2 sentences). Be specific — mention actual skills, numbers, locations.

Return ONLY valid JSON, no markdown:
{{
  "skill_score": <0-100>,
  "skill_explanation": "<1-2 sentences>",
  "experience_score": <0-100>,
  "experience_explanation": "<1-2 sentences>",
  "language_score": <0-100>,
  "language_explanation": "<1-2 sentences>",
  "location_score": <0-100>,
  "location_explanation": "<1-2 sentences>",
  "salary_score": <0-100>,
  "salary_explanation": "<1-2 sentences>",
  "availability_score": <0-100>,
  "availability_explanation": "<1-2 sentences>",
  "cross_industry_match": true or false,
  "cross_industry_source": "<industry name or null>",
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "gaps": ["gap 1", "gap 2"],
  "overall_recommendation": "shortlist" or "consider" or "reject"
}}
"""
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        result["total_score"] = _compute_total(result)
        return result
    except Exception as e:
        logger.error(f"Claude screening failed: {e}")
        return None


async def _claude_explain_deterministic(candidate: dict, job: dict, scored: dict) -> Optional[dict]:
    """Explain fixed deterministic scores. Model output cannot alter scores or decisions."""
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        fixed = {key: scored[key] for key in (
            "skill_score", "experience_score", "language_score", "location_score",
            "salary_score", "availability_score", "total_score", "overall_recommendation",
        )}
        prompt = f"""You are explaining a deterministic hospitality recruitment score to an Indian recruiter.
The scores and recommendation below are FIXED. Do not rescore, change, or contradict them.

JOB: {json.dumps(_build_job_context(job), default=str)}
CANDIDATE: {json.dumps(_build_candidate_context(candidate), default=str)}
FIXED_RESULT: {json.dumps(fixed)}

Return ONLY JSON with these fields and no numeric scores:
{{
  "skill_explanation": "specific evidence-based sentence",
  "experience_explanation": "specific evidence-based sentence",
  "language_explanation": "specific evidence-based sentence",
  "location_explanation": "specific evidence-based sentence",
  "salary_explanation": "specific evidence-based sentence",
  "availability_explanation": "specific evidence-based sentence",
  "strengths": ["evidence-backed strength"],
  "gaps": ["evidence-backed gap"],
  "summary": "2-3 sentence explanation stating this is a recommendation for recruiter review"
}}"""
        response = client.messages.create(model=CLAUDE_MODEL, max_tokens=1100, messages=[{"role": "user", "content": prompt}])
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.content[0].text.strip())
        result = json.loads(text)
        allowed = {
            "skill_explanation", "experience_explanation", "language_explanation",
            "location_explanation", "salary_explanation", "availability_explanation",
            "strengths", "gaps", "summary",
        }
        return {key: value for key, value in result.items() if key in allowed}
    except Exception as exc:
        logger.warning("Claude explanation unavailable; deterministic explanations retained: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Public: score a single candidate
# ─────────────────────────────────────────────────────────────────────────────

async def score_candidate(
    candidate: dict,
    job: dict,
    blind_mode: bool = False,
    weights: Optional[dict] = None,
    shortlist_threshold: float = 75,
    reject_threshold: float = 45,
    use_ai_explanation: bool = True,
) -> ScreeningResult:
    """
    Score a single candidate against a job across 6 dimensions.
    Scores deterministically. Claude can explain but can never change a score.
    """
    cand_id = candidate.get("id", "")
    blind_id = get_blind_id(cand_id) if cand_id else "C-UNKNOWN"

    scored_candidate = apply_blind_mode(candidate) if blind_mode else candidate

    # Cross-industry detection (uses original candidate data, not blind copy)
    cross = detect_cross_industry(candidate)
    if not cross_industry_applies(cross, job):
        cross = None

    configured_weights = validate_weights(weights)
    raw = deterministic_score_candidate(
        scored_candidate, job, configured_weights, shortlist_threshold, reject_threshold,
    )

    # Apply cross-industry boost to experience score if detected
    if cross and not raw.get("cross_industry_match"):
        raw["cross_industry_match"] = True
        raw["cross_industry_source"] = cross["industry"]
        boost_pts = cross["boost"] * 20  # up to 20 point boost on experience
        raw["experience_score"] = min(raw.get("experience_score", 0) + boost_pts, 100)
        raw["experience_explanation"] = (
            raw.get("experience_explanation", "")
            + f" Cross-industry boost applied ({cross['industry']} background)."
        )
        raw["total_score"] = _compute_total(raw, configured_weights)

    if raw["total_score"] >= shortlist_threshold:
        raw["overall_recommendation"] = "shortlist"
    elif raw["total_score"] < reject_threshold:
        raw["overall_recommendation"] = "reject"
    else:
        raw["overall_recommendation"] = "consider"

    explanation_source = "DETERMINISTIC"
    if use_ai_explanation:
        explanation = await _claude_explain_deterministic(scored_candidate, job, raw)
        if explanation:
            for key in (
                "skill_explanation", "experience_explanation", "language_explanation",
                "location_explanation", "salary_explanation", "availability_explanation",
                "strengths", "gaps",
            ):
                if key in explanation: raw[key] = explanation[key]
            if explanation.get("summary"):
                raw["recommendation_reasons"] = [explanation["summary"], *raw.get("recommendation_reasons", [])]
            explanation_source = "CLAUDE"

    display_name = ""
    if not blind_mode:
        display_name = (
            f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip()
            or candidate.get("name", "")
            or "Unknown"
        )

    def _ds(score_key: str, expl_key: str) -> DimensionScore:
        return DimensionScore(
            score=float(raw.get(score_key, 50)),
            explanation=raw.get(expl_key, ""),
        )

    return ScreeningResult(
        candidate_id=cand_id,
        blind_id=blind_id,
        display_name=display_name,
        total_score=float(raw.get("total_score", 0)),
        skill=        _ds("skill_score",        "skill_explanation"),
        experience=   _ds("experience_score",   "experience_explanation"),
        language=     _ds("language_score",     "language_explanation"),
        location=     _ds("location_score",     "location_explanation"),
        salary=       _ds("salary_score",       "salary_explanation"),
        availability= _ds("availability_score", "availability_explanation"),
        cross_industry_match=raw.get("cross_industry_match", False),
        cross_industry_source=raw.get("cross_industry_source") or (cross["industry"] if cross else ""),
        cross_industry_target=", ".join(cross["maps_to"]) if cross else "",
        cross_industry_note=cross["note"] if cross else "",
        cross_industry_boost=cross["boost"] if cross else 0.0,
        strengths=raw.get("strengths") or [],
        gaps=raw.get("gaps") or [],
        overall_recommendation=raw.get("overall_recommendation", "consider"),
        recommendation_reasons=raw.get("recommendation_reasons") or [],
        scoring_weights=configured_weights,
        scoring_version=SCORING_VERSION,
        explanation_source=explanation_source,
    )


def _result_to_db_row(
    result: ScreeningResult,
    job_id: Optional[str],
    job_role_id: Optional[str],
    org_id: Optional[str],
    blind_mode: bool,
) -> dict:
    return {
        "org_id":                   org_id,
        "job_id":                   job_id,
        "job_role_id":              job_role_id,
        "candidate_id":             result.candidate_id,
        "total_score":              result.total_score,
        "deterministic_score":      result.total_score,
        "skill_score":              result.skill.score,
        "experience_score":         result.experience.score,
        "language_score":           result.language.score,
        "location_score":           result.location.score,
        "salary_score":             result.salary.score,
        "availability_score":       result.availability.score,
        "skill_explanation":        result.skill.explanation,
        "experience_explanation":   result.experience.explanation,
        "language_explanation":     result.language.explanation,
        "location_explanation":     result.location.explanation,
        "salary_explanation":       result.salary.explanation,
        "availability_explanation": result.availability.explanation,
        "cross_industry_match":     result.cross_industry_match,
        "cross_industry_source":    result.cross_industry_source or None,
        "cross_industry_target":    result.cross_industry_target or None,
        "cross_industry_note":      result.cross_industry_note or None,
        "cross_industry_boost":     result.cross_industry_boost,
        "blind_id":                 result.blind_id,
        "blind_mode_used":          blind_mode,
        "overall_recommendation":   result.overall_recommendation,
        "recommendation_reasons":   result.recommendation_reasons,
        "scoring_weights":          result.scoring_weights,
        "scoring_version":          result.scoring_version,
        "explanation_source":       result.explanation_source,
        "score_breakdown": {
            "skill": {"score": result.skill.score, "reason": result.skill.explanation},
            "experience": {"score": result.experience.score, "reason": result.experience.explanation},
            "language": {"score": result.language.score, "reason": result.language.explanation},
            "location": {"score": result.location.score, "reason": result.location.explanation},
            "salary": {"score": result.salary.score, "reason": result.salary.explanation},
            "availability": {"score": result.availability.score, "reason": result.availability.explanation},
            "cross_industry": {"matched": result.cross_industry_match, "source": result.cross_industry_source,
                               "target": result.cross_industry_target, "boost": result.cross_industry_boost,
                               "reason": result.cross_industry_note},
        },
        "auto_shortlisted":         False,
        "strengths":                result.strengths,
        "gaps":                     result.gaps,
        "screened_at":              datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public: screen all candidates for a job
# ─────────────────────────────────────────────────────────────────────────────

async def screen_job_candidates(
    supabase,
    job_id: Optional[str],
    job_role_id: Optional[str],
    org_id: str,
    blind_mode: bool = False,
    screen_all: bool = False,
    triggered_by: Optional[str] = None,
) -> dict:
    """
    Screen all candidates for a given job (or all org candidates).

    Returns dict with:
      - total_screened: int
      - results: list of dicts (serialized ScreeningResult)
    """
    # Fetch job details
    job = {}
    if job_id:
        try:
            row = supabase.table("jobs").select("*").eq("id", job_id).eq("org_id", org_id).single().execute()
            job = row.data or {}
        except Exception as e:
            logger.error(f"Could not fetch job {job_id}: {e}")
    elif job_role_id:
        try:
            row = supabase.table("job_roles").select("*").eq("id", job_role_id).eq("org_id", org_id).single().execute()
            job = row.data or {}
        except Exception as e:
            logger.error(f"Could not fetch job_role {job_role_id}: {e}")

    # Fetch candidates
    try:
        q = supabase.table("candidates").select("*").eq("org_id", org_id)
        if job_id and not screen_all:
            q = q.eq("applied_job_id", job_id)
        candidates = (q.execute()).data or []
    except Exception as e:
        logger.error(f"Could not fetch candidates: {e}")
        candidates = []

    if not candidates:
        return {"total_screened": 0, "results": [], "message": "No candidates found for this job."}

    weights = DEFAULT_WEIGHTS
    shortlist_threshold, reject_threshold = 75.0, 45.0
    try:
        config_rows = (supabase.table("screening_weight_configs").select("*")
                       .eq("org_id", org_id).eq("job_id", job_id).limit(1).execute()).data or []
        if not config_rows:
            config_rows = (supabase.table("screening_weight_configs").select("*")
                           .eq("org_id", org_id).is_("job_id", "null").limit(1).execute()).data or []
        if config_rows:
            config = config_rows[0]
            weights = {key: float(config[f"{key}_weight"]) for key in DEFAULT_WEIGHTS}
            shortlist_threshold = float(config.get("shortlist_threshold", 75))
            reject_threshold = float(config.get("reject_threshold", 45))
    except Exception as exc:
        logger.info("Using default screening weights: %s", exc)

    # Score each candidate
    results: list[ScreeningResult] = []
    for c in candidates:
        try:
            r = await score_candidate(c, job, blind_mode=blind_mode, weights=weights,
                                      shortlist_threshold=shortlist_threshold,
                                      reject_threshold=reject_threshold)
            results.append(r)
        except Exception as e:
            logger.error(f"Error scoring candidate {c.get('id')}: {e}")

    # Rank by total_score
    results.sort(key=lambda x: x.total_score, reverse=True)
    for i, r in enumerate(results, 1):
        r.rank = i

    # Upsert results to DB
    conflict = "job_id,candidate_id" if job_id else "job_role_id,candidate_id"
    for r in results:
        row = _result_to_db_row(r, job_id, job_role_id, org_id, blind_mode)
        try:
            saved = supabase.table("candidate_screening_results").upsert(
                row, on_conflict=conflict
            ).execute()
            if saved.data:
                r.screening_result_id = saved.data[0].get("id")
            # Also update candidate's screening_score
            supabase.table("candidates").update(
                {"screening_score": r.total_score, "blind_id": r.blind_id}
            ).eq("id", r.candidate_id).execute()
            supabase.table("screening_decision_audit").insert({
                "org_id": org_id,
                "screening_result_id": ((saved.data or [{}])[0]).get("id"),
                "candidate_id": r.candidate_id,
                "job_id": job_id,
                "action": "SCREENED",
                "new_value": {"score": r.total_score, "recommendation": r.overall_recommendation,
                              "weights": r.scoring_weights, "version": r.scoring_version},
                "reason": "; ".join(r.recommendation_reasons[:3]) or "Deterministic screening completed",
                "actor_id": triggered_by,
            }).execute()
        except Exception as e:
            logger.error(f"DB upsert failed for candidate {r.candidate_id}: {e}")

    # Log screening run
    try:
        supabase.table("screening_runs").insert({
            "org_id":            org_id,
            "job_id":            job_id,
            "job_role_id":       job_role_id,
            "triggered_by_user": triggered_by,
            "candidate_count":   len(results),
            "shortlisted_count": 0,
            "blind_mode":        blind_mode,
            "screen_all":        screen_all,
        }).execute()
    except Exception:
        pass

    return {
        "total_screened": len(results),
        "results":        [_serialize_result(r) for r in results],
    }


def _serialize_result(r: ScreeningResult) -> dict:
    return {
        "rank":                   r.rank,
        "candidate_id":           r.candidate_id,
        "screening_result_id":    r.screening_result_id,
        "blind_id":               r.blind_id,
        "display_name":           r.display_name,
        "total_score":            r.total_score,
        "skill_score":            r.skill.score,
        "skill_explanation":      r.skill.explanation,
        "experience_score":       r.experience.score,
        "experience_explanation": r.experience.explanation,
        "language_score":         r.language.score,
        "language_explanation":   r.language.explanation,
        "location_score":         r.location.score,
        "location_explanation":   r.location.explanation,
        "salary_score":           r.salary.score,
        "salary_explanation":     r.salary.explanation,
        "availability_score":     r.availability.score,
        "availability_explanation": r.availability.explanation,
        "cross_industry_match":   r.cross_industry_match,
        "cross_industry_source":  r.cross_industry_source,
        "cross_industry_target":  r.cross_industry_target,
        "cross_industry_note":    r.cross_industry_note,
        "strengths":              r.strengths,
        "gaps":                   r.gaps,
        "overall_recommendation": r.overall_recommendation,
        "recommendation_reasons": r.recommendation_reasons,
        "scoring_weights":        r.scoring_weights,
        "scoring_version":        r.scoring_version,
        "explanation_source":     r.explanation_source,
        "auto_shortlisted":       False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public: auto-shortlist top N
# ─────────────────────────────────────────────────────────────────────────────

def auto_shortlist(
    supabase,
    job_id: Optional[str],
    job_role_id: Optional[str],
    org_id: str,
    top_n: int = 10,
    confirmed_by: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict:
    """
    Confirm top recommendations. No writes occur without named recruiter consent.
    """
    if not confirmed_by or not reason or not reason.strip():
        return {"shortlisted": 0, "candidate_ids": [], "requires_confirmation": True,
                "message": "A recruiter must explicitly confirm and provide a reason."}
    try:
        q = (
            supabase.table("candidate_screening_results")
            .select("id,candidate_id,total_score")
            .eq("org_id", org_id)
            .order("total_score", desc=True)
            .limit(top_n)
        )
        if job_id:
            q = q.eq("job_id", job_id)
        elif job_role_id:
            q = q.eq("job_role_id", job_role_id)
        rows = q.execute().data or []
    except Exception as e:
        logger.error(f"auto_shortlist fetch failed: {e}")
        return {"shortlisted": 0, "candidate_ids": []}

    now_iso = datetime.now(timezone.utc).isoformat()
    shortlisted_ids = []
    for row in rows:
        csr_id = row["id"]
        cand_id = row["candidate_id"]
        try:
            supabase.table("candidate_screening_results").update({
                "auto_shortlisted": False,
                "shortlisted_at": now_iso,
                "recruiter_decision": "SHORTLIST_CONFIRMED",
                "decision_by": confirmed_by,
                "decision_at": now_iso,
            }).eq("id", csr_id).execute()
            supabase.table("candidates").update({
                "auto_shortlisted": False,
                "pipeline_stage": "shortlisted",
                "shortlisted_at": now_iso,
            }).eq("id", cand_id).execute()
            try:
                application = (supabase.table("applications").select("id,status").eq("candidate_id", cand_id)
                               .eq("org_id", org_id).order("created_at", desc=True).limit(1).execute()).data or []
                if application:
                    app = application[0]
                    supabase.table("applications").update({"status": "SHORTLISTED", "stage_updated_at": now_iso}).eq("id", app["id"]).execute()
                    supabase.table("application_stage_history").insert({
                        "org_id": org_id, "application_id": app["id"], "candidate_id": cand_id,
                        "job_id": job_id, "from_stage": str(app.get("status") or "screened").lower(),
                        "to_stage": "shortlisted", "notes": reason, "changed_by": confirmed_by,
                    }).execute()
            except Exception as exc:
                logger.warning("Application stage sync failed for confirmed shortlist %s: %s", cand_id, exc)
            supabase.table("screening_decision_audit").insert({
                "org_id": org_id, "screening_result_id": csr_id, "candidate_id": cand_id,
                "job_id": job_id, "action": "SHORTLIST_CONFIRMED",
                "previous_value": {"recommendation_only": True},
                "new_value": {"pipeline_stage": "shortlisted"},
                "reason": reason.strip(), "actor_id": confirmed_by,
            }).execute()
            shortlisted_ids.append(cand_id)
        except Exception as e:
            logger.error(f"Shortlist update failed for {cand_id}: {e}")

    # Update screening run shortlist count
    try:
        supabase.table("screening_runs").update({
            "shortlisted_count": len(shortlisted_ids)
        }).eq("job_id", job_id).order("run_at", desc=True).limit(1).execute()
    except Exception:
        pass

    return {"shortlisted": len(shortlisted_ids), "candidate_ids": shortlisted_ids,
            "requires_confirmation": False, "decision": "RECRUITER_CONFIRMED"}


# ─────────────────────────────────────────────────────────────────────────────
# Public: get blind profile
# ─────────────────────────────────────────────────────────────────────────────

def get_blind_profile(candidate: dict) -> dict:
    """Return an anonymized candidate profile for blind screening review."""
    blind = apply_blind_mode(candidate)
    blind["blind_id"] = get_blind_id(candidate.get("id", ""))
    blind["id"] = blind["blind_id"]  # replace real ID with blind ID in response
    return blind
