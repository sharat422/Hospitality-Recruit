"""Staff Ops language preference and the server-side language resolver.

Language is per person (PLAN.md decision 8). Notification templates and
generated documents read the recipient's preference from here, so a WhatsApp
message and the UI agree on language.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.staff_ops_language import (
    SUPPORTED_LANGUAGES,
    default_language_for_state,
    resolve_language,
)

router = APIRouter()
CurrentUser = Annotated[dict, Depends(get_current_user)]


def rows(result):
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


class LanguageBody(BaseModel):
    preferred_language: Literal["en", "hi", "te", "ta", "kn"]


@router.get("/languages")
async def list_languages(user: CurrentUser):
    """Languages Staff Ops supports."""
    return SUPPORTED_LANGUAGES


@router.get("/me/language")
async def get_my_language(supabase: SupabaseClient, user: CurrentUser):
    """The caller's language, resolved through preference → hotel state → English."""
    user_id = user.get("sub")
    found = rows(supabase.table("users")
                 .select("preferred_language,active_property_id")
                 .eq("id", user_id).limit(1).execute())
    if not found:
        raise HTTPException(404, "User not found")
    record = found[0]

    state = None
    if property_id := record.get("active_property_id"):
        prop = rows(supabase.table("properties").select("state")
                    .eq("id", property_id).limit(1).execute())
        state = prop[0].get("state") if prop else None

    stored = record.get("preferred_language")
    return {
        "preferred_language": stored,
        "resolved_language": resolve_language(stored, state),
        "hotel_state": state,
        "hotel_default": default_language_for_state(state),
        "source": "USER" if stored else ("HOTEL_STATE" if state else "DEFAULT"),
    }


@router.put("/me/language")
async def set_my_language(body: LanguageBody, supabase: SupabaseClient, user: CurrentUser):
    """Save the caller's own language. A user may only set their own."""
    user_id = user.get("sub")
    saved = rows(supabase.table("users").update({
        "preferred_language": body.preferred_language,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", user_id).execute())
    if not saved:
        raise HTTPException(500, "Could not save language preference")
    return {"preferred_language": body.preferred_language}
