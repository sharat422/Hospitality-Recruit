"""
Ghosting Risk Service — calculates risk scores for candidates likely to ghost.
Pain Point #3: 30-40% no-show/ghosting rate in hospitality.
"""

from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

SIGNAL_WEIGHTS = {
    "no_reply_48h": 0.25,
    "interview_unconfirmed": 0.20,
    "shortlisted_5_days": 0.15,
    "multi_platform": 0.15,
    "offer_no_response_24h": 0.30,
    "portal_not_viewed": 0.10,
    "commute_far": 0.10,
    "prev_ghosted": 0.20,
}


def calculate_ghosting_risk(
    candidate: dict,
    messages: list,
    interview_slot: Optional[dict] = None,
) -> dict:
    score = 0.0
    signals = []
    now = datetime.utcnow()

    # No reply to last recruiter message in >48h
    recruiter_msgs = [m for m in messages if m.get("sender_type") == "RECRUITER"]
    if recruiter_msgs:
        last_recruiter_msg = max(recruiter_msgs, key=lambda m: m.get("sent_at", ""))
        last_sent = last_recruiter_msg.get("sent_at")
        if last_sent:
            if isinstance(last_sent, str):
                last_sent = datetime.fromisoformat(last_sent.replace("Z", "+00:00")).replace(tzinfo=None)
            if (now - last_sent).total_seconds() > 172800:
                score += SIGNAL_WEIGHTS["no_reply_48h"]
                signals.append("No reply to recruiter message in 48+ hours")

    # Interview scheduled but not confirmed
    if interview_slot and interview_slot.get("status") == "BOOKED":
        created = interview_slot.get("created_at")
        if created:
            if isinstance(created, str):
                created = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
            if (now - created).total_seconds() > 86400:
                score += SIGNAL_WEIGHTS["interview_unconfirmed"]
                signals.append("Interview scheduled but unconfirmed for 24+ hours")

    # In SHORTLISTED stage > 5 days
    pipeline_stage = candidate.get("pipeline_stage", "")
    updated_at = candidate.get("updated_at")
    if pipeline_stage == "SHORTLISTED" and updated_at:
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).replace(tzinfo=None)
        if (now - updated_at).total_seconds() > 432000:
            score += SIGNAL_WEIGHTS["shortlisted_5_days"]
            signals.append("In Shortlisted stage for 5+ days")

    # Offer with no response in >24h
    if pipeline_stage == "OFFER_SENT" and updated_at:
        if isinstance(updated_at, str):
            _updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).replace(tzinfo=None) if isinstance(updated_at, str) else updated_at
        else:
            _updated_at = updated_at
        if (now - _updated_at).total_seconds() > 86400:
            score += SIGNAL_WEIGHTS["offer_no_response_24h"]
            signals.append("Offer sent with no response in 24+ hours — CRITICAL")

    # Cap at 1.0
    score = min(score, 1.0)

    if score < 0.3:
        level = "LOW"
    elif score < 0.5:
        level = "MEDIUM"
    elif score < 0.7:
        level = "HIGH"
    else:
        level = "CRITICAL"

    return {"risk_score": round(score, 3), "risk_level": level, "risk_signals": signals}
