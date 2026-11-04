import random
import secrets
import string
import logging
from typing import Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Code / token generation
# ---------------------------------------------------------------------------

def generate_referral_code(length: int = 10) -> str:
    """Short human-readable code shown to the employee (e.g. REF-AB12CD34EF)."""
    chars = random.choices(string.ascii_uppercase + string.digits, k=length)
    return "REF-" + "".join(chars)


def generate_link_token() -> str:
    """
    Cryptographically random, URL-safe token used in the public referral link.
    32 characters from a 64-character alphabet — ~192 bits of entropy.
    Practically impossible to enumerate or brute-force.
    """
    return secrets.token_urlsafe(24)  # 24 raw bytes → 32-char base64url string


# ---------------------------------------------------------------------------
# Link builders
# ---------------------------------------------------------------------------

def build_referral_link(base_url: str, job_role_id: str, referral_code: str) -> str:
    """Legacy link builder — uses short referral_code (kept for backward compat)."""
    return f"{base_url}/apply/{job_role_id}?ref={referral_code}"


def build_referral_link_v2(base_url: str, job_role_id: str, link_token: str) -> str:
    """Secure link builder — uses the opaque link_token, not the short code."""
    return f"{base_url}/apply/{job_role_id}?token={link_token}"


def build_whatsapp_url(
    referral_link: str,
    job_title: str = "a hospitality role",
    reward: float = 0,
    currency: str = "₹",
) -> str:
    """
    Return a wa.me deeplink with a pre-filled share message.
    If reward > 0 the message mentions the incentive to motivate sharing.
    """
    if reward > 0:
        reward_str = (
            f"{currency}{reward:,.0f}"
            if currency == "₹"
            else f"{currency}{reward:.0f}"
        )
        msg = (
            f"Hi! I think you'd be great for *{job_title}*. "
            f"Apply using my referral link — I earn {reward_str} if you join! "
            f"👉 {referral_link}"
        )
    else:
        msg = (
            f"Hi! I think you'd be great for *{job_title}*. "
            f"Apply using my referral link: 👉 {referral_link}"
        )
    return f"https://wa.me/?text={quote(msg)}"


# ---------------------------------------------------------------------------
# Reward lookup
# ---------------------------------------------------------------------------

def get_reward_amount(supabase, job_role_id: str, event: str = "hire") -> float:
    """Fetch configured reward amount for a role and event from referral_rewards_config."""
    try:
        result = (
            supabase.table("referral_rewards_config")
            .select("*")
            .eq("job_role_id", job_role_id)
            .eq("is_active", True)
            .execute()
        )
        if result.data:
            config = result.data[0]
            return config.get("reward_on_hire", 50) if event == "hire" else config.get("reward_on_apply", 0)
    except Exception as e:
        logger.warning(f"Could not fetch reward config: {e}")
    return 50.0


def get_program_reward(supabase, program_id: str) -> float:
    """Fetch reward_on_hire from a referral_programs row."""
    try:
        result = (
            supabase.table("referral_programs")
            .select("reward_on_hire, currency")
            .eq("id", program_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if result.data:
            return float(result.data[0].get("reward_on_hire", 5000))
    except Exception as e:
        logger.warning(f"Could not fetch program reward: {e}")
    return 5000.0
