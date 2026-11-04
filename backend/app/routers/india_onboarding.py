"""
India Digital Onboarding Router

Endpoints:
  POST /flows/init               — init onboarding flow + checklist
  GET  /flows                    — list all flows (with at-risk flag)
  GET  /flows/{flow_id}          — get one flow with tasks
  PATCH /flows/{flow_id}/tasks/{task_id}   — complete a task
  POST /flows/{flow_id}/appointment-letter — generate appointment letter
  GET  /flows/{flow_id}/appointment-letter — get letter
  POST /flows/{flow_id}/appointment-letter/esign — request Aadhaar eSign
  POST /flows/{flow_id}/pf-form2            — generate PF Form 2
  POST /flows/{flow_id}/esic-declaration    — generate ESIC declaration
  POST /flows/{flow_id}/preboarding/schedule — schedule WhatsApp sequence
  GET  /dashboard                            — summary with at-risk
  GET  /at-risk                              — list at-risk flows
  POST /send-preboarding                     — trigger due message sends
"""

import logging
from datetime import date, datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.india_onboarding_service import (
    compute_ctc_breakup,
    generate_appointment_letter_html,
    generate_pf_form2_data,
    generate_esic_declaration_data,
    ESignAdapter,
    schedule_preboarding_messages,
    init_onboarding_flow,
    send_due_preboarding_messages,
    CHECKLIST_TEMPLATE,
)
from app.services.onboarding_orchestration_service import recalculate_and_persist
from app.services.rbac_service import authorize, build_access_context

logger = logging.getLogger(__name__)
router = APIRouter(tags=["India Onboarding"])

CurrentUser = Annotated[dict, Depends(get_current_user)]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_org_id(db: SupabaseClient, user_id: str) -> Optional[str]:
    try:
        row = db.table("users").select("org_id").eq("id", user_id).single().execute()
        return row.data.get("org_id") if row.data else None
    except Exception:
        return None


def _get_org(db: SupabaseClient, org_id: str) -> dict:
    try:
        row = db.table("organizations").select("*").eq("id", org_id).single().execute()
        return row.data or {}
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────

class InitFlowRequest(BaseModel):
    candidate_id: str
    job_id: Optional[str] = None
    joining_date: Optional[str] = None        # ISO date string
    gross_monthly_inr: Optional[int] = None


class CompleteTaskRequest(BaseModel):
    notes: Optional[str] = None
    document_url: Optional[str] = None


class GenerateLetterRequest(BaseModel):
    gross_monthly_inr: int
    probation_months: int = 6
    notice_period_days: int = 30
    candidate_address: str = "As per records"


class ESignRequest(BaseModel):
    provider: str = "demo"    # leegality | digio | signdesk | demo
    callback_url: str = ""


class SchedulePreboardingRequest(BaseModel):
    sequence_id: Optional[str] = None   # uses default if None


class PFFormRequest(BaseModel):
    org_pf_code: str = "MH/00000"
    org_esic_code: str = "12-00-000000-000-0001"


class TemplateTaskRequest(BaseModel):
    stage: str = Field(pattern="^(documents|kyc|certifications|payroll|ready)$")
    task_type: str = Field(min_length=2, max_length=80)
    task_label: str = Field(min_length=2, max_length=255)
    instructions: Optional[str] = None
    is_mandatory: bool = True
    is_system: bool = False
    due_offset_days: int = Field(default=-1, ge=-365, le=365)
    weight: float = Field(default=1, gt=0, le=100)
    sort_order: int = 0


class TemplateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: Optional[str] = None
    property_id: Optional[str] = None
    department_id: Optional[str] = None
    role_template_id: Optional[str] = None
    version: int = Field(default=1, ge=1)
    auto_start: bool = True
    tasks: list[TemplateTaskRequest] = Field(min_length=1)


class FlowAssignmentRequest(BaseModel):
    manager_id: Optional[str] = None
    joining_date: Optional[date] = None
    reporting_location: Optional[str] = None
    reporting_time: Optional[str] = None


def _scoped_flow(db, context, flow_id: str) -> dict:
    rows = db.table("onboarding_flows").select("*").eq("id", flow_id).eq("org_id", context.org_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Onboarding flow not found")
    flow = rows[0]
    authorize(context, "employees.read", property_id=flow.get("property_id"), department_id=flow.get("department_id"))
    return flow


@router.get("/templates")
async def list_templates(db: SupabaseClient, current_user: CurrentUser, property_id: Optional[str] = None):
    context = build_access_context(db, current_user)
    authorize(context, "employees.read", property_id=property_id)
    query = db.table("onboarding_templates").select("*,onboarding_template_tasks(*)").or_(f"org_id.eq.{context.org_id},org_id.is.null").eq("is_active", True)
    if property_id:
        query = query.or_(f"property_id.eq.{property_id},property_id.is.null")
    return {"templates": query.order("created_at", desc=True).execute().data or []}


@router.post("/templates", status_code=201)
async def create_template(body: TemplateRequest, db: SupabaseClient, current_user: CurrentUser):
    context = build_access_context(db, current_user)
    authorize(context, "employees.manage", property_id=body.property_id, department_id=body.department_id)
    payload = {k: v for k, v in body.model_dump(exclude={"tasks"}).items() if v is not None}
    payload.update(org_id=context.org_id, created_by=context.user_id, is_active=True)
    saved = db.table("onboarding_templates").insert(payload).execute().data or []
    if not saved:
        raise HTTPException(500, "Template could not be created")
    template = saved[0]
    task_rows = [{**task.model_dump(), "template_id": template["id"]} for task in body.tasks]
    db.table("onboarding_template_tasks").insert(task_rows).execute()
    return {"template": template, "tasks": task_rows}


@router.patch("/flows/{flow_id}/assignment")
async def update_flow_assignment(flow_id: str, body: FlowAssignmentRequest, db: SupabaseClient, current_user: CurrentUser):
    context = build_access_context(db, current_user)
    flow = _scoped_flow(db, context, flow_id)
    authorize(context, "employees.manage", property_id=flow.get("property_id"), department_id=flow.get("department_id"))
    values = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in body.model_dump(exclude_none=True).items()}
    if body.manager_id:
        manager = db.table("users").select("id,full_name,phone").eq("id", body.manager_id).eq("org_id", context.org_id).limit(1).execute().data or []
        if not manager:
            raise HTTPException(400, "Manager must belong to the same organization")
        values.update(manager_name=manager[0].get("full_name"), manager_phone=manager[0].get("phone"))
    return {"flow": (db.table("onboarding_flows").update(values).eq("id", flow_id).eq("org_id", context.org_id).execute().data or [values])[0]}


@router.post("/flows/{flow_id}/recalculate")
async def recalculate_flow(flow_id: str, db: SupabaseClient, current_user: CurrentUser):
    context = build_access_context(db, current_user)
    flow = _scoped_flow(db, context, flow_id)
    tasks = db.table("onboarding_tasks").select("*").eq("flow_id", flow_id).execute().data or []
    letter = db.table("appointment_letters").select("esign_status").eq("flow_id", flow_id).order("generated_at", desc=True).limit(1).execute().data or []
    flow["appointment_signed"] = bool(letter and letter[0].get("esign_status") == "signed")
    return {"flow": recalculate_and_persist(db, flow, tasks)}


# ─────────────────────────────────────────────────────────────────────────────
# POST /flows/init
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/flows/init")
async def init_flow(
    body: InitFlowRequest,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """
    Initialise an onboarding flow for a candidate.
    Creates all 5-stage checklist tasks automatically.
    """
    context = build_access_context(db, current_user)
    authorize(context, "employees.manage")
    user_id, org_id = context.user_id, context.org_id

    # Fetch candidate
    try:
        cand_row = db.table("candidates").select("*").eq("id", body.candidate_id).eq("org_id", org_id).single().execute()
        candidate = cand_row.data or {}
    except Exception:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Fetch job
    job = {}
    if body.job_id:
        try:
            job_row = db.table("jobs").select("*").eq("id", body.job_id).eq("org_id", org_id).single().execute()
            job = job_row.data or {}
        except Exception:
            raise HTTPException(status_code=404, detail="Job not found")
    authorize(context, "employees.manage", property_id=job.get("property_id"), department_id=job.get("department_id"))

    joining = None
    if body.joining_date:
        try:
            joining = date.fromisoformat(body.joining_date)
        except ValueError:
            pass

    result = init_onboarding_flow(
        supabase=db,
        candidate=candidate,
        job=job,
        org_id=org_id,
        joining_date=joining,
        gross_monthly_inr=body.gross_monthly_inr,
        triggered_by=user_id,
    )

    # If salary provided, generate CTC breakup
    ctc = None
    if body.gross_monthly_inr:
        ctc = compute_ctc_breakup(body.gross_monthly_inr)

    return {**result, "ctc_breakup": ctc}


# ─────────────────────────────────────────────────────────────────────────────
# GET /flows
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/flows")
async def list_flows(
    status: Optional[str] = Query(None),
    at_risk_only: bool = Query(False),
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """List all onboarding flows for the organisation."""
    context = build_access_context(db, current_user)
    authorize(context, "employees.read")
    org_id = context.org_id

    try:
        q = (
            db.table("v_onboarding_dashboard")
            .select("*")
            .eq("org_id", org_id)
            .order("joining_date", desc=False)
        )
        if status:
            q = q.eq("status", status)
        if at_risk_only:
            q = q.eq("is_at_risk", True)
        rows = q.execute().data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch flows: {e}")

    return {"total": len(rows), "flows": rows}


# ─────────────────────────────────────────────────────────────────────────────
# GET /flows/{flow_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/flows/{flow_id}")
async def get_flow(
    flow_id: str,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Get a single onboarding flow with all tasks grouped by stage."""
    context = build_access_context(db, current_user)
    scoped = _scoped_flow(db, context, flow_id)
    try:
        flow_row = db.table("v_onboarding_dashboard").select("*").eq("id", flow_id).eq("org_id", context.org_id).single().execute()
        flow = flow_row.data or scoped
    except Exception:
        flow = scoped

    # Fetch tasks
    try:
        tasks_row = (
            db.table("onboarding_tasks")
            .select("*")
            .eq("flow_id", flow_id)
            .order("sort_order", desc=False)
            .execute()
        )
        tasks = tasks_row.data or []
    except Exception:
        tasks = []

    # Group tasks by stage
    stages = {}
    for stage_key in CHECKLIST_TEMPLATE.keys():
        stage_tasks = [t for t in tasks if t["stage"] == stage_key]
        done = sum(1 for t in stage_tasks if t["status"] in ("completed", "waived"))
        stages[stage_key] = {
            "tasks": stage_tasks,
            "total": len(stage_tasks),
            "done":  done,
            "pct":   round(done / max(len(stage_tasks), 1) * 100),
        }

    # Letter status
    try:
        letter_row = (
            db.table("appointment_letters")
            .select("id,esign_status,generated_at,esign_url,signed_letter_url,letter_url")
            .eq("flow_id", flow_id)
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
        )
        letter = letter_row.data[0] if letter_row.data else None
    except Exception:
        letter = None

    # PF/ESIC forms
    try:
        forms_row = (
            db.table("pf_esic_declarations")
            .select("id,form_type,status,submitted_at")
            .eq("flow_id", flow_id)
            .execute()
        )
        forms = forms_row.data or []
    except Exception:
        forms = []

    # Pre-boarding messages
    try:
        msgs_row = (
            db.table("preboarding_messages")
            .select("id,template_label,scheduled_for,sent_at,status")
            .eq("flow_id", flow_id)
            .order("scheduled_for", desc=False)
            .execute()
        )
        preboarding_msgs = msgs_row.data or []
    except Exception:
        preboarding_msgs = []

    return {
        "flow":             flow,
        "stages":           stages,
        "appointment_letter": letter,
        "pf_esic_forms":    forms,
        "preboarding":      preboarding_msgs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /flows/{flow_id}/tasks/{task_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.patch("/flows/{flow_id}/tasks/{task_id}")
async def complete_task(
    flow_id: str,
    task_id: str,
    body: CompleteTaskRequest,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Mark an onboarding task as completed."""
    context = build_access_context(db, current_user)
    flow = _scoped_flow(db, context, flow_id)
    authorize(context, "employees.manage", property_id=flow.get("property_id"), department_id=flow.get("department_id"))
    user_id = context.user_id
    update = {
        "status":       "completed",
        "completed_at": datetime.utcnow().isoformat(),
        "completed_by": user_id,
    }
    if body.notes:
        update["notes"] = body.notes
    if body.document_url:
        update["document_url"] = body.document_url

    try:
        res = (
            db.table("onboarding_tasks")
            .update(update)
            .eq("id", task_id)
            .eq("flow_id", flow_id)
            .execute()
        )
        tasks = db.table("onboarding_tasks").select("*").eq("flow_id", flow_id).execute().data or []
        updated_flow = recalculate_and_persist(db, flow, tasks)
        return {"task": res.data[0] if res.data else update, "flow": updated_flow}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update task: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /flows/{flow_id}/appointment-letter
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/flows/{flow_id}/appointment-letter")
async def generate_letter(
    flow_id: str,
    body: GenerateLetterRequest,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """
    Generate an Indian Appointment Letter with CTC breakup for a flow.
    Stores the HTML letter and computed CTC in appointment_letters table.
    """
    context = build_access_context(db, current_user)
    flow = _scoped_flow(db, context, flow_id)
    authorize(context, "employees.manage", property_id=flow.get("property_id"), department_id=flow.get("department_id"))
    user_id, org_id = context.user_id, context.org_id

    # Fetch candidate
    try:
        cand_row = db.table("candidates").select("*").eq("id", flow["candidate_id"]).single().execute()
        candidate = cand_row.data or {}
    except Exception:
        candidate = {}

    # Fetch org
    org = _get_org(db, org_id or "")
    org_name    = org.get("name") or "HospRecruit Organisation"
    org_address = org.get("address") or "India"

    # Compute CTC
    ctc = compute_ctc_breakup(body.gross_monthly_inr)

    # Parse joining date
    joining_date = None
    if flow.get("joining_date"):
        try:
            joining_date = date.fromisoformat(str(flow["joining_date"]))
        except ValueError:
            pass

    # Generate HTML
    letter_html = generate_appointment_letter_html(
        org_name=org_name,
        org_address=org_address,
        candidate_name=flow.get("candidate_name") or "Candidate",
        candidate_address=body.candidate_address,
        role_title=flow.get("role_title") or "Staff",
        department=flow.get("department") or "",
        property_name=flow.get("property_name") or org_name,
        joining_date=joining_date or date.today(),
        ctc=ctc,
        probation_months=body.probation_months,
        notice_period_days=body.notice_period_days,
    )

    # Upsert letter record
    letter_payload = {
        "flow_id":          flow_id,
        "org_id":           org_id,
        "candidate_id":     flow.get("candidate_id"),
        "gross_monthly_inr": body.gross_monthly_inr,
        "ctc_breakup":      ctc,
        "letter_html":      letter_html,
        "probation_months": body.probation_months,
        "notice_period_days": body.notice_period_days,
        "esign_status":     "not_requested",
        "generated_by":     user_id,
    }

    try:
        res = db.table("appointment_letters").upsert(
            letter_payload, on_conflict="flow_id"
        ).execute()
        letter = res.data[0] if res.data else letter_payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save letter: {e}")

    return {
        "letter_id":   letter.get("id"),
        "ctc_breakup": ctc,
        "letter_html": letter_html,
        "esign_status": "not_requested",
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /flows/{flow_id}/appointment-letter
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/flows/{flow_id}/appointment-letter")
async def get_letter(
    flow_id: str,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Get the generated appointment letter for a flow."""
    context = build_access_context(db, current_user)
    _scoped_flow(db, context, flow_id)
    try:
        row = (
            db.table("appointment_letters")
            .select("*")
            .eq("flow_id", flow_id)
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
        )
        if not row.data:
            raise HTTPException(status_code=404, detail="No letter generated for this flow yet.")
        return row.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /flows/{flow_id}/appointment-letter/esign
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/flows/{flow_id}/appointment-letter/esign")
async def request_esign(
    flow_id: str,
    body: ESignRequest,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """
    Request Aadhaar eSign for an appointment letter via Leegality, Digio, or demo.
    Sends the sign URL to HR for forwarding to the candidate.
    """
    context = build_access_context(db, current_user)
    flow = _scoped_flow(db, context, flow_id)
    authorize(context, "employees.manage", property_id=flow.get("property_id"), department_id=flow.get("department_id"))
    # Fetch letter
    try:
        letter_row = (
            db.table("appointment_letters")
            .select("*")
            .eq("flow_id", flow_id)
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
        )
        if not letter_row.data:
            raise HTTPException(status_code=404, detail="Generate appointment letter first.")
        letter = letter_row.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Fetch candidate for phone/email
    try:
        cand_row = db.table("candidates").select("*").eq("id", letter["candidate_id"]).single().execute()
        candidate = cand_row.data or {}
    except Exception:
        candidate = {}

    cand_name  = candidate.get("first_name", "") + " " + candidate.get("last_name", "")
    cand_phone = candidate.get("phone") or ""
    cand_email = candidate.get("email") or ""
    doc_url    = letter.get("letter_url") or ""

    adapter = ESignAdapter(provider=body.provider)
    result = await adapter.create_sign_request(
        document_url=doc_url,
        signer_name=cand_name.strip(),
        signer_phone=cand_phone,
        signer_email=cand_email,
        callback_url=body.callback_url,
    )

    # Update letter record
    try:
        db.table("appointment_letters").update({
            "esign_status":     "requested",
            "esign_provider":   result["provider"],
            "esign_request_id": result["sign_request_id"],
            "esign_url":        result["sign_url"],
        }).eq("id", letter["id"]).execute()
    except Exception as e:
        logger.error(f"Failed to update esign status: {e}")

    return {
        "sign_request_id": result["sign_request_id"],
        "sign_url":        result["sign_url"],
        "provider":        result["provider"],
        "status":          "requested",
        "candidate_name":  cand_name.strip(),
        "candidate_phone": cand_phone,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /flows/{flow_id}/pf-form2
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/flows/{flow_id}/pf-form2")
async def generate_pf_form(
    flow_id: str,
    body: PFFormRequest,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Generate PF Form 2 (Nomination & Declaration) for a flow."""
    context = build_access_context(db, current_user)
    flow = _scoped_flow(db, context, flow_id)
    authorize(context, "employees.manage", property_id=flow.get("property_id"), department_id=flow.get("department_id"))
    org_id = context.org_id

    try:
        cand_row = db.table("candidates").select("*").eq("id", flow["candidate_id"]).single().execute()
        candidate = cand_row.data or {}
    except Exception:
        candidate = {}

    joining_date = date.today()
    if flow.get("joining_date"):
        try:
            joining_date = date.fromisoformat(str(flow["joining_date"]))
        except ValueError:
            pass

    org = _get_org(db, org_id or "")
    form_data = generate_pf_form2_data(
        candidate=candidate,
        joining_date=joining_date,
        org_name=org.get("name") or "Organisation",
        org_pf_code=body.org_pf_code,
    )

    payload = {
        "flow_id":      flow_id,
        "org_id":       org_id,
        "candidate_id": flow.get("candidate_id"),
        "form_type":    "pf_form2",
        "form_data":    form_data,
        "status":       "draft",
    }

    try:
        res = db.table("pf_esic_declarations").insert(payload).execute()
        return {"form": res.data[0] if res.data else payload, "form_data": form_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save PF Form 2: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /flows/{flow_id}/esic-declaration
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/flows/{flow_id}/esic-declaration")
async def generate_esic_form(
    flow_id: str,
    body: PFFormRequest,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Generate ESIC Declaration Form for a flow."""
    context = build_access_context(db, current_user)
    flow = _scoped_flow(db, context, flow_id)
    authorize(context, "employees.manage", property_id=flow.get("property_id"), department_id=flow.get("department_id"))
    org_id = context.org_id

    try:
        cand_row = db.table("candidates").select("*").eq("id", flow["candidate_id"]).single().execute()
        candidate = cand_row.data or {}
    except Exception:
        candidate = {}

    joining_date = date.today()
    if flow.get("joining_date"):
        try:
            joining_date = date.fromisoformat(str(flow["joining_date"]))
        except ValueError:
            pass

    org = _get_org(db, org_id or "")
    form_data = generate_esic_declaration_data(
        candidate=candidate,
        joining_date=joining_date,
        org_name=org.get("name") or "Organisation",
        org_esic_code=body.org_esic_code,
    )

    payload = {
        "flow_id":      flow_id,
        "org_id":       org_id,
        "candidate_id": flow.get("candidate_id"),
        "form_type":    "esic_declaration",
        "form_data":    form_data,
        "status":       "draft",
    }

    try:
        res = db.table("pf_esic_declarations").insert(payload).execute()
        return {"form": res.data[0] if res.data else payload, "form_data": form_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save ESIC Declaration: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /flows/{flow_id}/preboarding/schedule
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/flows/{flow_id}/preboarding/schedule")
async def schedule_preboarding(
    flow_id: str,
    body: SchedulePreboardingRequest,
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Schedule WhatsApp pre-boarding sequence for a candidate."""
    context = build_access_context(db, current_user)
    flow = _scoped_flow(db, context, flow_id)
    authorize(context, "employees.manage", property_id=flow.get("property_id"), department_id=flow.get("department_id"))
    org_id = context.org_id

    # Fetch candidate for phone
    try:
        cand_row = db.table("candidates").select("phone,expected_salary_inr,current_location").eq(
            "id", flow["candidate_id"]
        ).single().execute()
        candidate = cand_row.data or {}
    except Exception:
        candidate = {}

    # Fetch sequence config
    try:
        seq_q = db.table("preboarding_sequences").select("*").eq("is_active", True)
        if body.sequence_id:
            seq_q = seq_q.eq("id", body.sequence_id)
        seq_row = seq_q.limit(1).execute()
        sequence = seq_row.data[0] if seq_row.data else {}
    except Exception:
        sequence = {}

    days_config = sequence.get("days_config") or []
    if not days_config:
        raise HTTPException(status_code=400, detail="No active pre-boarding sequence found. Run the seed migration.")

    joining_date = date.today()
    if flow.get("joining_date"):
        try:
            joining_date = date.fromisoformat(str(flow["joining_date"]))
        except ValueError:
            pass

    offer_date = date.today()
    if flow.get("offer_date"):
        try:
            offer_date = date.fromisoformat(str(flow["offer_date"]))
        except ValueError:
            pass

    phone = candidate.get("phone") or ""
    if not phone:
        raise HTTPException(status_code=400, detail="Candidate has no phone number on record.")

    net_monthly = 0
    try:
        letter_row = (
            db.table("appointment_letters")
            .select("ctc_breakup")
            .eq("flow_id", flow_id)
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
        )
        if letter_row.data:
            net_monthly = letter_row.data[0].get("ctc_breakup", {}).get("net_monthly", 0)
    except Exception:
        pass

    msgs = schedule_preboarding_messages(
        flow_id=flow_id,
        org_id=org_id or "",
        candidate_id=flow["candidate_id"],
        candidate_phone=phone,
        candidate_name=flow.get("candidate_name") or "Candidate",
        role_title=flow.get("role_title") or "Staff",
        property_name=flow.get("property_name") or "the property",
        joining_date=joining_date,
        offer_date=offer_date,
        net_monthly=net_monthly,
        manager_name=flow.get("manager_name") or "Your Manager",
        department=flow.get("department") or "",
        reporting_location=flow.get("reporting_location") or flow.get("property_name") or "",
        reporting_time=flow.get("reporting_time") or "09:00 AM",
        sequence_config=days_config,
    )

    try:
        db.table("preboarding_messages").insert(msgs).execute()
        db.table("onboarding_flows").update({
            "preboarding_started_at": datetime.utcnow().isoformat(),
            "preboarding_sequence_id": sequence.get("id"),
        }).eq("id", flow_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save preboarding messages: {e}")

    return {
        "scheduled": len(msgs),
        "messages": [
            {
                "template":      m["template_key"],
                "label":         m["template_label"],
                "scheduled_for": m["scheduled_for"],
                "status":        m["status"],
                "preview":       m["message_body"][:120] + "..." if len(m["message_body"]) > 120 else m["message_body"],
            }
            for m in msgs
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /dashboard
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def onboarding_dashboard(
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Onboarding dashboard: summary stats + at-risk candidates."""
    context = build_access_context(db, current_user)
    authorize(context, "employees.read")
    org_id = context.org_id

    try:
        flows = (
            db.table("v_onboarding_dashboard")
            .select("*")
            .eq("org_id", org_id)
            .execute()
        ).data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch dashboard: {e}")

    active     = [f for f in flows if f["status"] == "active"]
    at_risk    = [f for f in flows if f.get("is_at_risk")]
    completed  = [f for f in flows if f["status"] == "completed"]
    avg_pct    = round(
        sum(f.get("completion_pct", 0) or 0 for f in active) / max(len(active), 1), 1
    )

    return {
        "stats": {
            "active_flows":       len(active),
            "at_risk_count":      len(at_risk),
            "completed_this_month": len(completed),
            "avg_completion_pct": avg_pct,
        },
        "at_risk":  at_risk,
        "recent":   sorted(flows, key=lambda x: x.get("created_at") or "", reverse=True)[:20],
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /at-risk
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/at-risk")
async def get_at_risk(
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Return flows where joining is within 7 days and completion < 50%."""
    context = build_access_context(db, current_user)
    authorize(context, "employees.read")
    org_id = context.org_id

    try:
        rows = (
            db.table("v_onboarding_dashboard")
            .select("*")
            .eq("org_id", org_id)
            .eq("is_at_risk", True)
            .order("days_until_joining", desc=False)
            .execute()
        ).data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"at_risk_count": len(rows), "flows": rows}


# ─────────────────────────────────────────────────────────────────────────────
# POST /send-preboarding  (triggered by cron or webhook)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/send-preboarding")
async def trigger_preboarding_sends(
    db: SupabaseClient = None,
    current_user: CurrentUser = None,
):
    """Send all due WhatsApp pre-boarding messages. Typically called by a cron job."""
    context = build_access_context(db, current_user)
    authorize(context, "employees.manage")
    sent = send_due_preboarding_messages(db, context.org_id)
    return {"sent": sent}


# ─────────────────────────────────────────────────────────────────────────────
# POST /ctc-preview  (helper — compute CTC without creating a flow)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/ctc-preview")
async def preview_ctc(
    gross_monthly_inr: int,
    current_user: CurrentUser = None,
):
    """Compute CTC breakup without creating any records."""
    if gross_monthly_inr <= 0:
        raise HTTPException(status_code=400, detail="Gross monthly must be positive.")
    return compute_ctc_breakup(gross_monthly_inr)
