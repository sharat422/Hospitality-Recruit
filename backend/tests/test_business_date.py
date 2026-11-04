"""Business dates are the hotel's calendar, not UTC.

The bug this guards against: between 00:00 and 05:30 IST the UTC date is still
yesterday, so anything using `datetime.now(timezone.utc).date()` as a business
date is wrong for 5h30m of every day.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app.core.business_date import (
    DEFAULT_TIMEZONE,
    business_date_range,
    business_now,
    business_today,
    days_until,
)

IST = ZoneInfo("Asia/Kolkata")


class TestDefaults:
    def test_default_timezone_is_india(self):
        assert DEFAULT_TIMEZONE == "Asia/Kolkata"

    def test_business_now_is_timezone_aware(self):
        assert business_now().tzinfo is not None

    def test_unknown_timezone_is_rejected(self):
        with pytest.raises(ValueError, match="Unknown timezone"):
            business_today("Mars/Olympus_Mons")


class TestTheBrokenWindow:
    """00:00-05:30 IST, where UTC is still on the previous day."""

    @pytest.mark.parametrize("ist_clock,expected_day", [
        ("00:01", 3),   # just after midnight IST, UTC is still the 2nd
        ("03:00", 3),
        ("05:29", 3),   # last minute of the window
        ("05:31", 3),   # after it, UTC agrees
        ("12:00", 3),
        ("23:59", 3),
    ])
    def test_business_today_is_the_ist_day_throughout(self, ist_clock, expected_day):
        hour, minute = (int(part) for part in ist_clock.split(":"))
        moment = datetime(2026, 11, 3, hour, minute, tzinfo=IST)
        with patch("app.core.business_date.datetime") as fake:
            fake.now.return_value = moment
            assert business_today().day == expected_day

    def test_utc_really_does_disagree_in_that_window(self):
        # Guards the premise: if this ever stops being true the bug is gone.
        moment = datetime(2026, 11, 3, 3, 0, tzinfo=IST)
        assert moment.date().day == 3
        assert moment.astimezone(timezone.utc).date().day == 2


class TestDaysUntil:
    def test_future_date_is_positive(self):
        assert days_until(business_today() + timedelta(days=10)) == 10

    def test_today_is_zero(self):
        assert days_until(business_today()) == 0

    def test_past_date_is_negative(self):
        assert days_until(business_today() - timedelta(days=1)) == -1

    def test_accepts_an_iso_string(self):
        assert days_until((business_today() + timedelta(days=5)).isoformat()) == 5

    def test_accepts_a_full_timestamp_string(self):
        stamp = f"{(business_today() + timedelta(days=5)).isoformat()}T18:30:00Z"
        assert days_until(stamp) == 5

    def test_missing_date_is_none_not_zero(self):
        # "no expiry" must not read as "expires today".
        assert days_until(None) is None
        assert days_until("") is None


class TestDateRange:
    def test_range_starts_today(self):
        start, _ = business_date_range(14)
        assert start == business_today()

    def test_range_spans_the_requested_days(self):
        start, end = business_date_range(14)
        assert (end - start).days == 14


class TestCertificateExpiryUsesIt:
    """The bug that prompted this module."""

    def test_certificate_expiring_today_is_not_yet_expired(self):
        from app.services.certification_service import certificate_state
        state = certificate_state(business_today().isoformat(), "VERIFIED")
        assert state["days_remaining"] == 0
        assert state["status"] == "RENEWAL_DUE"

    def test_certificate_expiring_yesterday_is_exactly_one_day_gone(self):
        from app.services.certification_service import certificate_state
        expiry = (business_today() - timedelta(days=1)).isoformat()
        assert certificate_state(expiry, "VERIFIED") == {
            "status": "EXPIRED", "days_remaining": -1,
        }

    def test_certificate_service_no_longer_uses_utc(self):
        import inspect
        from app.services import certification_service
        source = inspect.getsource(certification_service)
        assert "timezone.utc" not in source, "business dates must not come from UTC"
        assert "business_today" in source


class TestNoRegressionToUtc:
    def test_helper_does_not_return_the_utc_date_in_the_broken_window(self):
        moment = datetime(2026, 11, 3, 2, 0, tzinfo=IST)
        with patch("app.core.business_date.datetime") as fake:
            fake.now.return_value = moment
            assert business_today() != moment.astimezone(timezone.utc).date()
            assert business_today() == date(2026, 11, 3)
