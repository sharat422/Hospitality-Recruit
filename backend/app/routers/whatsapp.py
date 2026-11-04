"""
WhatsApp Webhook Router
Prefix: /api/whatsapp

Handles Meta WhatsApp Business API and Interakt inbound webhooks.
The existing Twilio webhook stays at /api/v1/hr-bot/webhook unchanged.

Endpoints:
  GET  /webhook  — Meta hub verification (challenge handshake)
  POST /webhook  — Inbound messages from Meta or Interakt

Setup guides:
  Meta:     App Dashboard → WhatsApp → Configuration → Webhook
            URL: https://your-domain/api/whatsapp/webhook
            Verify Token: value of WHATSAPP_VERIFY_TOKEN env var
            Subscribe to: messages
  Interakt: Dashboard → Settings → Webhooks
            URL: https://your-domain/api/whatsapp/webhook

Provider selection:
  Set WHATSAPP_PROVIDER=meta  or  WHATSAPP_PROVIDER=interakt  in .env.
  Default is "twilio" (existing hr_bot webhook handles that).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.dependencies import SupabaseAdminClient
from app.services.hr_bot_service import (
    handle_whatsapp_message,
    log_outbound_message,
    log_inbound_message,
    update_message_response,
    resolve_employee,
    get_or_create_whatsapp_user,
    parse_command,
)
from app.services.whatsapp_gateway import (
    WhatsAppGateway,
    ParsedMessage,
    parse_inbound,
    verify_meta_signature,
    _normalise_phone,
)
from app.services.whatsapp_apply_service import handle_whatsapp_application

router  = APIRouter(tags=["WhatsApp Webhook"])
logger  = logging.getLogger(__name__)
gateway = WhatsAppGateway()   # single instance, reads WHATSAPP_PROVIDER at startup


# ─────────────────────────────────────────────────────────────────────────────
# GET /webhook — Meta hub verification handshake
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode:        str = Query(alias="hub.mode",         default=""),
    hub_challenge:   str = Query(alias="hub.challenge",    default=""),
    hub_verify_token:str = Query(alias="hub.verify_token", default=""),
):
    """
    Meta sends a GET with hub.mode=subscribe to verify the webhook endpoint.
    We must respond with hub.challenge (plain text, HTTP 200) if the
    hub.verify_token matches WHATSAPP_VERIFY_TOKEN.

    Interakt does not send a verification GET — this endpoint is no-op for them.
    """
    if not settings.WHATSAPP_VERIFY_TOKEN:
        logger.warning("Webhook GET received but WHATSAPP_VERIFY_TOKEN is not set")
        raise HTTPException(503, "WHATSAPP_VERIFY_TOKEN not configured")

    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Meta webhook verified successfully")
        return hub_challenge

    logger.warning(
        "Meta webhook verification failed: mode=%r token_match=%s",
        hub_mode,
        hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN,
    )
    raise HTTPException(403, "Webhook verification failed")


# ─────────────────────────────────────────────────────────────────────────────
# POST /webhook — Inbound messages (Meta or Interakt JSON)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/webhook")
async def receive_webhook(
    request:          Request,
    background_tasks: BackgroundTasks,
    supabase:         SupabaseAdminClient,
    x_hub_signature_256: Optional[str] = Header(default=None, alias="x-hub-signature-256"),
):
    """
    Receive inbound WhatsApp messages from Meta or Interakt.

    Processing flow:
      1. Read raw body bytes (needed for Meta HMAC verification).
      2. Verify Meta signature (if WHATSAPP_APP_SECRET is set).
      3. Parse JSON into provider-agnostic ParsedMessage list.
      4. For each text message:
           a. Identify employee by phone.
           b. Log inbound to whatsapp_messages.
           c. Route to hr_bot command handler.
           d. Log + send reply via WhatsApp gateway.
      5. Return {"status": "ok"} immediately — Meta requires 200 within 20 s.

    Media-only messages receive a polite "text only" reply.
    Status/delivery webhooks (no messages[]) are acknowledged and ignored.
    """
    raw_body = await request.body()

    # ── 1. Signature verification (Meta only) ─────────────────────────────────
    provider = settings.WHATSAPP_PROVIDER.lower()

    if provider == "meta":
        if not settings.WHATSAPP_APP_SECRET:
            raise HTTPException(503, "WhatsApp webhook secret is not configured")
        if not x_hub_signature_256 or not verify_meta_signature(raw_body, x_hub_signature_256, settings.WHATSAPP_APP_SECRET):
            logger.warning("Meta signature mismatch — rejecting webhook")
            raise HTTPException(403, "Invalid signature")

    # ── 2. Parse JSON body ────────────────────────────────────────────────────
    try:
        data: dict = await request.json()
    except Exception:
        logger.warning("Webhook POST: invalid JSON body")
        return {"status": "ok"}   # return 200 anyway to avoid Meta retries

    logger.debug("Webhook inbound [%s]: %s", provider, str(data)[:300])

    # ── 3. Meta status-update pings (delivery receipts, read receipts) ────────
    # Meta also POSTs when messages are delivered/read — those have no 'messages'
    # key in the value object. Acknowledge and skip.
    if provider == "meta":
        has_messages = any(
            msg_list
            for entry in data.get("entry", [])
            for change in entry.get("changes", [])
            for msg_list in [change.get("value", {}).get("messages")]
            if msg_list
        )
        if not has_messages:
            return {"status": "ok"}   # delivery/read receipt — nothing to process

    # ── 4. Parse into ParsedMessage list ─────────────────────────────────────
    messages = parse_inbound(provider, data)
    if not messages:
        logger.debug("No parseable messages in webhook payload")
        return {"status": "ok"}

    # ── 5. Process each message ───────────────────────────────────────────────
    for msg in messages:
        background_tasks.add_task(
            _process_message, supabase, msg, provider
        )

    # Always return 200 quickly so Meta/Interakt don't retry
    return {"status": "ok", "queued": len(messages)}


# ─────────────────────────────────────────────────────────────────────────────
# Message processor (runs in background task)
# ─────────────────────────────────────────────────────────────────────────────

def _process_message(supabase: Any, msg: ParsedMessage, provider: str) -> None:
    """
    Process a single inbound WhatsApp message end-to-end:
      resolve employee → log → dispatch → reply → update log.
    Runs in a FastAPI BackgroundTask so the webhook endpoint returns instantly.
    """
    phone = msg.phone
    body  = msg.body.strip()

    logger.info("Processing [%s] from %s: %r", provider, phone, body[:80])

    # Handle media-only (no text)
    if not body and not msg.is_text:
        inbound_id = log_inbound_message(
            supabase, phone, None, None, "[media message]", msg.provider_msg_id,
            "UNKNOWN", "media",
        )
        reply = (
            "🤖 HospBot: I can only process text commands. "
            "Please type *HELP* to see available commands."
        )
        _send_reply(supabase, phone, reply, provider, inbound_message_id=inbound_id)
        return

    application_reply = handle_whatsapp_application(supabase, phone, body)
    if application_reply is not None:
        employee = resolve_employee(supabase, phone)
        wu_id = get_or_create_whatsapp_user(supabase, phone, employee)
        inbound_id = log_inbound_message(
            supabase, phone, employee, wu_id, body, msg.provider_msg_id,
            "APPLY", body,
        )
        update_message_response(supabase, inbound_id, application_reply)
        _send_reply(supabase, phone, application_reply, provider, inbound_message_id=inbound_id)
        return

    # Delegate employee self-service to the shared hr_bot dispatcher.
    # handle_whatsapp_message does:
    #   - resolve_employee
    #   - get_or_create_whatsapp_user (writes whatsapp_users)
    #   - log_inbound_message (writes whatsapp_messages)
    #   - parse_command + dispatch
    #   - update_message_response
    reply = handle_whatsapp_message(
        supabase    = supabase,
        phone       = phone,
        body        = body,
        twilio_sid  = msg.provider_msg_id,
    )

    _send_reply(supabase, phone, reply, provider, inbound_provider_id=msg.provider_msg_id)


def _send_reply(
    supabase: Any,
    phone: str,
    body: str,
    provider: str,
    *,
    inbound_provider_id: Optional[str] = None,
    inbound_message_id: Optional[str] = None,
) -> None:
    """Send through the configured provider and persist the outbound audit row."""
    msg_id = gateway.send(phone, body)
    inbound_id = inbound_message_id
    if not inbound_id and inbound_provider_id:
        try:
            found = (supabase.table("whatsapp_messages").select("id")
                     .eq("twilio_sid", inbound_provider_id).eq("direction", "INBOUND")
                     .limit(1).execute())
            inbound_id = found.data[0]["id"] if found.data else None
        except Exception:
            inbound_id = None
    log_outbound_message(
        supabase, phone, body, msg_id, provider=provider, inbound_message_id=inbound_id,
    )
    if msg_id:
        logger.info("Reply sent [%s] to %s: %s", provider, phone, msg_id)
    else:
        logger.warning("Reply send failed [%s] to %s", provider, phone)


# ─────────────────────────────────────────────────────────────────────────────
# GET /webhook/status — health check for this webhook endpoint (admin)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/webhook/status")
async def webhook_status():
    """
    Returns configuration summary for the active WhatsApp provider.
    Use this to verify env vars are set before wiring Twilio/Meta/Interakt.
    Does NOT expose secret values — only presence flags.
    """
    provider = settings.WHATSAPP_PROVIDER.lower()

    status: dict = {
        "provider":            provider,
        "verify_token_set":    bool(settings.WHATSAPP_VERIFY_TOKEN),
    }

    if provider == "meta":
        status.update({
            "access_token_set":    bool(settings.WHATSAPP_ACCESS_TOKEN),
            "phone_number_id_set": bool(settings.WHATSAPP_PHONE_NUMBER_ID),
            "app_secret_set":      bool(settings.WHATSAPP_APP_SECRET),
            "signature_verify":    bool(settings.WHATSAPP_APP_SECRET),
        })
    elif provider == "interakt":
        status.update({
            "api_key_set": bool(settings.INTERAKT_API_KEY),
        })
    elif provider == "twilio":
        status.update({
            "account_sid_set":    bool(settings.TWILIO_ACCOUNT_SID),
            "auth_token_set":     bool(settings.TWILIO_AUTH_TOKEN),
            "whatsapp_number":    settings.TWILIO_WHATSAPP_NUMBER,
        })

    return status
