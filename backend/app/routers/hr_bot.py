"""
WhatsApp HR Bot Router
Prefix: /api/v1/hr-bot

Endpoints:
  POST /webhook          — Twilio inbound WhatsApp webhook (public)
  GET  /sessions         — Active bot sessions (admin)
  GET  /leave-requests   — All leave requests (admin)
  PATCH /leave-requests/{id}/approve — Approve leave (admin)
  PATCH /leave-requests/{id}/reject  — Reject leave with reason (admin)
  POST /payslips         — Create/upload payslip (admin)
  GET  /payslips         — List payslips (admin)
  GET  /complaints       — List HR complaints (admin)
  PATCH /complaints/{id}/resolve — Resolve complaint (admin)
  POST /send             — Send WhatsApp message to employee (admin)
  GET  /stats            — Bot usage statistics (admin)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.dependencies import SupabaseAdminClient, SupabaseClient
from app.core.security import get_current_user
from app.services.hr_bot_service import (
    get_or_create_whatsapp_user,
    handle_whatsapp_message,
    log_inbound_message,
    log_outbound_message,
    resolve_employee,
    update_message_response,
)
from app.services.leave_service import review_leave_request
from app.services.rbac_service import authorize, build_access_context
from app.services.whatsapp_apply_service import handle_whatsapp_application

router = APIRouter(tags=["HR Bot"])
logger = logging.getLogger(__name__)

CurrentUser = Annotated[dict, Depends(get_current_user)]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_org(supabase, user: dict) -> str:
    res = supabase.table("users").select("org_id").eq("id", user["sub"]).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "User not found")
    return res.data[0]["org_id"]


def _send_whatsapp(to_phone: str, body: str) -> Optional[str]:
    """Send a WhatsApp reply via Twilio. Returns message SID or None."""
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        to = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone
        msg = client.messages.create(
            body=body,
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            to=to,
        )
        return msg.sid
    except Exception as exc:
        logger.warning("WhatsApp send failed to %s: %s", to_phone, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class ApproveLeaveRequest(BaseModel):
    notes: Optional[str] = None


class RejectLeaveRequest(BaseModel):
    rejection_reason: str


class ResolveComplaintRequest(BaseModel):
    resolution_notes: str


class CreatePayslipRequest(BaseModel):
    employee_id:          str
    month:                int   # 1-12
    year:                 int
    gross_salary_inr:     float
    net_salary_inr:       float
    basic_salary_inr:     Optional[float] = None
    hra_inr:              Optional[float] = 0
    da_inr:               Optional[float] = 0
    allowances_inr:       Optional[float] = 0
    overtime_inr:         Optional[float] = 0
    bonus_inr:            Optional[float] = 0
    epf_deduction_inr:    Optional[float] = 0
    esic_deduction_inr:   Optional[float] = 0
    professional_tax_inr: Optional[float] = 0
    tds_inr:              Optional[float] = 0
    other_deductions_inr: Optional[float] = 0
    paid_at:              Optional[str]   = None
    payment_method:       str             = "BANK_TRANSFER"
    payslip_pdf_url:      Optional[str]   = None
    working_days:         Optional[int]   = None
    present_days:         Optional[int]   = None
    absent_days:          Optional[int]   = None
    leave_days:           Optional[int]   = None


class SendMessageRequest(BaseModel):
    phone:   str
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# POST /webhook — Twilio inbound WhatsApp (public, no auth)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/webhook", response_class=PlainTextResponse)
async def whatsapp_webhook(
    supabase: SupabaseAdminClient,
    From: str    = Form(...),
    Body: str    = Form(...),
    MessageSid:  str = Form(default=""),
    NumMedia:    str = Form(default="0"),
):
    """
    Twilio inbound WhatsApp webhook.
    Processes employee commands and sends back a WhatsApp reply.

    Configure in Twilio Console:
      Messaging → WhatsApp → Sandbox → When a message comes in:
      https://your-api-domain.com/api/v1/hr-bot/webhook  (HTTP POST)
    """
    logger.info("HR Bot inbound: from=%s sid=%s body=%r", From, MessageSid, Body[:80])

    # Ignore media-only messages gracefully
    if not Body.strip() and int(NumMedia or 0) > 0:
        reply = "🤖 HospBot: I can only process text commands. Please type HELP to see available commands."
        inbound_id = log_inbound_message(
            supabase, From, None, None, "[media message]", MessageSid,
            "UNKNOWN", "media",
        )
        update_message_response(supabase, inbound_id, reply)
    else:
        phone = From.replace("whatsapp:", "")
        reply = handle_whatsapp_application(supabase, phone, Body)
        if reply is not None:
            employee = resolve_employee(supabase, phone)
            wu_id = get_or_create_whatsapp_user(supabase, phone, employee)
            inbound_id = log_inbound_message(
                supabase, phone, employee, wu_id, Body, MessageSid, "APPLY", Body,
            )
            update_message_response(supabase, inbound_id, reply)
        else:
            inbound_id = None
            reply = handle_whatsapp_message(supabase, From, Body, twilio_sid=MessageSid)

    # Send WhatsApp reply
    to_phone = From if From.startswith("whatsapp:") else f"whatsapp:{From}"
    outbound_sid = _send_whatsapp(to_phone, reply)
    log_outbound_message(
        supabase, From, reply, outbound_sid, provider="twilio",
        inbound_message_id=inbound_id,
    )

    # Twilio expects empty 200 OK (we sent the reply programmatically above)
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# GET /sessions — active bot sessions (admin)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    supabase: SupabaseClient,
    user:     CurrentUser,
    limit:    int = Query(50, ge=1, le=200),
):
    """List active WhatsApp bot sessions for this org."""
    org_id = _get_org(supabase, user)
    res = (
        supabase.table("hr_bot_sessions")
        .select("phone, employee_id, last_command, last_message_at, message_count")
        .eq("org_id", org_id)
        .eq("is_active", True)
        .order("last_message_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ─────────────────────────────────────────────────────────────────────────────
# Leave requests (admin view)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/leave-requests")
async def list_leave_requests(
    supabase: SupabaseClient,
    user:     CurrentUser,
    status:   Optional[str] = Query(None),
    limit:    int           = Query(50, ge=1, le=200),
):
    """List all leave requests for the org (admin)."""
    context = build_access_context(supabase, user)
    authorize(context, "leave.read")
    org_id = context.org_id
    q = (
        supabase.table("leave_requests")
        .select("id, employee_id, leave_date, leave_type, reason, status, "
                "ticket_number, approved_by, approved_at, rejection_reason, created_at")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        q = q.eq("status", status.upper())
    return q.execute().data or []


@router.patch("/leave-requests/{request_id}/approve")
async def approve_leave(
    request_id: str,
    body:       ApproveLeaveRequest,
    supabase:   SupabaseClient,
    user:       CurrentUser,
):
    """Approve a leave request and notify employee via WhatsApp."""
    context = build_access_context(supabase, user)
    authorize(context, "leave.manage")
    org_id  = context.org_id

    req_res = (
        supabase.table("leave_requests")
        .select("*")
        .eq("id", request_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not req_res.data:
        raise HTTPException(404, "Leave request not found")

    req = req_res.data[0]
    if req["status"] != "PENDING":
        raise HTTPException(409, f"Request already {req['status'].lower()}")

    saved = review_leave_request(supabase, request=req, actor_id=context.user_id,
                                 actor_role=context.role, action="APPROVE", note=body.notes)

    # Notify employee
    _notify_employee_leave(supabase, req, "APPROVED" if saved.get("status") == "APPROVED" else "PENDING_HR", body.notes)

    return {"approved": saved.get("status") == "APPROVED", "request_id": request_id, "request": saved}


@router.patch("/leave-requests/{request_id}/reject")
async def reject_leave(
    request_id: str,
    body:       RejectLeaveRequest,
    supabase:   SupabaseClient,
    user:       CurrentUser,
):
    """Reject a leave request and notify employee via WhatsApp."""
    context = build_access_context(supabase, user)
    authorize(context, "leave.manage")
    org_id  = context.org_id

    req_res = (
        supabase.table("leave_requests")
        .select("*")
        .eq("id", request_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not req_res.data:
        raise HTTPException(404, "Leave request not found")

    req = req_res.data[0]
    if req["status"] != "PENDING":
        raise HTTPException(409, f"Request already {req['status'].lower()}")

    saved = review_leave_request(supabase, request=req, actor_id=context.user_id,
                                 actor_role=context.role, action="REJECT", note=body.rejection_reason)

    _notify_employee_leave(supabase, req, "REJECTED", body.rejection_reason)

    return {"rejected": True, "request_id": request_id, "request": saved}


# ─────────────────────────────────────────────────────────────────────────────
# Payslips (admin upload + employee view)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/payslips", status_code=201)
async def create_payslip(
    body:     CreatePayslipRequest,
    supabase: SupabaseClient,
    user:     CurrentUser,
):
    """Upload a payslip for an employee (HR admin). Notifies via WhatsApp."""
    org_id = _get_org(supabase, user)
    now    = datetime.utcnow().isoformat()

    payload = {
        "org_id":               org_id,
        "employee_id":          body.employee_id,
        "month":                body.month,
        "year":                 body.year,
        "gross_salary_inr":     body.gross_salary_inr,
        "net_salary_inr":       body.net_salary_inr,
        "basic_salary_inr":     body.basic_salary_inr,
        "hra_inr":              body.hra_inr or 0,
        "da_inr":               body.da_inr or 0,
        "allowances_inr":       body.allowances_inr or 0,
        "overtime_inr":         body.overtime_inr or 0,
        "bonus_inr":            body.bonus_inr or 0,
        "epf_deduction_inr":    body.epf_deduction_inr or 0,
        "esic_deduction_inr":   body.esic_deduction_inr or 0,
        "professional_tax_inr": body.professional_tax_inr or 0,
        "tds_inr":              body.tds_inr or 0,
        "other_deductions_inr": body.other_deductions_inr or 0,
        "paid_at":              body.paid_at,
        "payment_method":       body.payment_method,
        "payslip_pdf_url":      body.payslip_pdf_url,
        "working_days":         body.working_days,
        "present_days":         body.present_days,
        "absent_days":          body.absent_days,
        "leave_days":           body.leave_days,
        "created_at":           now,
    }

    res = supabase.table("payslips").insert(payload).execute()
    if not res.data:
        raise HTTPException(500, "Failed to create payslip")

    # Notify employee: payslip ready
    _notify_payslip_ready(supabase, body.employee_id, body.month, body.year)

    return res.data[0]


@router.get("/payslips")
async def list_payslips(
    supabase:    SupabaseClient,
    user:        CurrentUser,
    employee_id: Optional[str] = Query(None),
    month:       Optional[int] = Query(None),
    year:        Optional[int] = Query(None),
    limit:       int           = Query(50, ge=1, le=200),
):
    """List payslips (admin: all org; filtered by employee/month/year)."""
    org_id = _get_org(supabase, user)
    q = (
        supabase.table("payslips")
        .select("id, employee_id, month, year, gross_salary_inr, net_salary_inr, "
                "paid_at, payment_method, payslip_pdf_url, created_at")
        .eq("org_id", org_id)
        .order("year", desc=True)
        .order("month", desc=True)
        .limit(limit)
    )
    if employee_id:
        q = q.eq("employee_id", employee_id)
    if month:
        q = q.eq("month", month)
    if year:
        q = q.eq("year", year)
    return q.execute().data or []


# ─────────────────────────────────────────────────────────────────────────────
# Complaints (admin)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/complaints")
async def list_complaints(
    supabase: SupabaseClient,
    user:     CurrentUser,
    status:   Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit:    int           = Query(50, ge=1, le=200),
):
    """
    List HR complaints for this org.
    Uses v_hr_complaints_display — anonymous reporters appear as
    'Anonymous Reporter' (Req 3: identity hidden from normal managers).
    """
    org_id = _get_org(supabase, user)
    q = (
        supabase.table("v_hr_complaints_display")
        .select(
            "id, ticket_number, category, severity, status, source, "
            "reporter_display, reporter_employee_id, is_anonymous, "
            "sla_status, days_open, sla_deadline, sla_breached, "
            "assigned_to, resolution_notes, resolved_at, "
            "identity_view_count, created_at, updated_at"
        )
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        q = q.eq("status", status.upper())
    if category:
        q = q.eq("category", category.upper())
    return q.execute().data or []


@router.patch("/complaints/{complaint_id}/resolve")
async def resolve_complaint(
    complaint_id: str,
    body:         ResolveComplaintRequest,
    supabase:     SupabaseClient,
    user:         CurrentUser,
):
    """Mark a complaint as resolved and notify the reporter via WhatsApp."""
    raise HTTPException(410, "Use POST /api/v1/grievances/cases/{id}/resolve so investigation, authorization and access auditing are enforced")
    org_id = _get_org(supabase, user)
    now    = datetime.utcnow().isoformat()

    # Read from hr_complaints (authoritative table from migration 022)
    comp_res = (
        supabase.table("hr_complaints")
        .select("*")
        .eq("id", complaint_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not comp_res.data:
        raise HTTPException(404, "Complaint not found")

    comp = comp_res.data[0]
    supabase.table("hr_complaints").update({
        "status":           "RESOLVED",
        "resolution_notes": body.resolution_notes,
        "resolved_at":      now,
        "updated_at":       now,
    }).eq("id", complaint_id).execute()

    _notify_complaint_resolved(supabase, comp, body.resolution_notes)

    return {"resolved": True, "complaint_id": complaint_id}


# ─────────────────────────────────────────────────────────────────────────────
# GET /complaints/{id}/identity — reveal identity (privileged only, Req 4)
# ─────────────────────────────────────────────────────────────────────────────

_PRIVILEGED_ROLES = frozenset({"hr_admin", "super_admin", "admin"})


@router.get("/complaints/{complaint_id}/identity")
async def get_complaint_identity(
    complaint_id: str,
    supabase:     SupabaseClient,
    user:         CurrentUser,
    purpose:      Optional[str] = Query(
        None,
        description="Reason for accessing reporter identity (required for audit).",
    ),
):
    """
    Req 4 — Reveal the real identity behind a complaint (including anonymous ones).

    Access control:
      • Only users with role hr_admin, super_admin, or admin may call this.
      • All other roles receive HTTP 403.
      • Every successful access is permanently recorded in
        complaint_identity_views for compliance audit.

    Anonymity is not broken silently:
      • The reporter was told that only HR Admin can access their identity.
      • This endpoint exists to honour that promise under controlled conditions.
    """
    raise HTTPException(
        410,
        "Use GET /api/v1/grievances/cases/{complaint_id}/identity with a purpose. "
        "The legacy identity endpoint is retired.",
    )
    if not purpose or len(purpose.strip()) < 10:
        raise HTTPException(422, "A specific identity-access purpose of at least 10 characters is required")
    context = build_access_context(supabase, user)
    org_id  = context.org_id
    user_id = user["sub"]
    now     = datetime.utcnow().isoformat()

    # ── Role check ────────────────────────────────────────────────────────────
    user_role = context.role
    assigned = supabase.table("complaint_case_members").select("id").eq(
        "complaint_id", complaint_id).eq("user_id", user_id).eq("can_view_identity", True).is_("revoked_at", "null").limit(1).execute()
    if not assigned.data:
        raise HTTPException(403, "Reporter identity requires an explicit complaint assignment")

    # ── Fetch complaint ───────────────────────────────────────────────────────
    comp_res = (
        supabase.table("hr_complaints")
        .select(
            "id, employee_id, phone, is_anonymous, ticket_number, "
            "category, severity, status, created_at"
        )
        .eq("id", complaint_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not comp_res.data:
        raise HTTPException(404, "Complaint not found")

    comp = comp_res.data[0]

    # ── Audit log — always written before returning data ─────────────────────
    try:
        supabase.table("complaint_identity_views").insert({
            "org_id":        org_id,
            "complaint_id":  complaint_id,
            "ticket_number": comp.get("ticket_number"),
            "is_anonymous":  comp.get("is_anonymous"),
            "viewed_by":     user_id,
            "viewer_role":   user_role,
            "purpose":       purpose,
            "viewed_at":     now,
        }).execute()
    except Exception as exc:
        logger.error("Audit log write failed for identity access: %s", exc)
        raise HTTPException(503, "Identity access denied because audit logging is unavailable") from exc

    # ── Fetch employee details ────────────────────────────────────────────────
    employee_id   = comp.get("employee_id")
    employee_info = None
    if employee_id:
        try:
            emp_res = (
                supabase.table("users")
                .select("id, email, phone")
                .eq("id", employee_id)
                .limit(1)
                .execute()
            )
            if emp_res.data:
                employee_info = emp_res.data[0]
        except Exception:
            pass

    return {
        "complaint_id":  complaint_id,
        "ticket_number": comp.get("ticket_number"),
        "is_anonymous":  comp.get("is_anonymous"),
        "category":      comp.get("category"),
        "severity":      comp.get("severity"),
        "status":        comp.get("status"),
        "filed_at":      comp.get("created_at"),
        # Identity fields
        "employee_id":   employee_id,
        "employee_info": employee_info,
        "phone":         comp.get("phone"),
        # Access metadata
        "accessed_by":   user_id,
        "accessor_role": user_role,
        "accessed_at":   now,
        "purpose":       purpose,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /complaints/track/{token} — anonymous complaint status (no auth)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/complaints/track/{token}")
async def track_anonymous_complaint(token: str, supabase: SupabaseClient):
    """
    Public endpoint — lets an anonymous reporter check their complaint status
    using the 40-char token returned at submission time. No auth required.
    """
    res = (
        supabase.table("hr_complaints")
        .select("ticket_number, status, category, severity, sla_deadline, "
                "created_at, resolved_at, resolution_notes")
        .eq("anonymous_token", token)
        .eq("is_anonymous", True)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "No complaint found for this token")

    c = res.data[0]
    return {
        "ticket_number":   c["ticket_number"],
        "status":          c["status"],
        "category":        c["category"],
        "severity":        c["severity"],
        "sla_deadline":    c["sla_deadline"],
        "filed_at":        c["created_at"],
        "resolved_at":     c["resolved_at"],
        "resolution_notes": c["resolution_notes"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /whatsapp-users — registered WhatsApp users (admin)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/whatsapp-users")
async def list_whatsapp_users(
    supabase: SupabaseClient,
    user:     CurrentUser,
    limit:    int = Query(50, ge=1, le=200),
    verified: Optional[bool] = Query(None),
):
    """List registered WhatsApp users for this org."""
    org_id = _get_org(supabase, user)
    q = (
        supabase.table("whatsapp_users")
        .select("phone, display_name, employee_id, is_verified, is_active, "
                "opt_out, last_message_at, message_count, last_command, created_at")
        .eq("org_id", org_id)
        .order("last_message_at", desc=True)
        .limit(limit)
    )
    if verified is not None:
        q = q.eq("is_verified", verified)
    return q.execute().data or []


# ─────────────────────────────────────────────────────────────────────────────
# GET /messages — message audit log (admin)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/messages")
async def list_messages(
    supabase: SupabaseClient,
    user:     CurrentUser,
    phone:    Optional[str] = Query(None),
    command:  Optional[str] = Query(None),
    limit:    int           = Query(100, ge=1, le=500),
):
    """Full WhatsApp message audit log for this org (admin)."""
    org_id = _get_org(supabase, user)
    q = (
        supabase.table("whatsapp_messages")
        .select("id, phone, direction, body, command, command_status, "
                "response_body, twilio_sid, created_at")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if phone:
        q = q.eq("phone", phone.replace("whatsapp:", "").strip())
    if command:
        q = q.eq("command", command.upper())
    return q.execute().data or []


# ─────────────────────────────────────────────────────────────────────────────
# GET /payslip-requests — payslip request log (admin)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/payslip-requests")
async def list_payslip_requests(
    supabase:    SupabaseClient,
    user:        CurrentUser,
    status:      Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    limit:       int           = Query(50, ge=1, le=200),
):
    """List payslip requests filed via the WhatsApp bot (admin)."""
    org_id = _get_org(supabase, user)
    q = (
        supabase.table("payslip_requests")
        .select("id, employee_id, requested_month, requested_year, "
                "status, fulfilled_at, payslip_id, source, created_at")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        q = q.eq("status", status.upper())
    if employee_id:
        q = q.eq("employee_id", employee_id)
    return q.execute().data or []


# ─────────────────────────────────────────────────────────────────────────────
# POST /send — admin sends WhatsApp to employee
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/send")
async def send_to_employee(
    body:     SendMessageRequest,
    supabase: SupabaseClient,
    user:     CurrentUser,
):
    """Send a WhatsApp message to an employee from HR admin."""
    _get_org(supabase, user)
    sid = _send_whatsapp(body.phone, body.message)
    return {"sent": sid is not None, "sid": sid}


# ─────────────────────────────────────────────────────────────────────────────
# GET /stats — bot usage statistics
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def bot_stats(supabase: SupabaseClient, user: CurrentUser):
    """Return summary statistics for the HR Bot (admin)."""
    org_id = _get_org(supabase, user)

    def _count(table: str, filters: dict) -> int:
        q = supabase.table(table).select("id", count="exact")
        for k, v in filters.items():
            q = q.eq(k, v)
        res = q.execute()
        return res.count or 0

    return {
        "active_sessions":         _count("hr_bot_sessions",   {"org_id": org_id, "is_active": True}),
        "leave_requests_pending":  _count("leave_requests",    {"org_id": org_id, "status": "PENDING"}),
        "leave_requests_total":    _count("leave_requests",    {"org_id": org_id}),
        "complaints_open":         _count("employee_complaints",{"org_id": org_id, "status": "OPEN"}),
        "complaints_total":        _count("employee_complaints",{"org_id": org_id}),
        "payslips_this_month":     _count("payslips",          {
            "org_id": org_id,
            "month":  datetime.utcnow().month,
            "year":   datetime.utcnow().year,
        }),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /dashboard — single-call aggregation for the admin dashboard
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def bot_dashboard(supabase: SupabaseClient, user: CurrentUser):
    """
    All data the WhatsApp HR Bot admin dashboard needs in one request.

    Returns:
      stats           — headline counts for stat cards
      commands_today  — per-command count for today (INBOUND messages)
      failed_today    — recent UNKNOWN / FAILED messages
      unregistered    — phone numbers that messaged but aren't in the system
    """
    from collections import Counter, defaultdict

    org_id  = _get_org(supabase, user)
    today   = datetime.utcnow().date().isoformat()

    # ── Helper: count with filters ────────────────────────────────────────────
    def _count(table: str, **filters: str) -> int:
        q = supabase.table(table).select("id", count="exact")
        for k, v in filters.items():
            q = q.eq(k, v)
        try:
            return q.execute().count or 0
        except Exception:
            return 0

    # ── Headline stats ────────────────────────────────────────────────────────
    total_whatsapp_users = _count("whatsapp_users", org_id=org_id)
    unverified_users     = _count("whatsapp_users", org_id=org_id, is_verified=False)
    leave_pending        = _count("leave_requests", org_id=org_id, status="PENDING")
    leave_total          = _count("leave_requests", org_id=org_id)
    complaints_open      = _count("hr_complaints",  org_id=org_id, status="OPEN")
    complaints_total     = _count("hr_complaints",  org_id=org_id)
    anon_complaints      = _count("hr_complaints",  org_id=org_id, is_anonymous=True)
    payslips_month       = _count("payslips", org_id=org_id,
                                  month=str(datetime.utcnow().month),
                                  year=str(datetime.utcnow().year))

    payslip_req_pending   = _count("payslip_requests", org_id=org_id, status="PENDING")
    payslip_req_fulfilled = _count("payslip_requests", org_id=org_id, status="FULFILLED")
    payslip_req_not_found = _count("payslip_requests", org_id=org_id, status="NOT_FOUND")

    # ── Today's inbound messages ──────────────────────────────────────────────
    try:
        msg_res = (
            supabase.table("whatsapp_messages")
            .select("command, command_status, phone, body, created_at")
            .eq("org_id", org_id)
            .eq("direction", "INBOUND")
            .gte("created_at", today)
            .limit(1000)
            .execute()
        )
        messages_today = msg_res.data or []
    except Exception:
        messages_today = []

    # Per-command counts
    cmd_counts: dict[str, int] = Counter(
        (m.get("command") or "UNKNOWN") for m in messages_today
    )
    commands_today = {
        cmd: cmd_counts.get(cmd, 0)
        for cmd in ("LEAVE", "PAYSLIP", "SHIFT", "BALANCE",
                    "COMPLAINT", "CAREER", "HELP", "UNKNOWN")
    }
    commands_today["total"] = sum(commands_today.values())

    failed_today = int(cmd_counts.get("UNKNOWN", 0))

    # Recent failed/unrecognised messages (last 10)
    failed_messages = [
        {
            "phone":      m["phone"],
            "body":       (m.get("body") or "")[:60],
            "created_at": m["created_at"],
        }
        for m in messages_today
        if m.get("command") == "UNKNOWN" or m.get("command_status") == "FAILED"
    ][-10:]

    # Unregistered phone numbers (messaged but not in system)
    unreg_msgs = [m for m in messages_today if m.get("command_status") == "UNREGISTERED"]
    phone_groups: dict[str, list] = defaultdict(list)
    for m in unreg_msgs:
        phone_groups[m["phone"]].append(m["created_at"])
    unregistered = [
        {
            "phone":        phone,
            "attempts":     len(times),
            "last_attempt": max(times),
        }
        for phone, times in sorted(
            phone_groups.items(), key=lambda x: max(x[1]), reverse=True
        )
    ][:10]

    return {
        "stats": {
            "total_whatsapp_users": total_whatsapp_users,
            "unverified_users":     unverified_users,
            "leave_pending":        leave_pending,
            "leave_total":          leave_total,
            "complaints_open":      complaints_open,
            "complaints_total":     complaints_total,
            "anon_complaints":      anon_complaints,
            "payslips_this_month":  payslips_month,
            "payslip_req_pending":  payslip_req_pending,
            "payslip_req_fulfilled":payslip_req_fulfilled,
            "payslip_req_not_found":payslip_req_not_found,
        },
        "commands_today":  commands_today,
        "failed_today":    failed_today,
        "failed_messages": failed_messages,
        "unregistered":    unregistered,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal notification helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_employee_phone(supabase, employee_id: str) -> Optional[str]:
    try:
        res = (
            supabase.table("users")
            .select("phone")
            .eq("id", employee_id)
            .limit(1)
            .execute()
        )
        if res.data and res.data[0].get("phone"):
            return res.data[0]["phone"]
    except Exception:
        pass
    return None


def _notify_employee_leave(supabase, req: dict, decision: str, notes: Optional[str]) -> None:
    phone = _get_employee_phone(supabase, req["employee_id"])
    if not phone:
        return

    date_str = req.get("leave_date", "")
    ticket   = req.get("ticket_number", "")

    if decision == "APPROVED":
        msg = (
            f"🤖 HospBot ✅ Leave Approved!\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🎫 Ticket: {ticket}\n"
            f"📅 Date:   {date_str}\n"
            f"✅ Status: Approved\n"
        )
        if notes:
            msg += f"📝 Note: {notes}\n"
    elif decision == "PENDING_HR":
        msg = (
            f"🤖 HospBot ⏳ Manager Approved — HR Review Pending\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🎫 Ticket: {ticket}\n"
            f"📅 Date:   {date_str}\n"
            f"Your manager approved the request. HR final approval is still required.\n"
            f"प्रबंधक की मंजूरी मिल गई है; HR की अंतिम मंजूरी बाकी है।"
        )
    else:
        msg = (
            f"🤖 HospBot ❌ Leave Rejected\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🎫 Ticket: {ticket}\n"
            f"📅 Date:   {date_str}\n"
            f"❌ Status: Rejected\n"
            f"📝 Reason: {notes or 'Contact HR for details'}\n\n"
            f"You can apply for another date using: LEAVE [date] [reason]"
        )

    _send_whatsapp(phone, msg)


def _notify_payslip_ready(supabase, employee_id: str, month: int, year: int) -> None:
    phone = _get_employee_phone(supabase, employee_id)
    if not phone:
        return

    month_name = {
        1:"January",2:"February",3:"March",4:"April",5:"May",6:"June",
        7:"July",8:"August",9:"September",10:"October",11:"November",12:"December"
    }.get(month, str(month))

    msg = (
        f"🤖 HospBot 💰 Payslip Ready!\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Your payslip for {month_name} {year} is ready.\n"
        f"Type *PAYSLIP {month_name}* to view it.\n\n"
        f"आपका {month_name} {year} का वेतन पर्ची तैयार है।"
    )
    _send_whatsapp(phone, msg)


def _notify_complaint_resolved(supabase, comp: dict, notes: str) -> None:
    """
    Notify the reporter that their complaint has been resolved.
    Works for both named and anonymous complaints:
      - Named: look up phone via employee_id
      - Anonymous: use comp["phone"] directly (always stored, even for anon)
    Identity is NOT revealed to the reporter — only ticket + resolution shown.
    """
    phone = None

    # Named complaint: look up via employee_id
    employee_id = comp.get("employee_id")
    if employee_id:
        phone = _get_employee_phone(supabase, employee_id)

    # Anonymous complaint (or named where user has no phone in users table):
    # use the phone stored on the complaint row
    if not phone:
        phone = comp.get("phone")

    if not phone:
        logger.warning(
            "Cannot notify complaint resolved: no phone for ticket %s",
            comp.get("ticket_number"),
        )
        return

    ticket = comp.get("ticket_number", "")
    msg = (
        f"🤖 HospBot ✅ Complaint Resolved\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🎫 Ticket:     {ticket}\n"
        f"✅ Status:     Resolved\n"
        f"📝 Resolution: {notes[:200]}\n\n"
        f"If you have further concerns, type COMPLAINT [your message].\n"
        f"अगर और कोई समस्या हो, तो COMPLAINT [संदेश] टाइप करें।"
    )
    _send_whatsapp(phone, msg)
