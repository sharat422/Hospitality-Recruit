"""
Twilio Service — sends SMS and WhatsApp messages.
Pain Point #2: Mobile-first SMS engagement for hospitality candidates.
"""

import logging
from typing import Optional
from twilio.rest import Client
from app.core.config import settings

logger = logging.getLogger(__name__)


class TwilioService:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            sid = settings.TWILIO_ACCOUNT_SID
            # Only init real client if we have a real SID (not placeholder)
            if sid and not sid.startswith("AC...") and sid != "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx":
                try:
                    self._client = Client(sid, settings.TWILIO_AUTH_TOKEN)
                except Exception as e:
                    logger.warning(f"Twilio client init failed: {e}")
        return self._client

    def send_sms(self, to: str, body: str, channel: str = "sms") -> dict:
        """Send SMS or WhatsApp message. Returns mock response if Twilio not configured."""
        if not self.client:
            logger.warning("Twilio not configured — skipping SMS send (mock mode)")
            return {"sid": "MOCK_SID", "status": "mock"}
        try:
            from_number = settings.TWILIO_PHONE_NUMBER
            if channel == "whatsapp":
                from_number = f"whatsapp:{from_number}"
                to = f"whatsapp:{to}" if not to.startswith("whatsapp:") else to
            msg = self.client.messages.create(body=body, from_=from_number, to=to)
            return {"sid": msg.sid, "status": msg.status}
        except Exception as e:
            logger.error(f"Twilio send error: {e}")
            return {"sid": None, "status": "failed", "error": str(e)}


twilio_service = TwilioService()
