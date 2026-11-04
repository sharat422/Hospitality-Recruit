"""
SMS & Conversational recruiting service (Module 4).
Pain #2: Mobile-first, SMS-first engagement.
Twilio webhooks → FastAPI → AI conversation.
"""

from twilio.rest import Client as TwilioClient
from anthropic import Anthropic
from app.core.config import settings
from typing import Optional
import json


class SMSService:
    """Handle inbound/outbound SMS via Twilio."""

    def __init__(self):
        self.twilio_client = TwilioClient(
            settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
        )
        self.anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def send_sms(self, to_number: str, message: str) -> str:
        """Send SMS to candidate (Pain #2: mobile-first)."""
        msg = self.twilio_client.messages.create(
            body=message,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=to_number,
        )
        return msg.sid

    async def handle_inbound_sms(
        self, from_number: str, body: str, twilio_sid: str
    ) -> dict:
        """
        Process inbound SMS from candidate.
        Parse intent, extract data, generate AI response (Pain #2).
        """
        # Use AI to understand intent + extract data
        intent_response = await self._analyze_sms_intent(body)

        # Build response
        ai_reply = await self._generate_sms_response(body, intent_response)

        return {
            "from": from_number,
            "intent": intent_response.get("intent", "unknown"),
            "extracted_data": intent_response.get("data", {}),
            "ai_reply": ai_reply,
            "twilio_sid": twilio_sid,
        }

    async def _analyze_sms_intent(self, message: str) -> dict:
        """
        Use Claude to analyze SMS intent + extract structured data (Pain #2).
        Intents: apply, availability, questions, decline.
        """
        prompt = f"""
Analyze this SMS from a job candidate. Extract intent and any structured data.

SMS: "{message}"

Return JSON:
{{
  "intent": <"apply", "availability", "questions", "decline", or "other">,
  "data": {{
    <extracted fields like availability_start, location, etc>
  }},
  "confidence": <0-1>
}}
"""
        response = self.anthropic_client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            result_text = response.content[0].text
            if "```json" in result_text:
                json_str = result_text.split("```json")[1].split("```")[0].strip()
            else:
                json_str = result_text
            return json.loads(json_str)
        except:
            return {"intent": "unknown", "data": {}}

    async def _generate_sms_response(
        self, inbound_message: str, intent_analysis: dict
    ) -> str:
        """Generate appropriate SMS reply (Pain #2: conversational recruiting)."""
        intent = intent_analysis.get("intent", "unknown")

        prompts = {
            "apply": "Acknowledge interest, ask availability in 1-2 sentences.",
            "availability": "Confirm availability info received, ask next question.",
            "questions": "Answer briefly, ask to confirm interest, max 160 chars.",
            "decline": "Thank them, give option to reapply later.",
            "other": "Ask clarifying question, max 160 chars.",
        }

        prompt = f"""
Respond to candidate via SMS. {prompts.get(intent, prompts["other"])}
Keep under 160 characters for best delivery.
Original message: "{inbound_message}"
"""
        response = self.anthropic_client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text.strip()


class ConversationalService:
    """Multi-turn SMS conversation state management."""

    def __init__(self, sms_service: SMSService):
        self.sms_service = sms_service

    async def start_recruitment_conversation(
        self, candidate_phone: str, job_id: str
    ) -> str:
        """
        Initiate multi-turn SMS recruiting flow (Pain #2).
        Send first message: job description, quick qualification questions.
        """
        initial_message = f"""Hi! We have an exciting hospitality position available. 
Are you interested in hearing more? Reply YES or NO."""

        sid = await self.sms_service.send_sms(candidate_phone, initial_message)
        return sid
