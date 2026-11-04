"""
Indian Diversity Reporting Service

Laws:
  RPWD Act 2016                  — disability classification + rights
  Transgender Persons Act 2019   — gender identity recognition
  Equal Remuneration Act 1976    — gender pay gap obligation
  Factories Act 1948             — statutory diversity returns (≥ 500 workers)
  DPDP Act 2023                  — consent required before collection

Design rules (non-negotiable):
  • Gender and PwD status are always optional (voluntary self-declaration).
  • Religion is NEVER collected — no parameter, no DB column, no API field.
  • SC/ST/OBC/EWS collected ONLY when org.statutory_reporting_required = true.
  • Blind screening strips name, email, phone, location — does not modify DB.
"""

from __future__ import annotations

import hashlib
import logging
import statistics
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

VALID_GENDERS = {
    "MALE", "FEMALE", "TRANSGENDER", "NON_BINARY", "PREFER_NOT_TO_SAY",
}

VALID_SOCIAL_CATEGORIES = {
    "SC", "ST", "OBC", "EWS", "GENERAL", "PREFER_NOT_TO_SAY",
}

VALID_PWD_CATEGORIES = {
    "LOCOMOTOR", "VISUAL", "HEARING", "INTELLECTUAL",
    "MENTAL_ILLNESS", "AUTISM", "MULTIPLE", "OTHER",
}

# Fields hidden in blind screening (values replaced, not deleted)
BLIND_FIELDS = ("first_name", "last_name", "email", "phone",
                "location", "city", "state", "profile_photo", "hometown")

# Hired stages — candidate is considered "hired" when pipeline_stage is one of these
HIRED_STAGES = {"hired", "offer_accepted", "joined", "onboarded"}


# ─────────────────────────────────────────────────────────────────────────────
# Blind screening
# ─────────────────────────────────────────────────────────────────────────────

def apply_blind_screening(candidate: dict) -> dict:
    """
    Return a copy of the candidate dict with identifying fields redacted.
    Does NOT modify the database — purely a presentation transformation.

    Hidden: name, email, phone, location, city, state, profile_photo, hometown.
    Kept: skills, experience, certifications, pipeline_stage, scores, etc.
    """
    blinded = dict(candidate)
    cid     = candidate.get("id", "UNKNOWN")
    code    = cid.replace("-", "")[:6].upper()

    blinded["first_name"]    = "Candidate"
    blinded["last_name"]     = f"#{code}"
    blinded["phone"]         = None
    blinded["profile_photo"] = None
    blinded["location"]      = None
    blinded["city"]          = None
    blinded["state"]         = None
    blinded["hometown"]      = None

    if candidate.get("email"):
        # Hash email so uniqueness is preserved but address is not revealed
        h = hashlib.sha256(candidate["email"].encode()).hexdigest()[:12]
        blinded["email"] = f"blind-{h}@review.internal"

    blinded["_blind_screening"] = True
    blinded["_blind_code"]      = code
    return blinded


def blind_screen_batch(candidates: list[dict]) -> list[dict]:
    """Apply blind screening to a list of candidate dicts."""
    return [apply_blind_screening(c) for c in candidates]


# ─────────────────────────────────────────────────────────────────────────────
# Statutory reporting gate
# ─────────────────────────────────────────────────────────────────────────────

def is_statutory_reporting_required(supabase, org_id: str) -> bool:
    """
    Check whether the org has statutory_reporting_required = true.
    SC/ST/OBC/EWS collection is gated on this flag.
    """
    try:
        res = (
            supabase.table("organizations")
            .select("statutory_reporting_required")
            .eq("id", org_id)
            .limit(1)
            .execute()
        )
        if res.data:
            return bool(res.data[0].get("statutory_reporting_required", False))
    except Exception as exc:
        logger.warning("statutory_reporting_required lookup failed: %s", exc)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Data collection
# ─────────────────────────────────────────────────────────────────────────────

def collect_diversity_data(
    supabase,
    org_id:              str,
    candidate_id:        str,
    gender:              Optional[str] = None,
    is_pwd:              bool          = False,
    pwd_category:        Optional[str] = None,
    pwd_cert_number:     Optional[str] = None,
    pwd_disability_pct:  Optional[int] = None,
    is_ex_serviceman:    bool          = False,
    service_branch:      Optional[str] = None,
    social_category:     Optional[str] = None,
    self_declared:       bool          = True,
    dpdp_consent_id:     Optional[str] = None,
) -> dict:
    """
    Persist voluntary diversity data for a candidate.

    Rules:
      • gender and is_pwd are always acceptable (if DPDP consent given).
      • social_category (SC/ST/OBC/EWS) requires statutory_reporting_required=true on org.
      • Religion is never accepted — any caller passing it must be rejected upstream.

    Raises:
      ValueError — social_category submitted without statutory reporting enabled.
      RuntimeError — DB insert failed.
    """
    if not dpdp_consent_id:
        raise ValueError(
            "dpdp_consent_id is required. Obtain DPDP SENSITIVE_DATA consent "
            "from the candidate before recording diversity data."
        )

    if gender and gender not in VALID_GENDERS:
        raise ValueError(
            f"gender must be one of: {sorted(VALID_GENDERS)}"
        )

    if social_category:
        if social_category not in VALID_SOCIAL_CATEGORIES:
            raise ValueError(
                f"social_category must be one of: {sorted(VALID_SOCIAL_CATEGORIES)}"
            )
        if not is_statutory_reporting_required(supabase, org_id):
            raise ValueError(
                "social_category (SC/ST/OBC/EWS) can only be collected when "
                "statutory_reporting_required = true on the organisation. "
                "This field is not collected for general diversity monitoring — "
                "use gender and is_pwd instead."
            )

    if pwd_category and pwd_category.upper() not in VALID_PWD_CATEGORIES:
        raise ValueError(
            f"pwd_category must be one of: {sorted(VALID_PWD_CATEGORIES)}"
        )

    now = datetime.utcnow().isoformat()
    payload = {
        "org_id":            org_id,
        "candidate_id":      candidate_id,
        "gender":            gender,
        "is_pwd":            is_pwd,
        "pwd_category":      pwd_category.upper() if pwd_category else None,
        "pwd_cert_number":   pwd_cert_number,
        "pwd_disability_pct":pwd_disability_pct,
        "is_ex_serviceman":  is_ex_serviceman,
        "service_branch":    service_branch,
        "social_category":   social_category,
        "dpdp_consent_id":   dpdp_consent_id,
        "self_declared":     self_declared,
        "collected_at":      now,
    }

    # Upsert (candidate may update their own data)
    result = (
        supabase.table("india_diversity_data")
        .insert(payload)
        .execute()
    )
    if not result.data:
        raise RuntimeError("Failed to save diversity data")

    # Denormalise gender + pwd to candidates table for fast dashboard queries
    _sync_candidate_diversity(supabase, candidate_id, gender, is_pwd)

    return result.data[0]


def _sync_candidate_diversity(supabase, candidate_id: str,
                               gender: Optional[str], is_pwd: bool) -> None:
    """Best-effort sync of gender + is_pwd to candidates table for fast queries."""
    update: dict = {}
    if gender:
        update["gender"] = gender
    if is_pwd:
        update["is_pwd"] = True
    if update:
        try:
            supabase.table("candidates").update(update).eq("id", candidate_id).execute()
        except Exception as exc:
            logger.warning("diversity sync to candidates failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard computation (pure — receives rows, not supabase)
# ─────────────────────────────────────────────────────────────────────────────

def _count_by_gender(rows: list[dict], stage_filter: Optional[set] = None) -> dict:
    counts: dict[str, int] = {}
    for r in rows:
        if stage_filter and (r.get("pipeline_stage") or "").lower() not in stage_filter:
            continue
        g = r.get("gender") or "NOT_DISCLOSED"
        counts[g] = counts.get(g, 0) + 1
    return counts


def compute_gender_breakdown(candidates: list[dict]) -> dict:
    """
    Split candidates into applications (all) and hires (hired stages).
    Returns: {applications: {gender: count}, hires: {gender: count}}
    """
    applications = _count_by_gender(candidates)
    hires        = _count_by_gender(candidates, stage_filter=HIRED_STAGES)

    total_apps  = sum(applications.values())
    total_hires = sum(hires.values())

    hire_rate_by_gender: dict[str, Optional[float]] = {}
    for gender, app_count in applications.items():
        hired = hires.get(gender, 0)
        hire_rate_by_gender[gender] = round(hired / app_count * 100, 1) if app_count else None

    return {
        "total_applications":    total_apps,
        "total_hires":           total_hires,
        "applications_by_gender": applications,
        "hires_by_gender":       hires,
        "hire_rate_by_gender":   hire_rate_by_gender,
    }


def compute_pwd_metrics(candidates: list[dict]) -> dict:
    """Applications and hires split by PwD / non-PwD status."""
    total = len(candidates)
    pwd_apps  = sum(1 for c in candidates if c.get("is_pwd"))
    non_pwd   = total - pwd_apps

    pwd_hires = sum(
        1 for c in candidates
        if c.get("is_pwd") and (c.get("pipeline_stage") or "").lower() in HIRED_STAGES
    )
    total_hires = sum(
        1 for c in candidates
        if (c.get("pipeline_stage") or "").lower() in HIRED_STAGES
    )

    return {
        "total_applications":     total,
        "pwd_applications":       pwd_apps,
        "non_pwd_applications":   non_pwd,
        "pwd_pct_of_applications": round(pwd_apps / total * 100, 1) if total else 0,
        "total_hires":            total_hires,
        "pwd_hires":              pwd_hires,
        "pwd_hire_rate":          round(pwd_hires / total_hires * 100, 1) if total_hires else 0,
        "law":                    "RPWD Act 2016",
    }


def compute_gender_pay_gap(candidates: list[dict]) -> dict:
    """
    Compute gender pay gap from offered_salary_inr on candidates.
    Returns median pay gap (male vs female) per Equal Remuneration Act 1976.

    Returns {"insufficient_data": True} when fewer than 5 salaries per gender.
    """
    male_salaries   = [c["offered_salary_inr"] for c in candidates
                       if c.get("gender") == "MALE" and c.get("offered_salary_inr")]
    female_salaries = [c["offered_salary_inr"] for c in candidates
                       if c.get("gender") == "FEMALE" and c.get("offered_salary_inr")]

    if len(male_salaries) < 5 or len(female_salaries) < 5:
        return {
            "insufficient_data":    True,
            "reason":               "Fewer than 5 salary records per gender",
            "male_sample":          len(male_salaries),
            "female_sample":        len(female_salaries),
            "law":                  "Equal Remuneration Act 1976",
        }

    median_male   = statistics.median(male_salaries)
    median_female = statistics.median(female_salaries)
    mean_male     = statistics.mean(male_salaries)
    mean_female   = statistics.mean(female_salaries)

    # Positive gap = men earn more; negative = women earn more
    median_gap_pct = round((median_male - median_female) / median_male * 100, 2)
    mean_gap_pct   = round((mean_male - mean_female) / mean_male * 100, 2)

    return {
        "insufficient_data":      False,
        "median_male_inr":        round(median_male, 2),
        "median_female_inr":      round(median_female, 2),
        "mean_male_inr":          round(mean_male, 2),
        "mean_female_inr":        round(mean_female, 2),
        "median_pay_gap_pct":     median_gap_pct,
        "mean_pay_gap_pct":       mean_gap_pct,
        "male_sample_size":       len(male_salaries),
        "female_sample_size":     len(female_salaries),
        "direction":              "men_earn_more" if median_gap_pct > 0 else "women_earn_more"
                                  if median_gap_pct < 0 else "equal",
        "law":                    "Equal Remuneration Act 1976",
    }


def compute_social_category_breakdown(diversity_rows: list[dict]) -> dict:
    """Aggregate SC/ST/OBC/EWS counts — only called when statutory_reporting_required=true."""
    counts: dict[str, int] = {}
    for r in diversity_rows:
        cat = r.get("social_category") or "NOT_DISCLOSED"
        counts[cat] = counts.get(cat, 0) + 1
    return {
        "statutory_categories": counts,
        "total_records":        len(diversity_rows),
        "note":                 "Collected under Factories Act / statutory obligation",
    }


# ─────────────────────────────────────────────────────────────────────────────
# DB-backed dashboard builder
# ─────────────────────────────────────────────────────────────────────────────

def build_diversity_dashboard(
    supabase,
    org_id:    str,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
) -> dict:
    """
    Fetch candidate data from DB and return full diversity dashboard payload.
    """
    # Candidates with gender/pwd/salary/stage
    q = (
        supabase.table("candidates")
        .select("id, gender, is_pwd, offered_salary_inr, pipeline_stage, created_at, hired_at")
        .eq("org_id", org_id)
    )
    if date_from:
        q = q.gte("created_at", date_from)
    if date_to:
        q = q.lte("created_at", date_to)

    candidates = q.execute().data or []

    gender_data = compute_gender_breakdown(candidates)
    pwd_data    = compute_pwd_metrics(candidates)
    pay_gap     = compute_gender_pay_gap(candidates)

    # Social category — only if org has statutory reporting
    statutory = is_statutory_reporting_required(supabase, org_id)
    social_data = None
    if statutory:
        diversity_rows = (
            supabase.table("india_diversity_data")
            .select("social_category")
            .eq("org_id", org_id)
            .execute()
        ).data or []
        social_data = compute_social_category_breakdown(diversity_rows)

    return {
        "org_id":                    org_id,
        "date_from":                 date_from,
        "date_to":                   date_to,
        "total_candidates":          len(candidates),
        "gender_breakdown":          gender_data,
        "pwd_metrics":               pwd_data,
        "gender_pay_gap":            pay_gap,
        "statutory_reporting":       statutory,
        "social_category_breakdown": social_data,
        "generated_at":              datetime.utcnow().isoformat(),
    }
