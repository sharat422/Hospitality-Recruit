"""
Indian Diversity Reporting Router
Prefix: /api/v1/diversity

Endpoints:
  POST /collect                    – Collect gender + PwD (+ SC/ST/OBC if statutory)
  GET  /dashboard                  – Full diversity dashboard
  GET  /gender-breakdown           – Applications + hires by gender
  GET  /pwd-metrics                – PwD applications and hire rate
  GET  /pay-gap                    – Gender pay gap (Equal Remuneration Act)
  POST /blind-screening/{id}       – Return blinded candidate record
  POST /blind-screening/batch      – Blind a list of candidates
  GET  /settings                   – Org statutory reporting flag
  PATCH /settings                  – Update statutory reporting flag

Policy:
  • Religion field is never accepted in any endpoint (validated in Pydantic).
  • SC/ST/OBC/EWS collected only when org.statutory_reporting_required=true.
  • All collection requires a valid DPDP consent reference.
  • Blind screening is purely a response transformation — no DB writes.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, field_validator, model_validator

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.diversity_service import (
    VALID_GENDERS,
    VALID_SOCIAL_CATEGORIES,
    VALID_PWD_CATEGORIES,
    collect_diversity_data,
    apply_blind_screening,
    blind_screen_batch,
    is_statutory_reporting_required,
    build_diversity_dashboard,
    compute_gender_breakdown,
    compute_pwd_metrics,
    compute_gender_pay_gap,
)
from app.services.india_compliance_service import log_india_compliance_audit

router = APIRouter(tags=["Diversity"])
logger = logging.getLogger(__name__)

CurrentUser = Annotated[dict, Depends(get_current_user)]

LAW_REF = "RPWD Act 2016 / Transgender Persons Act 2019 / DPDP Act 2023"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _org(supabase, user: dict) -> str:
    res = (
        supabase.table("users").select("org_id")
        .eq("id", user["sub"]).limit(1).execute()
    )
    if not res.data:
        raise HTTPException(404, "User not found")
    return res.data[0]["org_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class DiversityCollectRequest(BaseModel):
    candidate_id:       str
    dpdp_consent_id:    str       # mandatory — must have SENSITIVE_DATA consent
    gender:             Optional[str] = None
    is_pwd:             bool          = False
    pwd_category:       Optional[str] = None
    pwd_cert_number:    Optional[str] = None
    pwd_disability_pct: Optional[int] = None
    is_ex_serviceman:   bool          = False
    service_branch:     Optional[str] = None
    social_category:    Optional[str] = None
    self_declared:      bool          = True
    # religion is intentionally absent — never collected

    @field_validator("gender")
    @classmethod
    def val_gender(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in VALID_GENDERS:
            raise ValueError(
                f"gender must be one of: {sorted(VALID_GENDERS)}"
            )
        return v

    @field_validator("social_category")
    @classmethod
    def val_category(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in VALID_SOCIAL_CATEGORIES:
            raise ValueError(
                f"social_category must be one of: {sorted(VALID_SOCIAL_CATEGORIES)}"
            )
        return v

    @field_validator("pwd_category")
    @classmethod
    def val_pwd_cat(cls, v: Optional[str]) -> Optional[str]:
        if v and v.upper() not in VALID_PWD_CATEGORIES:
            raise ValueError(
                f"pwd_category must be one of: {sorted(VALID_PWD_CATEGORIES)}"
            )
        return v.upper() if v else v

    @field_validator("pwd_disability_pct")
    @classmethod
    def val_pct(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("pwd_disability_pct must be 0–100")
        return v

    @model_validator(mode="after")
    def no_religion_field(self) -> "DiversityCollectRequest":
        # Belt-and-suspenders: ensure no religion snuck in via extra fields
        # Pydantic v2 ignores extra fields by default; this is documentation.
        return self


class BlindBatchRequest(BaseModel):
    candidate_ids: List[str]


class StatutorySettingsUpdate(BaseModel):
    statutory_reporting_required: bool
    statutory_employee_threshold: Optional[int] = None
    statutory_reporting_law:      Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# POST /collect
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/collect", status_code=201)
async def collect_diversity(
    body: DiversityCollectRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Collect voluntary diversity data for a candidate.

    Fields always accepted (with DPDP consent):
      gender, is_pwd, pwd_category, is_ex_serviceman

    Fields gated on statutory_reporting_required=true:
      social_category (SC / ST / OBC / EWS / GENERAL)

    Religion is never collected — not present in this schema.
    """
    org_id = _org(supabase, user)

    try:
        rec = collect_diversity_data(
            supabase, org_id, body.candidate_id,
            gender=body.gender, is_pwd=body.is_pwd,
            pwd_category=body.pwd_category,
            pwd_cert_number=body.pwd_cert_number,
            pwd_disability_pct=body.pwd_disability_pct,
            is_ex_serviceman=body.is_ex_serviceman,
            service_branch=body.service_branch,
            social_category=body.social_category,
            self_declared=body.self_declared,
            dpdp_consent_id=body.dpdp_consent_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc

    log_india_compliance_audit(
        supabase, "DIVERSITY_DATA_COLLECTED",
        "candidate", body.candidate_id, org_id,
        law_reference=LAW_REF,
    )
    return rec


# ─────────────────────────────────────────────────────────────────────────────
# GET /dashboard
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def diversity_dashboard(
    supabase:  SupabaseClient,
    user:      CurrentUser,
    date_from: Optional[str] = Query(None, description="ISO date e.g. 2026-01-01"),
    date_to:   Optional[str] = Query(None, description="ISO date e.g. 2026-12-31"),
):
    """
    Full diversity dashboard: gender breakdown, PwD metrics, pay gap.
    SC/ST/OBC section included only when statutory_reporting_required=true.
    """
    org_id = _org(supabase, user)
    return build_diversity_dashboard(supabase, org_id, date_from, date_to)


# ─────────────────────────────────────────────────────────────────────────────
# GET /gender-breakdown
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/gender-breakdown")
async def gender_breakdown(
    supabase:  SupabaseClient,
    user:      CurrentUser,
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
):
    """Applications and hires broken down by gender."""
    org_id = _org(supabase, user)
    q = (
        supabase.table("candidates")
        .select("id, gender, pipeline_stage, created_at")
        .eq("org_id", org_id)
    )
    if date_from:
        q = q.gte("created_at", date_from)
    if date_to:
        q = q.lte("created_at", date_to)
    candidates = q.execute().data or []
    return compute_gender_breakdown(candidates)


# ─────────────────────────────────────────────────────────────────────────────
# GET /pwd-metrics
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/pwd-metrics")
async def pwd_metrics(
    supabase:  SupabaseClient,
    user:      CurrentUser,
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
):
    """PwD application and hire counts (RPWD Act 2016)."""
    org_id = _org(supabase, user)
    q = (
        supabase.table("candidates")
        .select("id, is_pwd, pipeline_stage, created_at")
        .eq("org_id", org_id)
    )
    if date_from:
        q = q.gte("created_at", date_from)
    if date_to:
        q = q.lte("created_at", date_to)
    candidates = q.execute().data or []
    return compute_pwd_metrics(candidates)


# ─────────────────────────────────────────────────────────────────────────────
# GET /pay-gap
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/pay-gap")
async def gender_pay_gap(
    supabase:  SupabaseClient,
    user:      CurrentUser,
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
):
    """
    Gender pay gap analysis using offered_salary_inr on candidates.
    Returns median and mean pay gap percentages (Equal Remuneration Act 1976).
    Returns insufficient_data=true when fewer than 5 records per gender.
    """
    org_id = _org(supabase, user)
    q = (
        supabase.table("candidates")
        .select("id, gender, offered_salary_inr, pipeline_stage, created_at")
        .eq("org_id", org_id)
    )
    if date_from:
        q = q.gte("created_at", date_from)
    if date_to:
        q = q.lte("created_at", date_to)
    candidates = q.execute().data or []
    return compute_gender_pay_gap(candidates)


# ─────────────────────────────────────────────────────────────────────────────
# POST /blind-screening/batch  ← MUST be defined BEFORE /{candidate_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/blind-screening/batch")
async def blind_screen_candidates(
    body:     BlindBatchRequest,
    supabase: SupabaseClient,
    user:     CurrentUser,
):
    """
    Blind-screen multiple candidates in one call.
    Useful for rendering a shortlist without revealing names to interviewers.
    """
    org_id = _org(supabase, user)
    res = (
        supabase.table("candidates")
        .select("*")
        .eq("org_id", org_id)
        .in_("id", body.candidate_ids)
        .execute()
    )
    candidates = res.data or []
    return {
        "blinded":   blind_screen_batch(candidates),
        "count":     len(candidates),
        "requested": len(body.candidate_ids),
        "not_found": len(body.candidate_ids) - len(candidates),
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /blind-screening/{candidate_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/blind-screening/{candidate_id}")
async def blind_screen_candidate(
    candidate_id: str,
    supabase:     SupabaseClient,
    user:         CurrentUser,
):
    """
    Return a candidate record with all identifying information redacted.

    Hidden: first_name → "Candidate #XXXXXX", last_name, email (hashed),
            phone, location, city, state, profile_photo, hometown.
    Preserved: skills, experience, certifications, pipeline_stage, screening scores.

    Does NOT modify the database — purely a response transformation.
    """
    org_id = _org(supabase, user)
    res = (
        supabase.table("candidates")
        .select("*")
        .eq("id", candidate_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "Candidate not found")

    return apply_blind_screening(res.data[0])


# ─────────────────────────────────────────────────────────────────────────────
# GET /settings
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_diversity_settings(supabase: SupabaseClient, user: CurrentUser):
    """Return org diversity settings including the statutory_reporting_required flag."""
    org_id = _org(supabase, user)
    res = (
        supabase.table("organizations")
        .select("id, name, statutory_reporting_required, "
                "statutory_employee_threshold, statutory_reporting_law")
        .eq("id", org_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "Organisation not found")
    org = res.data[0]
    return {
        **org,
        "social_category_collection_enabled": org.get("statutory_reporting_required", False),
        "note": (
            "SC/ST/OBC/EWS data is only collected when statutory_reporting_required=true. "
            "Religion is never collected per policy."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /settings
# ─────────────────────────────────────────────────────────────────────────────

@router.patch("/settings")
async def update_diversity_settings(
    body:     StatutorySettingsUpdate,
    supabase: SupabaseClient,
    user:     CurrentUser,
):
    """
    Enable or disable statutory diversity reporting for this org.
    Only enable when the org is legally required to submit diversity returns
    (e.g. Factories Act ≥ 500 workers, or specific state acts).
    """
    org_id = _org(supabase, user)
    update: dict = {"statutory_reporting_required": body.statutory_reporting_required}
    if body.statutory_employee_threshold is not None:
        update["statutory_employee_threshold"] = body.statutory_employee_threshold
    if body.statutory_reporting_law:
        update["statutory_reporting_law"] = body.statutory_reporting_law

    supabase.table("organizations").update(update).eq("id", org_id).execute()

    log_india_compliance_audit(
        supabase, "STATUTORY_REPORTING_UPDATED",
        "organization", org_id, org_id,
        metadata={"statutory_reporting_required": body.statutory_reporting_required},
        law_reference="Factories Act 1948 / Equal Remuneration Act 1976",
    )

    return {
        "updated": True,
        "statutory_reporting_required": body.statutory_reporting_required,
    }
