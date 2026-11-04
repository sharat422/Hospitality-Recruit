"""
S3 upload service for resume files.

Region is ALWAYS ap-south-1 (India data localisation — DPDP Act 2023 s.16).
Falls back to local:// placeholder URLs when AWS_S3_BUCKET is not configured.

Every upload is audit-logged to file_upload_audit_log via the
DataLocalizationGuard when a supabase client is provided.
"""

import logging
import uuid
from typing import Optional

from app.core.config import settings
from app.services.data_localization import (
    DataLocalizationGuard,
    DataLocalizationError,
    INDIA_S3_REGION,
)

logger = logging.getLogger(__name__)


class S3Service:
    """Resume upload service — always uses ap-south-1 for India data residency."""

    def __init__(self):
        self.bucket  = getattr(settings, "AWS_S3_BUCKET", None) or ""
        self._region = INDIA_S3_REGION   # hard-coded; not from settings
        self.client  = None

        if self.bucket:
            try:
                import boto3
                self.client = boto3.client(
                    "s3",
                    region_name=self._region,
                    aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
                    aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
                )
                # Validate the config region matches India requirement
                guard = DataLocalizationGuard(settings)
                guard.validate_config_region()
            except DataLocalizationError:
                raise  # propagate hard violations
            except Exception as exc:
                logger.warning("S3Service init failed — sandbox mode: %s", exc)
                self.client = None

    async def upload_resume(
        self,
        file_bytes:   bytes,
        filename:     str,
        content_type: str,
        candidate_id: Optional[str] = None,
        org_id:       Optional[str] = None,
        supabase=None,
    ) -> str:
        """
        Upload a resume to S3 ap-south-1.
        Returns the public S3 URL or a local:// placeholder in sandbox mode.
        Audit-logs the upload if supabase is provided.
        """
        guard = DataLocalizationGuard(settings, supabase=supabase)

        # Hard-validate region before every upload
        guard.validate_s3_region(self._region, "RESUME")

        if not self.client or not self.bucket:
            placeholder = f"local://{uuid.uuid4()}/{filename}"
            # Still audit-log in sandbox mode
            guard.log_file_upload(
                file_type      = "RESUME",
                s3_key         = placeholder,
                s3_region      = self._region,
                content_type   = content_type,
                file_size_bytes= len(file_bytes),
                candidate_id   = candidate_id,
                org_id         = org_id,
                uploader_type  = "SYSTEM",
                notes          = "Sandbox mode — no real S3 upload",
            )
            return placeholder

        key = f"resumes/{uuid.uuid4()}/{filename}"
        encryption = "aws:kms" if getattr(settings, "AWS_KMS_KEY_ID", None) else "AES256"
        put_args = {"Bucket": self.bucket, "Key": key, "Body": file_bytes,
                    "ContentType": content_type, "ServerSideEncryption": encryption}
        if encryption == "aws:kms":
            put_args["SSEKMSKeyId"] = settings.AWS_KMS_KEY_ID
        self.client.put_object(**put_args)
        doc_url = f"https://{self.bucket}.s3.{self._region}.amazonaws.com/{key}"

        # Audit log
        guard.log_file_upload(
            file_type      = "RESUME",
            s3_key         = key,
            s3_bucket      = self.bucket,
            s3_region      = self._region,
            content_type   = content_type,
            file_size_bytes= len(file_bytes),
            candidate_id   = candidate_id,
            org_id         = org_id,
            uploader_type  = "SYSTEM",
        )

        return doc_url

    def generate_document_upload_url(
        self, org_id: str, candidate_id: str, filename: str, content_type: str,
    ) -> dict:
        """Issue a five-minute private, encrypted India-region document upload URL."""
        allowed = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
        if content_type not in allowed:
            raise ValueError(f"Unsupported document content type: {content_type}")
        safe_name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        key = f"candidate-documents/{org_id}/{candidate_id}/{uuid.uuid4()}-{safe_name}"
        encryption = "aws:kms" if getattr(settings, "AWS_KMS_KEY_ID", None) else "AES256"
        headers = {"Content-Type": content_type, "x-amz-server-side-encryption": encryption}
        if encryption == "aws:kms":
            headers["x-amz-server-side-encryption-aws-kms-key-id"] = settings.AWS_KMS_KEY_ID
        if not self.client or not self.bucket:
            return {"upload_url": f"https://sandbox-s3.example.com/{key}", "storage_key": key,
                    "upload_headers": headers, "expires_in": 300, "region": self._region,
                    "encryption_mode": encryption, "sandbox": True}
        params = {"Bucket": self.bucket, "Key": key, "ContentType": content_type,
                  "ServerSideEncryption": encryption}
        if encryption == "aws:kms":
            params["SSEKMSKeyId"] = settings.AWS_KMS_KEY_ID
        url = self.client.generate_presigned_url("put_object", Params=params, ExpiresIn=300)
        return {"upload_url": url, "storage_key": key, "upload_headers": headers,
                "expires_in": 300, "region": self._region,
                "encryption_mode": encryption, "sandbox": False}

    def generate_employee_certificate_upload_url(
        self, org_id: str, employee_id: str, filename: str, content_type: str,
    ) -> dict:
        """Issue an encrypted private upload URL for an employee certificate."""
        result = self.generate_document_upload_url(org_id, employee_id, filename, content_type)
        old_prefix = f"candidate-documents/{org_id}/{employee_id}/"
        new_prefix = f"employee-certificates/{org_id}/{employee_id}/"
        key = result["storage_key"].replace(old_prefix, new_prefix, 1)
        if not result.get("sandbox"):
            # Regenerate because the key is part of the S3 signature.
            encryption = "aws:kms" if getattr(settings, "AWS_KMS_KEY_ID", None) else "AES256"
            params = {"Bucket": self.bucket, "Key": key, "ContentType": content_type,
                      "ServerSideEncryption": encryption}
            if encryption == "aws:kms": params["SSEKMSKeyId"] = settings.AWS_KMS_KEY_ID
            result["upload_url"] = self.client.generate_presigned_url("put_object", Params=params, ExpiresIn=300)
        else:
            result["upload_url"] = f"https://sandbox-s3.example.com/{key}"
        result["storage_key"] = key
        return result

    def generate_grievance_evidence_upload_url(self, org_id: str, complaint_id: str, filename: str, content_type: str) -> dict:
        """Issue an encrypted private India-region upload URL for case evidence."""
        result = self.generate_document_upload_url(org_id, complaint_id, filename, content_type)
        old_prefix = f"candidate-documents/{org_id}/{complaint_id}/"
        key = result["storage_key"].replace(old_prefix, f"grievance-evidence/{org_id}/{complaint_id}/", 1)
        if not result.get("sandbox"):
            encryption = "aws:kms" if getattr(settings, "AWS_KMS_KEY_ID", None) else "AES256"
            params = {"Bucket": self.bucket, "Key": key, "ContentType": content_type, "ServerSideEncryption": encryption}
            if encryption == "aws:kms": params["SSEKMSKeyId"] = settings.AWS_KMS_KEY_ID
            result["upload_url"] = self.client.generate_presigned_url("put_object", Params=params, ExpiresIn=300)
        else:
            result["upload_url"] = f"https://sandbox-s3.example.com/{key}"
        result["storage_key"] = key
        return result

    def generate_private_download_url(self, storage_key: str, expires_in: int = 300) -> dict:
        """Issue a short-lived URL for a private India-resident object."""
        if not storage_key or ".." in storage_key or storage_key.startswith("/"):
            raise ValueError("Invalid storage key")
        DataLocalizationGuard(settings).validate_s3_region(self._region, "EMPLOYEE_CERTIFICATE")
        if not self.client or not self.bucket:
            return {"download_url": f"https://sandbox-s3.example.com/{storage_key}",
                    "expires_in": expires_in, "region": self._region, "sandbox": True}
        url = self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": storage_key}, ExpiresIn=expires_in,
        )
        return {"download_url": url, "expires_in": expires_in,
                "region": self._region, "sandbox": False}

    def delete_objects(self, storage_keys: list[str]) -> dict:
        """Delete India-resident candidate objects for an approved DPDP erasure."""
        keys = [key for key in storage_keys if key and not key.startswith("local://")]
        if not keys:
            return {
                "requested": len(storage_keys), "deleted": len(storage_keys),
                "errors": [], "sandbox": not bool(self.client),
            }
        if not self.client or not self.bucket:
            return {
                "requested": len(storage_keys), "deleted": len(storage_keys),
                "errors": [], "sandbox": True,
            }
        guard = DataLocalizationGuard(settings)
        guard.validate_s3_region(self._region, "DPDP_ERASURE")
        response = self.client.delete_objects(
            Bucket=self.bucket,
            Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
        )
        errors = response.get("Errors", [])
        return {
            "requested": len(storage_keys),
            "deleted": len(keys) - len(errors),
            "errors": errors,
            "sandbox": False,
        }
