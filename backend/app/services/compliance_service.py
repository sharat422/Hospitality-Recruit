"""
Compliance Service — jurisdiction detection, scheduling violation checks,
GDPR anonymization helpers, and audit logging.
Feature 06: Compliance, Visa & Right-to-Work Management.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Jurisdiction rules: advance notice and rest hours per jurisdiction
JURISDICTION_RULES = {
    "NYC": {
        "advance_notice_days": 14,
        "min_rest_hours": 11,
        "penalty": 100,
    },
    "SF": {
        "advance_notice_days": 14,
        "min_rest_hours": 0,
        "penalty": 75,
    },
    "CHICAGO": {
        "advance_notice_days": 10,
        "min_rest_hours": 0,
        "penalty": 50,
    },
    "SEATTLE": {
        "advance_notice_days": 14,
        "min_rest_hours": 0,
        "penalty": 100,
    },
    "UK_NATIONAL": {
        "advance_notice_days": 0,
        "min_rest_hours": 11,
        "penalty": 0,
    },
}


def detect_jurisdiction(location: str) -> str:
    """
    Detect the compliance jurisdiction from a location string.
    Returns a jurisdiction code or 'NONE'.
    """
    if not location:
        return "NONE"
    loc = location.upper()
    if "NYC" in loc or "NEW YORK" in loc:
        return "NYC"
    if "SF" in loc or "SAN FRANCISCO" in loc:
        return "SF"
    if "CHICAGO" in loc:
        return "CHICAGO"
    if "SEATTLE" in loc:
        return "SEATTLE"
    if "UK" in loc or "ENGLAND" in loc or "LONDON" in loc:
        return "UK_NATIONAL"
    return "NONE"


def check_scheduling_violation(
    shift_start: datetime,
    shift_end: datetime,
    last_shift_end: Optional[datetime],
    published_at: datetime,
    jurisdiction: str,
) -> list:
    """
    Check for Fair Workweek / scheduling violations.
    Returns a list of violation dicts with type, severity, description, penalty_risk.
    """
    violations = []
    rules = JURISDICTION_RULES.get(jurisdiction)
    if not rules:
        return violations

    # --- Advance notice check ---
    notice_days = rules.get("advance_notice_days", 0)
    if notice_days > 0:
        # published_at must be at least notice_days before shift_start
        # Ensure both are timezone-aware or both naive
        if shift_start.tzinfo is not None and published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        elif shift_start.tzinfo is None and published_at.tzinfo is not None:
            shift_start = shift_start.replace(tzinfo=timezone.utc)

        advance_hours = (shift_start - published_at).total_seconds() / 3600
        advance_days = advance_hours / 24
        if advance_days < notice_days:
            penalty = rules.get("penalty", 0)
            violations.append(
                {
                    "type": "INSUFFICIENT_ADVANCE_NOTICE",
                    "severity": "FINE_RISK" if penalty > 0 else "WARNING",
                    "description": (
                        f"{jurisdiction} requires {notice_days} days advance notice. "
                        f"Only {advance_days:.1f} days provided."
                    ),
                    "penalty_risk": penalty,
                }
            )

    # --- Minimum rest between shifts ---
    min_rest = rules.get("min_rest_hours", 0)
    if min_rest > 0 and last_shift_end is not None:
        # Normalize timezone
        if shift_start.tzinfo is not None and last_shift_end.tzinfo is None:
            last_shift_end = last_shift_end.replace(tzinfo=timezone.utc)
        elif shift_start.tzinfo is None and last_shift_end.tzinfo is not None:
            shift_start = shift_start.replace(tzinfo=timezone.utc)

        rest_hours = (shift_start - last_shift_end).total_seconds() / 3600
        if rest_hours < min_rest:
            penalty = rules.get("penalty", 0)
            violations.append(
                {
                    "type": "INSUFFICIENT_REST",
                    "severity": "CRITICAL" if penalty > 50 else "WARNING",
                    "description": (
                        f"{jurisdiction} requires {min_rest}h rest between shifts. "
                        f"Only {rest_hours:.1f}h gap found (clopening restriction)."
                    ),
                    "penalty_risk": penalty,
                }
            )

    return violations


def anonymize_candidate_fields(candidate_id: str) -> dict:
    """
    Return a dict of fields to overwrite for a candidate to anonymize them.
    Does not perform the update — caller is responsible for the DB write.
    """
    return {
        "first_name": "ANONYMIZED",
        "last_name": "ANONYMIZED",
        "email": f"anon_{candidate_id[:8]}@deleted.invalid",
        "phone": None,
        "location": None,
        "resume_url": None,
        "linkedin_url": None,
        "data_status": "ANONYMIZED",
    }


async def log_audit_action(
    supabase,
    actor_type: str,
    actor_id: Optional[str],
    action: str,
    entity_type: str,
    entity_id: str,
    metadata: dict,
    ip: Optional[str] = None,
) -> None:
    """
    Insert a record into compliance_audit_logs.
    Swallows all errors to avoid disrupting the main flow.
    """
    try:
        supabase.table("compliance_audit_logs").insert(
            {
                "actor_type": actor_type,
                "actor_id": actor_id,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "metadata": metadata,
                "ip_address": ip,
            }
        ).execute()
    except Exception as exc:
        logger.warning("audit log insert failed (non-fatal): %s", exc)
