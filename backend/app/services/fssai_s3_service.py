"""
FSSAI Certificate S3 Service — ap-south-1 (India data residency).

Handles presigned URL generation for certificate uploads.
Falls back to sandbox mode (no real S3 calls) when AWS credentials are absent.

Certificate data is always stored in ap-south-1 to comply with India
data-localisation requirements under DPDP Act 2023.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from app.core.config import settings
from app.services.data_localization import DataLocalizationGuard, INDIA_S3_REGION

logger = logging.getLogger(__name__)

FSSAI_S3_REGION  = INDIA_S3_REGION   # ap-south-1 — hard-coded for compliance
FSSAI_S3_PREFIX  = "fssai-certificates"
UPLOAD_EXPIRY_S  = 300            # presigned PUT URL valid for 5 minutes
DOWNLOAD_EXPIRY_S = 3600          # presigned GET URL valid for 1 hour

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class FSSAIStorageService:
    """
    Presigned URL service for FSSAI certificate documents.

    Sandbox mode (no S3 client) is active when AWS_S3_BUCKET is not set.
    In sandbox mode all URLs are deterministic fake URLs — useful for dev/test.
    """

    def __init__(self):
        self._bucket: Optional[str] = getattr(settings, "AWS_S3_BUCKET", None)
        self._sandbox = not bool(self._bucket)
        self._client = None

        if not self._sandbox:
            try:
                import boto3
                self._client = boto3.client(
                    "s3",
                    region_name=FSSAI_S3_REGION,
                    aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
                    aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
                )
            except Exception as exc:
                logger.warning("FSSAI S3 client init failed — sandbox mode: %s", exc)
                self._sandbox = True

    # ── Public API ──────────────────────────────────────────────────────────

    def generate_upload_url(
        self,
        cert_id: str,
        cert_type: str,
        original_filename: str,
        content_type: str,
    ) -> dict:
        """
        Generate a presigned PUT URL for direct-to-S3 upload from the browser.

        Returns:
            upload_url   – PUT to this URL from the frontend
            s3_key       – store this; used for confirm-upload and downloads
            sandbox      – True when real S3 is not configured
            expires_in   – seconds until the presigned URL expires
        """
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError(
                f"Content type {content_type!r} is not allowed. "
                f"Accepted: {sorted(ALLOWED_CONTENT_TYPES)}"
            )

        ext = self._safe_extension(original_filename)
        s3_key = f"{FSSAI_S3_PREFIX}/{cert_type.lower()}/{cert_id}/{uuid.uuid4()}{ext}"

        if self._sandbox:
            encryption = "aws:kms" if getattr(settings, "AWS_KMS_KEY_ID", None) else "AES256"
            return {
                "upload_url": f"https://sandbox-s3.example.com/{s3_key}",
                "s3_key":     s3_key,
                "sandbox":    True,
                "expires_in": UPLOAD_EXPIRY_S,
                "region":     FSSAI_S3_REGION,
                "upload_headers": {
                    "Content-Type": content_type,
                    "x-amz-server-side-encryption": encryption,
                    **({"x-amz-server-side-encryption-aws-kms-key-id": settings.AWS_KMS_KEY_ID}
                       if encryption == "aws:kms" else {}),
                },
            }

        encryption = "aws:kms" if getattr(settings, "AWS_KMS_KEY_ID", None) else "AES256"
        params = {
            "Bucket": self._bucket,
            "Key": s3_key,
            "ContentType": content_type,
            "ContentLength": MAX_FILE_SIZE_BYTES,
            "ServerSideEncryption": encryption,
        }
        if encryption == "aws:kms":
            params["SSEKMSKeyId"] = settings.AWS_KMS_KEY_ID
        url = self._client.generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=UPLOAD_EXPIRY_S,
        )
        return {
            "upload_url": url,
            "s3_key":     s3_key,
            "sandbox":    False,
            "expires_in": UPLOAD_EXPIRY_S,
            "region":     FSSAI_S3_REGION,
            "upload_headers": {
                "Content-Type": content_type,
                "x-amz-server-side-encryption": encryption,
                **({"x-amz-server-side-encryption-aws-kms-key-id": settings.AWS_KMS_KEY_ID}
                   if encryption == "aws:kms" else {}),
            },
        }

    def generate_download_url(self, s3_key: str) -> str:
        """
        Generate a presigned GET URL for secure download.
        Returns a sandbox URL when not configured.
        """
        if self._sandbox:
            return f"https://sandbox-s3.example.com/{s3_key}?X-Amz-Expires={DOWNLOAD_EXPIRY_S}"

        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": s3_key},
            ExpiresIn=DOWNLOAD_EXPIRY_S,
        )

    def public_url(self, s3_key: str) -> str:
        """
        Private storage reference. Documents are retrieved only with a short-lived
        presigned URL; the compliance bucket must not be public.
        """
        if self._sandbox:
            return f"https://sandbox-s3.example.com/{s3_key}"
        return f"s3://{self._bucket}/{s3_key}"

    # ── Private ─────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_extension(filename: str) -> str:
        """Extract extension from filename, defaulting to .pdf."""
        parts = filename.rsplit(".", 1)
        if len(parts) == 2 and 2 <= len(parts[1]) <= 4:
            return f".{parts[1].lower()}"
        return ".pdf"


# Singleton
_storage: Optional[FSSAIStorageService] = None


def get_fssai_storage() -> FSSAIStorageService:
    global _storage
    if _storage is None:
        _storage = FSSAIStorageService()
    return _storage
