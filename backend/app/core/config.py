"""
Core configuration for HospRecruit AI.
Pain Point #1: 100-500 unqualified apps per role → screening efficiency critical
Pain Point #6: Thin margins → optimize infrastructure costs
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # FastAPI
    API_VERSION: str = "v1"
    API_TITLE: str = "HospRecruit AI API"
    DEBUG: bool = False

    # Supabase (Auth + DB + Realtime)
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_JWT_SECRET: str

    # AI Providers (Pain #1: efficient screening requires top-tier models)
    ANTHROPIC_API_KEY: str
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"

    # SMS (Pain #2: seasonal chaos → SMS-first mobile engagement)
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_PHONE_NUMBER: str

    # ATS Integration (Merge.dev → Bullhorn + iCIMS)
    MERGE_DEV_API_KEY: str
    MERGE_DEV_BASE_URL: str = "https://api.merge.dev/api"

    # Payment (Billing & white-label)
    # Stripe is the original US billing rail and is OFF by default: Indian
    # billing settles through Razorpay (see services/razorpay_payout_service.py).
    # Set BILLING_ENABLED=true only when a Stripe account is actually in use;
    # the billing router is not mounted while this is false.
    BILLING_ENABLED: bool = False
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # Redis/Celery (Background jobs: onboarding, compliance checks, bulk SMS)
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # CORS
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:5173",  # Vite dev
        "http://localhost:3000",  # Alternative dev
    ]

    # AWS S3 (optional — for resume and compliance document storage)
    # DPDP Act 2023 s.16: ALL PII uploads MUST use ap-south-1 (Mumbai / India)
    # Changing AWS_REGION away from ap-south-1 will trigger a startup hard-violation.
    AWS_S3_BUCKET: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "ap-south-1"   # CHANGED: was us-east-1; India data residency required
    AWS_KMS_KEY_ID: Optional[str] = None

    # India data localisation — cross-border PII control
    # Set to true only when candidates have explicitly granted CROSS_BORDER DPDP consent.
    # PII_CROSS_BORDER_JUSTIFICATION is required when ALLOW_PII_CROSS_BORDER=true.
    ALLOW_PII_CROSS_BORDER:         bool            = False
    PII_CROSS_BORDER_JUSTIFICATION: Optional[str]   = None
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # DeepL Translation (optional)
    DEEPL_API_KEY: Optional[str] = None

    # App base URL (for confirmation links in SMS)
    APP_BASE_URL: str = "http://localhost:5173"
    API_PUBLIC_BASE_URL: str = "http://localhost:8000"

    # Twilio WhatsApp sandbox number
    TWILIO_WHATSAPP_NUMBER: str = "whatsapp:+14155238886"

    # ── WhatsApp provider selection ───────────────────────────────────────────
    # WHATSAPP_PROVIDER controls which API is used for send + which webhook
    # endpoint format is expected.
    # Values: "twilio" (default/sandbox) | "meta" | "interakt"
    WHATSAPP_PROVIDER: str = "twilio"

    # Meta WhatsApp Business API (Cloud API)
    # Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
    WHATSAPP_VERIFY_TOKEN: Optional[str] = None
    # Arbitrary secret you set in Meta App Dashboard → Webhooks → Verify Token
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    # System user access token from Meta Business Manager
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    # Phone Number ID from Meta App Dashboard (not the phone number itself)
    WHATSAPP_APP_SECRET: Optional[str] = None
    # App Secret for HMAC-SHA256 signature verification of inbound webhooks

    # Interakt (India-focused Meta BSP)
    # Docs: https://developer.interakt.ai
    INTERAKT_API_KEY: Optional[str] = None
    # API key from Interakt dashboard → Settings → API

    # Google Calendar OAuth (optional)
    GOOGLE_CALENDAR_CLIENT_ID: Optional[str] = None
    GOOGLE_CALENDAR_CLIENT_SECRET: Optional[str] = None

    # Razorpay (UPI VPA validation + Payouts)
    RAZORPAY_KEY_ID: Optional[str] = None
    RAZORPAY_KEY_SECRET: Optional[str] = None
    # RazorpayX source account number from which bonus payouts are debited
    RAZORPAY_FUND_ACCOUNT: Optional[str] = None

    # Vendor-neutral biometric webhook. Store production vendor credentials in
    # a secret manager; this shared token is only for the GENERIC_JSON adapter.
    BIOMETRIC_WEBHOOK_SECRET: Optional[str] = None

    # India KYC providers
    # Surepass (Aadhaar eKYC + PAN) — https://kyc-api.surepass.io
    # Leave unset → sandbox/mock mode (safe for dev/staging)
    SUREPASS_API_TOKEN: Optional[str] = None
    # DigiLocker OAuth 2.0 — https://api.digitallocker.gov.in
    DIGILOCKER_CLIENT_ID: Optional[str] = None
    DIGILOCKER_CLIENT_SECRET: Optional[str] = None
    DIGILOCKER_REDIRECT_URI: Optional[str] = None

    # Security
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
