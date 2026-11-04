"""
Tests for India Data Localisation Enforcement.

Coverage:
  1. DataLocalizationError type and attributes
  2. validate_startup_config — correct region, wrong region, cross-border flags
  3. DataLocalizationGuard.validate_s3_region — hard block non-India
  4. DataLocalizationGuard.check_external_pii — Aadhaar/PAN never cross border,
     India services always allowed, non-India logged
  5. DataLocalizationGuard.log_file_upload — best-effort, never raises
  6. S3Service — India region enforced at construction
  7. FSSAI S3 service — region constant is ap-south-1
  8. KYC router — Aadhaar initiate + PAN verify guarded
  9. /data-localization endpoint
  10. /health endpoint includes localisation status
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

# ─── Test IDs ─────────────────────────────────────────────────────────────────
ORG_ID       = "aaaa1111-cccc-dddd-eeee-ffff11112222"
CANDIDATE_ID = "bbbbcccc-aaaa-bbbb-cccc-ddddeeeeffff"

_ORG_ROW   = [{"org_id": ORG_ID}]
_AUDIT_ROW = []

# ─── Settings mocks ──────────────────────────────────────────────────────────

def _settings(
    region              = "ap-south-1",
    bucket              = None,
    allow_cross_border  = False,
    justification       = None,
    anthropic_key       = "sk-test",
    openai_key          = None,
    surepass_token      = None,
):
    s = MagicMock()
    s.AWS_REGION                    = region
    s.AWS_S3_BUCKET                 = bucket
    s.ALLOW_PII_CROSS_BORDER        = allow_cross_border
    s.PII_CROSS_BORDER_JUSTIFICATION= justification
    s.ANTHROPIC_API_KEY             = anthropic_key
    s.OPENAI_API_KEY                = openai_key
    s.SUREPASS_API_TOKEN            = surepass_token
    return s


# ═════════════════════════════════════════════════════════════════════════════
# 1. DataLocalizationError
# ═════════════════════════════════════════════════════════════════════════════

class TestDataLocalizationError:
    def test_is_exception(self):
        from app.services.data_localization import DataLocalizationError
        e = DataLocalizationError("test message")
        assert isinstance(e, Exception)
        assert str(e) == "test message"

    def test_carries_pii_types(self):
        from app.services.data_localization import DataLocalizationError
        e = DataLocalizationError("blocked", pii_types=["AADHAAR"], service="OPENAI")
        assert e.pii_types == ["AADHAAR"]
        assert e.service == "OPENAI"

    def test_defaults(self):
        from app.services.data_localization import DataLocalizationError
        e = DataLocalizationError("x")
        assert e.pii_types == []
        assert e.service is None


# ═════════════════════════════════════════════════════════════════════════════
# 2. validate_startup_config
# ═════════════════════════════════════════════════════════════════════════════

class TestStartupConfig:
    def test_correct_india_region_passes(self):
        from app.services.data_localization import validate_startup_config
        result = validate_startup_config(_settings(region="ap-south-1", bucket="my-bucket"))
        assert result["ok"] is True
        assert result["issues"] == []

    def test_wrong_region_is_hard_violation(self):
        from app.services.data_localization import validate_startup_config
        result = validate_startup_config(_settings(region="us-east-1", bucket="my-bucket"))
        assert result["ok"] is False
        assert any("ap-south-1" in i for i in result["issues"])

    def test_eu_west_1_is_hard_violation(self):
        from app.services.data_localization import validate_startup_config
        result = validate_startup_config(_settings(region="eu-west-1", bucket="my-bucket"))
        assert result["ok"] is False

    def test_no_bucket_passes_with_warning(self):
        from app.services.data_localization import validate_startup_config
        result = validate_startup_config(_settings(bucket=None))
        assert result["ok"] is True
        assert any("AWS_S3_BUCKET" in w or "sandbox" in w.lower() for w in result["warnings"])

    def test_cross_border_true_without_justification_is_violation(self):
        from app.services.data_localization import validate_startup_config
        result = validate_startup_config(_settings(allow_cross_border=True, justification=None))
        assert result["ok"] is False
        assert any("PII_CROSS_BORDER_JUSTIFICATION" in i for i in result["issues"])

    def test_cross_border_true_with_justification_passes(self):
        from app.services.data_localization import validate_startup_config
        result = validate_startup_config(_settings(
            allow_cross_border=True,
            justification="Candidates granted CROSS_BORDER DPDP consent",
        ))
        assert result["ok"] is True

    def test_anthropic_without_cross_border_warns(self):
        from app.services.data_localization import validate_startup_config
        result = validate_startup_config(_settings(
            anthropic_key="sk-real", allow_cross_border=False,
        ))
        assert any("ANTHROPIC" in w or "anthropic" in w.lower() for w in result["warnings"])

    def test_openai_without_cross_border_warns(self):
        from app.services.data_localization import validate_startup_config
        result = validate_startup_config(_settings(openai_key="sk-openai"))
        assert any("OPENAI" in w or "openai" in w.lower() for w in result["warnings"])

    def test_no_surepass_warns(self):
        from app.services.data_localization import validate_startup_config
        result = validate_startup_config(_settings(surepass_token=None))
        assert any("SUREPASS" in w or "sandbox" in w.lower() for w in result["warnings"])

    def test_result_has_required_keys(self):
        from app.services.data_localization import validate_startup_config
        result = validate_startup_config(_settings())
        assert "ok" in result
        assert "issues" in result
        assert "warnings" in result


# ═════════════════════════════════════════════════════════════════════════════
# 3. DataLocalizationGuard — S3 region
# ═════════════════════════════════════════════════════════════════════════════

class TestS3RegionGuard:
    def _guard(self, region="ap-south-1"):
        from app.services.data_localization import DataLocalizationGuard
        return DataLocalizationGuard(_settings(region=region))

    def test_india_region_passes(self):
        g = self._guard()
        g.validate_s3_region("ap-south-1", "RESUME")  # must not raise

    def test_us_east_1_raises(self):
        from app.services.data_localization import DataLocalizationError
        g = self._guard()
        with pytest.raises(DataLocalizationError, match="ap-south-1"):
            g.validate_s3_region("us-east-1", "FSSAI_CERT")

    def test_eu_west_1_raises(self):
        from app.services.data_localization import DataLocalizationError
        g = self._guard()
        with pytest.raises(DataLocalizationError):
            g.validate_s3_region("eu-west-1", "KYC_AADHAAR")

    def test_ap_southeast_1_raises(self):
        from app.services.data_localization import DataLocalizationError
        g = self._guard()
        with pytest.raises(DataLocalizationError):
            g.validate_s3_region("ap-southeast-1", "RESUME")

    def test_validate_config_region_passes_india(self):
        g = self._guard("ap-south-1")
        g.validate_config_region()  # no exception

    def test_validate_config_region_raises_non_india(self):
        from app.services.data_localization import DataLocalizationError
        g = self._guard("us-east-1")
        with pytest.raises(DataLocalizationError):
            g.validate_config_region()


# ═════════════════════════════════════════════════════════════════════════════
# 4. DataLocalizationGuard — external PII check
# ═════════════════════════════════════════════════════════════════════════════

class TestExternalPIIGuard:
    def _guard(self, allow_cross_border=False, justification=None):
        from app.services.data_localization import DataLocalizationGuard
        return DataLocalizationGuard(_settings(
            allow_cross_border=allow_cross_border,
            justification=justification,
        ))

    # ── India services always allowed ────────────────────────────────────────

    def test_surepass_aadhaar_allowed(self):
        g = self._guard()
        result = g.check_external_pii("SUREPASS", ["AADHAAR"])
        assert result["allowed"] is True
        assert result["reason"] == "INDIA_SERVICE"

    def test_surepass_pan_allowed(self):
        g = self._guard()
        result = g.check_external_pii("SUREPASS", ["PAN"])
        assert result["allowed"] is True

    def test_digilocker_identity_allowed(self):
        g = self._guard()
        result = g.check_external_pii("DIGILOCKER", ["IDENTITY_DOCS", "AADHAAR"])
        assert result["allowed"] is True
        assert result["reason"] == "INDIA_SERVICE"

    def test_razorpay_upi_allowed(self):
        g = self._guard()
        result = g.check_external_pii("RAZORPAY", ["UPI_ID"])
        assert result["allowed"] is True

    # ── Aadhaar/PAN hard-blocked to non-India ────────────────────────────────

    def test_aadhaar_to_anthropic_hard_blocked(self):
        from app.services.data_localization import DataLocalizationError
        g = self._guard(allow_cross_border=True, justification="test")
        with pytest.raises(DataLocalizationError) as exc_info:
            g.check_external_pii("ANTHROPIC", ["AADHAAR"])
        assert exc_info.value.service == "ANTHROPIC"
        assert "AADHAAR" in exc_info.value.pii_types

    def test_pan_to_openai_hard_blocked(self):
        from app.services.data_localization import DataLocalizationError
        g = self._guard(allow_cross_border=True, justification="test")
        with pytest.raises(DataLocalizationError):
            g.check_external_pii("OPENAI", ["PAN"])

    def test_biometric_to_twilio_hard_blocked(self):
        from app.services.data_localization import DataLocalizationError
        g = self._guard(allow_cross_border=True, justification="test")
        with pytest.raises(DataLocalizationError):
            g.check_external_pii("TWILIO", ["BIOMETRIC"])

    def test_aadhaar_blocked_even_with_cross_border_config(self):
        """Cross-border config cannot override the hard block for Aadhaar/PAN."""
        from app.services.data_localization import DataLocalizationError
        g = self._guard(allow_cross_border=True, justification="explicit override")
        with pytest.raises(DataLocalizationError):
            g.check_external_pii("OPENAI", ["AADHAAR"])

    # ── Non-sensitive PII to non-India ────────────────────────────────────────

    def test_resume_text_to_anthropic_logged_allowed(self):
        """Resume text is not hard-blocked — logged and allowed."""
        g = self._guard(allow_cross_border=False)
        result = g.check_external_pii("ANTHROPIC", ["RESUME_TEXT"])
        assert result["allowed"] is True
        assert result["logged"] is True

    def test_resume_to_anthropic_with_cross_border_config(self):
        g = self._guard(allow_cross_border=True, justification="DPDP consent")
        result = g.check_external_pii("ANTHROPIC", ["RESUME_TEXT", "CANDIDATE_NAME"])
        assert result["allowed"] is True
        assert result["reason"] == "CROSS_BORDER_CONFIGURED"

    def test_phone_to_twilio_logged_allowed(self):
        g = self._guard()
        result = g.check_external_pii("TWILIO", ["PHONE_NUMBER"])
        assert result["allowed"] is True

    def test_mixed_pii_blocks_if_any_is_sensitive(self):
        """If the list includes AADHAAR alongside RESUME_TEXT, still blocked."""
        from app.services.data_localization import DataLocalizationError
        g = self._guard()
        with pytest.raises(DataLocalizationError):
            g.check_external_pii("ANTHROPIC", ["RESUME_TEXT", "AADHAAR"])

    # ── DB logging ────────────────────────────────────────────────────────────

    def test_transmission_logged_to_supabase(self):
        sb = MagicMock()
        chain = MagicMock()
        for m in ("insert", "select", "eq"):
            getattr(chain, m).return_value = chain
        chain.execute.return_value = MagicMock(data=[{"id": "log-001"}])
        sb.table.return_value = chain

        from app.services.data_localization import DataLocalizationGuard
        g = DataLocalizationGuard(_settings(), supabase=sb)
        g.check_external_pii("SUREPASS", ["AADHAAR"])

        # pii_external_transmission_log must have been written
        sb.table.assert_called_with("pii_external_transmission_log")

    def test_transmission_log_failure_doesnt_raise(self):
        """Audit logging is best-effort — DB failure must not propagate."""
        sb = MagicMock()
        sb.table.side_effect = Exception("DB down")

        from app.services.data_localization import DataLocalizationGuard
        g = DataLocalizationGuard(_settings(), supabase=sb)
        # Must not raise even with DB failure
        result = g.check_external_pii("SUREPASS", ["AADHAAR"])
        assert result["allowed"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 5. DataLocalizationGuard — file upload audit
# ═════════════════════════════════════════════════════════════════════════════

class TestFileUploadAudit:
    def test_log_upload_writes_to_db(self):
        sb = MagicMock()
        chain = MagicMock()
        for m in ("insert", "select", "eq"):
            getattr(chain, m).return_value = chain
        chain.execute.return_value = MagicMock(data=[{"id": "audit-001"}])
        sb.table.return_value = chain

        from app.services.data_localization import DataLocalizationGuard
        g = DataLocalizationGuard(_settings(), supabase=sb)
        row_id = g.log_file_upload(
            file_type="FSSAI_CERT",
            s3_key="fssai-certificates/fssai_license/cert1/abc.pdf",
            s3_bucket="my-bucket",
            s3_region="ap-south-1",
            content_type="application/pdf",
            file_size_bytes=204800,
            candidate_id=CANDIDATE_ID,
            org_id=ORG_ID,
        )
        assert row_id == "audit-001"
        sb.table.assert_called_with("file_upload_audit_log")

    def test_log_upload_no_supabase_returns_none(self):
        from app.services.data_localization import DataLocalizationGuard
        g = DataLocalizationGuard(_settings(), supabase=None)
        result = g.log_file_upload(file_type="RESUME", s3_region="ap-south-1")
        assert result is None

    def test_log_upload_db_failure_returns_none(self):
        sb = MagicMock()
        sb.table.side_effect = Exception("DB error")

        from app.services.data_localization import DataLocalizationGuard
        g = DataLocalizationGuard(_settings(), supabase=sb)
        result = g.log_file_upload(file_type="KYC_AADHAAR", s3_region="ap-south-1")
        assert result is None   # best-effort, never raises


# ═════════════════════════════════════════════════════════════════════════════
# 6. S3Service — India region enforced
# ═════════════════════════════════════════════════════════════════════════════

class TestS3ServiceRegion:
    def test_s3_service_uses_india_region(self):
        from app.services.s3_service import S3Service
        svc = S3Service()   # no bucket → sandbox
        assert svc._region == "ap-south-1"

    def test_s3_service_sandbox_without_bucket(self):
        from app.services.s3_service import S3Service
        svc = S3Service()
        assert svc.client is None
        assert svc.bucket == ""

    @pytest.mark.asyncio
    async def test_upload_returns_local_url_in_sandbox(self):
        from app.services.s3_service import S3Service
        svc = S3Service()
        url = await svc.upload_resume(b"resume content", "resume.pdf", "application/pdf")
        assert url.startswith("local://")

    @pytest.mark.asyncio
    async def test_upload_local_url_contains_filename(self):
        from app.services.s3_service import S3Service
        svc = S3Service()
        url = await svc.upload_resume(b"content", "my_cv.pdf", "application/pdf")
        assert "my_cv.pdf" in url

    @pytest.mark.asyncio
    async def test_upload_audit_logged_even_in_sandbox(self):
        from app.services.s3_service import S3Service

        sb = MagicMock()
        chain = MagicMock()
        for m in ("insert", "select", "eq"):
            getattr(chain, m).return_value = chain
        chain.execute.return_value = MagicMock(data=[{"id": "ul-001"}])
        sb.table.return_value = chain

        svc = S3Service()
        await svc.upload_resume(
            b"resume", "cv.pdf", "application/pdf",
            candidate_id=CANDIDATE_ID, org_id=ORG_ID,
            supabase=sb,
        )
        sb.table.assert_called_with("file_upload_audit_log")


# ═════════════════════════════════════════════════════════════════════════════
# 7. FSSAI S3 service — region constant
# ═════════════════════════════════════════════════════════════════════════════

class TestFSSAIServiceRegion:
    def test_fssai_s3_region_is_india(self):
        from app.services.fssai_s3_service import FSSAI_S3_REGION
        assert FSSAI_S3_REGION == "ap-south-1"

    def test_fssai_service_sandbox_generate_upload_url(self):
        from app.services.fssai_s3_service import FSSAIStorageService
        svc = FSSAIStorageService()
        result = svc.generate_upload_url("cert-id", "FSSAI_LICENSE", "cert.pdf", "application/pdf")
        assert result["region"] == "ap-south-1"

    def test_fssai_service_sandbox_flag(self):
        from app.services.fssai_s3_service import FSSAIStorageService
        svc = FSSAIStorageService()
        assert svc._sandbox is True   # no AWS_S3_BUCKET set in test env


# ═════════════════════════════════════════════════════════════════════════════
# 8. KYC router — Aadhaar / PAN guarded
# ═════════════════════════════════════════════════════════════════════════════

_SESSION_INSERT = [{"id": "sess-0001", "request_id": "sandbox-req-00000000"}]


class TestKYCDataLocalizationGuard:
    """
    The KYC router calls DataLocalizationGuard before sending Aadhaar/PAN
    to Surepass. Since Surepass is an India service, these should always be
    allowed (no block). The guard call itself is logged.
    """

    def test_aadhaar_initiate_logs_pii_transmission(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                 _ORG_ROW)
        sb.configure("pii_external_transmission_log", [{"id": "ptl-001"}])
        sb.configure("aadhaar_kyc_sessions",  _SESSION_INSERT)
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)

        resp = client.post("/api/v1/kyc/aadhaar/initiate", json={
            "aadhaar_number": "234512349012",
            "candidate_id":   CANDIDATE_ID,
        })
        assert resp.status_code == 200   # Surepass is India service → allowed

    def test_pan_verify_logs_pii_transmission(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                        _ORG_ROW)
        sb.configure("pii_external_transmission_log",[{"id": "ptl-002"}])
        sb.configure("india_identity_verifications", [{"id": "verif-0001"}])
        sb.configure("candidates",                   [{"id": CANDIDATE_ID}])
        sb.configure("india_compliance_audit_logs",  _AUDIT_ROW)

        resp = client.post("/api/v1/kyc/pan/verify", json={
            "pan_number":   "ABCDE1234F",
            "candidate_id": CANDIDATE_ID,
        })
        assert resp.status_code == 200   # Surepass is India service → allowed


# ═════════════════════════════════════════════════════════════════════════════
# 9. FSSAI confirm-upload — audit logged
# ═════════════════════════════════════════════════════════════════════════════

_CERT_ID = "ccccdddd-aaaa-bbbb-cccc-ddddeeeeffff"
_S3_KEY  = "fssai-certificates/fssai_license/ccccdddd-aaaa-bbbb-cccc-ddddeeeeffff/abc.pdf"

_CERT_WITH_S3 = [{
    "id": _CERT_ID, "org_id": ORG_ID, "cert_type": "FSSAI_LICENSE",
    "s3_key": _S3_KEY, "upload_token": "tok-abc", "candidate_id": CANDIDATE_ID,
}]


class TestFSSAIUploadAudit:
    def test_confirm_upload_writes_audit_log(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                     _ORG_ROW)
        sb.configure("fssai_certificates",        _CERT_WITH_S3)   # SELECT cert
        sb.configure("fssai_certificates",        [{"id": _CERT_ID}])  # UPDATE doc_url
        sb.configure("india_compliance_audit_logs", _AUDIT_ROW)
        sb.configure("file_upload_audit_log",     [{"id": "aul-001"}])

        resp = client.patch(f"/api/v1/fssai/certificates/{_CERT_ID}/confirm-upload",
                            json={"s3_key": _S3_KEY})
        assert resp.status_code == 200
        assert resp.json()["confirmed"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 10. /data-localization and /health endpoints
# ═════════════════════════════════════════════════════════════════════════════

class TestLocalizationEndpoints:
    def test_data_localization_endpoint(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.get("/data-localization")
        assert resp.status_code == 200
        body = resp.json()
        assert "pii_storage_region" in body
        assert body["pii_storage_region"] == "ap-south-1"
        assert "ok" in body
        assert "hard_blocked_pii" in body
        assert "AADHAAR" in body["hard_blocked_pii"]
        assert "PAN" in body["hard_blocked_pii"]

    def test_health_includes_localization(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "data_localization" in body
        assert "localization_ok" in body

    def test_india_services_listed(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.get("/data-localization")
        body = resp.json()
        india = body["india_services"]
        assert "SUREPASS"   in india
        assert "DIGILOCKER" in india
        assert "RAZORPAY"   in india

    def test_non_india_services_listed(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.get("/data-localization")
        body = resp.json()
        non_india = body["non_india_services"]
        assert "ANTHROPIC" in non_india
        assert "OPENAI"    in non_india
        assert "TWILIO"    in non_india

    def test_law_reference_present(self, client_as_admin, mock_supabase):
        client, _ = client_as_admin
        resp = client.get("/data-localization")
        body = resp.json()
        assert "DPDP" in body["law"]


# ═════════════════════════════════════════════════════════════════════════════
# 11. NEVER_CROSS_BORDER constant completeness
# ═════════════════════════════════════════════════════════════════════════════

class TestNeverCrossBorderSet:
    def test_aadhaar_variants_blocked(self):
        from app.services.data_localization import NEVER_CROSS_BORDER
        assert "AADHAAR"        in NEVER_CROSS_BORDER
        assert "AADHAAR_LAST4"  in NEVER_CROSS_BORDER
        assert "AADHAAR_OTP"    in NEVER_CROSS_BORDER

    def test_pan_blocked(self):
        from app.services.data_localization import NEVER_CROSS_BORDER
        assert "PAN"        in NEVER_CROSS_BORDER
        assert "PAN_MASKED" in NEVER_CROSS_BORDER

    def test_biometric_blocked(self):
        from app.services.data_localization import NEVER_CROSS_BORDER
        assert "BIOMETRIC"   in NEVER_CROSS_BORDER
        assert "FACE_PHOTO"  in NEVER_CROSS_BORDER

    def test_resume_text_not_blocked(self):
        """Resume text is logged but not hard-blocked (needed for AI screening)."""
        from app.services.data_localization import NEVER_CROSS_BORDER
        assert "RESUME_TEXT" not in NEVER_CROSS_BORDER

    def test_phone_number_not_blocked(self):
        """Phone numbers go to Twilio — logged but not hard-blocked."""
        from app.services.data_localization import NEVER_CROSS_BORDER
        assert "PHONE_NUMBER" not in NEVER_CROSS_BORDER


# ═════════════════════════════════════════════════════════════════════════════
# 12. get_compliance_summary
# ═════════════════════════════════════════════════════════════════════════════

class TestComplianceSummary:
    def test_summary_structure(self):
        from app.services.data_localization import get_compliance_summary
        s = get_compliance_summary()
        assert s["pii_storage_region"] == "ap-south-1"
        assert isinstance(s["hard_blocked_pii"], list)
        assert isinstance(s["india_services"], list)
        assert isinstance(s["non_india_services"], list)
        assert "DPDP" in s["law"]

    def test_no_overlap_india_non_india(self):
        from app.services.data_localization import get_compliance_summary
        s = get_compliance_summary()
        overlap = set(s["india_services"]) & set(s["non_india_services"])
        assert overlap == set()
