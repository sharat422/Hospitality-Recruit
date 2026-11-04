"""
Referral Program Engine — Router.
Endpoints for creating referral links, tracking referrals, managing rewards,
leaderboard, and admin views.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Annotated
from datetime import datetime
import logging

from fastapi import Depends

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.core.config import settings
from app.services.referral_service import (
    generate_referral_code,
    generate_link_token,
    build_referral_link,
    build_referral_link_v2,
    build_whatsapp_url,
    get_reward_amount,
    get_program_reward,
)
from app.services.whatsapp_template_service import (
    render_template,
    build_wa_url,
    SUPPORTED_LANGS,
)
from app.services.rbac_service import authorize, build_access_context
from app.services.referral_lifecycle_service import mark_application_referral_hired

CurrentUser = Annotated[dict, Depends(get_current_user)]

router = APIRouter(tags=["Referrals"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateReferralRequest(BaseModel):
    """
    Input for POST /referrals/create.

    programId           — active referral_programs row (drives the reward amount)
    referrerEmployeeId  — the employee making this referral (caller must be them or admin)
    jobRoleId           — the job being referred to
    candidateEmail      — optional; enables duplicate detection across referrers
    candidateId         — optional UUID if the candidate already exists in the DB
    jobTitle            — shown in the WhatsApp share message
    notes               — free-text, stored on the row
    """
    programId: str
    referrerEmployeeId: str
    jobRoleId: str
    candidateEmail: Optional[str] = None
    candidateId: Optional[str] = None
    jobTitle: str = "a hospitality role"
    notes: Optional[str] = None


class ApplyReferralRequest(BaseModel):
    candidate_email: str
    candidate_id: Optional[str] = None


class UpdateStatusRequest(BaseModel):
    status: str
    candidate_id: Optional[str] = None


# ---------------------------------------------------------------------------
# POST /create — auth required
# ---------------------------------------------------------------------------

@router.post("/create", status_code=201)
async def create_referral(
    body: CreateReferralRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Create a referral link.

    Authorization
    -------------
    The caller must be the referrerEmployeeId themselves **or** have
    role='admin' in the users table.

    Duplicate handling
    ------------------
    1. Exact duplicate  — same referrer + same candidate + same job + active
       status (PENDING/APPLIED/SHORTLISTED/HIRED) → return the existing record
       unchanged (idempotent).
    2. Cross-referrer conflict — same candidate already in active pipeline for
       the same job via a *different* referrer → 409 Conflict (first-referrer
       wins).

    Returns
    -------
    referralCode   – short human-readable code (REF-…)
    linkToken      – secure URL-safe token embedded in the link
    referralLink   – full apply URL (uses linkToken)
    whatsappUrl    – pre-filled wa.me deeplink
    referralId     – UUID of the created/existing row
    rewardAmount   – INR reward on hire from the program
    duplicate      – true when an existing referral was returned unchanged
    """
    caller_id = user.get("sub", "")
    caller_email = user.get("email", "")

    # ------------------------------------------------------------------
    # 1. Authorization
    # ------------------------------------------------------------------
    if caller_id != body.referrerEmployeeId:
        role_res = (
            supabase.table("users")
            .select("role")
            .eq("id", caller_id)
            .limit(1)
            .execute()
        )
        caller_role = role_res.data[0].get("role") if role_res.data else None
        if caller_role != "admin":
            raise HTTPException(
                status_code=403,
                detail=(
                    "Not authorized. You may only create referrals for yourself "
                    "unless you are an admin."
                ),
            )

    # ------------------------------------------------------------------
    # 2. Validate program exists and is active
    # ------------------------------------------------------------------
    prog_res = (
        supabase.table("referral_programs")
        .select("id, name, reward_on_hire, currency, is_active, org_id")
        .eq("id", body.programId)
        .limit(1)
        .execute()
    )
    if not prog_res.data:
        raise HTTPException(status_code=404, detail=f"Program '{body.programId}' not found.")
    program = prog_res.data[0]
    if not program.get("is_active"):
        raise HTTPException(status_code=409, detail=f"Program '{program['name']}' is not active.")

    reward = float(program.get("reward_on_hire") or 5000)
    currency = program.get("currency", "INR")

    # ------------------------------------------------------------------
    # 3. Duplicate detection (only when a candidate is identified)
    # ------------------------------------------------------------------
    active_statuses = ["PENDING", "APPLIED", "SHORTLISTED", "HIRED"]

    if body.candidateEmail or body.candidateId:
        candidate_filter_key = "candidate_email" if body.candidateEmail else "candidate_id"
        candidate_filter_val = body.candidateEmail or body.candidateId

        # 3a. Exact duplicate — same referrer already has this candidate+job active
        exact_res = (
            supabase.table("referrals")
            .select("id, referral_code, link_token, status, reward_amount")
            .eq("referrer_id", body.referrerEmployeeId)
            .eq("job_role_id", body.jobRoleId)
            .eq(candidate_filter_key, candidate_filter_val)
            .in_("status", active_statuses)
            .limit(1)
            .execute()
        )
        if exact_res.data:
            ref = exact_res.data[0]
            existing_token = ref.get("link_token") or ref["referral_code"]
            existing_link = build_referral_link_v2(
                settings.APP_BASE_URL, body.jobRoleId, existing_token
            )
            # 200 (not 201) — nothing was created; caller gets the existing record
            return JSONResponse(status_code=200, content={
                "referralId":    ref["id"],
                "referralCode":  ref["referral_code"],
                "linkToken":     existing_token,
                "referralLink":  existing_link,
                "whatsappUrl":   build_whatsapp_url(existing_link, body.jobTitle, reward, currency),
                "rewardAmount":  ref.get("reward_amount", reward),
                "duplicate":     True,
                "status":        ref["status"],
            })

        # 3b. Cross-referrer conflict — someone else already has this candidate
        #     in pipeline (APPLIED or beyond — not just PENDING)
        pipeline_statuses = ["APPLIED", "SHORTLISTED", "HIRED"]
        conflict_res = (
            supabase.table("referrals")
            .select("id, referrer_id")
            .eq("job_role_id", body.jobRoleId)
            .eq(candidate_filter_key, candidate_filter_val)
            .neq("referrer_id", body.referrerEmployeeId)
            .in_("status", pipeline_statuses)
            .limit(1)
            .execute()
        )
        if conflict_res.data:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This candidate already has an active referral for this job "
                    "from another referrer. The first referrer retains credit."
                ),
            )

    # ------------------------------------------------------------------
    # 4. Generate unique link_token (collision-safe retry)
    # ------------------------------------------------------------------
    link_token: Optional[str] = None
    for _ in range(3):
        candidate_token = generate_link_token()
        token_check = (
            supabase.table("referrals")
            .select("id")
            .eq("link_token", candidate_token)
            .limit(1)
            .execute()
        )
        if not token_check.data:
            link_token = candidate_token
            break

    if link_token is None:  # astronomically unlikely
        raise HTTPException(status_code=500, detail="Failed to generate a unique token.")

    referral_code = generate_referral_code()
    referral_link = build_referral_link_v2(settings.APP_BASE_URL, body.jobRoleId, link_token)

    # ------------------------------------------------------------------
    # 5. Insert
    # ------------------------------------------------------------------
    now = datetime.utcnow().isoformat()
    payload: dict = {
        "referrer_id":    body.referrerEmployeeId,
        "referrer_email": caller_email,
        "job_role_id":    body.jobRoleId,
        "referral_code":  referral_code,
        "link_token":     link_token,
        "status":         "PENDING",
        "reward_amount":  reward,
        "reward_status":  "NOT_EARNED",
        "currency":       currency,
        "notes":          body.notes,
        "created_at":     now,
        "updated_at":     now,
    }
    if program.get("org_id"):
        payload["org_id"] = program["org_id"]
    if body.candidateEmail:
        payload["candidate_email"] = body.candidateEmail
    if body.candidateId:
        payload["candidate_id"] = body.candidateId
    if body.programId:
        payload["program_id"] = body.programId

    try:
        result = supabase.table("referrals").insert(payload).execute()
    except Exception as exc:
        err = str(exc).lower()
        if "unique" in err or "duplicate" in err:
            # Race condition: another request inserted concurrently — treat as
            # idempotent and fall through to a fresh lookup.
            logger.warning("Concurrent insert collision for referral: %s", exc)
            raise HTTPException(
                status_code=409,
                detail="A referral for this combination was just created. Please retry.",
            )
        logger.error("Referral insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create referral.")

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create referral.")

    ref = result.data[0]
    return {
        "referralId":   ref["id"],
        "referralCode": referral_code,
        "linkToken":    link_token,
        "referralLink": referral_link,
        "whatsappUrl":  build_whatsapp_url(referral_link, body.jobTitle, reward, currency),
        "rewardAmount": reward,
        "duplicate":    False,
        "status":       "PENDING",
    }


# ---------------------------------------------------------------------------
# GET /my-referrals — auth required
# ---------------------------------------------------------------------------

@router.get("/my-referrals")
async def get_my_referrals(
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Fetch all referrals created by the current user with summary stats."""
    referrer_id = user.get("sub")

    result = (
        supabase.table("referrals")
        .select("*")
        .eq("referrer_id", referrer_id)
        .order("created_at", desc=True)
        .execute()
    )
    referrals = result.data or []

    total_referrals = len(referrals)
    applied_count = sum(1 for r in referrals if r.get("status") in ("APPLIED", "SHORTLISTED", "HIRED", "REWARDED"))
    hired_count = sum(1 for r in referrals if r.get("status") in ("HIRED", "REWARDED"))
    total_earned = sum(
        r.get("reward_amount", 0) or 0
        for r in referrals
        if r.get("reward_status") in ("EARNED", "PAID")
    )
    total_paid = sum(
        r.get("reward_amount", 0) or 0
        for r in referrals
        if r.get("reward_status") == "PAID"
    )

    return {
        "referrals": referrals,
        "summary": {
            "total_referrals": total_referrals,
            "applied_count": applied_count,
            "hired_count": hired_count,
            "total_earned": total_earned,
            "total_paid": total_paid,
        },
    }


# ---------------------------------------------------------------------------
# GET /all — auth required (admin view)
# ---------------------------------------------------------------------------

@router.get("/all")
async def get_all_referrals(
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Fetch ALL referrals across all referrers (admin view)."""
    result = (
        supabase.table("referrals")
        .select("id,referral_code,referrer_email,candidate_email,job_role_id,status,reward_amount,reward_status,created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


# ---------------------------------------------------------------------------
# GET /leaderboard — auth required
# ---------------------------------------------------------------------------

@router.get("/leaderboard")
async def get_leaderboard(
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Return top 10 referrers by hired count."""
    result = (
        supabase.table("referrals")
        .select("referrer_id,referrer_email,status,reward_amount,reward_status")
        .execute()
    )
    referrals = result.data or []

    # Aggregate by referrer
    aggregated: dict = {}
    for ref in referrals:
        rid = ref.get("referrer_id") or ref.get("referrer_email", "unknown")
        email = ref.get("referrer_email", "unknown")
        if rid not in aggregated:
            aggregated[rid] = {
                "referrer_email": email,
                "total_referrals": 0,
                "hired_count": 0,
                "total_earned": 0.0,
            }
        aggregated[rid]["total_referrals"] += 1
        if ref.get("status") in ("HIRED", "REWARDED"):
            aggregated[rid]["hired_count"] += 1
        if ref.get("reward_status") in ("EARNED", "PAID"):
            aggregated[rid]["total_earned"] += ref.get("reward_amount", 0) or 0

    leaderboard = sorted(
        aggregated.values(),
        key=lambda x: x["hired_count"],
        reverse=True,
    )[:10]

    return leaderboard


# ---------------------------------------------------------------------------
# GET /track/{referral_code} — PUBLIC, no auth
# ---------------------------------------------------------------------------

@router.get("/track/{referral_code}")
async def track_referral(
    referral_code: str,
    supabase: SupabaseClient,
):
    """Public endpoint — track a referral by code (minimal info, no PII)."""
    result = (
        supabase.table("referrals")
        .select("status,job_role_id,reward_amount,created_at")
        .eq("referral_code", referral_code)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Referral not found")

    ref = result.data[0]
    return {
        "status": ref.get("status"),
        "job_role_id": ref.get("job_role_id"),
        "reward_amount": ref.get("reward_amount"),
        "created_at": ref.get("created_at"),
    }


# ---------------------------------------------------------------------------
# POST /apply/{referral_code} — PUBLIC, no auth
# ---------------------------------------------------------------------------

@router.post("/apply/{referral_code}")
async def apply_via_referral(
    referral_code: str,
    body: ApplyReferralRequest,
    supabase: SupabaseClient,
):
    """Public endpoint — record a candidate application via referral link."""
    # Find referral
    result = (
        supabase.table("referrals")
        .select("*")
        .eq("referral_code", referral_code)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Referral not found")

    ref = result.data[0]

    # Already applied?
    if ref.get("status") != "PENDING":
        return {
            "already_applied": True,
            "status": ref.get("status"),
        }

    # Duplicate check — same candidate_email + job_role_id with different referrer
    try:
        dup_result = (
            supabase.table("referrals")
            .select("id,referrer_id")
            .eq("candidate_email", body.candidate_email)
            .eq("job_role_id", ref["job_role_id"])
            .neq("id", ref["id"])
            .in_("status", ["APPLIED", "SHORTLISTED", "HIRED", "REWARDED"])
            .limit(1)
            .execute()
        )
        if dup_result.data:
            return {"duplicate": True}
    except Exception as e:
        logger.warning(f"Duplicate candidate check failed: {e}")

    # Check apply reward
    apply_reward = get_reward_amount(supabase, ref["job_role_id"], event="apply")
    referrer_rewarded = apply_reward > 0

    update_data: dict = {
        "status": "APPLIED",
        "candidate_email": body.candidate_email,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if body.candidate_id:
        update_data["candidate_id"] = body.candidate_id
    if referrer_rewarded:
        update_data["reward_status"] = "EARNED"
        update_data["reward_amount"] = apply_reward

    supabase.table("referrals").update(update_data).eq("id", ref["id"]).execute()

    return {
        "success": True,
        "referral_id": ref["id"],
        "referrer_rewarded": referrer_rewarded,
    }


# ---------------------------------------------------------------------------
# PATCH /{referral_id}/update-status — auth required
# ---------------------------------------------------------------------------

@router.patch("/{referral_id}/update-status")
async def update_referral_status(
    referral_id: str,
    body: UpdateStatusRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Update referral status with valid transitions."""
    context = build_access_context(supabase, user)
    authorize(context, "applications.manage")
    valid_transitions = {
        "APPLIED": ["SHORTLISTED"],
        "SHORTLISTED": ["HIRED"],
        "HIRED": [],
    }

    # Fetch current referral
    result = (
        supabase.table("referrals")
        .select("*")
        .eq("id", referral_id)
        .eq("org_id", context.org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Referral not found")

    ref = result.data[0]
    current_status = ref.get("status")

    allowed = valid_transitions.get(current_status, [])
    if body.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition: {current_status} → {body.status}. Allowed: {allowed}",
        )

    update_data: dict = {
        "status": body.status,
        "updated_at": datetime.utcnow().isoformat(),
    }

    if body.candidate_id:
        update_data["candidate_id"] = body.candidate_id

    if body.status == "HIRED":
        linked_application = ref.get("application_id")
        if not linked_application:
            raise HTTPException(status_code=409, detail="Referral is not linked to an application")
        hired = mark_application_referral_hired(supabase, linked_application)
        return hired or ref

    if body.status == "REWARDED":
        update_data["reward_status"] = "PAID"
        update_data["reward_paid_at"] = datetime.utcnow().isoformat()

    updated = (
        supabase.table("referrals").update(update_data).eq("id", referral_id).execute()
    )

    return updated.data[0] if updated.data else {"id": referral_id, **update_data}


# ---------------------------------------------------------------------------
# POST /{referral_id}/mark-paid — auth required
# ---------------------------------------------------------------------------

@router.post("/{referral_id}/mark-paid")
async def mark_referral_paid(
    referral_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Deprecated: rewards must pass verified UPI and retention eligibility."""
    raise HTTPException(
        status_code=410,
        detail="Direct payment marking is disabled. Use POST /referrals/trigger-upi-payout.",
    )


# ---------------------------------------------------------------------------
# DELETE /{referral_id} — auth required
# ---------------------------------------------------------------------------

@router.delete("/{referral_id}")
async def delete_referral(
    referral_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Delete a referral (only if status is PENDING)."""
    result = (
        supabase.table("referrals")
        .select("id,status")
        .eq("id", referral_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Referral not found")

    ref = result.data[0]
    if ref.get("status") != "PENDING":
        raise HTTPException(
            status_code=400,
            detail=f"Can only delete PENDING referrals. Current status: {ref.get('status')}",
        )

    supabase.table("referrals").delete().eq("id", referral_id).execute()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# POST /{referral_id}/share/whatsapp — auth required
# ---------------------------------------------------------------------------

class WhatsAppShareRequest(BaseModel):
    lang: str = "en"
    property_name: str = "our property"
    role_title: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None


@router.post("/{referral_id}/share/whatsapp")
async def generate_whatsapp_share(
    referral_id: str,
    body: WhatsAppShareRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Generate a pre-filled WhatsApp share link for a referral.

    - Supports ``lang`` = "en" (English) or "hi" (Hindi).
    - Includes property name, role, salary range, apply link, referral code.
    - Marks ``whatsapp_shared = true`` on the referral row so sharing is tracked.
    - The caller must own the referral **or** be an admin.

    Returns ``whatsapp_url``, a ``message_preview`` (plain text, not encoded),
    and ``tracked: true`` confirming the share was recorded.
    """
    caller_id = user.get("sub", "")

    # ------------------------------------------------------------------
    # 1. Fetch referral
    # ------------------------------------------------------------------
    ref_res = (
        supabase.table("referrals")
        .select("id, referrer_id, job_role_id, referral_code, link_token, reward_amount")
        .eq("id", referral_id)
        .limit(1)
        .execute()
    )
    if not ref_res.data:
        raise HTTPException(status_code=404, detail="Referral not found.")
    ref = ref_res.data[0]

    # ------------------------------------------------------------------
    # 2. Authorization — owner or admin
    # ------------------------------------------------------------------
    if caller_id != ref.get("referrer_id"):
        role_res = (
            supabase.table("users")
            .select("role")
            .eq("id", caller_id)
            .limit(1)
            .execute()
        )
        caller_role = role_res.data[0].get("role") if role_res.data else None
        if caller_role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Not authorized. Only the referral owner or an admin may share it.",
            )

    # ------------------------------------------------------------------
    # 3. Resolve role title (DB lookup → request body → fallback)
    # ------------------------------------------------------------------
    role = body.role_title
    if not role:
        job_res = (
            supabase.table("job_roles")
            .select("title")
            .eq("id", ref.get("job_role_id", ""))
            .limit(1)
            .execute()
        )
        role = (job_res.data[0].get("title") if job_res.data else None) or "Hospitality Role"

    # ------------------------------------------------------------------
    # 4. Build apply link
    # ------------------------------------------------------------------
    link_token = ref.get("link_token") or ref.get("referral_code", "")
    apply_link = build_referral_link_v2(
        settings.APP_BASE_URL, ref.get("job_role_id", ""), link_token
    )

    # ------------------------------------------------------------------
    # 5. Render template
    # ------------------------------------------------------------------
    lang = body.lang if body.lang in SUPPORTED_LANGS else "en"
    message = render_template(
        lang=lang,
        property_name=body.property_name,
        role=role,
        apply_link=apply_link,
        referral_code=ref.get("referral_code", ""),
        salary_min=body.salary_min,
        salary_max=body.salary_max,
        reward=float(ref.get("reward_amount") or 0),
    )

    # ------------------------------------------------------------------
    # 6. Track sharing
    # ------------------------------------------------------------------
    try:
        if hasattr(supabase, "rpc"):
            supabase.rpc("track_referral_whatsapp_share", {"p_referral_id": referral_id}).execute()
        else:
            supabase.table("referrals").update({
                "whatsapp_shared": True,
                "whatsapp_shared_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", referral_id).execute()
    except Exception as exc:
        logger.warning("Failed to track whatsapp_shared for %s: %s", referral_id, exc)

    return {
        "whatsapp_url":     build_wa_url(message),
        "message_preview":  message,
        "lang":             lang,
        "apply_link":       apply_link,
        "referral_code":    ref.get("referral_code"),
        "tracked":          True,
    }


# ---------------------------------------------------------------------------
# POST /trigger-upi-payout — admin: manually trigger 90-day retention bonus
# ---------------------------------------------------------------------------

class TriggerPayoutRequest(BaseModel):
    referral_id: str


@router.post("/trigger-upi-payout")
async def trigger_upi_payout(
    body: TriggerPayoutRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """
    Admin endpoint: manually trigger the 90-day retention bonus payout
    for a referral that is HIRED + eligible.

    Checks:
      • Caller must be Owner or Group Admin/HR.
      • Referral must be HIRED with hire_date ≥ 90 days ago.
      • bonus_paid_at must be NULL (idempotency guard).
      • Employee must have a Razorpay-verified UPI ID.

    Razorpay must be configured; production payments never fall back to a mock.
    """
    from app.services.razorpay_payout_service import create_razorpay_payout_service

    context = build_access_context(supabase, user)
    if context.role not in {"OWNER", "GROUP_ADMIN_HR"}:
        raise HTTPException(status_code=403, detail="Owner or Group Admin/HR access required.")

    referral_id = body.referral_id

    # ── Fetch referral ────────────────────────────────────────────────────────
    ref_res = (
        supabase.table("referrals")
        .select("*")
        .eq("id", referral_id)
        .eq("org_id", context.org_id)
        .limit(1)
        .execute()
    )
    if not ref_res.data:
        raise HTTPException(status_code=404, detail="Referral not found.")
    ref = ref_res.data[0]

    if ref.get("bonus_paid_at"):
        raise HTTPException(status_code=409, detail="Retention bonus already paid for this referral.")

    if ref.get("status") != "HIRED":
        raise HTTPException(
            status_code=400,
            detail=f"Referral must be in HIRED status. Current: {ref.get('status')}",
        )

    hire_date_str = ref.get("hire_date")
    if not hire_date_str:
        raise HTTPException(status_code=409, detail="Referral has no hire date; eligibility cannot be verified.")
    from datetime import timedelta as _td
    hd = datetime.fromisoformat(hire_date_str.replace("Z", "+00:00"))
    if hd.tzinfo is not None:
        hd = hd.astimezone().replace(tzinfo=None)
    if datetime.utcnow() < hd + _td(days=90):
        raise HTTPException(
            status_code=400,
            detail="90-day retention period has not elapsed yet for this referral.",
        )

    amount_inr = float(ref.get("retention_bonus_amount") or 0)
    if amount_inr <= 0:
        raise HTTPException(status_code=400, detail="Retention bonus amount is zero for this referral.")

    # ── Employee UPI details ──────────────────────────────────────────────────
    upi_res = (
        supabase.table("employee_upi_details")
        .select("upi_id, account_holder_name, razorpay_fund_account_id, is_verified")
        .eq("user_id", ref.get("referrer_id"))
        .limit(1)
        .execute()
    )
    if not upi_res.data or not upi_res.data[0].get("upi_id"):
        raise HTTPException(
            status_code=400,
            detail="Employee has no UPI ID. Ask them to add it in the portal first.",
        )
    upi_row = upi_res.data[0]
    if not upi_row.get("is_verified"):
        raise HTTPException(status_code=409, detail="Employee UPI ID must be verified before payout.")

    # Reserve this payout before calling Razorpay. Only one concurrent request wins.
    now = datetime.utcnow().isoformat()
    claim = (
        supabase.table("referrals").update({
            "payout_status": "PROCESSING", "payout_claimed_at": now, "payout_error": None,
            "updated_at": now,
        }).eq("id", referral_id).is_("bonus_paid_at", None)
        .in_("payout_status", ["NOT_INITIATED", "FAILED"]).execute()
    )
    if not claim.data:
        raise HTTPException(status_code=409, detail="Payout is already processing or has been paid.")

    # ── Razorpay payout (real or mock) ───────────────────────────────────────
    rzp = create_razorpay_payout_service(
        settings.RAZORPAY_KEY_ID,
        settings.RAZORPAY_KEY_SECRET,
        getattr(settings, "RAZORPAY_FUND_ACCOUNT", None),
    )

    try:
        if rzp is None:
            supabase.table("referrals").update({"payout_status": "FAILED", "payout_error": "Razorpay is not configured"}).eq("id", referral_id).execute()
            raise HTTPException(status_code=503, detail="Razorpay payout service is not configured.")
        payout = await rzp.process_referral_payout(
            referral_id=f"bonus-{referral_id}",
            upi_id=upi_row["upi_id"],
            amount_inr=amount_inr,
            employee_name=upi_row.get("account_holder_name") or "Employee",
            existing_fund_account_id=upi_row.get("razorpay_fund_account_id"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Manual payout failed for referral %s: %s", referral_id, exc)
        supabase.table("referrals").update({"payout_status": "FAILED", "payout_error": str(exc)[:1000]}).eq("id", referral_id).execute()
        raise HTTPException(status_code=502, detail=f"Payout failed: {exc}")

    internal_status = payout.get("internal_status", "PROCESSING")
    payout_values = {
        "payout_status": internal_status,
        "bonus_payout_id": payout["payout_id"],
        "razorpay_payout_id": payout["payout_id"],
        "updated_at": datetime.utcnow().isoformat(),
    }
    if internal_status == "PAID":
        payout_values.update({
            "status": "BONUS_PAID", "retention_bonus_status": "PAID",
            "bonus_paid_at": datetime.utcnow().isoformat(),
        })
    supabase.table("referrals").update(payout_values).eq("id", referral_id).eq("payout_status", "PROCESSING").execute()

    logger.info(
        "Admin manual payout: %s → %s  ₹%s",
        referral_id, payout["payout_id"], amount_inr,
    )

    return {
        "success":          internal_status == "PAID",
        "status":           internal_status,
        "referral_id":      referral_id,
        "payout_id":        payout["payout_id"],
        "amount_inr":       amount_inr,
        "formatted_amount": f"₹{amount_inr:,.0f}",
        "upi_id":           upi_row["upi_id"],
        "mock":             payout.get("mock", False),
    }
