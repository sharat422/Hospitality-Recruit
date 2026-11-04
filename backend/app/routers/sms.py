"""
SMS & conversational recruiting routes (Module 4).
Pain #2: Mobile-first, SMS-first. Twilio webhooks → FastAPI.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.security import get_current_user
from app.core.config import settings
from twilio.request_validator import RequestValidator
from app.core.dependencies import SupabaseClient
from app.services.sms_service import SMSService, ConversationalService
from app.repositories.candidate_repo import CandidateRepository
from typing import Optional

router = APIRouter()


@router.post("/webhook/twilio")
async def handle_twilio_webhook(
    request: Request,
    supabase: SupabaseClient,
):
    """
    Twilio inbound SMS webhook (Pain #2: SMS-first recruiting).
    Validates signature, processes message, generates AI response.
    """
    form = await request.form()
    signature = request.headers.get("X-Twilio-Signature", "")
    webhook_url = settings.API_PUBLIC_BASE_URL.rstrip('/') + request.url.path
    if request.url.query:
        webhook_url += '?' + request.url.query
    if not signature or not RequestValidator(settings.TWILIO_AUTH_TOKEN).validate(webhook_url, dict(form), signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    from_number = form.get("From")
    body = form.get("Body")
    twilio_sid = form.get("MessageSid")
    
    if not (from_number and body and twilio_sid):
        raise HTTPException(status_code=400, detail="Invalid Twilio webhook")
    
    # Process SMS
    sms_service = SMSService()
    result = await sms_service.handle_inbound_sms(from_number, body, twilio_sid)
    
    # Send AI response
    await sms_service.send_sms(from_number, result["ai_reply"])
    
    # TODO: Update candidate profile with extracted data
    # TODO: Log conversation turn
    
    return {"status": "ok", "intent": result["intent"]}


@router.post("/send")
async def send_sms(
    to_number: str,
    message: str,
    user: dict = Depends(get_current_user),
):
    """
    Send SMS to candidate (Pain #2).
    Requires auth if sending from specific campaign.
    """
    sms_service = SMSService()
    
    try:
        sid = await sms_service.send_sms(to_number, message)
        return {"status": "sent", "twilio_sid": sid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start-conversation/{candidate_id}")
async def start_recruitment_conversation(
    candidate_id: str,
    job_id: str,
    supabase: SupabaseClient,
    user: dict = Depends(get_current_user),
):
    """
    Initiate multi-turn SMS recruiting (Pain #2).
    Sends first message, sets up conversation state.
    """
    candidate_repo = CandidateRepository(supabase)
    candidate = await candidate_repo.get_candidate(candidate_id, user.get("sub") if user else None)
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    sms_service = SMSService()
    conv_service = ConversationalService(sms_service)
    
    sid = await conv_service.start_recruitment_conversation(candidate["phone"], job_id)
    
    return {
        "status": "started",
        "candidate_id": candidate_id,
        "twilio_sid": sid,
    }


@router.get("/conversation/{candidate_id}")
async def get_conversation_history(
    candidate_id: str,
    supabase: SupabaseClient,
    user: dict = Depends(get_current_user),
):
    """
    Get SMS conversation history with candidate (Pain #2).
    Returns all turns in recruiting conversation.
    """
    # TODO: Query conversation_turns table
    return {
        "candidate_id": candidate_id,
        "turns": [],
    }
