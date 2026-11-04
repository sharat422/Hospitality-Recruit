"""Today's date in the hotel's timezone.

Timestamps are stored in UTC, which is correct. A *business date* is not a
timestamp: "has this certificate expired?", "what is today's roster?" and
"which month does this attendance belong to?" are all answered in the hotel's
local calendar, not UTC.

Using `datetime.now(timezone.utc).date()` for a business date is wrong for
5 hours 30 minutes of every single day in India: between 00:00 and 05:30 IST
the UTC date is still yesterday. A certificate expiring today reads as expired
tomorrow, a roster query returns the wrong day, and Celery — which this
project runs on `Asia/Kolkata` — fires a job whose own idea of "today"
disagrees with its schedule.

`attendance_service.attendance_date_for()` already does this correctly for a
given punch timestamp. This module is the same idea for "now".
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Kolkata"

_IST = ZoneInfo(DEFAULT_TIMEZONE)


def business_now(timezone_name: str = DEFAULT_TIMEZONE) -> datetime:
    """Current time in the hotel's timezone, timezone-aware."""
    try:
        zone = ZoneInfo(timezone_name)
    except Exception as exc:  # unknown or misconfigured property timezone
        raise ValueError(f"Unknown timezone: {timezone_name}") from exc
    return datetime.now(zone)


def business_today(timezone_name: str = DEFAULT_TIMEZONE) -> date:
    """Today's date in the hotel's timezone.

    Use this anywhere a date is compared against a stored DATE column:
    expiry dates, attendance dates, roster dates, payroll periods.
    """
    return business_now(timezone_name).date()


def days_until(target: date | str | None, timezone_name: str = DEFAULT_TIMEZONE) -> int | None:
    """Whole days from today until `target`; negative once it has passed.

    Returns None for a missing date so callers can distinguish "no expiry" from
    "expires today".
    """
    if target is None or target == "":
        return None
    due = target if isinstance(target, date) else date.fromisoformat(str(target)[:10])
    return (due - business_today(timezone_name)).days


def business_date_range(days: int, timezone_name: str = DEFAULT_TIMEZONE) -> tuple[date, date]:
    """(today, today + days) in the hotel's timezone, for horizon queries."""
    start = business_today(timezone_name)
    return start, start + timedelta(days=days)
