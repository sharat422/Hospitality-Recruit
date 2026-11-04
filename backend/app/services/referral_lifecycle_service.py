"""Shared application, hiring and payout lifecycle rules for employee referrals."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


ACTIVE_REFERRAL_STATUSES = ("PENDING", "APPLIED", "SHORTLISTED", "HIRED")


def _rows(result: Any) -> list[dict]:
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


def attribute_application(
    supabase: Any,
    *,
    token: str,
    job_role_id: str,
    application_id: str,
    candidate_email: str | None = None,
    candidate_id: str | None = None,
) -> dict | None:
    """Attach a submitted application to the secure referral token, once."""
    matches = _rows(
        supabase.table("referrals").select("*").eq("link_token", token).eq(
            "job_role_id", job_role_id
        ).limit(1).execute()
    )
    if not matches:
        return None
    referral = matches[0]
    if referral.get("application_id") and referral["application_id"] != application_id:
        raise ValueError("This referral link has already been used")
    if referral.get("status") not in ("PENDING", "APPLIED"):
        raise ValueError("This referral is no longer accepting applications")

    normalized_email = (candidate_email or referral.get("candidate_email") or "").strip().lower() or None
    if normalized_email:
        duplicate = _rows(
            supabase.table("referrals").select("id").eq("job_role_id", job_role_id)
            .ilike("candidate_email", normalized_email).in_("status", list(ACTIVE_REFERRAL_STATUSES))
            .neq("id", referral["id"]).limit(1).execute()
        )
        if duplicate:
            raise ValueError("An active referral already exists for this candidate and job")

    values = {
        "application_id": application_id,
        "status": "APPLIED",
        "candidate_email": normalized_email,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if candidate_id:
        values["candidate_id"] = candidate_id
    updated = _rows(supabase.table("referrals").update(values).eq("id", referral["id"]).execute())
    return updated[0] if updated else {**referral, **values}


def mark_application_referral_hired(supabase: Any, application_id: str, *, hired_at: datetime | None = None) -> dict | None:
    """Start retention eligibility when the linked application reaches HIRED."""
    matches = _rows(
        supabase.table("referrals").select("*").eq("application_id", application_id).limit(1).execute()
    )
    if not matches:
        return None
    referral = matches[0]
    if referral.get("status") in ("BONUS_PAID", "REWARDED"):
        return referral

    hired_at = hired_at or datetime.now(timezone.utc)
    retention_days = 90
    reward = float(referral.get("retention_bonus_amount") or referral.get("reward_amount") or 0)
    if referral.get("program_id"):
        programs = _rows(
            supabase.table("referral_programs").select("retention_days,reward_on_hire")
            .eq("id", referral["program_id"]).limit(1).execute()
        )
        if programs:
            retention_days = int(programs[0].get("retention_days") or 90)
            reward = float(programs[0].get("reward_on_hire") or reward)

    values = {
        "status": "HIRED",
        "hire_date": hired_at.isoformat(),
        "retention_check_date": (hired_at + timedelta(days=retention_days)).isoformat(),
        "retention_bonus_amount": reward,
        "retention_bonus_status": "PENDING",
        "reward_amount": reward,
        "reward_status": "EARNED",
        "updated_at": hired_at.isoformat(),
    }
    updated = _rows(supabase.table("referrals").update(values).eq("id", referral["id"]).execute())
    return updated[0] if updated else {**referral, **values}
