"""Celery workers must compute 'today' in the hotel's calendar, not UTC.

Beat is configured `timezone="Asia/Kolkata"` and these jobs fire between
03:30 and 04:00 IST — which is 22:00-22:30 UTC the *previous* day. Anything
using the UTC date inside them was therefore wrong on every single run, not
merely some of the time.

These tests read the source rather than executing the jobs, because each one
opens a Supabase client at import time. That is enough to catch a regression:
the defect is which function is called, and it is visible in the text.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.workers import dpdp_retention, fssai_expiry, identity_document_expiry

IST = ZoneInfo("Asia/Kolkata")

WORKERS = [
    pytest.param(fssai_expiry, "03:30", id="fssai_expiry"),
    pytest.param(identity_document_expiry, "03:45", id="identity_document_expiry"),
    pytest.param(dpdp_retention, "04:00", id="dpdp_retention"),
]


class TestBeatWindowIsTheBrokenOne:
    """The premise: every one of these fire times lands in 00:00-05:30 IST."""

    @pytest.mark.parametrize("module,fire_time", WORKERS)
    def test_utc_date_would_be_yesterday(self, module, fire_time):
        hour, minute = (int(p) for p in fire_time.split(":"))
        fires = datetime(2026, 11, 3, hour, minute, tzinfo=IST)
        assert fires.astimezone(timezone.utc).date() != fires.date(), (
            f"{module.__name__} fires at {fire_time} IST; if UTC no longer "
            "disagrees there, this whole class of bug is gone")


class TestWorkersUseBusinessDates:
    @pytest.mark.parametrize("module,fire_time", WORKERS)
    def test_no_utc_date_for_business_dates(self, module, fire_time):
        source = inspect.getsource(module)
        assert "datetime.now(timezone.utc).date()" not in source
        assert "datetime.utcnow().date()" not in source

    @pytest.mark.parametrize("module,fire_time", WORKERS)
    def test_uses_the_shared_helper(self, module, fire_time):
        assert "business_today" in inspect.getsource(module)

    @pytest.mark.parametrize("module,fire_time", WORKERS)
    def test_helper_is_actually_imported(self, module, fire_time):
        assert hasattr(module, "business_today"), (
            f"{module.__name__} mentions business_today but does not import it")


class TestTimestampsStayUtc:
    """Only *dates* changed. `updated_at` and `sent_at` are timestamps and UTC
    remains correct for them; swapping those too would be the opposite bug."""

    @pytest.mark.parametrize("module,fire_time", WORKERS)
    def test_timestamps_still_written_in_utc(self, module, fire_time):
        source = inspect.getsource(module)
        assert "datetime.utcnow().isoformat()" in source, (
            "timestamp writes should still be UTC")

    @pytest.mark.parametrize("module,fire_time", WORKERS)
    def test_no_unused_timezone_import_left_behind(self, module, fire_time):
        source = inspect.getsource(module)
        if "timezone" in source:
            assert "timezone.utc" in source, "stale `timezone` import"
