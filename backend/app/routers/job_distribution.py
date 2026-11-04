from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.job_distribution_service import (
    CHANNELS, channel_catalog, expiry_iso, export_csv, platform_content,
    tracked_url, whatsapp_share_url,
)

router = APIRouter(tags=["Job Distribution"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


def _first(result):
    rows = getattr(result, "data", None) or []
    return rows[0] if rows else None


def _org(supabase, user: dict) -> str:
    row = _first(supabase.table("users").select("org_id").eq("id", user["sub"]).limit(1).execute())
    if not row:
        raise HTTPException(404, "User not found")
    return row["org_id"]


class ChannelConfigUpdate(BaseModel):
    is_enabled: bool = True
    default_expiry_days: int = Field(30, ge=1, le=365)
    configuration: dict = Field(default_factory=dict)


class PrepareRequest(BaseModel):
    channels: list[str] = Field(min_length=1, max_length=20)
    expiry_days: int = Field(30, ge=1, le=365)


class PublishRequest(BaseModel):
    posting_url: Optional[str] = None
    external_post_id: Optional[str] = None
    expires_at: Optional[str] = None


@router.get("/channels")
async def list_channels(supabase: SupabaseClient, user: CurrentUser):
    org_id = _org(supabase, user)
    saved = supabase.table("distribution_channels").select("*").eq("org_id", org_id).execute().data or []
    by_key = {row["channel_key"]: row for row in saved}
    return [{**item, **by_key.get(item["channel_key"], {})} for item in channel_catalog()]


@router.patch("/channels/{channel_key}")
async def configure_channel(channel_key: str, body: ChannelConfigUpdate, supabase: SupabaseClient, user: CurrentUser):
    if channel_key not in CHANNELS:
        raise HTTPException(404, "Unknown distribution channel")
    org_id = _org(supabase, user)
    name, mode = CHANNELS[channel_key]
    payload = {"org_id": org_id, "channel_key": channel_key, "display_name": name,
               "delivery_mode": mode, **body.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}
    existing = _first(supabase.table("distribution_channels").select("id").eq("org_id", org_id).eq("channel_key", channel_key).limit(1).execute())
    query = supabase.table("distribution_channels").update(payload).eq("id", existing["id"]) if existing else supabase.table("distribution_channels").insert(payload)
    row = _first(query.execute())
    return row or payload


@router.post("/jobs/{job_id}/prepare", status_code=201)
async def prepare_distributions(job_id: str, body: PrepareRequest, supabase: SupabaseClient, user: CurrentUser):
    org_id = _org(supabase, user)
    job = _first(supabase.table("jobs").select("*").eq("id", job_id).eq("org_id", org_id).limit(1).execute())
    if not job:
        raise HTTPException(404, "Job not found")
    unknown = sorted(set(body.channels) - set(CHANNELS))
    if unknown:
        raise HTTPException(422, f"Unsupported channels: {', '.join(unknown)}")
    results = []
    for key in body.channels:
        name, mode = CHANNELS[key]
        english, hindi = platform_content(job, key)
        existing = _first(supabase.table("job_distributions").select("*").eq("job_id", job_id).eq("channel_key", key).limit(1).execute())
        payload = {"org_id": org_id, "job_id": job_id, "channel_key": key, "delivery_mode": mode,
                   "content_english": english, "content_hindi": hindi, "expires_at": expiry_iso(body.expiry_days),
                   "created_by": user["sub"], "updated_at": datetime.now(timezone.utc).isoformat()}
        query = supabase.table("job_distributions").update(payload).eq("id", existing["id"]) if existing else supabase.table("job_distributions").insert(payload)
        saved = _first(query.execute()) or {**payload, "display_name": name}
        if saved.get("attribution_token"):
            apply_link = tracked_url(settings.API_PUBLIC_BASE_URL, str(saved["attribution_token"]))
            english, hindi = platform_content({**job, "distribution_apply_url": apply_link}, key)
            supabase.table("job_distributions").update({
                "content_english": english, "content_hindi": hindi,
            }).eq("id", saved.get("id")).execute()
            saved.update({"content_english": english, "content_hindi": hindi})
        results.append(saved)
    return {"job_id": job_id, "distributions": results}


@router.get("/jobs/{job_id}")
async def list_job_distributions(job_id: str, supabase: SupabaseClient, user: CurrentUser):
    org_id = _org(supabase, user)
    return supabase.table("job_distributions").select("*").eq("org_id", org_id).eq("job_id", job_id).order("created_at").execute().data or []


@router.post("/{distribution_id}/publish")
async def publish_distribution(distribution_id: str, body: PublishRequest, supabase: SupabaseClient, user: CurrentUser):
    org_id = _org(supabase, user)
    dist = _first(supabase.table("job_distributions").select("*").eq("id", distribution_id).eq("org_id", org_id).limit(1).execute())
    if not dist:
        raise HTTPException(404, "Distribution not found")
    job = _first(supabase.table("jobs").select("id,status,approval_status").eq("id", dist["job_id"]).eq("org_id", org_id).limit(1).execute())
    if not job or job.get("status") != "open" or job.get("approval_status") != "APPROVED":
        raise HTTPException(409, "Only approved open jobs can be published")
    mode = dist["delivery_mode"]
    if mode == "API":
        raise HTTPException(501, "No external board API adapter is configured")
    url = body.posting_url or tracked_url(settings.API_PUBLIC_BASE_URL, str(dist["attribution_token"]))
    if mode == "SHARE_LINK":
        url = whatsapp_share_url(dist.get("content_english") or "", url)
    values = {"status": "PUBLISHED", "posting_url": url, "external_post_id": body.external_post_id,
              "published_at": datetime.now(timezone.utc).isoformat(), "unpublished_at": None,
              "expires_at": body.expires_at or dist.get("expires_at"), "last_error": None,
              "updated_at": datetime.now(timezone.utc).isoformat()}
    supabase.table("job_distributions").update(values).eq("id", distribution_id).eq("org_id", org_id).execute()
    return {**values, "distribution_id": distribution_id, "delivery_mode": mode,
            "requires_manual_posting": mode == "MANUAL_EXPORT"}


@router.post("/{distribution_id}/unpublish")
async def unpublish_distribution(distribution_id: str, supabase: SupabaseClient, user: CurrentUser):
    org_id = _org(supabase, user)
    existing = _first(supabase.table("job_distributions").select("id").eq("id", distribution_id).eq("org_id", org_id).limit(1).execute())
    if not existing:
        raise HTTPException(404, "Distribution not found")
    values = {"status": "UNPUBLISHED", "unpublished_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
    supabase.table("job_distributions").update(values).eq("id", distribution_id).execute()
    return values


@router.get("/export.csv")
async def download_export(supabase: SupabaseClient, user: CurrentUser, job_id: Optional[str] = Query(None), channel: Optional[str] = Query(None)):
    org_id = _org(supabase, user)
    query = supabase.table("job_distributions").select("*").eq("org_id", org_id)
    if job_id: query = query.eq("job_id", job_id)
    if channel: query = query.eq("channel_key", channel)
    rows = query.execute().data or []
    job_ids = list({row["job_id"] for row in rows})
    jobs = supabase.table("jobs").select("*").eq("org_id", org_id).in_("id", job_ids).execute().data or [] if job_ids else []
    return Response(export_csv(rows, {row["id"]: row for row in jobs}), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=job-distribution.csv"})


@router.get("/analytics/summary")
async def distribution_analytics(supabase: SupabaseClient, user: CurrentUser, job_id: Optional[str] = Query(None)):
    org_id = _org(supabase, user)
    query = supabase.table("job_distributions").select("*").eq("org_id", org_id)
    if job_id: query = query.eq("job_id", job_id)
    rows = query.execute().data or []
    totals = {"clicks": 0, "applications": 0, "hires": 0}
    for row in rows:
        totals["clicks"] += row.get("click_count", 0); totals["applications"] += row.get("application_count", 0); totals["hires"] += row.get("hire_count", 0)
    totals["application_conversion_pct"] = round(totals["applications"] / totals["clicks"] * 100, 1) if totals["clicks"] else 0
    totals["hire_conversion_pct"] = round(totals["hires"] / totals["applications"] * 100, 1) if totals["applications"] else 0
    return {"totals": totals, "channels": rows}


@router.get("/t/{token}", include_in_schema=False)
async def track_distribution_click(token: str, request: Request, supabase: SupabaseClient):
    ip = request.client.host if request.client else ""
    if hasattr(supabase, "rpc"):
        rpc = supabase.rpc("record_distribution_click", {"p_token": token,
            "p_ip_hash": hashlib.sha256(ip.encode()).hexdigest() if ip else None,
            "p_user_agent": request.headers.get("user-agent")}).execute()
        recorded = (rpc.data or [None])[0]
        if not recorded:
            raise HTTPException(404, "Posting is unavailable or expired")
        target = f"{settings.APP_BASE_URL.rstrip('/')}/india-apply/{recorded['job_id']}?org={recorded['org_id']}&src={recorded['channel_key']}&dist={token}"
        return RedirectResponse(target, status_code=302)
    dist = _first(supabase.table("job_distributions").select("*").eq("attribution_token", token).eq("status", "PUBLISHED").limit(1).execute())
    if not dist:
        raise HTTPException(404, "Posting is unavailable or expired")
    if dist.get("expires_at"):
        expires = datetime.fromisoformat(dist["expires_at"].replace("Z", "+00:00"))
        if expires < datetime.now(timezone.utc):
            supabase.table("job_distributions").update({"status": "EXPIRED"}).eq("id", dist["id"]).execute()
            raise HTTPException(410, "Posting has expired")
    supabase.table("job_distribution_events").insert({"org_id": dist["org_id"], "distribution_id": dist["id"],
        "job_id": dist["job_id"], "event_type": "CLICK", "ip_hash": hashlib.sha256(ip.encode()).hexdigest() if ip else None,
        "user_agent": request.headers.get("user-agent")}).execute()
    supabase.table("job_distributions").update({"click_count": int(dist.get("click_count") or 0) + 1}).eq("id", dist["id"]).execute()
    target = f"{settings.APP_BASE_URL.rstrip('/')}/india-apply/{dist['job_id']}?org={dist['org_id']}&src={dist['channel_key']}&dist={token}"
    return RedirectResponse(target, status_code=302)
