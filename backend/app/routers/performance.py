"""Configurable hospitality appraisal cycles, reviews, KPIs and outcomes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.performance_service import calculate_overall_score, eligibility, normalize_kpi_score
from app.services.rbac_service import authorize, build_access_context

router = APIRouter(tags=["Performance Management"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


def _rows(result):
    return getattr(result, "data", None) or []


def _now():
    return datetime.utcnow().isoformat()


class KPITemplateCreate(BaseModel):
    department_name: str = Field(min_length=1, max_length=120)
    role_title: Optional[str] = Field(None, max_length=180)
    metric_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=180)
    description: Optional[str] = None
    unit: str = "SCORE"
    direction: str = "HIGHER_BETTER"
    target_value: Optional[float] = None
    min_value: Optional[float] = 0
    max_value: Optional[float] = 100
    default_weight: float = Field(25, gt=0, le=100)
    source: str = "MANAGER"

    @field_validator("direction")
    @classmethod
    def direction_allowed(cls, value):
        value = value.upper()
        if value not in {"HIGHER_BETTER", "LOWER_BETTER", "TARGET"}: raise ValueError("Invalid direction")
        return value


class CycleKPIInput(BaseModel):
    template_id: str
    weight: Optional[float] = Field(None, gt=0, le=100)
    department_id: Optional[str] = None
    role_title: Optional[str] = None


class CycleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    property_id: Optional[str] = None
    review_period_start: str
    review_period_end: str
    self_review_due_at: Optional[str] = None
    peer_review_due_at: Optional[str] = None
    manager_review_due_at: Optional[str] = None
    promotion_threshold: float = Field(80, ge=0, le=100)
    increment_threshold: float = Field(70, ge=0, le=100)
    kpis: list[CycleKPIInput] = Field(min_length=1)

    @field_validator("review_period_start", "review_period_end")
    @classmethod
    def valid_cycle_date(cls, value):
        date.fromisoformat(value)
        return value


class ReviewCreate(BaseModel):
    employee_id: str


class PeerAssign(BaseModel):
    reviewer_id: str


class CycleStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_cycle_status(cls, value):
        value = value.upper()
        if value not in {"ACTIVE", "CALIBRATION", "CLOSED", "CANCELLED"}: raise ValueError("Invalid cycle status")
        return value


class ScoreInput(BaseModel):
    cycle_kpi_id: str
    actual_value: float
    evidence: Optional[str] = None


class ReviewSubmission(BaseModel):
    comments: Optional[str] = None
    strengths: Optional[str] = None
    development_areas: Optional[str] = None
    scores: list[ScoreInput] = Field(default_factory=list)


class GuestFeedbackCreate(BaseModel):
    employee_id: str
    review_id: Optional[str] = None
    property_id: Optional[str] = None
    source: str = "MANUAL"
    rating: float = Field(ge=1, le=5)
    complaint_count: int = Field(0, ge=0)
    compliment_count: int = Field(0, ge=0)
    feedback_date: str
    reference_id: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("feedback_date")
    @classmethod
    def valid_feedback_date(cls, value):
        date.fromisoformat(value)
        return value


class OutcomeCreate(BaseModel):
    increment_percent: Optional[float] = Field(None, ge=0, le=100)
    promotion_role_title: Optional[str] = None
    recommendation_reason: str = Field(min_length=3)


class OutcomeDecision(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def decision(cls, value):
        value = value.upper()
        if value not in {"APPROVED", "REJECTED"}: raise ValueError("Use APPROVED or REJECTED")
        return value


def _employee(db, org_id, employee_id):
    rows = _rows(db.table("users").select("id,org_id,active_property_id,department_id,job_title,manager_id")
                 .eq("id", employee_id).eq("org_id", org_id).limit(1).execute())
    if not rows: raise HTTPException(404, "Employee not found")
    return rows[0]


def _review(db, org_id, review_id):
    rows = _rows(db.table("employee_performance_reviews").select("*")
                 .eq("id", review_id).eq("org_id", org_id).limit(1).execute())
    if not rows: raise HTTPException(404, "Performance review not found")
    return rows[0]


def _cycle(db, org_id, cycle_id):
    rows = _rows(db.table("performance_appraisal_cycles").select("*")
                 .eq("id", cycle_id).eq("org_id", org_id).limit(1).execute())
    if not rows: raise HTTPException(404, "Appraisal cycle not found")
    return rows[0]


def _audit(db, context, action, entity_type, entity_id, metadata=None):
    db.table("employee_lifecycle_events").insert({
        "org_id": context.org_id, "employee_id": metadata.get("employee_id") if metadata else context.user_id,
        "event_type": action, "title": action.replace("_", " ").title(), "source_table": entity_type,
        "source_id": entity_id, "visibility": "MANAGER", "created_by": context.user_id,
        "metadata": metadata or {},
    }).execute()


def _applicable_kpis(db, review):
    rows = _rows(db.table("performance_cycle_kpis").select("*").eq("cycle_id", review["cycle_id"])
                 .eq("is_active", True).order("name").execute())
    role = str(review.get("role_title_snapshot") or "").strip().lower()
    return [row for row in rows if (not row.get("department_id") or row.get("department_id") == review.get("department_id"))
            and (not row.get("role_title") or str(row.get("role_title")).strip().lower() == role)]


@router.get("/kpi-templates")
async def list_kpi_templates(supabase: SupabaseClient, user: CurrentUser,
                             department: Optional[str] = Query(None), role_title: Optional[str] = Query(None)):
    context = build_access_context(supabase, user); authorize(context, "performance.read")
    q = supabase.table("performance_kpi_templates").select("*").eq("is_active", True).or_(f"org_id.is.null,org_id.eq.{context.org_id}")
    if department: q = q.eq("department_name", department)
    if role_title: q = q.or_(f"role_title.is.null,role_title.eq.{role_title}")
    return _rows(q.order("department_name").execute())


@router.post("/kpi-templates", status_code=201)
async def create_kpi_template(body: KPITemplateCreate, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "performance.manage")
    payload = {"org_id": context.org_id, **body.model_dump(), "created_by": context.user_id}
    try: rows = _rows(supabase.table("performance_kpi_templates").insert(payload).execute())
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower(): raise HTTPException(409, "KPI metric key already exists for this scope")
        raise
    return rows[0] if rows else payload


@router.get("/cycles")
async def list_cycles(supabase: SupabaseClient, user: CurrentUser, status: Optional[str] = Query(None)):
    context = build_access_context(supabase, user); authorize(context, "performance.read")
    q = supabase.table("performance_appraisal_cycles").select("*").eq("org_id", context.org_id)
    if status: q = q.eq("status", status.upper())
    return _rows(q.order("review_period_end", desc=True).execute())


@router.post("/cycles", status_code=201)
async def create_cycle(body: CycleCreate, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); authorize(context, "performance.manage", property_id=body.property_id)
    if body.review_period_end < body.review_period_start: raise HTTPException(422, "review_period_end must not precede start")
    templates = _rows(supabase.table("performance_kpi_templates").select("*")
                      .in_("id", [item.template_id for item in body.kpis]).execute())
    by_id = {row["id"]: row for row in templates}
    if len(by_id) != len(set(item.template_id for item in body.kpis)): raise HTTPException(422, "One or more KPI templates were not found")
    pending_snapshots = []
    for item in body.kpis:
        template = by_id[item.template_id]
        pending_snapshots.append({"template_id": template["id"],
            "department_id": item.department_id, "role_title": item.role_title or template.get("role_title"),
            "name": template["name"], "description": template.get("description"), "unit": template["unit"],
            "direction": template["direction"], "target_value": template.get("target_value"),
            "min_value": template.get("min_value"), "max_value": template.get("max_value"),
            "weight": item.weight or template["default_weight"], "source": template["source"]})
    if abs(sum(float(row["weight"]) for row in pending_snapshots) - 100) > 0.01: raise HTTPException(422, "Cycle KPI weights must total 100")
    cycle_payload = body.model_dump(exclude={"kpis"}) | {"org_id": context.org_id, "created_by": context.user_id}
    rows = _rows(supabase.table("performance_appraisal_cycles").insert(cycle_payload).execute())
    if not rows: raise HTTPException(500, "Cycle could not be created")
    cycle = rows[0]
    snapshots = [{"cycle_id": cycle["id"], **row} for row in pending_snapshots]
    supabase.table("performance_cycle_kpis").insert(snapshots).execute()
    return {**cycle, "kpis": snapshots}


@router.get("/cycles/{cycle_id}")
async def cycle_detail(cycle_id: str, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); cycle = _cycle(supabase, context.org_id, cycle_id)
    authorize(context, "performance.read", property_id=cycle.get("property_id"))
    kpis = _rows(supabase.table("performance_cycle_kpis").select("*").eq("cycle_id", cycle_id)
                 .eq("is_active", True).order("name").execute())
    return {**cycle, "kpis": kpis}


@router.patch("/cycles/{cycle_id}/activate")
async def activate_cycle(cycle_id: str, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); cycle = _cycle(supabase, context.org_id, cycle_id)
    authorize(context, "performance.manage", property_id=cycle.get("property_id"))
    rows = _rows(supabase.table("performance_appraisal_cycles").update({"status":"ACTIVE","updated_at":_now()})
                 .eq("id", cycle_id).eq("org_id", context.org_id).execute())
    return rows[0] if rows else {**cycle, "status":"ACTIVE"}


@router.patch("/cycles/{cycle_id}/status")
async def update_cycle_status(cycle_id: str, body: CycleStatusUpdate, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); cycle = _cycle(supabase, context.org_id, cycle_id)
    authorize(context, "performance.manage", property_id=cycle.get("property_id"))
    rows = _rows(supabase.table("performance_appraisal_cycles").update({"status":body.status,"updated_at":_now()})
                 .eq("id",cycle_id).eq("org_id",context.org_id).execute())
    return rows[0] if rows else {**cycle,"status":body.status}


@router.post("/cycles/{cycle_id}/reviews", status_code=201)
async def create_review(cycle_id: str, body: ReviewCreate, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); cycle = _cycle(supabase, context.org_id, cycle_id)
    employee = _employee(supabase, context.org_id, body.employee_id)
    authorize(context, "performance.manage", property_id=employee.get("active_property_id"), department_id=employee.get("department_id"))
    if cycle["status"] not in {"DRAFT","ACTIVE"}: raise HTTPException(409, "Cycle is not open for reviews")
    if cycle.get("property_id") and cycle["property_id"] != employee.get("active_property_id"):
        raise HTTPException(422, "Employee is not assigned to the cycle property")
    payload = {"org_id":context.org_id,"employee_id":body.employee_id,"property_id":employee.get("active_property_id"),
        "department_id":employee.get("department_id"),"cycle_id":cycle_id,"review_period_start":cycle["review_period_start"],
        "review_period_end":cycle["review_period_end"],"role_title_snapshot":employee.get("job_title"),"status":"DRAFT"}
    try: rows = _rows(supabase.table("employee_performance_reviews").insert(payload).execute())
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower(): raise HTTPException(409, "Employee already has a review in this cycle")
        raise
    return rows[0] if rows else payload


def _submit_scores(db, context, review, submission, reviewer_type):
    kpis = _applicable_kpis(db, review)
    by_id = {row["id"]: row for row in kpis}
    invalid = [row.cycle_kpi_id for row in submission.scores if row.cycle_kpi_id not in by_id]
    if invalid: raise HTTPException(422, "Score references KPI outside this appraisal cycle")
    payloads = [{"org_id":context.org_id,"review_id":review["id"],"cycle_kpi_id":row.cycle_kpi_id,
        "reviewer_id":context.user_id,"reviewer_type":reviewer_type,"actual_value":row.actual_value,
        "normalized_score":normalize_kpi_score(by_id[row.cycle_kpi_id],row.actual_value),"evidence":row.evidence,
        "updated_at":_now()} for row in submission.scores]
    if payloads: db.table("performance_kpi_scores").upsert(payloads,
        on_conflict="review_id,cycle_kpi_id,reviewer_id,reviewer_type").execute()
    contribution = {"org_id":context.org_id,"review_id":review["id"],"reviewer_id":context.user_id,
        "reviewer_type":reviewer_type,"comments":submission.comments,"strengths":submission.strengths,
        "development_areas":submission.development_areas,"submitted_at":_now()}
    db.table("performance_review_contributions").upsert(contribution,
        on_conflict="review_id,reviewer_id,reviewer_type").execute()
    return kpis, payloads


@router.patch("/reviews/{review_id}/self-review")
async def submit_self_review(review_id: str, body: ReviewSubmission, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); review = _review(supabase, context.org_id, review_id)
    if review["employee_id"] != context.user_id: raise HTTPException(403, "Only the employee may submit this self-review")
    _submit_scores(supabase, context, review, body, "SELF")
    supabase.table("employee_performance_reviews").update({"self_review":body.model_dump(),"self_submitted_at":_now(),"updated_at":_now()}).eq("id",review_id).execute()
    return {"review_id":review_id,"submitted":True,"reviewer_type":"SELF"}


@router.post("/reviews/{review_id}/peers", status_code=201)
async def assign_peer(review_id: str, body: PeerAssign, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); review = _review(supabase, context.org_id, review_id)
    authorize(context, "performance.manage", property_id=review.get("property_id"), department_id=review.get("department_id"))
    if body.reviewer_id == review["employee_id"]: raise HTTPException(409, "Employee cannot be assigned as their own peer reviewer")
    _employee(supabase, context.org_id, body.reviewer_id)
    payload = {"org_id":context.org_id,"review_id":review_id,"reviewer_id":body.reviewer_id,
               "assigned_by":context.user_id,"status":"ASSIGNED"}
    try: rows = _rows(supabase.table("performance_peer_assignments").insert(payload).execute())
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower(): raise HTTPException(409, "Peer is already assigned")
        raise
    return rows[0] if rows else payload


@router.get("/reviews/{review_id}")
async def review_detail(review_id: str, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); review = _review(supabase, context.org_id, review_id)
    if review["employee_id"] != context.user_id:
        if "performance.manage" in context.permissions:
            authorize(context, "performance.manage", property_id=review.get("property_id"), department_id=review.get("department_id"))
        else:
            assigned = _rows(supabase.table("performance_peer_assignments").select("id").eq("review_id",review_id)
                             .eq("reviewer_id",context.user_id).eq("status","ASSIGNED").limit(1).execute())
            if not assigned: raise HTTPException(403, "You are not assigned to this appraisal")
    kpis = _applicable_kpis(supabase, review)
    return {**review, "kpis": kpis}


@router.post("/reviews/{review_id}/peer-review")
async def submit_peer_review(review_id: str, body: ReviewSubmission, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); review = _review(supabase, context.org_id, review_id)
    if review["employee_id"] == context.user_id: raise HTTPException(409, "Use self-review for your own appraisal")
    assigned = _rows(supabase.table("performance_peer_assignments").select("id,status").eq("review_id",review_id)
                     .eq("reviewer_id",context.user_id).eq("status","ASSIGNED").limit(1).execute())
    if not assigned: raise HTTPException(403, "You are not assigned as a peer reviewer for this appraisal")
    _submit_scores(supabase, context, review, body, "PEER")
    supabase.table("performance_peer_assignments").update({"status":"COMPLETED","completed_at":_now()})\
        .eq("id",assigned[0]["id"]).eq("reviewer_id",context.user_id).execute()
    return {"review_id":review_id,"submitted":True,"reviewer_type":"PEER"}


@router.patch("/reviews/{review_id}/manager-review")
async def submit_manager_review(review_id: str, body: ReviewSubmission, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user); review = _review(supabase, context.org_id, review_id)
    authorize(context, "performance.manage", property_id=review.get("property_id"), department_id=review.get("department_id"))
    if review["employee_id"] == context.user_id: raise HTTPException(409, "A manager cannot submit their own manager review")
    if not body.scores: raise HTTPException(422, "Manager review requires KPI scores")
    kpis, current = _submit_scores(supabase, context, review, body, "MANAGER")
    stored = _rows(supabase.table("performance_kpi_scores").select("*").eq("review_id", review_id).execute()) or current
    result = calculate_overall_score(kpis, stored); cycle = _cycle(supabase, context.org_id, review["cycle_id"])
    flags = eligibility(result["overall_score"], float(cycle["promotion_threshold"]), float(cycle["increment_threshold"]))
    update = {"overall_score":result["overall_score"],**flags,"manager_comments":body.comments,
        "strengths":body.strengths,"development_areas":body.development_areas,"reviewed_by":context.user_id,
        "reviewed_at":_now(),"manager_submitted_at":_now(),"status":"SHARED","updated_at":_now()}
    supabase.table("employee_performance_reviews").update(update).eq("id",review_id).eq("org_id",context.org_id).execute()
    _audit(supabase,context,"PERFORMANCE_REVIEW_SHARED","employee_performance_reviews",review_id,{"employee_id":review["employee_id"],"overall_score":result["overall_score"]})
    return {**update,"breakdown":result["breakdown"],"advisory_only":True}


@router.post("/guest-feedback", status_code=201)
async def add_guest_feedback(body: GuestFeedbackCreate, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase,user); employee = _employee(supabase,context.org_id,body.employee_id)
    authorize(context,"performance.manage",property_id=body.property_id or employee.get("active_property_id"),department_id=employee.get("department_id"))
    payload={"org_id":context.org_id,**body.model_dump(),"created_by":context.user_id}
    rows=_rows(supabase.table("performance_guest_feedback").insert(payload).execute())
    return rows[0] if rows else payload


@router.get("/employees/{employee_id}")
async def employee_performance(employee_id: str, supabase: SupabaseClient, user: CurrentUser):
    context=build_access_context(supabase,user); employee=_employee(supabase,context.org_id,employee_id)
    if employee_id != context.user_id: authorize(context,"performance.read",property_id=employee.get("active_property_id"),department_id=employee.get("department_id"))
    reviews=_rows(supabase.table("employee_performance_reviews").select("*").eq("org_id",context.org_id).eq("employee_id",employee_id).order("review_period_end",desc=True).execute())
    feedback=_rows(supabase.table("performance_guest_feedback").select("*").eq("org_id",context.org_id).eq("employee_id",employee_id).order("feedback_date",desc=True).execute())
    return {"employee":employee,"reviews":reviews,"guest_feedback":feedback}


@router.post("/reviews/{review_id}/outcome", status_code=201)
async def recommend_outcome(review_id: str, body: OutcomeCreate, supabase: SupabaseClient, user: CurrentUser):
    context=build_access_context(supabase,user); review=_review(supabase,context.org_id,review_id)
    authorize(context,"performance.manage",property_id=review.get("property_id"),department_id=review.get("department_id"))
    if review.get("overall_score") is None: raise HTTPException(409,"Manager review must be scored first")
    payload={"org_id":context.org_id,"review_id":review_id,"employee_id":review["employee_id"],**body.model_dump(),"recommended_by":context.user_id}
    rows=_rows(supabase.table("performance_outcome_recommendations").upsert(payload,on_conflict="review_id").execute())
    supabase.table("employee_performance_reviews").update({"outcome_status":"RECOMMENDED"}).eq("id",review_id).execute()
    return {**(rows[0] if rows else payload),"advisory_only":True,"payroll_updated":False,"employment_updated":False}


@router.patch("/outcomes/{outcome_id}")
async def decide_outcome(outcome_id: str, body: OutcomeDecision, supabase: SupabaseClient, user: CurrentUser):
    context=build_access_context(supabase,user); authorize(context,"performance.manage")
    rows=_rows(supabase.table("performance_outcome_recommendations").update({"status":body.status,
        "approved_by":context.user_id,"approved_at":_now(),"updated_at":_now()}).eq("id",outcome_id).eq("org_id",context.org_id).execute())
    if not rows: raise HTTPException(404,"Outcome recommendation not found")
    supabase.table("employee_performance_reviews").update({"outcome_status":body.status}).eq("id",rows[0]["review_id"]).eq("org_id",context.org_id).execute()
    return {**rows[0],"payroll_updated":False,"employment_updated":False}
