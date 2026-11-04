"""
Indian Labour Compliance Router
Prefix: /api/v1/labour

Dedicated router for all labour law compliance checks — keeps concerns
separate from the broader india_compliance router.

Endpoints:
  GET  /minimum-wages/states           – All states with wage data
  GET  /minimum-wages                  – Wages for a state (+ industry filter)
  POST /minimum-wages/lookup           – Single row lookup
  POST /minimum-wages/check            – Salary compliance check
  POST /working-hours/check            – Single shift check (stateless)
  POST /working-hours/check-rest       – 12-hour rest between shifts
  POST /working-hours/check-weekly     – Weekly hours check
  POST /working-hours/log              – Log shift + run all checks (DB-backed)
  POST /working-hours/log-rest         – Log rest period (DB-backed)
  POST /epf-esic/calculate             – EPF calculator
  POST /epf-esic/esic-calculate        – ESIC calculator
  POST /epf-esic/full                  – EPF + ESIC combined
  GET  /epf-esic/thresholds            – Threshold reference card
  POST /gratuity/calculate             – Gratuity calculator
  GET  /audit-log                      – Compliance audit trail
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, field_validator

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.labour_compliance_service import (
    lookup_minimum_wage,
    check_salary_compliance,
    list_wages_for_state,
    get_all_seeded_states,
    check_shift_hours,
    check_rest_period,
    check_weekly_hours,
    check_night_shift_compliance,
    log_shift_and_check,
    log_rest_period,
    calculate_epf,
    calculate_esic,
    calculate_full_social_security,
    calculate_gratuity,
    log_labour_audit,
    VALID_INDUSTRIES,
    VALID_SKILL_CATEGORIES,
    DAILY_STANDARD_HOURS,
    MAX_DAILY_HOURS_SHOP,
    MAX_WEEKLY_HOURS,
    MIN_REST_BETWEEN_SHIFTS_H,
    EPF_WAGE_CEILING_INR,
    EPF_EMPLOYEE_PCT,
    EPF_EMPLOYER_EPS_PCT,
    EPF_EMPLOYER_EPF_PCT,
    ESIC_WAGE_CEILING_INR,
    ESIC_EMPLOYEE_PCT,
    ESIC_EMPLOYER_PCT,
    GRATUITY_MIN_YEARS,
    NATIONAL_FLOOR_WAGE_INR,
    OT_RATE_MULTIPLIER,
)

router = APIRouter(tags=["Labour Compliance"])
logger = logging.getLogger(__name__)

CurrentUser = Annotated[dict, Depends(get_current_user)]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_org_id(supabase, user: dict) -> str:
    res = supabase.table("users").select("org_id").eq("id", user["sub"]).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "User not found")
    return res.data[0]["org_id"]


def _parse_dt(s: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        raise HTTPException(422, f"{field} must be ISO 8601 datetime, e.g. 2026-06-01T09:00:00")


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic request models
# ─────────────────────────────────────────────────────────────────────────────

class WageLookupRequest(BaseModel):
    state_code:     str
    skill_category: str
    industry:       str = "HOSPITALITY"
    zone:           str = "A"

    @field_validator("skill_category")
    @classmethod
    def val_skill(cls, v):
        v = v.upper()
        if v not in VALID_SKILL_CATEGORIES:
            raise ValueError(f"skill_category must be one of {sorted(VALID_SKILL_CATEGORIES)}")
        return v

    @field_validator("industry")
    @classmethod
    def val_industry(cls, v):
        v = v.upper()
        if v not in VALID_INDUSTRIES:
            raise ValueError(f"industry must be one of {sorted(VALID_INDUSTRIES)}")
        return v


class SalaryComplianceRequest(BaseModel):
    state_code:           str
    skill_category:       str
    offered_monthly_inr:  float
    industry:             str = "HOSPITALITY"
    zone:                 str = "A"
    candidate_id:         Optional[str] = None

    @field_validator("skill_category")
    @classmethod
    def val_skill(cls, v): return v.upper()

    @field_validator("offered_monthly_inr")
    @classmethod
    def val_salary(cls, v):
        if v <= 0:
            raise ValueError("offered_monthly_inr must be positive")
        return v


class ShiftHoursRequest(BaseModel):
    shift_start:        str    # ISO datetime
    shift_end:          str    # ISO datetime
    break_hours:        float = 0.5
    establishment_type: str   = "SHOP"
    hourly_rate_inr:    float = 0.0

    @field_validator("establishment_type")
    @classmethod
    def val_est(cls, v):
        v = v.upper()
        if v not in ("FACTORY", "SHOP"):
            raise ValueError("establishment_type must be FACTORY or SHOP")
        return v


class RestPeriodRequest(BaseModel):
    previous_shift_end:  str   # ISO datetime
    current_shift_start: str   # ISO datetime
    candidate_id:        Optional[str] = None


class WeeklyHoursRequest(BaseModel):
    weekly_actual_hours: float
    establishment_type:  str = "SHOP"

    @field_validator("weekly_actual_hours")
    @classmethod
    def val_hours(cls, v):
        if v < 0:
            raise ValueError("weekly_actual_hours must be non-negative")
        return v


class ShiftLogRequest(BaseModel):
    shift_start:          str
    shift_end:            str
    break_hours:          float = 0.5
    establishment_type:   str   = "SHOP"
    candidate_id:         Optional[str] = None
    state_code:           Optional[str] = None
    hourly_rate_inr:      float = 0.0
    weekly_hours_so_far:  float = 0.0
    is_female_worker:     bool  = False
    night_shift_consent:  bool  = False
    transport_arranged:   bool  = False


class RestLogRequest(BaseModel):
    previous_shift_end:  str
    current_shift_start: str
    candidate_id:        Optional[str] = None
    state_code:          Optional[str] = None


class EPFRequest(BaseModel):
    monthly_basic_da_inr: float

    @field_validator("monthly_basic_da_inr")
    @classmethod
    def val_salary(cls, v):
        if v <= 0:
            raise ValueError("monthly_basic_da_inr must be positive")
        return v


class ESICRequest(BaseModel):
    monthly_gross_inr: float

    @field_validator("monthly_gross_inr")
    @classmethod
    def val_salary(cls, v):
        if v <= 0:
            raise ValueError("monthly_gross_inr must be positive")
        return v


class FullSSRequest(BaseModel):
    monthly_basic_da_inr: float   # EPF basis
    monthly_gross_inr:    float   # ESIC basis


class GratuityRequest(BaseModel):
    monthly_last_drawn_inr: float
    years_of_service:       float

    @field_validator("years_of_service")
    @classmethod
    def val_years(cls, v):
        if v < 0:
            raise ValueError("years_of_service must be non-negative")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Minimum Wages endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/minimum-wages/states")
async def list_wage_states(supabase: SupabaseClient, user: CurrentUser):
    """Return all states/UTs that have minimum wage data seeded."""
    _get_org_id(supabase, user)
    return get_all_seeded_states(supabase)


@router.get("/minimum-wages")
async def list_wages(
    supabase: SupabaseClient,
    user: CurrentUser,
    state_code: str = Query(..., description="Two-letter state code e.g. MH, DL, KA"),
    industry:   str = Query("HOSPITALITY"),
):
    """List all current minimum wage rows for a state (all skill categories)."""
    _get_org_id(supabase, user)
    rows = list_wages_for_state(supabase, state_code, industry)
    if not rows:
        raise HTTPException(404, f"No wage data found for state={state_code}, industry={industry}")
    return rows


@router.post("/minimum-wages/lookup")
async def wage_lookup(
    body: WageLookupRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Fetch a single minimum wage row for (state, skill, industry, zone)."""
    _get_org_id(supabase, user)
    row = lookup_minimum_wage(supabase, body.state_code, body.skill_category,
                              body.industry, body.zone)
    if not row:
        raise HTTPException(404, "No matching wage data found")
    return row


@router.post("/minimum-wages/check")
async def salary_compliance_check(
    body: SalaryComplianceRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Check whether the offered salary meets state minimum wage + national floor.
    Audit-logged as WAGE_COMPLIANCE_CHECK.
    """
    org_id = _get_org_id(supabase, user)

    result = check_salary_compliance(
        supabase,
        body.state_code,
        body.skill_category,
        body.offered_monthly_inr,
        body.industry,
        body.zone,
    )

    log_labour_audit(
        supabase, "WAGE_COMPLIANCE_CHECK",
        org_id=org_id,
        entity_id=body.candidate_id,
        metadata={
            "state":       body.state_code,
            "skill":       body.skill_category,
            "offered_inr": body.offered_monthly_inr,
            "compliant":   result.get("compliant"),
        },
        law_reference="Minimum Wages Act 1948 / Code on Wages 2019",
    )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Working Hours endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/working-hours/check")
async def check_shift(
    body: ShiftHoursRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Stateless single-shift check: daily hours, spread-over, overtime.
    Returns violations without saving to DB.
    """
    org_id = _get_org_id(supabase, user)
    start  = _parse_dt(body.shift_start, "shift_start")
    end    = _parse_dt(body.shift_end,   "shift_end")

    if end <= start:
        raise HTTPException(422, "shift_end must be after shift_start")

    result = check_shift_hours(start, end, body.break_hours,
                               body.establishment_type, body.hourly_rate_inr)

    if result["violations"]:
        log_labour_audit(
            supabase, "WORKING_HOURS_FLAGGED",
            org_id=org_id,
            metadata={"violations": [v["type"] for v in result["violations"]]},
            law_reference="OSH Code 2020 / Factories Act 1948",
        )

    return result


@router.post("/working-hours/check-rest")
async def check_rest(
    body: RestPeriodRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Check minimum 12-hour rest between consecutive shifts.
    Does NOT save to DB — call /working-hours/log-rest for persistence.
    """
    _get_org_id(supabase, user)
    prev_end = _parse_dt(body.previous_shift_end,  "previous_shift_end")
    curr_start = _parse_dt(body.current_shift_start, "current_shift_start")

    if curr_start <= prev_end:
        raise HTTPException(422, "current_shift_start must be after previous_shift_end")

    return check_rest_period(prev_end, curr_start)


@router.post("/working-hours/check-weekly")
async def check_weekly(
    body: WeeklyHoursRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Check total weekly hours against the 48-hour limit."""
    _get_org_id(supabase, user)
    return check_weekly_hours(body.weekly_actual_hours, body.establishment_type)


@router.post("/working-hours/log", status_code=201)
async def log_shift(
    body: ShiftLogRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Log a shift to working_hours_compliance and run all compliance checks:
      • Daily hours (8h standard, 9h hard max)
      • Weekly accumulation (48h limit)
      • Overtime detection and calculation
      • Night shift consent for female workers
    Returns DB record ID + full compliance result.
    """
    org_id = _get_org_id(supabase, user)
    start  = _parse_dt(body.shift_start, "shift_start")
    end    = _parse_dt(body.shift_end,   "shift_end")

    if end <= start:
        raise HTTPException(422, "shift_end must be after shift_start")

    result = log_shift_and_check(
        supabase,
        org_id       = org_id,
        shift_start  = start,
        shift_end    = end,
        break_hours  = body.break_hours,
        establishment_type    = body.establishment_type,
        candidate_id          = body.candidate_id,
        state_code            = body.state_code,
        hourly_rate_inr       = body.hourly_rate_inr,
        weekly_hours_so_far   = body.weekly_hours_so_far,
        is_female_worker      = body.is_female_worker,
        night_shift_consent   = body.night_shift_consent,
        transport_arranged    = body.transport_arranged,
    )

    if result["violations"]:
        log_labour_audit(
            supabase, "WORKING_HOURS_FLAGGED",
            org_id=org_id,
            entity_id=result.get("record_id"),
            metadata={"violations": [v["type"] for v in result["violations"]]},
            law_reference="OSH Code 2020 / Factories Act 1948",
        )

    return result


@router.post("/working-hours/log-rest", status_code=201)
async def log_rest(
    body: RestLogRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Check + persist rest period between consecutive shifts to shift_rest_log.
    Logs INSUFFICIENT_REST violation to audit log if applicable.
    """
    org_id     = _get_org_id(supabase, user)
    prev_end   = _parse_dt(body.previous_shift_end,   "previous_shift_end")
    curr_start = _parse_dt(body.current_shift_start,  "current_shift_start")

    if curr_start <= prev_end:
        raise HTTPException(422, "current_shift_start must be after previous_shift_end")

    result = log_rest_period(
        supabase, org_id,
        prev_end, curr_start,
        body.candidate_id,
        body.state_code,
    )

    if not result["compliant"]:
        log_labour_audit(
            supabase, "WORKING_HOURS_FLAGGED",
            org_id=org_id,
            entity_id=result.get("record_id"),
            metadata={"violation": "INSUFFICIENT_REST",
                      "rest_hours": result["rest_hours"]},
            law_reference="OSH Code 2020 s.25",
        )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# EPF / ESIC endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/epf-esic/calculate")
async def epf_calculate(
    body: EPFRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Calculate EPF contributions (employee 12% + employer 8.33% EPS + 3.67% EPF).
    Audit-logged as EPF_CALCULATED.
    """
    org_id = _get_org_id(supabase, user)
    result = calculate_epf(body.monthly_basic_da_inr)

    log_labour_audit(
        supabase, "EPF_CALCULATED",
        org_id=org_id,
        metadata={"basic_da_inr": body.monthly_basic_da_inr,
                  "total_monthly": result["total_monthly_inr"]},
        law_reference="EPF Act 1952 / Social Security Code 2020",
    )

    return result


@router.post("/epf-esic/esic-calculate")
async def esic_calculate(
    body: ESICRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Calculate ESIC contributions (employee 0.75% + employer 3.25%).
    Returns non-applicable if gross > ₹21,000.
    """
    org_id = _get_org_id(supabase, user)
    result = calculate_esic(body.monthly_gross_inr)

    log_labour_audit(
        supabase, "ESIC_CALCULATED",
        org_id=org_id,
        metadata={"gross_inr": body.monthly_gross_inr,
                  "applicable": result.get("applicable")},
        law_reference="ESIC Act 1948 / Social Security Code 2020",
    )

    return result


@router.post("/epf-esic/full")
async def full_social_security(
    body: FullSSRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Calculate complete EPF + ESIC in one call.
    Returns per-component breakdown + total employer cost + take-home reduction.
    Audit-logged as EPF_ESIC_FULL_CALC.
    """
    org_id = _get_org_id(supabase, user)
    result = calculate_full_social_security(body.monthly_basic_da_inr, body.monthly_gross_inr)

    log_labour_audit(
        supabase, "EPF_ESIC_FULL_CALC",
        org_id=org_id,
        metadata={
            "basic_da_inr":  body.monthly_basic_da_inr,
            "gross_inr":     body.monthly_gross_inr,
            "total_cost":    result["total_compliance_cost"],
        },
        law_reference="EPF Act 1952 / ESIC Act 1948 / Social Security Code 2020",
    )

    return result


@router.get("/epf-esic/thresholds")
async def epf_esic_thresholds(supabase: SupabaseClient, user: CurrentUser):
    """Reference card: all EPF/ESIC/Gratuity thresholds and rates."""
    _get_org_id(supabase, user)
    return {
        "epf": {
            "applicability":         f"Establishments with ≥{20} employees",
            "wage_ceiling_inr":      EPF_WAGE_CEILING_INR,
            "employee_pct":          EPF_EMPLOYEE_PCT,
            "employer_eps_pct":      EPF_EMPLOYER_EPS_PCT,
            "employer_epf_pct":      EPF_EMPLOYER_EPF_PCT,
            "law":                   "EPF Act 1952 / Social Security Code 2020",
        },
        "esic": {
            "applicability":         f"Establishments with ≥{10} employees",
            "wage_ceiling_inr":      ESIC_WAGE_CEILING_INR,
            "employee_pct":          ESIC_EMPLOYEE_PCT,
            "employer_pct":          ESIC_EMPLOYER_PCT,
            "law":                   "ESIC Act 1948 / Social Security Code 2020",
        },
        "gratuity": {
            "min_years_service":     GRATUITY_MIN_YEARS,
            "formula":               "(15/26) × last_salary × completed_years",
            "cap_inr":               2_000_000,
            "law":                   "Payment of Gratuity Act 1972",
        },
        "working_hours": {
            "daily_standard_hours":  DAILY_STANDARD_HOURS,
            "daily_max_hours":       MAX_DAILY_HOURS_SHOP,
            "weekly_max_hours":      MAX_WEEKLY_HOURS,
            "min_rest_hours":        MIN_REST_BETWEEN_SHIFTS_H,
            "overtime_rate":         f"{OT_RATE_MULTIPLIER}× ordinary rate",
            "law":                   "OSH Code 2020 / Factories Act 1948",
        },
        "minimum_wages": {
            "national_floor_daily":  NATIONAL_FLOOR_WAGE_INR,
            "national_floor_monthly": NATIONAL_FLOOR_WAGE_INR * 26,
            "law":                   "Code on Wages 2019",
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Gratuity
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/gratuity/calculate")
async def gratuity_calculate(
    body: GratuityRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Calculate gratuity under Payment of Gratuity Act 1972."""
    org_id = _get_org_id(supabase, user)
    result = calculate_gratuity(body.monthly_last_drawn_inr, body.years_of_service)

    log_labour_audit(
        supabase, "GRATUITY_CALCULATED",
        org_id=org_id,
        metadata={
            "years": body.years_of_service,
            "salary": body.monthly_last_drawn_inr,
            "gratuity_inr": result.get("gratuity_inr"),
        },
        law_reference="Payment of Gratuity Act 1972",
    )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Audit log
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/audit-log")
async def get_labour_audit_log(
    supabase: SupabaseClient,
    user: CurrentUser,
    action:  Optional[str] = Query(None),
    limit:   int           = Query(50, ge=1, le=200),
):
    """Return labour compliance audit log entries for this org."""
    org_id = _get_org_id(supabase, user)

    labour_actions = {
        "WAGE_COMPLIANCE_CHECK", "EPF_CALCULATED", "ESIC_CALCULATED",
        "EPF_ESIC_FULL_CALC", "GRATUITY_CALCULATED", "WORKING_HOURS_FLAGGED",
        "INSUFFICIENT_REST",
    }

    q = (
        supabase.table("india_compliance_audit_logs")
        .select("*")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
    )

    if action:
        q = q.eq("action", action)
    else:
        # Filter only labour-related actions when no specific action requested
        q = q.in_("action", list(labour_actions))

    result = q.execute()
    return result.data or []
