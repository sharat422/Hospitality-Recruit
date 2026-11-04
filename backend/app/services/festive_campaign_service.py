"""
Festive Campaign Service — comprehensive Indian festival engine.

Supports all 7 required festivals:
  DIWALI, EID, HOLI, ONAM, PONGAL, CHRISTMAS, NEW_YEAR

Key capabilities:
  • All active campaigns at once (not just the best one)
  • Next upcoming campaign with countdown
  • Stacked bonus calculation (highest multiplier + sum of flat bonuses)
  • Festival metadata for UI (emoji, Hindi name, color, description)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Festival metadata — UI display properties
# ---------------------------------------------------------------------------

FESTIVAL_META: dict[str, dict] = {
    "DIWALI": {
        "name_en":        "Diwali",
        "name_hi":        "दीवाली",
        "emoji":          "🪔",
        "color":          "#FF6B00",
        "description_hi": "रोशनी का त्योहार — refer करें, दुगना कमाएं!",
        "description_en": "Festival of Lights — earn double referral rewards!",
    },
    "EID": {
        "name_en":        "Eid ul-Fitr",
        "name_hi":        "ईद मुबारक",
        "emoji":          "🌙",
        "color":          "#10B981",
        "description_hi": "ईद की खुशियों में referral bonus भी!",
        "description_en": "Eid Mubarak — celebrate with bonus referral rewards!",
    },
    "HOLI": {
        "name_en":        "Holi",
        "name_hi":        "होली",
        "emoji":          "🎨",
        "color":          "#EC4899",
        "description_hi": "रंगों के त्योहार में रंगीन कमाई!",
        "description_en": "Festival of Colours — colourful referral bonuses!",
    },
    "ONAM": {
        "name_en":        "Onam",
        "name_hi":        "ओणम",
        "emoji":          "🌸",
        "color":          "#F59E0B",
        "description_hi": "Kerala का फसल त्योहार — Onam bonanza referral!",
        "description_en": "Kerala harvest festival — extra referral bonuses!",
    },
    "PONGAL": {
        "name_en":        "Pongal",
        "name_hi":        "पोंगल",
        "emoji":          "🌾",
        "color":          "#16A34A",
        "description_hi": "Tamil Nadu का फसल त्योहार — नई फसल, नई कमाई!",
        "description_en": "Tamil Nadu harvest festival — fresh season, fresh rewards!",
    },
    "CHRISTMAS": {
        "name_en":        "Christmas",
        "name_hi":        "क्रिसमस",
        "emoji":          "🎄",
        "color":          "#DC2626",
        "description_hi": "क्रिसमस की शुभकामनाएं — referral bonus के साथ!",
        "description_en": "Season's greetings with bonus referral rewards!",
    },
    "NEW_YEAR": {
        "name_en":        "New Year",
        "name_hi":        "नया साल",
        "emoji":          "🎆",
        "color":          "#4F46E5",
        "description_hi": "नए साल में नई कमाई — refer करें और जीतें!",
        "description_en": "New Year, new earnings — refer and win!",
    },
}


def _enrich(campaign: dict) -> dict:
    """Attach festival_meta to a campaign dict."""
    meta = FESTIVAL_META.get(campaign.get("festival_name", ""), {})
    return {**campaign, "festival_meta": meta}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_all_active_campaigns(supabase) -> list[dict]:
    """
    Return all campaigns currently in progress.

    Unlike the original single-campaign helper, this returns ALL active
    campaigns so the UI can show stacked bonuses when festivals overlap.
    Sorted by bonus_multiplier descending.
    """
    now = datetime.utcnow().isoformat()
    try:
        result = (
            supabase.table("referral_campaigns")
            .select("*")
            .eq("is_active", True)
            .lte("start_date", now)
            .gte("end_date", now)
            .order("bonus_multiplier", desc=True)
            .execute()
        )
        return [_enrich(c) for c in (result.data or [])]
    except Exception as exc:
        logger.warning("get_all_active_campaigns failed: %s", exc)
        return []


def get_next_campaign(supabase) -> Optional[dict]:
    """
    Return the nearest upcoming campaign (start_date > now).
    Includes `days_until` so the UI can show a countdown.
    """
    now = datetime.utcnow().isoformat()
    try:
        result = (
            supabase.table("referral_campaigns")
            .select("*")
            .eq("is_active", True)
            .gt("start_date", now)
            .order("start_date", desc=False)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None

        campaign = _enrich(result.data[0])

        # Compute days until campaign starts
        start = datetime.fromisoformat(campaign["start_date"].replace("Z", ""))
        days_until = max(0, (start - datetime.utcnow()).days)
        campaign["days_until"] = days_until
        return campaign
    except Exception as exc:
        logger.warning("get_next_campaign failed: %s", exc)
        return None


def stack_bonuses(base_amount: float, campaigns: list[dict]) -> dict:
    """
    Calculate the effective reward when multiple campaigns are active.

    Strategy (consistent with Razorpay payouts logic):
      • Take the single highest bonus_multiplier (not additive).
      • Sum ALL flat bonuses (additive).

    Returns a breakdown dict for the UI.
    """
    if not campaigns:
        return {
            "total":      base_amount,
            "multiplier": 1.0,
            "flat_bonus": 0.0,
            "breakdown":  [],
        }

    max_mult  = max(c.get("bonus_multiplier", 1.0) for c in campaigns)
    flat_sum  = sum(c.get("bonus_flat", 0.0) for c in campaigns)
    total     = (base_amount * max_mult) + flat_sum

    return {
        "total":      total,
        "multiplier": max_mult,
        "flat_bonus": flat_sum,
        "breakdown": [
            {
                "name":       c.get("name"),
                "festival":   c.get("festival_name"),
                "multiplier": c.get("bonus_multiplier"),
                "flat":       c.get("bonus_flat"),
            }
            for c in campaigns
        ],
    }


def get_festival_meta(festival_name: str) -> dict:
    """Lookup display metadata for a festival. Returns safe defaults."""
    return FESTIVAL_META.get(festival_name, {
        "name_en":        festival_name,
        "name_hi":        festival_name,
        "emoji":          "🎉",
        "color":          "#6B7280",
        "description_hi": "Special referral bonus!",
        "description_en": "Special referral bonus!",
    })


def get_supported_festivals() -> list[str]:
    """Return the list of all supported festival codes."""
    return list(FESTIVAL_META.keys())
