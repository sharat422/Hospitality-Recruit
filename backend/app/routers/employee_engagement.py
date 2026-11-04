"""Privacy-safe employee engagement, recognition and trend APIs."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.dependencies import SupabaseAdminClient, SupabaseClient
from app.core.security import get_current_user
from app.services.employee_engagement_service import (
    aggregate_comparison,
    calculate_engagement_score,
    submit_pulse_response,
)
from app.services.rbac_service import authorize, build_access_context

router = APIRouter(tags=["Employee Engagement"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


def rows(result):
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class SurveyCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    question_text: str = Field(min_length=5, max_length=1000)
    property_id: Optional[str] = None
    department_id: Optional[str] = None
    closes_at: Optional[str] = None
    is_anonymous: bool = True
    channels: list[Literal["PWA", "WHATSAPP", "WEB"]] = ["PWA", "WHATSAPP"]
    language_code: str = Field(default="en", max_length=10)
    min_reporting_group: int = Field(default=5, ge=3, le=50)


class SurveyResponse(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=1000)
    source: Literal["PWA", "WEB"] = "PWA"


class RecognitionCreate(BaseModel):
    employee_id: str
    category: Literal["GUEST_DELIGHT", "TEAMWORK", "SERVICE_EXCELLENCE", "INNOVATION", "SAFETY", "LEADERSHIP", "VALUES", "OTHER"]
    reason: str = Field(min_length=10, max_length=2000)
    recognition_points: int = Field(default=1, ge=0, le=100)
    is_public: bool = True


class RecognitionReview(BaseModel):
    status: Literal["APPROVED", "REJECTED"]


class AwardCreate(BaseModel):
    employee_id: str
    property_id: str
    department_id: Optional[str] = None
    award_year: int = Field(ge=2020, le=2100)
    award_month: int = Field(ge=1, le=12)
    citation: str = Field(min_length=10, max_length=2000)


def actor(db, context):
    found = rows(db.table("users").select("id,org_id,active_property_id,department_id,full_name").eq("id", context.user_id).eq("org_id", context.org_id).limit(1).execute())
    if not found:
        raise HTTPException(403, "Employee profile not found")
    return found[0]


def survey_or_404(db, org_id, survey_id, active=False):
    query = db.table("employee_pulse_surveys").select("*").eq("id", survey_id).eq("org_id", org_id)
    if active:
        query = query.eq("status", "ACTIVE")
    found = rows(query.limit(1).execute())
    if not found:
        raise HTTPException(404, "Pulse survey not found")
    return found[0]


@router.get("/surveys")
async def list_surveys(supabase: SupabaseClient, user: CurrentUser, status: str = Query("ACTIVE")):
    context = build_access_context(supabase, user)
    query = supabase.table("employee_pulse_surveys").select("id,title,question_text,property_id,department_id,scale_min,scale_max,is_anonymous,status,opens_at,closes_at,channels,language_code,min_reporting_group").eq("org_id", context.org_id)
    if status:
        query = query.eq("status", status.upper())
    output = rows(query.order("opens_at", desc=True).execute())
    participation = rows(supabase.table("employee_pulse_participation").select("survey_id").eq("employee_id", context.user_id).execute())
    answered = {x["survey_id"] for x in participation}
    return [{**item, "answered": item["id"] in answered} for item in output]


@router.post("/surveys", status_code=201)
async def create_survey(body: SurveyCreate, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "employees.manage", property_id=body.property_id, department_id=body.department_id)
    payload = {"org_id": context.org_id, **body.model_dump(), "created_by": context.user_id}
    saved = rows(supabase.table("employee_pulse_surveys").insert(payload).execute())
    return saved[0] if saved else payload


@router.post("/surveys/{survey_id}/respond", status_code=201)
async def respond(survey_id: str, body: SurveyResponse, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    survey = survey_or_404(supabase, context.org_id, survey_id, active=True)
    employee = actor(supabase, context)
    authorize(context, "attendance.read", property_id=employee.get("active_property_id"), owner_user_id=context.user_id)
    return submit_pulse_response(supabase, survey=survey, employee=employee, score=body.score, comment=body.comment, source=body.source)


def trend_points(responses):
    buckets = defaultdict(list)
    for item in responses:
        stamp = str(item.get("submitted_at") or "")[:10]
        if stamp:
            day = datetime.fromisoformat(stamp).date()
            week = (day - timedelta(days=day.weekday())).isoformat()
            buckets[week].append(float(item["score"]))
    return [{"week": key, "response_count": len(values), "average_score": round(sum(values) / len(values), 2)} for key, values in sorted(buckets.items())]


@router.get("/surveys/{survey_id}/analytics")
async def survey_analytics(survey_id: str, supabase: SupabaseClient, admin: SupabaseAdminClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "employees.read")
    survey = survey_or_404(supabase, context.org_id, survey_id)
    # Raw anonymous content is read only with the server credential after RBAC checks.
    responses = rows(admin.table("employee_pulse_responses").select("score,submitted_at,property_id,department_id").eq("survey_id", survey_id).eq("org_id", context.org_id).execute())
    minimum = int(survey.get("min_reporting_group") or 5)
    distribution = {str(value): sum(int(x["score"]) == value for x in responses) for value in range(int(survey["scale_min"]), int(survey["scale_max"]) + 1)}
    return {
        "survey_id": survey_id,
        "anonymous": bool(survey.get("is_anonymous")),
        "privacy": {"raw_responses_exposed": False, "minimum_reporting_group": minimum},
        "response_count": len(responses),
        "average_score": round(sum(float(x["score"]) for x in responses) / len(responses), 2) if responses else None,
        "distribution": distribution,
        "trend": trend_points(responses),
        "property_comparison": aggregate_comparison(responses, "property_id", minimum),
        "department_comparison": aggregate_comparison(responses, "department_id", minimum),
    }


@router.post("/recognitions", status_code=201)
async def nominate(body: RecognitionCreate, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    employee = rows(supabase.table("users").select("id,active_property_id,department_id").eq("id", body.employee_id).eq("org_id", context.org_id).limit(1).execute())
    if not employee:
        raise HTTPException(404, "Employee not found")
    authorize(context, "properties.read", property_id=employee[0].get("active_property_id"))
    payload = {"org_id": context.org_id, "property_id": employee[0].get("active_property_id"), "department_id": employee[0].get("department_id"), "nominated_by": context.user_id, **body.model_dump()}
    saved = rows(supabase.table("employee_recognitions").insert(payload).execute())
    return saved[0] if saved else payload


@router.get("/recognitions")
async def recognitions(supabase: SupabaseClient, user: CurrentUser, status: Optional[str] = None):
    context = build_access_context(supabase, user)
    query = supabase.table("employee_recognitions").select("*").eq("org_id", context.org_id)
    if status:
        query = query.eq("status", status.upper())
    return rows(query.order("created_at", desc=True).execute())


@router.patch("/recognitions/{recognition_id}/review")
async def review_recognition(recognition_id: str, body: RecognitionReview, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "employees.manage")
    saved = rows(supabase.table("employee_recognitions").update({"status": body.status, "reviewed_by": context.user_id, "reviewed_at": utcnow()}).eq("id", recognition_id).eq("org_id", context.org_id).execute())
    if not saved:
        raise HTTPException(404, "Recognition not found")
    return saved[0]


@router.post("/employee-of-month", status_code=201)
async def create_award(body: AwardCreate, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "employees.manage", property_id=body.property_id, department_id=body.department_id)
    approved = rows(supabase.table("employee_recognitions").select("id,category,recognition_points").eq("employee_id", body.employee_id).eq("org_id", context.org_id).eq("status", "APPROVED").execute())
    payload = {"org_id": context.org_id, **body.model_dump(), "recognition_summary": {"approved_count": len(approved), "points": sum(int(x.get("recognition_points") or 0) for x in approved)}, "approved_by": context.user_id}
    saved = rows(supabase.table("employee_of_month_awards").insert(payload).execute())
    return saved[0] if saved else payload


@router.get("/employee-of-month")
async def awards(supabase: SupabaseClient, user: CurrentUser, property_id: Optional[str] = None):
    context = build_access_context(supabase, user)
    authorize(context, "properties.read", property_id=property_id)
    query = supabase.table("employee_of_month_awards").select("*").eq("org_id", context.org_id)
    if property_id:
        query = query.eq("property_id", property_id)
    return rows(query.order("award_year", desc=True).order("award_month", desc=True).execute())


@router.post("/scores/{employee_id}/calculate")
async def calculate_score(employee_id: str, supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    authorize(context, "employees.manage")
    people = rows(supabase.table("users").select("id,active_property_id,department_id").eq("id", employee_id).eq("org_id", context.org_id).limit(1).execute())
    if not people:
        raise HTTPException(404, "Employee not found")
    employee = people[0]
    pulse = rows(supabase.table("employee_pulse_responses").select("score").eq("employee_id", employee_id).execute())
    attendance = rows(supabase.table("attendance_daily_records").select("status").eq("employee_id", employee_id).eq("validation_status", "VALIDATED").execute())
    training = rows(supabase.table("employee_training_records").select("status").eq("employee_id", employee_id).execute())
    recognition = rows(supabase.table("employee_recognitions").select("id").eq("employee_id", employee_id).eq("status", "APPROVED").execute())
    present = sum(x.get("status") in {"PRESENT", "LATE", "HALF_DAY"} for x in attendance)
    completed = sum(x.get("status") == "COMPLETED" for x in training)
    result = calculate_engagement_score({"pulse_average": sum(float(x["score"]) for x in pulse) / len(pulse) if pulse else None, "attendance_rate": present * 100 / len(attendance) if attendance else None, "training_completion_rate": completed * 100 / len(training) if training else None, "approved_recognitions": len(recognition)})
    supabase.table("employee_engagement_scores").update({"superseded_at": utcnow()}).eq("employee_id", employee_id).is_("superseded_at", "null").execute()
    payload = {"org_id": context.org_id, "employee_id": employee_id, "property_id": employee.get("active_property_id"), "department_id": employee.get("department_id"), **{key: result[key] for key in ("engagement_score", "engagement_level", "score_components", "data_quality", "model_type", "model_version")}, "calculated_by": context.user_id}
    saved = rows(supabase.table("employee_engagement_scores").insert(payload).execute())
    return {**(saved[0] if saved else payload), "disclaimer": result["disclaimer"]}


@router.get("/scores")
async def scores(supabase: SupabaseClient, user: CurrentUser, property_id: Optional[str] = None):
    context = build_access_context(supabase, user)
    authorize(context, "employees.read", property_id=property_id)
    query = supabase.table("employee_engagement_scores").select("*").eq("org_id", context.org_id).is_("superseded_at", "null")
    if property_id:
        query = query.eq("property_id", property_id)
    output = rows(query.order("engagement_score", desc=True).execute())
    ids = list({x["employee_id"] for x in output})
    people = rows(supabase.table("users").select("id,full_name,job_title").in_("id", ids).execute()) if ids else []
    names = {x["id"]: x for x in people}
    return [{**item, "employee": names.get(item["employee_id"], {})} for item in output]
