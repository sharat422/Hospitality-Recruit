"""
WhatsApp referral sharing — template engine.

Supports English and Hindi message templates that include:
  property_name, role, salary range, apply link, referral code.

Usage::

    msg = render_template(
        lang="hi",
        property_name="Taj Hotel Mumbai",
        role="Front Desk Executive",
        apply_link="https://app.hosprecruit.in/apply/abc?token=xyz",
        referral_code="REF-ABCD1234",
        salary_min=35_000,
        salary_max=50_000,
        reward=5000,
    )
    url = build_wa_url(msg)
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

SUPPORTED_LANGS = ["en", "hi"]

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
# {salary} placeholder receives a compact INR string like "35K–50K/month".
# All other placeholders are filled verbatim.

TEMPLATES: dict[str, dict] = {
    "en": {
        "name": "English",
        "body": (
            "Hi! 👋\n\n"
            "🏨 *{role}* opening at *{property_name}*!\n\n"
            "💰 Salary: ₹{salary}/month\n"
            "🔗 Apply: {apply_link}\n"
            "📋 Referral Code: *{referral_code}*\n\n"
            "{reward_line}"
            "Please apply before spots fill up! 🙏"
        ),
        "reward_line": "✨ Apply via my link — I earn ₹{reward} if you join!\n",
        "reward_line_none": "",
    },
    "hi": {
        "name": "हिंदी",
        "body": (
            "नमस्ते! 👋\n\n"
            "🏨 *{property_name}* में *{role}* की vacancy है!\n\n"
            "💰 वेतन: ₹{salary}/माह\n"
            "🔗 आवेदन करें: {apply_link}\n"
            "📋 रेफरल कोड: *{referral_code}*\n\n"
            "{reward_line}"
            "जल्दी apply करें, सीटें भर रही हैं! 🙏"
        ),
        "reward_line": "✨ मेरे लिंक से apply करें — join होने पर मुझे ₹{reward} मिलेगा!\n",
        "reward_line_none": "",
    },
}


# ---------------------------------------------------------------------------
# Salary formatting
# ---------------------------------------------------------------------------

def format_salary_inr(val: Optional[int]) -> str:
    """
    Compact Indian salary notation:
      35000  → "35K"
      150000 → "1.5L"
      None   → "Negotiable"
    """
    if not val or val <= 0:
        return "Negotiable"
    if val >= 100_000:
        lakhs = val / 100_000
        # Strip trailing zeros/dot BEFORE appending the suffix letter
        lakhs_str = f"{lakhs:.1f}".rstrip("0").rstrip(".")
        return f"{lakhs_str}L"
    if val >= 1_000:
        k = val // 1_000
        remainder = val % 1_000
        return f"{k}.{remainder // 100}K" if remainder else f"{k}K"
    return str(val)


def format_salary_range(salary_min: Optional[int], salary_max: Optional[int]) -> str:
    """
    Return a range string or a single value:
      35000, 50000  → "35K–50K"
      35000, None   → "35K"
      None, None    → "Negotiable"
    """
    lo = format_salary_inr(salary_min) if salary_min else None
    hi = format_salary_inr(salary_max) if salary_max else None

    if lo and hi and lo != hi:
        return f"{lo}–{hi}"
    return lo or hi or "Negotiable"


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def render_template(
    lang: str,
    property_name: str,
    role: str,
    apply_link: str,
    referral_code: str,
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    reward: float = 0,
) -> str:
    """
    Render a WhatsApp share message.
    Falls back to English for unsupported language codes.
    """
    tmpl = TEMPLATES.get(lang) or TEMPLATES["en"]

    salary = format_salary_range(salary_min, salary_max)

    if reward > 0:
        reward_line = tmpl["reward_line"].format(reward=f"{reward:,.0f}")
    else:
        reward_line = tmpl["reward_line_none"]

    return tmpl["body"].format(
        property_name=property_name,
        role=role,
        salary=salary,
        apply_link=apply_link,
        referral_code=referral_code,
        reward_line=reward_line,
    )


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------

def build_wa_url(message: str) -> str:
    """Encode a message into a wa.me deeplink."""
    return f"https://wa.me/?text={quote(message)}"
