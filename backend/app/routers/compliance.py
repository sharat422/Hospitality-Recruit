"""
Compliance & Right-to-Work router — Feature 06.
Covers: RTW checks, Fair Workweek, GDPR/consent, EEO reporting.
"""

import io
import csv
import logging
from datetime import datetime, timedelta, date
from typing import Annotated, Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request, Response
from pydantic import BaseModel

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.compliance_service import (
    check_scheduling_violation,
    log_audit_action,
    detect_jurisdiction,
)
from app.services.textract_service import extract_document_fields

logger = logging.getLogger(__name__)

router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Pydantic bodies
# ---------------------------------------------------------------------------

class RTWRequestBody(BaseModel):
    candidate_id: str
    application_id: Optional[str] = None
    check_type: str = "UK_RTW"


class RTWVerifyBody(BaseModel):
    expiry_date: Optional[str] = None
    notes: Optional[str] = None


class RTWRejectBody(BaseModel):
    reason: str


class ViolationCheckBody(BaseModel):
    employee_id: str
    jurisdiction: str
    new_shift_start: str
    new_shift_end: str
    published_at: str
    last_shift_end: Optional[str] = None


class ConsentItem(BaseModel):
    consent_type: str
    consented: bool
    consent_text_version: Optional[str] = "v1.0"


class ConsentRecordBody(BaseModel):
    candidate_id: str
    consents: List[ConsentItem]
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class WithdrawConsentBody(BaseModel):
    consent_type: str


class ErasureRequestBody(BaseModel):
    candidate_id: str
    requested_by_email: Optional[str] = None


class ErasureProcessBody(BaseModel):
    action: str  # "approve" or "deny"
    denial_reason: Optional[str] = None


class EEOCollectBody(BaseModel):
    candidate_id: str
    application_id: Optional[str] = None
    gender: Optional[str] = None
    ethnicity: Optional[str] = None
    disability_status: Optional[str] = None
    veteran_status: Optional[str] = None


class EEOExportBody(BaseModel):
    year: int
    format: str = "csv"


class BlindScreeningBody(BaseModel):
    enabled: bool


# ---------------------------------------------------------------------------
# RTW Endpoints
# ---------------------------------------------------------------------------

@router.post("/rtw/request")
async def create_rtw_request(
    body: RTWRequestBody,
    user: CurrentUser,
    supabase: SupabaseClient,
    request: Request,
):
    """Initiate a Right-to-Work check for a candidate."""
    row = {
        "candidate_id": body.candidate_id,
        "check_type": body.check_type,
        "status": "PENDING",
    }
    if body.application_id:
        row["application_id"] = body.application_id

    result = supabase.table("right_to_work_checks").insert(row).execute()
    check = result.data[0] if result.data else {}
    check_id = check.get("id")
    upload_token = check.get("upload_token")

    # Optional SMS notification — graceful fallback
    try:
        from app.services.twilio_service import TwilioService
        svc = TwilioService()
        # We don't have the candidate's phone here; SMS is best-effort
        logger.info("SMS notification skipped — no phone on RTW request payload")
    except ImportError:
        logger.info("twilio_service not available — skipping SMS")

    await log_audit_action(
        supabase,
        actor_type="USER",
        actor_id=user.get("sub"),
        action="RTW_REQUEST_CREATED",
        entity_type="right_to_work_checks",
        entity_id=str(check_id),
        metadata={"candidate_id": body.candidate_id, "check_type": body.check_type},
        ip=request.client.host if request.client else None,
    )

    from app.core.config import settings
    upload_url = f"{settings.APP_BASE_URL}/rtw/upload/{upload_token}"
    return {"check_id": check_id, "upload_token": upload_token, "upload_url": upload_url}


@router.get("/rtw/upload-info/{token}")
async def get_rtw_upload_info(token: str, supabase: SupabaseClient):
    """Public endpoint — returns check metadata so candidate can upload."""
    result = supabase.table("right_to_work_checks").select("id,check_type,status").eq("upload_token", token).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Upload token not found or expired")
    check = result.data[0]
    return {"check_type": check.get("check_type"), "status": check.get("status")}


@router.post("/rtw/upload/{token}")
async def upload_rtw_document(
    token: str,
    supabase: SupabaseClient,
    file: UploadFile = File(...),
):
    """Public endpoint — candidate uploads identity document for OCR extraction."""
    file_bytes = await file.read()
    extracted = extract_document_fields(file_bytes, file.filename or "document")

    result = supabase.table("right_to_work_checks").select("id,documents").eq("upload_token", token).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Upload token not found")

    check = result.data[0]
    check_id = check.get("id")
    existing_docs = check.get("documents") or []

    new_doc = {
        "filename": file.filename,
        "extracted": extracted,
        "uploaded_at": datetime.utcnow().isoformat(),
    }
    updated_docs = existing_docs + [new_doc]

    supabase.table("right_to_work_checks").update({
        "documents": updated_docs,
        "status": "DOCUMENTS_UPLOADED",
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", check_id).execute()

    await log_audit_action(
        supabase,
        actor_type="CANDIDATE",
        actor_id=None,
        action="RTW_DOCUMENT_UPLOADED",
        entity_type="right_to_work_checks",
        entity_id=str(check_id),
        metadata={"filename": file.filename, "extracted_by": extracted.get("extracted_by")},
    )

    return {"status": "DOCUMENTS_UPLOADED", "extracted_fields": extracted}


@router.patch("/rtw/{check_id}/verify")
async def verify_rtw_check(
    check_id: str,
    body: RTWVerifyBody,
    user: CurrentUser,
    supabase: SupabaseClient,
    request: Request,
):
    """Mark an RTW check as verified."""
    update_data: dict = {
        "status": "VERIFIED",
        "verified_by": user.get("sub"),
        "verified_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    if body.expiry_date:
        update_data["expiry_date"] = body.expiry_date
    if body.notes:
        update_data["notes"] = body.notes

    supabase.table("right_to_work_checks").update(update_data).eq("id", check_id).execute()

    await log_audit_action(
        supabase,
        actor_type="USER",
        actor_id=user.get("sub"),
        action="RTW_CHECK_VERIFIED",
        entity_type="right_to_work_checks",
        entity_id=check_id,
        metadata={"expiry_date": body.expiry_date},
        ip=request.client.host if request.client else None,
    )
    return {"status": "VERIFIED"}


@router.patch("/rtw/{check_id}/reject")
async def reject_rtw_check(
    check_id: str,
    body: RTWRejectBody,
    user: CurrentUser,
    supabase: SupabaseClient,
    request: Request,
):
    """Mark an RTW check as failed/rejected."""
    supabase.table("right_to_work_checks").update({
        "status": "FAILED",
        "notes": body.reason,
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", check_id).execute()

    await log_audit_action(
        supabase,
        actor_type="USER",
        actor_id=user.get("sub"),
        action="RTW_CHECK_REJECTED",
        entity_type="right_to_work_checks",
        entity_id=check_id,
        metadata={"reason": body.reason},
        ip=request.client.host if request.client else None,
    )
    return {"status": "FAILED"}


@router.get("/rtw/expiring")
async def get_expiring_rtw_checks(
    user: CurrentUser,
    supabase: SupabaseClient,
    days_ahead: int = Query(30, ge=1, le=365),
):
    """Return RTW checks expiring within the specified window."""
    today = date.today()
    cutoff = (today + timedelta(days=days_ahead)).isoformat()
    today_str = today.isoformat()

    result = (
        supabase.table("right_to_work_checks")
        .select("*")
        .eq("status", "VERIFIED")
        .gte("expiry_date", today_str)
        .lte("expiry_date", cutoff)
        .execute()
    )
    return result.data or []


@router.get("/rtw/candidate/{candidate_id}")
async def get_rtw_checks_for_candidate(
    candidate_id: str,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """Return all RTW checks for a candidate."""
    result = (
        supabase.table("right_to_work_checks")
        .select("*")
        .eq("candidate_id", candidate_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.post("/rtw/check-expiry")
async def process_rtw_expiry_alerts(
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """
    Scan RTW checks for upcoming/past expiry and set alert flags.
    Intended to be called by a scheduled job.
    """
    today = date.today()
    processed = 0

    # 30-day alert
    d30 = (today + timedelta(days=30)).isoformat()
    res30 = (
        supabase.table("right_to_work_checks")
        .select("id")
        .eq("status", "VERIFIED")
        .eq("alert_30_day_sent", False)
        .lte("expiry_date", d30)
        .gte("expiry_date", today.isoformat())
        .execute()
    )
    for row in res30.data or []:
        supabase.table("right_to_work_checks").update({"alert_30_day_sent": True}).eq("id", row["id"]).execute()
        processed += 1

    # 7-day alert
    d7 = (today + timedelta(days=7)).isoformat()
    res7 = (
        supabase.table("right_to_work_checks")
        .select("id")
        .eq("status", "VERIFIED")
        .eq("alert_7_day_sent", False)
        .lte("expiry_date", d7)
        .gte("expiry_date", today.isoformat())
        .execute()
    )
    for row in res7.data or []:
        supabase.table("right_to_work_checks").update({"alert_7_day_sent": True}).eq("id", row["id"]).execute()
        processed += 1

    # Expired alert
    res_exp = (
        supabase.table("right_to_work_checks")
        .select("id")
        .eq("status", "VERIFIED")
        .eq("alert_expired_sent", False)
        .lt("expiry_date", today.isoformat())
        .execute()
    )
    for row in res_exp.data or []:
        supabase.table("right_to_work_checks").update({
            "alert_expired_sent": True,
            "status": "EXPIRED",
        }).eq("id", row["id"]).execute()
        processed += 1

    return {"processed": processed}


# ---------------------------------------------------------------------------
# Fair Workweek Endpoints
# ---------------------------------------------------------------------------

@router.get("/fair-workweek/rules")
async def get_fair_workweek_rules(
    user: CurrentUser,
    supabase: SupabaseClient,
    jurisdiction: Optional[str] = Query(None),
):
    """Return fair workweek rules, optionally filtered by jurisdiction."""
    q = supabase.table("fair_workweek_rules").select("*")
    if jurisdiction:
        q = q.eq("jurisdiction", jurisdiction.upper())
    result = q.execute()
    return result.data or []


@router.post("/scheduling/check-violation")
async def check_scheduling_violations(
    body: ViolationCheckBody,
    user: CurrentUser,
    supabase: SupabaseClient,
    request: Request,
):
    """Check a proposed shift for Fair Workweek violations and log them."""
    def _parse(s: str) -> datetime:
        # Accept ISO format with or without timezone
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return datetime.fromisoformat(s)

    shift_start = _parse(body.new_shift_start)
    shift_end = _parse(body.new_shift_end)
    published_at = _parse(body.published_at)
    last_shift_end = _parse(body.last_shift_end) if body.last_shift_end else None

    jurisdiction = body.jurisdiction.upper()
    violations = check_scheduling_violation(shift_start, shift_end, last_shift_end, published_at, jurisdiction)

    # Log each violation to DB
    for v in violations:
        hours_rest = None
        if last_shift_end:
            hours_rest = (shift_start - last_shift_end).total_seconds() / 3600
        supabase.table("scheduling_compliance_log").insert({
            "employee_id": body.employee_id,
            "shift_date": shift_start.date().isoformat(),
            "shift_start": shift_start.isoformat(),
            "shift_end": shift_end.isoformat(),
            "hours_since_last_shift": hours_rest,
            "violation_type": v.get("type"),
            "violation_severity": v.get("severity"),
            "jurisdiction": jurisdiction,
            "resolved": False,
        }).execute()

    await log_audit_action(
        supabase,
        actor_type="USER",
        actor_id=user.get("sub"),
        action="SCHEDULING_VIOLATION_CHECK",
        entity_type="scheduling_compliance_log",
        entity_id=body.employee_id,
        metadata={"violations_found": len(violations), "jurisdiction": jurisdiction},
        ip=request.client.host if request.client else None,
    )

    return {"violations": violations, "jurisdiction": jurisdiction}


@router.get("/scheduling/violations")
async def list_scheduling_violations(
    user: CurrentUser,
    supabase: SupabaseClient,
    resolved: Optional[bool] = Query(None),
):
    """List scheduling compliance violations, optionally filtered by resolved status."""
    q = supabase.table("scheduling_compliance_log").select("*").order("created_at", desc=True)
    if resolved is not None:
        q = q.eq("resolved", resolved)
    result = q.execute()
    return result.data or []


@router.patch("/scheduling/violations/{violation_id}/resolve")
async def resolve_scheduling_violation(
    violation_id: str,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """Mark a scheduling violation as resolved."""
    supabase.table("scheduling_compliance_log").update({"resolved": True}).eq("id", violation_id).execute()
    return {"id": violation_id, "resolved": True}


@router.get("/audit-log")
async def get_audit_log(
    user: CurrentUser,
    supabase: SupabaseClient,
    entity_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Return compliance audit log entries, newest first."""
    q = supabase.table("compliance_audit_logs").select("*").order("created_at", desc=True).limit(limit)
    if entity_type:
        q = q.eq("entity_type", entity_type)
    result = q.execute()
    return result.data or []


# ---------------------------------------------------------------------------
# GDPR / Consent Endpoints
# ---------------------------------------------------------------------------

@router.post("/consent/record")
async def record_consent(
    body: ConsentRecordBody,
    supabase: SupabaseClient,
    request: Request,
):
    """Public endpoint — record candidate consent for data processing."""
    ip = body.ip_address or (request.client.host if request.client else None)
    rows = []
    for item in body.consents:
        rows.append({
            "candidate_id": body.candidate_id,
            "consent_type": item.consent_type,
            "consented": item.consented,
            "consent_text_version": item.consent_text_version or "v1.0",
            "ip_address": ip,
            "user_agent": body.user_agent,
            "consented_at": datetime.utcnow().isoformat(),
        })

    if rows:
        supabase.table("data_consent_records").insert(rows).execute()

    await log_audit_action(
        supabase,
        actor_type="CANDIDATE",
        actor_id=None,
        action="CONSENT_RECORDED",
        entity_type="data_consent_records",
        entity_id=body.candidate_id,
        metadata={"consent_count": len(rows), "ip": ip},
    )
    return {"recorded": True}


@router.get("/consent/{candidate_id}")
async def get_consent_records(
    candidate_id: str,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """Return all consent records for a candidate."""
    result = (
        supabase.table("data_consent_records")
        .select("*")
        .eq("candidate_id", candidate_id)
        .order("consented_at", desc=True)
        .execute()
    )
    return result.data or []


@router.post("/consent/{candidate_id}/withdraw")
async def withdraw_consent(
    candidate_id: str,
    body: WithdrawConsentBody,
    user: CurrentUser,
    supabase: SupabaseClient,
    request: Request,
):
    """Withdraw a specific consent type for a candidate."""
    supabase.table("data_consent_records").update({
        "withdrawn_at": datetime.utcnow().isoformat(),
    }).eq("candidate_id", candidate_id).eq("consent_type", body.consent_type).is_("withdrawn_at", "null").execute()

    await log_audit_action(
        supabase,
        actor_type="USER",
        actor_id=user.get("sub"),
        action="CONSENT_WITHDRAWN",
        entity_type="data_consent_records",
        entity_id=candidate_id,
        metadata={"consent_type": body.consent_type},
        ip=request.client.host if request.client else None,
    )
    return {"withdrawn": True}


@router.post("/erasure/request")
async def request_erasure(
    body: ErasureRequestBody,
    supabase: SupabaseClient,
    request: Request,
):
    """Public endpoint — candidate submits a GDPR right-to-erasure request."""
    result = supabase.table("erasure_requests").insert({
        "candidate_id": body.candidate_id,
        "status": "PENDING",
        "requested_at": datetime.utcnow().isoformat(),
    }).execute()

    req = result.data[0] if result.data else {}
    request_id = req.get("id")

    await log_audit_action(
        supabase,
        actor_type="CANDIDATE",
        actor_id=None,
        action="ERASURE_REQUEST_SUBMITTED",
        entity_type="erasure_requests",
        entity_id=str(request_id),
        metadata={"candidate_id": body.candidate_id, "requested_by_email": body.requested_by_email},
        ip=request.client.host if request.client else None,
    )
    return {"request_id": request_id}


@router.get("/erasure/requests")
async def list_erasure_requests(
    user: CurrentUser,
    supabase: SupabaseClient,
    status: Optional[str] = Query(None),
):
    """Return erasure requests, optionally filtered by status."""
    q = supabase.table("erasure_requests").select("*").order("requested_at", desc=True)
    if status:
        q = q.eq("status", status.upper())
    result = q.execute()
    return result.data or []


@router.post("/erasure/{request_id}/process")
async def process_erasure_request(
    request_id: str,
    body: ErasureProcessBody,
    user: CurrentUser,
    supabase: SupabaseClient,
    request: Request,
):
    """Approve or deny a GDPR erasure request."""
    req_result = supabase.table("erasure_requests").select("*").eq("id", request_id).execute()
    if not req_result.data:
        raise HTTPException(status_code=404, detail="Erasure request not found")

    erasure_req = req_result.data[0]
    candidate_id = erasure_req.get("candidate_id")
    action = body.action.lower()

    if action == "approve":
        # Anonymize candidate
        supabase.table("candidates").update({
            "first_name": "ANONYMIZED",
            "last_name": "DATA",
            "email": "anonymized@deleted.invalid",
            "phone": None,
            "data_status": "ANONYMIZED",
        }).eq("id", candidate_id).execute()

        supabase.table("erasure_requests").update({
            "status": "COMPLETED",
            "completed_at": datetime.utcnow().isoformat(),
            "processed_by": user.get("sub"),
        }).eq("id", request_id).execute()

        final_status = "COMPLETED"

    elif action == "deny":
        supabase.table("erasure_requests").update({
            "status": "DENIED",
            "denial_reason": body.denial_reason,
            "completed_at": datetime.utcnow().isoformat(),
            "processed_by": user.get("sub"),
        }).eq("id", request_id).execute()

        final_status = "DENIED"
    else:
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'deny'")

    await log_audit_action(
        supabase,
        actor_type="USER",
        actor_id=user.get("sub"),
        action=f"ERASURE_REQUEST_{final_status}",
        entity_type="erasure_requests",
        entity_id=request_id,
        metadata={"candidate_id": candidate_id, "action": action, "denial_reason": body.denial_reason},
        ip=request.client.host if request.client else None,
    )
    return {"status": final_status}


@router.post("/data-retention/process")
async def process_data_retention(
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """
    Stub: find candidates eligible for data retention processing.
    In production this would anonymize old inactive candidate records.
    """
    # Stub — returns 0 to avoid accidental mass anonymisation
    return {"processed": 0}


# ---------------------------------------------------------------------------
# EEO Endpoints
# ---------------------------------------------------------------------------

@router.post("/eeo/collect")
async def collect_eeo_data(
    body: EEOCollectBody,
    supabase: SupabaseClient,
    request: Request,
):
    """Public endpoint — voluntarily collect EEO demographic data."""
    row = {
        "candidate_id": body.candidate_id,
        "collected_at": datetime.utcnow().isoformat(),
    }
    if body.application_id:
        row["application_id"] = body.application_id
    if body.gender:
        row["gender"] = body.gender
    if body.ethnicity:
        row["ethnicity"] = body.ethnicity
    if body.disability_status:
        row["disability_status"] = body.disability_status
    if body.veteran_status:
        row["veteran_status"] = body.veteran_status

    supabase.table("eeo_data").insert(row).execute()

    await log_audit_action(
        supabase,
        actor_type="CANDIDATE",
        actor_id=None,
        action="EEO_DATA_COLLECTED",
        entity_type="eeo_data",
        entity_id=body.candidate_id,
        metadata={},
        ip=request.client.host if request.client else None,
    )
    return {"collected": True}


@router.get("/eeo/report")
async def get_eeo_report(
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """Return aggregated EEO report counts by gender and ethnicity."""
    result = supabase.table("eeo_data").select("gender,ethnicity").execute()
    rows = result.data or []

    by_gender: dict = {}
    by_ethnicity: dict = {}

    for r in rows:
        g = r.get("gender") or "Not disclosed"
        e = r.get("ethnicity") or "Not disclosed"
        by_gender[g] = by_gender.get(g, 0) + 1
        by_ethnicity[e] = by_ethnicity.get(e, 0) + 1

    return {"by_gender": by_gender, "by_ethnicity": by_ethnicity, "total": len(rows)}


@router.post("/eeo/report/export")
async def export_eeo_report(
    body: EEOExportBody,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """Export EEO data as a CSV file."""
    result = supabase.table("eeo_data").select("*").execute()
    rows = result.data or []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["candidate_id", "application_id", "gender", "ethnicity", "disability_status", "veteran_status", "collected_at"])
    for r in rows:
        writer.writerow([
            r.get("candidate_id", ""),
            r.get("application_id", ""),
            r.get("gender", ""),
            r.get("ethnicity", ""),
            r.get("disability_status", ""),
            r.get("veteran_status", ""),
            r.get("collected_at", ""),
        ])

    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=eeo_report_{body.year}.csv"},
    )


@router.patch("/jobs/{job_id}/blind-screening")
async def toggle_blind_screening(
    job_id: str,
    body: BlindScreeningBody,
    user: CurrentUser,
    supabase: SupabaseClient,
):
    """Enable or disable blind screening for a job posting (stub — no DB update required)."""
    # Optionally update the jobs table if it has a blind_screening column
    try:
        supabase.table("jobs").update({"blind_screening": body.enabled}).eq("id", job_id).execute()
    except Exception:
        pass  # best-effort — table/column may not exist yet
    return {"job_id": job_id, "enabled": body.enabled}
