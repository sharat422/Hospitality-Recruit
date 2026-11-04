"""Daily DPDP retention worker: delete only expired, non-held documents."""

from __future__ import annotations

import logging
from datetime import datetime

try:
    from app.celery_app import celery_app as _celery_app
    _HAS_CELERY = True
except ImportError:
    _celery_app = None
    _HAS_CELERY = False

from app.core.business_date import business_today
from app.core.config import settings
from app.services.s3_service import S3Service
from supabase import create_client

logger = logging.getLogger(__name__)


def _supabase_client():
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY)


def process_due_document_retention(supabase) -> dict:
    # Fires at 04:00 IST = 22:30 UTC the previous day. Using the UTC date
    # made the retention cutoff a day early, deleting documents one day
    # sooner than the policy allows — the wrong direction to err under DPDP.
    today = business_today().isoformat()
    stats = {"due": 0, "deleted": 0, "failed": 0}
    rows = (supabase.table("candidate_documents")
            .select("id,org_id,candidate_id,document_type,storage_key,retention_until,legal_hold")
            .eq("legal_hold", False).is_("erased_at", "null")
            .lt("retention_until", today).execute().data or [])
    stats["due"] = len(rows)
    storage = S3Service()
    for row in rows:
        now = datetime.utcnow().isoformat()
        try:
            result = storage.delete_objects([row.get("storage_key")] if row.get("storage_key") else [])
            if result.get("errors"):
                raise RuntimeError(str(result["errors"]))
            supabase.table("candidate_documents").update({
                "storage_key": "[ERASED]", "file_url": None,
                "status": "ERASED", "erased_at": now,
            }).eq("id", row["id"]).eq("org_id", row["org_id"]).eq("legal_hold", False).execute()
            supabase.table("dpdp_retention_actions").insert({
                "org_id": row["org_id"], "candidate_id": row.get("candidate_id"),
                "document_id": row["id"], "data_category": row.get("document_type") or "DOCUMENT",
                "action": "DELETE", "status": "COMPLETED", "completed_at": now,
                "scheduled_for": row.get("retention_until"),
                "legal_basis": "DPDP Act 2023 Section 8 — retention period expired",
            }).execute()
            supabase.table("india_compliance_audit_logs").insert({
                "org_id": row["org_id"], "actor_type": "SYSTEM",
                "action": "DPDP_RETENTION_DOCUMENT_DELETED",
                "entity_type": "candidate_document", "entity_id": row["id"],
                "law_reference": "DPDP Act 2023 Section 8",
                "metadata": {"retention_until": row.get("retention_until")},
            }).execute()
            stats["deleted"] += 1
        except Exception as exc:
            logger.error("DPDP retention deletion failed for %s: %s", row.get("id"), exc)
            stats["failed"] += 1
    return stats


def _run(self=None):
    try:
        return process_due_document_retention(_supabase_client())
    except Exception as exc:
        if self is not None:
            raise self.retry(exc=exc)
        raise


if _HAS_CELERY:
    process_dpdp_retention = _celery_app.task(
        bind=True, name="app.workers.dpdp_retention.process_dpdp_retention",
        max_retries=3, default_retry_delay=300,
    )(_run)
else:
    process_dpdp_retention = _run
