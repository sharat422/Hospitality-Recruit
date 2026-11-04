"""
OTP Service — generate, hash, verify OTPs for India mobile auth.
"""

import hashlib
import secrets
import logging

logger = logging.getLogger(__name__)


def generate_otp() -> str:
    """Generate a 6-digit OTP."""
    return str(secrets.randbelow(900000) + 100000)


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def verify_otp_hash(otp: str, stored_hash: str) -> bool:
    return hash_otp(otp) == stored_hash


def validate_india_phone(phone: str) -> bool:
    """Validate Indian phone number format: +91XXXXXXXXXX or 10 digits."""
    clean = phone.strip().replace(" ", "").replace("-", "")
    if clean.startswith("+91"):
        return len(clean) == 13 and clean[3:].isdigit()
    elif clean.startswith("91"):
        return len(clean) == 12 and clean[2:].isdigit()
    return len(clean) == 10 and clean.isdigit()


def normalize_india_phone(phone: str) -> str:
    """Normalize to +91XXXXXXXXXX format."""
    clean = phone.strip().replace(" ", "").replace("-", "")
    if clean.startswith("+91"):
        return clean
    if clean.startswith("91"):
        return "+" + clean
    return "+91" + clean
