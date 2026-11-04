"""Regression tests for India compliance identifier and retention hardening."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


ORG_ID = "11111111-2222-3333-4444-555555555555"
CANDIDATE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
VERIFICATION_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"


def test_manual_pan_is_masked_before_persistence(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", [{"org_id": ORG_ID}])
    sb.configure("india_identity_verifications", [{
        "id": VERIFICATION_ID,
        "candidate_id": CANDIDATE_ID,
        "doc_type": "PAN",
        "pan_number": "ABCDE****F",
        "pan_masked": "ABCDE****F",
        "status": "PENDING",
    }])
    sb.configure("india_compliance_audit_logs", [])

    response = client.post("/api/v1/india-compliance/identity-verification", json={
        "candidate_id": CANDIDATE_ID,
        "doc_type": "PAN",
        "pan_number": "ABCDE1234F",
    })

    assert response.status_code == 201
    encoded = response.text
    assert "ABCDE1234F" not in encoded
    assert response.json()["pan_masked"] == "ABCDE****F"


def test_manual_identity_rejects_full_aadhaar(client_as_admin):
    client, _ = client_as_admin
    response = client.post("/api/v1/india-compliance/identity-verification", json={
        "candidate_id": CANDIDATE_ID,
        "doc_type": "AADHAAR",
        "aadhaar_last4": "234512349012",
    })
    assert response.status_code == 422


def test_professional_tax_record_is_calculated_and_saved(client_as_admin):
    client, sb = client_as_admin
    sb.configure("users", [{"org_id": ORG_ID}])
    sb.configure("professional_tax_slabs", [{
        "state_code": "MH", "state_name": "Maharashtra",
        "slab_min_salary_inr": 10001, "slab_max_salary_inr": None,
        "pt_monthly_inr": 200, "pt_february_inr": 300,
    }])
    sb.configure("professional_tax_records", [{
        "id": "pt-1", "candidate_id": CANDIDATE_ID,
        "pt_period": "2026-02", "pt_deducted_inr": 300,
    }])
    sb.configure("india_compliance_audit_logs", [])

    response = client.post("/api/v1/india-compliance/professional-tax/records", json={
        "candidate_id": CANDIDATE_ID,
        "state_code": "MH",
        "monthly_salary_inr": 25000,
        "pt_period": "2026-02",
    })
    assert response.status_code == 201
    assert response.json()["pt_deducted_inr"] == 300


def test_professional_tax_period_validation(client_as_admin):
    client, _ = client_as_admin
    response = client.post("/api/v1/india-compliance/professional-tax/records", json={
        "candidate_id": CANDIDATE_ID,
        "state_code": "MH",
        "monthly_salary_inr": 25000,
        "pt_period": "Feb-2026",
    })
    assert response.status_code == 422


def _worker_supabase(rows_30=None, rows_7=None, expired=None):
    """Return a fluent mock with ordered identity query results."""
    sb = MagicMock()
    results = iter([rows_30 or [], rows_7 or [], expired or []])

    def table(name):
        chain = MagicMock()
        for method in ("select", "eq", "gte", "lte", "lt", "limit", "update", "insert"):
            getattr(chain, method).return_value = chain
        result = MagicMock()
        if name == "india_identity_verifications" and chain.select.called is False:
            pass
        chain.execute.side_effect = lambda: result
        if name == "india_identity_verifications":
            result.data = next(results, [])
        elif name == "candidates":
            result.data = [{"phone": "+919999988888"}]
        else:
            result.data = []
        return chain

    sb.table.side_effect = table
    return sb


def test_identity_expiry_worker_marks_expired():
    from app.workers.identity_document_expiry import scan_expiring_identity_documents

    row = {
        "id": VERIFICATION_ID, "org_id": ORG_ID,
        "candidate_id": CANDIDATE_ID, "doc_type": "PASSPORT",
        "doc_expiry_date": (datetime.utcnow() - timedelta(days=1)).date().isoformat(),
    }
    sb = _worker_supabase(expired=[row])
    with patch("app.workers.identity_document_expiry._twilio_client", return_value=None):
        stats = scan_expiring_identity_documents(sb)
    assert stats["marked_expired"] == 1
    assert stats["errors"] == 0


def test_s3_delete_objects_sandbox_never_calls_aws():
    from app.services.s3_service import S3Service

    service = S3Service()
    result = service.delete_objects(["candidate-documents/example.pdf", "local://old.pdf"])
    assert result["requested"] == 2
    assert result["errors"] == []
    assert result["sandbox"] is True


def test_dpdp_retention_classifies_statutory_and_ordinary_documents():
    from app.services.dpdp_service import classify_document_retention

    statutory = classify_document_retention({
        "document_type": "FORM_16", "created_at": "2026-04-01",
    })
    ordinary = classify_document_retention({
        "document_type": "RESUME", "created_at": "2026-04-01",
    })
    assert statutory["retain"] is True
    assert statutory["retention_until"] == "2034-04-01"
    assert ordinary["retain"] is False


def test_existing_legal_hold_always_wins():
    from app.services.dpdp_service import classify_document_retention

    result = classify_document_retention({
        "document_type": "RESUME", "legal_hold": True,
        "legal_hold_basis": "Pending labour dispute",
    })
    assert result["retain"] is True
    assert result["legal_basis"] == "Pending labour dispute"


def test_fssai_upload_contract_requires_server_side_encryption():
    from app.services.fssai_s3_service import FSSAIStorageService

    result = FSSAIStorageService().generate_upload_url(
        "cert-id", "FSSAI_LICENSE", "certificate.pdf", "application/pdf"
    )
    assert result["region"] == "ap-south-1"
    assert result["upload_headers"]["x-amz-server-side-encryption"] in {"AES256", "aws:kms"}
