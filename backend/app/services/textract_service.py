"""
Textract Service — OCR document field extraction.
Tries AWS Textract when credentials are available, otherwise returns a mock.
Feature 06: Compliance, Visa & Right-to-Work Management.
"""

import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

MOCK_RESULT = {
    "document_type": "Passport",
    "name": "SAMPLE EXTRACTED",
    "nationality": "GBR",
    "expiry_date": "2030-01-01",
    "document_number": "MOCK123456",
    "extracted_by": "mock",
    "confidence": 0.5,
}


def _aws_available() -> bool:
    """Return True only when real AWS credentials are configured."""
    key = settings.AWS_ACCESS_KEY_ID
    if not key:
        return False
    if key.startswith("AKIA") and "placeholder" not in key.lower() and key != "AKIAIOSFODNN7EXAMPLE":
        return True
    return False


def extract_document_fields(file_bytes: bytes, filename: str) -> dict:
    """
    Extract key fields from an identity document image / PDF.

    When AWS credentials are present, calls Textract AnalyzeID.
    Otherwise (or on any error) falls back to the mock result.
    """
    if _aws_available():
        try:
            import boto3  # optional dependency

            client = boto3.client(
                "textract",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )
            response = client.analyze_id(
                DocumentPages=[{"Bytes": file_bytes}]
            )
            fields: dict = {}
            for doc in response.get("IdentityDocuments", []):
                for field in doc.get("IdentityDocumentFields", []):
                    field_type = field.get("Type", {}).get("Text", "")
                    field_val = field.get("ValueDetection", {})
                    text = field_val.get("Text", "")
                    confidence = field_val.get("Confidence", 0) / 100
                    fields[field_type.lower()] = text
            return {
                "document_type": fields.get("document_type", "UNKNOWN"),
                "name": fields.get("last_name", "") + " " + fields.get("first_name", ""),
                "nationality": fields.get("country_region", ""),
                "expiry_date": fields.get("expiration_date", ""),
                "document_number": fields.get("document_number", ""),
                "extracted_by": "textract",
                "confidence": 0.9,
                "raw_fields": fields,
            }
        except Exception as exc:
            logger.warning("Textract extraction failed, using mock: %s", exc)

    return {**MOCK_RESULT, "filename": filename}
