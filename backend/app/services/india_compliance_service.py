"""
India Compliance Service — Feature 06 India

Replaces Western compliance helpers (GDPR, EEO, Fair Workweek, RTW)
with India-specific law:
  • DPDP Act 2023 (Digital Personal Data Protection)
  • EPF / ESIC (Social Security Code 2020)
  • Minimum Wages Act + Code on Wages 2019
  • Factories Act 1948 / OSH Code 2020 (working hours)
  • Professional Tax (state-specific)
  • FSSAI (Food Safety and Standards Authority of India)
  • India Diversity (SC/ST/OBC/PWD voluntary collection)
  • India Identity Verification (Aadhaar/PAN/DigiLocker)
"""

from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import Optional
import logging
import re

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# DPDP consent purpose codes (Section 6, DPDP Act 2023)
DPDP_PURPOSE_CODES = {
    "RECRUITMENT_DATA":  "Processing personal data for recruitment and hiring",
    "BACKGROUND_CHECK":  "Verification of identity, credentials, and past employment",
    "SENSITIVE_DATA":    "Medical records, biometric data, or financial information",
    "MARKETING":         "Job alerts, newsletters, and promotional content",
    "THIRD_PARTY_SHARE": "Sharing with hotels, employers, or staffing agencies",
    "AI_PROFILING":      "AI-based candidate assessment, screening, or ranking",
    "CROSS_BORDER":      "Transfer of personal data outside India",
}

# DPDP response deadline (30 days per Section 13)
DPDP_RESPONSE_DAYS = 30

# EPF thresholds (Social Security Code 2020)
EPF_EMPLOYEE_THRESHOLD   = 20       # Min employees for EPF applicability
EPF_WAGE_CEILING_INR     = 15_000   # EPF wage ceiling (monthly)
EPF_EMPLOYEE_CONTRIB_PCT = 12.0
EPF_EMPLOYER_CONTRIB_PCT = 12.0     # 8.33% EPS + 3.67% EPF
EPF_EPS_CONTRIB_PCT      = 8.33

# ESIC thresholds
ESIC_EMPLOYEE_THRESHOLD      = 10
ESIC_WAGE_CEILING_INR        = 21_000
ESIC_EMPLOYEE_CONTRIB_PCT    = 0.75
ESIC_EMPLOYER_CONTRIB_PCT    = 3.25

# Working hours (Factories Act 1948 / OSH Code 2020)
MAX_DAILY_HOURS_FACTORY      = 9
MAX_DAILY_HOURS_SHOP         = 9      # Most Shops Acts
MAX_WEEKLY_HOURS             = 48
MAX_SPREAD_OVER_HOURS        = 10.5   # Start-to-end including breaks
MAX_OVERTIME_HOURS_PER_DAY   = 2
OVERTIME_RATE_MULTIPLIER     = 2.0    # Code on Wages Section 14

# Gratuity (Social Security Code 2020)
GRATUITY_ELIGIBLE_YEARS      = 5      # Min continuous service
GRATUITY_DAYS_PER_YEAR       = 15     # 15 days salary per completed year
GRATUITY_CAP_INR             = 2_000_000   # ₹20 lakh cap

# FSSAI alert thresholds
FSSAI_ALERT_30_DAYS = 30
FSSAI_ALERT_7_DAYS  = 7

# States with Professional Tax (all others are exempt)
STATES_WITH_PROFESSIONAL_TAX = {
    "MH", "KA", "WB", "TN", "AP", "TS", "KL", "MP",
    "AS", "OD", "BR", "JH", "ML", "SK"
}

# Indian states — ISO 3166-2:IN codes
INDIA_STATES = {
    "AN": "Andaman and Nicobar Islands",
    "AP": "Andhra Pradesh",
    "AR": "Arunachal Pradesh",
    "AS": "Assam",
    "BR": "Bihar",
    "CH": "Chandigarh",
    "CG": "Chhattisgarh",
    "DD": "Daman and Diu",
    "DL": "Delhi",
    "DN": "Dadra and Nagar Haveli",
    "GA": "Goa",
    "GJ": "Gujarat",
    "HP": "Himachal Pradesh",
    "HR": "Haryana",
    "JH": "Jharkhand",
    "JK": "Jammu and Kashmir",
    "KA": "Karnataka",
    "KL": "Kerala",
    "LA": "Ladakh",
    "LD": "Lakshadweep",
    "MH": "Maharashtra",
    "ML": "Meghalaya",
    "MN": "Manipur",
    "MP": "Madhya Pradesh",
    "MZ": "Mizoram",
    "NL": "Nagaland",
    "OD": "Odisha",
    "PB": "Punjab",
    "PY": "Puducherry",
    "RJ": "Rajasthan",
    "SK": "Sikkim",
    "TN": "Tamil Nadu",
    "TR": "Tripura",
    "TS": "Telangana",
    "UK": "Uttarakhand",
    "UP": "Uttar Pradesh",
    "WB": "West Bengal",
}


# ─────────────────────────────────────────────────────────────────────────────
# Identity Verification
# ─────────────────────────────────────────────────────────────────────────────

def validate_aadhaar_last4(last4: str) -> bool:
    """Validate that 4 digits were provided (never store full Aadhaar)."""
    return bool(re.fullmatch(r"\d{4}", last4 or ""))


def validate_pan(pan: str) -> bool:
    """
    Validate PAN format: 5 letters, 4 digits, 1 letter.
    E.g. ABCDE1234F
    """
    return bool(re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", (pan or "").strip().upper()))


def mask_pan(pan: str) -> str:
    """ABCDE1234F → ABCDE****F  (first 5 + four stars + last char)."""
    pan = pan.upper().strip()
    if not validate_pan(pan):
        raise ValueError(f"Invalid PAN format: {pan!r}")
    return f"{pan[:5]}****{pan[-1]}"


def mask_aadhaar(aadhaar_digits: str) -> str:
    """123456789012 → XXXX XXXX 9012 (only last 4 kept per UIDAI mandate)."""
    digits = re.sub(r"[\s\-]", "", aadhaar_digits or "")
    if len(digits) != 12 or not digits.isdigit():
        raise ValueError("Aadhaar must be exactly 12 digits")
    return f"XXXX XXXX {digits[-4:]}"


def get_expiring_identity_docs(supabase, days_ahead: int = 30) -> list[dict]:
    """Return identity documents expiring within `days_ahead` days."""
    cutoff = (datetime.utcnow() + timedelta(days=days_ahead)).date().isoformat()
    today  = datetime.utcnow().date().isoformat()
    try:
        result = (
            supabase.table("india_identity_verifications")
            .select("id, org_id, candidate_id, doc_type, doc_expiry_date, status")
            .eq("status", "VERIFIED")
            .gte("doc_expiry_date", today)
            .lte("doc_expiry_date", cutoff)
            .order("doc_expiry_date")
            .execute()
        )
        return result.data or []
    except Exception as exc:
        logger.warning("get_expiring_identity_docs failed: %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# EPF / ESIC
# ─────────────────────────────────────────────────────────────────────────────

def validate_uan(uan: str) -> bool:
    """UAN is a 12-digit numeric string."""
    return bool(re.fullmatch(r"\d{12}", (uan or "").strip()))


def is_esic_eligible(monthly_wage_inr: float) -> bool:
    """ESIC applies when monthly gross wages ≤ ₹21,000."""
    return monthly_wage_inr <= ESIC_WAGE_CEILING_INR


def calculate_epf_contribution(monthly_basic_da_inr: float) -> dict:
    """
    Calculate EPF/EPS contributions based on monthly Basic+DA.
    Contribution is capped at ₹15,000 for EPS purposes.
    """
    wage_for_eps = min(monthly_basic_da_inr, EPF_WAGE_CEILING_INR)
    employee_epf = round(monthly_basic_da_inr * EPF_EMPLOYEE_CONTRIB_PCT / 100, 2)
    employer_eps = round(wage_for_eps * EPF_EPS_CONTRIB_PCT / 100, 2)
    employer_epf = round(monthly_basic_da_inr * EPF_EMPLOYER_CONTRIB_PCT / 100, 2) - employer_eps
    return {
        "employee_epf_inr":    employee_epf,
        "employer_eps_inr":    employer_eps,
        "employer_epf_inr":    employer_epf,
        "total_epf_inr":       round(employee_epf + employer_epf + employer_eps, 2),
        "wage_ceiling_applied": monthly_basic_da_inr > EPF_WAGE_CEILING_INR,
    }


def calculate_esic_contribution(monthly_gross_inr: float) -> dict:
    """Calculate ESIC contributions if eligible."""
    if not is_esic_eligible(monthly_gross_inr):
        return {"eligible": False, "employee_esic_inr": 0, "employer_esic_inr": 0}
    employee = round(monthly_gross_inr * ESIC_EMPLOYEE_CONTRIB_PCT / 100, 2)
    employer = round(monthly_gross_inr * ESIC_EMPLOYER_CONTRIB_PCT / 100, 2)
    return {
        "eligible":          True,
        "employee_esic_inr": employee,
        "employer_esic_inr": employer,
        "total_esic_inr":    round(employee + employer, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Minimum Wages
# ─────────────────────────────────────────────────────────────────────────────

def get_minimum_wage(supabase, state_code: str, skill_category: str, zone: str = "A") -> Optional[dict]:
    """Fetch the current minimum wage for a state + skill + zone."""
    try:
        result = (
            supabase.table("india_minimum_wages")
            .select("*")
            .eq("state_code", state_code.upper())
            .eq("skill_category", skill_category.upper())
            .eq("zone", zone.upper())
            .eq("is_current", True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as exc:
        logger.warning("get_minimum_wage failed: %s", exc)
        return None


def check_wage_compliance(
    supabase,
    state_code: str,
    skill_category: str,
    offered_monthly_inr: float,
    zone: str = "A",
) -> dict:
    """Check whether an offered wage meets the state minimum wage."""
    mw = get_minimum_wage(supabase, state_code, skill_category, zone)
    if not mw:
        return {
            "checked": False,
            "reason": f"No minimum wage data for {state_code} / {skill_category}",
        }
    minimum = float(mw["monthly_wage_inr"])
    compliant = offered_monthly_inr >= minimum
    return {
        "checked":              True,
        "compliant":            compliant,
        "offered_monthly_inr":  offered_monthly_inr,
        "minimum_monthly_inr":  minimum,
        "shortfall_inr":        max(0, minimum - offered_monthly_inr),
        "state":                mw["state_name"],
        "skill_category":       skill_category,
        "effective_from":       mw["effective_from"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Working Hours Compliance
# ─────────────────────────────────────────────────────────────────────────────

def check_working_hours_violation(
    shift_start: datetime,
    shift_end: datetime,
    break_hours: float = 0.5,
    establishment_type: str = "SHOP",
    is_female_worker: bool = False,
) -> dict:
    """
    Detect working-hours violations per Factories Act 1948 / OSH Code 2020.

    Returns a dict with violation details (or empty if compliant).
    """
    actual_hours    = (shift_end - shift_start).total_seconds() / 3600 - break_hours
    spread_over     = (shift_end - shift_start).total_seconds() / 3600
    is_night_shift  = shift_start.hour >= 22 or shift_end.hour <= 6

    violations = []

    max_hours = MAX_DAILY_HOURS_FACTORY if establishment_type == "FACTORY" else MAX_DAILY_HOURS_SHOP
    if actual_hours > max_hours:
        excess = round(actual_hours - max_hours, 2)
        violations.append({
            "type":     "EXCESS_DAILY_HOURS",
            "severity": "CRITICAL" if excess > 2 else "WARNING",
            "detail":   f"Worked {actual_hours:.1f}h; max {max_hours}h. Excess: {excess:.1f}h",
        })

    if spread_over > MAX_SPREAD_OVER_HOURS:
        violations.append({
            "type":     "EXCESS_SPREAD_OVER",
            "severity": "WARNING",
            "detail":   f"Spread-over {spread_over:.1f}h; max {MAX_SPREAD_OVER_HOURS}h",
        })

    if is_night_shift and is_female_worker:
        violations.append({
            "type":     "NIGHT_SHIFT_NO_CONSENT",
            "severity": "CRITICAL",
            "detail":   "Female worker on night shift — written consent and transport required",
        })

    return {
        "compliant":       len(violations) == 0,
        "actual_hours":    round(actual_hours, 2),
        "spread_over":     round(spread_over, 2),
        "is_night_shift":  is_night_shift,
        "violations":      violations,
    }


def calculate_overtime(
    actual_hours: float,
    establishment_type: str = "SHOP",
    hourly_rate_inr: float = 0,
) -> dict:
    """Calculate overtime hours and INR amount."""
    max_hours = MAX_DAILY_HOURS_FACTORY if establishment_type == "FACTORY" else MAX_DAILY_HOURS_SHOP
    ot_hours  = max(0, actual_hours - max_hours)
    ot_capped = min(ot_hours, MAX_OVERTIME_HOURS_PER_DAY)
    ot_inr    = round(ot_capped * hourly_rate_inr * OVERTIME_RATE_MULTIPLIER, 2)
    return {
        "overtime_hours":    round(ot_capped, 2),
        "excess_ot_hours":   round(max(0, ot_hours - MAX_OVERTIME_HOURS_PER_DAY), 2),
        "overtime_inr":      ot_inr,
        "ot_rate_multiplier": OVERTIME_RATE_MULTIPLIER,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Professional Tax
# ─────────────────────────────────────────────────────────────────────────────

def get_professional_tax(
    supabase,
    state_code: str,
    monthly_salary_inr: float,
    month: Optional[int] = None,
) -> dict:
    """
    Lookup the Professional Tax amount for a state + salary slab.
    `month` (1-12) matters for Maharashtra (extra ₹100 in February).
    """
    if state_code.upper() not in STATES_WITH_PROFESSIONAL_TAX:
        return {
            "applicable": False,
            "state_code": state_code,
            "reason":     f"{state_code} does not levy Professional Tax",
            "pt_inr":     0,
        }

    try:
        # Find matching slab (salary >= slab_min AND (slab_max is NULL OR salary <= slab_max))
        result = (
            supabase.table("professional_tax_slabs")
            .select("*")
            .eq("state_code", state_code.upper())
            .eq("is_current", True)
            .lte("slab_min_salary_inr", monthly_salary_inr)
            .order("slab_min_salary_inr", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return {"applicable": True, "pt_inr": 0, "state_code": state_code}

        slab = result.data[0]
        slab_max = slab.get("slab_max_salary_inr")
        if slab_max and monthly_salary_inr > float(slab_max):
            return {"applicable": True, "pt_inr": 0, "state_code": state_code}

        # Maharashtra: February has ₹300 instead of ₹200 for top slab
        is_february = (month == 2) if month else False
        pt_amount = float(slab.get("pt_february_inr") or slab["pt_monthly_inr"]) if is_february \
                    else float(slab["pt_monthly_inr"])

        return {
            "applicable":         True,
            "state_code":         state_code,
            "state_name":         slab["state_name"],
            "monthly_salary_inr": monthly_salary_inr,
            "pt_inr":             pt_amount,
            "slab_min_inr":       float(slab["slab_min_salary_inr"]),
            "slab_max_inr":       slab_max,
            "is_february":        is_february,
        }
    except Exception as exc:
        logger.warning("get_professional_tax failed: %s", exc)
        return {"applicable": True, "pt_inr": 0, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# DPDP Consent
# ─────────────────────────────────────────────────────────────────────────────

def record_dpdp_consent(
    supabase,
    org_id: str,
    candidate_id: str,
    purpose_code: str,
    consented: bool,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    consent_mechanism: str = "DIGITAL_FORM",
    data_fiduciary_name: Optional[str] = None,
    consent_text_version: str = "v1.0",
) -> dict:
    """Record a DPDP consent event (grant or withdrawal)."""
    if purpose_code not in DPDP_PURPOSE_CODES:
        raise ValueError(f"Invalid DPDP purpose_code: {purpose_code}")

    now = datetime.utcnow().isoformat()
    payload = {
        "org_id":               org_id,
        "candidate_id":         candidate_id,
        "purpose_code":         purpose_code,
        "purpose_description":  DPDP_PURPOSE_CODES[purpose_code],
        "consented":            consented,
        "consent_text_version": consent_text_version,
        "consent_mechanism":    consent_mechanism,
        "consented_at":         now,
        "ip_address":           ip_address,
        "user_agent":           user_agent,
        "data_fiduciary_name":  data_fiduciary_name,
    }
    if not consented:
        payload["withdrawal_requested_at"] = now

    result = supabase.table("dpdp_consent_records").insert(payload).execute()
    if not result.data:
        raise RuntimeError("Failed to record DPDP consent")

    log_india_compliance_audit(
        supabase,
        action="DPDP_CONSENT_GIVEN" if consented else "DPDP_CONSENT_WITHDRAWN",
        entity_type="candidate",
        entity_id=candidate_id,
        org_id=org_id,
        metadata={"purpose_code": purpose_code, "consented": consented},
        ip_address=ip_address,
        law_reference="DPDP Act 2023 Section 6",
    )
    return result.data[0]


def create_dpdp_erasure_request(
    supabase,
    org_id: str,
    candidate_id: str,
    request_type: str = "ERASURE",
    reason: Optional[str] = None,
    specific_fields: Optional[list] = None,
) -> dict:
    """Create a DPDP erasure or correction request with 30-day SLA."""
    now = datetime.utcnow().isoformat()
    result = supabase.table("dpdp_erasure_requests").insert({
        "org_id":               org_id,
        "candidate_id":         candidate_id,
        "request_type":         request_type,
        "reason":               reason,
        "specific_data_fields": specific_fields or [],
        "status":               "PENDING",
        "requested_at":         now,
        "acknowledged_at":      now,
    }).execute()

    if not result.data:
        raise RuntimeError("Failed to create DPDP erasure request")

    log_india_compliance_audit(
        supabase,
        action="DPDP_ERASURE_REQUESTED",
        entity_type="candidate",
        entity_id=candidate_id,
        org_id=org_id,
        metadata={"request_type": request_type},
        law_reference="DPDP Act 2023 Section 13",
    )
    return result.data[0]


def anonymize_candidate_dpdp(supabase, candidate_id: str, org_id: str) -> dict:
    """
    Anonymize a candidate's personal data per DPDP erasure obligation.
    Retains non-personal data for analytics/audit.
    """
    now = datetime.utcnow().isoformat()
    anonymized_update = {
        "email":           f"anonymised_{candidate_id[:8]}@deleted.invalid",
        "first_name":      "[Anonymised]",
        "last_name":       "[Anonymised]",
        "phone":           None,
        "location":        None,
        "state":           None,
        "city":            None,
        "resume_url":      None,
        "raw_data":       {},
        "screening_result": {},
        "data_status":     "ANONYMISED",
        "updated_at":      now,
    }
    try:
        supabase.table("candidates").update(anonymized_update).eq("id", candidate_id).eq("org_id", org_id).execute()
    except Exception as exc:
        logger.error("DPDP anonymization failed for %s: %s", candidate_id, exc)
        raise

    # Remove non-statutory application payloads and document access references.
    docs = []
    retained_docs = []
    erasable_docs = []
    try:
        docs = (supabase.table("candidate_documents").select(
                "id,storage_key,document_type,data_category,retention_until,legal_hold,legal_hold_basis,created_at")
                .eq("candidate_id", candidate_id).eq("org_id", org_id).execute().data or [])
        from app.services.dpdp_service import classify_document_retention
        for document in docs:
            decision = classify_document_retention(document)
            (retained_docs if decision["retain"] else erasable_docs).append((document, decision))
        from app.services.s3_service import S3Service
        storage_result = S3Service().delete_objects([
            row.get("storage_key") for row, _ in erasable_docs if row.get("storage_key")
        ])
        erasable_ids = [row["id"] for row, _ in erasable_docs if row.get("id")]
        if erasable_ids:
            supabase.table("candidate_documents").update({
                "storage_key": "[ERASED]", "file_url": None, "status": "ERASED", "erased_at": now,
            }).in_("id", erasable_ids).eq("org_id", org_id).execute()
        for document, decision in retained_docs:
            supabase.table("candidate_documents").update({
                "legal_hold": True,
                "legal_hold_basis": decision["legal_basis"],
                "retention_until": decision["retention_until"],
                "data_category": decision["data_category"],
            }).eq("id", document["id"]).eq("org_id", org_id).execute()
        actions = [{
            "org_id": org_id,
            "candidate_id": candidate_id,
            "document_id": document.get("id"),
            "data_category": decision["data_category"],
            "action": "LEGAL_HOLD" if decision["retain"] else "DELETE",
            "status": "COMPLETED",
            "scheduled_for": decision.get("retention_until"),
            "completed_at": now,
            "legal_basis": decision.get("legal_basis"),
        } for document, decision in retained_docs + erasable_docs]
        if actions:
            supabase.table("dpdp_retention_actions").insert(actions).execute()
    except Exception as exc:
        logger.error("DPDP storage deletion failed for %s: %s", candidate_id, exc)
        storage_result = {"requested": len(docs), "deleted": 0, "errors": [str(exc)]}

    try:
        supabase.table("applications").update({"form_data": {}}).eq(
            "candidate_id", candidate_id
        ).eq("org_id", org_id).execute()
        supabase.table("india_identity_verifications").update({
            "doc_image_url": None,
            "digilocker_uri": None,
            "aadhaar_last4": None,
            "aadhaar_masked": None,
            "pan_number": None,
            "pan_masked": None,
            "notes": "Identity data erased under approved DPDP request",
        }).eq("candidate_id", candidate_id).eq("org_id", org_id).execute()
        supabase.table("aadhaar_kyc_sessions").delete().eq("candidate_id", candidate_id).eq("org_id", org_id).execute()
        supabase.table("privacy_center_sessions").delete().eq("candidate_id", candidate_id).execute()
    except Exception as exc:
        logger.error("DPDP related-record cleanup failed for %s: %s", candidate_id, exc)
        raise

    manifest = {
        "anonymised": True,
        "candidate_id": candidate_id,
        "candidate_fields": list(anonymized_update.keys()),
        "application_form_data_cleared": True,
        "identity_references_cleared": True,
        "documents_found": len(docs),
        "documents_retained": len(retained_docs),
        "documents_erased": len(erasable_docs),
        "retained_document_reasons": [decision for _, decision in retained_docs],
        "storage": storage_result,
        "storage_deletion_status": "COMPLETED" if not storage_result.get("errors") else "FAILED",
        "statutory_records_retained": ["EPF", "ESIC", "professional_tax", "payroll_audit"],
    }

    log_india_compliance_audit(
        supabase,
        action="DATA_ANONYMISED",
        entity_type="candidate",
        entity_id=candidate_id,
        org_id=org_id,
        metadata=manifest,
        law_reference="DPDP Act 2023 Section 13",
    )
    return manifest


# ─────────────────────────────────────────────────────────────────────────────
# FSSAI
# ─────────────────────────────────────────────────────────────────────────────

def validate_fssai_license(license_number: str) -> bool:
    """FSSAI license is 14 digits."""
    return bool(re.fullmatch(r"\d{14}", (license_number or "").strip()))


def get_expiring_fssai_certs(supabase, org_id: str, days_ahead: int = 30) -> list[dict]:
    """Return FSSAI certificates expiring within `days_ahead` days."""
    cutoff = (datetime.utcnow() + timedelta(days=days_ahead)).date().isoformat()
    today  = datetime.utcnow().date().isoformat()
    try:
        result = (
            supabase.table("fssai_certificates")
            .select("id, org_id, candidate_id, cert_type, license_number, expiry_date, status")
            .eq("org_id", org_id)
            .eq("status", "ACTIVE")
            .gte("expiry_date", today)
            .lte("expiry_date", cutoff)
            .order("expiry_date")
            .execute()
        )
        return result.data or []
    except Exception as exc:
        logger.warning("get_expiring_fssai_certs failed: %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Audit Logging
# ─────────────────────────────────────────────────────────────────────────────

def log_india_compliance_audit(
    supabase,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    org_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    actor_type: str = "SYSTEM",
    metadata: Optional[dict] = None,
    ip_address: Optional[str] = None,
    law_reference: Optional[str] = None,
) -> None:
    """Append an India-compliance audit log entry (best-effort, never raises)."""
    try:
        supabase.table("india_compliance_audit_logs").insert({
            "org_id":        org_id,
            "actor_type":    actor_type,
            "actor_id":      actor_id,
            "action":        action,
            "entity_type":   entity_type,
            "entity_id":     entity_id,
            "law_reference": law_reference,
            "metadata":      metadata or {},
            "ip_address":    ip_address,
            "created_at":    datetime.utcnow().isoformat(),
        }).execute()
    except Exception as exc:
        logger.warning("Audit log write failed (%s): %s", action, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Gratuity
# ─────────────────────────────────────────────────────────────────────────────

def calculate_gratuity(monthly_last_drawn_inr: float, years_of_service: float) -> dict:
    """
    Gratuity = (15 / 26) × last-drawn monthly salary × years of service
    Applicable if service ≥ 5 years (Payment of Gratuity Act 1972).
    Cap: ₹20 lakh.
    """
    if years_of_service < GRATUITY_ELIGIBLE_YEARS:
        return {
            "eligible":   False,
            "reason":     f"Minimum {GRATUITY_ELIGIBLE_YEARS} years required; served {years_of_service:.1f} years",
            "gratuity_inr": 0,
        }
    raw = (15 / 26) * monthly_last_drawn_inr * years_of_service
    capped = min(raw, GRATUITY_CAP_INR)
    return {
        "eligible":       True,
        "years_of_service": years_of_service,
        "formula":        "(15/26) × last_salary × years",
        "raw_inr":        round(raw, 2),
        "gratuity_inr":   round(capped, 2),
        "cap_applied":    raw > GRATUITY_CAP_INR,
    }
