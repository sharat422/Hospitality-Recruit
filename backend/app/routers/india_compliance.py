"""
India Compliance Router — Feature 06 India
Prefix: /api/v1/india-compliance

Replaces Western compliance router (/compliance) with India-specific law:
  DPDP | EPF/ESIC | Minimum Wages | Working Hours | Professional Tax |
  FSSAI | Identity Verification | Diversity | Audit Log | Gratuity
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional, List, Annotated
from datetime import datetime, date
import logging

from fastapi import Depends

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.india_compliance_service import (
    validate_pan, mask_pan, validate_aadhaar_last4, validate_uan, validate_fssai_license,
    get_minimum_wage, check_wage_compliance, get_professional_tax,
    check_working_hours_violation, calculate_overtime,
    calculate_epf_contribution, calculate_esic_contribution, is_esic_eligible,
    calculate_gratuity,
    record_dpdp_consent, create_dpdp_erasure_request, anonymize_candidate_dpdp,
    get_expiring_identity_docs, get_expiring_fssai_certs,
    log_india_compliance_audit,
    DPDP_PURPOSE_CODES, INDIA_STATES, STATES_WITH_PROFESSIONAL_TAX,
)

router = APIRouter(tags=["India Compliance"])
logger = logging.getLogger(__name__)

CurrentUser = Annotated[dict, Depends(get_current_user)]


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class IdentityVerificationCreate(BaseModel):
    candidate_id:     str
    doc_type:         str  # AADHAAR | PAN | DIGILOCKER | VOTER_ID | PASSPORT | DRIVING_LICENCE
    aadhaar_last4:    Optional[str] = None
    pan_number:       Optional[str] = None
    digilocker_uri:   Optional[str] = None
    doc_number_last4: Optional[str] = None
    doc_expiry_date:  Optional[str] = None
    doc_issuing_state: Optional[str] = None
    notes:            Optional[str] = None

    @field_validator("pan_number")
    @classmethod
    def validate_pan_field(cls, v: Optional[str]) -> Optional[str]:
        if v and not validate_pan(v):
            raise ValueError("Invalid PAN format. Expected: ABCDE1234F")
        return mask_pan(v) if v else v

    @field_validator("aadhaar_last4")
    @classmethod
    def validate_aadhaar_field(cls, v: Optional[str]) -> Optional[str]:
        if v and not validate_aadhaar_last4(v):
            raise ValueError("Aadhaar last-4 must be exactly 4 digits")
        return v


class VerifyIdentityRequest(BaseModel):
    status:           str   # VERIFIED | REJECTED
    rejection_reason: Optional[str] = None


class EPFESICCreate(BaseModel):
    candidate_id:           str
    epf_uan:                Optional[str] = None
    epf_account_number:     Optional[str] = None
    esic_ip_number:         Optional[str] = None
    epf_joining_date:       Optional[str] = None
    esic_monthly_wage_inr:  Optional[float] = None
    nominee_name:           Optional[str] = None
    nominee_relation:       Optional[str] = None

    @field_validator("epf_uan")
    @classmethod
    def validate_uan_field(cls, v: Optional[str]) -> Optional[str]:
        if v and not validate_uan(v):
            raise ValueError("UAN must be a 12-digit number")
        return v


class WageComplianceCheck(BaseModel):
    state_code:          str
    skill_category:      str   # UNSKILLED | SEMI_SKILLED | SKILLED | HIGHLY_SKILLED
    offered_monthly_inr: float
    zone:                str = "A"


class WorkingHoursCheck(BaseModel):
    shift_start:         str   # ISO datetime
    shift_end:           str   # ISO datetime
    break_hours:         float = 0.5
    establishment_type:  str   = "SHOP"   # FACTORY | SHOP
    is_female_worker:    bool  = False
    hourly_rate_inr:     float = 0


class ProfessionalTaxQuery(BaseModel):
    state_code:         str
    monthly_salary_inr: float
    month:              Optional[int] = None   # 1-12


class ProfessionalTaxRecordCreate(ProfessionalTaxQuery):
    candidate_id: str
    pt_period: str
    ptrc_number: Optional[str] = None
    ptec_number: Optional[str] = None

    @field_validator("pt_period")
    @classmethod
    def validate_pt_period(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m")
        except ValueError as exc:
            raise ValueError("pt_period must use YYYY-MM format") from exc
        return v


class EPFContribCalc(BaseModel):
    monthly_basic_da_inr: float


class DPDPConsentRequest(BaseModel):
    candidate_id:        str
    purpose_code:        str
    consented:           bool
    ip_address:          Optional[str] = None
    user_agent:          Optional[str] = None
    consent_mechanism:   str = "DIGITAL_FORM"
    consent_text_version: str = "v1.0"

    @field_validator("purpose_code")
    @classmethod
    def validate_purpose(cls, v: str) -> str:
        if v not in DPDP_PURPOSE_CODES:
            raise ValueError(f"purpose_code must be one of: {list(DPDP_PURPOSE_CODES.keys())}")
        return v


class DPDPErasureRequest(BaseModel):
    candidate_id:    str
    request_type:    str = "ERASURE"   # ERASURE | CORRECTION | ACCESS
    reason:          Optional[str] = None
    specific_fields: Optional[List[str]] = None


class FSSAICreate(BaseModel):
    candidate_id:    Optional[str] = None   # None for establishment license
    cert_type:       str   # ESTABLISHMENT_LICENSE | FOSTAC_TRAINING | FOOD_HANDLER
    license_number:  Optional[str] = None
    license_type:    Optional[str] = None   # BASIC | STATE | CENTRAL
    licensed_entity: Optional[str] = None
    fostac_cert_number: Optional[str] = None
    training_provider:  Optional[str] = None
    fostac_course:      Optional[str] = None
    issue_date:      Optional[str] = None
    expiry_date:     str
    state_code:      Optional[str] = None
    activity_category: Optional[str] = None

    @field_validator("license_number")
    @classmethod
    def validate_fssai_num(cls, v: Optional[str]) -> Optional[str]:
        if v and not validate_fssai_license(v):
            raise ValueError("FSSAI license number must be 14 digits")
        return v


class DiversityDataCreate(BaseModel):
    candidate_id:     str
    social_category:  Optional[str] = None  # SC | ST | OBC | EWS | GENERAL
    gender:           Optional[str] = None
    is_pwd:           bool = False
    pwd_category:     Optional[str] = None
    pwd_cert_number:  Optional[str] = None
    pwd_disability_pct: Optional[int] = None
    is_ex_serviceman: bool = False
    service_branch:   Optional[str] = None
    self_declared:    bool = True
    dpdp_consent_id:  Optional[str] = None  # Consent must be obtained first


class GratuityCalcRequest(BaseModel):
    monthly_last_drawn_inr: float
    years_of_service:       float


# ─────────────────────────────────────────────────────────────────────────────
# Identity Verification
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/identity-verification", status_code=201)
async def create_identity_verification(
    body: IdentityVerificationCreate,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Submit an identity document for verification (Aadhaar/PAN/DigiLocker/Passport)."""
    org_id = _get_org_id(supabase, user)
    payload = {
        "org_id":            org_id,
        "candidate_id":      body.candidate_id,
        "doc_type":          body.doc_type,
        "aadhaar_last4":     body.aadhaar_last4,
        "pan_number":        body.pan_number,
        "pan_masked":        body.pan_number,
        "digilocker_uri":    body.digilocker_uri,
        "doc_number_last4":  body.doc_number_last4,
        "doc_expiry_date":   body.doc_expiry_date,
        "doc_issuing_state": body.doc_issuing_state,
        "notes":             body.notes,
        "status":            "PENDING",
        "created_at":        datetime.utcnow().isoformat(),
        "updated_at":        datetime.utcnow().isoformat(),
    }
    result = supabase.table("india_identity_verifications").insert(payload).execute()
    if not result.data:
        raise HTTPException(500, "Failed to create identity verification")
    log_india_compliance_audit(supabase, "IDENTITY_VERIFICATION_SUBMITTED",
                               "candidate", body.candidate_id, org_id,
                               law_reference="Aadhaar Act 2016 / IT Act 2000")
    return result.data[0]


@router.get("/identity-verification/{candidate_id}")
async def get_candidate_verifications(
    candidate_id: str, supabase: SupabaseClient, user: CurrentUser,
):
    """List all identity verification records for a candidate."""
    org_id = _get_org_id(supabase, user)
    result = (
        supabase.table("india_identity_verifications")
        .select("id,org_id,candidate_id,doc_type,aadhaar_masked,pan_masked,status,"
                "verified_by,verified_at,rejection_reason,doc_number_last4,doc_expiry_date,"
                "doc_issuing_state,kyc_provider,created_at,updated_at")
        .eq("org_id", org_id)
        .eq("candidate_id", candidate_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.patch("/identity-verification/{verification_id}/verify")
async def verify_identity_doc(
    verification_id: str, body: VerifyIdentityRequest,
    supabase: SupabaseClient, user: CurrentUser,
):
    """Mark an identity document as VERIFIED or REJECTED (HR admin action)."""
    org_id  = _get_org_id(supabase, user)
    user_id = user.get("sub")
    now     = datetime.utcnow().isoformat()

    update = {
        "status":           body.status,
        "verified_by":      user_id if body.status == "VERIFIED" else None,
        "verified_at":      now     if body.status == "VERIFIED" else None,
        "rejection_reason": body.rejection_reason,
        "updated_at":       now,
    }
    result = (
        supabase.table("india_identity_verifications")
        .update(update).eq("id", verification_id).execute()
    )
    if not result.data:
        raise HTTPException(404, "Verification record not found")

    # Update convenience flag on candidates table
    if body.status == "VERIFIED":
        doc_type = result.data[0].get("doc_type", "")
        cand_id  = result.data[0].get("candidate_id")
        if doc_type == "AADHAAR" and cand_id:
            supabase.table("candidates").update({"aadhaar_verified": True}).eq("id", cand_id).execute()
        elif doc_type == "PAN" and cand_id:
            supabase.table("candidates").update({"pan_verified": True}).eq("id", cand_id).execute()

    log_india_compliance_audit(supabase,
                               "IDENTITY_VERIFIED" if body.status == "VERIFIED" else "IDENTITY_REJECTED",
                               "identity_verification", verification_id, org_id, user_id)
    return result.data[0]


@router.get("/identity-verification/expiring")
async def get_expiring_docs(
    days: int = Query(30, ge=1, le=365),
    supabase: SupabaseClient = None,
    user: CurrentUser = None,
):
    """Return identity documents expiring within `days` days."""
    return get_expiring_identity_docs(supabase, days)


# ─────────────────────────────────────────────────────────────────────────────
# EPF / ESIC
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/epf-esic", status_code=201)
async def register_epf_esic(
    body: EPFESICCreate, supabase: SupabaseClient, user: CurrentUser,
):
    """Register or update EPF/ESIC details for a candidate."""
    org_id = _get_org_id(supabase, user)
    esic_eligible = is_esic_eligible(body.esic_monthly_wage_inr or 0)

    payload = {
        "org_id":                 org_id,
        "candidate_id":           body.candidate_id,
        "epf_uan":                body.epf_uan,
        "epf_account_number":     body.epf_account_number,
        "epf_joining_date":       body.epf_joining_date,
        "esic_ip_number":         body.esic_ip_number,
        "esic_monthly_wage_inr":  body.esic_monthly_wage_inr,
        "esic_eligible":          esic_eligible,
        "nominee_name":           body.nominee_name,
        "nominee_relation":       body.nominee_relation,
        "status":                 "ACTIVE",
        "created_at":             datetime.utcnow().isoformat(),
        "updated_at":             datetime.utcnow().isoformat(),
    }
    result = supabase.table("epf_esic_registrations").insert(payload).execute()
    if not result.data:
        raise HTTPException(500, "Failed to save EPF/ESIC registration")

    # Update UAN on candidates table
    if body.epf_uan:
        supabase.table("candidates").update({"epf_uan": body.epf_uan}).eq("id", body.candidate_id).execute()

    log_india_compliance_audit(supabase, "EPF_REGISTERED", "candidate",
                               body.candidate_id, org_id,
                               law_reference="EPF Act 1952 / Social Security Code 2020")
    return {**result.data[0], "esic_eligible": esic_eligible}


@router.post("/epf-esic/calculate")
async def calculate_epf_esic(body: EPFESICCreate, supabase: SupabaseClient, user: CurrentUser):
    """Calculate EPF and ESIC contribution amounts without saving."""
    epf = calculate_epf_contribution(body.esic_monthly_wage_inr or 0)
    esic = calculate_esic_contribution(body.esic_monthly_wage_inr or 0)
    return {"epf": epf, "esic": esic}


@router.post("/epf-esic/contribution-calc")
async def calc_contributions(body: EPFContribCalc, supabase: SupabaseClient, user: CurrentUser):
    """Calculate EPF contributions for a given monthly Basic+DA salary."""
    return {
        "epf": calculate_epf_contribution(body.monthly_basic_da_inr),
        "gratuity_preview": calculate_gratuity(body.monthly_basic_da_inr, 5),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Minimum Wages
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/minimum-wages")
async def list_minimum_wages(
    state_code:     Optional[str] = Query(None),
    skill_category: Optional[str] = Query(None),
    supabase: SupabaseClient = None,
    user: CurrentUser = None,
):
    """List current minimum wages. Filter by state_code and/or skill_category."""
    q = (
        supabase.table("india_minimum_wages")
        .select("*")
        .eq("is_current", True)
        .order("state_code")
        .order("skill_category")
    )
    if state_code:     q = q.eq("state_code", state_code.upper())
    if skill_category: q = q.eq("skill_category", skill_category.upper())
    return q.execute().data or []


@router.post("/minimum-wages/check")
async def check_minimum_wage(
    body: WageComplianceCheck, supabase: SupabaseClient, user: CurrentUser,
):
    """Check whether an offered salary meets the state minimum wage."""
    return check_wage_compliance(
        supabase, body.state_code, body.skill_category,
        body.offered_monthly_inr, body.zone,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Working Hours
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/working-hours/check")
async def check_working_hours(
    body: WorkingHoursCheck, supabase: SupabaseClient, user: CurrentUser,
):
    """Detect working-hour violations per Factories Act / OSH Code."""
    try:
        start = datetime.fromisoformat(body.shift_start)
        end   = datetime.fromisoformat(body.shift_end)
    except ValueError:
        raise HTTPException(422, "shift_start and shift_end must be ISO datetime strings")

    result = check_working_hours_violation(
        start, end, body.break_hours, body.establishment_type, body.is_female_worker
    )
    if body.hourly_rate_inr > 0 and result["actual_hours"] > 0:
        result["overtime"] = calculate_overtime(
            result["actual_hours"], body.establishment_type, body.hourly_rate_inr
        )
    return result


@router.post("/working-hours/log")
async def log_working_hours(
    body: WorkingHoursCheck,
    candidate_id: str = Query(...),
    supabase: SupabaseClient = None,
    user: CurrentUser = None,
):
    """Log a shift's working hours and auto-detect violations."""
    org_id = _get_org_id(supabase, user)
    try:
        start = datetime.fromisoformat(body.shift_start)
        end   = datetime.fromisoformat(body.shift_end)
    except ValueError:
        raise HTTPException(422, "Invalid datetime format")

    result_check = check_working_hours_violation(
        start, end, body.break_hours, body.establishment_type, body.is_female_worker
    )
    violations = result_check.get("violations", [])
    first_violation = violations[0] if violations else {}

    row = {
        "org_id":            org_id,
        "candidate_id":      candidate_id,
        "shift_date":        start.date().isoformat(),
        "shift_start":       body.shift_start,
        "shift_end":         body.shift_end,
        "actual_hours":      result_check["actual_hours"],
        "break_hours":       body.break_hours,
        "spread_over_hours": result_check["spread_over"],
        "is_night_shift":    result_check["is_night_shift"],
        "applicable_act":    "FACTORIES_ACT" if body.establishment_type == "FACTORY" else "SHOPS_ACT",
        "violation_type":    first_violation.get("type"),
        "violation_severity": first_violation.get("severity"),
        "created_at":        datetime.utcnow().isoformat(),
    }
    saved = supabase.table("working_hours_compliance").insert(row).execute()
    if violations:
        log_india_compliance_audit(supabase, "WORKING_HOURS_FLAGGED",
                                   "candidate", candidate_id, org_id,
                                   metadata={"violations": violations},
                                   law_reference="Factories Act 1948 / OSH Code 2020")
    return {**result_check, "saved_id": (saved.data[0]["id"] if saved.data else None)}


# ─────────────────────────────────────────────────────────────────────────────
# Professional Tax
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/professional-tax/slabs")
async def get_pt_slabs(
    state_code: Optional[str] = Query(None),
    supabase: SupabaseClient = None,
    user: CurrentUser = None,
):
    """List professional tax slabs. Optionally filter by state_code."""
    q = supabase.table("professional_tax_slabs").select("*").eq("is_current", True)
    if state_code:
        q = q.eq("state_code", state_code.upper())
    return q.order("state_code").order("slab_min_salary_inr").execute().data or []


@router.post("/professional-tax/calculate")
async def calculate_pt(body: ProfessionalTaxQuery, supabase: SupabaseClient, user: CurrentUser):
    """Calculate Professional Tax for a given state and monthly salary."""
    return get_professional_tax(supabase, body.state_code, body.monthly_salary_inr, body.month)


@router.get("/professional-tax/applicable-states")
async def pt_applicable_states(supabase: SupabaseClient, user: CurrentUser):
    """Return the list of states that levy Professional Tax."""
    return {"states": sorted(STATES_WITH_PROFESSIONAL_TAX)}


@router.post("/professional-tax/records", status_code=201)
async def create_pt_record(
    body: ProfessionalTaxRecordCreate,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Calculate and persist one auditable monthly PT deduction."""
    org_id = _get_org_id(supabase, user)
    calculation = get_professional_tax(
        supabase, body.state_code, body.monthly_salary_inr,
        body.month or datetime.strptime(body.pt_period, "%Y-%m").month,
    )
    state_code = body.state_code.upper()
    payload = {
        "org_id": org_id,
        "candidate_id": body.candidate_id,
        "state_code": state_code,
        "state_name": INDIA_STATES.get(state_code, state_code),
        "ptrc_number": body.ptrc_number,
        "ptec_number": body.ptec_number,
        "monthly_salary_inr": body.monthly_salary_inr,
        "pt_deducted_inr": calculation["pt_inr"],
        "pt_period": body.pt_period,
        "payment_status": "PENDING",
    }
    try:
        saved = supabase.table("professional_tax_records").insert(payload).execute()
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            raise HTTPException(409, "Professional Tax record already exists for this employee and period")
        raise HTTPException(500, "Failed to save Professional Tax record") from exc
    if not saved.data:
        raise HTTPException(500, "Failed to save Professional Tax record")
    log_india_compliance_audit(
        supabase, "PROFESSIONAL_TAX_RECORDED", "candidate", body.candidate_id, org_id,
        metadata={"period": body.pt_period, "amount_inr": calculation["pt_inr"]},
        law_reference="Applicable State Professional Tax Act",
    )
    return saved.data[0]


@router.get("/professional-tax/records")
async def list_pt_records(
    candidate_id: Optional[str] = Query(None),
    pt_period: Optional[str] = Query(None),
    supabase: SupabaseClient = None,
    user: CurrentUser = None,
):
    """List organisation-scoped PT records; RLS also allows employee self-service."""
    org_id = _get_org_id(supabase, user)
    q = supabase.table("professional_tax_records").select("*").eq("org_id", org_id)
    if candidate_id:
        q = q.eq("candidate_id", candidate_id)
    if pt_period:
        q = q.eq("pt_period", pt_period)
    return q.order("pt_period", desc=True).execute().data or []


# ─────────────────────────────────────────────────────────────────────────────
# DPDP Consent
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dpdp/purpose-codes")
async def list_dpdp_purposes(supabase: SupabaseClient, user: CurrentUser):
    """Return all valid DPDP purpose codes with descriptions."""
    return [{"code": k, "description": v} for k, v in DPDP_PURPOSE_CODES.items()]


@router.post("/dpdp/consent")
async def record_consent(body: DPDPConsentRequest, supabase: SupabaseClient, user: CurrentUser):
    """Record a DPDP consent event (grant or withdrawal) for a candidate."""
    org_id = _get_org_id(supabase, user)
    return record_dpdp_consent(
        supabase, org_id, body.candidate_id, body.purpose_code,
        body.consented, body.ip_address, body.user_agent,
        body.consent_mechanism, None, body.consent_text_version,
    )


@router.get("/dpdp/consent/{candidate_id}")
async def get_candidate_consent(
    candidate_id: str, supabase: SupabaseClient, user: CurrentUser,
):
    """List all DPDP consent records for a candidate."""
    org_id = _get_org_id(supabase, user)
    result = (
        supabase.table("dpdp_consent_records")
        .select("*")
        .eq("org_id", org_id)
        .eq("candidate_id", candidate_id)
        .order("consented_at", desc=True)
        .execute()
    )
    return result.data or []


@router.post("/dpdp/erasure-request")
async def request_erasure(body: DPDPErasureRequest, supabase: SupabaseClient, user: CurrentUser):
    """Create a DPDP erasure or correction request (30-day SLA per DPDP Act)."""
    org_id = _get_org_id(supabase, user)
    return create_dpdp_erasure_request(
        supabase, org_id, body.candidate_id,
        body.request_type, body.reason, body.specific_fields,
    )


@router.get("/dpdp/erasure-requests")
async def list_erasure_requests(
    status: Optional[str] = Query(None),
    supabase: SupabaseClient = None,
    user: CurrentUser = None,
):
    """List DPDP erasure/correction requests. Filter by status."""
    org_id = _get_org_id(supabase, user)
    q = (
        supabase.table("dpdp_erasure_requests")
        .select("*")
        .eq("org_id", org_id)
        .order("requested_at", desc=True)
    )
    if status:
        q = q.eq("status", status)
    return q.execute().data or []


@router.post("/dpdp/erasure-requests/{request_id}/process")
async def process_erasure(
    request_id: str,
    action: str = Query(..., description="COMPLETE | REJECT"),
    reason: Optional[str] = Query(None),
    supabase: SupabaseClient = None,
    user: CurrentUser = None,
):
    """Process a DPDP erasure request (complete or reject with reason)."""
    org_id  = _get_org_id(supabase, user)
    user_id = user.get("sub")

    req_res = (
        supabase.table("dpdp_erasure_requests")
        .select("*").eq("id", request_id).limit(1).execute()
    )
    if not req_res.data:
        raise HTTPException(404, "Erasure request not found")

    req = req_res.data[0]
    now = datetime.utcnow().isoformat()

    if action == "COMPLETE":
        manifest = anonymize_candidate_dpdp(supabase, req["candidate_id"], org_id)
        supabase.table("dpdp_erasure_requests").update({
            "status": "COMPLETED", "completed_at": now, "processed_by": user_id,
            "erasure_manifest": manifest,
            "storage_deletion_status": manifest.get("storage_deletion_status", "COMPLETED"),
            "storage_deleted_at": now if manifest.get("storage_deletion_status") == "COMPLETED" else None,
        }).eq("id", request_id).execute()
        log_india_compliance_audit(supabase, "DPDP_ERASURE_COMPLETED",
                                   "candidate", req["candidate_id"], org_id, user_id,
                                   law_reference="DPDP Act 2023 Section 13")
        return {"processed": True, "action": "COMPLETED", "anonymised": True, "manifest": manifest}

    elif action == "REJECT":
        if not reason:
            raise HTTPException(422, "denial_reason required when rejecting")
        supabase.table("dpdp_erasure_requests").update({
            "status": "REJECTED", "denial_reason": reason,
            "completed_at": now, "processed_by": user_id,
        }).eq("id", request_id).execute()
        return {"processed": True, "action": "REJECTED", "denial_reason": reason}

    raise HTTPException(422, "action must be COMPLETE or REJECT")


# ─────────────────────────────────────────────────────────────────────────────
# FSSAI
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/fssai", status_code=201)
async def add_fssai_cert(body: FSSAICreate, supabase: SupabaseClient, user: CurrentUser):
    """Add an FSSAI establishment license or FoSTaC training certificate."""
    org_id = _get_org_id(supabase, user)
    result = supabase.table("fssai_certificates").insert({
        "org_id":            org_id,
        "candidate_id":      body.candidate_id,
        "cert_type":         body.cert_type,
        "license_number":    body.license_number,
        "license_type":      body.license_type,
        "licensed_entity":   body.licensed_entity,
        "fostac_cert_number": body.fostac_cert_number,
        "training_provider": body.training_provider,
        "fostac_course":     body.fostac_course,
        "issue_date":        body.issue_date,
        "expiry_date":       body.expiry_date,
        "state_code":        body.state_code,
        "activity_category": body.activity_category,
        "status":            "ACTIVE",
        "created_at":        datetime.utcnow().isoformat(),
        "updated_at":        datetime.utcnow().isoformat(),
    }).execute()
    if not result.data:
        raise HTTPException(500, "Failed to save FSSAI certificate")

    # Mark candidate as FSSAI trained if it's a training cert
    if body.candidate_id and body.cert_type in ("FOSTAC_TRAINING", "FOOD_HANDLER"):
        supabase.table("candidates").update({"fssai_trained": True}).eq("id", body.candidate_id).execute()

    log_india_compliance_audit(supabase, "FSSAI_CERT_ADDED",
                               "fssai_certificates", result.data[0]["id"], org_id,
                               law_reference="Food Safety and Standards Act 2006")
    return result.data[0]


@router.get("/fssai")
async def list_fssai_certs(
    candidate_id: Optional[str] = Query(None),
    supabase: SupabaseClient = None,
    user: CurrentUser = None,
):
    """List all FSSAI certificates for the org, optionally filtered by candidate."""
    org_id = _get_org_id(supabase, user)
    q = supabase.table("fssai_certificates").select("*").eq("org_id", org_id).order("expiry_date")
    if candidate_id:
        q = q.eq("candidate_id", candidate_id)
    return q.execute().data or []


@router.get("/fssai/expiring")
async def get_expiring_fssai(
    days: int = Query(30, ge=1, le=180),
    supabase: SupabaseClient = None,
    user: CurrentUser = None,
):
    """Return FSSAI certificates expiring within `days` days."""
    org_id = _get_org_id(supabase, user)
    return get_expiring_fssai_certs(supabase, org_id, days)


# ─────────────────────────────────────────────────────────────────────────────
# India Diversity Data
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/diversity", status_code=201)
async def collect_diversity_data(body: DiversityDataCreate, supabase: SupabaseClient, user: CurrentUser):
    """
    Record voluntary India diversity data (SC/ST/OBC/PWD/Ex-servicemen).
    DPDP consent MUST be obtained before calling this endpoint.
    """
    org_id = _get_org_id(supabase, user)
    if not body.dpdp_consent_id:
        raise HTTPException(
            422,
            "dpdp_consent_id is required. Obtain DPDP consent for SENSITIVE_DATA "
            "before collecting diversity data."
        )
    result = supabase.table("india_diversity_data").insert({
        "org_id":             org_id,
        "candidate_id":       body.candidate_id,
        "social_category":    body.social_category,
        "gender":             body.gender,
        "is_pwd":             body.is_pwd,
        "pwd_category":       body.pwd_category,
        "pwd_cert_number":    body.pwd_cert_number,
        "pwd_disability_pct": body.pwd_disability_pct,
        "is_ex_serviceman":   body.is_ex_serviceman,
        "service_branch":     body.service_branch,
        "dpdp_consent_id":    body.dpdp_consent_id,
        "self_declared":      body.self_declared,
        "collected_at":       datetime.utcnow().isoformat(),
    }).execute()
    if not result.data:
        raise HTTPException(500, "Failed to save diversity data")
    log_india_compliance_audit(supabase, "DIVERSITY_DATA_COLLECTED",
                               "candidate", body.candidate_id, org_id,
                               law_reference="RPWD Act 2016 / DPDP Act 2023 Section 6")
    return result.data[0]


@router.get("/diversity/report")
async def diversity_report(supabase: SupabaseClient, user: CurrentUser):
    """Aggregate diversity data report for the org."""
    org_id = _get_org_id(supabase, user)
    rows = (
        supabase.table("india_diversity_data")
        .select("social_category, gender, is_pwd, is_ex_serviceman")
        .eq("org_id", org_id)
        .execute()
    ).data or []

    categories: dict = {}
    genders: dict = {}
    pwd_count = 0
    ex_sm_count = 0
    for r in rows:
        cat = r.get("social_category") or "NOT_DISCLOSED"
        categories[cat] = categories.get(cat, 0) + 1
        gen = r.get("gender") or "NOT_DISCLOSED"
        genders[gen] = genders.get(gen, 0) + 1
        if r.get("is_pwd"): pwd_count += 1
        if r.get("is_ex_serviceman"): ex_sm_count += 1

    return {
        "total_records":     len(rows),
        "social_categories": categories,
        "genders":           genders,
        "pwd_count":         pwd_count,
        "ex_serviceman_count": ex_sm_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Gratuity
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/gratuity/calculate")
async def calc_gratuity(body: GratuityCalcRequest, supabase: SupabaseClient, user: CurrentUser):
    """Calculate gratuity amount per Payment of Gratuity Act 1972."""
    return calculate_gratuity(body.monthly_last_drawn_inr, body.years_of_service)


# ─────────────────────────────────────────────────────────────────────────────
# Audit Log
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/audit-log")
async def get_audit_log(
    action:      Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    limit:       int           = Query(50, ge=1, le=500),
    supabase: SupabaseClient = None,
    user: CurrentUser = None,
):
    """Return India compliance audit log entries for the org."""
    org_id = _get_org_id(supabase, user)
    q = (
        supabase.table("india_compliance_audit_logs")
        .select("*")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if action:      q = q.eq("action", action)
    if entity_type: q = q.eq("entity_type", entity_type)
    return q.execute().data or []


# ─────────────────────────────────────────────────────────────────────────────
# Reference Data
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/states")
async def list_india_states(supabase: SupabaseClient, user: CurrentUser):
    """Return all India state codes and names."""
    return [{"code": k, "name": v} for k, v in sorted(INDIA_STATES.items())]


@router.get("/labour-codes")
async def get_labour_code_rules(
    code: Optional[str] = Query(None, description="WAGES | INDUSTRIAL_RELATIONS | SOCIAL_SECURITY | OSH"),
    supabase: SupabaseClient = None,
    user: CurrentUser = None,
):
    """Return Labour Code rules. Filter by specific code."""
    q = (
        supabase.table("labour_code_compliance")
        .select("labour_code, rule_type, state_code, state_name, description, threshold_value, threshold_unit, rule_detail, effective_date")
        .is_("org_id", None)  # National/Central rules
        .order("labour_code")
        .order("rule_type")
    )
    if code:
        q = q.eq("labour_code", code.upper())
    return q.execute().data or []


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_org_id(supabase, user: dict) -> str:
    """Resolve the caller's org_id from the users table."""
    user_id = user.get("sub", "")
    try:
        result = (
            supabase.table("users")
            .select("org_id")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("org_id"):
            return result.data[0]["org_id"]
    except Exception as exc:
        logger.warning("_get_org_id failed: %s", exc)
    raise HTTPException(403, "Could not determine organisation for caller.")
