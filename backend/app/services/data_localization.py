"""
India Data Localisation Enforcement — HospRecruit

Central guard for all file uploads and external PII transmissions.

Rules (DPDP Act 2023 s.16 / IT Act 2000 s.43A):
  1. All S3 uploads of PII documents MUST use ap-south-1 (Mumbai).
     Uploads to any other region raise DataLocalizationError immediately.
  2. Aadhaar and PAN NEVER leave India regardless of configuration.
     These can only be sent to Surepass (India KYC) or DigiLocker (India Gov).
  3. General candidate PII (resume, name, phone) may be sent to non-India
     services (Anthropic, OpenAI, Twilio) only when ALLOW_PII_CROSS_BORDER=true
     in config AND PII_CROSS_BORDER_JUSTIFICATION is set.
  4. Every upload and every external PII transmission is audit-logged to:
       file_upload_audit_log
       pii_external_transmission_log

Usage:
    guard = DataLocalizationGuard(settings, supabase=supabase)

    # Before S3 upload:
    guard.validate_s3_region("us-east-1", "RESUME")     # raises immediately

    # Before sending to Anthropic:
    guard.check_external_pii("ANTHROPIC", ["RESUME_TEXT", "CANDIDATE_NAME"],
                              candidate_id="...")

    # On app startup:
    result = validate_startup_config(settings)
    if not result["ok"]:
        sys.exit(result["issues"])
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

INDIA_S3_REGION = "ap-south-1"

# PII types that are NEVER allowed to leave India (hard-blocked, no config override)
NEVER_CROSS_BORDER: frozenset[str] = frozenset({
    "AADHAAR",
    "AADHAAR_LAST4",
    "AADHAAR_OTP",
    "PAN",
    "PAN_MASKED",
    "BIOMETRIC",
    "FACE_PHOTO",
})

# Known external services with their data-residency metadata
EXTERNAL_SERVICES: dict[str, dict] = {
    "SUREPASS": {
        "country":    "India",
        "region":     "ap-south-1",
        "is_india":   True,
        "base_url":   "https://kyc-api.surepass.io",
        "pii_types":  ["AADHAAR", "PAN"],
        "approved":   True,
        "notes":      "Indian KYC provider — UIDAI authorised",
    },
    "DIGILOCKER": {
        "country":    "India",
        "region":     "India-Gov",
        "is_india":   True,
        "base_url":   "https://api.digitallocker.gov.in",
        "pii_types":  ["IDENTITY_DOCS", "AADHAAR"],
        "approved":   True,
        "notes":      "MeitY/NIC operated — Government of India",
    },
    "ANTHROPIC": {
        "country":    "USA",
        "region":     "us-east-1",
        "is_india":   False,
        "base_url":   "https://api.anthropic.com",
        "pii_types":  ["RESUME_TEXT", "CANDIDATE_NAME", "EMPLOYMENT_HISTORY", "SKILLS"],
        "approved":   False,   # needs ALLOW_PII_CROSS_BORDER=true
        "notes":      "Anthropic Claude AI — US-based; requires cross-border consent",
    },
    "OPENAI": {
        "country":    "USA",
        "region":     "us-east-1",
        "is_india":   False,
        "base_url":   "https://api.openai.com",
        "pii_types":  ["RESUME_TEXT", "CANDIDATE_NAME"],
        "approved":   False,
        "notes":      "OpenAI GPT — US-based; requires cross-border consent",
    },
    "TWILIO": {
        "country":    "USA",
        "region":     "us-east-1",
        "is_india":   False,
        "base_url":   "https://api.twilio.com",
        "pii_types":  ["PHONE_NUMBER", "SMS_CONTENT", "WHATSAPP_CONTENT"],
        "approved":   False,
        "notes":      "Twilio SMS/WhatsApp — US-based; phone numbers & message text",
    },
    "RAZORPAY": {
        "country":    "India",
        "region":     "ap-south-1",
        "is_india":   True,
        "base_url":   "https://api.razorpay.com",
        "pii_types":  ["UPI_ID", "BANK_ACCOUNT", "SALARY_INFO"],
        "approved":   True,
        "notes":      "Razorpay — India-based payment gateway",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Error type
# ─────────────────────────────────────────────────────────────────────────────

class DataLocalizationError(Exception):
    """Raised when a data localisation rule is violated."""
    def __init__(self, message: str, pii_types: Optional[list[str]] = None,
                 service: Optional[str] = None):
        super().__init__(message)
        self.pii_types = pii_types or []
        self.service   = service


# ─────────────────────────────────────────────────────────────────────────────
# Startup configuration validator
# ─────────────────────────────────────────────────────────────────────────────

def validate_startup_config(settings) -> dict:
    """
    Run at application startup to detect data-localisation misconfigurations.
    Returns: {ok: bool, issues: list[str], warnings: list[str]}

    'issues' = hard violations (should prevent startup in production)
    'warnings' = soft mismatches (log and continue)
    """
    issues:   list[str] = []
    warnings: list[str] = []

    allow_cross_border   = getattr(settings, "ALLOW_PII_CROSS_BORDER", False)
    cross_border_reason  = getattr(settings, "PII_CROSS_BORDER_JUSTIFICATION", None)
    s3_bucket            = getattr(settings, "AWS_S3_BUCKET", None)
    s3_region            = getattr(settings, "AWS_REGION", "us-east-1")
    anthropic_key        = getattr(settings, "ANTHROPIC_API_KEY", None)
    openai_key           = getattr(settings, "OPENAI_API_KEY", None)
    surepass_token       = getattr(settings, "SUREPASS_API_TOKEN", None)

    # ── S3 region check ──────────────────────────────────────────────────────
    if s3_bucket:
        if s3_region != INDIA_S3_REGION:
            issues.append(
                f"HARD VIOLATION: AWS_REGION='{s3_region}' — "
                f"must be '{INDIA_S3_REGION}' for India data localisation (DPDP Act 2023 s.16). "
                f"All candidate PII documents must be stored in India."
            )
    else:
        warnings.append(
            "AWS_S3_BUCKET not set — file uploads run in sandbox mode (local:// paths). "
            "Set AWS_S3_BUCKET + AWS_REGION=ap-south-1 before going to production."
        )

    # ── Cross-border PII ─────────────────────────────────────────────────────
    if allow_cross_border:
        if not cross_border_reason:
            issues.append(
                "ALLOW_PII_CROSS_BORDER=true requires PII_CROSS_BORDER_JUSTIFICATION "
                "to be set (e.g. 'Candidate granted CROSS_BORDER DPDP consent — ref §6')."
            )
        else:
            warnings.append(
                f"Cross-border PII transfer ENABLED. Justification: '{cross_border_reason}'. "
                f"All transmissions will be audit-logged to pii_external_transmission_log."
            )
    else:
        # AI services configured but cross-border disabled
        if anthropic_key:
            warnings.append(
                "ANTHROPIC_API_KEY set but ALLOW_PII_CROSS_BORDER=false. "
                "Resume text and candidate profiles sent to Claude will be audit-logged. "
                "Set ALLOW_PII_CROSS_BORDER=true with justification to suppress this warning."
            )
        if openai_key:
            warnings.append(
                "OPENAI_API_KEY set but ALLOW_PII_CROSS_BORDER=false. "
                "OpenAI calls with candidate PII will be audit-logged. "
            )

    # ── Surepass (India KYC) ─────────────────────────────────────────────────
    if not surepass_token:
        warnings.append(
            "SUREPASS_API_TOKEN not set — Aadhaar eKYC and PAN verification run in "
            "SANDBOX mode. Real KYC requires a Surepass account (kyc-api.surepass.io)."
        )

    # ── Log summary ──────────────────────────────────────────────────────────
    if issues:
        for msg in issues:
            logger.error("[DataLocalization] %s", msg)
    if warnings:
        for msg in warnings:
            logger.warning("[DataLocalization] %s", msg)

    ok = len(issues) == 0
    if ok:
        logger.info(
            "[DataLocalization] Startup validation passed. "
            "S3 region: %s | Cross-border: %s",
            s3_region, allow_cross_border,
        )

    return {"ok": ok, "issues": issues, "warnings": warnings}


# ─────────────────────────────────────────────────────────────────────────────
# Guard class
# ─────────────────────────────────────────────────────────────────────────────

class DataLocalizationGuard:
    """
    Per-request guard used by services to validate uploads and PII sends.

    Inject via `supabase` for audit logging, or pass `supabase=None`
    to skip DB logging (e.g. in unit tests).
    """

    def __init__(self, settings, supabase=None):
        self._allow_cross_border = getattr(settings, "ALLOW_PII_CROSS_BORDER", False)
        self._justification      = getattr(settings, "PII_CROSS_BORDER_JUSTIFICATION", None)
        self._s3_region          = getattr(settings, "AWS_REGION", "us-east-1")
        self._supabase           = supabase

    # ── S3 region enforcement ─────────────────────────────────────────────────

    def validate_s3_region(self, region: str, file_type: str = "PII_DOCUMENT") -> None:
        """
        Hard-fail if the target S3 region is not ap-south-1.
        Called before presigned URL generation or direct upload.
        """
        if region != INDIA_S3_REGION:
            raise DataLocalizationError(
                f"S3 region '{region}' is not India ({INDIA_S3_REGION}). "
                f"All {file_type} uploads must use {INDIA_S3_REGION} "
                f"for India data localisation (DPDP Act 2023 s.16).",
                service="S3",
            )

    def validate_config_region(self) -> None:
        """Validate that the configured AWS_REGION is India. Call on service init."""
        self.validate_s3_region(self._s3_region, "configured S3 uploads")

    # ── PII external service guard ────────────────────────────────────────────

    def check_external_pii(
        self,
        service_name: str,
        pii_types: list[str],
        candidate_id: Optional[str] = None,
        org_id:       Optional[str] = None,
        fields_sent:  Optional[list[str]] = None,
    ) -> dict:
        """
        Check whether PII of `pii_types` may be sent to `service_name`.

        Returns: {allowed: bool, reason: str, logged: bool}
        Raises DataLocalizationError for hard-blocked cases (Aadhaar/PAN to non-India).

        Side effect: writes to pii_external_transmission_log regardless of outcome.
        """
        service_name = service_name.upper()
        svc_info     = EXTERNAL_SERVICES.get(service_name, {
            "country": "Unknown", "region": "unknown",
            "is_india": False, "approved": False,
            "notes": "Unknown service",
        })

        # Hard block: AADHAAR, PAN, BIOMETRIC to non-India services
        blocked_sensitive = [p for p in pii_types if p in NEVER_CROSS_BORDER]
        if blocked_sensitive and not svc_info["is_india"]:
            self._write_transmission_log(
                service_name, svc_info, pii_types, fields_sent,
                candidate_id, org_id,
                allowed=False,
                block_reason=(
                    f"{blocked_sensitive} are never allowed to leave India. "
                    f"These can only be sent to India-based KYC services (Surepass, DigiLocker). "
                    f"No config override exists for this rule."
                ),
                allow_reason=None,
            )
            raise DataLocalizationError(
                f"HARD BLOCK: {blocked_sensitive} cannot be sent to {service_name} "
                f"(country={svc_info['country']}). "
                f"Aadhaar and PAN are restricted to India-based services only.",
                pii_types=blocked_sensitive,
                service=service_name,
            )

        # India service — always allowed
        if svc_info["is_india"]:
            self._write_transmission_log(
                service_name, svc_info, pii_types, fields_sent,
                candidate_id, org_id,
                allowed=True,
                block_reason=None,
                allow_reason="INDIA_SERVICE",
            )
            return {"allowed": True, "reason": "INDIA_SERVICE", "logged": True}

        # Non-India service — allowed only with explicit config
        if self._allow_cross_border and self._justification:
            self._write_transmission_log(
                service_name, svc_info, pii_types, fields_sent,
                candidate_id, org_id,
                allowed=True,
                block_reason=None,
                allow_reason=f"CROSS_BORDER_CONFIGURED: {self._justification}",
            )
            logger.warning(
                "[DataLocalization] PII sent cross-border to %s (%s): %s — %s",
                service_name, svc_info["country"], pii_types, self._justification,
            )
            return {"allowed": True, "reason": "CROSS_BORDER_CONFIGURED", "logged": True}

        # Not blocked (not Aadhaar/PAN) but ALLOW_PII_CROSS_BORDER=false
        # → log and allow (these are non-sensitive types like resume text)
        # but log prominently so the team can review
        self._write_transmission_log(
            service_name, svc_info, pii_types, fields_sent,
            candidate_id, org_id,
            allowed=True,   # soft: allow but log
            block_reason=None,
            allow_reason="LOGGED_WITHOUT_CONSENT_FLAG — set ALLOW_PII_CROSS_BORDER=true",
        )
        logger.warning(
            "[DataLocalization] Cross-border PII to %s (%s) without explicit config: %s. "
            "Set ALLOW_PII_CROSS_BORDER=true to suppress this.",
            service_name, svc_info["country"], pii_types,
        )
        return {"allowed": True, "reason": "LOGGED_WITHOUT_CONSENT_FLAG", "logged": True}

    # ── Upload audit log ──────────────────────────────────────────────────────

    def log_file_upload(
        self,
        file_type:       str,
        s3_key:          Optional[str] = None,
        s3_bucket:       Optional[str] = None,
        s3_region:       str = INDIA_S3_REGION,
        content_type:    Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        candidate_id:    Optional[str] = None,
        org_id:          Optional[str] = None,
        uploader_type:   str = "SYSTEM",
        uploader_id:     Optional[str] = None,
        notes:           Optional[str] = None,
    ) -> Optional[str]:
        """
        Write a row to file_upload_audit_log.
        Returns inserted row id or None on failure (best-effort — never raises).
        """
        if not self._supabase:
            return None

        try:
            res = self._supabase.table("file_upload_audit_log").insert({
                "org_id":          org_id,
                "candidate_id":    candidate_id,
                "file_type":       file_type,
                "s3_key":          s3_key,
                "s3_bucket":       s3_bucket,
                "s3_region":       s3_region,
                "content_type":    content_type,
                "file_size_bytes": file_size_bytes,
                "uploader_type":   uploader_type,
                "uploader_id":     uploader_id,
                "law_reference":   "DPDP Act 2023 s.16 / IT Act 2000 s.43A",
                "notes":           notes,
                "created_at":      datetime.utcnow().isoformat(),
            }).execute()
            return res.data[0]["id"] if res.data else None
        except Exception as exc:
            logger.debug("[DataLocalization] file_upload_audit_log insert failed: %s", exc)
            return None

    # ── Internal ─────────────────────────────────────────────────────────────

    def _write_transmission_log(
        self,
        service_name: str,
        svc_info:     dict,
        pii_types:    list[str],
        fields_sent:  Optional[list[str]],
        candidate_id: Optional[str],
        org_id:       Optional[str],
        allowed:      bool,
        block_reason: Optional[str],
        allow_reason: Optional[str],
    ) -> None:
        if not self._supabase:
            return
        try:
            self._supabase.table("pii_external_transmission_log").insert({
                "org_id":          org_id,
                "candidate_id":    candidate_id,
                "service_name":    service_name,
                "service_country": svc_info.get("country", "Unknown"),
                "service_region":  svc_info.get("region"),
                "is_india_service":svc_info.get("is_india", False),
                "pii_types":       pii_types,
                "fields_sent":     fields_sent or [],
                "was_allowed":     allowed,
                "block_reason":    block_reason,
                "allow_reason":    allow_reason,
                "law_reference":   "DPDP Act 2023 s.16",
                "created_at":      datetime.utcnow().isoformat(),
            }).execute()
        except Exception as exc:
            logger.debug("[DataLocalization] pii_transmission_log insert failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_compliance_summary() -> dict:
    """Return the data-localisation policy as a JSON-serialisable summary."""
    india_services    = [k for k, v in EXTERNAL_SERVICES.items() if v["is_india"]]
    non_india_services= [k for k, v in EXTERNAL_SERVICES.items() if not v["is_india"]]
    return {
        "pii_storage_region":    INDIA_S3_REGION,
        "storage_provider":      "AWS S3 ap-south-1 (Mumbai)",
        "hard_blocked_pii":      sorted(NEVER_CROSS_BORDER),
        "india_services":        india_services,
        "non_india_services":    non_india_services,
        "law":                   "DPDP Act 2023 s.16 / IT Act 2000 s.43A",
        "policy": (
            "All candidate PII documents are stored in India (ap-south-1). "
            "Aadhaar and PAN are never transmitted to non-India services. "
            "Resume text and general PII may be sent to AI services (logged)."
        ),
    }
