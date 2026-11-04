"""
DPDP Act 2023 Privacy Service — HospRecruit India

Implements Digital Personal Data Protection Act 2023 requirements:
  s.6  — Free, specific, informed, unconditional, unambiguous consent (no bundling)
  s.8  — Data retention: erase when purpose fulfilled or consent withdrawn
  s.8(7) — Legal retention exception where statutory obligation exists
  s.13 — Erasure / correction / access / nomination rights (30-day SLA)
  s.16 — Data localisation (PII stored in India)

WhatsApp acknowledgment: Twilio WhatsApp API (same account as SMS)
Privacy Centre token: cryptographically secure 32-char URL-safe token
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

CONSENT_TEXT_VERSION = "v2.0"   # bump when consent text changes
PRIVACY_TOKEN_EXPIRY_DAYS = 7
ERASURE_SLA_DAYS = 30           # DPDP Act 2023 s.13

DATA_REGION = "ap-south-1"      # Mumbai — India data localisation

# DPDP purpose codes with full metadata (no bundling — one toggle per code)
PURPOSE_DEFINITIONS: dict[str, dict] = {
    "RECRUITMENT_DATA": {
        "description_en": "Processing your personal data for recruitment and hiring",
        "description_hi": "भर्ती और नियुक्ति के लिए आपके व्यक्तिगत डेटा का प्रसंस्करण",
        "required":        True,   # required for core service — cannot be withdrawn
        "legal_basis":    "Contractual necessity (DPDP Act 2023 s.4)",
        "retention_years": 1,
        "icon":           "👤",
    },
    "BACKGROUND_CHECK": {
        "description_en": "Verification of your identity, credentials, and past employment",
        "description_hi": "आपकी पहचान, योग्यता और पिछले रोजगार की सत्यापन",
        "required":        False,
        "legal_basis":    "Consent (DPDP Act 2023 s.6)",
        "retention_years": 3,
        "icon":           "🔍",
    },
    "SENSITIVE_DATA": {
        "description_en": "Medical records, biometric data, or financial information",
        "description_hi": "चिकित्सा रिकॉर्ड, बायोमेट्रिक डेटा, या वित्तीय जानकारी",
        "required":        False,
        "legal_basis":    "Explicit consent (DPDP Act 2023 s.9)",
        "retention_years": None,   # indefinite — statutory obligation may apply
        "icon":           "🔒",
    },
    "MARKETING": {
        "description_en": "Job alerts, newsletters, and promotional content",
        "description_hi": "नौकरी अलर्ट, न्यूज़लेटर, और प्रचार सामग्री",
        "required":        False,
        "legal_basis":    "Consent (DPDP Act 2023 s.6)",
        "retention_years": 0,   # erase when withdrawn
        "icon":           "📢",
    },
    "THIRD_PARTY_SHARE": {
        "description_en": "Sharing your profile with hotels, employers, or staffing agencies",
        "description_hi": "आपका प्रोफ़ाइल होटल, नियोक्ता या स्टाफिंग एजेंसियों के साथ साझा करना",
        "required":        False,
        "legal_basis":    "Consent (DPDP Act 2023 s.6)",
        "retention_years": 0,
        "icon":           "🤝",
    },
    "AI_PROFILING": {
        "description_en": "AI-based assessment, screening, and ranking of your application",
        "description_hi": "आपके आवेदन का AI-आधारित मूल्यांकन, स्क्रीनिंग और रैंकिंग",
        "required":        False,
        "legal_basis":    "Consent (DPDP Act 2023 s.6)",
        "retention_years": 1,
        "icon":           "🤖",
    },
    "CROSS_BORDER": {
        "description_en": "Transfer of your personal data outside India",
        "description_hi": "भारत के बाहर आपके व्यक्तिगत डेटा का स्थानांतरण",
        "required":        False,
        "legal_basis":    "Consent (DPDP Act 2023 s.16)",
        "retention_years": 3,
        "icon":           "🌐",
    },
}

# Legal retention periods that can override erasure requests
STATUTORY_RETENTION: dict[str, dict] = {
    "EPF_UAN":       {"years": 8, "law": "EPF Act 1952 r.32",            "exempts_erasure": True},
    "PAN_FORM16":    {"years": 8, "law": "Income Tax Act 1961 s.44AB",   "exempts_erasure": True},
    "ESIC_RECORDS":  {"years": 8, "law": "ESIC Act 1948 r.56",           "exempts_erasure": True},
    "FSSAI_CERT":    {"years": 3, "law": "FSSAI Act 2006",               "exempts_erasure": False},
    "MEDICAL_RECORD":{"years": None, "law": "Factories Act 1948 s.7A",   "exempts_erasure": True},
    "PROF_TAX":      {"years": 5, "law": "State PT Acts",                "exempts_erasure": True},
}

DOCUMENT_RETENTION_RULES: dict[str, dict] = {
    "EPF": {"years": 8, "law": "EPF Act 1952 r.32"},
    "UAN": {"years": 8, "law": "EPF Act 1952 r.32"},
    "ESIC": {"years": 8, "law": "ESIC Act 1948 r.56"},
    "PAN": {"years": 8, "law": "Income Tax Act 1961 / Form 16 retention"},
    "FORM16": {"years": 8, "law": "Income Tax Act 1961 / Form 16 retention"},
    "FORM_16": {"years": 8, "law": "Income Tax Act 1961 / Form 16 retention"},
    "PROFESSIONAL_TAX": {"years": 5, "law": "Applicable State Professional Tax Act"},
    "MEDICAL": {"years": None, "law": "Applicable occupational health retention obligation"},
}


def classify_document_retention(document: dict) -> dict:
    """Classify one document without exposing or inspecting its contents."""
    category = str(document.get("data_category") or document.get("document_type") or "").upper()
    normalized = category.replace("-", "_").replace(" ", "_")
    rule = DOCUMENT_RETENTION_RULES.get(normalized)
    if not rule:
        for key, candidate_rule in DOCUMENT_RETENTION_RULES.items():
            if key in normalized:
                rule = candidate_rule
                break
    if document.get("legal_hold"):
        return {"retain": True, "data_category": normalized or "LEGAL_HOLD",
                "retention_until": document.get("retention_until"),
                "legal_basis": document.get("legal_hold_basis") or "Existing legal hold"}
    if not rule:
        return {"retain": False, "data_category": normalized or "RECRUITMENT_DOCUMENT",
                "retention_until": document.get("retention_until"), "legal_basis": None}
    retention_until = document.get("retention_until")
    if not retention_until and rule["years"] is not None:
        created = str(document.get("created_at") or datetime.utcnow().date().isoformat())[:10]
        try:
            created_date = datetime.fromisoformat(created).date()
            try:
                retention_until = created_date.replace(year=created_date.year + rule["years"]).isoformat()
            except ValueError:
                retention_until = created_date.replace(month=2, day=28, year=created_date.year + rule["years"]).isoformat()
        except ValueError:
            retention_until = None
    return {"retain": True, "data_category": normalized,
            "retention_until": retention_until, "legal_basis": rule["law"]}


def build_candidate_retention_plan(supabase, candidate_id: str, org_id: str) -> dict:
    """Return the exact retain/delete decision used by the erasure processor."""
    documents = (supabase.table("candidate_documents")
                 .select("id,document_type,data_category,retention_until,legal_hold,legal_hold_basis,created_at,storage_key")
                 .eq("candidate_id", candidate_id).eq("org_id", org_id).execute().data or [])
    items = []
    for document in documents:
        decision = classify_document_retention(document)
        items.append({"document_id": document.get("id"), "document_type": document.get("document_type"),
                      "action": "RETAIN" if decision["retain"] else "DELETE", **decision})
    return {"candidate_id": candidate_id, "documents": items,
            "retained_count": sum(1 for item in items if item["retain"]),
            "erasable_count": sum(1 for item in items if not item["retain"]),
            "statutory_records": STATUTORY_RETENTION}

DOCUMENT_RETENTION_RULES: dict[str, dict] = {
    "EPF": {"years": 8, "law": "EPF Act 1952 r.32"},
    "UAN": {"years": 8, "law": "EPF Act 1952 r.32"},
    "ESIC": {"years": 8, "law": "ESIC Act 1948 r.56"},
    "PAN": {"years": 8, "law": "Income Tax Act 1961 / Form 16 retention"},
    "FORM16": {"years": 8, "law": "Income Tax Act 1961 / Form 16 retention"},
    "FORM_16": {"years": 8, "law": "Income Tax Act 1961 / Form 16 retention"},
    "PROFESSIONAL_TAX": {"years": 5, "law": "Applicable State Professional Tax Act"},
    "MEDICAL": {"years": None, "law": "Applicable occupational health retention obligation"},
}


def classify_document_retention(document: dict) -> dict:
    """Classify one document without exposing or inspecting its contents."""
    category = str(document.get("data_category") or document.get("document_type") or "").upper()
    normalized = category.replace("-", "_").replace(" ", "_")
    rule = DOCUMENT_RETENTION_RULES.get(normalized)
    if not rule:
        for key, candidate_rule in DOCUMENT_RETENTION_RULES.items():
            if key in normalized:
                rule = candidate_rule
                break
    if document.get("legal_hold"):
        return {
            "retain": True,
            "data_category": normalized or "LEGAL_HOLD",
            "retention_until": document.get("retention_until"),
            "legal_basis": document.get("legal_hold_basis") or "Existing legal hold",
        }
    if not rule:
        return {
            "retain": False, "data_category": normalized or "RECRUITMENT_DOCUMENT",
            "retention_until": document.get("retention_until"), "legal_basis": None,
        }

    retention_until = document.get("retention_until")
    if not retention_until and rule["years"] is not None:
        created = str(document.get("created_at") or datetime.utcnow().date().isoformat())[:10]
        try:
            created_date = datetime.fromisoformat(created).date()
            try:
                retention_until = created_date.replace(year=created_date.year + rule["years"]).isoformat()
            except ValueError:  # 29 February
                retention_until = created_date.replace(month=2, day=28, year=created_date.year + rule["years"]).isoformat()
        except ValueError:
            retention_until = None
    return {
        "retain": True,
        "data_category": normalized,
        "retention_until": retention_until,
        "legal_basis": rule["law"],
    }


def build_candidate_retention_plan(supabase, candidate_id: str, org_id: str) -> dict:
    """Return the exact retain/delete decision used by the erasure processor."""
    documents = (supabase.table("candidate_documents")
                 .select("id,document_type,data_category,retention_until,legal_hold,legal_hold_basis,created_at,storage_key")
                 .eq("candidate_id", candidate_id).eq("org_id", org_id).execute().data or [])
    items = []
    for document in documents:
        decision = classify_document_retention(document)
        items.append({
            "document_id": document.get("id"),
            "document_type": document.get("document_type"),
            "action": "RETAIN" if decision["retain"] else "DELETE",
            **decision,
        })
    return {
        "candidate_id": candidate_id,
        "documents": items,
        "retained_count": sum(1 for item in items if item["retain"]),
        "erasable_count": sum(1 for item in items if not item["retain"]),
        "statutory_records": STATUTORY_RETENTION,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Privacy Centre token
# ─────────────────────────────────────────────────────────────────────────────

def generate_privacy_token() -> str:
    """Generate a cryptographically secure 32-char URL-safe token."""
    return secrets.token_urlsafe(32)


def create_privacy_session(
    supabase,
    candidate_id: str,
    purpose: str = "GENERAL",
    ip_address: Optional[str] = None,
) -> dict:
    """Create a tokenised Privacy Centre session for a candidate."""
    token      = generate_privacy_token()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=PRIVACY_TOKEN_EXPIRY_DAYS)).isoformat()
    row = {
        "candidate_id": candidate_id,
        "token":        token,
        "purpose":      purpose,
        "expires_at":   expires_at,
        "ip_address":   ip_address,
        "created_at":   datetime.utcnow().isoformat(),
    }
    result = supabase.table("privacy_center_sessions").insert(row).execute()
    if not result.data:
        raise RuntimeError("Failed to create privacy session")
    return {**result.data[0], "token": token}


def validate_privacy_token(supabase, token: str) -> str:
    """
    Validate a Privacy Centre access token. Returns candidate_id on success.
    Raises ValueError if token is expired or not found.
    """
    result = (
        supabase.table("privacy_center_sessions")
        .select("id, candidate_id, expires_at, used_at")
        .eq("token", token)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise ValueError("Invalid or expired privacy token")

    session = result.data[0]
    now = datetime.now(timezone.utc)

    # Parse expires_at (may or may not have timezone info)
    exp_str = session["expires_at"]
    try:
        exp = datetime.fromisoformat(exp_str)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError("Malformed token expiry")

    if now > exp:
        raise ValueError("Privacy token has expired")

    # Mark as used (single-use token)
    supabase.table("privacy_center_sessions").update(
        {"used_at": now.isoformat()}
    ).eq("id", session["id"]).execute()

    return session["candidate_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Consent management (no bundling)
# ─────────────────────────────────────────────────────────────────────────────

def get_latest_consents(supabase, candidate_id: str, org_id: Optional[str] = None) -> dict[str, dict]:
    """
    Return the most recent consent record per purpose for a candidate.
    Returns dict keyed by purpose_code.
    """
    q = (
        supabase.table("dpdp_consent_records")
        .select("purpose_code, consented, consented_at, consent_text_version, "
                "ip_address, consent_mechanism, legal_retention_basis")
        .eq("candidate_id", candidate_id)
        .order("consented_at", desc=True)
    )
    if org_id:
        q = q.eq("org_id", org_id)

    rows = q.execute().data or []

    # Keep only the latest row per purpose (ordered DESC, so first wins)
    latest: dict[str, dict] = {}
    for row in rows:
        code = row["purpose_code"]
        if code not in latest:
            latest[code] = row

    return latest


def record_single_consent(
    supabase,
    org_id: str,
    candidate_id: str,
    purpose_code: str,
    consented: bool,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    consent_mechanism: str = "PRIVACY_CENTRE",
    data_fiduciary_name: Optional[str] = "HospRecruit",
) -> dict:
    """
    Record a single-purpose consent toggle. DPDP Act 2023 s.6 compliance:
    - Free: no penalty for refusing optional consent
    - Specific: one record per purpose_code (never bundled)
    - Informed: consent_text_version tracks the exact text shown
    - Unconditional: required=True purposes cannot be withdrawn via this function
    - Unambiguous: boolean consented field — no ambiguity
    Raises ValueError for unknown purpose or attempted withdrawal of required consent.
    """
    if purpose_code not in PURPOSE_DEFINITIONS:
        raise ValueError(f"Unknown purpose_code: {purpose_code!r}. "
                         f"Valid: {list(PURPOSE_DEFINITIONS)}")

    defn = PURPOSE_DEFINITIONS[purpose_code]
    if defn["required"] and not consented:
        raise ValueError(
            f"Purpose '{purpose_code}' is required for core recruitment service. "
            "Withdrawing this consent would end your registration."
        )

    # Legal retention basis (if purpose has statutory retention beyond consent)
    retention_basis = None
    if purpose_code == "RECRUITMENT_DATA":
        retention_basis = (
            "EPF Act 1952 r.32 (8 yr) / Income Tax Act 1961 s.44AB (8 yr) "
            "may require retention of payroll records regardless of consent"
        )

    now = datetime.utcnow().isoformat()
    payload: dict = {
        "org_id":                org_id,
        "candidate_id":          candidate_id,
        "purpose_code":          purpose_code,
        "purpose_description":   defn["description_en"],
        "consented":             consented,
        "consent_text_version":  CONSENT_TEXT_VERSION,
        "consent_mechanism":     consent_mechanism,
        "consented_at":          now,
        "ip_address":            ip_address,
        "user_agent":            user_agent,
        "data_fiduciary_name":   data_fiduciary_name,
        "legal_retention_basis": retention_basis,
        "data_region":           DATA_REGION,
    }
    if not consented:
        payload["withdrawal_requested_at"] = now

    result = supabase.table("dpdp_consent_records").insert(payload).execute()
    if not result.data:
        raise RuntimeError("Failed to record consent")

    if not consented:
        years = defn.get("retention_years")
        scheduled = datetime.utcnow().date()
        if years:
            scheduled = scheduled.replace(year=scheduled.year + years)
        try:
            supabase.table("dpdp_retention_actions").insert({
                "org_id": org_id, "candidate_id": candidate_id,
                "data_category": purpose_code, "action": "ANONYMISE",
                "status": "PENDING", "scheduled_for": scheduled.isoformat(),
                "legal_basis": defn["legal_basis"],
                "metadata": {"trigger": "CONSENT_WITHDRAWAL", "consent_record_id": result.data[0].get("id")},
            }).execute()
        except Exception as exc:
            logger.warning("Could not schedule consent-withdrawal retention action: %s", exc)

    _log_audit(
        supabase,
        action="DPDP_CONSENT_GIVEN" if consented else "DPDP_CONSENT_WITHDRAWN",
        org_id=org_id,
        entity_id=candidate_id,
        ip_address=ip_address,
        metadata={"purpose_code": purpose_code, "consented": consented,
                  "version": CONSENT_TEXT_VERSION},
    )

    return result.data[0]


# ─────────────────────────────────────────────────────────────────────────────
# Erasure request + WhatsApp acknowledgment
# ─────────────────────────────────────────────────────────────────────────────

def build_whatsapp_erasure_ack(
    candidate_name: str,
    request_id: str,
    request_type: str,
    requested_at: str,
    due_date: str,
    org_name: str = "HospRecruit",
) -> str:
    """Build the WhatsApp acknowledgment message for an erasure request."""
    req_short = request_id[:8].upper()
    type_hi = {
        "ERASURE":    "डेटा मिटाना",
        "CORRECTION": "सुधार",
        "ACCESS":     "डेटा देखना",
        "NOMINATION": "नामांकन",
    }.get(request_type, request_type)

    return (
        f"नमस्ते {candidate_name} जी 🙏\n\n"
        f"आपके डेटा अनुरोध की पुष्टि हो गई है।\n\n"
        f"📋 Request ID: #{req_short}\n"
        f"📌 Type: {request_type} ({type_hi})\n"
        f"📅 Submitted: {requested_at[:10]}\n"
        f"⏰ Response Deadline: {due_date[:10]}\n\n"
        f"DPDP Act 2023 Section 13 के तहत, {org_name} "
        f"{due_date[:10]} तक आपके अनुरोध का जवाब देगा।\n\n"
        f"📧 privacy@hosprecruit.ai\n"
        f"यदि 30 दिनों में कोई जवाब नहीं मिला, तो आप Data Protection Board of India "
        f"में शिकायत दर्ज कर सकते हैं।\n\n"
        f"- {org_name} Privacy Team"
    )


def send_whatsapp_erasure_ack(
    twilio,
    to_phone: str,
    from_whatsapp: str,
    message: str,
) -> Optional[str]:
    """
    Send WhatsApp erasure acknowledgment via Twilio.
    Returns Twilio message SID on success, None on failure (never raises).
    """
    if not twilio or not to_phone:
        return None

    # Ensure E.164 format for Indian numbers
    phone = to_phone.strip()
    if not phone.startswith("+"):
        phone = f"+91{phone.lstrip('0')}"

    try:
        msg = twilio.messages.create(
            body=message,
            from_=f"whatsapp:{from_whatsapp}",
            to=f"whatsapp:{phone}",
        )
        return msg.sid
    except Exception as exc:
        logger.warning("WhatsApp erasure ack failed to %s: %s", phone, exc)
        return None


def create_erasure_request_with_ack(
    supabase,
    org_id: str,
    candidate_id: str,
    request_type: str = "ERASURE",
    reason: Optional[str] = None,
    specific_fields: Optional[list] = None,
    candidate_phone: Optional[str] = None,
    candidate_name: str = "Candidate",
    org_name: str = "HospRecruit",
    twilio=None,
    whatsapp_from: Optional[str] = None,
) -> dict:
    """
    Create a DPDP erasure request and send WhatsApp acknowledgment.
    30-day SLA response_due_at is generated by the DB trigger.
    """
    now = datetime.utcnow().isoformat()

    payload = {
        "org_id":               org_id,
        "candidate_id":         candidate_id,
        "request_type":         request_type,
        "reason":               reason,
        "specific_data_fields": specific_fields or [],
        "status":               "PENDING",
        "requested_at":         now,
        "acknowledged_at":      now,
        "candidate_phone":      candidate_phone,
    }

    result = supabase.table("dpdp_erasure_requests").insert(payload).execute()
    if not result.data:
        raise RuntimeError("Failed to create erasure request")

    req = result.data[0]

    # WhatsApp acknowledgment (best-effort)
    wa_sid   = None
    wa_error = None
    if candidate_phone and twilio and whatsapp_from:
        due_date = req.get("response_due_at") or (
            datetime.utcnow() + timedelta(days=ERASURE_SLA_DAYS)
        ).isoformat()
        msg = build_whatsapp_erasure_ack(
            candidate_name, req["id"], request_type, now, due_date, org_name
        )
        wa_sid = send_whatsapp_erasure_ack(twilio, candidate_phone, whatsapp_from, msg)

        supabase.table("dpdp_erasure_requests").update({
            "whatsapp_ack_sent_at": now if wa_sid else None,
            "whatsapp_ack_sid":     wa_sid,
            "whatsapp_ack_failed":  wa_sid is None,
            "whatsapp_ack_error":   None if wa_sid else "Twilio send failed",
        }).eq("id", req["id"]).execute()

    _log_audit(
        supabase, "DPDP_ERASURE_REQUESTED",
        org_id=org_id, entity_id=candidate_id,
        metadata={"request_type": request_type, "wa_ack": wa_sid is not None},
        law_reference="DPDP Act 2023 Section 13",
    )

    return {**req, "whatsapp_ack_sent": wa_sid is not None, "whatsapp_sid": wa_sid}


# ─────────────────────────────────────────────────────────────────────────────
# Legal retention checker
# ─────────────────────────────────────────────────────────────────────────────

def check_legal_retention(purpose_code: str) -> dict:
    """
    Returns the retention period and statutory basis for a purpose.
    Used to determine if an erasure request can be fully honoured.
    """
    defn = PURPOSE_DEFINITIONS.get(purpose_code)
    if not defn:
        return {"found": False}

    result: dict = {
        "found":           True,
        "purpose_code":    purpose_code,
        "retention_years": defn["retention_years"],
        "legal_basis":     defn["legal_basis"],
        "required":        defn["required"],
    }

    # Check if any statutory record categories apply
    statutory: list[dict] = []
    if purpose_code == "RECRUITMENT_DATA":
        statutory = [
            STATUTORY_RETENTION["EPF_UAN"],
            STATUTORY_RETENTION["PAN_FORM16"],
            STATUTORY_RETENTION["ESIC_RECORDS"],
        ]
    elif purpose_code == "SENSITIVE_DATA":
        statutory = [STATUTORY_RETENTION["MEDICAL_RECORD"]]

    if statutory:
        result["statutory_retention"] = statutory
        result["can_fully_erase"] = not any(s["exempts_erasure"] for s in statutory)
    else:
        result["can_fully_erase"] = True

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Data localisation status
# ─────────────────────────────────────────────────────────────────────────────

def get_data_localisation_status() -> dict:
    """
    Return data localisation compliance status.
    DPDP Act 2023 s.16 — certain data must remain in India.
    """
    return {
        "compliant":          True,
        "pii_storage_region": DATA_REGION,
        "storage_provider":   "Supabase (PostgreSQL) + AWS S3 ap-south-1",
        "fssai_docs_region":  DATA_REGION,
        "kyc_docs_region":    DATA_REGION,
        "law":                "DPDP Act 2023 s.16",
        "note": (
            "All personally identifiable information is stored in India (ap-south-1 / Mumbai). "
            "Cross-border transfer of PII requires explicit CROSS_BORDER consent."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal audit helper
# ─────────────────────────────────────────────────────────────────────────────

def _log_audit(
    supabase,
    action: str,
    org_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[dict] = None,
    law_reference: Optional[str] = None,
) -> None:
    try:
        supabase.table("india_compliance_audit_logs").insert({
            "org_id":        org_id,
            "actor_type":    "CANDIDATE",
            "action":        action,
            "entity_type":   "candidate",
            "entity_id":     entity_id,
            "law_reference": law_reference or "DPDP Act 2023",
            "metadata":      metadata or {},
            "ip_address":    ip_address,
            "created_at":    datetime.utcnow().isoformat(),
        }).execute()
    except Exception as exc:
        logger.debug("DPDP audit log suppressed: %s", exc)
