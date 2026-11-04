"""Language resolution, and the SMS segment arithmetic that drives cost."""

from __future__ import annotations

import pytest

from app.services.staff_ops_language import (
    LANGUAGE_CODES,
    SUPPORTED_LANGUAGES,
    default_language_for_state,
    language_label,
    pick_for_user,
    requires_unicode_sms,
    resolve_language,
    sms_segments,
)


class TestSupportedLanguages:
    def test_exactly_the_five_agreed_languages(self):
        assert LANGUAGE_CODES == ("en", "hi", "te", "ta", "kn")

    def test_every_language_has_a_native_label(self):
        assert all(entry["native_label"] for entry in SUPPORTED_LANGUAGES)

    def test_native_labels_are_in_their_own_script(self):
        labels = {e["code"]: e["native_label"] for e in SUPPORTED_LANGUAGES}
        assert labels["hi"] == "हिंदी"
        assert labels["te"] == "తెలుగు"
        assert labels["ta"] == "தமிழ்"
        assert labels["kn"] == "ಕನ್ನಡ"


class TestStateDefaults:
    @pytest.mark.parametrize("state,expected", [
        ("Telangana", "te"), ("Andhra Pradesh", "te"),
        ("Tamil Nadu", "ta"), ("Puducherry", "ta"),
        ("Karnataka", "kn"),
        ("Uttar Pradesh", "hi"), ("Bihar", "hi"), ("Delhi", "hi"),
    ])
    def test_known_states(self, state, expected):
        assert default_language_for_state(state) == expected

    @pytest.mark.parametrize("code,expected", [
        ("TS", "te"), ("AP", "te"), ("TN", "ta"), ("KA", "kn"), ("UP", "hi"),
    ])
    def test_two_letter_codes(self, code, expected):
        assert default_language_for_state(code) == expected

    def test_case_and_padding_tolerated(self):
        assert default_language_for_state("  tamil nadu  ") == "ta"
        assert default_language_for_state("KARNATAKA") == "kn"

    def test_unknown_state_falls_back_to_english_not_a_guess(self):
        assert default_language_for_state("Maharashtra") == "en"
        assert default_language_for_state("Goa") == "en"
        assert default_language_for_state("Kerala") == "en"

    def test_missing_state_is_english(self):
        assert default_language_for_state(None) == "en"
        assert default_language_for_state("") == "en"


class TestResolution:
    def test_user_preference_beats_hotel_state(self):
        # A Tamil speaker in a Bengaluru hotel gets Tamil, not Kannada.
        assert resolve_language("ta", "Karnataka") == "ta"

    def test_hotel_state_used_when_no_preference(self):
        assert resolve_language(None, "Karnataka") == "kn"

    def test_unsupported_preference_is_ignored(self):
        # Someone's stale profile asking for Spanish gets the hotel default.
        assert resolve_language("es", "Tamil Nadu") == "ta"

    def test_nothing_known_is_english(self):
        assert resolve_language(None, None) == "en"

    def test_pick_for_user_reads_both_rows(self):
        assert pick_for_user({"preferred_language": "hi"}, {"state": "Karnataka"}) == "hi"
        assert pick_for_user({"preferred_language": None}, {"state": "Karnataka"}) == "kn"
        assert pick_for_user({}, None) == "en"


class TestSmsSegments:
    def test_english_uses_gsm7_length(self):
        assert sms_segments("a" * 160, "en") == 1
        assert sms_segments("a" * 161, "en") == 2

    def test_indic_scripts_need_unicode(self):
        for language in ("hi", "te", "ta", "kn"):
            assert requires_unicode_sms(language) is True
        assert requires_unicode_sms("en") is False

    def test_unicode_single_segment_is_70_characters(self):
        assert sms_segments("क" * 70, "hi") == 1
        assert sms_segments("क" * 71, "hi") == 2

    def test_long_unicode_message_uses_67_per_part(self):
        # 134 = exactly two concatenated UCS-2 parts.
        assert sms_segments("த" * 134, "ta") == 2
        assert sms_segments("த" * 135, "ta") == 3

    def test_same_text_costs_more_in_an_indic_script(self):
        # 100 characters: one GSM-7 part, but two UCS-2 parts.
        text = "x" * 100
        assert sms_segments(text, "en") == 1
        assert sms_segments("அ" * 100, "ta") == 2

    def test_empty_message_costs_nothing(self):
        assert sms_segments("", "hi") == 0


class TestLabels:
    def test_known_code_returns_native_label(self):
        assert language_label("te") == "తెలుగు"

    def test_unknown_code_returns_itself(self):
        assert language_label("xx") == "xx"
