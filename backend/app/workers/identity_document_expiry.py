"""Daily India identity-document expiry alerts (Passport/Driving Licence/etc.)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

try:
    from app.celery_app import celery_app as _celery_app
    _HAS_CELERY = True
except ImportError:
    _celery_app = None
    _HAS_CELERY = False

from app.core.business_date import business_today
from app.core.config import settings
from supabase import create_client

logger = logging.getLogger(__name__)


def _supabase_client():
    key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
    return create_client(settings.SUPABASE_URL, key)


def _twilio_client():
    try:
        from twilio.rest import Client
        return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    except Exception:
        return None


def _send_sms(client, phone: str | None, body: str) -> bool:
    if not client or not phone:
        return False
    number = phone if phone.startswith("+") else f"+91{phone.lstrip('0')}"
    client.messages.create(body=body, from_=settings.TWILIO_PHONE_NUMBER, to=number)
    return True


def _message(row: dict, tier: str) -> str:
    label = str(row.get("doc_type") or "identity document").replace("_", " ").title()
    expiry = row.get("doc_expiry_date")
    if tier == "EXPIRED":
        return f"URGENT: Your {label} expired on {expiry}. Please upload a renewed document. - HospRecruit"
    prefix = "URGENT: " if tier == "7D" else ""
    return f"{prefix}Your {label} expires on {expiry}. Please renew and upload it in the compliance portal. - HospRecruit"


def _candidate_phone(supabase, candidate_id: str | None) -> str | None:
    if not candidate_id:
        return None
    rows = (supabase.table("candidates").select("phone").eq("id", candidate_id).limit(1).execute().data or [])
    return rows[0].get("phone") if rows else None


def _audit(supabase, row: dict, action: str):
    supabase.table("india_compliance_audit_logs").insert({
        "org_id": row.get("org_id"),
        "actor_type": "SYSTEM",
        "action": action,
        "entity_type": "identity_verification",
        "entity_id": row.get("id"),
        "metadata": {"doc_type": row.get("doc_type"), "expiry_date": row.get("doc_expiry_date")},
        "law_reference": "DPDP Act 2023 / applicable identity document rules",
    }).execute()


def scan_expiring_identity_documents(supabase) -> dict:
    # Fires at 03:45 IST = 22:15 UTC the previous day, so the UTC date was
    # always yesterday. doc_expiry_date is a business date.
    today = business_today()
    today_s = today.isoformat()
    client = _twilio_client()
    stats = {"alerted_30d": 0, "alerted_7d": 0, "marked_expired": 0, "errors": 0}

    tiers = (
        ("30D", "alert_30_day_sent", today_s, (today + timedelta(days=30)).isoformat()),
        ("7D", "alert_7_day_sent", today_s, (today + timedelta(days=7)).isoformat()),
    )
    for tier, flag, start, end in tiers:
        try:
            rows = (supabase.table("india_identity_verifications")
                    .select("id,org_id,candidate_id,doc_type,doc_expiry_date")
                    .eq("status", "VERIFIED").eq(flag, False)
                    .gte("doc_expiry_date", start).lte("doc_expiry_date", end).execute().data or [])
        except Exception as exc:
            logger.error("Identity %s expiry query failed: %s", tier, exc)
            stats["errors"] += 1
            continue
        for row in rows:
            try:
                _send_sms(client, _candidate_phone(supabase, row.get("candidate_id")), _message(row, tier))
                supabase.table("india_identity_verifications").update({flag: True, "updated_at": datetime.utcnow().isoformat()}).eq("id", row["id"]).execute()
                _audit(supabase, row, f"IDENTITY_EXPIRY_{tier}_ALERTED")
                stats["alerted_30d" if tier == "30D" else "alerted_7d"] += 1
            except Exception as exc:
                logger.error("Identity expiry alert failed for %s: %s", row.get("id"), exc)
                stats["errors"] += 1

    try:
        expired = (supabase.table("india_identity_verifications")
                   .select("id,org_id,candidate_id,doc_type,doc_expiry_date")
                   .eq("status", "VERIFIED").eq("alert_expired_sent", False)
                   .lt("doc_expiry_date", today_s).execute().data or [])
    except Exception as exc:
        logger.error("Identity expired query failed: %s", exc)
        expired = []
        stats["errors"] += 1
    for row in expired:
        try:
            _send_sms(client, _candidate_phone(supabase, row.get("candidate_id")), _message(row, "EXPIRED"))
            supabase.table("india_identity_verifications").update({
                "status": "EXPIRED", "alert_expired_sent": True,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", row["id"]).execute()
            _audit(supabase, row, "IDENTITY_DOCUMENT_EXPIRED")
            stats["marked_expired"] += 1
        except Exception as exc:
            logger.error("Identity expiry update failed for %s: %s", row.get("id"), exc)
            stats["errors"] += 1
    return stats


def _run(self=None):
    try:
        return scan_expiring_identity_documents(_supabase_client())
    except Exception as exc:
        if self is not None:
            raise self.retry(exc=exc)
        raise


if _HAS_CELERY:
    check_identity_document_expiry = _celery_app.task(
        bind=True, name="app.workers.identity_document_expiry.check_identity_document_expiry",
        max_retries=3, default_retry_delay=300,
    )(_run)
else:
    check_identity_document_expiry = _run

