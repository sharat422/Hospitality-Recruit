"""
Badge Service — Hindi badge catalog, milestone detection, and auto-award.

Six gamification badges (as specified):
  पहला कदम    (First Step)      — 1 hire
  टीम बिल्डर (Team Builder)    — 3 hires
  टैलेंट हंटर (Talent Hunter)  — 5 hires
  स्टार रेफरर (Star Referrer)  — 10 hires
  Legend                        — 20 hires
  दोस्त बनाओ  (Make Friends)   — 5 WhatsApp shares
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Badge catalog — source of truth for milestone thresholds
# ---------------------------------------------------------------------------

BADGE_CATALOG: list[dict] = [
    {
        "name":           "पहला कदम",
        "name_en":        "First Step",
        "name_hi":        "पहला कदम",
        "description":    "Got your very first referral hired!",
        "description_hi": "पहला referral hire कराया! आपका पहला कदम। 🌱",
        "icon":           "🌱",
        "tier":           "BRONZE",
        "milestone_type": "hired_count",
        "threshold":      1,
        "reward_bonus":   500,
    },
    {
        "name":           "टीम बिल्डर",
        "name_en":        "Team Builder",
        "name_hi":        "टीम बिल्डर",
        "description":    "Referred 3 candidates who got hired.",
        "description_hi": "3 candidates hire कराए — आप एक अच्छे टीम प्लेयर हैं! 🤝",
        "icon":           "🤝",
        "tier":           "SILVER",
        "milestone_type": "hired_count",
        "threshold":      3,
        "reward_bonus":   1500,
    },
    {
        "name":           "टैलेंट हंटर",
        "name_en":        "Talent Hunter",
        "name_hi":        "टैलेंट हंटर",
        "description":    "Referred 5 candidates who got hired.",
        "description_hi": "5 candidates hire कराए — talent ढूंढने में माहिर! 🎯",
        "icon":           "🎯",
        "tier":           "GOLD",
        "milestone_type": "hired_count",
        "threshold":      5,
        "reward_bonus":   3000,
    },
    {
        "name":           "स्टार रेफरर",
        "name_en":        "Star Referrer",
        "name_hi":        "स्टार रेफरर",
        "description":    "Referred 10 candidates who got hired.",
        "description_hi": "10 candidates hire कराए — आप हमारे Star हैं! ⭐",
        "icon":           "⭐",
        "tier":           "GOLD",
        "milestone_type": "hired_count",
        "threshold":      10,
        "reward_bonus":   5000,
    },
    {
        "name":           "Legend",
        "name_en":        "Legend",
        "name_hi":        "Legend",
        "description":    "Referred 20 candidates who got hired. You are a legend!",
        "description_hi": "20 candidates hire कराए — आप एक Legend हैं! 💎",
        "icon":           "💎",
        "tier":           "PLATINUM",
        "milestone_type": "hired_count",
        "threshold":      20,
        "reward_bonus":   10000,
    },
    {
        "name":           "दोस्त बनाओ",
        "name_en":        "Make Friends",
        "name_hi":        "दोस्त बनाओ",
        "description":    "Shared 5 referrals via WhatsApp.",
        "description_hi": "WhatsApp से 5 referral share किए — दोस्त बनाओ, साथ बढ़ो! 📱",
        "icon":           "📱",
        "tier":           "BRONZE",
        "milestone_type": "whatsapp_count",
        "threshold":      5,
        "reward_bonus":   500,
    },
]

# Pre-sorted milestone lists for O(n) lookup
_HIRED_MILESTONES: list[dict] = sorted(
    [b for b in BADGE_CATALOG if b["milestone_type"] == "hired_count"],
    key=lambda b: b["threshold"],
)
_WA_MILESTONES: list[dict] = sorted(
    [b for b in BADGE_CATALOG if b["milestone_type"] == "whatsapp_count"],
    key=lambda b: b["threshold"],
)

TIER_ORDER = {"BRONZE": 0, "SILVER": 1, "GOLD": 2, "PLATINUM": 3}


# ---------------------------------------------------------------------------
# Milestone helpers
# ---------------------------------------------------------------------------

def get_next_milestone(hired_count: int, whatsapp_count: int = 0) -> Optional[dict]:
    """
    Return the next unearned milestone.

    Checks hired milestones first (primary track), then WhatsApp milestones.
    Returns None when all milestones have been completed.
    """
    for badge in _HIRED_MILESTONES:
        if hired_count < badge["threshold"]:
            return {
                "badge_name":    badge["name_hi"],
                "badge_name_en": badge["name_en"],
                "icon":          badge["icon"],
                "tier":          badge["tier"],
                "threshold":     badge["threshold"],
                "current":       hired_count,
                "progress_pct":  min(99, int((hired_count / badge["threshold"]) * 100)),
                "reward_bonus":  badge["reward_bonus"],
                "milestone_type": "hired_count",
            }

    for badge in _WA_MILESTONES:
        if whatsapp_count < badge["threshold"]:
            return {
                "badge_name":    badge["name_hi"],
                "badge_name_en": badge["name_en"],
                "icon":          badge["icon"],
                "tier":          badge["tier"],
                "threshold":     badge["threshold"],
                "current":       whatsapp_count,
                "progress_pct":  min(99, int((whatsapp_count / badge["threshold"]) * 100)),
                "reward_bonus":  badge["reward_bonus"],
                "milestone_type": "whatsapp_count",
            }

    return None   # all milestones completed


def award_milestones(supabase, user_id: str, hired_count: int, whatsapp_count: int) -> list[dict]:
    """
    Check every badge in the catalog and award any that are now earned
    but not yet recorded in employee_badges.

    Returns the list of newly awarded badge dicts (empty if none).
    This is idempotent — calling it twice for the same counts is safe.
    """
    awarded: list[dict] = []

    try:
        # Fetch all badge definitions from DB (to get their UUIDs)
        badges_res = supabase.table("referral_badges").select("*").execute()
        badge_by_name: dict[str, dict] = {
            b["name"]: b for b in (badges_res.data or [])
        }

        # Fetch already-earned badge IDs for this user
        earned_res = (
            supabase.table("employee_badges")
            .select("badge_id")
            .eq("user_id", user_id)
            .execute()
        )
        earned_ids: set[str] = {r["badge_id"] for r in (earned_res.data or [])}

        now = datetime.utcnow().isoformat()

        for entry in BADGE_CATALOG:
            db_badge = badge_by_name.get(entry["name"])
            if not db_badge:
                continue   # badge not seeded yet (run migration 013 first)

            if db_badge["id"] in earned_ids:
                continue   # already earned

            count = hired_count if entry["milestone_type"] == "hired_count" else whatsapp_count
            if count < entry["threshold"]:
                continue   # milestone not yet reached

            # Award the badge
            try:
                supabase.table("employee_badges").insert({
                    "user_id":               user_id,
                    "badge_id":              db_badge["id"],
                    "referral_count_at_award": count,
                    "earned_at":             now,
                }).execute()
                awarded.append({**db_badge, **entry})
                logger.info(
                    "Badge awarded: %s to user %s (count=%d)",
                    entry["name"], user_id, count,
                )
            except Exception as exc:
                err_str = str(exc).lower()
                if "unique" in err_str or "duplicate" in err_str:
                    pass   # concurrent award — safe to ignore
                else:
                    logger.warning("Badge insert failed (%s): %s", entry["name"], exc)

    except Exception as exc:
        logger.warning("award_milestones failed for user %s: %s", user_id, exc)

    return awarded
