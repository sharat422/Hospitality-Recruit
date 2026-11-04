"""
Celery application — HospRecruit background task queue.
Broker: Redis (same instance as FastAPI cache).
Beat schedule: FSSAI expiry check daily at 09:00 IST (03:30 UTC).
"""

from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "hosprecruit",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.fssai_expiry",
        "app.workers.identity_document_expiry",
        "app.workers.dpdp_retention",
        "app.workers.certification_expiry",
        "app.workers.scheduled_reports",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,           # re-queue on worker crash
    worker_prefetch_multiplier=1,  # one task at a time per worker
    beat_schedule={
        # Unified FSSAI + employee certificate scan, daily 09:00 IST.
        "certification-expiry-daily": {
            "task": "app.workers.certification_expiry.check_certification_expiry",
            "schedule": crontab(hour=3, minute=30),
        },
        "identity-document-expiry-daily": {
            "task": "app.workers.identity_document_expiry.check_identity_document_expiry",
            "schedule": crontab(hour=3, minute=45),
        },
        "dpdp-retention-daily": {
            "task": "app.workers.dpdp_retention.process_dpdp_retention",
            "schedule": crontab(hour=4, minute=0),
        },
        "scheduled-reports-every-15-minutes": {
            "task": "app.workers.scheduled_reports.run_scheduled_reports",
            "schedule": crontab(minute="*/15"),
        },
    },
)
