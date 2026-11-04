"""
WhatsApp HR Bot Service — HospRecruit India

Handles all seven employee self-service commands via WhatsApp.
Employees are identified by their registered phone number — no app needed.

Commands:
  LEAVE   [date] [reason]   — Submit a leave request
  PAYSLIP [month]           — View payslip summary
  SHIFT                     — View upcoming shifts
  BALANCE                   — Check leave balance
  COMPLAINT [text]          — File an HR complaint (prefix ANON for anonymous)
  CAREER                    — Browse internal job openings
  HELP                      — Command reference (English + Hindi)

Phone lookup order:
  1. whatsapp_users (canonical registry, migration 022)
  2. users.phone (platform users)
  3. candidates.phone (hired candidates not yet in users)

All messages logged to whatsapp_messages for full audit trail.
Complaints written to hr_complaints (supports anonymous via ANON prefix).
Payslip queries logged to payslip_requests.
"""

from __future__ import annotations

import logging
import random
import re
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

BOT_NAME = "🤖 HospBot"

MONTH_MAP = {
    "january": 1, "jan": 1, "february": 2, "feb": 2,
    "march": 3, "mar": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

MONTH_NAME = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

LEAVE_TYPES = {"casual", "sick", "emergency", "earned"}


# ─────────────────────────────────────────────────────────────────────────────
# Ticket generators
# ─────────────────────────────────────────────────────────────────────────────

def _gen_leave_ticket() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"LV-{datetime.utcnow().strftime('%Y%m%d')}-{suffix}"


def _gen_complaint_ticket() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"HR-{datetime.utcnow().strftime('%Y%m%d')}-{suffix}"


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_inr(amount: float) -> str:
    """Format number as Indian currency: ₹1,23,456"""
    if amount is None:
        return "₹—"
    amount = float(amount)
    s = f"{amount:,.2f}".rstrip("0").rstrip(".")
    return f"₹{s}"


def _fmt_date(date_str: str) -> str:
    try:
        d = datetime.fromisoformat(str(date_str))
        return d.strftime("%a, %d %b %Y")
    except Exception:
        return str(date_str)


def _divider() -> str:
    return "━━━━━━━━━━━━━━━━━"


# ─────────────────────────────────────────────────────────────────────────────
# Command parser — delegated to command_parser module
# ─────────────────────────────────────────────────────────────────────────────

from app.services.command_parser import (         # noqa: E402
    parse_command as _structured_parse,
    ParsedCommand,
    infer_leave_type   as _infer_leave_type,
    infer_complaint_category as _infer_complaint_category,
    infer_complaint_severity as _infer_complaint_severity,
    parse_date_arg     as _parse_date,
    parse_month_arg    as _parse_month_arg,
    MONTH_MAP,
)
from app.services.employee_engagement_service import submit_pulse_response  # noqa: E402


def parse_command(text: str) -> tuple[str, list[str]]:
    """
    Backward-compatible wrapper.
    Delegates to the structured parser and returns (COMMAND, args_list).
    New code should call command_parser.parse_command() directly for the
    full ParsedCommand output with validation and Hindi support.
    """
    result = _structured_parse(text)
    return result.command, result.args


# ─────────────────────────────────────────────────────────────────────────────
# Employee lookup
# ─────────────────────────────────────────────────────────────────────────────

def resolve_employee(supabase, phone: str) -> Optional[dict]:
    """
    Find employee by phone number.
    Lookup order:
      1. whatsapp_users (canonical registry — migration 022)
      2. users.phone (platform users)
      3. candidates.phone (hired candidates not yet in users)
    Returns: {employee_id, org_id, name, source, whatsapp_user_id} or None.
    """
    clean = phone.replace("whatsapp:", "").strip()
    variants = [clean]
    if clean.startswith("+91"):
        variants.append(clean[3:])
    elif not clean.startswith("+"):
        variants.append(f"+91{clean.lstrip('0')}")

    for ph in variants:
        # 1. whatsapp_users — fastest; already verified and linked
        try:
            res = (
                supabase.table("whatsapp_users")
                .select("id, employee_id, org_id, display_name, opt_out")
                .eq("phone", ph)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            if res.data:
                wu = res.data[0]
                if wu.get("opt_out"):
                    return None  # employee has opted out of bot
                if wu.get("employee_id"):
                    return {
                        "employee_id":      wu["employee_id"],
                        "org_id":           wu["org_id"],
                        "name":             wu.get("display_name") or "Employee",
                        "source":           "whatsapp_users",
                        "phone":            clean,
                        "whatsapp_user_id": wu["id"],
                    }
        except Exception as exc:
            logger.debug("whatsapp_users lookup failed: %s", exc)

        # 2. users table
        try:
            res = (
                supabase.table("users")
                .select("id, org_id, email, phone")
                .eq("phone", ph)
                .limit(1)
                .execute()
            )
            if res.data:
                u = res.data[0]
                return {
                    "employee_id":      u["id"],
                    "org_id":           u["org_id"],
                    "name":             u.get("email", "Employee").split("@")[0].title(),
                    "source":           "users",
                    "phone":            clean,
                    "whatsapp_user_id": None,
                }
        except Exception as exc:
            logger.debug("users lookup failed: %s", exc)

        # 3. candidates table
        try:
            res = (
                supabase.table("candidates")
                .select("id, org_id, first_name, last_name, phone")
                .eq("phone", ph)
                .in_("pipeline_stage", ["hired", "offer_accepted", "joined", "onboarded"])
                .limit(1)
                .execute()
            )
            if res.data:
                c = res.data[0]
                return {
                    "employee_id":      c["id"],
                    "org_id":           c["org_id"],
                    "name":             f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or "Employee",
                    "source":           "candidates",
                    "phone":            clean,
                    "whatsapp_user_id": None,
                }
        except Exception as exc:
            logger.debug("candidates lookup failed: %s", exc)

    return None


def get_or_create_whatsapp_user(supabase, phone: str, employee: Optional[dict]) -> Optional[str]:
    """
    Upsert a whatsapp_users row (migration 022) and return its UUID.
    Also keeps the legacy hr_bot_sessions row in sync for backward compat.
    """
    clean = phone.replace("whatsapp:", "").strip()
    wu_id: Optional[str] = employee.get("whatsapp_user_id") if employee else None

    try:
        now = datetime.utcnow().isoformat()
        row: dict = {
            "phone":           clean,
            "last_message_at": now,
        }
        if employee:
            row["employee_id"]  = employee["employee_id"]
            row["org_id"]       = employee["org_id"]
            row["display_name"] = employee.get("name")
            row["is_verified"]  = True

        existing = (
            supabase.table("whatsapp_users")
            .select("id, message_count")
            .eq("phone", clean)
            .limit(1)
            .execute()
        )
        if existing.data:
            wu_id = existing.data[0]["id"]
            count = (existing.data[0].get("message_count") or 0) + 1
            supabase.table("whatsapp_users").update(
                {**row, "message_count": count}
            ).eq("id", wu_id).execute()
        else:
            res = supabase.table("whatsapp_users").insert(
                {**row, "message_count": 1, "first_message_at": now}
            ).execute()
            if res.data:
                wu_id = res.data[0]["id"]
    except Exception as exc:
        logger.debug("whatsapp_users upsert failed: %s", exc)

    # Keep legacy hr_bot_sessions in sync
    _sync_legacy_session(supabase, clean, employee)
    return wu_id


def _sync_legacy_session(supabase, phone: str, employee: Optional[dict]) -> None:
    """Keep hr_bot_sessions (migration 021) in sync for backward compatibility."""
    try:
        now = datetime.utcnow().isoformat()
        row: dict = {"phone": phone, "last_message_at": now}
        if employee:
            row["employee_id"] = employee["employee_id"]
            row["org_id"]      = employee["org_id"]

        existing = (
            supabase.table("hr_bot_sessions")
            .select("id, message_count")
            .eq("phone", phone)
            .limit(1)
            .execute()
        )
        if existing.data:
            count = (existing.data[0].get("message_count") or 0) + 1
            supabase.table("hr_bot_sessions").update(
                {**row, "message_count": count}
            ).eq("phone", phone).execute()
        else:
            supabase.table("hr_bot_sessions").insert(
                {**row, "message_count": 1}
            ).execute()
    except Exception as exc:
        logger.debug("hr_bot_sessions sync failed: %s", exc)


# kept for external callers that still reference the old name
def get_or_create_session(supabase, phone: str, employee: Optional[dict]) -> None:
    get_or_create_whatsapp_user(supabase, phone, employee)


def log_inbound_message(
    supabase,
    phone: str,
    employee: Optional[dict],
    wu_id: Optional[str],
    body: str,
    twilio_sid: str,
    command: str,
    command_args: str,
) -> Optional[str]:
    """
    Write one INBOUND row to whatsapp_messages.
    Returns the new row UUID (used to link the response later).
    """
    try:
        res = supabase.table("whatsapp_messages").insert({
            "org_id":           employee["org_id"] if employee else None,
            "whatsapp_user_id": wu_id,
            "phone":            phone.replace("whatsapp:", "").strip(),
            "direction":        "INBOUND",
            "body":             body,
            "twilio_sid":       twilio_sid or None,
            "command":          command if command != "UNKNOWN" else "UNKNOWN",
            "command_args":     command_args,
            "command_status":   "PROCESSED" if employee else "UNREGISTERED",
            "source":           "WHATSAPP",
            "processed_at":     datetime.utcnow().isoformat(),
            "created_at":       datetime.utcnow().isoformat(),
        }).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as exc:
        logger.debug("whatsapp_messages insert failed: %s", exc)
        return None


def update_message_response(
    supabase,
    message_id: Optional[str],
    response_body: str,
    command_status: str = "PROCESSED",
    error_message: Optional[str] = None,
) -> None:
    """Patch the inbound message row with the bot's response text."""
    if not message_id:
        return
    try:
        supabase.table("whatsapp_messages").update({
            "response_body":  response_body,
            "command_status": command_status,
            "error_message":  error_message,
        }).eq("id", message_id).execute()
    except Exception as exc:
        logger.debug("whatsapp_messages update failed: %s", exc)


def log_outbound_message(
    supabase,
    phone: str,
    body: str,
    provider_message_id: Optional[str],
    *,
    provider: str,
    inbound_message_id: Optional[str] = None,
) -> Optional[str]:
    """Persist an immutable outbound audit row and link it to its inbound command."""
    employee = resolve_employee(supabase, phone)
    clean = phone.replace("whatsapp:", "").strip()
    wu_id = employee.get("whatsapp_user_id") if employee else None
    if employee and not wu_id:
        try:
            found = (supabase.table("whatsapp_users").select("id").eq("phone", clean)
                     .limit(1).execute())
            wu_id = found.data[0]["id"] if found.data else None
        except Exception:
            wu_id = None
    status = "SENT" if provider_message_id else "FAILED"
    try:
        saved = supabase.table("whatsapp_messages").insert({
            "org_id": employee.get("org_id") if employee else None,
            "whatsapp_user_id": wu_id,
            "phone": clean,
            "direction": "OUTBOUND",
            "body": body,
            "twilio_sid": provider_message_id,
            "twilio_status": status.lower(),
            "command_status": status,
            "source": "WHATSAPP",
            "processed_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
        if inbound_message_id:
            supabase.table("whatsapp_messages").update({
                "response_sid": provider_message_id,
                "command_status": "PROCESSED" if provider_message_id else "FAILED",
                "error_message": None if provider_message_id else f"{provider} outbound delivery failed",
            }).eq("id", inbound_message_id).execute()
        return saved.data[0]["id"] if saved.data else None
    except Exception as exc:
        logger.warning("outbound WhatsApp audit failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Command handlers — all return a plain-text string (WhatsApp message)
# ─────────────────────────────────────────────────────────────────────────────

def handle_help(employee: dict) -> str:
    name = employee["name"].split()[0]
    return (
        f"{BOT_NAME} | नमस्ते {name}! 👋\n"
        f"{_divider()}\n"
        f"Available Commands / उपलब्ध कमांड:\n\n"
        f"📅 *LEAVE [date] [reason]*\n"
        f"   Apply for leave\n"
        f"   E.g.: LEAVE 2026-06-20 not feeling well\n\n"
        f"💰 *PAYSLIP [month]*\n"
        f"   Get payslip summary\n"
        f"   E.g.: PAYSLIP April\n\n"
        f"🕐 *SHIFT*\n"
        f"   View your upcoming shifts\n\n"
        f"📊 *BALANCE*\n"
        f"   Check your leave balance\n\n"
        f"📋 *COMPLAINT [text]*\n"
        f"   File an HR complaint\n"
        f"   E.g.: COMPLAINT my break time is not given\n\n"
        f"🌟 *CAREER*\n"
        f"   View internal job openings\n\n"
        f"💬 *SURVEY [1-5] [comment]*\n"
        f"   Answer the current employee pulse survey\n"
        f"   E.g.: SURVEY 4 Good team support\n\n"
        f"❓ *HELP*\n"
        f"   Show this menu again\n"
        f"{_divider()}\n"
        f"All data is secure 🔒 | DPDP Act 2023 compliant"
    )


def handle_leave(
    supabase, employee: dict, args: list[str], msg_id: Optional[str] = None
) -> str:
    """
    LEAVE [date] [reason] — full leave request flow.

    Steps:
      1. Parse & validate args via structured command parser.
      2. Guard against duplicate requests (same date + PENDING/APPROVED).
      3. Check leave balance — block if exhausted, show shortfall.
      4. Insert leave_requests row with PENDING status + SLA deadline.
      5. Deduct one day from the appropriate balance bucket.
      6. Notify org managers/admins via WhatsApp.
      7. Reply to employee with ticket, date, type, and remaining balance.
    """
    raw    = args[0] if args else ""
    parsed = _structured_parse(f"LEAVE {raw}")

    # ── Req 2: Validate date (and reason presence) ────────────────────────────
    if not parsed.is_valid:
        return f"{BOT_NAME}\n{parsed.error_message}"

    pa         = parsed.parsed_args
    leave_date = pa["date"]        # ISO YYYY-MM-DD
    reason     = pa["reason"]
    leave_type = pa["leave_type"]  # CASUAL | SICK | EMERGENCY | EARNED

    # Resolve the employee's roster property without creating channel-specific logic.
    property_id = None
    department_id = None
    try:
        actor = supabase.table("users").select("active_property_id,department_id").eq("id", employee["employee_id"]).limit(1).execute()
        if actor.data:
            property_id = actor.data[0].get("active_property_id")
            department_id = actor.data[0].get("department_id")
    except Exception:
        pass

    try:
        from app.services.leave_service import submit_leave_request
        request = submit_leave_request(
            supabase, org_id=employee["org_id"], employee_id=employee["employee_id"],
            property_id=property_id, department_id=department_id,
            start_date=datetime.fromisoformat(leave_date).date(), end_date=datetime.fromisoformat(leave_date).date(),
            leave_type=leave_type, reason=reason, source="WHATSAPP", whatsapp_message_id=msg_id,
        )
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        logger.warning("canonical leave submission rejected: %s", detail or exc)
        return f"{BOT_NAME}\n❌ {detail or 'Failed to submit leave. Please contact HR.'}"

    ticket = request.get("ticket_number", "Submitted")

    # ── Req 5: Notify managers/admins ─────────────────────────────────────────
    _notify_managers_new_leave(
        supabase, employee, ticket, leave_date, leave_type, reason
    )

    # ── Req 6: Build confirmation reply with remaining balance ────────────────
    type_label      = {"CASUAL": "Casual", "SICK": "Sick",
                       "EMERGENCY": "Emergency", "EARNED": "Earned"}.get(
        leave_type, leave_type.title()
    )

    reply = (
        f"{BOT_NAME} ✅ Leave Request Submitted\n"
        f"{_divider()}\n"
        f"👤 Name:     {employee['name']}\n"
        f"📅 Date:     {_fmt_date(leave_date)}\n"
        f"🏷️  Type:     {type_label}\n"
        f"📝 Reason:   {reason[:80]}{'…' if len(reason) > 80 else ''}\n"
        f"🎫 Ticket:   {ticket}\n"
        f"⏳ Status:   Pending Approval\n"
        f"📆 Decision: Within 3 working days\n"
    )
    reply += (
        f"{_divider()}\n"
        f"You will receive a WhatsApp notification once HR acts.\n"
        f"HR के निर्णय पर आपको WhatsApp सूचना मिलेगी।"
    )
    return reply


def handle_payslip(
    supabase, employee: dict, args: list[str], msg_id: Optional[str] = None
) -> str:
    """
    PAYSLIP [month] — full payslip delivery flow.

    Steps:
      1. Parse month/year via structured command parser.
      2. Log payslip request to payslip_requests (Req 5).
      3. Fetch payslip filtered strictly by employee_id (Req 2 + 6).
      4. Verify returned record belongs to requester (defense-in-depth, Req 6).
      5. Attempt PDF generation + S3 upload if no URL cached (Req 3).
      6. Send PDF document via WhatsApp gateway (Req 4).
      7. Reply with text summary + PDF status (Req 4 fallback).
    """
    raw    = args[0].strip() if args else ""
    parsed = _structured_parse(f"PAYSLIP {raw}") if raw else _structured_parse("PAYSLIP")

    # ── Req 1 (month parsing) ─────────────────────────────────────────────────
    if not parsed.is_valid:
        return f"{BOT_NAME}\n{parsed.error_message}"

    pa    = parsed.parsed_args
    month = pa["month"]
    year  = pa["year"]

    # ── Req 5: Log the request ────────────────────────────────────────────────
    pr_id = _log_payslip_request(supabase, employee, month, year, msg_id)

    # ── Reqs 2 + 6: Fetch payslip — filter by employee_id (owner-only) ───────
    try:
        res = (
            supabase.table("payslips")
            .select("*")
            .eq("employee_id", employee["employee_id"])  # Req 6: primary guard
            .eq("month", month)
            .eq("year", year)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.error("payslip fetch failed: %s", exc)
        _update_payslip_request(supabase, pr_id, "ERROR", error_detail=str(exc))
        return f"{BOT_NAME}\n❌ Unable to fetch payslip. Please try again later."

    if not res.data:
        _update_payslip_request(supabase, pr_id, "NOT_FOUND")
        return (
            f"{BOT_NAME}\n"
            f"📊 Payslip — {MONTH_NAME[month]} {year}\n"
            f"{_divider()}\n"
            f"No payslip found for {MONTH_NAME[month]} {year}.\n"
            f"Contact HR if you believe this is an error.\n"
            f"HR से संपर्क करें यदि यह गलती लगती है।"
        )

    ps = res.data[0]

    # ── Req 6: Defense-in-depth — verify the row's owner matches requester ────
    # The .eq("employee_id", ...) above is the primary guard. This check catches
    # any edge-case where the DB layer returns a mismatched row (e.g., RLS off).
    row_owner = ps.get("employee_id")
    if row_owner and row_owner != employee["employee_id"]:
        logger.error(
            "SECURITY: Payslip owner mismatch — requester=%s row_owner=%s",
            employee["employee_id"], row_owner,
        )
        _update_payslip_request(supabase, pr_id, "ERROR",
                                error_detail="security_owner_mismatch")
        return f"{BOT_NAME}\n❌ Unable to retrieve payslip. Please contact HR."

    _update_payslip_request(supabase, pr_id, "FULFILLED", payslip_id=ps.get("id"))

    # ── Reqs 3 + 4: PDF generation and document delivery ─────────────────────
    pdf_url  = ps.get("payslip_pdf_url")
    pdf_sent = False

    if not pdf_url:
        # Try to generate in-memory and upload to S3 ap-south-1
        pdf_url = _generate_and_cache_payslip_pdf(supabase, ps, employee)

    if pdf_url:
        pdf_sent = _send_payslip_document(employee["phone"], pdf_url, month, year)
        if not pdf_sent:
            logger.warning(
                "PDF document send failed for %s %s/%s",
                employee["phone"], month, year,
            )

    # ── Req 4 / fallback: always send text summary ────────────────────────────
    return _build_payslip_text_reply(ps, employee, month, year, pdf_url, pdf_sent)


def _generate_and_cache_payslip_pdf(
    supabase, ps: dict, employee: dict
) -> Optional[str]:
    """
    Generate payslip PDF in-memory, upload to S3 ap-south-1, cache URL on
    the payslips row so subsequent requests skip regeneration.
    Returns the presigned URL or None if generation/upload not available.
    """
    try:
        from app.services.payslip_pdf import generate_payslip_pdf, upload_payslip_to_s3

        pdf_bytes = generate_payslip_pdf(ps, employee["name"])
        if not pdf_bytes:
            return None

        url = upload_payslip_to_s3(
            pdf_bytes,
            org_id      = employee["org_id"],
            employee_id = employee["employee_id"],
            month       = ps.get("month", 0),
            year        = ps.get("year", 0),
        )
        if url:
            # Cache URL on payslips row — best-effort update
            try:
                supabase.table("payslips").update(
                    {"payslip_pdf_url": url}
                ).eq("id", ps["id"]).execute()
            except Exception:
                pass  # URL returned even if cache write fails
        return url

    except Exception as exc:
        logger.warning("PDF generation/upload skipped: %s", exc)
        return None


def _send_payslip_document(
    phone: str, pdf_url: str, month: int, year: int
) -> bool:
    """
    Send payslip PDF as a WhatsApp document message.
    Returns True if the provider accepted the message.
    """
    try:
        from app.services.whatsapp_gateway import WhatsAppGateway
        gw         = WhatsAppGateway()
        month_name = MONTH_NAME.get(month, str(month))
        caption    = (
            f"Your Payslip for {month_name} {year} is attached. "
            f"CONFIDENTIAL — for your eyes only. "
            f"आपकी {month_name} {year} की वेतन पर्ची संलग्न है।"
        )
        filename = f"Payslip_{month_name}_{year}.pdf"
        msg_id   = gw.send_document(phone, pdf_url, caption=caption, filename=filename)
        return msg_id is not None
    except Exception as exc:
        logger.warning("payslip document send failed: %s", exc)
        return False


def _build_payslip_text_reply(
    ps:       dict,
    employee: dict,
    month:    int,
    year:     int,
    pdf_url:  Optional[str],
    pdf_sent: bool,
) -> str:
    """Build the WhatsApp text summary of the payslip."""
    earnings  = float(ps.get("gross_salary_inr") or 0)
    net       = float(ps.get("net_salary_inr") or 0)
    epf       = float(ps.get("epf_deduction_inr") or 0)
    esic      = float(ps.get("esic_deduction_inr") or 0)
    pt        = float(ps.get("professional_tax_inr") or 0)
    tds       = float(ps.get("tds_inr") or 0)
    other_ded = float(ps.get("other_deductions_inr") or 0)
    paid_at   = ps.get("paid_at")

    lines = [
        f"{BOT_NAME} | Payslip — {MONTH_NAME[month]} {year}",
        _divider(),
        f"👤 {employee['name']}",
        "",
        "💼 Earnings:",
        f"   Gross Salary:    {_fmt_inr(earnings)}",
    ]
    if ps.get("basic_salary_inr"):
        lines.append(f"   Basic:           {_fmt_inr(ps['basic_salary_inr'])}")
    if ps.get("hra_inr") and float(ps["hra_inr"] or 0) > 0:
        lines.append(f"   HRA:             {_fmt_inr(ps['hra_inr'])}")
    if ps.get("bonus_inr") and float(ps["bonus_inr"] or 0) > 0:
        lines.append(f"   Bonus:           {_fmt_inr(ps['bonus_inr'])}")

    lines += ["", "📉 Deductions:"]
    if epf:      lines.append(f"   EPF:             {_fmt_inr(epf)}")
    if esic:     lines.append(f"   ESIC:            {_fmt_inr(esic)}")
    if pt:       lines.append(f"   Professional Tax:{_fmt_inr(pt)}")
    if tds:      lines.append(f"   TDS:             {_fmt_inr(tds)}")
    if other_ded: lines.append(f"   Other:           {_fmt_inr(other_ded)}")

    lines += [_divider(), f"✅ Net Pay:         {_fmt_inr(net)}"]
    if paid_at:
        lines.append(f"💳 Paid On:         {_fmt_date(paid_at)}")
    if ps.get("present_days") and ps.get("working_days"):
        lines.append(f"📅 Attendance:      {ps['present_days']}/{ps['working_days']} days")

    lines.append("")
    if pdf_sent:
        lines.append("📄 PDF payslip sent above ⬆️")
        lines.append("   Save it for your records.")
    elif pdf_url:
        lines.append(f"📄 PDF: {pdf_url}")
    else:
        lines.append("📄 PDF not available — contact HR for a printed copy.")

    lines += [
        "",
        "🔒 CONFIDENTIAL — For your eyes only. Do not share.",
        "गोपनीय — केवल आपके लिए।",
    ]
    return "\n".join(lines)


def handle_shift(supabase, employee: dict, args: list[str]) -> str:
    """
    SHIFT — show the employee's schedule for the next 7 days.

    Fields per shift:
      date, start time, end time, property/venue, department, manager, role.

    Data source priority:
      1. v_workforce_schedule (published employee roster)
      2. v_employee_shifts (legacy candidate shift matches)
      3. v_candidate_shifts / raw fallback
    """
    today    = datetime.now(timezone.utc).date()
    week_end = (today + timedelta(days=7)).isoformat()
    today_s  = today.isoformat()
    from app.services.employee_self_service import employee_shifts
    rows: list[dict] = employee_shifts(supabase, employee["employee_id"], days=7)

    # ── Legacy platform-user shift view ───────────────────────────────────────
    if not rows:
      try:
        res = (
            supabase.table("v_employee_shifts")
            .select("*")
            .eq("employee_id", employee["employee_id"])
            .gte("start_date", today_s)
            .lte("start_date", week_end)
            .order("start_date")
            .limit(20)
            .execute()
        )
        rows = res.data or []
      except Exception as exc:
        logger.debug("v_employee_shifts query failed: %s", exc)

    # ── Secondary: view for hired candidates ──────────────────────────────────
    if not rows and employee.get("source") == "candidates":
        try:
            res = (
                supabase.table("v_candidate_shifts")
                .select("*")
                .eq("candidate_id", employee["employee_id"])
                .gte("start_date", today_s)
                .lte("start_date", week_end)
                .order("start_date")
                .limit(20)
                .execute()
            )
            rows = res.data or []
        except Exception as exc:
            logger.debug("v_candidate_shifts query failed: %s", exc)

    # ── Tertiary: raw join fallback (dev / view-unavailable) ──────────────────
    if not rows:
        rows = _fetch_shifts_fallback(supabase, employee, today_s, week_end)

    if not rows:
        return (
            f"{BOT_NAME}\n"
            f"📅 No shifts scheduled in the next 7 days.\n"
            f"Contact your supervisor for the latest roster.\n"
            f"अगले 7 दिनों में कोई शिफ्ट निर्धारित नहीं है।\n"
            f"रोस्टर के लिए अपने सुपरवाइज़र से संपर्क करें।"
        )

    lines = [
        f"{BOT_NAME} | Your Schedule — Next 7 Days",
        _divider(),
    ]
    for shift in rows:
        lines.extend(_fmt_shift_block(shift))
        lines.append("")   # blank line between shifts

    # Summary
    n = len(rows)
    lines += [
        _divider(),
        f"📋 {n} shift{'s' if n != 1 else ''} in the next 7 days.",
        "Type HELP for all commands.",
    ]
    return "\n".join(lines)


def handle_balance(supabase, employee: dict, args: list[str]) -> str:
    """BALANCE — show leave balance for current year."""
    year = datetime.now(timezone.utc).year

    try:
        from app.services.employee_self_service import leave_snapshot
        snapshot = leave_snapshot(supabase, employee["employee_id"])
        balance = snapshot.get("balance")
    except Exception as exc:
        logger.error("leave_balance fetch failed: %s", exc)
        return f"{BOT_NAME}\n❌ Unable to fetch balance. Please try again."

    if not balance:
        # Auto-create default balance for this year
        _ensure_leave_balance(supabase, employee, year)
        casual_rem = 12; sick_rem = 12; earned_rem = 15
        casual_used = 0; sick_used = 0; earned_used = 0
    else:
        b = balance
        casual_rem  = b.get("casual_remaining", 0)
        sick_rem    = b.get("sick_remaining", 0)
        earned_rem  = b.get("earned_remaining", 0)
        casual_used = b.get("casual_used", 0)
        sick_used   = b.get("sick_used", 0)
        earned_used = b.get("earned_used", 0)

    total_rem  = (casual_rem or 0) + (sick_rem or 0) + (earned_rem or 0)
    total_used = (casual_used or 0) + (sick_used or 0) + (earned_used or 0)

    return (
        f"{BOT_NAME} | Leave Balance {year}\n"
        f"{_divider()}\n"
        f"👤 {employee['name']}\n\n"
        f"📅 Casual Leave:   {casual_rem} remaining ({casual_used} used)\n"
        f"🤒 Sick Leave:     {sick_rem} remaining ({sick_used} used)\n"
        f"🌴 Earned Leave:   {earned_rem} remaining ({earned_used} used)\n"
        f"{_divider()}\n"
        f"✅ Total Remaining: {total_rem} days\n"
        f"   Total Used:      {total_used} days\n\n"
        f"To apply: LEAVE [date] [reason]"
    )


def handle_complaint(
    supabase, employee: dict, args: list[str], msg_id: Optional[str] = None
) -> str:
    """
    COMPLAINT [text]        — file complaint anonymously (default, Req 2).
    COMPLAINT NAMED [text]  — attach employee identity to the complaint.
    COMPLAINT ANON  [text]  — explicitly anonymous (backward-compat alias).

    Data flow:
      • Writes to hr_complaints (022) — authoritative table, supports anonymous.
      • For named complaints, also writes to employee_complaints (021) for
        backward compatibility with admin dashboards not yet migrated.
      • Req 3: identity hidden from normal managers via v_hr_complaints_display.
      • Req 4: only hr_admin/super_admin can call /complaints/{id}/identity.
      • Req 5: WhatsApp reply includes reference number (ticket + track ID).
    """
    raw    = args[0].strip() if args else ""
    parsed = _structured_parse(f"COMPLAINT {raw}")

    # ── Validation (Req 1 — minimum text length, format) ─────────────────────
    if not parsed.is_valid:
        return f"{BOT_NAME}\n{parsed.error_message}"

    pa           = parsed.parsed_args
    text         = pa["text"]
    is_anonymous = pa["is_anonymous"]   # True by default (Req 2)
    category     = pa["category"]
    severity     = pa["severity"]

    try:
        from app.services.employee_self_service import submit_grievance
        complaint = submit_grievance(
            supabase, org_id=employee["org_id"], employee_id=employee["employee_id"],
            phone=employee.get("phone"), text=text, category=category, severity=severity,
            anonymous=is_anonymous, complaint_type="POSH" if category == "HARASSMENT" else "GRIEVANCE",
            property_id=employee.get("property_id"), source="WHATSAPP", whatsapp_message_id=msg_id,
        )
    except Exception as exc:
        logger.error("hr_complaints insert failed: %s", exc)
        return f"{BOT_NAME}\n❌ Failed to file complaint. Please try again or call HR directly."

    # ── Req 5: WhatsApp confirmation with reference number ───────────────────
    return _build_complaint_reply(
        complaint["ticket_number"], complaint["category"], complaint["severity"], text,
        is_anonymous, complaint.get("anonymous_token")
    )


def _build_complaint_reply(
    ticket:       str,
    category:     str,
    severity:     str,
    text:         str,
    is_anonymous: bool,
    anon_token:   Optional[str],
) -> str:
    """Build the WhatsApp confirmation message for a filed complaint."""
    sev_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(
        severity, "⚪"
    )

    lines = [
        f"{BOT_NAME} ✅ Complaint Filed",
        _divider(),
        f"🎫 Reference:  {ticket}",
        f"🏷️  Category:  {category.title()}",
        f"{sev_emoji} Severity:  {severity.title()}",
        f"⏳ Status:     Open",
    ]

    if is_anonymous:
        # Req 2+3: identity is protected — show track ID for status follow-up
        short_id = anon_token[:8].upper() if anon_token else "N/A"
        lines += [
            f"🔒 Mode:       Anonymous",
            f"🔑 Track ID:   {short_id}",
            f"   (Use this ID to check status without revealing who you are)",
        ]
    else:
        lines.append(f"👤 Mode:       Named (your identity is on record)")

    lines += [
        "",
        f"📝 Your complaint:",
        f'   "{text[:120]}{"…" if len(text) > 120 else ""}"',
        _divider(),
    ]

    if is_anonymous:
        lines += [
            "🛡️ Your identity is protected.",
            "   Normal managers can only see the complaint text, not who filed it.",
            "   Only HR Admin can access identity if legally required.",
            "",
        ]

    lines += [
        "HR will review and contact you within 3 working days.",
        "HR 3 कार्य दिवसों में आपसे संपर्क करेगा।",
    ]
    return "\n".join(lines)


def handle_survey(supabase, employee: dict, args: list[str]) -> str:
    """Submit the latest WhatsApp-enabled pulse through the shared service."""
    raw = args[0] if args else ""
    parsed = _structured_parse(f"SURVEY {raw}")
    if not parsed.is_valid:
        return f"{BOT_NAME}\n{parsed.error_message}"
    surveys = supabase.table("employee_pulse_surveys").select("*").eq("org_id", employee["org_id"]).eq("status", "ACTIVE").order("opens_at", desc=True).execute()
    enabled = [item for item in (surveys.data or []) if "WHATSAPP" in (item.get("channels") or [])]
    if not enabled:
        return f"{BOT_NAME}\nNo active employee survey right now.\nअभी कोई सक्रिय कर्मचारी सर्वे नहीं है।"
    profile = supabase.table("users").select("id,org_id,active_property_id,department_id").eq("id", employee["employee_id"]).limit(1).execute()
    if not profile.data:
        return f"{BOT_NAME}\nYour employee profile could not be verified. Please contact HR."
    try:
        receipt = submit_pulse_response(supabase, survey=enabled[0], employee=profile.data[0], score=parsed.parsed_args["score"], comment=parsed.parsed_args.get("comment"), source="WHATSAPP")
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return f"{BOT_NAME}\n{detail}"
    privacy = "Your answer is anonymous." if receipt["anonymous"] else "Your answer is recorded with your employee profile."
    return f"{BOT_NAME}\n✅ Survey response recorded: {parsed.parsed_args['score']}/5.\n{privacy}\nआपकी प्रतिक्रिया दर्ज हो गई है।"


def handle_career(supabase, employee: dict, args: list[str]) -> str:
    """
    CAREER — Personalised career guidance for the employee.

    Steps:
      Req 1 — Detect current role (candidate_profiles → shifts → fallback).
      Req 2 — Show next 3 possible hospitality roles.
      Req 3 — Show required skills + certifications, marking ones already held.
      Req 4 — Suggest open internal jobs matching the next roles.
      Req 5 — Return a compact WhatsApp-friendly reply.
    """
    from app.services.career_service import (
        detect_current_role,
        get_career_path,
        get_employee_certs,
        find_matching_jobs,
    )

    # Reqs 1–3: detect role, fetch path and existing certs
    current_role  = detect_current_role(supabase, employee)
    path          = get_career_path(current_role)
    existing_certs = get_employee_certs(supabase, employee)

    # Req 4: find matching open jobs
    open_jobs = find_matching_jobs(supabase, employee, path.next_roles)

    # Req 5: build compact WhatsApp reply
    return _build_career_reply(employee, current_role, path, existing_certs, open_jobs)


def _build_career_reply(
    employee:       dict,
    current_role:   Optional[str],
    path,                           # CareerPath from career_service
    existing_certs: list[str],
    open_jobs:      list[dict],
) -> str:
    """
    Req 5 — WhatsApp-friendly career guidance message.

    Format:
      Header + current role
      📈 Next roles (max 3, numbered)
      🎓 Skills to build (max 4 bullet points)
      📜 Certifications (✅ if already held, 📋 if still needed)
      🏢 Open positions (max 3)
      Hindi footer
    """
    name = employee["name"].split()[0]
    display_role = (current_role or "").strip() or "Not yet assigned"

    lines = [
        f"{BOT_NAME} | Your Career Path 🌟",
        _divider(),
        f"👤 {name}",
        f"💼 Current Role:  {display_role}",
        "",
        "📈 Next Steps:",
    ]

    ordinals = ["1️⃣", "2️⃣", "3️⃣"]
    for i, role in enumerate(path.next_roles[:3]):
        lines.append(f"  {ordinals[i]} {role}")

    lines += ["", "🎓 Skills to Build:"]
    for skill in path.skills[:4]:
        lines.append(f"  • {skill}")

    if path.certifications:
        lines += ["", "📜 Certifications:"]
        for cert in path.certifications[:3]:
            # Mark as held (✅) or still needed (📋)
            held = any(cert.lower() in ec or ec in cert.lower()
                       for ec in existing_certs)
            badge = "✅" if held else "📋"
            lines.append(f"  {badge} {cert}")

    if path.timeline:
        lines += ["", f"⏱ Timeline: ~{path.timeline}"]

    lines.append("")
    if open_jobs:
        lines.append("🏢 Open Internally:")
        for job in open_jobs[:3]:
            title     = (job.get("title")     or "Open Role").strip()
            role_type = (job.get("role_type") or "").strip()
            label     = f"{title}"
            if role_type and role_type.lower() not in title.lower():
                label += f" ({role_type})"
            lines.append(f"  → {label}")
        lines.append("  Talk to HR to apply internally.")
    else:
        lines += [
            "🏢 No open internal positions right now.",
            "  We'll notify you when roles match your path!",
        ]

    lines += [
        _divider(),
        "Type HELP to see all commands.",
        "करियर सलाह के लिए HR से संपर्क करें। 🚀",
    ]
    return "\n".join(lines)


def handle_unknown(text: str) -> str:
    """Catch-all for unrecognised messages."""
    return (
        f"{BOT_NAME}\n"
        f"Sorry, I didn't understand that. 🤔\n\n"
        f"Type *HELP* to see all available commands.\n"
        f"HELP टाइप करें सभी कमांड देखने के लिए।\n\n"
        f"Quick commands: LEAVE · PAYSLIP · SHIFT · BALANCE · COMPLAINT · CAREER"
    )


def handle_not_registered(phone: str) -> str:
    return (
        f"{BOT_NAME}\n"
        f"Your number ({phone}) is not registered in our system.\n\n"
        f"Please ask your HR manager to link your WhatsApp number.\n"
        f"कृपया अपने HR मैनेजर से अपना WhatsApp नंबर लिंक करवाएं।\n\n"
        f"For help: Call HR or email hr@hosprecruit.ai"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def handle_whatsapp_message(
    supabase,
    phone: str,
    body: str,
    twilio_sid: str = "",
) -> str:
    """
    Top-level entry point: parse message, identify employee, dispatch.
    Writes to whatsapp_users + whatsapp_messages for full audit trail.
    Returns the text to send back via WhatsApp.
    """
    employee = resolve_employee(supabase, phone)
    wu_id    = get_or_create_whatsapp_user(supabase, phone, employee)

    command, args      = parse_command(body)
    command_args_str   = args[0] if args else ""

    structured = _structured_parse(body)
    anonymous_complaint = command == "COMPLAINT" and structured.is_valid and bool(structured.parsed_args.get("is_anonymous"))

    # Log the inbound message before dispatching
    msg_id = log_inbound_message(
        supabase, "ANONYMOUS" if anonymous_complaint else phone, None if anonymous_complaint else employee, None if anonymous_complaint else wu_id,
        "[REDACTED ANONYMOUS COMPLAINT]" if anonymous_complaint else body, twilio_sid, command, "[REDACTED]" if anonymous_complaint else command_args_str,
    )

    if not employee:
        reply = handle_not_registered(phone)
        update_message_response(supabase, msg_id, reply, "UNREGISTERED")
        return reply

    dispatch = {
        "HELP":      lambda: handle_help(employee),
        "LEAVE":     lambda: handle_leave(supabase, employee, args),
        "PAYSLIP":   lambda: handle_payslip(supabase, employee, args, msg_id),
        "SHIFT":     lambda: handle_shift(supabase, employee, args),
        "BALANCE":   lambda: handle_balance(supabase, employee, args),
        "COMPLAINT": lambda: handle_complaint(supabase, employee, args, msg_id),
        "CAREER":    lambda: handle_career(supabase, employee, args),
        "SURVEY":    lambda: handle_survey(supabase, employee, args),
        "UNKNOWN":   lambda: handle_unknown(body),
    }

    handler = dispatch.get(command, dispatch["UNKNOWN"])
    try:
        reply = handler()
        update_message_response(supabase, msg_id, reply)
        return reply
    except Exception as exc:
        logger.error("hr_bot handler %s crashed: %s", command, exc)
        reply = (
            f"{BOT_NAME}\n"
            f"⚠️ Something went wrong. Please try again in a moment.\n"
            f"कुछ गलत हो गया। कृपया थोड़ी देर बाद पुनः प्रयास करें।"
        )
        update_message_response(supabase, msg_id, reply, "FAILED", str(exc))
        return reply


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

# _parse_date, _parse_month_arg, _infer_leave_type, _infer_complaint_category,
# _infer_complaint_severity are all imported from command_parser at the top of
# the Command parser section. Kept as aliases so callsites below still work.


def _log_payslip_request(
    supabase,
    employee: dict,
    month: int,
    year: int,
    msg_id: Optional[str],
) -> Optional[str]:
    """Write a payslip_requests row and return its UUID."""
    try:
        res = supabase.table("payslip_requests").insert({
            "org_id":               employee["org_id"],
            "employee_id":          employee["employee_id"],
            "whatsapp_message_id":  msg_id,
            "requested_month":      month,
            "requested_year":       year,
            "status":               "PENDING",
            "source":               "WHATSAPP",
            "created_at":           datetime.utcnow().isoformat(),
            "updated_at":           datetime.utcnow().isoformat(),
        }).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as exc:
        logger.debug("payslip_requests insert failed: %s", exc)
        return None


def _update_payslip_request(
    supabase,
    pr_id: Optional[str],
    status: str,
    payslip_id: Optional[str] = None,
    error_detail: Optional[str] = None,
) -> None:
    """Update the payslip_requests row with the resolution."""
    if not pr_id:
        return
    try:
        payload: dict = {
            "status":     status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if status == "FULFILLED":
            payload["fulfilled_at"] = datetime.utcnow().isoformat()
            payload["payslip_id"]   = payslip_id
        if error_detail:
            payload["error_detail"] = error_detail
        supabase.table("payslip_requests").update(payload).eq("id", pr_id).execute()
    except Exception as exc:
        logger.debug("payslip_requests update failed: %s", exc)


def _check_leave_balance(
    supabase, employee: dict, leave_type: str
) -> tuple[bool, str, dict]:
    """
    Req 3 — Check whether the employee has at least 1 day remaining for
    the requested leave type before creating the request.

    Returns (ok, error_message, balance_info).
    On DB error, returns ok=True (fail-open) and logs a warning.

    Column mapping:
      CASUAL    → casual_remaining  (also used for EMERGENCY)
      SICK      → sick_remaining
      EARNED    → earned_remaining
    """
    year = datetime.now(timezone.utc).year
    rem_col = {
        "SICK":      "sick_remaining",
        "EARNED":    "earned_remaining",
        "CASUAL":    "casual_remaining",
        "EMERGENCY": "casual_remaining",
    }.get(leave_type, "casual_remaining")

    type_label = {
        "CASUAL": "Casual", "SICK": "Sick",
        "EMERGENCY": "Casual (Emergency)", "EARNED": "Earned",
    }.get(leave_type, leave_type.title())

    try:
        res = (
            supabase.table("leave_balances")
            .select(
                "casual_remaining, sick_remaining, earned_remaining, "
                "casual_used, sick_used, earned_used, "
                "casual_total, sick_total, earned_total"
            )
            .eq("employee_id", employee["employee_id"])
            .eq("year", year)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning("balance check DB error — failing open: %s", exc)
        return True, "", {"remaining": 12}  # fail-open with default

    if not res.data:
        # No row yet — auto-create with defaults and allow (first leave this year)
        _ensure_leave_balance(supabase, employee, year)
        defaults = {"CASUAL": 12, "SICK": 12, "EMERGENCY": 12, "EARNED": 15}
        return True, "", {"remaining": defaults.get(leave_type, 12)}

    b         = res.data[0]
    remaining = int(b.get(rem_col) or 0)

    if remaining <= 0:
        casual_rem = int(b.get("casual_remaining") or 0)
        sick_rem   = int(b.get("sick_remaining")   or 0)
        earned_rem = int(b.get("earned_remaining") or 0)
        return False, (
            f"❌ No {type_label} Leave Remaining\n"
            f"{_divider()}\n"
            f"You have used all your {type_label.lower()} leave days for {year}.\n\n"
            f"📊 Current Balance:\n"
            f"  📅 Casual:  {casual_rem} day(s)\n"
            f"  🤒 Sick:    {sick_rem} day(s)\n"
            f"  🌴 Earned:  {earned_rem} day(s)\n\n"
            f"Contact HR for leave-without-pay (LWP) options.\n"
            f"HR से बिना वेतन की छुट्टी के लिए संपर्क करें।"
        ), {"remaining": 0}

    return True, "", {
        "remaining": remaining,
        "casual_remaining": int(b.get("casual_remaining") or 0),
        "sick_remaining":   int(b.get("sick_remaining")   or 0),
        "earned_remaining": int(b.get("earned_remaining") or 0),
    }


def _is_duplicate_request(supabase, employee: dict, leave_date: str) -> bool:
    """
    Return True if the employee already has a PENDING or APPROVED leave request
    for exactly this date (prevents double-booking the same day).
    """
    try:
        res = (
            supabase.table("leave_requests")
            .select("id")
            .eq("employee_id", employee["employee_id"])
            .eq("leave_date", leave_date)
            .in_("status", ["PENDING", "APPROVED"])
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception as exc:
        logger.warning("duplicate-request check failed: %s", exc)
        return False  # fail-open


def _notify_managers_new_leave(
    supabase,
    employee: dict,
    ticket: str,
    leave_date: str,
    leave_type: str,
    reason: str,
) -> None:
    """
    Req 5 — Send a WhatsApp notification to all managers/admins in the org
    when a new leave request is created.  Best-effort: never raises.
    """
    try:
        # Find managers/admins in the same org.
        # Falls back to any org user if no explicit manager role found.
        mgr_res = (
            supabase.table("users")
            .select("id, phone, email")
            .eq("org_id", employee["org_id"])
            .in_("role", ["admin", "manager", "hr_manager", "hr", "recruiter"])
            .limit(10)
            .execute()
        )
        managers = mgr_res.data or []

        # Exclude the requesting employee themselves
        managers = [m for m in managers if m.get("id") != employee["employee_id"]]

        if not managers:
            logger.info(
                "No managers found for leave notification (ticket=%s org=%s)",
                ticket, employee["org_id"],
            )
            return

        msg = (
            f"🤖 HospBot 📋 New Leave Request\n"
            f"{_divider()}\n"
            f"👤 Employee:  {employee['name']}\n"
            f"📅 Date:      {_fmt_date(leave_date)}\n"
            f"🏷️  Type:      {leave_type.title()}\n"
            f"📝 Reason:    {reason[:100]}{'…' if len(reason) > 100 else ''}\n"
            f"🎫 Ticket:    {ticket}\n"
            f"{_divider()}\n"
            f"Reply via HR dashboard to approve or reject.\n"
            f"कृपया HR डैशबोर्ड पर अनुरोध की समीक्षा करें।"
        )

        # Use WhatsApp gateway (avoids importing from router)
        try:
            from app.services.whatsapp_gateway import send_whatsapp
            for mgr in managers:
                phone = mgr.get("phone")
                if phone:
                    provider_id = send_whatsapp(phone, msg)
                    log_outbound_message(
                        supabase, phone, msg, provider_id,
                        provider="configured_gateway",
                    )
        except ImportError:
            logger.debug("whatsapp_gateway not available for manager notification")

    except Exception as exc:
        logger.warning("manager leave notification failed: %s", exc)


def _restore_leave_balance(
    supabase, employee_id: str, org_id: str, leave_type: str
) -> None:
    """
    Reverse a balance deduction when a leave request is rejected or cancelled.
    Decrements the *_used counter by 1 (floor at 0) so the remaining day
    is returned to the employee's balance.
    Called by the rejection endpoint in hr_bot.py.
    """
    year = datetime.now(timezone.utc).year
    col_map = {
        "SICK":      "sick_used",
        "EARNED":    "earned_used",
        "CASUAL":    "casual_used",
        "EMERGENCY": "casual_used",
    }
    col = col_map.get(leave_type, "casual_used")

    try:
        res = (
            supabase.table("leave_balances")
            .select(f"id, {col}")
            .eq("employee_id", employee_id)
            .eq("year", year)
            .limit(1)
            .execute()
        )
        if res.data:
            current = int(res.data[0].get(col, 0) or 0)
            restored = max(0, current - 1)  # never go below 0
            supabase.table("leave_balances").update(
                {col: restored, "updated_at": datetime.utcnow().isoformat()}
            ).eq("id", res.data[0]["id"]).execute()
            logger.info(
                "Balance restored: employee=%s type=%s %s → %s",
                employee_id, leave_type, current, restored,
            )
    except Exception as exc:
        logger.warning("balance restore failed for %s: %s", employee_id, exc)


def _deduct_leave_balance(supabase, employee: dict, leave_type: str) -> None:
    """Deduct 1 leave day from the appropriate balance bucket."""
    year    = datetime.now(timezone.utc).year
    col_map = {
        "SICK": "sick_used", "EMERGENCY": "casual_used",
        "EARNED": "earned_used", "CASUAL": "casual_used",
    }
    col = col_map.get(leave_type, "casual_used")
    try:
        res = (
            supabase.table("leave_balances")
            .select("id, " + col)
            .eq("employee_id", employee["employee_id"])
            .eq("year", year)
            .limit(1)
            .execute()
        )
        if res.data:
            current = res.data[0].get(col, 0) or 0
            supabase.table("leave_balances").update(
                {col: current + 1, "updated_at": datetime.utcnow().isoformat()}
            ).eq("id", res.data[0]["id"]).execute()
        else:
            _ensure_leave_balance(supabase, employee, year)
    except Exception as exc:
        logger.warning("leave balance deduction failed: %s", exc)


def _ensure_leave_balance(supabase, employee: dict, year: int) -> None:
    """Create a default leave balance row if not present."""
    try:
        supabase.table("leave_balances").insert({
            "org_id":      employee["org_id"],
            "employee_id": employee["employee_id"],
            "year":        year,
        }).execute()
    except Exception:
        pass  # UNIQUE conflict is fine


def _fetch_shifts_fallback(
    supabase,
    employee: dict,
    today_s:  str = "",
    week_end: str = "",
) -> list[dict]:
    """
    Fallback shift fetch when v_employee_shifts / v_candidate_shifts views are
    unavailable (dev / fresh DB).

    Bug fixed vs original: the old version fetched *any* candidate in the org.
    This version looks up the specific employee's candidate record by phone or
    by using their employee_id directly (when source == "candidates").
    """
    if not today_s:
        today_s  = datetime.now(timezone.utc).date().isoformat()
    if not week_end:
        week_end = (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat()

    try:
        # ── Candidate lookup — match this specific employee ────────────────────
        if employee.get("source") == "candidates":
            # employee_id IS the candidate UUID
            cand_ids = [employee["employee_id"]]
        else:
            # Look up candidate by phone + org (most reliable cross-table link)
            cand_res = (
                supabase.table("candidates")
                .select("id")
                .eq("phone", employee.get("phone", ""))
                .eq("org_id", employee["org_id"])
                .in_("pipeline_stage",
                     ["hired", "offer_accepted", "joined", "onboarded"])
                .limit(3)
                .execute()
            )
            cand_ids = [r["id"] for r in (cand_res.data or [])]
            if not cand_ids:
                return []

        # ── Shift assignments ─────────────────────────────────────────────────
        sm_res = (
            supabase.table("shift_matches")
            .select("shift_id, status")
            .in_("candidate_id", cand_ids)
            .in_("status", ["confirmed", "matched"])
            .limit(20)
            .execute()
        )
        shift_ids = [r["shift_id"] for r in (sm_res.data or [])]
        if not shift_ids:
            return []

        # ── Fetch shifts with all detail columns ──────────────────────────────
        s_res = (
            supabase.table("shifts")
            .select(
                "id, role, shift_type, start_date, end_date, status, "
                "hours_per_week, property_name, department, location, "
                "manager_id, urgency"
            )
            .in_("id", shift_ids)
            .eq("status", "open")
            .gte("start_date", today_s)
            .lte("start_date", week_end)
            .order("start_date")
            .execute()
        )
        return s_res.data or []

    except Exception as exc:
        logger.debug("fallback shift fetch failed: %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Shift formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_time(ts: str) -> str:
    """Extract HH:MM from a TIMESTAMP string. Returns '' on failure."""
    try:
        return datetime.fromisoformat(str(ts)).strftime("%H:%M")
    except Exception:
        return ""


def _calc_shift_duration(start: str, end: str) -> str:
    """Return human-readable duration like '8 hrs' or '4.5 hrs'."""
    try:
        s = datetime.fromisoformat(str(start))
        e = datetime.fromisoformat(str(end))
        hrs = (e - s).total_seconds() / 3600
        if hrs <= 0:
            return ""
        return f"{int(hrs)} hrs" if hrs == int(hrs) else f"{hrs:.1f} hrs"
    except Exception:
        return ""


def _fmt_shift_block(s: dict) -> list[str]:
    """
    Format one shift as a list of WhatsApp-ready lines.

    Output per shift:
      🔹 Mon, 23 Jun 2026
         ⏰ 09:00 – 17:00  (8 hrs)
         🏨 Grand Hyatt Mumbai
         🏢 F&B — Banquet
         👤 Mgr: Rajesh Kumar
         💼 Banquet Waiter | Full Day
    """
    lines: list[str] = []

    # Date (always shown)
    start_ts  = str(s.get("start_date", ""))
    end_ts    = str(s.get("end_date", ""))
    date_str  = _fmt_date(start_ts) if start_ts else "—"
    lines.append(f"🔹 {date_str}")

    # Time range + duration
    start_t  = _fmt_time(start_ts)
    end_t    = _fmt_time(end_ts)
    if start_t and end_t:
        dur = _calc_shift_duration(start_ts, end_ts)
        time_str = f"{start_t} – {end_t}"
        if dur:
            time_str += f"  ({dur})"
        lines.append(f"   ⏰ {time_str}")

    # Property / venue
    prop = (s.get("property_name") or "").strip()
    loc  = (s.get("location")      or "").strip()
    venue = prop or loc
    if venue:
        lines.append(f"   🏨 {venue}")

    # Department
    dept = (s.get("department") or "").strip()
    if dept:
        lines.append(f"   🏢 {dept}")

    # Manager display name
    mgr_display = (s.get("manager_display_name") or "").strip()
    mgr_email   = (s.get("manager_email") or "").strip()
    if not mgr_display and mgr_email:
        mgr_display = mgr_email.split("@")[0].replace(".", " ").title()
    if mgr_display:
        lines.append(f"   👤 Mgr: {mgr_display}")

    # Role + shift type
    role  = (s.get("role")       or "").strip()
    stype = (s.get("shift_type") or "").replace("_", " ").strip()
    parts = [p.title() for p in [role, stype] if p]
    if parts:
        lines.append(f"   💼 {' | '.join(parts)}")

    return lines
