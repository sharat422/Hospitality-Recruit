"""Configurable attendance codes and their effect on pay and leave.

An Indian hotel marks each staff day with a code: P, WO, CL, SL, EL, CO, LWP,
A, HD, H or OD. What a code does to pay differs by hotel and by state and
changes over time, so codes are stored per hotel rather than compiled in.

The single bridge to payroll is ``lop_factor`` -- the share of a day's pay
lost. Payroll sums it across the month and needs to know nothing else:

    P, WO, H, CL, SL, EL, CO, OD -> 0.0   (fully paid)
    HD                           -> 0.5   (half day)
    A, LWP                       -> 1.0   (unpaid)

Every function here is pure. Persistence and access control live in the router.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

LEAVE_TYPES = ("CASUAL", "SICK", "EARNED", "COMP_OFF", "MATERNITY", "PATERNITY")


@dataclass(frozen=True)
class AttendanceCode:
    code: str
    label_en: str
    label_hi: str | None = None
    lop_factor: float = 0.0
    counts_as_worked: bool = False
    consumes_leave_type: str | None = None
    requires_approval: bool = False
    rules: dict[str, Any] = field(default_factory=dict)
    display_order: int = 100

    def __post_init__(self) -> None:
        if not 0.0 <= self.lop_factor <= 1.0:
            raise ValueError(f"{self.code}: lop_factor must be between 0 and 1")
        if self.consumes_leave_type and self.consumes_leave_type not in LEAVE_TYPES:
            raise ValueError(f"{self.code}: unknown leave type {self.consumes_leave_type}")

    @property
    def is_paid(self) -> bool:
        return self.lop_factor < 1.0


# Sensible Indian hotel defaults. A hotel that stores its own codes overrides
# these entirely; nothing here is a statutory value that must not be edited.
DEFAULT_CODES: tuple[AttendanceCode, ...] = (
    AttendanceCode("P",   "Present",            "उपस्थित",            0.0, True,  None,       False, {}, 10),
    AttendanceCode("WO",  "Weekly Off",         "साप्ताहिक अवकाश",     0.0, False, None,       False, {}, 20),
    AttendanceCode("H",   "Holiday",            "सार्वजनिक अवकाश",     0.0, False, None,       False, {}, 30),
    AttendanceCode("CL",  "Casual Leave",       "आकस्मिक अवकाश",       0.0, False, "CASUAL",   True,  {}, 40),
    AttendanceCode("SL",  "Sick Leave",         "बीमारी अवकाश",        0.0, False, "SICK",     True,  {}, 50),
    AttendanceCode("EL",  "Earned Leave",       "अर्जित अवकाश",        0.0, False, "EARNED",   True,  {}, 60),
    AttendanceCode("CO",  "Comp Off",           "क्षतिपूर्ति अवकाश",    0.0, False, "COMP_OFF", True,
                   {"earn_basis": "PER_OT_DAY", "expiry_days": 30}, 70),
    AttendanceCode("HD",  "Half Day",           "आधा दिन",             0.5, True,  None,       False, {}, 80),
    AttendanceCode("OD",  "On Duty (elsewhere)", "ड्यूटी पर (बाहर)",   0.0, True,  None,       True,  {}, 90),
    AttendanceCode("LWP", "Leave Without Pay",  "अवैतनिक अवकाश",       1.0, False, None,       True,  {}, 100),
    AttendanceCode("A",   "Absent",             "अनुपस्थित",           1.0, False, None,       False, {}, 110),
)

# Codes that earn a comp-off when actually worked.
COMP_OFF_EARNING_CODES = ("WO", "H")


def code_from_row(row: dict[str, Any]) -> AttendanceCode:
    """Build a code from a stored ``attendance_codes`` row."""
    return AttendanceCode(
        code=row["code"],
        label_en=row.get("label_en") or row["code"],
        label_hi=row.get("label_hi"),
        lop_factor=float(row.get("lop_factor") or 0),
        counts_as_worked=bool(row.get("counts_as_worked")),
        consumes_leave_type=row.get("consumes_leave_type"),
        requires_approval=bool(row.get("requires_approval")),
        rules=row.get("rules") or {},
        display_order=int(row.get("display_order") or 100),
    )


def code_map(codes: Iterable[AttendanceCode] | None = None) -> dict[str, AttendanceCode]:
    return {c.code: c for c in (codes or DEFAULT_CODES)}


# Statuses written by the attendance engine before this feature existed.
# They are mapped so historical rows still cost the right amount of pay.
LEGACY_STATUS_ALIASES = {
    "PRESENT": "P",
    "ABSENT": "A",
    "WEEKLY_OFF": "WO",
    "LEAVE": "CL",
}


def resolve_code(status: str | None, codes: dict[str, AttendanceCode]) -> AttendanceCode | None:
    """Map a stored status to a configured code, tolerating legacy values."""
    if not status:
        return None
    if status in codes:
        return codes[status]
    alias = LEGACY_STATUS_ALIASES.get(status)
    return codes.get(alias) if alias else None


def lop_days(records: Iterable[dict[str, Any]],
             codes: Iterable[AttendanceCode] | None = None) -> float:
    """Loss-of-pay days for a month: the sum of each day's lop_factor.

    An unrecognised status is treated as fully unpaid rather than free, so a
    bad import shows up as a pay query instead of silently paying for days
    nobody can account for. MISSING_PUNCH and INVALID land here deliberately.
    """
    resolved = code_map(codes)
    total = 0.0
    for record in records:
        code = resolve_code(record.get("status"), resolved)
        total += code.lop_factor if code else 1.0
    return round(total, 2)


def worked_days(records: Iterable[dict[str, Any]],
                codes: Iterable[AttendanceCode] | None = None) -> float:
    """Days that count as worked, a half day counting as half."""
    resolved = code_map(codes)
    total = 0.0
    for record in records:
        code = resolve_code(record.get("status"), resolved)
        if code and code.counts_as_worked:
            total += 1.0 - code.lop_factor
    return round(total, 2)


def leave_consumption(records: Iterable[dict[str, Any]],
                      codes: Iterable[AttendanceCode] | None = None) -> dict[str, float]:
    """Days drawn from each leave balance over the period."""
    resolved = code_map(codes)
    consumed: dict[str, float] = {}
    for record in records:
        code = resolve_code(record.get("status"), resolved)
        if code and code.consumes_leave_type:
            consumed[code.consumes_leave_type] = round(
                consumed.get(code.consumes_leave_type, 0.0) + (1.0 - code.lop_factor), 2)
    return consumed


def comp_off_earned(records: Iterable[dict[str, Any]],
                    codes: Iterable[AttendanceCode] | None = None,
                    earned_on: date | None = None) -> list[dict[str, Any]]:
    """Comp-off entitlements earned by working a weekly off or a holiday.

    One worked rest day earns one comp-off day, which lapses after the window
    configured on the CO code (default 30 days). Returns ledger rows ready to
    insert; the caller adds org, property and employee.
    """
    resolved = code_map(codes)
    co = resolved.get("CO")
    expiry_days = int((co.rules if co else {}).get("expiry_days", 30))
    basis = (co.rules if co else {}).get("earn_basis", "PER_OT_DAY")
    earned_on = earned_on or date.today()

    entitlements = []
    for record in records:
        # The day was rostered as rest, but the person actually worked it.
        rostered = record.get("rostered_status") or record.get("scheduled_status")
        if rostered not in COMP_OFF_EARNING_CODES:
            continue
        code = resolve_code(record.get("status"), resolved)
        if not code or not code.counts_as_worked:
            continue
        if basis == "PER_OT_DAY" and float(record.get("worked_minutes") or 0) <= 0:
            continue
        for_date = record.get("attendance_date")
        entitlements.append({
            "earned_for_date": str(for_date)[:10] if for_date else None,
            "earned_on": earned_on.isoformat(),
            "expires_on": (earned_on + timedelta(days=expiry_days)).isoformat(),
            "status": "AVAILABLE",
            "notes": f"Worked rostered {rostered}",
        })
    return entitlements


def available_comp_off(ledger: Iterable[dict[str, Any]],
                       as_of: date | None = None) -> list[dict[str, Any]]:
    """Unconsumed comp-off that has not yet lapsed, soonest to expire first."""
    as_of = as_of or date.today()
    live = [row for row in ledger
            if row.get("status") == "AVAILABLE"
            and row.get("expires_on")
            and date.fromisoformat(str(row["expires_on"])[:10]) >= as_of]
    return sorted(live, key=lambda r: str(r["expires_on"]))


def expired_comp_off(ledger: Iterable[dict[str, Any]],
                     as_of: date | None = None) -> list[dict[str, Any]]:
    """Comp-off still marked available whose expiry has passed."""
    as_of = as_of or date.today()
    return [row for row in ledger
            if row.get("status") == "AVAILABLE"
            and row.get("expires_on")
            and date.fromisoformat(str(row["expires_on"])[:10]) < as_of]


def attendance_summary(records: Iterable[dict[str, Any]],
                       codes: Iterable[AttendanceCode] | None = None) -> dict[str, Any]:
    """Month-end figures for one employee: the payroll input."""
    records = list(records)
    resolved = code_map(codes)
    by_code: dict[str, int] = {}
    unknown = 0
    for record in records:
        code = resolve_code(record.get("status"), resolved)
        if code:
            by_code[code.code] = by_code.get(code.code, 0) + 1
        else:
            unknown += 1
    return {
        "total_days": len(records),
        "lop_days": lop_days(records, codes),
        "worked_days": worked_days(records, codes),
        "leave_consumed": leave_consumption(records, codes),
        "days_by_code": by_code,
        "unrecognised_days": unknown,
    }
