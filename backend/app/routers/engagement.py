"""
Engagement Router — Anti-Ghosting, Interview Scheduling, NPS, Messaging, Drip Sequences.
Feature 02: Anti-Ghosting & Candidate Engagement System.
Sub-features 4 (Ghosting Risk), 5 (Interview + NPS), 6 (Drip + Messaging).
"""

from fastapi import APIRouter, HTTPException, Query, Form, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional, List, Annotated
from datetime import datetime, timedelta
import uuid
import anthropic
import logging

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.core.config import settings
from app.services.ghosting_risk_service import calculate_ghosting_risk
from app.services.twilio_service import twilio_service
from app.services.nps_service import calculate_nps, cluster_feedback_themes

CurrentUser = Annotated[dict, Depends(get_current_user)]

router = APIRouter(tags=["Engagement"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SlotItem(BaseModel):
    start_time: str
    end_time: str


class CreateSlotsRequest(BaseModel):
    job_role_id: str
    slots: List[SlotItem]


class InviteRequest(BaseModel):
    candidate_id: str
    slot_id: str
    phone: str


class ConfirmActionRequest(BaseModel):
    action: str  # "confirm" | "reschedule"
    message: Optional[str] = None


class OutreachRequest(BaseModel):
    job_role_id: str
    phone: str


class NpsSendRequest(BaseModel):
    candidate_id: str
    job_role_id: str
    stage: str


class NpsRespondRequest(BaseModel):
    score: int
    feedback: Optional[str] = None


class SendMessageRequest(BaseModel):
    candidate_id: str
    channel: str = "SMS"
    body: str
    job_role_id: Optional[str] = None


class DripStepRequest(BaseModel):
    step_order: int
    delay_hours: int
    channel: str = "SMS"
    message_template: str
    is_ai_personalized: bool = False


class CreateSequenceRequest(BaseModel):
    name: str
    trigger_event: str
    steps: List[DripStepRequest]


class EnrollRequest(BaseModel):
    candidate_id: str
    job_role_id: str
    sequence_id: str


# ---------------------------------------------------------------------------
# GHOSTING RISK ENDPOINTS
# ---------------------------------------------------------------------------

@router.get("/ghosting-risk")
async def list_ghosting_risks(
    supabase: SupabaseClient,
    user: CurrentUser,
    min_level: Optional[str] = Query(None, description="LOW|MEDIUM|HIGH|CRITICAL"),
):
    """Fetch candidates at risk of ghosting, calculate and return risk scores."""
    # Fetch active candidates
    query = (
        supabase.table("candidates")
        .select("*")
        .in_("pipeline_stage", ["SHORTLISTED", "INTERVIEW_SCHEDULED", "OFFER_SENT"])
    )
    candidates_resp = query.execute()
    candidates = candidates_resp.data or []

    results = []
    for candidate in candidates:
        cid = candidate["id"]

        # Fetch messages for this candidate
        conv_resp = (
            supabase.table("conversations")
            .select("id")
            .eq("candidate_id", cid)
            .execute()
        )
        conv_ids = [c["id"] for c in (conv_resp.data or [])]

        messages = []
        if conv_ids:
            msg_resp = (
                supabase.table("messages")
                .select("*")
                .in_("conversation_id", conv_ids)
                .execute()
            )
            messages = msg_resp.data or []

        # Fetch interview slot
        slot_resp = (
            supabase.table("interview_slots")
            .select("*")
            .eq("candidate_id", cid)
            .limit(1)
            .execute()
        )
        interview_slot = slot_resp.data[0] if slot_resp.data else None

        risk = calculate_ghosting_risk(candidate, messages, interview_slot)

        # Apply level filter
        level_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        if min_level and level_order.get(risk["risk_level"], 0) < level_order.get(min_level, 0):
            continue

        # Upsert to ghosting_risk_scores
        job_role_id = candidate.get("job_role_id") or candidate.get("applied_job_id")
        if job_role_id:
            try:
                supabase.table("ghosting_risk_scores").upsert(
                    {
                        "candidate_id": cid,
                        "job_role_id": job_role_id,
                        "risk_score": risk["risk_score"],
                        "risk_level": risk["risk_level"],
                        "risk_signals": risk["risk_signals"],
                        "last_calculated_at": datetime.utcnow().isoformat(),
                    },
                    on_conflict="candidate_id,job_role_id",
                ).execute()
            except Exception as e:
                logger.warning(f"Upsert ghosting risk failed: {e}")

        # Get job role title
        role_title = None
        if job_role_id:
            try:
                role_resp = (
                    supabase.table("job_roles")
                    .select("title")
                    .eq("id", job_role_id)
                    .single()
                    .execute()
                )
                role_title = role_resp.data.get("title") if role_resp.data else None
            except Exception:
                pass

        # Last message date
        last_msg_date = None
        if messages:
            last_msg = max(messages, key=lambda m: m.get("sent_at", ""))
            last_msg_date = last_msg.get("sent_at")

        results.append(
            {
                "candidate_id": cid,
                "name": candidate.get("name") or candidate.get("full_name") or "Unknown",
                "email": candidate.get("email"),
                "phone": candidate.get("phone"),
                "pipeline_stage": candidate.get("pipeline_stage"),
                "role_title": role_title,
                "job_role_id": job_role_id,
                **risk,
                "last_message_date": last_msg_date,
            }
        )

    results.sort(key=lambda r: r["risk_score"], reverse=True)
    return results


@router.post("/ghosting-risk/{candidate_id}/outreach")
async def send_outreach(
    candidate_id: str,
    body: OutreachRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Generate a personalized check-in SMS via Claude and send it."""
    # Fetch candidate
    cand_resp = (
        supabase.table("candidates")
        .select("*")
        .eq("id", candidate_id)
        .single()
        .execute()
    )
    if not cand_resp.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate = cand_resp.data

    # Fetch job role
    role_title = "the position"
    try:
        role_resp = (
            supabase.table("job_roles")
            .select("title")
            .eq("id", body.job_role_id)
            .single()
            .execute()
        )
        if role_resp.data:
            role_title = role_resp.data.get("title", role_title)
    except Exception:
        pass

    candidate_name = candidate.get("name") or candidate.get("full_name") or "there"

    # Generate message with Claude
    try:
        ai_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = ai_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Write a warm, empathetic 160-character SMS check-in for a hospitality recruiter "
                        f"to send to {candidate_name} who applied for {role_title} but hasn't replied. "
                        f"Be casual, friendly, and include a simple question to re-engage. "
                        f"No longer than 160 characters. Return only the message text."
                    ),
                }
            ],
        )
        generated_message = response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Claude generation error: {e}")
        generated_message = (
            f"Hi {candidate_name}! Just checking in about the {role_title} role. "
            f"Still interested? Reply YES or NO — happy to answer any questions!"
        )[:160]

    # Send via Twilio
    sms_result = twilio_service.send_sms(body.phone, generated_message)

    # Save as outbound message
    try:
        conv_resp = (
            supabase.table("conversations")
            .select("id")
            .eq("candidate_id", candidate_id)
            .eq("job_role_id", body.job_role_id)
            .limit(1)
            .execute()
        )
        if conv_resp.data:
            conv_id = conv_resp.data[0]["id"]
        else:
            new_conv = (
                supabase.table("conversations")
                .insert(
                    {
                        "candidate_id": candidate_id,
                        "job_role_id": body.job_role_id,
                        "recruiter_id": user.get("sub"),
                        "channel": "SMS",
                    }
                )
                .execute()
            )
            conv_id = new_conv.data[0]["id"]

        supabase.table("messages").insert(
            {
                "conversation_id": conv_id,
                "sender_type": "RECRUITER",
                "sender_id": user.get("sub"),
                "body": generated_message,
                "channel": "SMS",
                "twilio_sid": sms_result.get("sid"),
                "status": sms_result.get("status", "SENT"),
            }
        ).execute()
    except Exception as e:
        logger.warning(f"Failed to save outreach message: {e}")

    return {"message": generated_message, "sms_result": sms_result}


@router.post("/ghosting-risk/calculate-all")
async def calculate_all_risks(supabase: SupabaseClient, user: CurrentUser):
    """Trigger batch ghosting risk calculation for all active candidates."""
    query = (
        supabase.table("candidates")
        .select("*")
        .in_("pipeline_stage", ["SHORTLISTED", "INTERVIEW_SCHEDULED", "OFFER_SENT"])
    )
    candidates_resp = query.execute()
    candidates = candidates_resp.data or []
    count = 0

    for candidate in candidates:
        cid = candidate["id"]
        job_role_id = candidate.get("job_role_id") or candidate.get("applied_job_id")
        if not job_role_id:
            continue

        conv_resp = (
            supabase.table("conversations")
            .select("id")
            .eq("candidate_id", cid)
            .execute()
        )
        conv_ids = [c["id"] for c in (conv_resp.data or [])]
        messages = []
        if conv_ids:
            msg_resp = (
                supabase.table("messages")
                .select("*")
                .in_("conversation_id", conv_ids)
                .execute()
            )
            messages = msg_resp.data or []

        slot_resp = (
            supabase.table("interview_slots")
            .select("*")
            .eq("candidate_id", cid)
            .limit(1)
            .execute()
        )
        interview_slot = slot_resp.data[0] if slot_resp.data else None

        risk = calculate_ghosting_risk(candidate, messages, interview_slot)
        try:
            supabase.table("ghosting_risk_scores").upsert(
                {
                    "candidate_id": cid,
                    "job_role_id": job_role_id,
                    "risk_score": risk["risk_score"],
                    "risk_level": risk["risk_level"],
                    "risk_signals": risk["risk_signals"],
                    "last_calculated_at": datetime.utcnow().isoformat(),
                },
                on_conflict="candidate_id,job_role_id",
            ).execute()
            count += 1
        except Exception as e:
            logger.warning(f"Upsert failed for candidate {cid}: {e}")

    return {"processed": count, "total_candidates": len(candidates)}


# ---------------------------------------------------------------------------
# INTERVIEW SLOTS ENDPOINTS
# ---------------------------------------------------------------------------

@router.post("/interviews/slots")
async def create_interview_slots(
    body: CreateSlotsRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Create multiple interview slots for a job role."""
    recruiter_id = user.get("sub")
    rows = [
        {
            "job_role_id": body.job_role_id,
            "recruiter_id": recruiter_id,
            "start_time": slot.start_time,
            "end_time": slot.end_time,
            "status": "AVAILABLE",
        }
        for slot in body.slots
    ]
    result = supabase.table("interview_slots").insert(rows).execute()
    slot_ids = [r["id"] for r in (result.data or [])]
    return {"slot_ids": slot_ids, "created": len(slot_ids)}


@router.get("/interviews/slots")
async def list_interview_slots(
    supabase: SupabaseClient,
    user: CurrentUser,
    job_role_id: Optional[str] = None,
    status: Optional[str] = None,
):
    """List interview slots with optional filters."""
    query = supabase.table("interview_slots").select("*")
    if job_role_id:
        query = query.eq("job_role_id", job_role_id)
    if status:
        query = query.eq("status", status)
    result = query.order("start_time").execute()
    slots = result.data or []

    # Enrich with candidate info
    enriched = []
    for slot in slots:
        item = dict(slot)
        if slot.get("candidate_id"):
            try:
                cand = (
                    supabase.table("candidates")
                    .select("name,full_name,email,phone")
                    .eq("id", slot["candidate_id"])
                    .single()
                    .execute()
                )
                item["candidate"] = cand.data
            except Exception:
                item["candidate"] = None
        else:
            item["candidate"] = None
        enriched.append(item)
    return enriched


@router.post("/interviews/invite")
async def send_interview_invite(
    body: InviteRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Assign candidate to slot and send SMS invite with confirmation link."""
    # Update slot
    result = (
        supabase.table("interview_slots")
        .update({"candidate_id": body.candidate_id, "status": "INVITED"})
        .eq("id", body.slot_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Slot not found")
    slot = result.data[0]

    confirmation_token = slot.get("confirmation_token")
    confirm_url = f"{settings.APP_BASE_URL}/schedule/{confirmation_token}"

    # Format time
    start_time = slot.get("start_time", "")
    try:
        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        time_str = dt.strftime("%A %b %d at %I:%M %p")
    except Exception:
        time_str = start_time

    sms_body = (
        f"You've been invited for an interview! "
        f"Please confirm your slot: {time_str}. "
        f"Click to confirm: {confirm_url}"
    )
    sms_result = twilio_service.send_sms(body.phone, sms_body)

    return {"slot": slot, "confirmation_url": confirm_url, "sms_result": sms_result}


@router.get("/interviews/confirm/{token}")
async def get_interview_confirmation(token: str, supabase: SupabaseClient):
    """Public endpoint — return slot details for confirmation page."""
    result = (
        supabase.table("interview_slots")
        .select("*")
        .eq("confirmation_token", token)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Interview slot not found")
    slot = result.data[0]

    # Enrich with candidate, role, recruiter
    enriched = dict(slot)

    if slot.get("candidate_id"):
        try:
            cand = (
                supabase.table("candidates")
                .select("name,full_name,email")
                .eq("id", slot["candidate_id"])
                .single()
                .execute()
            )
            enriched["candidate"] = cand.data
        except Exception:
            enriched["candidate"] = None

    if slot.get("job_role_id"):
        try:
            role = (
                supabase.table("job_roles")
                .select("title,location,description")
                .eq("id", slot["job_role_id"])
                .single()
                .execute()
            )
            enriched["job_role"] = role.data
        except Exception:
            enriched["job_role"] = None

    if slot.get("recruiter_id"):
        try:
            rec = (
                supabase.table("users")
                .select("email,full_name,phone")
                .eq("id", slot["recruiter_id"])
                .single()
                .execute()
            )
            enriched["recruiter"] = rec.data
        except Exception:
            enriched["recruiter"] = None

    return enriched


@router.post("/interviews/confirm/{token}")
async def confirm_interview(
    token: str,
    body: ConfirmActionRequest,
    supabase: SupabaseClient,
):
    """Public endpoint — confirm or reschedule an interview slot."""
    # Fetch slot
    result = (
        supabase.table("interview_slots")
        .select("*")
        .eq("confirmation_token", token)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Interview slot not found")
    slot = result.data[0]

    if body.action == "confirm":
        supabase.table("interview_slots").update(
            {"status": "BOOKED", "updated_at": datetime.utcnow().isoformat()}
        ).eq("id", slot["id"]).execute()

        # Send confirmation SMS if candidate has phone
        if slot.get("candidate_id"):
            try:
                cand = (
                    supabase.table("candidates")
                    .select("phone,name,full_name")
                    .eq("id", slot["candidate_id"])
                    .single()
                    .execute()
                )
                if cand.data and cand.data.get("phone"):
                    name = cand.data.get("name") or cand.data.get("full_name") or "there"
                    start_time = slot.get("start_time", "")
                    try:
                        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                        time_str = dt.strftime("%A %b %d at %I:%M %p")
                    except Exception:
                        time_str = start_time
                    sms_body = (
                        f"Hi {name}! Your interview is confirmed for {time_str}. "
                        f"We look forward to meeting you! Reply HELP if you have questions."
                    )
                    twilio_service.send_sms(cand.data["phone"], sms_body)
            except Exception as e:
                logger.warning(f"Confirmation SMS failed: {e}")

        return {"status": "confirmed", "message": "Interview confirmed successfully!"}

    elif body.action == "reschedule":
        supabase.table("interview_slots").update(
            {"status": "AVAILABLE", "candidate_id": None, "updated_at": datetime.utcnow().isoformat()}
        ).eq("id", slot["id"]).execute()

        # Notify recruiter via SMS if they have a phone
        if slot.get("recruiter_id"):
            try:
                rec = (
                    supabase.table("users")
                    .select("phone,email")
                    .eq("id", slot["recruiter_id"])
                    .single()
                    .execute()
                )
                if rec.data and rec.data.get("phone"):
                    reschedule_msg = body.message or "Candidate requested to reschedule."
                    twilio_service.send_sms(
                        rec.data["phone"],
                        f"Interview reschedule request received. {reschedule_msg} Please offer a new time slot.",
                    )
            except Exception as e:
                logger.warning(f"Recruiter reschedule notification failed: {e}")

        return {"status": "rescheduled", "message": "Reschedule request sent to recruiter."}
    else:
        raise HTTPException(status_code=400, detail="action must be 'confirm' or 'reschedule'")


@router.post("/interviews/reminders")
async def send_interview_reminders(supabase: SupabaseClient, user: CurrentUser):
    """Send 24h and 1h reminders for upcoming interview slots."""
    now = datetime.utcnow()
    count_24h = 0
    count_1h = 0

    # 24h reminders: start_time within next 25 hours, not yet sent
    cutoff_24h = now + timedelta(hours=25)
    slots_24h = (
        supabase.table("interview_slots")
        .select("*")
        .eq("reminder_24h_sent", False)
        .eq("status", "BOOKED")
        .lte("start_time", cutoff_24h.isoformat())
        .gte("start_time", now.isoformat())
        .execute()
    )

    for slot in slots_24h.data or []:
        if slot.get("candidate_id"):
            try:
                cand = (
                    supabase.table("candidates")
                    .select("phone,name,full_name")
                    .eq("id", slot["candidate_id"])
                    .single()
                    .execute()
                )
                if cand.data and cand.data.get("phone"):
                    name = cand.data.get("name") or cand.data.get("full_name") or "there"
                    start_time = slot.get("start_time", "")
                    try:
                        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                        time_str = dt.strftime("%A %b %d at %I:%M %p")
                    except Exception:
                        time_str = start_time
                    twilio_service.send_sms(
                        cand.data["phone"],
                        f"Hi {name}! Reminder: your interview is tomorrow at {time_str}. Reply HELP for questions.",
                    )
                    supabase.table("interview_slots").update(
                        {"reminder_24h_sent": True}
                    ).eq("id", slot["id"]).execute()
                    count_24h += 1
            except Exception as e:
                logger.warning(f"24h reminder failed for slot {slot['id']}: {e}")

    # 1h reminders: start_time within next 65 minutes, not yet sent
    cutoff_1h = now + timedelta(minutes=65)
    slots_1h = (
        supabase.table("interview_slots")
        .select("*")
        .eq("reminder_1h_sent", False)
        .eq("status", "BOOKED")
        .lte("start_time", cutoff_1h.isoformat())
        .gte("start_time", now.isoformat())
        .execute()
    )

    for slot in slots_1h.data or []:
        if slot.get("candidate_id"):
            try:
                cand = (
                    supabase.table("candidates")
                    .select("phone,name,full_name")
                    .eq("id", slot["candidate_id"])
                    .single()
                    .execute()
                )
                if cand.data and cand.data.get("phone"):
                    name = cand.data.get("name") or cand.data.get("full_name") or "there"
                    twilio_service.send_sms(
                        cand.data["phone"],
                        f"Hi {name}! Your interview starts in about 1 hour. See you soon! Reply HELP for questions.",
                    )
                    supabase.table("interview_slots").update(
                        {"reminder_1h_sent": True}
                    ).eq("id", slot["id"]).execute()
                    count_1h += 1
            except Exception as e:
                logger.warning(f"1h reminder failed for slot {slot['id']}: {e}")

    return {"reminders_24h_sent": count_24h, "reminders_1h_sent": count_1h}


# ---------------------------------------------------------------------------
# NPS ENDPOINTS
# ---------------------------------------------------------------------------

@router.post("/nps/send")
async def send_nps_survey(
    body: NpsSendRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Create an NPS survey record and send the survey link via SMS."""
    response_token = str(uuid.uuid4())
    result = (
        supabase.table("nps_surveys")
        .insert(
            {
                "candidate_id": body.candidate_id,
                "job_role_id": body.job_role_id,
                "stage": body.stage,
                "response_token": response_token,
                "sent_at": datetime.utcnow().isoformat(),
            }
        )
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create NPS survey")
    survey = result.data[0]

    # Fetch candidate phone
    try:
        cand = (
            supabase.table("candidates")
            .select("phone,name,full_name")
            .eq("id", body.candidate_id)
            .single()
            .execute()
        )
        if cand.data and cand.data.get("phone"):
            name = cand.data.get("name") or cand.data.get("full_name") or "there"
            survey_url = f"{settings.APP_BASE_URL}/nps/{response_token}"
            sms_body = (
                f"Hi {name}! How was your experience with us? "
                f"Please rate us 0-10: {survey_url}"
            )
            twilio_service.send_sms(cand.data["phone"], sms_body)
    except Exception as e:
        logger.warning(f"NPS SMS send failed: {e}")

    return {"survey_id": survey["id"], "response_token": response_token}


@router.post("/nps/respond/{token}")
async def respond_to_nps(
    token: str,
    body: NpsRespondRequest,
    supabase: SupabaseClient,
):
    """Public endpoint — record NPS survey response."""
    if not (0 <= body.score <= 10):
        raise HTTPException(status_code=400, detail="Score must be between 0 and 10")

    result = (
        supabase.table("nps_surveys")
        .update(
            {
                "score": body.score,
                "feedback_text": body.feedback,
                "responded_at": datetime.utcnow().isoformat(),
            }
        )
        .eq("response_token", token)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Survey not found")

    if body.score >= 9:
        message = "Thank you for the great rating! We're glad you had a positive experience."
    elif body.score >= 7:
        message = "Thank you for your feedback! We appreciate your input."
    else:
        message = "Thank you for your honest feedback. We're sorry about your experience and will work to improve."

    return {"status": "recorded", "message": message}


@router.get("/nps/analytics")
async def get_nps_analytics(
    supabase: SupabaseClient,
    user: CurrentUser,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Return NPS analytics: overall score, by-stage breakdown, weekly trend."""
    query = (
        supabase.table("nps_surveys")
        .select("*")
        .not_.is_("responded_at", "null")
    )
    if date_from:
        query = query.gte("responded_at", date_from)
    if date_to:
        query = query.lte("responded_at", date_to)

    result = query.execute()
    surveys = result.data or []

    all_scores = [s["score"] for s in surveys if s.get("score") is not None]
    overall_nps = calculate_nps(all_scores)

    # By stage
    stages = {}
    for s in surveys:
        stage = s.get("stage", "UNKNOWN")
        if stage not in stages:
            stages[stage] = []
        if s.get("score") is not None:
            stages[stage].append(s["score"])

    by_stage = []
    for stage, scores in stages.items():
        by_stage.append(
            {
                "stage": stage,
                "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
                "count": len(scores),
                "nps": calculate_nps(scores),
            }
        )

    # Total sent this month
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sent_this_month_resp = (
        supabase.table("nps_surveys")
        .select("id", count="exact")
        .gte("sent_at", month_start.isoformat())
        .execute()
    )
    sent_this_month = sent_this_month_resp.count or 0

    # Response rate
    total_sent_resp = supabase.table("nps_surveys").select("id", count="exact").execute()
    total_sent = total_sent_resp.count or 0
    total_responded = len([s for s in surveys if s.get("responded_at")])
    response_rate = round((total_responded / total_sent * 100), 1) if total_sent > 0 else 0

    # Weekly trend: last 12 weeks
    weekly_trend = []
    for week in range(11, -1, -1):
        week_start = now - timedelta(weeks=week + 1)
        week_end = now - timedelta(weeks=week)
        week_scores = [
            s["score"]
            for s in surveys
            if s.get("score") is not None and s.get("responded_at")
            and week_start.isoformat() <= s["responded_at"] <= week_end.isoformat()
        ]
        weekly_trend.append(
            {
                "week": week_start.strftime("W%W %Y"),
                "nps": calculate_nps(week_scores),
                "count": len(week_scores),
            }
        )

    # Recent verbatim feedback
    recent_feedback = [
        {
            "stage": s.get("stage"),
            "score": s.get("score"),
            "feedback": s.get("feedback_text"),
            "responded_at": s.get("responded_at"),
        }
        for s in sorted(surveys, key=lambda x: x.get("responded_at", ""), reverse=True)[:20]
        if s.get("feedback_text")
    ]

    return {
        "overall_nps": overall_nps,
        "response_rate": response_rate,
        "sent_this_month": sent_this_month,
        "total_responded": total_responded,
        "by_stage": by_stage,
        "weekly_trend": weekly_trend,
        "recent_feedback": recent_feedback,
    }


@router.get("/nps/themes")
async def get_nps_themes(
    supabase: SupabaseClient,
    user: CurrentUser,
    stage: str = Query("POST_INTERVIEW"),
):
    """Cluster NPS feedback into themes using Claude AI."""
    result = (
        supabase.table("nps_surveys")
        .select("feedback_text")
        .eq("stage", stage)
        .not_.is_("feedback_text", "null")
        .execute()
    )
    feedback_list = [
        s["feedback_text"] for s in (result.data or []) if s.get("feedback_text")
    ]
    themes = await cluster_feedback_themes(feedback_list, stage)
    return {"stage": stage, "themes": themes, "feedback_count": len(feedback_list)}


# ---------------------------------------------------------------------------
# MESSAGING ENDPOINTS
# ---------------------------------------------------------------------------

@router.post("/messages/send")
async def send_message(
    body: SendMessageRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Send a message to a candidate via SMS/WhatsApp and save to conversation."""
    recruiter_id = user.get("sub")

    # Fetch candidate phone
    cand_resp = (
        supabase.table("candidates")
        .select("phone,name,full_name")
        .eq("id", body.candidate_id)
        .single()
        .execute()
    )
    if not cand_resp.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate = cand_resp.data
    phone = candidate.get("phone")

    # Look up or create conversation
    conv_query = (
        supabase.table("conversations")
        .select("id")
        .eq("candidate_id", body.candidate_id)
    )
    if body.job_role_id:
        conv_query = conv_query.eq("job_role_id", body.job_role_id)
    conv_resp = conv_query.limit(1).execute()

    if conv_resp.data:
        conv_id = conv_resp.data[0]["id"]
    else:
        new_conv = (
            supabase.table("conversations")
            .insert(
                {
                    "candidate_id": body.candidate_id,
                    "job_role_id": body.job_role_id,
                    "recruiter_id": recruiter_id,
                    "channel": body.channel,
                    "status": "ACTIVE",
                }
            )
            .execute()
        )
        conv_id = new_conv.data[0]["id"]

    # Send via Twilio
    sms_result = {"sid": "NO_PHONE", "status": "skipped"}
    if phone:
        sms_result = twilio_service.send_sms(phone, body.body, channel=body.channel.lower())

    # Save message
    msg_resp = (
        supabase.table("messages")
        .insert(
            {
                "conversation_id": conv_id,
                "sender_type": "RECRUITER",
                "sender_id": recruiter_id,
                "body": body.body,
                "channel": body.channel,
                "twilio_sid": sms_result.get("sid"),
                "status": sms_result.get("status", "SENT").upper(),
                "sent_at": datetime.utcnow().isoformat(),
            }
        )
        .execute()
    )

    # Update conversation last_message_at
    supabase.table("conversations").update(
        {"last_message_at": datetime.utcnow().isoformat()}
    ).eq("id", conv_id).execute()

    return msg_resp.data[0] if msg_resp.data else {}


@router.get("/conversations")
async def list_conversations(
    supabase: SupabaseClient,
    user: CurrentUser,
    status: Optional[str] = None,
):
    """Return all conversations with last message preview and candidate name."""
    query = supabase.table("conversations").select("*").order(
        "last_message_at", desc=True
    )
    if status:
        query = query.eq("status", status)
    convs = query.execute().data or []

    enriched = []
    for conv in convs:
        item = dict(conv)

        # Candidate name
        if conv.get("candidate_id"):
            try:
                cand = (
                    supabase.table("candidates")
                    .select("name,full_name,email")
                    .eq("id", conv["candidate_id"])
                    .single()
                    .execute()
                )
                item["candidate"] = cand.data
            except Exception:
                item["candidate"] = None

        # Job role title
        if conv.get("job_role_id"):
            try:
                role = (
                    supabase.table("job_roles")
                    .select("title")
                    .eq("id", conv["job_role_id"])
                    .single()
                    .execute()
                )
                item["job_role"] = role.data
            except Exception:
                item["job_role"] = None

        # Last message + unread count
        msgs_resp = (
            supabase.table("messages")
            .select("*")
            .eq("conversation_id", conv["id"])
            .order("sent_at", desc=True)
            .limit(1)
            .execute()
        )
        last_msg = msgs_resp.data[0] if msgs_resp.data else None
        item["last_message"] = last_msg

        unread_resp = (
            supabase.table("messages")
            .select("id", count="exact")
            .eq("conversation_id", conv["id"])
            .is_("read_at", "null")
            .eq("sender_type", "CANDIDATE")
            .execute()
        )
        item["unread_count"] = unread_resp.count or 0

        enriched.append(item)

    return enriched


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Return all messages in a conversation sorted by sent_at."""
    result = (
        supabase.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("sent_at")
        .execute()
    )
    return result.data or []


@router.post("/conversations/{conversation_id}/mark-read")
async def mark_conversation_read(
    conversation_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Mark all candidate messages in a conversation as read."""
    supabase.table("messages").update(
        {"read_at": datetime.utcnow().isoformat(), "status": "READ"}
    ).eq("conversation_id", conversation_id).eq("sender_type", "CANDIDATE").is_(
        "read_at", "null"
    ).execute()
    return {"status": "ok"}


@router.post("/webhooks/twilio/inbound")
async def twilio_inbound_webhook(
    supabase: SupabaseClient,
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...),
):
    """Public Twilio webhook — process inbound SMS from candidates."""
    phone = From.replace("whatsapp:", "").strip()

    # Find candidate by phone number
    cand_resp = (
        supabase.table("candidates")
        .select("id,name,full_name")
        .eq("phone", phone)
        .limit(1)
        .execute()
    )
    candidate = cand_resp.data[0] if cand_resp.data else None

    if candidate:
        # Find or create conversation
        conv_resp = (
            supabase.table("conversations")
            .select("id")
            .eq("candidate_id", candidate["id"])
            .order("last_message_at", desc=True)
            .limit(1)
            .execute()
        )
        if conv_resp.data:
            conv_id = conv_resp.data[0]["id"]
        else:
            new_conv = (
                supabase.table("conversations")
                .insert(
                    {
                        "candidate_id": candidate["id"],
                        "channel": "SMS",
                        "status": "ACTIVE",
                    }
                )
                .execute()
            )
            conv_id = new_conv.data[0]["id"]

        # Save inbound message
        supabase.table("messages").insert(
            {
                "conversation_id": conv_id,
                "sender_type": "CANDIDATE",
                "sender_id": candidate["id"],
                "body": Body,
                "channel": "SMS",
                "twilio_sid": MessageSid,
                "status": "RECEIVED",
                "sent_at": datetime.utcnow().isoformat(),
            }
        ).execute()

        # Update conversation timestamp
        supabase.table("conversations").update(
            {"last_message_at": datetime.utcnow().isoformat()}
        ).eq("id", conv_id).execute()
    else:
        logger.info(f"Inbound SMS from unknown number: {phone}")

    # Return empty TwiML response
    return PlainTextResponse(content="<Response/>", media_type="application/xml")


# ---------------------------------------------------------------------------
# DRIP SEQUENCE ENDPOINTS
# ---------------------------------------------------------------------------

@router.get("/drip/sequences")
async def list_drip_sequences(supabase: SupabaseClient, user: CurrentUser):
    """List all drip sequences with step counts."""
    seqs = supabase.table("drip_sequences").select("*").order("created_at").execute().data or []
    enriched = []
    for seq in seqs:
        steps_resp = (
            supabase.table("drip_steps")
            .select("id", count="exact")
            .eq("sequence_id", seq["id"])
            .execute()
        )
        item = dict(seq)
        item["step_count"] = steps_resp.count or 0
        enriched.append(item)
    return enriched


@router.post("/drip/sequences")
async def create_drip_sequence(
    body: CreateSequenceRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Create a new drip sequence with its steps."""
    seq_resp = (
        supabase.table("drip_sequences")
        .insert({"name": body.name, "trigger_event": body.trigger_event, "is_active": True})
        .execute()
    )
    if not seq_resp.data:
        raise HTTPException(status_code=500, detail="Failed to create sequence")
    seq = seq_resp.data[0]

    # Insert steps
    steps = [
        {
            "sequence_id": seq["id"],
            "step_order": step.step_order,
            "delay_hours": step.delay_hours,
            "channel": step.channel,
            "message_template": step.message_template,
            "is_ai_personalized": step.is_ai_personalized,
        }
        for step in body.steps
    ]
    if steps:
        supabase.table("drip_steps").insert(steps).execute()

    return {**seq, "steps": steps}


@router.post("/drip/enroll")
async def enroll_in_drip(
    body: EnrollRequest,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Enroll a candidate in a drip sequence."""
    # Get first step to determine next_send_at
    first_step_resp = (
        supabase.table("drip_steps")
        .select("delay_hours")
        .eq("sequence_id", body.sequence_id)
        .order("step_order")
        .limit(1)
        .execute()
    )
    delay_hours = first_step_resp.data[0]["delay_hours"] if first_step_resp.data else 0
    next_send_at = (datetime.utcnow() + timedelta(hours=delay_hours)).isoformat()

    enroll_resp = (
        supabase.table("drip_enrollments")
        .insert(
            {
                "candidate_id": body.candidate_id,
                "job_role_id": body.job_role_id,
                "sequence_id": body.sequence_id,
                "current_step": 0,
                "status": "ACTIVE",
                "enrolled_at": datetime.utcnow().isoformat(),
                "next_send_at": next_send_at,
            }
        )
        .execute()
    )
    if not enroll_resp.data:
        raise HTTPException(status_code=500, detail="Failed to enroll candidate")
    return enroll_resp.data[0]


@router.delete("/drip/enrollments/{enrollment_id}")
async def cancel_drip_enrollment(
    enrollment_id: str,
    supabase: SupabaseClient,
    user: CurrentUser,
):
    """Cancel a drip enrollment."""
    supabase.table("drip_enrollments").update({"status": "CANCELLED"}).eq(
        "id", enrollment_id
    ).execute()
    return {"status": "cancelled"}


@router.post("/drip/process")
async def process_drip_queue(supabase: SupabaseClient, user: CurrentUser):
    """Process due drip enrollments — send messages and advance steps."""
    now = datetime.utcnow()
    enrollments = (
        supabase.table("drip_enrollments")
        .select("*")
        .eq("status", "ACTIVE")
        .lte("next_send_at", now.isoformat())
        .execute()
        .data or []
    )
    processed = 0

    for enrollment in enrollments:
        try:
            seq_id = enrollment["sequence_id"]
            current_step = enrollment["current_step"]

            # Fetch current step
            step_resp = (
                supabase.table("drip_steps")
                .select("*")
                .eq("sequence_id", seq_id)
                .eq("step_order", current_step)
                .limit(1)
                .execute()
            )
            if not step_resp.data:
                # No more steps — mark complete
                supabase.table("drip_enrollments").update({"status": "COMPLETED"}).eq(
                    "id", enrollment["id"]
                ).execute()
                continue

            step = step_resp.data[0]

            # Fetch candidate
            cand_resp = (
                supabase.table("candidates")
                .select("*")
                .eq("id", enrollment["candidate_id"])
                .single()
                .execute()
            )
            if not cand_resp.data:
                continue
            candidate = cand_resp.data

            # Prepare message
            message = step["message_template"]
            name = candidate.get("name") or candidate.get("full_name") or "there"
            message = message.replace("{{name}}", name).replace("{name}", name)

            # AI personalize if requested
            if step.get("is_ai_personalized"):
                try:
                    ai_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
                    ai_resp = ai_client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=100,
                        messages=[
                            {
                                "role": "user",
                                "content": (
                                    f"Personalize this hospitality recruiting message for {name}: "
                                    f'"{message}". Keep under 160 chars. Return only the message.'
                                ),
                            }
                        ],
                    )
                    message = ai_resp.content[0].text.strip()
                except Exception as e:
                    logger.warning(f"AI personalization failed: {e}")

            # Send message
            phone = candidate.get("phone")
            if phone:
                twilio_service.send_sms(phone, message, channel=step.get("channel", "SMS").lower())

            # Fetch next step
            next_step_resp = (
                supabase.table("drip_steps")
                .select("delay_hours,step_order")
                .eq("sequence_id", seq_id)
                .eq("step_order", current_step + 1)
                .limit(1)
                .execute()
            )

            if next_step_resp.data:
                next_delay = next_step_resp.data[0]["delay_hours"]
                next_send_at = (now + timedelta(hours=next_delay)).isoformat()
                supabase.table("drip_enrollments").update(
                    {
                        "current_step": current_step + 1,
                        "next_send_at": next_send_at,
                    }
                ).eq("id", enrollment["id"]).execute()
            else:
                supabase.table("drip_enrollments").update({"status": "COMPLETED"}).eq(
                    "id", enrollment["id"]
                ).execute()

            processed += 1

        except Exception as e:
            logger.error(f"Drip enrollment processing failed for {enrollment['id']}: {e}")

    return {"processed": processed, "total_due": len(enrollments)}


# ---------------------------------------------------------------------------
# CANDIDATE STATUS PORTAL ENDPOINT
# ---------------------------------------------------------------------------

@router.get("/portal/{token}")
async def get_candidate_portal(token: str, supabase: SupabaseClient):
    """Public endpoint — return candidate pipeline status for self-service portal."""
    cand_resp = (
        supabase.table("candidates")
        .select("*")
        .eq("tracking_token", token)
        .limit(1)
        .execute()
    )
    if not cand_resp.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate = cand_resp.data[0]

    result = {
        "name": candidate.get("name") or candidate.get("full_name"),
        "email": candidate.get("email"),
        "pipeline_stage": candidate.get("pipeline_stage", "APPLIED"),
    }

    # Job role info
    job_role_id = candidate.get("job_role_id") or candidate.get("applied_job_id")
    if job_role_id:
        try:
            role_resp = (
                supabase.table("job_roles")
                .select("title,location,description")
                .eq("id", job_role_id)
                .single()
                .execute()
            )
            result["job_role"] = role_resp.data
        except Exception:
            result["job_role"] = None
    else:
        result["job_role"] = None

    # Interview slots
    slot_resp = (
        supabase.table("interview_slots")
        .select("*")
        .eq("candidate_id", candidate["id"])
        .order("start_time")
        .execute()
    )
    slots = slot_resp.data or []

    # Recruiter phone
    recruiter_phone = None
    for slot in slots:
        if slot.get("recruiter_id"):
            try:
                rec = (
                    supabase.table("users")
                    .select("phone,email,full_name")
                    .eq("id", slot["recruiter_id"])
                    .single()
                    .execute()
                )
                if rec.data:
                    recruiter_phone = rec.data.get("phone")
                    result["recruiter"] = rec.data
                    break
            except Exception:
                pass

    result["interview_slots"] = slots
    result["recruiter_phone"] = recruiter_phone

    return result
