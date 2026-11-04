"""
Feature 05 India — Employee Referral Program Engine
Routes: /api/v1/india-referrals/...
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Annotated
from datetime import datetime
import logging

from fastapi import Depends

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.india_referral_service import (
    get_active_campaign,
    calculate_total_reward,
    check_retention_eligibility,
    check_and_award_badges,
    check_and_award_whatsapp_badge,
    build_whatsapp_share_link,
    format_inr,
)
from app.services.referral_service import (
    generate_referral_code,
    build_referral_link,
)
from app.core.config import settings
from app.services.festive_campaign_service import (
    get_all_active_campaigns,
    get_next_campaign,
    stack_bonuses,
    get_supported_festivals,
)
from app.services.badge_service import (
    BADGE_CATALOG,
    get_next_milestone,
    award_milestones,
)
from app.services.razorpay_payout_service import (
    create_razorpay_payout_service,
)

CurrentUser = Annotated[dict, Depends(get_current_user)]

router = APIRouter(tags=["India Referrals"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ProgramCreate(BaseModel):
    name: str
    description: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    reward_on_apply: float = 0
    reward_on_hire: float = 5000
    retention_bonus: float = 2000
    retention_days: int = 90
    currency: str = "INR"


class CampaignCreate(BaseModel):
    name: str
    festival_name: Optional[str] = None
    start_date: str
    end_date: str
    bonus_multiplier: float = 1.0
    bonus_flat: float = 0
    banner_text: Optional[str] = None
    banner_color: str = "#FF6B00"
    whatsapp_template: Optional[str] = None


class UPIDetailsRequest(BaseModel):
    upi_id: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bank_name: Optional[str] = None
    account_holder_name: Optional[str] = None


class CreateIndiaReferralRequest(BaseModel):
    job_role_id: str
    job_title: str = "Hospitality Role"
    candidate_email: Optional[str] = None
    program_id: Optional[str] = None
    notes: Optional[str] = None


class RetentionCheckRequest(BaseModel):
    referral_id: str


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------

@router.get("/programs")
async def list_programs(supabase: SupabaseClient, user: CurrentUser):
    """List all referral programs (active first)."""
    result = (
        supabase.table("referral_programs")
        .select("*")
        .order("is_active", desc=True)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.post("/programs")
async def create_program(body: ProgramCreate, supabase: SupabaseClient, user: CurrentUser):
    """Create a new referral program."""
    result = supabase.table("referral_programs").insert({
        **body.model_dump(exclude_none=True),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create program")
    return result.data[0]


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

@router.get("/campaigns")
async def list_campaigns(supabase: SupabaseClient, user: CurrentUser):
    """List all festive campaigns, newest first."""
    result = (
        supabase.table("referral_campaigns")
        .select("*")
        .order("start_date", desc=True)
        .execute()
    )
    return result.data or []


@router.get("/campaigns/active")
async def get_active_campaign_endpoint(supabase: SupabaseClient, user: CurrentUser):
    """Return current active festive campaign (null if none)."""
    campaign = get_active_campaign(supabase)
    return {"campaign": campaign}


@router.post("/campaigns")
async def create_campaign(body: CampaignCreate, supabase: SupabaseClient, user: CurrentUser):
    """Create a new festive campaign."""
    result = supabase.table("referral_campaigns").insert({
        **body.model_dump(exclude_none=True),
        "created_at": datetime.utcnow().isoformat(),
    }).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create campaign")
    return result.data[0]


# ---------------------------------------------------------------------------
# Badges
# ---------------------------------------------------------------------------

@router.get("/badges")
async def list_badges(supabase: SupabaseClient, user: CurrentUser):
    """Return full badge catalog sorted by required_hires."""
    result = (
        supabase.table("referral_badges")
        .select("*")
        .order("required_hires")
        .execute()
    )
    return result.data or []


@router.get("/my-badges")
async def get_my_badges(supabase: SupabaseClient, user: CurrentUser):
    """Return badges earned by the current user with badge details."""
    user_id = user.get("sub")
    result = (
        supabase.table("employee_badges")
        .select("*, referral_badges(*)")
        .eq("user_id", user_id)
        .order("earned_at", desc=True)
        .execute()
    )
    return result.data or []


# ---------------------------------------------------------------------------
# UPI / Bank Details
# ---------------------------------------------------------------------------

@router.get("/upi")
async def get_upi_details(supabase: SupabaseClient, user: CurrentUser):
    """Get current user's UPI/bank details."""
    user_id = user.get("sub")
    result = (
        supabase.table("employee_upi_details")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return {"upi_details": None}
    details = result.data[0]
    # Mask account number for safety
    if details.get("bank_account_number"):
        acct = details["bank_account_number"]
        details["bank_account_number"] = "****" + acct[-4:] if len(acct) > 4 else "****"
    return {"upi_details": details}


@router.post("/upi")
async def save_upi_details(body: UPIDetailsRequest, supabase: SupabaseClient, user: CurrentUser):
    """Create or update UPI/bank details for the current user."""
    user_id = user.get("sub")
    payload = {
        **body.model_dump(exclude_none=True),
        "user_id": user_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    # Upsert on unique(user_id)
    existing = (
        supabase.table("employee_upi_details")
        .select("id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        result = (
            supabase.table("employee_upi_details")
            .update(payload)
            .eq("user_id", user_id)
            .execute()
        )
    else:
        payload["created_at"] = datetime.utcnow().isoformat()
        result = supabase.table("employee_upi_details").insert(payload).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save UPI details")
    return {"saved": True, "upi_id": body.upi_id}


# ---------------------------------------------------------------------------
# India-aware referral creation
# ---------------------------------------------------------------------------

@router.post("/create")
async def create_india_referral(
    body: CreateIndiaReferralRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Create a referral link with India campaign + INR reward applied."""
    referrer_id = user.get("sub")
    referrer_email = user.get("email", "")
    campaign = get_active_campaign(supabase)

    # Determine base reward from program or default
    base_reward = 5000.0
    if body.program_id:
        prog = supabase.table("referral_programs").select("reward_on_hire").eq("id", body.program_id).limit(1).execute()
        if prog.data:
            base_reward = float(prog.data[0].get("reward_on_hire", 5000))

    reward_breakdown = calculate_total_reward(base_reward, campaign)
    total_reward = reward_breakdown["total_reward"]

    referral_code = generate_referral_code()
    referral_link = build_referral_link(settings.APP_BASE_URL, body.job_role_id, referral_code)
    whatsapp_link = build_whatsapp_share_link(referral_link, body.job_title, total_reward, campaign)

    insert_payload: dict = {
        "referrer_id": referrer_id,
        "referrer_email": referrer_email,
        "candidate_email": body.candidate_email,
        "job_role_id": body.job_role_id,
        "referral_code": referral_code,
        "status": "PENDING",
        "reward_amount": total_reward,
        "reward_status": "NOT_EARNED",
        "currency": "INR",
        "notes": body.notes,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    if body.program_id:
        insert_payload["program_id"] = body.program_id
    if campaign:
        insert_payload["campaign_id"] = campaign["id"]

    result = supabase.table("referrals").insert(insert_payload).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create referral")

    return {
        "referral_id": result.data[0]["id"],
        "referral_code": referral_code,
        "referral_link": referral_link,
        "whatsapp_link": whatsapp_link,
        "reward_breakdown": reward_breakdown,
        "active_campaign": campaign,
    }


# ---------------------------------------------------------------------------
# WhatsApp share tracking
# ---------------------------------------------------------------------------

@router.post("/referrals/{referral_id}/whatsapp-shared")
async def mark_whatsapp_shared(
    referral_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Mark a referral as shared via WhatsApp."""
    user_id = user.get("sub")
    result = (
        supabase.table("referrals")
        .select("id,referrer_id")
        .eq("id", referral_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Referral not found")
    if result.data[0].get("referrer_id") != user_id:
        raise HTTPException(status_code=403, detail="Not your referral")

    supabase.table("referrals").update({
        "whatsapp_shared": True,
        "whatsapp_shared_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", referral_id).execute()

    # Check WhatsApp Hero badge
    new_badge = check_and_award_whatsapp_badge(supabase, user_id)
    return {"tracked": True, "new_badge": new_badge}


# ---------------------------------------------------------------------------
# WhatsApp share link (re-generate)
# ---------------------------------------------------------------------------

@router.get("/referrals/{referral_id}/whatsapp-link")
async def get_whatsapp_link(
    referral_id: str,
    job_title: str = "Hospitality Role",
    supabase: SupabaseClient = None,
    user: CurrentUser = None,
):
    """Return a fresh wa.me link for sharing a referral."""
    result = (
        supabase.table("referrals")
        .select("referral_code,reward_amount,job_role_id,campaign_id")
        .eq("id", referral_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Referral not found")
    ref = result.data[0]

    campaign = None
    if ref.get("campaign_id"):
        camp_res = supabase.table("referral_campaigns").select("*").eq("id", ref["campaign_id"]).limit(1).execute()
        if camp_res.data:
            campaign = camp_res.data[0]

    referral_link = build_referral_link(settings.APP_BASE_URL, ref["job_role_id"], ref["referral_code"])
    wa_link = build_whatsapp_share_link(referral_link, job_title, ref.get("reward_amount", 5000), campaign)
    return {"whatsapp_link": wa_link, "referral_link": referral_link}


# ---------------------------------------------------------------------------
# 90-day retention check
# ---------------------------------------------------------------------------

@router.post("/referrals/{referral_id}/check-retention")
async def check_retention(
    referral_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Check 90-day retention gate and release bonus if eligible."""
    result = (
        supabase.table("referrals")
        .select("*")
        .eq("id", referral_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Referral not found")
    ref = result.data[0]

    if ref.get("status") not in ("HIRED", "REWARDED"):
        return {"eligible": False, "reason": "Referral not yet in HIRED status"}

    if ref.get("retention_bonus_status") == "PAID":
        return {"eligible": False, "reason": "Retention bonus already paid", "already_paid": True}

    hire_date = ref.get("hire_date")
    eligible = check_retention_eligibility(hire_date, retention_days=90)

    if not eligible:
        if hire_date:
            from datetime import timedelta
            hd = datetime.fromisoformat(hire_date.replace("Z", ""))
            eligible_on = (hd + timedelta(days=90)).strftime("%d %b %Y")
        else:
            eligible_on = "Unknown (hire date not recorded)"
        return {"eligible": False, "reason": f"90-day period not complete. Eligible on: {eligible_on}"}

    # Determine retention bonus from program or default
    retention_bonus = 2000.0
    if ref.get("program_id"):
        prog = supabase.table("referral_programs").select("retention_bonus").eq("id", ref["program_id"]).limit(1).execute()
        if prog.data:
            retention_bonus = float(prog.data[0].get("retention_bonus", 2000))

    supabase.table("referrals").update({
        "retention_bonus_status": "ELIGIBLE",
        "retention_bonus_amount": retention_bonus,
        "retention_check_date": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", referral_id).execute()

    return {
        "eligible": True,
        "retention_bonus_amount": retention_bonus,
        "formatted_bonus": format_inr(retention_bonus),
        "message": f"90-day retention confirmed. ₹{retention_bonus:,.0f} retention bonus is now ELIGIBLE for payout.",
    }


# ---------------------------------------------------------------------------
# UPI payout (mock / stub)
# ---------------------------------------------------------------------------

@router.post("/referrals/{referral_id}/pay-upi")
async def initiate_upi_payout(
    referral_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Initiate a real UPI payout via Razorpay, or a deterministic mock when
    RAZORPAY_* env vars are not configured.

    States written to referrals.payout_status:
      PROCESSING — Razorpay accepted the request; final state arrives via webhook
      PAID       — processed immediately (rare for UPI; common in mock mode)
      FAILED     — Razorpay rejected the payout
    """
    user_id = user.get("sub")

    # ── Fetch referral ──────────────────────────────────────────────────────
    ref_res = (
        supabase.table("referrals")
        .select("id, referrer_id, reward_amount, reward_status, payout_status")
        .eq("id", referral_id)
        .eq("referrer_id", user_id)
        .limit(1)
        .execute()
    )
    if not ref_res.data:
        raise HTTPException(status_code=404, detail="Referral not found or not yours.")
    ref = ref_res.data[0]

    if ref.get("reward_status") != "EARNED":
        raise HTTPException(
            status_code=400,
            detail=f"Reward must be in EARNED state. Current: {ref.get('reward_status')}",
        )

    if ref.get("payout_status") in ("PROCESSING", "PAID"):
        raise HTTPException(
            status_code=409,
            detail=f"A payout is already {ref.get('payout_status')} for this referral.",
        )

    # ── Fetch employee UPI details ──────────────────────────────────────────
    upi_res = (
        supabase.table("employee_upi_details")
        .select("upi_id, account_holder_name, razorpay_fund_account_id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not upi_res.data or not upi_res.data[0].get("upi_id"):
        raise HTTPException(status_code=400, detail="No UPI ID saved. Add UPI details first.")

    upi_row = upi_res.data[0]
    upi_id  = upi_row["upi_id"]
    amount_inr = float(ref.get("reward_amount") or 0)

    # ── Razorpay payout (real or mock) ─────────────────────────────────────
    rzp = create_razorpay_payout_service(
        settings.RAZORPAY_KEY_ID,
        settings.RAZORPAY_KEY_SECRET,
        getattr(settings, "RAZORPAY_FUND_ACCOUNT", None),
    )

    if rzp is None:
        raise HTTPException(503, "Razorpay payouts are not configured; no payment was made")

    try:
        result = await rzp.process_referral_payout(
            referral_id=referral_id,
            upi_id=upi_id,
            amount_inr=amount_inr,
            employee_name=upi_row.get("account_holder_name") or "Employee",
            existing_fund_account_id=upi_row.get("razorpay_fund_account_id"),
        )

        # Cache the fund_account_id for next payout
        if result.get("fund_account_id") and not upi_row.get("razorpay_fund_account_id"):
            supabase.table("employee_upi_details").update({
                "razorpay_fund_account_id": result["fund_account_id"],
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("user_id", user_id).execute()

    except Exception as exc:
        logger.error("Razorpay payout failed for referral %s: %s", referral_id, exc)
        supabase.table("referrals").update({
            "payout_status": "FAILED",
            "updated_at":    datetime.utcnow().isoformat(),
        }).eq("id", referral_id).execute()
        raise HTTPException(status_code=502, detail=f"Payout failed: {exc}")

    # ── Persist payout state ────────────────────────────────────────────────
    internal_status = result["internal_status"]   # PROCESSING | PAID | FAILED
    now = datetime.utcnow().isoformat()
    update_data: dict = {
        "razorpay_payout_id": result["payout_id"],
        "payout_status":      internal_status,
        "upi_payment_ref":    result["payout_id"],
        "updated_at":         now,
    }
    if internal_status == "PAID":
        update_data["reward_status"]  = "PAID"
        update_data["reward_paid_at"] = now
    elif internal_status == "FAILED":
        update_data["reward_status"] = "FAILED"
    # PROCESSING: leave reward_status as EARNED until webhook confirms

    supabase.table("referrals").update(update_data).eq("id", referral_id).execute()

    # ── Badge check ─────────────────────────────────────────────────────────
    new_badges: list = []
    if internal_status == "PAID":
        hired_res = (
            supabase.table("referrals")
            .select("id", count="exact")
            .eq("referrer_id", user_id)
            .in_("status", ["HIRED", "REWARDED"])
            .execute()
        )
        new_badges = check_and_award_badges(supabase, user_id, hired_res.count or 0)

    return {
        "payout_id":       result["payout_id"],
        "payout_status":   internal_status,
        "upi_id":          upi_id,
        "amount_inr":      amount_inr,
        "amount_paise":    result["amount_paise"],
        "formatted_amount": format_inr(amount_inr),
        "mock":            result.get("mock", False),
        "new_badges_earned": new_badges,
    }


# ---------------------------------------------------------------------------
# India Leaderboard
# ---------------------------------------------------------------------------

@router.get("/leaderboard")
async def india_leaderboard(supabase: SupabaseClient, user: CurrentUser):
    """Leaderboard sorted by hired count with INR totals."""
    result = (
        supabase.table("referrals")
        .select("referrer_id,referrer_email,status,reward_amount,reward_status,currency")
        .execute()
    )
    referrals = result.data or []

    agg: dict = {}
    for ref in referrals:
        rid = ref.get("referrer_id") or ref.get("referrer_email", "unknown")
        email = ref.get("referrer_email", "unknown")
        if rid not in agg:
            agg[rid] = {
                "referrer_email": email,
                "total_referrals": 0,
                "hired_count": 0,
                "total_earned_inr": 0.0,
            }
        agg[rid]["total_referrals"] += 1
        if ref.get("status") in ("HIRED", "REWARDED"):
            agg[rid]["hired_count"] += 1
        if ref.get("reward_status") in ("EARNED", "PAID"):
            agg[rid]["total_earned_inr"] += ref.get("reward_amount", 0) or 0

    board = sorted(agg.values(), key=lambda x: x["hired_count"], reverse=True)[:10]
    for entry in board:
        entry["formatted_earned"] = format_inr(entry["total_earned_inr"])

    return board


# ---------------------------------------------------------------------------
# GET /gamification/status — auth required
# ---------------------------------------------------------------------------

@router.get("/gamification/status")
async def gamification_status(supabase: SupabaseClient, user: CurrentUser):
    """
    Complete gamification snapshot for the current user.

    Returns in a single call:
      • All active festive campaigns (with stacked bonus breakdown)
      • Next upcoming campaign + days until it starts
      • Hired count, WhatsApp share count, total earned INR
      • Earned badges (with badge details joined)
      • Full Hindi badge catalog (for rendering locked/unlocked grid)
      • Next unearned milestone with progress %
      • Newly awarded badges (triggered by this request's auto-award)
    """
    user_id = user.get("sub")
    active_hired_statuses = ["HIRED", "REWARDED", "BONUS_PAID"]

    # ── Parallel DB reads ────────────────────────────────────────────────────
    hired_res = (
        supabase.table("referrals")
        .select("id", count="exact")
        .eq("referrer_id", user_id)
        .in_("status", active_hired_statuses)
        .execute()
    )
    wa_res = (
        supabase.table("referrals")
        .select("id", count="exact")
        .eq("referrer_id", user_id)
        .eq("whatsapp_shared", True)
        .execute()
    )
    earned_res = (
        supabase.table("referrals")
        .select("reward_amount")
        .eq("referrer_id", user_id)
        .in_("reward_status", ["EARNED", "PAID"])
        .execute()
    )
    badges_res = (
        supabase.table("employee_badges")
        .select("id, earned_at, referral_count_at_award, referral_badges(*)")
        .eq("user_id", user_id)
        .execute()
    )

    hired_count  = hired_res.count or 0
    wa_count     = wa_res.count or 0
    total_earned = sum(r.get("reward_amount", 0) or 0 for r in (earned_res.data or []))
    earned_badges = badges_res.data or []

    # Collect earned badge names for lookup
    earned_badge_names: set[str] = {
        eb.get("referral_badges", {}).get("name", "")
        for eb in earned_badges
        if eb.get("referral_badges")
    }

    # ── Campaigns ───────────────────────────────────────────────────────────
    active_campaigns = get_all_active_campaigns(supabase)
    next_campaign    = get_next_campaign(supabase)

    # Stacked bonus on default base (5000 INR)
    bonus_breakdown = stack_bonuses(5000.0, active_campaigns) if active_campaigns else None

    # ── Auto-award newly reached milestones ─────────────────────────────────
    newly_awarded = award_milestones(supabase, user_id, hired_count, wa_count)

    # ── Next milestone ───────────────────────────────────────────────────────
    next_milestone = get_next_milestone(hired_count, wa_count)

    # ── Augment catalog with earned status ───────────────────────────────────
    catalog_with_status = [
        {
            **entry,
            "earned": entry["name"] in earned_badge_names,
            "earned_at": next(
                (eb["earned_at"] for eb in earned_badges
                 if eb.get("referral_badges", {}).get("name") == entry["name"]),
                None
            ),
        }
        for entry in BADGE_CATALOG
    ]

    return {
        "hired_count":       hired_count,
        "whatsapp_count":    wa_count,
        "total_earned_inr":  total_earned,
        "formatted_earned":  format_inr(total_earned),
        "active_campaigns":  active_campaigns,
        "next_campaign":     next_campaign,
        "bonus_breakdown":   bonus_breakdown,
        "badges_earned":     earned_badges,
        "badges_catalog":    catalog_with_status,
        "next_milestone":    next_milestone,
        "newly_awarded":     newly_awarded,
        "supported_festivals": get_supported_festivals(),
    }
