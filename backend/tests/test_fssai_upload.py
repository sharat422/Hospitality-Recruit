"""
Tests for FSSAI certificate upload API + expiry worker.

Strategy
--------
- All Supabase calls use MockSupabase from conftest (same as other test files).
- S3 service runs in sandbox mode (no AWS_S3_BUCKET set in test env).
- Celery worker logic is tested via scan_expiring_certs() directly (no broker needed).
- Twilio calls are mocked.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from tests.conftest import ADMIN_ID

# ─── Fixed test IDs ───────────────────────────────────────────────────────────
ORG_ID       = "aaaa1111-bbbb-cccc-dddd-eeee11112222"
CANDIDATE_ID = "bbbb2222-cccc-dddd-eeee-ffff22223333"
CERT_ID      = "cccc3333-dddd-eeee-ffff-aaaa33334444"
S3_KEY       = "fssai-certificates/fssai_license/cccc3333-dddd-eeee-ffff-aaaa33334444/abc.pdf"

_ORG_ROW    = [{"org_id": ORG_ID}]
_CERT_ROW   = [{
    "id": CERT_ID, "org_id": ORG_ID, "cert_type": "FSSAI_LICENSE",
    "expiry_date": "2027-01-01", "status": "ACTIVE",
    "license_number": "12345678901234",
}]
_CERT_WITH_S3 = [{**_CERT_ROW[0], "s3_key": S3_KEY, "upload_token": "tok-abc"}]
_UPDATE_ROW = [{"id": CERT_ID}]
_AUDIT_ROW  = []


# ═════════════════════════════════════════════════════════════════════════════
# 1. S3 service — pure unit tests (sandbox mode)
# ═════════════════════════════════════════════════════════════════════════════

class TestFSSAIS3Service:
    def test_sandbox_generate_upload_url(self):
        from app.services.fssai_s3_service import FSSAIStorageService
        svc = FSSAIStorageService()   # sandbox (no bucket)
        result = svc.generate_upload_url(CERT_ID, "FSSAI_LICENSE", "cert.pdf", "application/pdf")
        assert result["sandbox"] is True
        assert "upload_url" in result
        assert result["s3_key"].startswith("fssai-certificates/fssai_license/")
        assert result["s3_key"].endswith(".pdf")
        assert result["expires_in"] == 300
        assert result["region"] == "ap-south-1"

    def test_sandbox_generate_download_url(self):
        from app.services.fssai_s3_service import FSSAIStorageService
        svc = FSSAIStorageService()
        url = svc.generate_download_url(S3_KEY)
        assert S3_KEY in url

    def test_invalid_content_type_raises(self):
        from app.services.fssai_s3_service import FSSAIStorageService
        svc = FSSAIStorageService()
        with pytest.raises(ValueError, match="not allowed"):
            svc.generate_upload_url(CERT_ID, "FSSAI_LICENSE", "cert.pdf", "text/plain")

    def test_extension_extraction(self):
        from app.services.fssai_s3_service import FSSAIStorageService
        assert FSSAIStorageService._safe_extension("certificate.jpg") == ".jpg"
        assert FSSAIStorageService._safe_extension("no_extension")    == ".pdf"
        assert FSSAIStorageService._safe_extension("a.JPEG")          == ".jpeg"

    def test_public_url_format(self):
        from app.services.fssai_s3_service import FSSAIStorageService
        svc = FSSAIStorageService()  # sandbox
        url = svc.public_url(S3_KEY)
        assert S3_KEY in url

    def test_all_cert_types_produce_correct_s3_prefix(self):
        from app.services.fssai_s3_service import FSSAIStorageService
        svc = FSSAIStorageService()
        for ct in ["BASIC_FOOD_HYGIENE", "FOSTAC", "FSSAI_LICENSE", "ALCOHOL_LICENSE_FORM_FL"]:
            r = svc.generate_upload_url(CERT_ID, ct, "file.pdf", "application/pdf")
            assert ct.lower() in r["s3_key"]


# ═════════════════════════════════════════════════════════════════════════════
# 2. POST /fssai/certificates — create cert
# ═════════════════════════════════════════════════════════════════════════════

class TestCreateCert:
    def _make_payload(self, cert_type="FSSAI_LICENSE", with_file=False):
        payload = {
            "cert_type":       cert_type,
            "license_number":  "12345678901234",
            "licensed_entity": "Grand Hotel Mumbai",
            "expiry_date":     "2027-06-30",
            "state_code":      "MH",
            "candidate_phone": "+919876543210",
            "recruiter_email": "hr@grandhotel.in",
        }
        if with_file:
            payload["filename"]     = "license.pdf"
            payload["content_type"] = "application/pdf"
        return payload

    def test_create_fssai_license_happy(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",               _ORG_ROW)
        sb.configure("fssai_certificates",  _CERT_ROW)   # INSERT
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/fssai/certificates", json=self._make_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == CERT_ID
        assert body["cert_type"] == "FSSAI_LICENSE"

    def test_create_with_presigned_url(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",               _ORG_ROW)
        sb.configure("fssai_certificates",  _CERT_ROW)         # INSERT
        sb.configure("fssai_certificates",  _UPDATE_ROW)        # UPDATE s3_key
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/fssai/certificates", json=self._make_payload(with_file=True))
        assert resp.status_code == 201
        body = resp.json()
        assert "upload" in body
        assert "upload_url" in body["upload"]
        assert body["upload"]["sandbox"] is True
        assert body["upload"]["region"] == "ap-south-1"

    def test_create_basic_food_hygiene(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",               _ORG_ROW)
        sb.configure("fssai_certificates",  _CERT_ROW)
        sb.configure("candidates",          [{"id": CANDIDATE_ID}])  # fssai_trained update
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/fssai/certificates", json={
            "cert_type":        "BASIC_FOOD_HYGIENE",
            "candidate_id":     CANDIDATE_ID,
            "fostac_course":    "BASIC_HYGIENE",
            "training_provider": "SafeFood Training Centre",
            "expiry_date":      "2026-12-31",
        })
        assert resp.status_code == 201

    def test_create_alcohol_license(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",               _ORG_ROW)
        sb.configure("fssai_certificates",  _CERT_ROW)
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/fssai/certificates", json={
            "cert_type":            "ALCOHOL_LICENSE_FORM_FL",
            "alcohol_license_number": "MH-FL-2024-12345",
            "alcohol_license_form": "FL-11",
            "issuing_authority":    "Maharashtra State Excise Dept",
            "expiry_date":          "2025-03-31",
            "state_code":           "MH",
        })
        assert resp.status_code == 201

    def test_create_rejects_invalid_cert_type(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.post("/api/v1/fssai/certificates", json={
            "cert_type":   "INVALID_TYPE",
            "expiry_date": "2027-01-01",
        })
        assert resp.status_code == 422

    def test_create_rejects_bad_license_number(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.post("/api/v1/fssai/certificates", json={
            "cert_type":      "FSSAI_LICENSE",
            "license_number": "1234",   # only 4 digits — invalid
            "expiry_date":    "2027-01-01",
        })
        assert resp.status_code == 422

    def test_create_rejects_bad_content_type(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.post("/api/v1/fssai/certificates", json={
            "cert_type":    "FSSAI_LICENSE",
            "expiry_date":  "2027-01-01",
            "filename":     "cert.pdf",
            "content_type": "text/plain",   # not allowed
        })
        assert resp.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# 3. PATCH /certificates/{id}/confirm-upload
# ═════════════════════════════════════════════════════════════════════════════

class TestConfirmUpload:
    def test_confirm_upload_happy(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",               _ORG_ROW)
        sb.configure("fssai_certificates",  _CERT_WITH_S3)   # SELECT cert
        sb.configure("fssai_certificates",  _UPDATE_ROW)     # UPDATE doc_url
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.patch(f"/api/v1/fssai/certificates/{CERT_ID}/confirm-upload",
                            json={"s3_key": S3_KEY})
        assert resp.status_code == 200
        body = resp.json()
        assert body["confirmed"] is True
        assert body["cert_id"]  == CERT_ID
        assert "doc_url" in body

    def test_confirm_wrong_s3_key_rejected(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",              _ORG_ROW)
        sb.configure("fssai_certificates", _CERT_WITH_S3)   # has s3_key = S3_KEY

        resp = client.patch(f"/api/v1/fssai/certificates/{CERT_ID}/confirm-upload",
                            json={"s3_key": "fssai-certificates/other/different.pdf"})
        assert resp.status_code == 400
        assert "s3_key" in resp.json()["detail"].lower()

    def test_confirm_cert_not_found(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",              _ORG_ROW)
        sb.configure("fssai_certificates", [])   # not found

        resp = client.patch(f"/api/v1/fssai/certificates/{CERT_ID}/confirm-upload",
                            json={"s3_key": S3_KEY})
        assert resp.status_code == 404


# ═════════════════════════════════════════════════════════════════════════════
# 4. GET /certificates/expiring
# ═════════════════════════════════════════════════════════════════════════════

class TestExpiring:
    def test_expiring_returns_list(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",              _ORG_ROW)
        sb.configure("fssai_certificates", _CERT_ROW)

        resp = client.get("/api/v1/fssai/certificates/expiring?days=30")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_expiring_empty(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",              _ORG_ROW)
        sb.configure("fssai_certificates", [])

        resp = client.get("/api/v1/fssai/certificates/expiring?days=30")
        assert resp.status_code == 200
        assert resp.json() == []


# ═════════════════════════════════════════════════════════════════════════════
# 5. GET /certificates/{id}/download-url
# ═════════════════════════════════════════════════════════════════════════════

class TestDownloadUrl:
    def test_download_url_sandbox(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",              _ORG_ROW)
        sb.configure("fssai_certificates", _CERT_WITH_S3)

        resp = client.get(f"/api/v1/fssai/certificates/{CERT_ID}/download-url")
        assert resp.status_code == 200
        body = resp.json()
        assert "download_url" in body
        assert body["sandbox"] is True
        assert body["expires_in"] == 3600

    def test_download_url_no_file(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",              _ORG_ROW)
        # Cert without s3_key
        sb.configure("fssai_certificates", [{**_CERT_ROW[0], "s3_key": None}])

        resp = client.get(f"/api/v1/fssai/certificates/{CERT_ID}/download-url")
        assert resp.status_code == 404


# ═════════════════════════════════════════════════════════════════════════════
# 6. Expiry worker logic (scan_expiring_certs)
# ═════════════════════════════════════════════════════════════════════════════

class TestExpiryWorker:
    """Test scan_expiring_certs() with a fully mocked Supabase and Twilio."""

    def _make_supabase(self, rows_30d=None, rows_7d=None, expired=None):
        """Build a mock supabase that returns given rows for each tier."""
        sb = MagicMock()
        call_results = [rows_30d or [], rows_7d or [], expired or []]

        call_idx = [0]
        def table_side_effect(name):
            chain = MagicMock()
            chain.select.return_value = chain
            chain.eq.return_value     = chain
            chain.gte.return_value    = chain
            chain.lte.return_value    = chain
            chain.lt.return_value     = chain
            chain.update.return_value = chain

            result = MagicMock()
            result.data = call_results[call_idx[0] % len(call_results)]
            call_idx[0] += 1
            chain.execute.return_value = result
            return chain

        sb.table.side_effect = table_side_effect
        return sb

    def test_worker_alerted_30d(self):
        from app.workers.fssai_expiry import scan_expiring_certs

        cert = {
            "id": CERT_ID, "cert_type": "FSSAI_LICENSE",
            "licensed_entity": "Test Hotel",
            "expiry_date": (datetime.utcnow() + timedelta(days=20)).strftime("%Y-%m-%d"),
            "candidate_phone": "+919999988888",
            "recruiter_email": None,
        }
        sb = self._make_supabase(rows_30d=[cert])

        with patch("app.workers.fssai_expiry._twilio_client", return_value=None):
            stats = scan_expiring_certs(sb)

        assert stats["alerted_30d"] == 1
        assert stats["errors"] == 0

    def test_worker_marks_expired(self):
        from app.workers.fssai_expiry import scan_expiring_certs

        cert = {
            "id": CERT_ID, "cert_type": "FSSAI_LICENSE",
            "licensed_entity": "Old Hotel",
            "expiry_date": (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d"),
            "candidate_phone": None,
            "recruiter_email": None,
        }
        sb = self._make_supabase(expired=[cert])

        with patch("app.workers.fssai_expiry._twilio_client", return_value=None):
            stats = scan_expiring_certs(sb)

        assert stats["marked_expired"] == 1

    def test_worker_sends_sms(self):
        from app.workers.fssai_expiry import scan_expiring_certs

        cert = {
            "id": CERT_ID, "cert_type": "FOSTAC",
            "licensed_entity": "Test Hotel",
            "expiry_date": (datetime.utcnow() + timedelta(days=5)).strftime("%Y-%m-%d"),
            "candidate_phone": "+919999988888",
            "recruiter_email": None,
        }
        # Row appears in both 30d AND 7d windows
        sb = self._make_supabase(rows_30d=[cert], rows_7d=[cert])

        twilio_mock = MagicMock()
        twilio_mock.messages.create.return_value = MagicMock(sid="SM123")

        with patch("app.workers.fssai_expiry._twilio_client", return_value=twilio_mock), \
             patch("app.workers.fssai_expiry.settings") as mock_settings:
            mock_settings.TWILIO_PHONE_NUMBER = "+1234567890"
            stats = scan_expiring_certs(sb)

        # SMS sent for 30d + 7d tier
        assert twilio_mock.messages.create.call_count >= 1

    def test_worker_handles_db_error_gracefully(self):
        from app.workers.fssai_expiry import scan_expiring_certs

        sb = MagicMock()
        # Make all queries raise
        chain = MagicMock()
        chain.select.return_value  = chain
        chain.eq.return_value      = chain
        chain.gte.return_value     = chain
        chain.lte.return_value     = chain
        chain.lt.return_value      = chain
        chain.execute.side_effect  = Exception("DB unavailable")
        sb.table.return_value      = chain

        with patch("app.workers.fssai_expiry._twilio_client", return_value=None):
            stats = scan_expiring_certs(sb)

        # Worker should return without raising; errors logged
        assert isinstance(stats, dict)
        assert "errors" in stats

    def test_sms_message_contains_expiry_date(self):
        from app.workers.fssai_expiry import _build_sms
        cert = {
            "cert_type": "FSSAI_LICENSE",
            "licensed_entity": "Grand Hotel",
            "expiry_date": "2026-12-31",
        }
        msg = _build_sms(cert, 45, "30D")
        assert "2026-12-31" in msg
        assert "Grand Hotel" in msg

    def test_sms_expired_message_urgent(self):
        from app.workers.fssai_expiry import _build_sms
        cert = {
            "cert_type": "FSSAI_LICENSE",
            "licensed_entity": "Old Dhaba",
            "expiry_date": "2026-01-01",
        }
        msg = _build_sms(cert, 0, "EXPIRED")
        assert "expired" in msg.lower() or "EXPIRED" in msg
