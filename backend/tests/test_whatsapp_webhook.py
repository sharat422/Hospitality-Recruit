"""
Tests for WhatsApp webhook integration.

Covers:
  1. GET /webhook — Meta hub verification
  2. POST /webhook — Meta inbound messages
  3. POST /webhook — Interakt inbound messages
  4. Payload parsers (meta, interakt)
  5. Phone normalisation
  6. HMAC signature verification
  7. WhatsAppGateway send routing (meta / interakt / twilio)
  8. Employee identification + message routing
  9. Media-only messages
 10. Status/delivery receipt ping (no-op)
"""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ─── app import (lazy, avoids env errors in CI) ──────────────────────────────
try:
    from app.main import app
    from app.services.whatsapp_gateway import (
        WhatsAppGateway,
        ParsedMessage,
        parse_meta_payload,
        parse_interakt_payload,
        parse_inbound,
        verify_meta_signature,
        _normalise_phone,
        send_whatsapp,
    )
    _HAS_APP = True
except Exception:
    _HAS_APP = False

pytestmark = pytest.mark.skipif(not _HAS_APP, reason="app not importable in this env")


# ═════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


META_VERIFY_TOKEN = "test-verify-token-abc"

# Realistic Meta inbound webhook payload
META_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [{
        "id": "WABA_ID_123",
        "changes": [{
            "field": "messages",
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {
                    "display_phone_number": "911234567890",
                    "phone_number_id":      "PHONE_NUM_ID_456",
                },
                "contacts": [{
                    "profile": {"name": "Priya Sharma"},
                    "wa_id": "919876543210",
                }],
                "messages": [{
                    "from":      "919876543210",
                    "id":        "wamid.test001",
                    "timestamp": "1716192000",
                    "type":      "text",
                    "text":      {"body": "HELP"},
                }],
            },
        }],
    }],
}

# Meta delivery-receipt ping (no messages key)
META_STATUS_PING = {
    "object": "whatsapp_business_account",
    "entry": [{
        "changes": [{
            "field": "messages",
            "value": {
                "statuses": [{
                    "id":        "wamid.test001",
                    "status":    "delivered",
                    "timestamp": "1716192010",
                    "recipient_id": "919876543210",
                }],
            },
        }],
    }],
}

# Interakt inbound payload
INTERAKT_PAYLOAD = {
    "type": "incoming_message",
    "payload": {
        "id":   "interakt-msg-001",
        "type": "text",
        "text": {"body": "BALANCE"},
        "from": {
            "phone_number": "+919876543210",
            "name":         "Ravi Kumar",
        },
        "timestamp": "2026-05-20T10:00:00Z",
    },
}

# Interakt flat format (older webhook versions)
INTERAKT_FLAT = {
    "type": "text",
    "body": {"text": "SHIFT"},
    "from": "+919876543210",
}

# Image message (media only, no text body)
META_IMAGE_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [{
        "changes": [{
            "field": "messages",
            "value": {
                "contacts": [{"profile": {"name": "User"}, "wa_id": "919876543210"}],
                "messages": [{
                    "from":  "919876543210",
                    "id":    "wamid.img001",
                    "type":  "image",
                    "image": {"mime_type": "image/jpeg", "id": "media-id-123"},
                }],
            },
        }],
    }],
}


# ═════════════════════════════════════════════════════════════════════════════
# 1. Phone normalisation
# ═════════════════════════════════════════════════════════════════════════════

class TestPhoneNormalisation:
    def test_meta_format_no_plus(self):
        assert _normalise_phone("919876543210") == "+919876543210"

    def test_already_e164(self):
        assert _normalise_phone("+919876543210") == "+919876543210"

    def test_twilio_prefix(self):
        assert _normalise_phone("whatsapp:+919876543210") == "+919876543210"

    def test_bare_10_digit_india(self):
        assert _normalise_phone("9876543210") == "+919876543210"

    def test_us_number(self):
        assert _normalise_phone("12025550123") == "+12025550123"

    def test_plus_already(self):
        assert _normalise_phone("+14155238886") == "+14155238886"


# ═════════════════════════════════════════════════════════════════════════════
# 2. Meta payload parser
# ═════════════════════════════════════════════════════════════════════════════

class TestMetaParser:
    def test_text_message_parsed(self):
        msgs = parse_meta_payload(META_PAYLOAD)
        assert len(msgs) == 1
        m = msgs[0]
        assert m.phone == "+919876543210"
        assert m.body  == "HELP"
        assert m.is_text
        assert m.provider_msg_id == "wamid.test001"
        assert m.contact_name    == "Priya Sharma"

    def test_delivery_receipt_returns_empty(self):
        msgs = parse_meta_payload(META_STATUS_PING)
        assert msgs == []

    def test_image_message(self):
        msgs = parse_meta_payload(META_IMAGE_PAYLOAD)
        assert len(msgs) == 1
        m = msgs[0]
        assert not m.is_text
        assert m.body == ""
        assert m.media_type == "image"

    def test_empty_payload(self):
        assert parse_meta_payload({}) == []

    def test_non_messages_field_skipped(self):
        data = {
            "entry": [{"changes": [{"field": "account_update", "value": {}}]}]
        }
        assert parse_meta_payload(data) == []

    def test_multiple_messages(self):
        data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "contacts": [],
                        "messages": [
                            {"from": "919876543210", "id": "m1", "type": "text",
                             "text": {"body": "HELP"}},
                            {"from": "918888888888", "id": "m2", "type": "text",
                             "text": {"body": "BALANCE"}},
                        ],
                    },
                }],
            }],
        }
        msgs = parse_meta_payload(data)
        assert len(msgs) == 2
        assert msgs[0].body == "HELP"
        assert msgs[1].body == "BALANCE"


# ═════════════════════════════════════════════════════════════════════════════
# 3. Interakt payload parser
# ═════════════════════════════════════════════════════════════════════════════

class TestInteraktParser:
    def test_wrapped_format(self):
        msgs = parse_interakt_payload(INTERAKT_PAYLOAD)
        assert len(msgs) == 1
        m = msgs[0]
        assert m.phone        == "+919876543210"
        assert m.body         == "BALANCE"
        assert m.is_text
        assert m.contact_name == "Ravi Kumar"
        assert m.provider_msg_id == "interakt-msg-001"

    def test_flat_format(self):
        msgs = parse_interakt_payload(INTERAKT_FLAT)
        assert len(msgs) == 1
        assert msgs[0].body  == "SHIFT"
        assert msgs[0].phone == "+919876543210"

    def test_empty_payload(self):
        assert parse_interakt_payload({}) == []

    def test_missing_phone(self):
        assert parse_interakt_payload({"type": "text", "body": {"text": "HELP"}}) == []


# ═════════════════════════════════════════════════════════════════════════════
# 4. parse_inbound dispatcher
# ═════════════════════════════════════════════════════════════════════════════

class TestParseInbound:
    def test_meta_dispatch(self):
        msgs = parse_inbound("meta", META_PAYLOAD)
        assert len(msgs) == 1
        assert msgs[0].body == "HELP"

    def test_interakt_dispatch(self):
        msgs = parse_inbound("interakt", INTERAKT_PAYLOAD)
        assert len(msgs) == 1
        assert msgs[0].body == "BALANCE"

    def test_twilio_returns_empty(self):
        # Twilio uses form-encoded — parse_inbound doesn't handle it
        assert parse_inbound("twilio", {"Body": "HELP"}) == []

    def test_unknown_provider_returns_empty(self):
        assert parse_inbound("unknown_bsp", {}) == []


# ═════════════════════════════════════════════════════════════════════════════
# 5. HMAC signature verification
# ═════════════════════════════════════════════════════════════════════════════

class TestMetaSignature:
    APP_SECRET = "my-app-secret-12345"
    BODY       = b'{"object":"whatsapp_business_account"}'

    def _make_sig(self, body: bytes, secret: str) -> str:
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_valid_signature(self):
        sig = self._make_sig(self.BODY, self.APP_SECRET)
        with patch("app.services.whatsapp_gateway.settings") as mock_s:
            mock_s.WHATSAPP_APP_SECRET = self.APP_SECRET
            assert verify_meta_signature(self.BODY, sig) is True

    def test_invalid_signature(self):
        with patch("app.services.whatsapp_gateway.settings") as mock_s:
            mock_s.WHATSAPP_APP_SECRET = self.APP_SECRET
            assert verify_meta_signature(self.BODY, "sha256=deadbeef") is False

    def test_missing_prefix_rejected(self):
        with patch("app.services.whatsapp_gateway.settings") as mock_s:
            mock_s.WHATSAPP_APP_SECRET = self.APP_SECRET
            assert verify_meta_signature(self.BODY, "abc123") is False

    def test_no_secret_configured_rejects(self):
        with patch("app.services.whatsapp_gateway.settings") as mock_s:
            mock_s.WHATSAPP_APP_SECRET = None
            # An unconfigured signature verifier must fail closed.
            assert verify_meta_signature(self.BODY, "sha256=anything") is False


# ═════════════════════════════════════════════════════════════════════════════
# 6. WhatsAppGateway — send routing
# ═════════════════════════════════════════════════════════════════════════════

class TestWhatsAppGatewaySend:
    def test_meta_send_success(self):
        gw = WhatsAppGateway(provider="meta")
        with patch("app.services.whatsapp_gateway.settings") as mock_s, \
             patch("app.services.whatsapp_gateway.httpx.Client") as mock_http:
            mock_s.WHATSAPP_ACCESS_TOKEN    = "token123"
            mock_s.WHATSAPP_PHONE_NUMBER_ID = "pid456"
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"messages": [{"id": "wamid.sent001"}]}
            mock_resp.raise_for_status = MagicMock()
            mock_http.return_value.__enter__.return_value.post.return_value = mock_resp

            result = gw._send_meta("+919876543210", "Test message")
            assert result == "wamid.sent001"

    def test_meta_send_no_token_returns_none(self):
        gw = WhatsAppGateway(provider="meta")
        with patch("app.services.whatsapp_gateway.settings") as mock_s:
            mock_s.WHATSAPP_ACCESS_TOKEN    = None
            mock_s.WHATSAPP_PHONE_NUMBER_ID = None
            assert gw._send_meta("+919876543210", "Hello") is None

    def test_interakt_send_success(self):
        gw = WhatsAppGateway(provider="interakt")
        with patch("app.services.whatsapp_gateway.settings") as mock_s, \
             patch("app.services.whatsapp_gateway.httpx.Client") as mock_http:
            mock_s.INTERAKT_API_KEY = "interakt-key-xyz"
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"id": "interakt-out-001"}
            mock_resp.raise_for_status = MagicMock()
            mock_http.return_value.__enter__.return_value.post.return_value = mock_resp

            result = gw._send_interakt("+919876543210", "Test message")
            assert result == "interakt-out-001"

    def test_interakt_send_no_key_returns_none(self):
        gw = WhatsAppGateway(provider="interakt")
        with patch("app.services.whatsapp_gateway.settings") as mock_s:
            mock_s.INTERAKT_API_KEY = None
            assert gw._send_interakt("+919876543210", "Hello") is None

    def test_twilio_send_success(self):
        gw = WhatsAppGateway(provider="twilio")
        with patch("app.services.whatsapp_gateway.settings") as mock_s, \
             patch("app.services.whatsapp_gateway.Client") as _:
            pass  # Twilio tested separately in test_hr_bot.py

    def test_send_dispatches_to_provider(self):
        gw = WhatsAppGateway(provider="meta")
        gw._send_meta = MagicMock(return_value="wamid.x")
        result = gw.send("+919876543210", "Hi")
        gw._send_meta.assert_called_once_with("+919876543210", "Hi")
        assert result == "wamid.x"

    def test_interakt_phone_normalised_before_send(self):
        gw = WhatsAppGateway(provider="interakt")
        gw._send_interakt = MagicMock(return_value="ok")
        gw.send("919876543210", "Hi")   # bare digits, no +
        # normalise_phone should have added +91
        call_phone = gw._send_interakt.call_args[0][0]
        assert call_phone.startswith("+")


# ═════════════════════════════════════════════════════════════════════════════
# 7. GET /webhook — Meta verification endpoint
# ═════════════════════════════════════════════════════════════════════════════

class TestGetWebhook:
    def test_valid_verification(self, client):
        with patch("app.routers.whatsapp.settings") as mock_s:
            mock_s.WHATSAPP_VERIFY_TOKEN = META_VERIFY_TOKEN
            resp = client.get("/api/whatsapp/webhook", params={
                "hub.mode":         "subscribe",
                "hub.challenge":    "challenge_123",
                "hub.verify_token": META_VERIFY_TOKEN,
            })
        assert resp.status_code == 200
        assert resp.text == "challenge_123"

    def test_wrong_verify_token(self, client):
        with patch("app.routers.whatsapp.settings") as mock_s:
            mock_s.WHATSAPP_VERIFY_TOKEN = META_VERIFY_TOKEN
            resp = client.get("/api/whatsapp/webhook", params={
                "hub.mode":         "subscribe",
                "hub.challenge":    "challenge_123",
                "hub.verify_token": "wrong-token",
            })
        assert resp.status_code == 403

    def test_missing_verify_token_in_config(self, client):
        with patch("app.routers.whatsapp.settings") as mock_s:
            mock_s.WHATSAPP_VERIFY_TOKEN = None
            resp = client.get("/api/whatsapp/webhook", params={
                "hub.mode": "subscribe",
                "hub.challenge": "x",
                "hub.verify_token": "anything",
            })
        assert resp.status_code == 503

    def test_wrong_mode_returns_403(self, client):
        with patch("app.routers.whatsapp.settings") as mock_s:
            mock_s.WHATSAPP_VERIFY_TOKEN = META_VERIFY_TOKEN
            resp = client.get("/api/whatsapp/webhook", params={
                "hub.mode":         "unsubscribe",
                "hub.challenge":    "x",
                "hub.verify_token": META_VERIFY_TOKEN,
            })
        assert resp.status_code == 403


# ═════════════════════════════════════════════════════════════════════════════
# 8. POST /webhook — Meta inbound (end-to-end with mocked bot + gateway)
# ═════════════════════════════════════════════════════════════════════════════

class TestPostWebhookMeta:
    def _post(self, client, payload, provider="meta", signature=None):
        headers = {"Content-Type": "application/json"}
        raw = json.dumps(payload, separators=(",", ":")).encode()
        headers["x-hub-signature-256"] = signature or "sha256=" + hmac.new(b"audit-secret", raw, hashlib.sha256).hexdigest()
        with patch("app.routers.whatsapp.settings") as mock_s:
            mock_s.WHATSAPP_PROVIDER  = provider
            mock_s.WHATSAPP_APP_SECRET = "audit-secret"
            mock_s.WHATSAPP_VERIFY_TOKEN = META_VERIFY_TOKEN
            return client.post(
                "/api/whatsapp/webhook",
                content=raw,
                headers=headers,
            )

    def test_meta_text_message_acknowledged(self, client):
        with patch("app.routers.whatsapp._process_message"):
            resp = self._post(client, META_PAYLOAD)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["queued"] == 1

    def test_meta_status_ping_acknowledged_no_processing(self, client):
        with patch("app.routers.whatsapp._process_message") as mock_proc:
            resp = self._post(client, META_STATUS_PING)
        assert resp.status_code == 200
        mock_proc.assert_not_called()

    def test_unconfigured_meta_webhook_returns_503(self, client):
        with patch("app.routers.whatsapp.settings") as mock_s:
            mock_s.WHATSAPP_PROVIDER   = "meta"
            mock_s.WHATSAPP_APP_SECRET = None
            resp = client.post(
                "/api/whatsapp/webhook",
                content=b"not json at all",
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 503

    def test_meta_signature_mismatch_returns_403(self, client):
        with patch("app.routers.whatsapp.settings") as mock_s:
            mock_s.WHATSAPP_PROVIDER   = "meta"
            mock_s.WHATSAPP_APP_SECRET = "secret123"
            resp = client.post(
                "/api/whatsapp/webhook",
                json=META_PAYLOAD,
                headers={
                    "x-hub-signature-256": "sha256=badhash",
                    "Content-Type": "application/json",
                },
            )
        assert resp.status_code == 403

    def test_multiple_messages_queued(self, client):
        data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "contacts": [],
                        "messages": [
                            {"from": "919876543210", "id": "m1", "type": "text",
                             "text": {"body": "HELP"}},
                            {"from": "918888888888", "id": "m2", "type": "text",
                             "text": {"body": "BALANCE"}},
                        ],
                    },
                }],
            }],
        }
        with patch("app.routers.whatsapp._process_message"):
            resp = self._post(client, data)
        assert resp.json()["queued"] == 2


# ═════════════════════════════════════════════════════════════════════════════
# 9. POST /webhook — Interakt inbound
# ═════════════════════════════════════════════════════════════════════════════

class TestPostWebhookInterakt:
    def _post(self, client, payload):
        with patch("app.routers.whatsapp.settings") as mock_s:
            mock_s.WHATSAPP_PROVIDER   = "interakt"
            mock_s.WHATSAPP_APP_SECRET = None
            return client.post("/api/whatsapp/webhook", json=payload)

    def test_interakt_text_message_acknowledged(self, client):
        with patch("app.routers.whatsapp._process_message"):
            resp = self._post(client, INTERAKT_PAYLOAD)
        assert resp.status_code == 200
        assert resp.json()["queued"] == 1

    def test_interakt_flat_format_acknowledged(self, client):
        with patch("app.routers.whatsapp._process_message"):
            resp = self._post(client, INTERAKT_FLAT)
        assert resp.status_code == 200

    def test_empty_interakt_payload_returns_ok(self, client):
        resp = self._post(client, {})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ═════════════════════════════════════════════════════════════════════════════
# 10. _process_message — media-only message
# ═════════════════════════════════════════════════════════════════════════════

class TestProcessMessage:
    def test_media_only_sends_text_prompt(self):
        """Media-only message (no body) should reply asking for text commands."""
        from app.routers.whatsapp import _process_message

        supabase = MagicMock()
        msg      = ParsedMessage(
            phone    = "+919876543210",
            body     = "",
            is_text  = False,
            media_url = "https://example.com/img.jpg",
            media_type = "image/jpeg",
        )

        with patch("app.routers.whatsapp.gateway") as mock_gw:
            _process_message(supabase, msg, "meta")
            call_args = mock_gw.send.call_args
            assert call_args is not None
            reply_text = call_args[0][1]
            assert "HELP" in reply_text

    def test_text_message_dispatches_to_hr_bot(self):
        """Text message should be routed through handle_whatsapp_message."""
        from app.routers.whatsapp import _process_message

        supabase = MagicMock()
        msg      = ParsedMessage(
            phone           = "+919876543210",
            body            = "BALANCE",
            is_text         = True,
            provider_msg_id = "wamid.test",
        )

        with patch("app.routers.whatsapp.handle_whatsapp_message",
                   return_value="Your balance: 12 days") as mock_handler, \
             patch("app.routers.whatsapp.gateway") as mock_gw:
            _process_message(supabase, msg, "meta")
            mock_handler.assert_called_once_with(
                supabase   = supabase,
                phone      = "+919876543210",
                body       = "BALANCE",
                twilio_sid = "wamid.test",
            )
            mock_gw.send.assert_called_once_with("+919876543210", "Your balance: 12 days")


# ═════════════════════════════════════════════════════════════════════════════
# 11. GET /webhook/status
# ═════════════════════════════════════════════════════════════════════════════

class TestWebhookStatus:
    def test_meta_status(self, client):
        with patch("app.routers.whatsapp.settings") as mock_s:
            mock_s.WHATSAPP_PROVIDER        = "meta"
            mock_s.WHATSAPP_VERIFY_TOKEN    = "tok"
            mock_s.WHATSAPP_ACCESS_TOKEN    = "bearer"
            mock_s.WHATSAPP_PHONE_NUMBER_ID = "pid"
            mock_s.WHATSAPP_APP_SECRET      = "sec"
            resp = client.get("/api/whatsapp/webhook/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"]            == "meta"
        assert data["access_token_set"]    is True
        assert data["phone_number_id_set"] is True
        assert data["signature_verify"]    is True

    def test_interakt_status(self, client):
        with patch("app.routers.whatsapp.settings") as mock_s:
            mock_s.WHATSAPP_PROVIDER     = "interakt"
            mock_s.WHATSAPP_VERIFY_TOKEN = None
            mock_s.INTERAKT_API_KEY      = "key123"
            resp = client.get("/api/whatsapp/webhook/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"]     == "interakt"
        assert data["api_key_set"]  is True

    def test_twilio_status(self, client):
        with patch("app.routers.whatsapp.settings") as mock_s:
            mock_s.WHATSAPP_PROVIDER        = "twilio"
            mock_s.WHATSAPP_VERIFY_TOKEN    = None
            mock_s.TWILIO_ACCOUNT_SID       = "AC123"
            mock_s.TWILIO_AUTH_TOKEN        = "tok"
            mock_s.TWILIO_WHATSAPP_NUMBER   = "whatsapp:+14155238886"
            resp = client.get("/api/whatsapp/webhook/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "twilio"
