"""
WhatsApp Gateway — provider-agnostic send + inbound parser.

Providers supported:
  meta      — Meta WhatsApp Cloud API (graph.facebook.com)
  interakt  — Interakt BSP (api.interakt.ai)  — popular in India
  twilio    — Twilio WhatsApp (fallback / sandbox)

Provider is selected via WHATSAPP_PROVIDER env var.

Usage:
    from app.services.whatsapp_gateway import WhatsAppGateway, parse_inbound

    gw = WhatsAppGateway()
    gw.send("+919876543210", "Hello!")

    messages = parse_inbound("meta", request_body_dict)
    for msg in messages:
        print(msg.phone, msg.body)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Meta Cloud API base URL and version
_META_API_BASE = "https://graph.facebook.com/v19.0"
# Interakt send endpoint
_INTERAKT_SEND_URL = "https://api.interakt.ai/v1/public/message/"


# ─────────────────────────────────────────────────────────────────────────────
# Parsed inbound message (provider-agnostic)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ParsedMessage:
    phone:           str            # E.164, e.g. "+919876543210"
    body:            str            # raw text (empty string for media-only)
    provider_msg_id: str = ""       # native message ID from the provider
    contact_name:    str = ""       # display name from WhatsApp profile
    media_url:       Optional[str] = None
    media_type:      Optional[str] = None
    is_text:         bool = True
    raw:             dict = field(default_factory=dict)  # original payload


# ─────────────────────────────────────────────────────────────────────────────
# Inbound payload parsers — one per provider
# ─────────────────────────────────────────────────────────────────────────────

def parse_meta_payload(data: dict) -> list[ParsedMessage]:
    """
    Parse a Meta Cloud API webhook payload into ParsedMessage objects.

    Meta sends:
    {
      "object": "whatsapp_business_account",
      "entry": [{
        "changes": [{
          "value": {
            "contacts": [{"profile": {"name": "..."}, "wa_id": "91XXXXXXXXXX"}],
            "messages": [{
              "from": "91XXXXXXXXXX",   ← no leading +
              "id": "wamid.xxx",
              "type": "text",
              "text": {"body": "HELP"}
            }]
          }
        }]
      }]
    }
    """
    results: list[ParsedMessage] = []
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            val = change.get("value", {})
            if change.get("field") != "messages":
                continue

            # Build a name lookup from contacts list
            name_by_wa_id: dict[str, str] = {}
            for contact in val.get("contacts", []):
                wa_id = contact.get("wa_id", "")
                name  = contact.get("profile", {}).get("name", "")
                if wa_id:
                    name_by_wa_id[wa_id] = name

            for msg in val.get("messages", []):
                raw_phone = msg.get("from", "")
                # Meta omits leading + — normalise to E.164
                phone = _normalise_phone(raw_phone)
                msg_type = msg.get("type", "text")

                if msg_type == "text":
                    body     = msg.get("text", {}).get("body", "")
                    is_text  = True
                    media_url = None
                    media_type = None
                elif msg_type in ("image", "document", "audio", "video", "sticker"):
                    body      = msg.get("caption", "")
                    is_text   = False
                    media_info = msg.get(msg_type, {})
                    media_url  = media_info.get("link") or media_info.get("id")
                    media_type = media_info.get("mime_type") or msg_type
                else:
                    # Reaction, location, button reply, etc.
                    body       = ""
                    is_text    = False
                    media_url  = None
                    media_type = None

                results.append(ParsedMessage(
                    phone           = phone,
                    body            = body,
                    provider_msg_id = msg.get("id", ""),
                    contact_name    = name_by_wa_id.get(raw_phone, ""),
                    is_text         = is_text,
                    media_url       = media_url,
                    media_type      = media_type,
                    raw             = msg,
                ))
    return results


def parse_interakt_payload(data: dict) -> list[ParsedMessage]:
    """
    Parse an Interakt webhook payload into ParsedMessage objects.

    Interakt sends (v1.0):
    {
      "type": "incoming_message",
      "payload": {
        "id": "wamid.xxx",
        "type": "text",
        "text": {"body": "HELP"},
        "from": {
          "phone_number": "+919876543210",
          "name": "Priya Sharma"
        },
        "timestamp": "2026-05-20T10:00:00Z"
      }
    }
    Some older Interakt webhooks use a flat structure:
    {
      "type": "text",
      "body": {"text": "HELP"},
      "from": "+919876543210"
    }
    Both forms are handled below.
    """
    results: list[ParsedMessage] = []

    # Normalised wrapper form
    payload = data.get("payload") or data

    msg_type = payload.get("type", "text")
    raw_phone = (
        payload.get("from", {}).get("phone_number")
        if isinstance(payload.get("from"), dict)
        else payload.get("from", "")
    )
    phone = _normalise_phone(str(raw_phone or ""))
    name = (
        payload.get("from", {}).get("name", "")
        if isinstance(payload.get("from"), dict)
        else ""
    )

    if msg_type == "text":
        text_field = payload.get("text") or payload.get("body") or {}
        if isinstance(text_field, dict):
            body = text_field.get("body") or text_field.get("text") or ""
        else:
            body = str(text_field)
        is_text   = True
        media_url = None
        media_type = None
    elif msg_type in ("image", "document", "audio", "video"):
        body       = payload.get("caption", "")
        is_text    = False
        media_url  = payload.get(msg_type, {}).get("link") or payload.get("link")
        media_type = payload.get(msg_type, {}).get("mime_type") or msg_type
    else:
        body       = ""
        is_text    = False
        media_url  = None
        media_type = None

    if phone:
        results.append(ParsedMessage(
            phone           = phone,
            body            = body,
            provider_msg_id = payload.get("id", ""),
            contact_name    = name,
            is_text         = is_text,
            media_url       = media_url,
            media_type      = media_type,
            raw             = data,
        ))
    return results


def parse_inbound(provider: str, data: dict) -> list[ParsedMessage]:
    """Dispatch to the right parser based on provider name."""
    if provider == "meta":
        return parse_meta_payload(data)
    if provider == "interakt":
        return parse_interakt_payload(data)
    # Twilio is handled separately (form-encoded, not JSON)
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Meta webhook signature verification (HMAC-SHA256)
# ─────────────────────────────────────────────────────────────────────────────

def verify_meta_signature(raw_body: bytes, x_hub_signature_256: str, app_secret: str | None = None) -> bool:
    """
    Verify that an inbound Meta webhook POST is authentic.
    Meta sends 'X-Hub-Signature-256: sha256=<hex>' using the App Secret.
    Returns True only for a valid signature with a configured secret.
    """
    app_secret = app_secret or settings.WHATSAPP_APP_SECRET
    if not app_secret:
        logger.error("WHATSAPP_APP_SECRET not set — rejecting webhook")
        return False

    if not x_hub_signature_256.startswith("sha256="):
        return False

    expected = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    received = x_hub_signature_256[len("sha256="):]
    return hmac.compare_digest(expected, received)


# ─────────────────────────────────────────────────────────────────────────────
# WhatsApp Gateway — provider-agnostic outbound sender
# ─────────────────────────────────────────────────────────────────────────────

class WhatsAppGateway:
    """
    Send WhatsApp messages through the configured provider.

    Instantiate once and reuse, or use the module-level `send_whatsapp()`
    helper which reads the provider from settings on every call.
    """

    def __init__(self, provider: Optional[str] = None) -> None:
        self.provider = (provider or settings.WHATSAPP_PROVIDER or "twilio").lower()

    def send(self, to_phone: str, body: str) -> Optional[str]:
        """
        Send a text message.  Returns a provider message ID on success, None on failure.
        to_phone must be E.164 (e.g. "+919876543210").
        """
        to_phone = _normalise_phone(to_phone)
        if self.provider == "meta":
            return self._send_meta(to_phone, body)
        if self.provider == "interakt":
            return self._send_interakt(to_phone, body)
        return self._send_twilio(to_phone, body)

    # ── Meta Cloud API ────────────────────────────────────────────────────────

    def _send_meta(self, to_phone: str, body: str) -> Optional[str]:
        """
        Send via Meta WhatsApp Cloud API.

        POST https://graph.facebook.com/v19.0/{phone_number_id}/messages
        Authorization: Bearer {access_token}
        {
          "messaging_product": "whatsapp",
          "to": "919876543210",       ← no leading +
          "type": "text",
          "text": {"body": "..."}
        }
        """
        access_token    = settings.WHATSAPP_ACCESS_TOKEN
        phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID

        if not access_token or not phone_number_id:
            logger.error("Meta send failed: WHATSAPP_ACCESS_TOKEN or "
                         "WHATSAPP_PHONE_NUMBER_ID not configured")
            return None

        # Meta requires phone without leading +
        to_stripped = to_phone.lstrip("+")

        url     = f"{_META_API_BASE}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to":                to_stripped,
            "type":              "text",
            "text":              {"body": body},
        }

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            msg_id = (data.get("messages") or [{}])[0].get("id")
            logger.info("Meta send OK to %s: %s", to_phone, msg_id)
            return msg_id
        except httpx.HTTPStatusError as exc:
            logger.error("Meta send HTTP %s to %s: %s",
                         exc.response.status_code, to_phone, exc.response.text)
        except Exception as exc:
            logger.error("Meta send failed to %s: %s", to_phone, exc)
        return None

    # ── Interakt ──────────────────────────────────────────────────────────────

    def _send_interakt(self, to_phone: str, body: str) -> Optional[str]:
        """
        Send via Interakt (India BSP).

        POST https://api.interakt.ai/v1/public/message/
        Authorization: Basic base64(api_key)
        {
          "type": "Text",
          "data": {"message": "..."},
          "phoneNumber": "+919876543210",
          "countryCode": "91"
        }
        """
        api_key = settings.INTERAKT_API_KEY
        if not api_key:
            logger.error("Interakt send failed: INTERAKT_API_KEY not configured")
            return None

        # Interakt uses Basic auth with the API key as both user and password (or just key)
        b64_key = base64.b64encode(api_key.encode()).decode()
        headers = {
            "Authorization": f"Basic {b64_key}",
            "Content-Type":  "application/json",
        }

        # Extract country code (default 91 for India)
        country_code = "91"
        if to_phone.startswith("+"):
            digits = to_phone[1:]
            if digits.startswith("91") and len(digits) == 12:
                country_code = "91"
            elif digits.startswith("1") and len(digits) == 11:
                country_code = "1"

        payload = {
            "type":        "Text",
            "data":        {"message": body},
            "phoneNumber": to_phone,
            "countryCode": country_code,
        }

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(_INTERAKT_SEND_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data   = resp.json()
            msg_id = data.get("id") or data.get("messageId") or "interakt-ok"
            logger.info("Interakt send OK to %s: %s", to_phone, msg_id)
            return msg_id
        except httpx.HTTPStatusError as exc:
            logger.error("Interakt send HTTP %s to %s: %s",
                         exc.response.status_code, to_phone, exc.response.text)
        except Exception as exc:
            logger.error("Interakt send failed to %s: %s", to_phone, exc)
        return None

    # ── Twilio (fallback / sandbox) ───────────────────────────────────────────

    def _send_twilio(self, to_phone: str, body: str) -> Optional[str]:
        """Send via Twilio WhatsApp (sandbox or production)."""
        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            to_wa  = f"whatsapp:{to_phone}"
            msg    = client.messages.create(
                body  = body,
                from_ = settings.TWILIO_WHATSAPP_NUMBER,
                to    = to_wa,
            )
            logger.info("Twilio send OK to %s: %s", to_phone, msg.sid)
            return msg.sid
        except Exception as exc:
            logger.error("Twilio send failed to %s: %s", to_phone, exc)
            return None

    # ── Document / media sending ──────────────────────────────────────────────

    def send_document(
        self,
        to_phone:     str,
        document_url: str,
        caption:      str = "",
        filename:     str = "document.pdf",
    ) -> Optional[str]:
        """
        Send a document (PDF, etc.) to a WhatsApp user.
        Returns a provider message ID on success, None on failure.

        WhatsApp must be able to fetch document_url over HTTPS; use a public
        or presigned URL (not a localhost path).
        """
        to_phone = _normalise_phone(to_phone)
        if self.provider == "meta":
            return self._send_document_meta(to_phone, document_url, caption, filename)
        if self.provider == "interakt":
            return self._send_document_interakt(to_phone, document_url, caption, filename)
        return self._send_document_twilio(to_phone, document_url, caption)

    def _send_document_meta(
        self, to_phone: str, url: str, caption: str, filename: str
    ) -> Optional[str]:
        """
        Meta Cloud API document message.
        POST /v19.0/{phone_number_id}/messages with type=document.
        """
        access_token    = settings.WHATSAPP_ACCESS_TOKEN
        phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        if not access_token or not phone_number_id:
            logger.error("Meta send_document: access token or phone_number_id missing")
            return None

        payload = {
            "messaging_product": "whatsapp",
            "to":                to_phone.lstrip("+"),
            "type":              "document",
            "document": {
                "link":     url,
                "caption":  caption,
                "filename": filename,
            },
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
        }
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    f"{_META_API_BASE}/{phone_number_id}/messages",
                    headers = headers,
                    json    = payload,
                )
            resp.raise_for_status()
            data   = resp.json()
            msg_id = (data.get("messages") or [{}])[0].get("id")
            logger.info("Meta document sent to %s: %s", to_phone, msg_id)
            return msg_id
        except httpx.HTTPStatusError as exc:
            logger.error("Meta send_document HTTP %s: %s",
                         exc.response.status_code, exc.response.text)
        except Exception as exc:
            logger.error("Meta send_document failed: %s", exc)
        return None

    def _send_document_interakt(
        self, to_phone: str, url: str, caption: str, filename: str
    ) -> Optional[str]:
        """
        Interakt document message.
        POST /v1/public/message/ with type=Document.
        """
        api_key = settings.INTERAKT_API_KEY
        if not api_key:
            logger.error("Interakt send_document: INTERAKT_API_KEY not configured")
            return None

        b64_key = base64.b64encode(api_key.encode()).decode()
        country_code = "91" if to_phone.startswith("+91") else "1"
        payload = {
            "type": "Document",
            "data": {
                "document_link": url,
                "caption":       caption,
            },
            "phoneNumber": to_phone,
            "countryCode": country_code,
        }
        headers = {
            "Authorization": f"Basic {b64_key}",
            "Content-Type":  "application/json",
        }
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(_INTERAKT_SEND_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data   = resp.json()
            msg_id = data.get("id") or data.get("messageId") or "interakt-doc-ok"
            logger.info("Interakt document sent to %s: %s", to_phone, msg_id)
            return msg_id
        except httpx.HTTPStatusError as exc:
            logger.error("Interakt send_document HTTP %s: %s",
                         exc.response.status_code, exc.response.text)
        except Exception as exc:
            logger.error("Interakt send_document failed: %s", exc)
        return None

    def _send_document_twilio(
        self, to_phone: str, url: str, caption: str
    ) -> Optional[str]:
        """
        Twilio WhatsApp media message (supports PDF URLs).
        Twilio fetches the URL and attaches it as media.
        """
        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            msg    = client.messages.create(
                body      = caption or "Your payslip is attached.",
                from_     = settings.TWILIO_WHATSAPP_NUMBER,
                to        = f"whatsapp:{to_phone}",
                media_url = [url],
            )
            logger.info("Twilio document sent to %s: %s", to_phone, msg.sid)
            return msg.sid
        except Exception as exc:
            logger.error("Twilio send_document failed to %s: %s", to_phone, exc)
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience helpers
# ─────────────────────────────────────────────────────────────────────────────

def send_whatsapp(to_phone: str, body: str) -> Optional[str]:
    """Send a text message via the configured provider."""
    return WhatsAppGateway().send(to_phone, body)


def send_document(
    to_phone:     str,
    document_url: str,
    caption:      str = "",
    filename:     str = "document.pdf",
) -> Optional[str]:
    """Send a document via the configured provider. Returns message ID or None."""
    return WhatsAppGateway().send_document(to_phone, document_url, caption, filename)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_phone(phone: str) -> str:
    """
    Normalise a phone number to E.164 (+XXXXXXXXXXX).
    Handles:
      - Meta format: "919876543210"   → "+919876543210"
      - Twilio format: "whatsapp:+919876543210" → "+919876543210"
      - Already E.164: "+919876543210" → unchanged
    """
    phone = phone.strip()
    phone = phone.replace("whatsapp:", "").strip()
    if not phone or not phone.lstrip("+").isdigit():
        return ""

    if phone.startswith("+"):
        return phone

    # Bare digits — assume Indian number if 10 digits, else trust as-is
    digits = phone.lstrip("0")
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) >= 11:
        return f"+{digits}"
    return f"+{phone}"
