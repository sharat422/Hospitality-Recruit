"""
FSSAI Certificate Expiry Worker
Celery task: runs daily at 09:00 IST (scheduled via celery_app.beat_schedule).

Alert tiers:
  • 30 days before expiry → alert_30_day_sent (SMS to candidate + recruiter)
  • 7  days before expiry → alert_7_day_sent  (SMS — urgent)
  • On/after expiry       → alert_expired_sent + status=EXPIRED
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

try:
    from app.celery_app import celery_app as _celery_app
    _HAS_CELERY = True
except ImportError:  # Celery not installed in this environment (e.g. test venv)
    _celery_app = None
    _HAS_CELERY = False

from app.core.business_date import business_today
from app.core.config import settings
from supabase import create_client

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _supabase_client():
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY,
    )


def _twilio_client():
    try:
        from twilio.rest import Client
        return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    except Exception as exc:
        logger.warning("Twilio init failed: %s", exc)
        return None


def _send_sms(twilio, to_number: Optional[str], message: str) -> bool:
    """Send SMS, return True on success. Silently skips if no number or no Twilio."""
    if not twilio or not to_number:
        return False
    try:
        # Ensure E.164 format for Indian numbers
        number = to_number.strip()
        if not number.startswith("+"):
            number = f"+91{number.lstrip('0')}"
        twilio.messages.create(body=message, from_=settings.TWILIO_PHONE_NUMBER, to=number)
        return True
    except Exception as exc:
        logger.warning("SMS to %s failed: %s", to_number, exc)
        return False


def _build_sms(cert: dict, days_left: int, alert_type: str) -> str:
    cert_label = cert.get("cert_type", "FSSAI").replace("_", " ")
    entity     = cert.get("licensed_entity") or "your establishment"
    expiry     = cert.get("expiry_date", "")

    if alert_type == "EXPIRED":
        return (
            f"⚠️ FSSAI Alert: Your {cert_label} for {entity} expired on {expiry}. "
            f"Renew immediately to avoid penalties. Contact your recruiter. "
            f"- HospRecruit"
        )
    urgency = "URGENT: " if days_left <= 7 else ""
    return (
        f"{urgency}FSSAI Alert: Your {cert_label} for {entity} expires on {expiry} "
        f"({days_left} day{'s' if days_left != 1 else ''} left). "
        f"Upload renewal certificate at your recruitment portal. - HospRecruit"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Core scan logic (separated for testability)
# ─────────────────────────────────────────────────────────────────────────────

def scan_expiring_certs(supabase) -> dict:
    """
    Query active FSSAI certs across all orgs and dispatch the three alert tiers.
    Returns a summary dict for logging / monitoring.
    """
    # Celery beat runs on Asia/Kolkata and fires this at 03:30 IST, which is
    # 22:00 UTC the previous day — so the UTC date was yesterday on every run.
    # expiry_date is a business date, so today must be the hotel's date.
    today    = business_today()
    d7_cut   = (today + timedelta(days=7)).isoformat()
    d30_cut  = (today + timedelta(days=30)).isoformat()
    today_s  = today.isoformat()

    twilio = _twilio_client()
    stats  = {"alerted_30d": 0, "alerted_7d": 0, "marked_expired": 0, "errors": 0}

    # ── 30-day alerts ────────────────────────────────────────────────────────
    try:
        rows = (
            supabase.table("fssai_certificates")
            .select("id, org_id, candidate_id, cert_type, license_number, "
                    "licensed_entity, expiry_date, candidate_phone, recruiter_email, "
                    "foster_course, activity_category")
            .eq("status", "ACTIVE")
            .eq("alert_30_day_sent", False)
            .gte("expiry_date", today_s)
            .lte("expiry_date", d30_cut)
            .execute()
        ).data or []
    except Exception as exc:
        logger.error("30-day query failed: %s", exc)
        rows = []

    for cert in rows:
        try:
            days_left = (datetime.fromisoformat(cert["expiry_date"]) - datetime.now()).days
            msg = _build_sms(cert, days_left, "30D")
            _send_sms(twilio, cert.get("candidate_phone"), msg)
            if cert.get("recruiter_email"):
                _send_sms(twilio, cert.get("recruiter_email"), msg)

            supabase.table("fssai_certificates").update(
                {"alert_30_day_sent": True, "updated_at": datetime.utcnow().isoformat()}
            ).eq("id", cert["id"]).execute()
            stats["alerted_30d"] += 1
        except Exception as exc:
            logger.error("30d alert failed cert %s: %s", cert.get("id"), exc)
            stats["errors"] += 1

    # ── 7-day alerts ─────────────────────────────────────────────────────────
    try:
        rows7 = (
            supabase.table("fssai_certificates")
            .select("id, org_id, candidate_id, cert_type, license_number, "
                    "licensed_entity, expiry_date, candidate_phone, recruiter_email")
            .eq("status", "ACTIVE")
            .eq("alert_7_day_sent", False)
            .gte("expiry_date", today_s)
            .lte("expiry_date", d7_cut)
            .execute()
        ).data or []
    except Exception as exc:
        logger.error("7-day query failed: %s", exc)
        rows7 = []

    for cert in rows7:
        try:
            days_left = (datetime.fromisoformat(cert["expiry_date"]) - datetime.now()).days
            msg = _build_sms(cert, max(0, days_left), "7D")
            _send_sms(twilio, cert.get("candidate_phone"), msg)
            if cert.get("recruiter_email"):
                _send_sms(twilio, cert.get("recruiter_email"), msg)

            supabase.table("fssai_certificates").update(
                {"alert_7_day_sent": True, "updated_at": datetime.utcnow().isoformat()}
            ).eq("id", cert["id"]).execute()
            stats["alerted_7d"] += 1
        except Exception as exc:
            logger.error("7d alert failed cert %s: %s", cert.get("id"), exc)
            stats["errors"] += 1

    # ── Mark expired ─────────────────────────────────────────────────────────
    try:
        expired = (
            supabase.table("fssai_certificates")
            .select("id, cert_type, licensed_entity, expiry_date, candidate_phone, recruiter_email")
            .eq("status", "ACTIVE")
            .eq("alert_expired_sent", False)
            .lt("expiry_date", today_s)
            .execute()
        ).data or []
    except Exception as exc:
        logger.error("expired query failed: %s", exc)
        expired = []

    for cert in expired:
        try:
            msg = _build_sms(cert, 0, "EXPIRED")
            _send_sms(twilio, cert.get("candidate_phone"), msg)
            if cert.get("recruiter_email"):
                _send_sms(twilio, cert.get("recruiter_email"), msg)

            supabase.table("fssai_certificates").update({
                "status":             "EXPIRED",
                "alert_expired_sent": True,
                "updated_at":         datetime.utcnow().isoformat(),
            }).eq("id", cert["id"]).execute()
            stats["marked_expired"] += 1
        except Exception as exc:
            logger.error("expire mark failed cert %s: %s", cert.get("id"), exc)
            stats["errors"] += 1

    logger.info("FSSAI expiry scan: %s", stats)
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Celery task
# ─────────────────────────────────────────────────────────────────────────────

def _check_fssai_expiry_fn(self=None) -> dict:
    """Daily FSSAI certificate expiry check (Celery task body)."""
    logger.info("FSSAI expiry worker started at %s", datetime.utcnow().isoformat())
    try:
        supabase = _supabase_client()
        return scan_expiring_certs(supabase)
    except Exception as exc:
        logger.error("FSSAI expiry worker error: %s", exc)
        if self is not None:
            raise self.retry(exc=exc)
        raise


if _HAS_CELERY:
    check_fssai_expiry = _celery_app.task(
        bind=True,
        name="app.workers.fssai_expiry.check_fssai_expiry",
        max_retries=3,
        default_retry_delay=300,
    )(_check_fssai_expiry_fn)
else:
    check_fssai_expiry = _check_fssai_expiry_fn
