"""Deterministic attendance calculation and persistence helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException


def _rows(result: Any) -> list[dict]:
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


def parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def attendance_date_for(value: str | datetime, timezone_name: str = "Asia/Kolkata") -> date:
    parsed = parse_datetime(value)
    if not parsed:
        raise ValueError("Punch time is required")
    try:
        zone = ZoneInfo(timezone_name)
    except Exception as exc:
        raise ValueError(f"Unknown attendance timezone: {timezone_name}") from exc
    return parsed.astimezone(zone).date()


def distance_metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius * asin(sqrt(a))


def evaluate_geofence(latitude: float | None, longitude: float | None, policy: dict) -> tuple[str, float | None]:
    if not policy.get("require_geofence"):
        return "NOT_REQUIRED", None
    if latitude is None or longitude is None:
        return "UNAVAILABLE", None
    if policy.get("latitude") is None or policy.get("longitude") is None:
        return "UNAVAILABLE", None
    distance = distance_metres(float(latitude), float(longitude), float(policy["latitude"]), float(policy["longitude"]))
    return ("INSIDE" if distance <= int(policy.get("geofence_radius_m", 150)) else "OUTSIDE"), round(distance, 2)


def calculate_daily_attendance(
    punches: list[dict], *, scheduled_start: str | datetime | None = None,
    scheduled_end: str | datetime | None = None, policy: dict | None = None,
    on_leave: bool = False, weekly_off: bool = False, holiday: bool = False,
) -> dict:
    """Calculate one day without making payroll decisions.

    The output is always PENDING. A manager must explicitly validate it before
    any downstream payroll process may consume it.
    """
    policy = policy or {}
    start, end = parse_datetime(scheduled_start), parse_datetime(scheduled_end)
    ordered = sorted(punches, key=lambda p: parse_datetime(p["punched_at"]) or datetime.min.replace(tzinfo=timezone.utc))
    if not ordered:
        # A public holiday outranks the rest: nobody is absent on one and no
        # leave balance is consumed. Remaining precedence is unchanged.
        status = "H" if holiday else ("LEAVE" if on_leave else ("WEEKLY_OFF" if weekly_off else "ABSENT"))
        return {"first_in_at": None, "last_out_at": None, "worked_minutes": 0, "late_minutes": 0,
                "early_departure_minutes": 0, "overtime_minutes": 0, "status": status,
                "anomaly_codes": [], "validation_status": "PENDING"}

    anomalies: list[str] = []
    for punch in ordered:
        if punch.get("geofence_status") in {"OUTSIDE", "UNAVAILABLE"}:
            anomalies.append("GEOFENCE_" + punch["geofence_status"])
    for previous, current in zip(ordered, ordered[1:]):
        if previous["punch_type"] == current["punch_type"]:
            anomalies.append("DOUBLE_" + current["punch_type"])
    if ordered[0]["punch_type"] != "IN":
        anomalies.append("MISSING_IN")
    if ordered[-1]["punch_type"] != "OUT":
        anomalies.append("MISSING_OUT")

    pairs: list[tuple[datetime, datetime]] = []
    pending_in: datetime | None = None
    for punch in ordered:
        when = parse_datetime(punch["punched_at"])
        if punch["punch_type"] == "IN":
            if pending_in is None:
                pending_in = when
        elif pending_in is not None and when and when >= pending_in:
            pairs.append((pending_in, when))
            pending_in = None
    worked = sum(max(0, int((out_at - in_at).total_seconds() // 60)) for in_at, out_at in pairs)
    first_in = next((parse_datetime(p["punched_at"]) for p in ordered if p["punch_type"] == "IN"), None)
    last_out = next((parse_datetime(p["punched_at"]) for p in reversed(ordered) if p["punch_type"] == "OUT"), None)
    late = max(0, int((first_in - start).total_seconds() // 60) - int(policy.get("late_grace_minutes", 10))) if first_in and start else 0
    early = max(0, int((end - last_out).total_seconds() // 60) - int(policy.get("early_departure_grace_minutes", 5))) if last_out and end else 0
    overtime = max(0, worked - int(policy.get("overtime_after_minutes", 480)))
    anomaly_codes = sorted(set(anomalies))
    incomplete = any(code in anomaly_codes for code in ("MISSING_IN", "MISSING_OUT", "DOUBLE_IN", "DOUBLE_OUT"))
    return {
        "first_in_at": first_in.isoformat() if first_in else None,
        "last_out_at": last_out.isoformat() if last_out else None,
        "worked_minutes": worked, "late_minutes": late, "early_departure_minutes": early,
        "overtime_minutes": overtime, "status": "MISSING_PUNCH" if incomplete else "PRESENT",
        "anomaly_codes": anomaly_codes, "validation_status": "PENDING",
    }


def record_punch(supabase, *, org_id: str, employee_id: str, property_id: str, punch_type: str,
                 source: str, punched_at: datetime, latitude: float | None, longitude: float | None,
                 gps_accuracy_m: float | None, actor_id: str, provider_code: str | None = None,
                 provider_event_id: str | None = None, device_id: str | None = None) -> dict:
    policies = _rows(supabase.table("attendance_policies").select("*").eq("org_id", org_id)
                     .eq("property_id", property_id).eq("is_active", True).limit(1).execute())
    policy = policies[0] if policies else {}
    geofence_status, distance = evaluate_geofence(latitude, longitude, policy)
    if policy.get("require_geofence") and geofence_status != "INSIDE" and source in {"WEB", "MOBILE"}:
        raise HTTPException(422, f"Punch rejected: geofence status {geofence_status}")
    recent = _rows(supabase.table("attendance_punches").select("id,punch_type,punched_at")
                   .eq("org_id", org_id).eq("employee_id", employee_id).order("punched_at", desc=True).limit(1).execute())
    if recent and recent[0].get("punch_type") == punch_type:
        previous_at = parse_datetime(recent[0].get("punched_at"))
        timezone_name = str(policy.get("timezone") or "Asia/Kolkata")
        if previous_at and attendance_date_for(previous_at, timezone_name) == attendance_date_for(punched_at, timezone_name):
            raise HTTPException(409, f"Double {punch_type.lower()} is not allowed")
    row = {
        "org_id": org_id, "employee_id": employee_id, "property_id": property_id,
        "punch_type": punch_type, "punched_at": punched_at.isoformat(), "source": source,
        "latitude": latitude, "longitude": longitude, "gps_accuracy_m": gps_accuracy_m,
        "distance_from_property_m": distance, "geofence_status": geofence_status,
        "device_id": device_id, "provider_code": provider_code, "provider_event_id": provider_event_id,
        "created_by": actor_id,
    }
    inserted = _rows(supabase.table("attendance_punches").insert(row).execute())
    if not inserted:
        raise HTTPException(500, "Punch could not be recorded")
    return inserted[0]
