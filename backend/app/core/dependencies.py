"""
Dependency injection setup for Supabase client + services.
Pattern: services receive repositories, repositories receive Supabase client.
"""

from supabase import create_client, Client
from app.core.config import settings
from typing import Annotated, AsyncGenerator
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


optional_bearer = HTTPBearer(auto_error=False)


def get_supabase_client(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
) -> Client:
    """Create a Supabase client carrying the caller JWT for Postgres RLS."""
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    if credentials:
        client.postgrest.auth(credentials.credentials)
    return client


def get_supabase_admin_client() -> Client:
    """Server-only client for authenticated provider webhooks and workers."""
    key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
    return create_client(settings.SUPABASE_URL, key)


SupabaseClient = Annotated[Client, Depends(get_supabase_client)]
SupabaseAdminClient = Annotated[Client, Depends(get_supabase_admin_client)]


async def get_db():
    """
    Stub async database session dependency for SQLAlchemy-based routes.
    In production wire this to an actual AsyncSession factory.
    """
    raise HTTPException(status_code=503, detail="Billing database is not configured")
    yield  # make it an async generator for FastAPI Depends compatibility
