"""Honest job distribution: native links plus manual exports for unsupported boards."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from urllib.parse import quote


CHANNELS = {
    "website": ("Careers Website", "INTERNAL"),
    "whatsapp": ("WhatsApp", "SHARE_LINK"),
    "employee_referral": ("Employee Referrals", "REFERRAL"),
    "naukri": ("Naukri", "MANUAL_EXPORT"),
    "apna": ("Apna", "MANUAL_EXPORT"),
    "workindia": ("WorkIndia", "MANUAL_EXPORT"),
    "shine": ("Shine", "MANUAL_EXPORT"),
    "indeed": ("Indeed India", "MANUAL_EXPORT"),
    "linkedin": ("LinkedIn", "MANUAL_EXPORT"),
    "hospitality_board": ("Hospitality Job Boards", "MANUAL_EXPORT"),
    "qr_code": ("QR Codes", "QR"),
    "walk_in": ("Walk-in Campaign", "WALK_IN"),
}


def channel_catalog() -> list[dict]:
    return [
        {"channel_key": key, "display_name": name, "delivery_mode": mode,
         "classification": "API integration" if mode == "API" else
             "manual export" if mode == "MANUAL_EXPORT" else "native application channel"}
        for key, (name, mode) in CHANNELS.items()
    ]


def platform_content(job: dict, channel: str) -> tuple[str, str]:
    versions = job.get("job_board_versions") or {}
    aliases = {"indeed": "indeed_india", "employee_referral": "whatsapp",
               "workindia": "apna", "shine": "naukri", "hospitality_board": "linkedin",
               "website": "linkedin", "qr_code": "whatsapp", "walk_in": "whatsapp"}
    content = versions.get(channel) or versions.get(aliases.get(channel, channel)) or {}
    english = content.get("english") or job.get("jd_english") or job.get("description") or ""
    hindi = content.get("hindi") or job.get("jd_hindi") or ""
    distribution_url = job.get("distribution_apply_url")
    original_url = job.get("apply_url")
    if distribution_url:
        english = english.replace(original_url, distribution_url) if original_url and original_url in english else f"{english}\nApply: {distribution_url}".strip()
        hindi = hindi.replace(original_url, distribution_url) if original_url and original_url in hindi else f"{hindi}\nआवेदन: {distribution_url}".strip()
    return english, hindi


def tracked_url(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/api/v1/distribution/t/{token}"


def whatsapp_share_url(content: str, url: str) -> str:
    return f"https://wa.me/?text={quote((content + chr(10) + url).strip())}"


def expiry_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def export_csv(distributions: list[dict], jobs: dict[str, dict]) -> str:
    stream = io.StringIO()
    fields = ["channel", "job_id", "title", "property", "department", "location", "salary_min_inr",
              "salary_max_inr", "vacancies", "content_english", "content_hindi", "posting_url", "expires_at"]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for dist in distributions:
        job = jobs.get(dist.get("job_id"), {})
        writer.writerow({
            "channel": dist.get("channel_key"), "job_id": dist.get("job_id"), "title": job.get("title"),
            "property": job.get("property_name"), "department": job.get("department"),
            "location": ", ".join(filter(None, [job.get("location_city"), job.get("location_state")])),
            "salary_min_inr": job.get("salary_min_inr"), "salary_max_inr": job.get("salary_max_inr"),
            "vacancies": job.get("openings_count"), "content_english": dist.get("content_english"),
            "content_hindi": dist.get("content_hindi"), "posting_url": dist.get("posting_url"),
            "expires_at": dist.get("expires_at"),
        })
    return stream.getvalue()
