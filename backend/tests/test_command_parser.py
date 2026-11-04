"""
Tests for command_parser.py — WhatsApp HR Bot structured command parser.

Coverage:
  1.  Language detection
  2.  parse_command — English canonical commands
  3.  parse_command — English aliases
  4.  parse_command — Hindi (Devanagari) commands
  5.  parse_command — Hinglish transliteration
  6.  parse_command — fuzzy/typo matching
  7.  parse_command — case insensitivity
  8.  parse_command — unknown commands
  9.  ParsedCommand.to_dict() structure
  10. LEAVE  — valid input, all date formats, leave-type inference
  11. LEAVE  — invalid input (missing date, bad date, missing reason)
  12. PAYSLIP — with and without month arg
  13. PAYSLIP — Hindi month names
  14. PAYSLIP — invalid month
  15. SHIFT / BALANCE / CAREER / HELP — no-arg commands always valid
  16. COMPLAINT — named, anonymous (ANON prefix), category + severity inference
  17. COMPLAINT — too-short text rejected
  18. Date parsing — all supported formats + relative keywords
  19. Month parsing — English, Hindi, numeric, with year
  20. Confidence scoring
"""

from datetime import datetime, timezone

import pytest

from app.services.command_parser import (
    ParsedCommand,
    detect_language,
    infer_complaint_category,
    infer_complaint_severity,
    infer_leave_type,
    parse_command,
    parse_date_arg,
    parse_month_arg,
    MONTH_MAP,
)


# ═════════════════════════════════════════════════════════════════════════════
# 1. Language detection
# ═════════════════════════════════════════════════════════════════════════════

class TestLanguageDetection:
    def test_english(self):
        assert detect_language("LEAVE tomorrow sick") == "en"

    def test_hindi_many_chars(self):
        assert detect_language("छुट्टी चाहिए बीमार हूं") == "hi"

    def test_hinglish_one_char(self):
        assert detect_language("LEAVE कल sick") == "hinglish"

    def test_empty_string(self):
        assert detect_language("") == "en"

    def test_numbers_only(self):
        assert detect_language("12345") == "en"


# ═════════════════════════════════════════════════════════════════════════════
# 2. English canonical commands
# ═════════════════════════════════════════════════════════════════════════════

class TestEnglishCanonical:
    def _cmd(self, text) -> str:
        return parse_command(text).command

    def test_leave(self):    assert self._cmd("LEAVE 2026-06-20 sick")   == "LEAVE"
    def test_payslip(self):  assert self._cmd("PAYSLIP April")           == "PAYSLIP"
    def test_shift(self):    assert self._cmd("SHIFT")                    == "SHIFT"
    def test_balance(self):  assert self._cmd("BALANCE")                  == "BALANCE"
    def test_complaint(self):assert self._cmd("COMPLAINT something wrong") == "COMPLAINT"
    def test_career(self):   assert self._cmd("CAREER")                   == "CAREER"
    def test_help(self):     assert self._cmd("HELP")                     == "HELP"

    def test_lowercase(self):    assert self._cmd("leave 2026-06-20 ill")   == "LEAVE"
    def test_mixed_case(self):   assert self._cmd("Payslip April")          == "PAYSLIP"
    def test_leading_spaces(self):assert self._cmd("  SHIFT  ")             == "SHIFT"

    def test_confidence_exact(self):
        r = parse_command("LEAVE 2026-06-20 sick")
        assert r.confidence == 1.0

    def test_language_en(self):
        r = parse_command("HELP")
        assert r.language == "en"


# ═════════════════════════════════════════════════════════════════════════════
# 3. English aliases
# ═════════════════════════════════════════════════════════════════════════════

class TestEnglishAliases:
    def _cmd(self, text) -> str:
        return parse_command(text).command

    def test_salary_to_payslip(self):  assert self._cmd("salary April")    == "PAYSLIP"
    def test_pay_to_payslip(self):     assert self._cmd("pay")              == "PAYSLIP"
    def test_schedule_to_shift(self):  assert self._cmd("schedule")         == "SHIFT"
    def test_roster_to_shift(self):    assert self._cmd("roster")           == "SHIFT"
    def test_jobs_to_career(self):     assert self._cmd("jobs")             == "CAREER"
    def test_openings_to_career(self): assert self._cmd("openings")         == "CAREER"
    def test_grievance_to_complaint(self): assert self._cmd("grievance manager is mean") == "COMPLAINT"
    def test_issue_to_complaint(self): assert self._cmd("issue my pay is wrong") == "COMPLAINT"
    def test_question_mark_to_help(self): assert self._cmd("?")             == "HELP"
    def test_menu_to_help(self):       assert self._cmd("menu")             == "HELP"
    def test_hi_to_help(self):         assert self._cmd("hi")               == "HELP"
    def test_hello_to_help(self):      assert self._cmd("hello")            == "HELP"

    def test_alias_confidence_below_one(self):
        r = parse_command("salary April")
        assert r.confidence < 1.0
        assert r.confidence >= 0.8


# ═════════════════════════════════════════════════════════════════════════════
# 4. Hindi (Devanagari) commands
# ═════════════════════════════════════════════════════════════════════════════

class TestHindiCommands:
    def _cmd(self, text) -> str:
        return parse_command(text).command

    def test_chhuti_leave(self):      assert self._cmd("छुट्टी 2026-06-20 बीमार") == "LEAVE"
    def test_vetan_payslip(self):     assert self._cmd("वेतन अप्रैल")             == "PAYSLIP"
    def test_pali_shift(self):        assert self._cmd("पाली")                    == "SHIFT"
    def test_bakaya_balance(self):    assert self._cmd("बकाया")                   == "BALANCE"
    def test_shikayat_complaint(self):assert self._cmd("शिकायत मेरा वेतन नहीं मिला") == "COMPLAINT"
    def test_naukri_career(self):     assert self._cmd("नौकरी")                   == "CAREER"
    def test_madad_help(self):        assert self._cmd("मदद")                     == "HELP"
    def test_sahayata_help(self):     assert self._cmd("सहायता")                  == "HELP"
    def test_namaste_help(self):      assert self._cmd("नमस्ते")                  == "HELP"

    def test_hindi_language_detected(self):
        r = parse_command("छुट्टी 2026-06-20 बीमार हूं")
        assert r.language == "hi"

    def test_hindi_confidence(self):
        r = parse_command("छुट्टी 2026-06-20 बीमार")
        assert r.confidence >= 0.8


# ═════════════════════════════════════════════════════════════════════════════
# 5. Hinglish transliteration
# ═════════════════════════════════════════════════════════════════════════════

class TestHinglishCommands:
    def _cmd(self, text) -> str:
        return parse_command(text).command

    def test_chhutti_leave(self):   assert self._cmd("chhutti 2026-06-20 sick") == "LEAVE"
    def test_chutti_leave(self):    assert self._cmd("chutti 2026-06-20 sick")  == "LEAVE"
    def test_tankha_payslip(self):  assert self._cmd("tankha April")             == "PAYSLIP"
    def test_pali_shift(self):      assert self._cmd("pali")                     == "SHIFT"
    def test_bakaya_balance(self):  assert self._cmd("bakaya")                   == "BALANCE"
    def test_shikayat_complaint(self): assert self._cmd("shikayat manager is bad") == "COMPLAINT"
    def test_naukri_career(self):   assert self._cmd("naukri")                   == "CAREER"
    def test_madad_help(self):      assert self._cmd("madad")                    == "HELP"


# ═════════════════════════════════════════════════════════════════════════════
# 6. Fuzzy / typo matching
# ═════════════════════════════════════════════════════════════════════════════

class TestFuzzyMatching:
    def _cmd(self, text) -> str:
        return parse_command(text).command

    def test_leav_typo(self):    assert self._cmd("leav tomorrow sick")   == "LEAVE"
    def test_payslipp_typo(self):assert self._cmd("payslipp April")       == "PAYSLIP"
    def test_shifft_typo(self):  assert self._cmd("shifft")               == "SHIFT"
    def test_balanse_typo(self): assert self._cmd("balanse")              == "BALANCE"
    def test_halp_typo(self):    assert self._cmd("halp")                 == "HELP"

    def test_fuzzy_confidence_below_exact(self):
        exact = parse_command("LEAVE 2026-06-20 sick").confidence
        fuzzy = parse_command("leav 2026-06-20 sick").confidence
        assert fuzzy < exact

    def test_too_short_word_not_fuzzy_matched(self):
        # Single-char commands should not fuzzy-match anything
        r = parse_command("x")
        assert r.command == "UNKNOWN"

    def test_very_different_word_unknown(self):
        assert parse_command("XYZABC123").command == "UNKNOWN"


# ═════════════════════════════════════════════════════════════════════════════
# 7. Unknown commands
# ═════════════════════════════════════════════════════════════════════════════

class TestUnknownCommands:
    def test_random_word(self):
        r = parse_command("FOOBAR")
        assert r.command       == "UNKNOWN"
        assert r.is_valid      is False
        assert r.error_message is not None
        assert r.confidence    == 0.0

    def test_empty_message(self):
        r = parse_command("")
        assert r.command  == "UNKNOWN"
        assert r.is_valid is False

    def test_whitespace_only(self):
        r = parse_command("   ")
        assert r.command == "UNKNOWN"

    def test_number_only(self):
        r = parse_command("123456")
        assert r.command == "UNKNOWN"

    def test_error_message_present(self):
        r = parse_command("RANDOM_CMD")
        assert "HELP" in r.error_message or "मदद" in r.error_message

    def test_raw_text_preserved(self):
        r = parse_command("something unknown")
        assert r.raw_text == "something unknown"


# ═════════════════════════════════════════════════════════════════════════════
# 8. ParsedCommand.to_dict()
# ═════════════════════════════════════════════════════════════════════════════

class TestToDictShape:
    def test_required_keys_present(self):
        r = parse_command("HELP")
        d = r.to_dict()
        for key in ("command", "args", "parsedArgs", "isValid",
                    "errorMessage", "language", "matchedAlias", "confidence"):
            assert key in d, f"Missing key: {key}"

    def test_valid_help_dict(self):
        d = parse_command("HELP").to_dict()
        assert d["command"]      == "HELP"
        assert d["isValid"]      is True
        assert d["errorMessage"] is None
        assert d["confidence"]   == 1.0

    def test_unknown_dict(self):
        d = parse_command("NONSENSE").to_dict()
        assert d["command"]      == "UNKNOWN"
        assert d["isValid"]      is False
        assert d["errorMessage"] is not None


# ═════════════════════════════════════════════════════════════════════════════
# 9. LEAVE command — validation
# ═════════════════════════════════════════════════════════════════════════════

class TestLeaveValidation:
    def _parse(self, text) -> ParsedCommand:
        return parse_command(text)

    # ── Valid cases ───────────────────────────────────────────────────────────
    def test_iso_date_reason(self):
        r = self._parse("LEAVE 2026-06-20 not feeling well")
        assert r.command      == "LEAVE"
        assert r.is_valid     is True
        assert r.parsed_args["date"]   == "2026-06-20"
        assert r.parsed_args["reason"] == "not feeling well"

    def test_dmy_slash(self):
        r = self._parse("LEAVE 20/06/2026 sick")
        assert r.is_valid
        assert r.parsed_args["date"] == "2026-06-20"

    def test_dmy_dash(self):
        r = self._parse("LEAVE 20-06-2026 sick")
        assert r.is_valid
        assert r.parsed_args["date"] == "2026-06-20"

    def test_natural_date(self):
        r = self._parse("LEAVE June 20 not well")
        assert r.is_valid
        assert r.parsed_args["date"].endswith("-06-20")

    def test_ordinal_date(self):
        r = self._parse("LEAVE 20th June headache")
        assert r.is_valid

    def test_relative_today(self):
        r = self._parse("LEAVE today sick")
        assert r.is_valid
        today_utc = datetime.now(timezone.utc).date().isoformat()
        assert r.parsed_args["date"] == today_utc

    def test_relative_tomorrow(self):
        r = self._parse("LEAVE tomorrow family function")
        assert r.is_valid

    def test_relative_kal(self):
        r = self._parse("LEAVE kal sick")
        assert r.is_valid

    # ── Invalid cases ─────────────────────────────────────────────────────────
    def test_no_args(self):
        r = self._parse("LEAVE")
        assert r.command  == "LEAVE"
        assert r.is_valid is False
        assert r.error_message is not None

    def test_bad_date(self):
        r = self._parse("LEAVE 99-99-9999 sick")
        assert r.is_valid is False
        assert "99-99-9999" in r.error_message

    def test_date_no_reason(self):
        r = self._parse("LEAVE 2026-06-20")
        assert r.is_valid is False
        assert r.error_message is not None

    def test_hindi_leave_command(self):
        r = self._parse("छुट्टी 2026-06-20 बीमार")
        assert r.command  == "LEAVE"
        assert r.is_valid is True

    # ── Leave type inference ──────────────────────────────────────────────────
    def test_leave_type_sick(self):
        r = self._parse("LEAVE 2026-06-20 fever and headache")
        assert r.parsed_args["leave_type"] == "SICK"

    def test_leave_type_emergency(self):
        r = self._parse("LEAVE 2026-06-20 family emergency")
        assert r.parsed_args["leave_type"] == "EMERGENCY"

    def test_leave_type_casual_default(self):
        r = self._parse("LEAVE 2026-06-20 personal work")
        assert r.parsed_args["leave_type"] == "CASUAL"

    def test_hindi_sick_reason(self):
        r = self._parse("LEAVE 2026-06-20 बुखार है")
        assert r.parsed_args["leave_type"] == "SICK"


# ═════════════════════════════════════════════════════════════════════════════
# 10. PAYSLIP command — validation
# ═════════════════════════════════════════════════════════════════════════════

class TestPayslipValidation:
    def _parse(self, text) -> ParsedCommand:
        return parse_command(text)

    def test_no_arg_defaults_prev_month(self):
        r = self._parse("PAYSLIP")
        assert r.is_valid
        assert "month" in r.parsed_args
        assert r.parsed_args["is_default"] is True

    def test_full_month_name(self):
        r = self._parse("PAYSLIP April")
        assert r.is_valid
        assert r.parsed_args["month"] == 4

    def test_month_abbreviation(self):
        r = self._parse("PAYSLIP apr")
        assert r.is_valid
        assert r.parsed_args["month"] == 4

    def test_numeric_month(self):
        r = self._parse("PAYSLIP 4")
        assert r.is_valid
        assert r.parsed_args["month"] == 4

    def test_month_with_year(self):
        r = self._parse("PAYSLIP April 2025")
        assert r.is_valid
        assert r.parsed_args["month"] == 4
        assert r.parsed_args["year"]  == 2025

    def test_invalid_month(self):
        r = self._parse("PAYSLIP Octember")
        assert r.is_valid is False
        assert "Octember" in r.error_message

    def test_hindi_month(self):
        r = self._parse("वेतन अप्रैल")
        assert r.command == "PAYSLIP"
        assert r.is_valid
        assert r.parsed_args["month"] == 4

    def test_hindi_month_devanagari(self):
        r = self._parse("PAYSLIP जनवरी")
        assert r.is_valid
        assert r.parsed_args["month"] == 1

    def test_lowercase_month(self):
        r = self._parse("PAYSLIP december")
        assert r.is_valid
        assert r.parsed_args["month"] == 12


# ═════════════════════════════════════════════════════════════════════════════
# 11. COMPLAINT command — validation + anonymous mode
# ═════════════════════════════════════════════════════════════════════════════

class TestComplaintValidation:
    def _parse(self, text) -> ParsedCommand:
        return parse_command(text)

    def test_valid_complaint_anonymous_by_default(self):
        # Default is now anonymous (Req 2 — default anonymous)
        r = self._parse("COMPLAINT My salary has not been paid for this month")
        assert r.command                     == "COMPLAINT"
        assert r.is_valid                    is True
        assert r.parsed_args["is_anonymous"] is True     # default
        assert r.parsed_args["category"]     == "PAYROLL"

    def test_valid_named_complaint_with_prefix(self):
        # Use NAMED prefix to opt in to identity disclosure
        r = self._parse("COMPLAINT NAMED My salary has not been paid for this month")
        assert r.command                     == "COMPLAINT"
        assert r.is_valid                    is True
        assert r.parsed_args["is_anonymous"] is False
        assert r.parsed_args["category"]     == "PAYROLL"

    def test_too_short_text(self):
        r = self._parse("COMPLAINT bad")
        assert r.is_valid is False

    def test_no_text(self):
        r = self._parse("COMPLAINT")
        assert r.is_valid is False

    def test_anonymous_prefix(self):
        r = self._parse("COMPLAINT ANON My manager is harassing me continuously")
        assert r.is_valid
        assert r.parsed_args["is_anonymous"] is True
        assert r.parsed_args["text"]         == "My manager is harassing me continuously"

    def test_anonymous_prefix_case_insensitive(self):
        r = self._parse("COMPLAINT anon something very concerning here")
        assert r.parsed_args["is_anonymous"] is True

    def test_anonymous_alone_invalid(self):
        r = self._parse("COMPLAINT ANON")
        assert r.is_valid is False

    # ── Category inference ────────────────────────────────────────────────────
    def test_payroll_category(self):
        r = self._parse("COMPLAINT My wages have not been credited this month")
        assert r.parsed_args["category"] == "PAYROLL"

    def test_harassment_category(self):
        r = self._parse("COMPLAINT The manager bullies and harasses everyone daily")
        assert r.parsed_args["category"] == "HARASSMENT"

    def test_safety_category(self):
        r = self._parse("COMPLAINT There is a safety hazard near the kitchen equipment")
        assert r.parsed_args["category"] == "SAFETY"

    def test_discrimination_category(self):
        r = self._parse("COMPLAINT I am facing discriminat ion based on my background")
        assert r.parsed_args["category"] == "DISCRIMINATION"

    def test_general_fallback(self):
        r = self._parse("COMPLAINT I have a general concern to raise with HR today")
        assert r.parsed_args["category"] == "GENERAL"

    def test_hindi_complaint(self):
        r = self._parse("शिकायत मेरा वेतन इस महीने नहीं मिला है")
        assert r.command == "COMPLAINT"
        assert r.is_valid is True

    # ── Severity inference ────────────────────────────────────────────────────
    def test_critical_severity(self):
        r = self._parse("COMPLAINT There was a sexual assault incident at the workplace")
        assert r.parsed_args["severity"] == "CRITICAL"

    def test_high_severity(self):
        r = self._parse("COMPLAINT Manager harasses and bullies staff every single day")
        assert r.parsed_args["severity"] == "HIGH"

    def test_medium_severity(self):
        r = self._parse("COMPLAINT Salary was not paid on time this month again")
        assert r.parsed_args["severity"] == "MEDIUM"

    def test_low_severity(self):
        r = self._parse("COMPLAINT I have a minor concern about office atmosphere")
        assert r.parsed_args["severity"] == "LOW"


# ═════════════════════════════════════════════════════════════════════════════
# 12. No-arg commands: SHIFT, BALANCE, CAREER, HELP
# ═════════════════════════════════════════════════════════════════════════════

class TestNoArgCommands:
    @pytest.mark.parametrize("cmd", ["SHIFT", "BALANCE", "CAREER", "HELP"])
    def test_valid_no_args(self, cmd):
        r = parse_command(cmd)
        assert r.command  == cmd
        assert r.is_valid is True
        assert r.error_message is None

    @pytest.mark.parametrize("cmd", ["SHIFT", "BALANCE", "CAREER", "HELP"])
    def test_valid_with_extra_text(self, cmd):
        # Extra text is ignored — command remains valid
        r = parse_command(f"{cmd} extra stuff here")
        assert r.command  == cmd
        assert r.is_valid is True

    def test_shift_parsed_args_empty(self):
        assert parse_command("SHIFT").parsed_args == {}

    def test_balance_parsed_args_empty(self):
        assert parse_command("BALANCE").parsed_args == {}


# ═════════════════════════════════════════════════════════════════════════════
# 13. Date parsing — parse_date_arg()
# ═════════════════════════════════════════════════════════════════════════════

class TestDateParsing:
    def _d(self, s) -> str | None:
        return parse_date_arg(s)

    def test_iso_format(self):
        assert self._d("2026-06-20") == "2026-06-20"

    def test_dmy_dash(self):
        assert self._d("20-06-2026") == "2026-06-20"

    def test_dmy_slash(self):
        assert self._d("20/06/2026") == "2026-06-20"

    def test_dmy_dot(self):
        assert self._d("20.06.2026") == "2026-06-20"

    def test_natural_day_month(self):
        result = self._d("20 June")
        assert result is not None
        assert result.endswith("-06-20")

    def test_natural_month_day(self):
        result = self._d("June 20")
        assert result is not None
        assert result.endswith("-06-20")

    def test_ordinal(self):
        result = self._d("20th June")
        assert result is not None
        assert result.endswith("-06-20")

    def test_relative_today(self):
        # Use UTC to match the parser's timezone (avoids cross-tz failures)
        today = datetime.now(timezone.utc).date().isoformat()
        assert self._d("today") == today

    def test_relative_tomorrow(self):
        from datetime import timedelta
        tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        assert self._d("tomorrow") == tomorrow

    def test_relative_aaj_hindi(self):
        today = datetime.now(timezone.utc).date().isoformat()
        assert self._d("आज") == today

    def test_relative_kal_hindi(self):
        from datetime import timedelta
        tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        assert self._d("कल") == tomorrow

    def test_relative_kal_hinglish(self):
        from datetime import timedelta
        tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        assert self._d("kal") == tomorrow

    def test_invalid_returns_none(self):
        assert self._d("not-a-date") is None

    def test_empty_returns_none(self):
        assert self._d("") is None

    def test_gibberish_returns_none(self):
        assert self._d("xyzabc") is None


# ═════════════════════════════════════════════════════════════════════════════
# 14. Month parsing — parse_month_arg()
# ═════════════════════════════════════════════════════════════════════════════

class TestMonthParsing:
    def _m(self, s):
        return parse_month_arg(s, now=datetime(2026, 5, 20, tzinfo=timezone.utc))

    def test_full_english_name(self):   assert self._m("April")[0]    == 4
    def test_abbreviation(self):        assert self._m("apr")[0]      == 4
    def test_december_abbrev(self):     assert self._m("dec")[0]      == 12
    def test_numeric_string(self):      assert self._m("4")[0]        == 4
    def test_numeric_12(self):          assert self._m("12")[0]       == 12

    def test_with_year(self):
        m, y = self._m("April 2025")
        assert m == 4 and y == 2025

    def test_numeric_with_year(self):
        m, y = self._m("4 2025")
        assert m == 4 and y == 2025

    def test_hindi_april(self):         assert self._m("अप्रैल")[0]  == 4
    def test_hindi_january(self):       assert self._m("जनवरी")[0]   == 1
    def test_hindi_december(self):      assert self._m("दिसंबर")[0]  == 12

    def test_invalid_returns_none(self):
        m, _ = self._m("Octember")
        assert m is None

    def test_default_year_is_current(self):
        _, y = self._m("April")
        assert y == 2026


# ═════════════════════════════════════════════════════════════════════════════
# 15. Inference helpers (standalone)
# ═════════════════════════════════════════════════════════════════════════════

class TestInferenceHelpers:
    # Leave type
    def test_sick(self):       assert infer_leave_type("I have fever")          == "SICK"
    def test_hospital(self):   assert infer_leave_type("going to hospital")     == "SICK"
    def test_emergency(self):  assert infer_leave_type("family emergency today") == "EMERGENCY"
    def test_wedding(self):    assert infer_leave_type("sister's wedding")       == "EMERGENCY"
    def test_casual_default(self): assert infer_leave_type("personal work")     == "CASUAL"
    def test_hindi_sick(self): assert infer_leave_type("बुखार है")              == "SICK"
    def test_hindi_emergency(self): assert infer_leave_type("आपातकाल")          == "EMERGENCY"

    # Complaint category
    def test_payroll(self):    assert infer_complaint_category("salary not paid") == "PAYROLL"
    def test_harassment(self): assert infer_complaint_category("manager harasses")== "HARASSMENT"
    def test_safety(self):     assert infer_complaint_category("safety equipment missing") == "SAFETY"
    def test_discrimination(self): assert infer_complaint_category("racial bias") == "DISCRIMINATION"
    def test_facilities(self): assert infer_complaint_category("toilet is broken") == "FACILITIES"
    def test_workplace(self):  assert infer_complaint_category("forced overtime") == "WORKPLACE"
    def test_general(self):    assert infer_complaint_category("general concern")  == "GENERAL"
    def test_hindi_payroll(self):  assert infer_complaint_category("वेतन नहीं") == "PAYROLL"

    # Complaint severity
    def test_critical(self):   assert infer_complaint_severity("sexual assault reported")  == "CRITICAL"
    def test_high(self):       assert infer_complaint_severity("manager harasses staff")    == "HIGH"
    def test_medium(self):     assert infer_complaint_severity("salary was not paid")       == "MEDIUM"
    def test_low_default(self):assert infer_complaint_severity("minor concern about wifi")  == "LOW"


# ═════════════════════════════════════════════════════════════════════════════
# 16. Confidence scoring
# ═════════════════════════════════════════════════════════════════════════════

class TestConfidenceScoring:
    def test_exact_canonical_is_1(self):
        assert parse_command("LEAVE 2026-06-20 sick").confidence == 1.0

    def test_alias_is_less_than_1(self):
        assert parse_command("salary April").confidence < 1.0

    def test_fuzzy_is_lowest(self):
        alias_conf = parse_command("salary April").confidence
        fuzzy_conf = parse_command("leav 2026-06-20 sick").confidence
        assert fuzzy_conf <= alias_conf

    def test_unknown_is_zero(self):
        assert parse_command("XYZABC").confidence == 0.0

    def test_hindi_canonical_high_confidence(self):
        r = parse_command("छुट्टी 2026-06-20 बीमार")
        assert r.confidence >= 0.8
