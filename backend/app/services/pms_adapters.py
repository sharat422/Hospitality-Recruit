"""Vendor-neutral hotel PMS occupancy ingestion.

Indian hospitality groups run a Property Management System (IDS Next, eZee,
Hotelogix) as the system of record for rooms and occupancy. Staffing demand is
driven by that occupancy, so recruiting and rostering need it as a feed.

Vendors are integrated by registering an adapter. Domain code never depends on
a vendor SDK or payload shape -- it only ever sees ``OccupancyDay``.

Honesty note: the vendor field maps in ``PROVIDERS`` are *unverified defaults*.
They reflect the shapes these products expose in published REST docs, but no
field map here has been tested against a live tenant. Each is overridable per
connection via ``field_map`` so an implementer can correct it without a code
change. ``MOCK`` runs fully offline and needs no credentials.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx


@dataclass(frozen=True)
class OccupancyDay:
    """One business date of canonical occupancy for a single property."""

    business_date: date
    rooms_available: int
    rooms_sold: int
    arrivals: int = 0
    departures: int = 0

    def __post_init__(self) -> None:
        if self.rooms_available < 0 or self.rooms_sold < 0:
            raise ValueError("Room counts cannot be negative")
        if self.rooms_sold > self.rooms_available:
            raise ValueError(
                f"rooms_sold ({self.rooms_sold}) exceeds rooms_available "
                f"({self.rooms_available}) on {self.business_date}"
            )

    @property
    def occupancy_pct(self) -> float:
        if self.rooms_available == 0:
            return 0.0
        return round(self.rooms_sold / self.rooms_available * 100, 2)

    def as_row(self) -> dict[str, Any]:
        return {
            "business_date": self.business_date.isoformat(),
            "rooms_available": self.rooms_available,
            "rooms_sold": self.rooms_sold,
            "arrivals": self.arrivals,
            "departures": self.departures,
            "occupancy_pct": self.occupancy_pct,
        }


class PMSAdapter(ABC):
    @abstractmethod
    def fetch_occupancy(
        self, config: dict[str, Any], date_from: date, date_to: date
    ) -> list[OccupancyDay]:
        """Return canonical occupancy for [date_from, date_to] inclusive."""


def _coerce_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(float(value))


class MockPMSAdapter(PMSAdapter):
    """Deterministic offline occupancy -- sandbox mode, no credentials needed.

    Output is a pure function of (property_ref, date), so repeated syncs agree
    and tests stay stable. The shape mimics an Indian city hotel: a weekday
    business baseline with a weekend uplift.
    """

    def fetch_occupancy(
        self, config: dict[str, Any], date_from: date, date_to: date
    ) -> list[OccupancyDay]:
        rooms = _coerce_int(config.get("rooms_available")) or 120
        ref = str(config.get("property_ref") or "demo")
        days: list[OccupancyDay] = []
        current = date_from
        while current <= date_to:
            seed = hashlib.sha256(f"{ref}:{current.isoformat()}".encode()).digest()
            jitter = seed[0] % 15                        # 0-14 pct points of noise
            base = 78 if current.weekday() >= 4 else 62  # Fri/Sat/Sun uplift
            pct = min(97, base + jitter)
            sold = round(rooms * pct / 100)
            days.append(OccupancyDay(
                business_date=current,
                rooms_available=rooms,
                rooms_sold=sold,
                arrivals=round(sold * 0.42),
                departures=round(sold * 0.38),
            ))
            current += timedelta(days=1)
        return days


DEFAULT_FIELD_MAP = {
    "business_date": "date",
    "rooms_available": "rooms_available",
    "rooms_sold": "rooms_sold",
    "arrivals": "arrivals",
    "departures": "departures",
}


class GenericRestPMSAdapter(PMSAdapter):
    """Field-mapped REST reader.

    One adapter serves any PMS whose API returns a JSON list of per-date
    occupancy rows, which covers the documented REST surface of eZee,
    Hotelogix and IDS Next. The differences between them are configuration
    (``base_url``, ``path``, ``field_map``, auth header) rather than code.
    """

    def fetch_occupancy(
        self, config: dict[str, Any], date_from: date, date_to: date
    ) -> list[OccupancyDay]:
        base_url = config.get("base_url")
        if not base_url:
            raise ValueError("base_url is required for a REST PMS connection")

        field_map = {**DEFAULT_FIELD_MAP, **(config.get("field_map") or {})}
        headers = {"Accept": "application/json"}
        api_key = config.get("api_key")
        if api_key:
            header_name = config.get("auth_header") or "Authorization"
            scheme = config.get("auth_scheme", "Bearer ")
            headers[header_name] = f"{scheme}{api_key}" if scheme else api_key

        path = str(config.get("path") or "occupancy").lstrip("/")
        url = f"{base_url.rstrip('/')}/{path}"
        params = {
            config.get("param_from", "from_date"): date_from.isoformat(),
            config.get("param_to", "to_date"): date_to.isoformat(),
        }
        property_ref = config.get("property_ref")
        if property_ref:
            params[config.get("param_property", "property_id")] = property_ref

        response = httpx.get(url, params=params, headers=headers, timeout=20.0)
        response.raise_for_status()
        return self._normalize(response.json(), field_map, config)

    @staticmethod
    def _normalize(
        payload: Any, field_map: dict[str, str], config: dict[str, Any]
    ) -> list[OccupancyDay]:
        if isinstance(payload, dict):
            for key in (config.get("records_key"), "data", "records", "result", "occupancy"):
                if key and isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        if not isinstance(payload, list):
            raise ValueError("PMS response did not contain a list of occupancy rows")

        fallback_rooms = _coerce_int(config.get("rooms_available"))
        days: list[OccupancyDay] = []
        for item in payload:
            raw_date = item.get(field_map["business_date"])
            if not raw_date:
                continue
            available = _coerce_int(item.get(field_map["rooms_available"])) or fallback_rooms
            sold = _coerce_int(item.get(field_map["rooms_sold"]))
            days.append(OccupancyDay(
                business_date=date.fromisoformat(str(raw_date)[:10]),
                rooms_available=available,
                # A PMS may report sold > available mid-overbooking; clamp so
                # the canonical invariant holds instead of rejecting the sync.
                rooms_sold=min(sold, available) if available else sold,
                arrivals=_coerce_int(item.get(field_map["arrivals"])),
                departures=_coerce_int(item.get(field_map["departures"])),
            ))
        return sorted(days, key=lambda d: d.business_date)


# Vendor profiles. `field_map` entries are UNVERIFIED published-doc defaults;
# override per connection once tested against a live tenant.
PROVIDERS: dict[str, dict[str, Any]] = {
    "MOCK": {
        "display_name": "Sandbox (offline demo data)",
        "mode": "SANDBOX",
        "verified": True,
        "notes": "Deterministic synthetic occupancy. No credentials required.",
        "field_map": DEFAULT_FIELD_MAP,
    },
    "IDS_NEXT": {
        "display_name": "IDS Next (FortuneNEXT)",
        "mode": "REST",
        "verified": False,
        "notes": "Widely deployed across Indian hotel groups. Confirm the field map with your IDS implementation partner.",
        "field_map": {**DEFAULT_FIELD_MAP, "business_date": "BusinessDate",
                      "rooms_available": "TotalRooms", "rooms_sold": "OccupiedRooms",
                      "arrivals": "ExpectedArrivals", "departures": "ExpectedDepartures"},
    },
    "EZEE": {
        "display_name": "eZee Technosys (Absolute)",
        "mode": "REST",
        "verified": False,
        "notes": "Surat-based; common in Indian mid-market hotels.",
        "field_map": {**DEFAULT_FIELD_MAP, "business_date": "date",
                      "rooms_available": "total_rooms", "rooms_sold": "occupied_rooms"},
    },
    "HOTELOGIX": {
        "display_name": "Hotelogix",
        "mode": "REST",
        "verified": False,
        "notes": "Cloud PMS with a documented REST API.",
        "field_map": {**DEFAULT_FIELD_MAP, "business_date": "businessDate",
                      "rooms_available": "roomsAvailable", "rooms_sold": "roomsSold"},
    },
}

_ADAPTERS: dict[str, PMSAdapter] = {
    "MOCK": MockPMSAdapter(),
    "IDS_NEXT": GenericRestPMSAdapter(),
    "EZEE": GenericRestPMSAdapter(),
    "HOTELOGIX": GenericRestPMSAdapter(),
}


def register_pms_adapter(provider_code: str, adapter: PMSAdapter) -> None:
    _ADAPTERS[provider_code.upper()] = adapter


def get_pms_adapter(provider_code: str) -> PMSAdapter:
    adapter = _ADAPTERS.get((provider_code or "").upper())
    if not adapter:
        raise ValueError(f"Unsupported PMS provider: {provider_code}")
    return adapter


def provider_catalog() -> list[dict[str, Any]]:
    return [
        {"provider_code": code, "display_name": meta["display_name"],
         "mode": meta["mode"], "verified": meta["verified"], "notes": meta["notes"]}
        for code, meta in PROVIDERS.items()
    ]


def resolve_config(provider_code: str, connection: dict[str, Any]) -> dict[str, Any]:
    """Merge a stored connection over its provider profile defaults."""
    profile = PROVIDERS.get((provider_code or "").upper(), {})
    config = {**(connection.get("config") or {})}
    config["field_map"] = {**profile.get("field_map", DEFAULT_FIELD_MAP),
                           **(config.get("field_map") or {})}
    for key in ("base_url", "property_ref", "rooms_available"):
        if connection.get(key) is not None:
            config.setdefault(key, connection[key])
    return config
