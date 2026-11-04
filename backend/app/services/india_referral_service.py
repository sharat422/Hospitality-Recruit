"""India Referral Program Engine — Service helpers."""

from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote
import logging

logger = logging.getLogger(__name__)

BADGE_THRESHOLDS = [
    {"name": "First Hire",      "required_hires": 1},
    {"name": "Star Referrer",   "required_hires": 3},
    {"name": "Hiring Champion", "required_hires": 5},
    {"name": "Talent Magnet",   "required_hires": 10},
    {"name": "Loyalty Ace",     "required_hires": 20},
]


def format_inr(amount: float) -> str:
    """Format number using Indian numbering system: ₹12,34,567."""
    amount = int(amount)
    s = str(amount)
    if len(s) <= 3:
        return f"₹{s}"
    last3 = s[-3:]
    rest = s[:-3]
    groups: list[str] = []
    while len(rest) > 2:
        groups.append(rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.append(rest)
    groups.reverse()
    return f"₹{','.join(groups)},{last3}"


def get_active_campaign(supabase) -> Optional[dict]:
    """Return the highest-multiplier active festive campaign right now."""
    now = datetime.utcnow().isoformat()
    try:
        result = (
            supabase.table("referral_campaigns")
            .select("*")
            .eq("is_active", True)
            .lte("start_date", now)
            .gte("end_date", now)
            .order("bonus_multiplier", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.warning(f"Campaign lookup failed: {e}")
        return None


def calculate_total_reward(base_amount: float, campaign: Optional[dict] = None) -> dict:
    """Apply campaign multiplier + flat bonus to a base reward amount."""
    multiplier = float(campaign.get("bonus_multiplier", 1.0)) if campaign else 1.0
    flat = float(campaign.get("bonus_flat", 0.0)) if campaign else 0.0
    total = (base_amount * multiplier) + flat
    return {
        "base_amount": base_amount,
        "campaign_multiplier": multiplier,
        "campaign_flat_bonus": flat,
        "total_reward": total,
        "formatted": format_inr(total),
        "campaign_name": campaign.get("name") if campaign else None,
    }


def check_retention_eligibility(hire_date_str: Optional[str], retention_days: int = 90) -> bool:
    """True if hire_date + retention_days <= now (90-day bonus gate)."""
    if not hire_date_str:
        return False
    try:
        hd = datetime.fromisoformat(hire_date_str.replace("Z", ""))
        return datetime.utcnow() >= hd + timedelta(days=retention_days)
    except Exception:
        return False


def build_whatsapp_share_link(
    referral_link: str,
    job_title: str,
    reward_inr: float,
    campaign: Optional[dict] = None,
) -> str:
    """Build wa.me deeplink with pre-filled Hindi/English message."""
    reward_str = format_inr(reward_inr)
    if campaign:
        msg = (
            f"{campaign.get('banner_text', '🎉 Special Offer!')}\n\n"
            f"Apply for *{job_title}* — I earn {reward_str} when you join! 🙌\n"
            f"Apply here: {referral_link}"
        )
    else:
        msg = (
            f"नमस्ते! 👋 I think you'd be a great fit for *{job_title}*.\n"
            f"Apply here and I earn {reward_str}: {referral_link}"
        )
    return f"https://wa.me/?text={quote(msg)}"


def check_and_award_badges(supabase, user_id: str, hired_count: int) -> list[dict]:
    """Check if user qualifies for new hire-count badges and insert awards."""
    awarded: list[dict] = []
    try:
        badges_res = supabase.table("referral_badges").select("*").execute()
        all_badges = {b["name"]: b for b in (badges_res.data or [])}

        earned_res = (
            supabase.table("employee_badges")
            .select("badge_id")
            .eq("user_id", user_id)
            .execute()
        )
        earned_ids = {r["badge_id"] for r in (earned_res.data or [])}

        for threshold in BADGE_THRESHOLDS:
            badge = all_badges.get(threshold["name"])
            if not badge:
                continue
            if hired_count >= threshold["required_hires"] and badge["id"] not in earned_ids:
                try:
                    supabase.table("employee_badges").insert({
                        "user_id": user_id,
                        "badge_id": badge["id"],
                        "referral_count_at_award": hired_count,
                        "earned_at": datetime.utcnow().isoformat(),
                    }).execute()
                    awarded.append(badge)
                except Exception as e:
                    logger.warning(f"Badge insert failed ({badge['name']}): {e}")
    except Exception as e:
        logger.warning(f"Badge check failed: {e}")
    return awarded


def check_and_award_whatsapp_badge(supabase, user_id: str) -> Optional[dict]:
    """Award 'WhatsApp Hero' badge if user has 5+ WhatsApp-shared referrals."""
    try:
        count_res = (
            supabase.table("referrals")
            .select("id", count="exact")
            .eq("referrer_id", user_id)
            .eq("whatsapp_shared", True)
            .execute()
        )
        wa_count = count_res.count or 0
        if wa_count < 5:
            return None

        badge_res = supabase.table("referral_badges").select("*").eq("name", "WhatsApp Hero").limit(1).execute()
        if not badge_res.data:
            return None
        badge = badge_res.data[0]

        earned_res = (
            supabase.table("employee_badges")
            .select("id")
            .eq("user_id", user_id)
            .eq("badge_id", badge["id"])
            .limit(1)
            .execute()
        )
        if earned_res.data:
            return None

        supabase.table("employee_badges").insert({
            "user_id": user_id,
            "badge_id": badge["id"],
            "referral_count_at_award": wa_count,
            "earned_at": datetime.utcnow().isoformat(),
        }).execute()
        return badge
    except Exception as e:
        logger.warning(f"WhatsApp badge check failed: {e}")
        return None
