"""
Admin Referral Dashboard — backend router.
Prefix: /api/v1/admin-referrals

All endpoints require the caller to have role = 'admin' in the users table.

Endpoints:
  GET  /dashboard           Aggregated stats snapshot
  GET  /referrals           Paginated, filterable referral list
  GET  /pending-payouts     Referrals eligible for 90-day retention bonus
  POST /campaigns           Create a festive campaign
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Annotated
from datetime import datetime, timedelta
import logging

from fastapi import Depends

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.india_referral_service import format_inr

router = APIRouter(tags=["Admin Referrals"])
logger = logging.getLogger(__name__)

CurrentUser = Annotated[dict, Depends(get_current_user)]

# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _require_admin(user: dict, supabase) -> None:
    """Raise 403 if the caller does not have role='admin' in the users table."""
    caller_id = user.get("sub", "")
    try:
        res = (
            supabase.table("users")
            .select("role")
            .eq("id", caller_id)
            .limit(1)
            .execute()
        )
        if res.data and res.data[0].get("role") == "admin":
            return
    except Exception as exc:
        logger.warning("Admin role check failed: %s", exc)
    raise HTTPException(status_code=403, detail="Admin access required.")


# ---------------------------------------------------------------------------
# GET /dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard")
async def get_dashboard(supabase: SupabaseClient, user: CurrentUser):
    """
    Aggregated stats snapshot for the admin dashboard.

    Returns total referrals, hired count, pending 90-day bonuses,
    paid bonuses, WhatsApp shares, and ₹ totals — all in one call.
    Also returns the 10 most recent referrals and pending-payout rows.
    """
    _require_admin(user, supabase)

    cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()

    # ── Count queries ────────────────────────────────────────────────────────
    total_res = (
        supabase.table("referrals").select("id", count="exact").execute()
    )
    hired_res = (
        supabase.table("referrals")
        .select("id", count="exact")
        .in_("status", ["HIRED", "REWARDED", "BONUS_PAID"])
        .execute()
    )
    pending_bonus_res = (
        supabase.table("referrals")
        .select("id", count="exact")
        .eq("status", "HIRED")
        .lte("hire_date", cutoff)
        .is_("bonus_paid_at", None)
        .gt("retention_bonus_amount", 0)
        .execute()
    )
    paid_bonus_res = (
        supabase.table("referrals")
        .select("id", count="exact")
        .eq("retention_bonus_status", "PAID")
        .execute()
    )
    wa_res = (
        supabase.table("referrals")
        .select("id", count="exact")
        .eq("whatsapp_shared", True)
        .execute()
    )

    # ── Sum queries ──────────────────────────────────────────────────────────
    reward_rows = (
        supabase.table("referrals")
        .select("reward_amount")
        .in_("reward_status", ["EARNED", "PAID"])
        .execute()
    ).data or []

    bonus_rows = (
        supabase.table("referrals")
        .select("retention_bonus_amount")
        .eq("retention_bonus_status", "PAID")
        .execute()
    ).data or []

    total_reward = sum(r.get("reward_amount", 0) or 0 for r in reward_rows)
    total_bonus  = sum(r.get("retention_bonus_amount", 0) or 0 for r in bonus_rows)
    grand_total  = total_reward + total_bonus

    # ── Recent referrals (last 10) ───────────────────────────────────────────
    recent_rows = (
        supabase.table("referrals")
        .select(
            "id, referral_code, referrer_email, candidate_email, status, "
            "reward_amount, reward_status, whatsapp_shared, campaign_id, created_at"
        )
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    ).data or []

    # ── Pending 90-day payouts ────────────────────────────────────────────────
    pending_rows = (
        supabase.table("referrals")
        .select(
            "id, referral_code, referrer_email, referrer_id, candidate_email, "
            "hire_date, retention_bonus_amount, bonus_paid_at"
        )
        .eq("status", "HIRED")
        .lte("hire_date", cutoff)
        .is_("bonus_paid_at", None)
        .gt("retention_bonus_amount", 0)
        .order("hire_date", desc=False)
        .limit(50)
        .execute()
    ).data or []

    now = datetime.utcnow()
    for row in pending_rows:
        hd = row.get("hire_date")
        if hd:
            try:
                row["days_elapsed"] = (now - datetime.fromisoformat(hd.replace("Z", ""))).days
            except Exception:
                row["days_elapsed"] = None

    return {
        "stats": {
            "total_referrals":          total_res.count or 0,
            "hired_count":              hired_res.count or 0,
            "pending_eligible_bonuses": pending_bonus_res.count or 0,
            "paid_bonuses":             paid_bonus_res.count or 0,
            "whatsapp_shares":          wa_res.count or 0,
            "total_reward_paid_inr":    total_reward,
            "total_bonus_paid_inr":     total_bonus,
            "grand_total_paid_inr":     grand_total,
            "formatted_reward_paid":    format_inr(total_reward),
            "formatted_bonus_paid":     format_inr(total_bonus),
            "formatted_grand_total":    format_inr(grand_total),
        },
        "recent_referrals": recent_rows,
        "pending_payouts":  pending_rows,
    }


# ---------------------------------------------------------------------------
# GET /referrals
# ---------------------------------------------------------------------------

@router.get("/referrals")
async def list_referrals(
    supabase: SupabaseClient,
    user: CurrentUser,
    status:       Optional[str] = Query(None, description="Filter by referral status"),
    reward_status: Optional[str] = Query(None, description="Filter by reward_status"),
    campaign_id:  Optional[str] = Query(None, description="Filter by campaign UUID"),
    date_from:    Optional[str] = Query(None, description="ISO date — created_at ≥"),
    date_to:      Optional[str] = Query(None, description="ISO date — created_at ≤"),
    page:         int           = Query(1, ge=1),
    limit:        int           = Query(25, ge=1, le=100),
):
    """
    Paginated, filterable referral list (admin only).

    Filters: status, reward_status, campaign_id, date_from, date_to.
    Pagination: page (1-based) + limit (max 100).
    """
    _require_admin(user, supabase)

    offset = (page - 1) * limit

    q = (
        supabase.table("referrals")
        .select(
            "id, referral_code, referrer_email, candidate_email, job_role_id, "
            "status, reward_amount, reward_status, currency, whatsapp_shared, "
            "hire_date, bonus_paid_at, retention_bonus_amount, retention_bonus_status, "
            "campaign_id, created_at, link_token",
            count="exact",
        )
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )

    if status:       q = q.eq("status", status)
    if reward_status: q = q.eq("reward_status", reward_status)
    if campaign_id:  q = q.eq("campaign_id", campaign_id)
    if date_from:    q = q.gte("created_at", date_from)
    if date_to:      q = q.lte("created_at", date_to)

    result = q.execute()
    total  = result.count or 0

    return {
        "referrals": result.data or [],
        "total":     total,
        "page":      page,
        "limit":     limit,
        "pages":     max(1, (total + limit - 1) // limit),
    }


# ---------------------------------------------------------------------------
# GET /pending-payouts
# ---------------------------------------------------------------------------

@router.get("/pending-payouts")
async def get_pending_payouts(supabase: SupabaseClient, user: CurrentUser):
    """
    Return all HIRED referrals where hire_date ≤ 90 days ago,
    bonus_paid_at IS NULL, and retention_bonus_amount > 0.
    These are ready for the admin to trigger manual UPI payouts.
    """
    _require_admin(user, supabase)

    cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
    now    = datetime.utcnow()

    result = (
        supabase.table("referrals")
        .select(
            "id, referral_code, referrer_email, referrer_id, candidate_email, "
            "hire_date, retention_bonus_amount, retention_bonus_status, "
            "bonus_paid_at, upi_payment_ref, currency"
        )
        .eq("status", "HIRED")
        .lte("hire_date", cutoff)
        .is_("bonus_paid_at", None)
        .gt("retention_bonus_amount", 0)
        .order("hire_date", desc=False)
        .execute()
    )

    rows = result.data or []
    for row in rows:
        hd = row.get("hire_date")
        if hd:
            try:
                elapsed = (now - datetime.fromisoformat(hd.replace("Z", ""))).days
                row["days_elapsed"]   = elapsed
                row["over_threshold"] = elapsed >= 90
            except Exception:
                row["days_elapsed"]   = None
                row["over_threshold"] = False
        row["formatted_bonus"] = format_inr(row.get("retention_bonus_amount", 0))

    return {"pending_payouts": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# POST /campaigns  (admin campaign creation)
# ---------------------------------------------------------------------------

class AdminCampaignCreate(BaseModel):
    name:             str
    festival_name:    str
    start_date:       str
    end_date:         str
    bonus_multiplier: float = 1.5
    bonus_flat:       float = 0
    banner_text:      str   = ""
    banner_color:     str   = "#FF6B00"
    is_active:        bool  = True


@router.post("/campaigns", status_code=201)
async def admin_create_campaign(
    body: AdminCampaignCreate,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Create a new festive campaign (admin only)."""
    _require_admin(user, supabase)

    valid_festivals = {
        "DIWALI", "EID", "HOLI", "ONAM", "PONGAL", "CHRISTMAS", "NEW_YEAR"
    }
    if body.festival_name not in valid_festivals:
        raise HTTPException(
            status_code=422,
            detail=f"festival_name must be one of {sorted(valid_festivals)}",
        )

    if body.bonus_multiplier < 1.0 or body.bonus_multiplier > 5.0:
        raise HTTPException(status_code=422, detail="bonus_multiplier must be 1.0–5.0")

    result = supabase.table("referral_campaigns").insert({
        "name":             body.name,
        "festival_name":    body.festival_name,
        "start_date":       body.start_date,
        "end_date":         body.end_date,
        "bonus_multiplier": body.bonus_multiplier,
        "bonus_flat":       body.bonus_flat,
        "banner_text":      body.banner_text,
        "banner_color":     body.banner_color,
        "is_active":        body.is_active,
        "created_at":       datetime.utcnow().isoformat(),
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create campaign.")

    return result.data[0]
