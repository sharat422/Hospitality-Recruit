"""Focused tests for unified employee certification management."""

from datetime import timedelta
from unittest.mock import MagicMock

from app.core.business_date import business_today
from app.services.certification_service import (
    certificate_state,
    normalize_employee_certificate,
    normalize_fssai_certificate,
)
from app.services.s3_service import S3Service
from app.workers.certification_expiry import _already_sent, _record, _tier


def test_certificate_state_marks_expired():
    # business_today(), not date.today(): the test must use the same calendar
    # as the code, or it fails on a server whose local zone is not IST.
    expiry = (business_today() - timedelta(days=1)).isoformat()
    assert certificate_state(expiry, "VERIFIED") == {
        "status": "EXPIRED", "days_remaining": -1,
    }


def test_certificate_state_marks_30_day_renewal_window():
    expiry = (business_today() + timedelta(days=30)).isoformat()
    assert certificate_state(expiry, "VERIFIED")["status"] == "RENEWAL_DUE"


def test_certificate_without_expiry_preserves_status():
    assert certificate_state(None, "VERIFIED") == {
        "status": "VERIFIED", "days_remaining": None,
    }


def test_employee_certificate_normalization_accepts_supabase_relation_list():
    row = {
        "id": "cert-1", "status": "VERIFIED", "expiry_date": None,
        "certification_types": [{"code": "FIRST_AID", "name": "First Aid"}],
    }
    result = normalize_employee_certificate(row)
    assert result["certification_code"] == "FIRST_AID"
    assert result["certification_name"] == "First Aid"
    assert result["source_type"] == "EMPLOYEE_CERT"


def test_fssai_active_normalizes_to_verified():
    result = normalize_fssai_certificate({
        "id": "food-1", "cert_type": "FOSTAC", "status": "ACTIVE", "expiry_date": None,
    })
    assert result["status"] == "VERIFIED"
    assert result["source_type"] == "FSSAI"


def test_reminder_tier_boundaries():
    thresholds = [90, 60, 30, 7, 0]
    assert _tier(91, thresholds) is None
    assert _tier(90, thresholds) == 90
    assert _tier(61, thresholds) == 90
    assert _tier(60, thresholds) == 60
    assert _tier(8, thresholds) == 30
    assert _tier(7, thresholds) == 7
    assert _tier(0, thresholds) == 0
    assert _tier(-1, thresholds) == 0


def test_only_sent_reminders_are_idempotent():
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value.data = [{"id": "reminder-1"}]
    db = MagicMock()
    db.table.return_value = chain
    assert _already_sent(db, "EMPLOYEE_CERT", "cert-1", 30, "SMS", "EMPLOYEE") is True
    chain.eq.assert_any_call("status", "SENT")


def test_reminder_record_uses_conflict_safe_upsert():
    chain = MagicMock()
    chain.upsert.return_value = chain
    chain.execute.return_value.data = [{"id": "reminder-1"}]
    db = MagicMock()
    db.table.return_value = chain
    _record(db, {"id": "cert-1", "org_id": "org-1", "source_type": "EMPLOYEE_CERT",
                 "employee_id": "employee-1"}, 30, "SMS", "EMPLOYEE", "FAILED",
            error="provider unavailable")
    assert chain.upsert.call_args.kwargs["on_conflict"] == (
        "source_type,source_id,threshold_days,channel,recipient_type"
    )


def test_certificate_upload_is_private_and_india_resident():
    service = S3Service()
    service.client = None
    service.bucket = ""
    result = service.generate_employee_certificate_upload_url(
        "org-1", "employee-1", "first-aid.pdf", "application/pdf",
    )
    assert result["region"] == "ap-south-1"
    assert result["storage_key"].startswith("employee-certificates/org-1/employee-1/")
    assert result["upload_headers"]["x-amz-server-side-encryption"] in {"AES256", "aws:kms"}


def test_private_download_rejects_path_traversal():
    service = S3Service()
    service.client = None
    service.bucket = ""
    try:
        service.generate_private_download_url("../another-tenant/document.pdf")
    except ValueError as exc:
        assert "Invalid storage key" in str(exc)
    else:
        raise AssertionError("Path traversal storage key was accepted")
