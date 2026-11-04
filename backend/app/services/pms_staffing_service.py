"""Occupancy-driven staffing demand.

Turns a PMS occupancy forecast into required headcount per department per day,
compares it to the published roster, and raises a hiring signal when a
department is short for a sustained run of days.

This is the bridge between hotel operations and recruiting: a hotel does not
hire because a seat is empty, it hires because next month's occupancy cannot
be serviced by the people currently on the roster.

Every function here is pure -- no database, no network -- so the arithmetic is
testable on its own. Persistence and access control live in the router.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from app.services.pms_adapters import OccupancyDay

# Demand drivers. A department's headcount scales with exactly one of these.
DRIVERS = ("OCCUPIED_ROOMS", "ARRIVALS", "DEPARTURES", "COVERS", "FIXED")


@dataclass(frozen=True)
class StaffingRatio:
    """How one department's headcount scales with occupancy.

    ``units_per_staff`` is how many driver units one person covers in a day --
    e.g. housekeeping at 16 means one room attendant per 16 occupied rooms.
    ``min_staff`` is the floor that must be rostered even at zero occupancy
    (a front desk is staffed whether or not anyone checks in).
    """

    department_code: str
    department_name: str
    driver: str
    units_per_staff: float
    min_staff: int = 0
    covers_per_room: float = 1.6  # guests served per occupied room, F&B only

    def __post_init__(self) -> None:
        if self.driver not in DRIVERS:
            raise ValueError(f"Unknown staffing driver: {self.driver}")
        if self.driver != "FIXED" and self.units_per_staff <= 0:
            raise ValueError(f"{self.department_code}: units_per_staff must be > 0")
        if self.min_staff < 0:
            raise ValueError(f"{self.department_code}: min_staff cannot be negative")

    def driver_value(self, day: OccupancyDay) -> float:
        if self.driver == "OCCUPIED_ROOMS":
            return day.rooms_sold
        if self.driver == "ARRIVALS":
            return day.arrivals
        if self.driver == "DEPARTURES":
            return day.departures
        if self.driver == "COVERS":
            return day.rooms_sold * self.covers_per_room
        return 0.0  # FIXED

    def required_headcount(self, day: OccupancyDay) -> int:
        """Headcount needed to service this day. Always at least ``min_staff``."""
        if self.driver == "FIXED":
            return self.min_staff
        scaled = math.ceil(self.driver_value(day) / self.units_per_staff)
        return max(self.min_staff, scaled)


# Indian full-service hotel norms. These are starting points, not gospel --
# every property tunes them, so they are stored per property and editable.
# ponytail: flat per-day ratios, no shift-level split. Add shifts_per_day if a
# property needs 24h departments costed per shift rather than per day.
DEFAULT_RATIOS: tuple[StaffingRatio, ...] = (
    StaffingRatio("HOUSEKEEPING", "Housekeeping", "OCCUPIED_ROOMS", 16, min_staff=2),
    StaffingRatio("FRONT_OFFICE", "Front Office", "ARRIVALS", 40, min_staff=3),
    StaffingRatio("FB_SERVICE", "F&B Service", "COVERS", 20, min_staff=2),
    StaffingRatio("KITCHEN", "Kitchen", "COVERS", 35, min_staff=2),
    StaffingRatio("MAINTENANCE", "Maintenance", "OCCUPIED_ROOMS", 90, min_staff=1),
    StaffingRatio("SECURITY", "Security", "FIXED", 1, min_staff=3),
)


def ratio_from_row(row: dict[str, Any]) -> StaffingRatio:
    """Build a ratio from a stored ``department_staffing_ratios`` row."""
    return StaffingRatio(
        department_code=row["department_code"],
        department_name=row.get("department_name") or row["department_code"],
        driver=row.get("driver") or "OCCUPIED_ROOMS",
        units_per_staff=float(row.get("units_per_staff") or 1),
        min_staff=int(row.get("min_staff") or 0),
        covers_per_room=float(row.get("covers_per_room") or 1.6),
    )


def staffing_plan(
    days: Iterable[OccupancyDay],
    ratios: Iterable[StaffingRatio],
    scheduled: dict[tuple[str, date], int] | None = None,
) -> list[dict[str, Any]]:
    """Per-day, per-department required vs scheduled headcount.

    ``scheduled`` maps (department_code, business_date) to the number of people
    already rostered. A missing entry counts as zero rostered, which surfaces
    an unstaffed department rather than hiding it.
    """
    scheduled = scheduled or {}
    plan: list[dict[str, Any]] = []
    for day in days:
        for ratio in ratios:
            required = ratio.required_headcount(day)
            rostered = int(scheduled.get((ratio.department_code, day.business_date), 0))
            gap = required - rostered
            plan.append({
                "business_date": day.business_date.isoformat(),
                "department_code": ratio.department_code,
                "department_name": ratio.department_name,
                "driver": ratio.driver,
                "driver_value": round(ratio.driver_value(day), 1),
                "occupancy_pct": day.occupancy_pct,
                "rooms_sold": day.rooms_sold,
                "required_headcount": required,
                "scheduled_headcount": rostered,
                "gap": gap,
                "status": "SHORT" if gap > 0 else ("OVER" if gap < 0 else "BALANCED"),
            })
    return plan


def hiring_signal(
    plan: list[dict[str, Any]],
    min_short_days: int = 3,
) -> list[dict[str, Any]]:
    """Departments short for at least ``min_short_days`` days in the horizon.

    A one-off short day is a rostering problem -- move someone's shift. A
    department short across several days is a headcount problem, and that is
    what should become a requisition. Recommended hires uses the *median*
    shortfall, not the peak, so a single festival spike does not drive a
    permanent hire.
    """
    by_dept: dict[str, dict[str, Any]] = {}
    for entry in plan:
        if entry["gap"] <= 0:
            continue
        bucket = by_dept.setdefault(entry["department_code"], {
            "department_code": entry["department_code"],
            "department_name": entry["department_name"],
            "short_days": 0,
            "peak_gap": 0,
            "_gaps": [],
            "first_short_date": entry["business_date"],
        })
        bucket["short_days"] += 1
        bucket["peak_gap"] = max(bucket["peak_gap"], entry["gap"])
        bucket["_gaps"].append(entry["gap"])
        bucket["first_short_date"] = min(bucket["first_short_date"], entry["business_date"])

    signals = []
    for bucket in by_dept.values():
        if bucket["short_days"] < min_short_days:
            continue
        gaps = sorted(bucket.pop("_gaps"))
        bucket["recommended_hires"] = gaps[len(gaps) // 2]
        bucket["urgency"] = "HIGH" if bucket["short_days"] >= 7 else "MEDIUM"
        signals.append(bucket)
    return sorted(signals, key=lambda s: (-s["recommended_hires"], s["department_code"]))


def plan_summary(plan: list[dict[str, Any]]) -> dict[str, Any]:
    """Headline numbers for the dashboard."""
    if not plan:
        return {"days": 0, "total_required": 0, "total_scheduled": 0,
                "total_gap": 0, "short_entries": 0, "avg_occupancy_pct": 0.0}
    occupancies = {e["business_date"]: e["occupancy_pct"] for e in plan}
    return {
        "days": len(occupancies),
        "total_required": sum(e["required_headcount"] for e in plan),
        "total_scheduled": sum(e["scheduled_headcount"] for e in plan),
        "total_gap": sum(e["gap"] for e in plan if e["gap"] > 0),
        "short_entries": sum(1 for e in plan if e["gap"] > 0),
        "avg_occupancy_pct": round(sum(occupancies.values()) / len(occupancies), 2),
    }
