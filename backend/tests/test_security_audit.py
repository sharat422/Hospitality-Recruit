from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from jose import jwt

from app.core.config import settings
from app.core.security import get_current_user, get_optional_user
from app.main import app
from app.core.dependencies import get_supabase_client


def token(**overrides):
    claims = {"sub": "audit-user", "aud": "authenticated", "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
              "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
    claims.update(overrides)
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=jwt.encode(claims, settings.SUPABASE_JWT_SECRET, algorithm="HS256"))


@pytest.mark.asyncio
async def test_supabase_authenticated_audience_is_accepted():
    assert (await get_current_user(token()))["sub"] == "audit-user"


@pytest.mark.asyncio
@pytest.mark.parametrize("claims", [{"aud": "other"}, {"iss": "https://other.invalid/auth/v1"}, {"exp": 1}])
async def test_wrong_audience_issuer_and_expired_tokens_are_rejected(claims):
    with pytest.raises(HTTPException) as error:
        await get_current_user(token(**claims))
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_optional_auth_accepts_anonymous_request():
    assert await get_optional_user(None) is None


def test_unsigned_sms_webhook_cannot_send_messages():
    app.dependency_overrides[get_supabase_client] = lambda: object()
    try:
        with patch('app.routers.sms.SMSService') as service:
            response = TestClient(app).post('/api/v1/sms/webhook/twilio', data={"From": "+919000000000", "Body": "hello", "MessageSid": "audit"})
            assert response.status_code == 403
            service.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_anonymous_sms_send_is_rejected():
    with patch('app.routers.sms.SMSService') as service:
        response = TestClient(app).post('/api/v1/sms/send', params={"to_number": "+919000000000", "message": "audit"})
        assert response.status_code in (401, 403)
        service.assert_not_called()


def test_billing_prefix_is_registered_once_and_unconfigured_database_is_explicit():
    paths = app.openapi()['paths']
    if not settings.BILLING_ENABLED:
        # Stripe is the original US rail and ships disabled; Indian billing
        # settles through Razorpay. The router must not be mounted at all,
        # so an unauthenticated caller gets a plain 404 rather than a route
        # that exists but cannot work.
        assert '/api/v1/billing/pricing/tiers' not in paths
        assert TestClient(app).get('/api/v1/billing/pricing/tiers').status_code == 404
        return
    assert '/api/v1/billing/pricing/tiers' in paths
    assert '/api/v1/billing/billing/pricing/tiers' not in paths
    response = TestClient(app).get('/api/v1/billing/pricing/tiers')
    assert response.status_code == 503
    assert 'not configured' in response.json()['detail']
