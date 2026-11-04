"""Permission-aware Hospitality AI Assistant API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.hospitality_ai_assistant_service import (
    TOOLS, claude_narrative, classify_question, execute_tool, public_tool_catalog, rows,
)
from app.services.rbac_service import authorize, build_access_context

router = APIRouter(tags=["Hospitality AI Assistant"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    conversation_id: str | None = None
    property_id: str | None = None
    department_id: str | None = None
    period_days: int = Field(default=30, ge=1, le=366)


@router.get("/tools")
async def list_tools(supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "reports.read")
    return {"tools": public_tool_catalog(context), "destructiveToolsEnabled": False}


@router.get("/conversations")
async def list_conversations(supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "reports.read")
    return rows(supabase.table("ai_assistant_conversations").select("id,title,property_id,created_at,updated_at").eq("org_id", context.org_id).eq("user_id", context.user_id).order("updated_at", desc=True).limit(30).execute())


@router.get("/conversations/{conversation_id}")
async def conversation(conversation_id: str, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "reports.read")
    found = rows(supabase.table("ai_assistant_conversations").select("id,title,property_id,created_at,updated_at").eq("id", conversation_id).eq("org_id", context.org_id).eq("user_id", context.user_id).limit(1).execute())
    if not found: raise HTTPException(404, "Conversation not found")
    messages = rows(supabase.table("ai_assistant_messages").select("id,role,content,tool_name,sources,metrics,filters,generated_by,created_at").eq("conversation_id", conversation_id).eq("user_id", context.user_id).order("created_at").execute())
    return {"conversation": found[0], "messages": messages}


@router.post("/ask")
async def ask(body: AskBody, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "reports.read", property_id=body.property_id, department_id=body.department_id)
    tool_name = classify_question(body.question)
    if not tool_name or tool_name not in TOOLS:
        raise HTTPException(422, {"message": "I can answer supported hospitality analytics questions only.", "availableTools": public_tool_catalog(context)})
    if TOOLS[tool_name].permission not in context.permissions:
        raise HTTPException(403, "You do not have permission to access the data required for this answer")

    conversation_id = body.conversation_id or str(uuid4())
    if body.conversation_id:
        existing = rows(supabase.table("ai_assistant_conversations").select("id").eq("id", conversation_id).eq("org_id", context.org_id).eq("user_id", context.user_id).limit(1).execute())
        if not existing: raise HTTPException(404, "Conversation not found")
    else:
        supabase.table("ai_assistant_conversations").insert({"id": conversation_id, "org_id": context.org_id, "user_id": context.user_id, "title": body.question[:157], "property_id": body.property_id}).execute()
    user_message = rows(supabase.table("ai_assistant_messages").insert({"org_id": context.org_id, "conversation_id": conversation_id, "user_id": context.user_id, "role": "USER", "content": body.question}).execute())
    run_id = str(uuid4()); started = datetime.now(timezone.utc).isoformat()
    supabase.table("ai_assistant_tool_runs").insert({"id": run_id, "org_id": context.org_id, "conversation_id": conversation_id, "message_id": user_message[0].get("id") if user_message else None, "user_id": context.user_id, "tool_name": tool_name, "permission_required": TOOLS[tool_name].permission, "property_id": body.property_id, "department_id": body.department_id, "status": "RUNNING", "started_at": started}).execute()
    try:
        result = execute_tool(supabase, context, tool_name, property_id=body.property_id,
                              department_id=body.department_id, days=body.period_days, question=body.question)
        answer, generated_by = claude_narrative(body.question, result)
        payload = {"org_id": context.org_id, "conversation_id": conversation_id, "user_id": context.user_id,
                   "role": "ASSISTANT", "content": answer, "tool_name": tool_name,
                   "sources": result["sources"], "metrics": result["metrics"],
                   "filters": {"propertyId": body.property_id, "departmentId": body.department_id, "periodDays": body.period_days},
                   "generated_by": generated_by}
        saved = rows(supabase.table("ai_assistant_messages").insert(payload).execute())
        supabase.table("ai_assistant_tool_runs").update({"status": "SUCCEEDED", "row_count": result.get("row_count", 0), "completed_at": datetime.now(timezone.utc).isoformat()}).eq("id", run_id).execute()
        supabase.table("ai_assistant_conversations").update({"updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", conversation_id).eq("user_id", context.user_id).execute()
        return {"conversationId": conversation_id, "message": saved[0] if saved else payload,
                "rows": result.get("rows", []), "methodology": result.get("methodology"),
                "readOnly": True, "destructiveAction": None}
    except HTTPException:
        supabase.table("ai_assistant_tool_runs").update({"status": "DENIED", "error_code": "AUTHORIZATION_DENIED", "completed_at": datetime.now(timezone.utc).isoformat()}).eq("id", run_id).execute()
        raise
    except Exception as exc:
        supabase.table("ai_assistant_tool_runs").update({"status": "FAILED", "error_code": type(exc).__name__[:80], "completed_at": datetime.now(timezone.utc).isoformat()}).eq("id", run_id).execute()
        raise HTTPException(503, "The assistant could not retrieve verified application data") from exc


@router.post("/actions")
async def reject_actions(supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "reports.read")
    raise HTTPException(405, "The Hospitality AI Assistant is read-only. Destructive operations are not enabled.")
