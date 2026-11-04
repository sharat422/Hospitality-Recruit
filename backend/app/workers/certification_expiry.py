"""Daily unified certificate expiry and renewal reminders."""

from __future__ import annotations

import logging
from datetime import date, datetime

try:
    from app.celery_app import celery_app as _celery_app
    _HAS_CELERY = True
except ImportError:
    _celery_app = None
    _HAS_CELERY = False

from app.core.config import settings
from supabase import create_client

logger = logging.getLogger(__name__)


def _db():
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY)


def _twilio():
    try:
        from twilio.rest import Client
        return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    except Exception:
        return None


def _phone(value: str | None) -> str | None:
    if not value: return None
    value = value.strip()
    return value if value.startswith("+") else f"+91{value.lstrip('0')}"


def _send(client, channel: str, phone: str | None, body: str) -> str | None:
    phone = _phone(phone)
    if not client or not phone: return None
    if channel == "WHATSAPP":
        source = settings.TWILIO_WHATSAPP_NUMBER
        source = source if source.startswith("whatsapp:") else f"whatsapp:{source}"
        target = f"whatsapp:{phone}"
    else:
        source, target = settings.TWILIO_PHONE_NUMBER, phone
    return client.messages.create(body=body, from_=source, to=target).sid


def _tier(days_remaining: int, thresholds: list[int]) -> int | None:
    candidates = [threshold for threshold in thresholds if days_remaining <= threshold]
    return min(candidates) if candidates else None


def _message(name: str, label: str, expiry: str, days_remaining: int) -> str:
    if days_remaining < 0:
        return f"URGENT: {name}, your {label} expired on {expiry}. Upload the renewed certificate now. - HospRecruit"
    return f"{name}, your {label} expires in {days_remaining} days ({expiry}). Please start renewal. - HospRecruit"


def _already_sent(db, source_type: str, source_id: str, threshold: int, channel: str, recipient: str) -> bool:
    rows = (db.table("certification_reminders").select("id")
            .eq("source_type", source_type).eq("source_id", source_id)
            .eq("threshold_days", threshold).eq("channel", channel)
            .eq("recipient_type", recipient).eq("status", "SENT").limit(1).execute().data or [])
    return bool(rows)


def _record(db, row: dict, threshold: int, channel: str, recipient: str,
            status: str, sid: str | None = None, error: str | None = None):
    db.table("certification_reminders").upsert({
        "org_id": row["org_id"], "source_type": row["source_type"], "source_id": row["id"],
        "employee_id": row.get("employee_id"), "threshold_days": threshold,
        "recipient_type": recipient, "channel": channel, "status": status,
        "provider_message_id": sid, "error_message": error,
        "sent_at": datetime.utcnow().isoformat() if status == "SENT" else None,
    }, on_conflict="source_type,source_id,threshold_days,channel,recipient_type").execute()


def scan_certification_expiry(db) -> dict:
    stats = {"scanned": 0, "sent": 0, "skipped": 0, "failed": 0, "expired": 0}
    client = _twilio()
    settings_rows = db.table("certification_alert_settings").select("*").execute().data or []
    by_org = {row["org_id"]: row for row in settings_rows}
    general = (db.table("employee_certifications")
               .select("id,org_id,employee_id,expiry_date,status,certification_types(code,name)")
               .in_("status", ["VERIFIED","RENEWAL_DUE"]).not_.is_("expiry_date", "null").execute().data or [])
    for row in general:
        row["source_type"] = "EMPLOYEE_CERT"
        typ = row.get("certification_types") or {}
        row["label"] = typ.get("name") or typ.get("code") or "certificate"
    fssai = (db.table("fssai_certificates").select(
              "id,org_id,candidate_id,candidate_phone,cert_type,expiry_date,status")
              .eq("status", "ACTIVE").not_.is_("expiry_date", "null").execute().data or [])
    for row in fssai:
        row.update({"source_type": "FSSAI", "employee_id": None,
                    "label": str(row.get("cert_type") or "FSSAI").replace("_", " ").title()})
    for row in general + fssai:
        stats["scanned"] += 1
        try:
            days = (date.fromisoformat(str(row["expiry_date"])[:10]) - date.today()).days
            config = by_org.get(row["org_id"], {})
            threshold = _tier(days, config.get("reminder_days") or [90,60,30,7,0])
            if threshold is None: continue
            employee = {}
            if row.get("employee_id"):
                employees = (db.table("users").select("id,full_name,phone,manager_id")
                             .eq("id", row["employee_id"]).limit(1).execute().data or [])
                employee = employees[0] if employees else {}
            elif row.get("candidate_id"):
                candidates = (db.table("candidates").select("full_name,first_name,phone,user_id")
                              .eq("id", row["candidate_id"]).limit(1).execute().data or [])
                employee = candidates[0] if candidates else {}
                row["employee_id"] = employee.get("user_id")
                if employee.get("user_id"):
                    users = (db.table("users").select("id,full_name,phone,manager_id")
                             .eq("id", employee["user_id"]).limit(1).execute().data or [])
                    if users:
                        employee = {**employee, **users[0]}
            if row.get("candidate_phone") and not employee.get("phone"): employee["phone"] = row["candidate_phone"]
            name = employee.get("full_name") or employee.get("first_name") or "Employee"
            recipients = []
            if config.get("notify_employee", True): recipients.append(("EMPLOYEE", employee.get("phone")))
            if config.get("notify_manager", True) and employee.get("manager_id"):
                managers = db.table("users").select("phone").eq("id", employee["manager_id"]).limit(1).execute().data or []
                recipients.append(("MANAGER", managers[0].get("phone") if managers else None))
            channels = ["SMS","WHATSAPP"] if config.get("preferred_channel") == "BOTH" else [config.get("preferred_channel", "SMS")]
            for recipient, phone in recipients:
                for channel in channels:
                    if _already_sent(db, row["source_type"], row["id"], threshold, channel, recipient):
                        stats["skipped"] += 1; continue
                    if not phone:
                        _record(db, row, threshold, channel, recipient, "SKIPPED", error="No phone number")
                        stats["skipped"] += 1; continue
                    try:
                        sid = _send(client, channel, phone, _message(name, row["label"], row["expiry_date"], days))
                        _record(db, row, threshold, channel, recipient, "SENT" if sid else "FAILED", sid, None if sid else "Provider unavailable")
                        stats["sent" if sid else "failed"] += 1
                    except Exception as exc:
                        _record(db, row, threshold, channel, recipient, "FAILED", error=str(exc)); stats["failed"] += 1
            if days < 0:
                table = "employee_certifications" if row["source_type"] == "EMPLOYEE_CERT" else "fssai_certificates"
                db.table(table).update({"status":"EXPIRED","updated_at":datetime.utcnow().isoformat()}).eq("id",row["id"]).execute()
                stats["expired"] += 1
            elif days <= 30 and row["source_type"] == "EMPLOYEE_CERT" and row.get("status") == "VERIFIED":
                db.table("employee_certifications").update({"status":"RENEWAL_DUE"}).eq("id",row["id"]).execute()
        except Exception as exc:
            logger.error("Certificate expiry processing failed for %s: %s", row.get("id"), exc); stats["failed"] += 1
    return stats


def _run(self=None):
    try: return scan_certification_expiry(_db())
    except Exception as exc:
        if self is not None: raise self.retry(exc=exc)
        raise


if _HAS_CELERY:
    check_certification_expiry = _celery_app.task(bind=True,
        name="app.workers.certification_expiry.check_certification_expiry",
        max_retries=3, default_retry_delay=300)(_run)
else:
    check_certification_expiry = _run
