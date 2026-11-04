"""Canonical candidate/application ATS helpers."""
from __future__ import annotations

import re
from datetime import datetime, timezone

PIPELINE_STAGES = [
    "applied", "screened", "shortlisted", "interview", "selected",
    "offer", "offer_accepted", "onboarding", "hired",
]
TERMINAL_STAGES = ["rejected", "withdrawn"]
ALL_STAGES = PIPELINE_STAGES + TERMINAL_STAGES

STAGE_TIMESTAMPS = {
    "screened": "screened_at", "shortlisted": "shortlisted_at", "interview": "interview_at",
    "selected": "selected_at", "offer": "offered_at", "offer_accepted": "offer_accepted_at",
    "onboarding": "onboarding_at", "hired": "hired_at",
}


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def normalize_phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else digits


def duplicate_reasons(candidate: dict, other: dict) -> list[str]:
    reasons = []
    if normalize_email(candidate.get("email")) and normalize_email(candidate.get("email")) == normalize_email(other.get("email")):
        reasons.append("email")
    if normalize_phone(candidate.get("phone")) and normalize_phone(candidate.get("phone")) == normalize_phone(other.get("phone")):
        reasons.append("phone")
    return reasons


def matches_candidate(candidate: dict, *, search: str | None = None, location: str | None = None,
                      tags: list[str] | None = None, skills: list[str] | None = None,
                      languages: list[str] | None = None, min_experience: int | None = None) -> bool:
    if search:
        haystack = " ".join(str(candidate.get(k) or "") for k in ("first_name", "last_name", "email", "phone", "location", "city"))
        if search.lower() not in haystack.lower(): return False
    if location and location.lower() not in " ".join(filter(None, [candidate.get("location"), candidate.get("city"), candidate.get("state")])).lower(): return False
    candidate_tags = {str(v).lower() for v in (candidate.get("tags") or [])}
    if tags and not set(v.lower() for v in tags).issubset(candidate_tags): return False
    raw_skills = candidate.get("parsed_skills") or []
    if isinstance(raw_skills, dict): raw_skills = raw_skills.get("skills") or list(raw_skills.keys())
    candidate_skills = {str(v).lower() for v in raw_skills}
    if skills and not set(v.lower() for v in skills).issubset(candidate_skills): return False
    candidate_languages = {str(v).lower() for v in (candidate.get("languages") or [])}
    if languages and not set(v.lower() for v in languages).issubset(candidate_languages): return False
    if min_experience is not None and int(candidate.get("years_experience") or 0) < min_experience: return False
    return True


def stage_update(stage: str) -> dict:
    if stage not in ALL_STAGES:
        raise ValueError(f"Unsupported pipeline stage: {stage}")
    now = datetime.now(timezone.utc).isoformat()
    values = {"pipeline_stage": stage, "updated_at": now}
    if stage in STAGE_TIMESTAMPS: values[STAGE_TIMESTAMPS[stage]] = now
    if stage in {"screened", "shortlisted"}: values["qualified"] = True
    return values
