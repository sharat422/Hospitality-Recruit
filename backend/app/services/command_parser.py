"""
command_parser.py — WhatsApp HR Bot command parser.

Converts raw WhatsApp message text into a structured ParsedCommand object.
Self-contained: no imports from hr_bot_service (avoids circular dependency).

Supported commands (canonical / English / Hindi / Hinglish):
  LEAVE     छुट्टी  chhutti  chutti  leav
  PAYSLIP   वेतन    tankha   salary  pay
  SHIFT     पाली    shikayat schedule roster
  BALANCE   बकाया   bakaya   bal
  COMPLAINT शिकायत  shikayat issue   report
  CAREER    नौकरी   naukri   jobs    openings
  HELP      मदद     madad    ?       menu

Structured output (ParsedCommand):
  command       — canonical uppercase string or "UNKNOWN"
  args          — list[str]  (raw remaining text; first element is full tail)
  parsed_args   — dict with command-specific structured fields
  is_valid      — True if command recognised AND arguments pass validation
  error_message — human-readable error when is_valid=False, None otherwise
  raw_text      — original message
  language      — "en" | "hi" | "hinglish"
  matched_alias — the actual word that triggered recognition
  confidence    — 1.0 exact · 0.8 alias · 0.6 fuzzy
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Output type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ParsedCommand:
    command:       str               # LEAVE | PAYSLIP | SHIFT | BALANCE |
    #                                  COMPLAINT | CAREER | HELP | UNKNOWN
    args:          List[str]         # raw tail split; args[0] = full tail text
    parsed_args:   Dict[str, Any]    # structured, command-specific fields
    is_valid:      bool              # False when args fail validation
    error_message: Optional[str]     # populated when is_valid=False
    raw_text:      str               # original message before any processing
    language:      str               # "en" | "hi" | "hinglish"
    matched_alias: str               # word that triggered the match
    confidence:    float             # 1.0 exact · 0.8 alias · 0.6 fuzzy

    def to_dict(self) -> dict:
        """Serialise to plain dict (for API responses / logging)."""
        return {
            "command":       self.command,
            "args":          self.args,
            "parsedArgs":    self.parsed_args,
            "isValid":       self.is_valid,
            "errorMessage":  self.error_message,
            "language":      self.language,
            "matchedAlias":  self.matched_alias,
            "confidence":    self.confidence,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Alias table  (alias_lower → (canonical, language, confidence))
# ─────────────────────────────────────────────────────────────────────────────

# fmt: off
_ALIASES: Dict[str, tuple[str, str, float]] = {
    # ── English canonical ────────────────────────────────────────────────────
    "leave":      ("LEAVE",     "en", 1.0),
    "payslip":    ("PAYSLIP",   "en", 1.0),
    "shift":      ("SHIFT",     "en", 1.0),
    "balance":    ("BALANCE",   "en", 1.0),
    "complaint":  ("COMPLAINT", "en", 1.0),
    "career":     ("CAREER",    "en", 1.0),
    "help":       ("HELP",      "en", 1.0),
    "survey":     ("SURVEY",    "en", 1.0),
    "feedback":   ("SURVEY",    "en", 0.9),

    # ── English aliases ───────────────────────────────────────────────────────
    "salary":     ("PAYSLIP",   "en", 0.9),
    "pay":        ("PAYSLIP",   "en", 0.8),
    "wages":      ("PAYSLIP",   "en", 0.8),
    "slip":       ("PAYSLIP",   "en", 0.8),
    "schedule":   ("SHIFT",     "en", 0.9),
    "roster":     ("SHIFT",     "en", 0.9),
    "duty":       ("SHIFT",     "en", 0.8),
    "jobs":       ("CAREER",    "en", 0.9),
    "openings":   ("CAREER",    "en", 0.9),
    "vacancies":  ("CAREER",    "en", 0.8),
    "promote":    ("CAREER",    "en", 0.7),
    "report":     ("COMPLAINT", "en", 0.8),
    "issue":      ("COMPLAINT", "en", 0.8),
    "problem":    ("COMPLAINT", "en", 0.8),
    "grievance":  ("COMPLAINT", "en", 0.9),
    "?":          ("HELP",      "en", 0.9),
    "??":         ("HELP",      "en", 0.9),
    "hi":         ("HELP",      "en", 0.7),
    "hello":      ("HELP",      "en", 0.7),
    "hey":        ("HELP",      "en", 0.7),
    "menu":       ("HELP",      "en", 0.9),
    "commands":   ("HELP",      "en", 0.9),
    "start":      ("HELP",      "en", 0.8),

    # ── Hindi — Devanagari ────────────────────────────────────────────────────
    "छुट्टी":    ("LEAVE",     "hi", 1.0),
    "छुट्टि":    ("LEAVE",     "hi", 0.9),
    "लीव":        ("LEAVE",     "hi", 0.8),
    "अवकाश":      ("LEAVE",     "hi", 0.8),

    "वेतन":       ("PAYSLIP",   "hi", 1.0),
    "तनख्वाह":    ("PAYSLIP",   "hi", 0.9),
    "सैलरी":      ("PAYSLIP",   "hi", 0.9),
    "वेतन-पर्ची": ("PAYSLIP",   "hi", 0.9),

    "पाली":       ("SHIFT",     "hi", 1.0),
    "शिफ्ट":      ("SHIFT",     "hi", 0.9),
    "ड्यूटी":     ("SHIFT",     "hi", 0.8),
    "समय-सारिणी": ("SHIFT",     "hi", 0.8),

    "बकाया":      ("BALANCE",   "hi", 0.9),
    "बैलेंस":     ("BALANCE",   "hi", 0.9),
    "शेष":        ("BALANCE",   "hi", 0.8),
    "छुट्टी-शेष": ("BALANCE",   "hi", 0.9),

    "शिकायत":     ("COMPLAINT", "hi", 1.0),
    "समस्या":     ("COMPLAINT", "hi", 0.8),
    "परेशानी":    ("COMPLAINT", "hi", 0.8),

    "नौकरी":      ("CAREER",    "hi", 1.0),
    "करियर":      ("CAREER",    "hi", 0.9),
    "अवसर":       ("CAREER",    "hi", 0.8),
    "पदोन्नति":   ("CAREER",    "hi", 0.7),

    "मदद":        ("HELP",      "hi", 1.0),
    "सहायता":     ("HELP",      "hi", 0.9),
    "हेल्प":      ("HELP",      "hi", 0.8),
    "नमस्ते":     ("HELP",      "hi", 0.7),
    "हेलो":       ("HELP",      "hi", 0.7),
    "सर्वे":       ("SURVEY",    "hi", 1.0),
    "प्रतिक्रिया": ("SURVEY",    "hi", 0.9),

    # ── Hinglish — transliteration ────────────────────────────────────────────
    "chhutti":    ("LEAVE",     "hinglish", 0.8),
    "chutti":     ("LEAVE",     "hinglish", 0.8),
    "leav":       ("LEAVE",     "hinglish", 0.7),  # common typo

    "vetan":      ("PAYSLIP",   "hinglish", 0.8),
    "tankha":     ("PAYSLIP",   "hinglish", 0.8),

    "pali":       ("SHIFT",     "hinglish", 0.8),
    "duti":       ("SHIFT",     "hinglish", 0.7),

    "bakaya":     ("BALANCE",   "hinglish", 0.8),
    "bal":        ("BALANCE",   "hinglish", 0.8),

    "shikayat":   ("COMPLAINT", "hinglish", 0.8),
    "shikayet":   ("COMPLAINT", "hinglish", 0.8),
    "samasya":    ("COMPLAINT", "hinglish", 0.7),

    "naukri":     ("CAREER",    "hinglish", 0.8),
    "career":     ("CAREER",    "en",       1.0),  # already above, harmless dup

    "madad":      ("HELP",      "hinglish", 0.8),
    "sahayata":   ("HELP",      "hinglish", 0.8),
}
# fmt: on

# Canonical command set for quick membership checks
_KNOWN_COMMANDS: frozenset[str] = frozenset(
    {"LEAVE", "PAYSLIP", "SHIFT", "BALANCE", "COMPLAINT", "CAREER", "HELP", "SURVEY"}
)

# ─────────────────────────────────────────────────────────────────────────────
# Month tables (English + Hindi)
# ─────────────────────────────────────────────────────────────────────────────

MONTH_MAP: Dict[str, int] = {
    # English
    "january": 1,  "jan": 1,
    "february": 2, "feb": 2,
    "march": 3,    "mar": 3,
    "april": 4,    "apr": 4,
    "may": 5,
    "june": 6,     "jun": 6,
    "july": 7,     "jul": 7,
    "august": 8,   "aug": 8,
    "september": 9,"sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11,"nov": 11,
    "december": 12,"dec": 12,
    # Hindi — Devanagari
    "जनवरी": 1, "फरवरी": 2, "मार्च": 3,  "अप्रैल": 4,
    "मई": 5,    "जून": 6,   "जुलाई": 7,  "अगस्त": 8,
    "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "नवंबर": 11, "दिसंबर": 12,
    # Hinglish transliteration
    "janvari": 1, "farvari": 2, "march": 3, "aprail": 4,
    "mai": 5,     "jun": 6,    "julai": 7, "agast": 8,
    "sitambar": 9, "aktoobar": 10, "navambar": 11, "disambar": 12,
}

MONTH_NAME: Dict[int, str] = {
    1: "January", 2: "February", 3: "March",    4: "April",
    5: "May",     6: "June",     7: "July",      8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


# ─────────────────────────────────────────────────────────────────────────────
# Language detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """
    Classify message language as "hi", "hinglish", or "en".
    Hindi = ≥3 Devanagari chars; Hinglish = 1-2; else English.
    """
    devanagari = sum(1 for c in text if "ऀ" <= c <= "ॿ")
    if devanagari >= 3:
        return "hi"
    if devanagari >= 1:
        return "hinglish"
    return "en"


# ─────────────────────────────────────────────────────────────────────────────
# Command resolution
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_command(word: str) -> tuple[str, str, str, float]:
    """
    Map a single word to (canonical_command, matched_alias, language, confidence).
    Priority: exact alias → fuzzy match → UNKNOWN.
    """
    lower = word.lower()

    # 1. Exact alias lookup (covers canonical + all aliases)
    if lower in _ALIASES:
        cmd, lang, conf = _ALIASES[lower]
        return cmd, lower, lang, conf

    # 2. Case-insensitive canonical check (e.g. "LEAVE" already uppercase)
    upper = word.upper()
    if upper in _KNOWN_COMMANDS:
        return upper, lower, "en", 1.0

    # 3. Fuzzy match against canonical commands only
    #    (don't fuzzy-match against every alias — too noisy)
    for canonical in _KNOWN_COMMANDS:
        if _fuzzy_match(upper, canonical):
            return canonical, lower, "en", 0.6

    return "UNKNOWN", lower, detect_language(word), 0.0


def _fuzzy_match(a: str, b: str) -> bool:
    """
    True if two short words are likely the same with 1-2 typos.
    Checks character overlap ratio; skips very short words.
    """
    if len(a) < 3 or len(b) < 3:
        return False
    if abs(len(a) - len(b)) > 2:
        return False
    # Simple char-overlap heuristic (works well for 4-9 char command words)
    common = sum(1 for c in a if c in b)
    threshold = max(len(a), len(b)) - 2
    return common >= threshold


# ─────────────────────────────────────────────────────────────────────────────
# Date + month parsing helpers (standalone, no hr_bot_service import)
# ─────────────────────────────────────────────────────────────────────────────

# Natural-language relative date keywords (English + Hindi)
_RELATIVE_DATES: Dict[str, int] = {
    "today": 0,    "आज": 0,
    "tomorrow": 1, "कल": 1,      # "kal" = tomorrow in spoken Hindi
    "kal": 1,
    "parso": 2,    "परसों": 2,   # day after tomorrow
}

def parse_date_arg(s: str) -> Optional[str]:
    """
    Parse a date token into ISO format YYYY-MM-DD.
    Returns None (does not raise) so callers can generate a user-friendly error.
    Handles:
      ISO:           2026-06-20
      DMY formats:   20-06-2026  20/06/2026  20.06.2026
      Natural:       20 June  June 20  20th June  जून 20
      Relative:      today  tomorrow  आज  कल
    """
    if not s:
        return None
    s = s.strip()

    # Relative keywords
    lower = s.lower()
    if lower in _RELATIVE_DATES:
        delta = _RELATIVE_DATES[lower]
        return (datetime.now(timezone.utc).date() + timedelta(days=delta)).isoformat()

    # Structured formats
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
                "%d-%m-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass

    # Natural language: strip ordinal suffixes (1st, 2nd, 3rd, 20th …)
    s_clean = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", s, flags=re.I)
    for fmt in ("%d %B", "%B %d", "%d %b", "%b %d",
                "%d %B %Y", "%B %d %Y", "%d %b %Y", "%b %d %Y"):
        try:
            d = datetime.strptime(s_clean.strip().title(), fmt)
            year = datetime.now(timezone.utc).year
            # If month+day only, use current year
            if "%Y" not in fmt:
                d = d.replace(year=year)
            return d.date().isoformat()
        except ValueError:
            pass

    return None


def parse_month_arg(raw: str, now: Optional[datetime] = None) -> tuple[Optional[int], int]:
    """
    Parse a month token into (month_number, year).
    Accepts: "April" "apr" "4" "April 2026" "अप्रैल" "अप्रैल 2026"
    Returns (None, year) when the month cannot be determined.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    parts = raw.strip().split()
    year  = now.year

    # If two tokens given, second might be a year
    if len(parts) >= 2:
        try:
            year = int(parts[1])
            raw  = parts[0]
        except ValueError:
            raw = parts[0]

    lower = raw.lower()
    if lower in MONTH_MAP:
        return MONTH_MAP[lower], year

    # Numeric month
    try:
        m = int(raw)
        if 1 <= m <= 12:
            return m, year
    except ValueError:
        pass

    return None, year


# ─────────────────────────────────────────────────────────────────────────────
# Inference helpers
# ─────────────────────────────────────────────────────────────────────────────

def infer_leave_type(reason: str) -> str:
    r = reason.lower()
    if any(w in r for w in (
        "sick", "ill", "fever", "unwell", "hospital", "doctor",
        "medicine", "flu", "cold", "injury",
        "बीमार", "बुखार", "अस्पताल", "दवाई",
    )):
        return "SICK"
    if any(w in r for w in (
        "emergency", "urgent", "accident", "death", "funeral",
        "family", "marriage", "wedding",
        "अर्जेंट", "आपातकाल", "मृत्यु", "शादी",
    )):
        return "EMERGENCY"
    return "CASUAL"


def infer_complaint_category(text: str) -> str:
    t = text.lower()
    if any(w in t for w in (
        "salary", "pay", "payment", "payslip", "wages", "unpaid",
        "वेतन", "तनख्वाह",
    )):
        return "PAYROLL"
    if any(w in t for w in (
        "harass", "bully", "abuse", "misbehave", "molest",
        "उत्पीड़न", "दुर्व्यवहार",
    )):
        return "HARASSMENT"
    if any(w in t for w in (
        "safety", "accident", "danger", "injury", "fire", "unsafe",
        "सुरक्षा", "खतरा", "चोट",
    )):
        return "SAFETY"
    if any(w in t for w in (
        "discriminat", "bias", "unfair", "racist", "casteist",
        "भेदभाव",
    )):
        return "DISCRIMINATION"
    if any(w in t for w in (
        "toilet", "canteen", "locker", "uniform", "facilities", "room",
        "शौचालय", "कैंटीन",
    )):
        return "FACILITIES"
    if any(w in t for w in (
        "overtime", "schedule", "roster", "break time", "rest period",
        "ओवरटाइम", "रोस्टर",
    )):
        return "WORKPLACE"
    return "GENERAL"


def infer_complaint_severity(text: str) -> str:
    t = text.lower()
    if any(w in t for w in (
        "assault", "threat", "violence", "abuse", "illegal",
        "police", "fir", "arrest", "rape", "sexual",
    )):
        return "CRITICAL"
    if any(w in t for w in (
        "harass", "discriminat", "unsafe", "danger", "accident",
        "injury", "bully",
    )):
        return "HIGH"
    if any(w in t for w in (
        "salary", "pay", "unpaid", "misbehave",
    )):
        return "MEDIUM"
    return "LOW"


# ─────────────────────────────────────────────────────────────────────────────
# Per-command argument validators
# Each returns (is_valid, error_message, parsed_args_dict)
# ─────────────────────────────────────────────────────────────────────────────

def _validate_leave(raw_tail: str) -> tuple[bool, Optional[str], dict]:
    """
    LEAVE [date] [reason]
    Date token can be 1 or 2 words (handles "June 20", "20th June", "20 June").
    Tries 1-word date first, then 2-word date if the first attempt fails.
    """
    if not raw_tail.strip():
        return False, (
            "Please provide a date and reason.\n"
            "Format: LEAVE [date] [reason]\n"
            "Example: LEAVE 2026-06-20 not feeling well\n"
            "उदाहरण: छुट्टी 2026-06-20 तबियत ठीक नहीं"
        ), {}

    tokens = raw_tail.strip().split()

    # Try 1-token date first (ISO, DMY, relative)
    iso_date = parse_date_arg(tokens[0])
    if iso_date is not None:
        date_raw = tokens[0]
        reason   = " ".join(tokens[1:]).strip()
    else:
        # Try 2-token date ("June 20", "20 June", "20th June")
        two_token = " ".join(tokens[:2]) if len(tokens) >= 2 else ""
        iso_date  = parse_date_arg(two_token) if two_token else None
        if iso_date is not None:
            date_raw = two_token
            reason   = " ".join(tokens[2:]).strip()
        else:
            # Nothing worked
            bad_token = tokens[0] if len(tokens) <= 1 else " ".join(tokens[:2])
            return False, (
                f"Could not understand '{bad_token}' as a date.\n"
                f"Use YYYY-MM-DD, e.g. LEAVE 2026-06-20 sick\n"
                f"या: छुट्टी 20-06-2026 बीमार हूं"
            ), {"date_raw": tokens[0], "reason": " ".join(tokens[1:]).strip()}

    if not reason:
        return False, (
            f"Please add a reason after the date.\n"
            f"Example: LEAVE {date_raw} not feeling well\n"
            f"उदाहरण: LEAVE {date_raw} तबियत ठीक नहीं"
        ), {"date": iso_date, "date_raw": date_raw, "reason": ""}

    leave_type = infer_leave_type(reason)
    return True, None, {
        "date":       iso_date,
        "date_raw":   date_raw,
        "reason":     reason,
        "leave_type": leave_type,
    }


def _validate_payslip(raw_tail: str) -> tuple[bool, Optional[str], dict]:
    """
    PAYSLIP [month]
    No arg is valid — defaults to previous month.
    Invalid only when a month arg is given but cannot be parsed.
    """
    if not raw_tail.strip():
        # Default: previous month
        now   = datetime.now(timezone.utc)
        month = now.month - 1 or 12
        year  = now.year - (1 if now.month == 1 else 0)
        return True, None, {
            "month":      month,
            "year":       year,
            "month_name": MONTH_NAME[month],
            "is_default": True,
        }

    month, year = parse_month_arg(raw_tail.strip())
    if month is None:
        return False, (
            f"Could not understand '{raw_tail.strip()}' as a month.\n"
            "Try: PAYSLIP April  or  PAYSLIP April 2026\n"
            "या:  वेतन अप्रैल  or  वेतन 4"
        ), {"raw": raw_tail.strip()}

    return True, None, {
        "month":      month,
        "year":       year,
        "month_name": MONTH_NAME[month],
        "is_default": False,
    }


def _validate_complaint(raw_tail: str) -> tuple[bool, Optional[str], dict]:
    """
    COMPLAINT [text]        — anonymous by default (Req 2).
    COMPLAINT NAMED [text]  — attach employee identity explicitly.
    COMPLAINT ANON  [text]  — explicitly anonymous (backward-compat alias).

    Invalid if text is absent or < 10 chars.
    """
    tail = raw_tail.strip()
    upper = tail.upper()

    # Req 2: anonymous is the DEFAULT; NAMED opts in to identity disclosure
    is_anonymous = True

    if upper.startswith("NAMED "):
        is_anonymous = False
        tail = tail[6:].strip()
    elif upper == "NAMED":
        tail = ""          # NAMED with no text → validation will fail below
    elif upper.startswith("ANON "):
        is_anonymous = True  # explicit (backward-compat)
        tail = tail[5:].strip()
    elif upper == "ANON":
        tail = ""          # ANON with no text → validation will fail below

    if len(tail) < 10:
        return False, (
            "Please describe your complaint in detail (at least 10 characters).\n"
            "Format:  COMPLAINT [your complaint]       ← anonymous by default\n"
            "Named:   COMPLAINT NAMED [your complaint] ← attaches your name\n"
            "उदाहरण: शिकायत इस महीने वेतन नहीं मिला"
        ), {"is_anonymous": is_anonymous}

    category = infer_complaint_category(tail)
    severity = infer_complaint_severity(tail)
    return True, None, {
        "text":         tail,
        "is_anonymous": is_anonymous,
        "category":     category,
        "severity":     severity,
    }


def _validate_noargs(command: str, raw_tail: str) -> tuple[bool, Optional[str], dict]:
    """SHIFT, BALANCE, CAREER, HELP — no arguments needed; always valid."""
    return True, None, {}


def _validate_survey(raw_tail: str) -> tuple[bool, Optional[str], dict]:
    parts = raw_tail.strip().split(None, 1)
    if not parts or not parts[0].isdigit() or int(parts[0]) not in range(1, 6):
        return False, "Reply SURVEY 1-5 followed by an optional comment. Example: SURVEY 4 Good team support", {}
    return True, None, {"score": int(parts[0]), "comment": parts[1].strip() if len(parts) > 1 else None}


# Per-command validator dispatch
_VALIDATORS = {
    "LEAVE":     _validate_leave,
    "PAYSLIP":   _validate_payslip,
    "COMPLAINT": _validate_complaint,
    "SHIFT":     lambda t: _validate_noargs("SHIFT",     t),
    "BALANCE":   lambda t: _validate_noargs("BALANCE",   t),
    "CAREER":    lambda t: _validate_noargs("CAREER",    t),
    "HELP":      lambda t: _validate_noargs("HELP",      t),
    "SURVEY":    _validate_survey,
}


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def parse_command(text: str) -> ParsedCommand:
    """
    Parse a raw WhatsApp message into a structured ParsedCommand.

    Returns ParsedCommand with command="UNKNOWN" and is_valid=False
    when the message cannot be matched to any known command.
    """
    raw_text = text
    text     = text.strip()
    language = detect_language(text)

    if not text:
        return ParsedCommand(
            command       = "UNKNOWN",
            args          = [],
            parsed_args   = {},
            is_valid      = False,
            error_message = "Empty message received.",
            raw_text      = raw_text,
            language      = language,
            matched_alias = "",
            confidence    = 0.0,
        )

    # Split on first whitespace: command-word | remaining tail
    parts    = text.split(None, 1)
    cmd_word = parts[0]
    raw_tail = parts[1].strip() if len(parts) > 1 else ""

    canonical, matched_alias, cmd_lang, confidence = _resolve_command(cmd_word)

    # Language is the message language, not just the command-word language
    # (tail may mix scripts — keep the message-level detection)
    if cmd_lang == "hi" and language == "en":
        language = "hi"   # single Hindi word in otherwise-English message

    if canonical == "UNKNOWN":
        return ParsedCommand(
            command       = "UNKNOWN",
            args          = [text],
            parsed_args   = {"original_text": text},
            is_valid      = False,
            error_message = (
                f"Unknown command '{cmd_word}'.\n"
                "Type HELP or मदद to see all commands."
            ),
            raw_text      = raw_text,
            language      = language,
            matched_alias = matched_alias,
            confidence    = 0.0,
        )

    # Validate args for the resolved command
    validator = _VALIDATORS[canonical]
    is_valid, error_message, parsed_args = validator(raw_tail)

    return ParsedCommand(
        command       = canonical,
        args          = [raw_tail] if raw_tail else [],
        parsed_args   = parsed_args,
        is_valid      = is_valid,
        error_message = error_message,
        raw_text      = raw_text,
        language      = language,
        matched_alias = matched_alias,
        confidence    = confidence,
    )
