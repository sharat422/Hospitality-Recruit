"""Deterministic global-search ranking and authorization helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from app.services.rbac_service import AccessContext

SEARCH_CATEGORIES = (
    "candidates", "employees", "jobs", "applications", "referrals",
    "documents", "properties", "departments", "complaints",
)

CATEGORY_PERMISSIONS = {
    "candidates": "candidates.read", "employees": "employees.read",
    "jobs": "jobs.read", "applications": "applications.read",
    "documents": "documents.read", "properties": "properties.read",
    "departments": "properties.read", "complaints": "complaints.read",
}


def normalize_query(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def allowed_categories(context: AccessContext, requested: Iterable[str] | None = None) -> list[str]:
    requested_set = set(requested or SEARCH_CATEGORIES)
    allowed: list[str] = []
    for category in SEARCH_CATEGORIES:
        if category not in requested_set:
            continue
        if category == "referrals":
            if context.role == "EMPLOYEE" or "financial.read" in context.permissions or "reports.read" in context.permissions:
                allowed.append(category)
            continue
        permission = CATEGORY_PERMISSIONS[category]
        if permission in context.permissions:
            allowed.append(category)
    return allowed


def property_allowed(context: AccessContext, property_id: str | None) -> bool:
    if not property_id or context.role in {"OWNER", "GROUP_ADMIN_HR"}:
        return True
    return property_id in context.property_ids


def department_allowed(context: AccessContext, department_id: str | None) -> bool:
    if context.role != "DEPARTMENT_HEAD" or not department_id:
        return True
    allowed = set(context.department_ids)
    if context.department_id:
        allowed.add(context.department_id)
    return department_id in allowed


def complaint_search_allowed(context: AccessContext, complaint: dict, assigned_case_ids: set[str]) -> bool:
    """Mirror confidential case-list authorization without exposing case content."""
    case_id = str(complaint.get("id"))
    if complaint.get("complaint_type") == "POSH":
        return case_id in assigned_case_ids
    return context.role in {"OWNER", "GROUP_ADMIN_HR"} or case_id in assigned_case_ids


def match_score(query: str, values: Iterable[object]) -> tuple[float, str] | None:
    needle = normalize_query(query)
    best: tuple[float, str] | None = None
    for raw in values:
        value = normalize_query(str(raw or ""))
        if not value:
            continue
        if value == needle:
            current = (100.0, "exact")
        elif value.startswith(needle):
            current = (90.0, "prefix")
        elif needle in value:
            current = (75.0, "contains")
        elif all(token in value for token in needle.split()):
            current = (68.0, "tokens")
        else:
            ratio = SequenceMatcher(None, needle, value).ratio()
            token_ratio = max((SequenceMatcher(None, needle, token).ratio() for token in value.split()), default=0)
            ratio = max(ratio, token_ratio)
            if ratio < 0.62:
                continue
            current = (round(ratio * 65, 2), "fuzzy")
        if best is None or current[0] > best[0]:
            best = current
    return best


@dataclass(frozen=True)
class SearchResult:
    category: str
    id: str
    title: str
    subtitle: str
    status: str | None
    url: str
    score: float
    match_type: str
    metadata: dict

    def as_dict(self) -> dict:
        return {
            "category": self.category, "id": self.id, "title": self.title,
            "subtitle": self.subtitle, "status": self.status, "url": self.url,
            "score": self.score, "matchType": self.match_type, "metadata": self.metadata,
        }


def make_result(*, query: str, category: str, row_id: object, title: str,
                subtitle: str = "", status: object = None, url: str,
                searchable: Iterable[object] = (), metadata: dict | None = None) -> SearchResult | None:
    ranked = match_score(query, [title, subtitle, *searchable])
    if not ranked:
        return None
    return SearchResult(category, str(row_id), title, subtitle, str(status) if status else None,
                        url, ranked[0], ranked[1], metadata or {})
