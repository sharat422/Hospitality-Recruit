"""
Indian Labour Compliance Engine — standalone service module.

Laws covered:
  Minimum Wages Act 1948 / Code on Wages 2019
  Factories Act 1948 / OSH Code 2020 (working hours)
  Employees' Provident Funds Act 1952 / Social Security Code 2020
  Employees' State Insurance Act 1948 / Social Security Code 2020
  Payment of Gratuity Act 1972

Design: pure functions where possible (no DB I/O). DB-backed functions
receive the supabase client as first argument and are clearly labelled.
All monetary values are in INR.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Working hours — OSH Code 2020 / Factories Act 1948
DAILY_STANDARD_HOURS      = 8      # overtime starts after this (Code on Wages 2019)
MAX_DAILY_HOURS_FACTORY   = 9      # hard ceiling for factories (30-min break included)
MAX_DAILY_HOURS_SHOP      = 9      # Shops & Establishments (most states)
MAX_WEEKLY_HOURS          = 48     # OSH Code 2020 s.25
MAX_SPREAD_OVER_HOURS     = 10.5   # Factories Act s.56
MIN_REST_BETWEEN_SHIFTS_H = 12     # minimum gap between consecutive shifts
MAX_OT_PER_DAY_H          = 2      # OSH Code 2020 s.25(4)
MAX_OT_PER_QUARTER_H      = 50     # OSH Code 2020
OT_RATE_MULTIPLIER        = 2.0    # Code on Wages 2019 s.13
NIGHT_SHIFT_START_HOUR    = 22     # 22:00 – 06:00 is night shift

# EPF — Employees' Provident Funds Act 1952 / Social Security Code 2020
EPF_MIN_EMPLOYEE_THRESHOLD = 20
EPF_WAGE_CEILING_INR       = 15_000   # EPS contribution capped at this
EPF_EMPLOYEE_PCT           = 12.0
EPF_EMPLOYER_EPF_PCT       = 3.67     # goes to PF account
EPF_EMPLOYER_EPS_PCT       = 8.33     # goes to Pension Scheme
EDLI_ADMIN_PCT             = 0.50     # Employees' Deposit Linked Insurance admin charge
EDLI_CONTRIBUTION_PCT      = 0.00     # nil for most employers post-2020

# ESIC — Employees' State Insurance Act 1948
ESIC_MIN_EMPLOYEE_THRESHOLD = 10
ESIC_WAGE_CEILING_INR       = 21_000  # applicable if gross ≤ ₹21,000
ESIC_EMPLOYEE_PCT           = 0.75
ESIC_EMPLOYER_PCT           = 3.25

# Gratuity — Payment of Gratuity Act 1972
GRATUITY_MIN_YEARS   = 5
GRATUITY_DAYS_FACTOR = 15
GRATUITY_WORK_DAYS   = 26          # denominator (working days/month)
GRATUITY_CAP_INR     = 2_000_000   # ₹20 lakh cap

# Code on Wages 2019 — national floor wage
NATIONAL_FLOOR_WAGE_INR = 176      # per day (notified 2024)

# Industry identifiers (used in minimum wages lookup)
VALID_INDUSTRIES = {
    "HOSPITALITY", "CONSTRUCTION", "AGRICULTURE",
    "RETAIL", "MANUFACTURING", "SECURITY", "ALL",
}

VALID_SKILL_CATEGORIES = {
    "UNSKILLED", "SEMI_SKILLED", "SKILLED", "HIGHLY_SKILLED",
}

VALID_ESTABLISHMENT_TYPES = {"FACTORY", "SHOP"}


# ─────────────────────────────────────────────────────────────────────────────
# Minimum wage — DB-backed
# ─────────────────────────────────────────────────────────────────────────────

def lookup_minimum_wage(
    supabase,
    state_code: str,
    skill_category: str,
    industry: str = "HOSPITALITY",
    zone: str = "A",
) -> Optional[dict]:
    """
    Return current minimum wage row for (state, skill, industry, zone).
    Falls back to industry='ALL' if no industry-specific row exists.
    Returns None when state/skill combination is unknown.
    """
    state_code     = state_code.upper().strip()
    skill_category = skill_category.upper().strip()
    industry       = industry.upper().strip()

    try:
        # Primary: exact industry match
        result = (
            supabase.table("india_minimum_wages")
            .select("*")
            .eq("state_code",     state_code)
            .eq("skill_category", skill_category)
            .eq("industry",       industry)
            .eq("zone",           zone)
            .eq("is_current",     True)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]

        # Fallback: industry = ALL
        if industry != "ALL":
            fallback = (
                supabase.table("india_minimum_wages")
                .select("*")
                .eq("state_code",     state_code)
                .eq("skill_category", skill_category)
                .eq("industry",       "ALL")
                .eq("zone",           zone)
                .eq("is_current",     True)
                .limit(1)
                .execute()
            )
            if fallback.data:
                return fallback.data[0]

    except Exception as exc:
        logger.warning("lookup_minimum_wage failed: %s", exc)

    return None


def check_salary_compliance(
    supabase,
    state_code: str,
    skill_category: str,
    offered_monthly_inr: float,
    industry: str = "HOSPITALITY",
    zone: str = "A",
) -> dict:
    """
    Check whether `offered_monthly_inr` meets the state minimum wage.
    Also checks against the national floor wage (Code on Wages 2019).
    Returns a structured compliance dict with shortfall amounts.
    """
    wage_row = lookup_minimum_wage(supabase, state_code, skill_category, industry, zone)

    # National floor check (independent of state)
    national_floor_monthly = NATIONAL_FLOOR_WAGE_INR * 26
    floor_compliant = offered_monthly_inr >= national_floor_monthly

    if not wage_row:
        return {
            "checked":                False,
            "reason":                 "No minimum wage data found for this state/skill/industry",
            "state_code":             state_code,
            "skill_category":         skill_category,
            "industry":               industry,
            "national_floor_monthly": national_floor_monthly,
            "floor_compliant":        floor_compliant,
        }

    min_monthly = float(wage_row["monthly_wage_inr"])
    min_daily   = float(wage_row["daily_wage_inr"])
    compliant   = offered_monthly_inr >= min_monthly
    shortfall   = round(max(0.0, min_monthly - offered_monthly_inr), 2)

    return {
        "checked":                True,
        "compliant":              compliant and floor_compliant,
        "state_compliant":        compliant,
        "floor_compliant":        floor_compliant,
        "offered_monthly_inr":    round(offered_monthly_inr, 2),
        "minimum_monthly_inr":    min_monthly,
        "minimum_daily_inr":      min_daily,
        "national_floor_monthly": national_floor_monthly,
        "shortfall_inr":          shortfall,
        "state_code":             state_code,
        "state_name":             wage_row.get("state_name", ""),
        "skill_category":         skill_category,
        "industry":               wage_row.get("industry", industry),
        "zone":                   zone,
        "effective_from":         wage_row.get("effective_from", ""),
        "source":                 wage_row.get("source", ""),
        "law":                    "Minimum Wages Act 1948 / Code on Wages 2019",
    }


def list_wages_for_state(supabase, state_code: str, industry: str = "HOSPITALITY") -> list[dict]:
    """Return all current minimum wage rows for a state (all skill categories)."""
    try:
        result = (
            supabase.table("india_minimum_wages")
            .select("state_code, state_name, zone, skill_category, industry, "
                    "daily_wage_inr, monthly_wage_inr, effective_from, source")
            .eq("state_code", state_code.upper())
            .eq("industry",   industry.upper())
            .eq("is_current", True)
            .order("skill_category")
            .execute()
        )
        return result.data or []
    except Exception as exc:
        logger.warning("list_wages_for_state failed: %s", exc)
        return []


def get_all_seeded_states(supabase) -> list[dict]:
    """Return distinct state codes + names that have minimum wage data."""
    try:
        result = (
            supabase.table("india_minimum_wages")
            .select("state_code, state_name")
            .eq("is_current", True)
            .execute()
        )
        seen  = set()
        states = []
        for row in (result.data or []):
            if row["state_code"] not in seen:
                seen.add(row["state_code"])
                states.append({"state_code": row["state_code"], "state_name": row["state_name"]})
        return sorted(states, key=lambda s: s["state_code"])
    except Exception as exc:
        logger.warning("get_all_seeded_states failed: %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Working hours — pure functions (no DB required for the checkers)
# ─────────────────────────────────────────────────────────────────────────────

def check_shift_hours(
    shift_start: datetime,
    shift_end: datetime,
    break_hours: float = 0.5,
    establishment_type: str = "SHOP",
    hourly_rate_inr: float = 0.0,
) -> dict:
    """
    Check a single shift against OSH Code 2020 / Factories Act 1948 limits.

    Rules checked:
      • Overtime starts after 8 h (Code on Wages 2019 s.13)
      • Hard daily ceiling: 9 h (most establishments)
      • Spread-over must not exceed 10.5 h (Factories Act s.56)
      • Overtime capped at 2 h/day additional beyond 8 h

    Returns dict with violations list and calculated amounts.
    """
    establishment_type = establishment_type.upper()
    actual_hours  = (shift_end - shift_start).total_seconds() / 3600 - break_hours
    spread_over   = (shift_end - shift_start).total_seconds() / 3600
    max_daily     = MAX_DAILY_HOURS_FACTORY if establishment_type == "FACTORY" else MAX_DAILY_HOURS_SHOP
    overtime_hours = max(0.0, actual_hours - DAILY_STANDARD_HOURS)
    overtime_inr   = 0.0
    if hourly_rate_inr > 0 and overtime_hours > 0:
        overtime_inr = round(overtime_hours * hourly_rate_inr * OT_RATE_MULTIPLIER, 2)

    is_night = (
        shift_start.hour >= NIGHT_SHIFT_START_HOUR
        or shift_end.hour < 6
        or (shift_start.hour < 6 and shift_end.hour < 6)
    )

    violations: list[dict] = []

    if actual_hours > max_daily:
        violations.append({
            "type":     "EXCESS_DAILY_HOURS",
            "severity": "HIGH",
            "message":  f"Shift of {actual_hours:.1f}h exceeds daily maximum of {max_daily}h",
            "law":      "OSH Code 2020 s.25 / Factories Act 1948 s.51",
        })

    if spread_over > MAX_SPREAD_OVER_HOURS:
        violations.append({
            "type":     "EXCESS_SPREAD_OVER",
            "severity": "MEDIUM",
            "message":  f"Spread-over of {spread_over:.1f}h exceeds {MAX_SPREAD_OVER_HOURS}h limit",
            "law":      "Factories Act 1948 s.56",
        })

    if overtime_hours > MAX_OT_PER_DAY_H:
        violations.append({
            "type":     "EXCESS_DAILY_OVERTIME",
            "severity": "MEDIUM",
            "message":  f"Daily overtime of {overtime_hours:.1f}h exceeds {MAX_OT_PER_DAY_H}h cap",
            "law":      "OSH Code 2020 s.25(4)",
        })

    return {
        "compliant":         len(violations) == 0,
        "actual_hours":      round(actual_hours, 2),
        "spread_over_hours": round(spread_over, 2),
        "overtime_hours":    round(overtime_hours, 2),
        "overtime_inr":      overtime_inr,
        "ot_rate_multiplier": OT_RATE_MULTIPLIER,
        "is_night_shift":    is_night,
        "is_overtime":       overtime_hours > 0,
        "violations":        violations,
        "law":               "OSH Code 2020 / Factories Act 1948",
    }


def check_rest_period(
    previous_shift_end: datetime,
    current_shift_start: datetime,
) -> dict:
    """
    Check that at least 12 hours rest was given between consecutive shifts.
    OSH Code 2020 s.25 requires minimum 12 hours between shifts.
    """
    rest_hours = (current_shift_start - previous_shift_end).total_seconds() / 3600
    is_violation = rest_hours < MIN_REST_BETWEEN_SHIFTS_H

    result = {
        "rest_hours":          round(rest_hours, 2),
        "required_hours":      MIN_REST_BETWEEN_SHIFTS_H,
        "compliant":           not is_violation,
        "law":                 "OSH Code 2020 s.25 / State Shops & Establishments Acts",
    }

    if is_violation:
        deficit = MIN_REST_BETWEEN_SHIFTS_H - rest_hours
        result["violation"] = {
            "type":     "INSUFFICIENT_REST",
            "severity": "HIGH",
            "message":  (
                f"Only {rest_hours:.1f}h rest between shifts — "
                f"minimum required is {MIN_REST_BETWEEN_SHIFTS_H}h "
                f"(deficit: {deficit:.1f}h)"
            ),
            "law": "OSH Code 2020 s.25 / State Shops & Establishments Acts",
        }

    return result


def check_weekly_hours(
    weekly_actual_hours: float,
    establishment_type: str = "SHOP",
) -> dict:
    """
    Check total hours worked in a week against the 48-hour limit.
    Overtime is anything above 48h/week.
    """
    overtime_hours = max(0.0, weekly_actual_hours - MAX_WEEKLY_HOURS)
    is_violation   = weekly_actual_hours > MAX_WEEKLY_HOURS

    result = {
        "weekly_actual_hours": round(weekly_actual_hours, 2),
        "weekly_limit":        MAX_WEEKLY_HOURS,
        "overtime_hours":      round(overtime_hours, 2),
        "is_overtime":         weekly_actual_hours > 40,   # flag even before 48h
        "compliant":           not is_violation,
        "law":                 "OSH Code 2020 s.25 / Factories Act 1948 s.51",
    }

    if is_violation:
        result["violation"] = {
            "type":     "EXCESS_WEEKLY_HOURS",
            "severity": "HIGH",
            "message":  (
                f"Weekly hours {weekly_actual_hours:.1f}h exceed "
                f"48h limit (excess: {overtime_hours:.1f}h)"
            ),
            "law": "OSH Code 2020 s.25",
        }

    return result


def check_night_shift_compliance(
    is_female_worker: bool,
    night_shift_consent: bool = False,
    transport_arranged: bool = False,
) -> dict:
    """
    Night shift rules for female workers — OSH Code 2020 s.43.
    Requires explicit written consent + employer-arranged transport.
    """
    violations: list[dict] = []

    if is_female_worker:
        if not night_shift_consent:
            violations.append({
                "type":     "NIGHT_SHIFT_NO_CONSENT",
                "severity": "HIGH",
                "message":  "Night shift requires written consent from female worker",
                "law":      "OSH Code 2020 s.43",
            })
        if not transport_arranged:
            violations.append({
                "type":     "NIGHT_SHIFT_NO_TRANSPORT",
                "severity": "MEDIUM",
                "message":  "Employer must arrange transport for female workers on night shift",
                "law":      "OSH Code 2020 s.43 / State Factory Rules",
            })

    return {
        "compliant":        len(violations) == 0,
        "is_female_worker": is_female_worker,
        "violations":       violations,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EPF / ESIC calculator — pure functions
# ─────────────────────────────────────────────────────────────────────────────

def calculate_epf(monthly_basic_da_inr: float) -> dict:
    """
    Calculate EPF contributions.

    EPF = 12% of Basic+DA (both employee and employer).
    Employer split: 8.33% → EPS (Pension Scheme), 3.67% → EPF.
    EPS capped at ₹15,000 basic+DA.
    """
    wage_for_eps   = min(monthly_basic_da_inr, EPF_WAGE_CEILING_INR)
    employee_epf   = round(monthly_basic_da_inr * EPF_EMPLOYEE_PCT / 100, 2)
    employer_eps   = round(wage_for_eps * EPF_EMPLOYER_EPS_PCT / 100, 2)
    employer_epf   = round(monthly_basic_da_inr * EPF_EMPLOYER_EPF_PCT / 100, 2)
    total_employer = round(employer_eps + employer_epf, 2)
    total_monthly  = round(employee_epf + total_employer, 2)

    return {
        "applicable":               True,
        "monthly_basic_da_inr":     round(monthly_basic_da_inr, 2),
        "wage_ceiling_applied":     monthly_basic_da_inr > EPF_WAGE_CEILING_INR,
        # Employee
        "employee_epf_inr":         employee_epf,
        "employee_pct":             EPF_EMPLOYEE_PCT,
        # Employer
        "employer_eps_inr":         employer_eps,
        "employer_epf_inr":         employer_epf,
        "employer_total_inr":       total_employer,
        "employer_eps_pct":         EPF_EMPLOYER_EPS_PCT,
        "employer_epf_pct":         EPF_EMPLOYER_EPF_PCT,
        # Combined
        "total_monthly_inr":        total_monthly,
        "total_annual_inr":         round(total_monthly * 12, 2),
        "eps_wage_ceiling_inr":     EPF_WAGE_CEILING_INR,
        "law":                      "EPF Act 1952 / Social Security Code 2020",
    }


def calculate_esic(monthly_gross_inr: float) -> dict:
    """
    Calculate ESIC contributions.
    Applicable only when monthly gross ≤ ₹21,000.
    Employee 0.75%, employer 3.25%.
    """
    eligible = monthly_gross_inr <= ESIC_WAGE_CEILING_INR

    if not eligible:
        return {
            "applicable":         False,
            "reason":             f"Gross salary ₹{monthly_gross_inr:,.0f} exceeds ESIC ceiling ₹{ESIC_WAGE_CEILING_INR:,}",
            "wage_ceiling_inr":   ESIC_WAGE_CEILING_INR,
            "monthly_gross_inr":  round(monthly_gross_inr, 2),
            "law":                "ESIC Act 1948 / Social Security Code 2020",
        }

    employee_esic = round(monthly_gross_inr * ESIC_EMPLOYEE_PCT / 100, 2)
    employer_esic = round(monthly_gross_inr * ESIC_EMPLOYER_PCT / 100, 2)
    total         = round(employee_esic + employer_esic, 2)

    return {
        "applicable":           True,
        "monthly_gross_inr":    round(monthly_gross_inr, 2),
        "employee_esic_inr":    employee_esic,
        "employer_esic_inr":    employer_esic,
        "total_monthly_inr":    total,
        "total_annual_inr":     round(total * 12, 2),
        "employee_pct":         ESIC_EMPLOYEE_PCT,
        "employer_pct":         ESIC_EMPLOYER_PCT,
        "wage_ceiling_inr":     ESIC_WAGE_CEILING_INR,
        "law":                  "ESIC Act 1948 / Social Security Code 2020",
    }


def calculate_full_social_security(
    monthly_basic_da_inr: float,
    monthly_gross_inr: float,
) -> dict:
    """
    Calculate complete EPF + ESIC obligations in one call.
    monthly_basic_da_inr — basic salary + dearness allowance (EPF basis)
    monthly_gross_inr    — all components (ESIC basis)
    """
    epf  = calculate_epf(monthly_basic_da_inr)
    esic = calculate_esic(monthly_gross_inr)

    total_employee  = epf["employee_epf_inr"] + (esic.get("employee_esic_inr") or 0)
    total_employer  = epf["employer_total_inr"] + (esic.get("employer_esic_inr") or 0)
    total_cost      = round(total_employee + total_employer, 2)

    return {
        "epf":                    epf,
        "esic":                   esic,
        "total_employee_deduction": round(total_employee, 2),
        "total_employer_cost":    round(total_employer, 2),
        "total_compliance_cost":  total_cost,
        "take_home_reduction":    round(total_employee, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Gratuity — pure function
# ─────────────────────────────────────────────────────────────────────────────

def calculate_gratuity(monthly_last_drawn_inr: float, years_of_service: float) -> dict:
    """
    Payment of Gratuity Act 1972.
    Formula: (15/26) × last drawn salary × completed years of service
    Cap: ₹20,00,000.
    Eligible only after 5 years continuous service.
    """
    eligible = years_of_service >= GRATUITY_MIN_YEARS

    if not eligible:
        return {
            "eligible":          False,
            "reason":            f"Minimum {GRATUITY_MIN_YEARS} years required; got {years_of_service:.1f}",
            "years_of_service":  round(years_of_service, 2),
            "law":               "Payment of Gratuity Act 1972 s.4",
        }

    completed_years = int(years_of_service)  # only completed years count
    raw_inr         = (GRATUITY_DAYS_FACTOR / GRATUITY_WORK_DAYS) * monthly_last_drawn_inr * completed_years
    capped          = raw_inr > GRATUITY_CAP_INR
    gratuity_inr    = round(min(raw_inr, GRATUITY_CAP_INR), 2)

    return {
        "eligible":               True,
        "years_of_service":       round(years_of_service, 2),
        "completed_years":        completed_years,
        "monthly_last_drawn_inr": round(monthly_last_drawn_inr, 2),
        "formula":                f"(15/26) × ₹{monthly_last_drawn_inr:,.2f} × {completed_years} years",
        "raw_inr":                round(raw_inr, 2),
        "gratuity_inr":           gratuity_inr,
        "cap_applied":            capped,
        "cap_inr":                GRATUITY_CAP_INR,
        "law":                    "Payment of Gratuity Act 1972 s.4",
    }


# ─────────────────────────────────────────────────────────────────────────────
# DB-backed: log shift and detect violations
# ─────────────────────────────────────────────────────────────────────────────

def log_shift_and_check(
    supabase,
    org_id: str,
    shift_start: datetime,
    shift_end: datetime,
    break_hours: float = 0.5,
    establishment_type: str = "SHOP",
    candidate_id: Optional[str] = None,
    state_code: Optional[str] = None,
    hourly_rate_inr: float = 0.0,
    weekly_hours_so_far: float = 0.0,
    is_female_worker: bool = False,
    night_shift_consent: bool = False,
    transport_arranged: bool = False,
) -> dict:
    """
    Run all working-hours checks for one shift and persist to DB.
    Returns combined compliance result with DB record ID.
    """
    shift_check   = check_shift_hours(shift_start, shift_end, break_hours,
                                      establishment_type, hourly_rate_inr)
    weekly_total  = weekly_hours_so_far + shift_check["actual_hours"]
    weekly_check  = check_weekly_hours(weekly_total, establishment_type)
    night_check   = check_night_shift_compliance(is_female_worker, night_shift_consent, transport_arranged)

    all_violations = (
        shift_check["violations"]
        + ([weekly_check["violation"]] if weekly_check.get("violation") else [])
        + night_check["violations"]
    )

    violation_type = all_violations[0]["type"] if all_violations else None
    severity       = all_violations[0]["severity"] if all_violations else None

    row = {
        "org_id":              org_id,
        "candidate_id":        candidate_id,
        "shift_date":          shift_start.date().isoformat(),
        "shift_start":         shift_start.isoformat(),
        "shift_end":           shift_end.isoformat(),
        "actual_hours":        shift_check["actual_hours"],
        "break_hours":         break_hours,
        "spread_over_hours":   shift_check["spread_over_hours"],
        "overtime_hours":      shift_check["overtime_hours"],
        "overtime_inr":        shift_check["overtime_inr"],
        "week_number":         shift_start.isocalendar()[1],
        "weekly_total_hours":  round(weekly_total, 2),
        "is_night_shift":      shift_check["is_night_shift"],
        "night_shift_consent": night_shift_consent,
        "transport_arranged":  transport_arranged,
        "state_code":          state_code,
        "applicable_act":      "OSH Code 2020 / Factories Act 1948",
        "violation_type":      violation_type,
        "violation_severity":  severity,
        "resolved":            False,
        "created_at":          datetime.utcnow().isoformat(),
    }

    try:
        res = supabase.table("working_hours_compliance").insert(row).execute()
        record_id = res.data[0]["id"] if res.data else None
    except Exception as exc:
        logger.error("log_shift_and_check DB insert failed: %s", exc)
        record_id = None

    return {
        "record_id":    record_id,
        "shift":        shift_check,
        "weekly":       weekly_check,
        "night_shift":  night_check,
        "violations":   all_violations,
        "compliant":    len(all_violations) == 0,
        "weekly_total_hours": round(weekly_total, 2),
    }


def log_rest_period(
    supabase,
    org_id: str,
    previous_shift_end: datetime,
    current_shift_start: datetime,
    candidate_id: Optional[str] = None,
    state_code: Optional[str] = None,
) -> dict:
    """Check and persist rest-period record to shift_rest_log."""
    check = check_rest_period(previous_shift_end, current_shift_start)

    row = {
        "org_id":               org_id,
        "candidate_id":         candidate_id,
        "previous_shift_end":   previous_shift_end.isoformat(),
        "current_shift_start":  current_shift_start.isoformat(),
        "state_code":           state_code,
        "resolved":             False,
        "created_at":           datetime.utcnow().isoformat(),
    }

    try:
        res = supabase.table("shift_rest_log").insert(row).execute()
        check["record_id"] = res.data[0]["id"] if res.data else None
    except Exception as exc:
        logger.error("log_rest_period DB insert failed: %s", exc)
        check["record_id"] = None

    return check


# ─────────────────────────────────────────────────────────────────────────────
# Audit logger — best-effort, never raises
# ─────────────────────────────────────────────────────────────────────────────

def log_labour_audit(
    supabase,
    action: str,
    org_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    law_reference: Optional[str] = None,
) -> None:
    """Write a compliance check event to the audit log. Best-effort — never raises."""
    try:
        supabase.table("india_compliance_audit_logs").insert({
            "org_id":        org_id,
            "actor_type":    "SYSTEM",
            "action":        action,
            "entity_type":   "labour_compliance",
            "entity_id":     entity_id,
            "law_reference": law_reference,
            "metadata":      metadata or {},
            "created_at":    datetime.utcnow().isoformat(),
        }).execute()
    except Exception as exc:
        logger.debug("log_labour_audit suppressed: %s", exc)
