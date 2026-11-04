"""Language resolution shared by the API, the WhatsApp bot and generated PDFs.

Mirrors `frontend/src/lib/staffOpsI18n.ts`. The two must agree, because a
supervisor who sees Tamil on screen should receive Tamil on WhatsApp.
"""

from __future__ import annotations

from typing import Any

SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "label": "English", "native_label": "English", "script": "Latin"},
    {"code": "hi", "label": "Hindi", "native_label": "हिंदी", "script": "Devanagari"},
    {"code": "te", "label": "Telugu", "native_label": "తెలుగు", "script": "Telugu"},
    {"code": "ta", "label": "Tamil", "native_label": "தமிழ்", "script": "Tamil"},
    {"code": "kn", "label": "Kannada", "native_label": "ಕನ್ನಡ", "script": "Kannada"},
]

LANGUAGE_CODES = tuple(entry["code"] for entry in SUPPORTED_LANGUAGES)

DEFAULT_LANGUAGE = "en"

# `properties.state` is free text, so both the name and the usual two-letter
# code are matched. Anything unrecognised falls back to English rather than
# guessing at a region.
STATE_TO_LANGUAGE: dict[str, str] = {
    "telangana": "te", "ts": "te", "tg": "te",
    "andhra pradesh": "te", "ap": "te",
    "tamil nadu": "ta", "tamilnadu": "ta", "tn": "ta",
    "puducherry": "ta", "pondicherry": "ta", "py": "ta",
    "karnataka": "kn", "ka": "kn",
    "uttar pradesh": "hi", "up": "hi",
    "madhya pradesh": "hi", "mp": "hi",
    "bihar": "hi", "br": "hi",
    "rajasthan": "hi", "rj": "hi",
    "haryana": "hi", "hr": "hi",
    "delhi": "hi", "new delhi": "hi", "dl": "hi",
    "jharkhand": "hi", "jh": "hi",
    "chhattisgarh": "hi", "cg": "hi",
    "uttarakhand": "hi", "uk": "hi", "ut": "hi",
    "himachal pradesh": "hi", "hp": "hi",
}

# Scripts that must be sent as Unicode SMS (requirement 7). A GSM-7 message is
# 160 characters; a Unicode one is only 70, so an Indic SMS costs more parts.
UNICODE_SMS_LANGUAGES = ("hi", "te", "ta", "kn")


def default_language_for_state(state: str | None) -> str:
    if not state:
        return DEFAULT_LANGUAGE
    return STATE_TO_LANGUAGE.get(state.strip().lower(), DEFAULT_LANGUAGE)


def resolve_language(preferred: str | None, state: str | None = None) -> str:
    """Preference wins, then the hotel's state, then English."""
    if preferred and preferred in LANGUAGE_CODES:
        return preferred
    return default_language_for_state(state)


def requires_unicode_sms(language: str) -> bool:
    """True when an SMS in this language cannot be sent as GSM-7."""
    return language in UNICODE_SMS_LANGUAGES


def sms_segments(text: str, language: str) -> int:
    """How many SMS parts this message costs.

    Indic scripts force UCS-2: 70 characters per part, 67 when concatenated.
    Getting this wrong is a billing surprise, not a crash, so it is worth
    computing before a bulk send.
    """
    if not text:
        return 0
    if requires_unicode_sms(language):
        single, multi = 70, 67
    else:
        single, multi = 160, 153
    if len(text) <= single:
        return 1
    return -(-len(text) // multi)  # ceiling division


def language_label(code: str) -> str:
    for entry in SUPPORTED_LANGUAGES:
        if entry["code"] == code:
            return entry["native_label"]
    return code


def pick_for_user(user_row: dict[str, Any], property_row: dict[str, Any] | None = None) -> str:
    """Resolve from a users row and optionally its property row."""
    return resolve_language(
        (user_row or {}).get("preferred_language"),
        (property_row or {}).get("state"),
    )
