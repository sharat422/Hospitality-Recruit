"""Vendor-neutral biometric event normalization.

Vendors are integrated by registering an adapter. Attendance domain code never
depends on a vendor SDK or payload shape.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class BiometricPunchEvent:
    external_event_id: str
    employee_external_id: str
    punch_type: str
    punched_at: datetime
    device_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class BiometricProviderAdapter(ABC):
    @abstractmethod
    def verify_signature(self, raw_body: bytes, headers: dict[str, str], secret: str | None) -> bool:
        """Return True only when the provider webhook is authentic."""

    @abstractmethod
    def parse_events(self, payload: dict[str, Any]) -> list[BiometricPunchEvent]:
        """Normalize a provider payload to canonical punch events."""


class GenericJsonBiometricAdapter(BiometricProviderAdapter):
    """Documented canonical adapter for middleware and test integrations.

    Production vendors should subclass ``BiometricProviderAdapter`` and verify
    their own signature. This adapter requires a caller-supplied shared token.
    """

    def verify_signature(self, raw_body: bytes, headers: dict[str, str], secret: str | None) -> bool:
        return bool(secret) and headers.get("x-attendance-token") == secret

    def parse_events(self, payload: dict[str, Any]) -> list[BiometricPunchEvent]:
        events = payload.get("events") or []
        normalized = []
        for item in events:
            punch_type = str(item.get("punch_type", "")).upper()
            if punch_type not in {"IN", "OUT"}:
                raise ValueError("Biometric punch_type must be IN or OUT")
            normalized.append(BiometricPunchEvent(
                external_event_id=str(item["event_id"]),
                employee_external_id=str(item["employee_id"]),
                punch_type=punch_type,
                punched_at=datetime.fromisoformat(str(item["punched_at"]).replace("Z", "+00:00")),
                device_id=item.get("device_id"), latitude=item.get("latitude"), longitude=item.get("longitude"),
            ))
        return normalized


_ADAPTERS: dict[str, BiometricProviderAdapter] = {"GENERIC_JSON": GenericJsonBiometricAdapter()}


def register_biometric_adapter(provider_code: str, adapter: BiometricProviderAdapter) -> None:
    _ADAPTERS[provider_code.upper()] = adapter


def get_biometric_adapter(provider_code: str) -> BiometricProviderAdapter:
    adapter = _ADAPTERS.get(provider_code.upper())
    if not adapter:
        raise ValueError(f"Unsupported biometric provider: {provider_code}")
    return adapter

