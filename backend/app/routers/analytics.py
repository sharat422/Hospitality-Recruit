"""Live, tenant-scoped recruitment analytics endpoints."""

from datetime import date, timedelta
from zoneinfo import ZoneInfo
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.rbac_service import authorize, build_access_context
from app.services.recruitment_analytics_service import aggregate
from app.services.workforce_analytics_service import aggregate_workforce
from app.services.executive_dashboard_service import DEFAULT_WIDGETS, compose_executive_dashboard

router = APIRouter()
CurrentUser = Annotated[dict, Depends(get_current_user)]


def rows(result: Any) -> list[dict]:
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


class CostBody(BaseModel):
    category: str = Field(pattern="^(JOB_BOARD|ADVERTISING|AGENCY|REFERRAL|RECRUITER|INTERVIEW|TRAVEL|BACKGROUND_CHECK|ONBOARDING|OTHER)$")
    amount_inr: float = Field(ge=0)
    incurred_on: date
    property_id: str | None = None
    department_id: str | None = None
    job_id: str | None = None
    recruiter_id: str | None = None
    source: str | None = None
    description: str | None = Field(default=None, max_length=1000)
    external_reference: str | None = Field(default=None, max_length=200)


class RevenueBody(BaseModel):
    property_id: str
    revenue_date: date
    amount_inr: float = Field(ge=0)
    source: str = Field(default="MANUAL", pattern="^(MANUAL|PMS|POS|ACCOUNTING_IMPORT)$")
    external_reference: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)


class WidgetPreferencesBody(BaseModel):
    visible_widgets: list[str]
    widget_order: list[str] = Field(default_factory=list)
    default_property_id: str | None = None
    default_date_range_days: int = Field(default=30, ge=1, le=366)


def apply_filters(query, *, property_id=None, department_id=None, job_id=None,
                  recruiter_id=None, source=None, date_from=None, date_to=None,
                  date_column="created_at"):
    if property_id:
        query = query.eq("property_id", property_id)
    if department_id:
        query = query.eq("department_id", department_id)
    if job_id:
        query = query.eq("job_id", job_id)
    if recruiter_id:
        query = query.eq("recruiter_id", recruiter_id)
    if source:
        query = query.eq("source", source.upper())
    if date_from:
        query = query.gte(date_column, date_from.isoformat())
    if date_to:
        query = query.lt(date_column, (date_to + timedelta(days=1)).isoformat())
    return query


def collect_metrics(supabase, user, *, property_id=None, department_id=None,
                    job_id=None, recruiter_id=None, source=None,
                    date_from=None, date_to=None):
    context = build_access_context(supabase, user)
    authorize(context, "reports.read", property_id=property_id, department_id=department_id)

    job_query = supabase.table("jobs").select(
        "id,status,openings_count,created_at,approved_at,filled_at,property_id,department_id,recruiter_id"
    ).eq("org_id", context.org_id)
    job_query = apply_filters(job_query, property_id=property_id, department_id=department_id,
                              job_id=job_id, recruiter_id=recruiter_id)
    jobs = rows(job_query.limit(10000).execute())
    job_ids = {item["id"] for item in jobs}

    application_query = supabase.table("applications").select(
        "id,candidate_id,job_id,property_id,department_id,recruiter_id,source,status,"
        "created_at,selected_at,offer_accepted_at,onboarding_at,hired_at"
    ).eq("org_id", context.org_id)
    application_query = apply_filters(
        application_query, property_id=property_id, department_id=department_id,
        job_id=job_id, recruiter_id=recruiter_id, source=source,
        date_from=date_from, date_to=date_to,
    )
    applications = rows(application_query.limit(10000).execute())
    if any((property_id, department_id, job_id, recruiter_id)):
        applications = [item for item in applications if item.get("job_id") in job_ids]

    cost_query = supabase.table("recruitment_cost_entries").select("*").eq("org_id", context.org_id)
    cost_query = apply_filters(
        cost_query, property_id=property_id, department_id=department_id,
        job_id=job_id, recruiter_id=recruiter_id, source=source,
        date_from=date_from, date_to=date_to, date_column="incurred_on",
    )
    costs = rows(cost_query.limit(10000).execute())

    candidate_ids = {item.get("candidate_id") for item in applications if item.get("candidate_id")}
    application_ids = {item["id"] for item in applications}
    ghosting = []
    candidate_users: dict[str, str] = {}
    performance = []
    referrals = []
    if candidate_ids:
        ghosting = rows(supabase.table("ghosting_risk_scores").select(
            "candidate_id,risk_level,risk_score"
        ).in_("candidate_id", list(candidate_ids)).execute())
        candidates = rows(supabase.table("candidates").select("id,user_id").in_(
            "id", list(candidate_ids)
        ).execute())
        candidate_users = {item["id"]: item["user_id"] for item in candidates if item.get("user_id")}
        employee_ids = set(candidate_users.values())
        if employee_ids:
            reviews = rows(supabase.table("employee_performance_reviews").select(
                "employee_id,overall_score,rating,reviewed_at,created_at"
            ).in_("employee_id", list(employee_ids)).order("reviewed_at", desc=True).execute())
            seen = set()
            performance = [item for item in reviews if not (item["employee_id"] in seen or seen.add(item["employee_id"]))]
    if application_ids:
        referrals = rows(supabase.table("referrals").select("application_id,status").in_(
            "application_id", list(application_ids)
        ).execute())

    metrics = aggregate(
        applications=applications, jobs=jobs, costs=costs, ghosting=ghosting,
        referrals=referrals, performance=performance, candidate_users=candidate_users,
    )
    metrics["data_source"] = "LIVE_DATABASE"
    metrics["filters_applied"] = {
        "property_id": property_id, "department_id": department_id, "job_id": job_id,
        "recruiter_id": recruiter_id, "source": source,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
    }
    return metrics


@router.get("/recruitment")
async def recruitment_analytics(
    user: CurrentUser, supabase: SupabaseClient,
    property_id: str | None = None, department_id: str | None = None,
    job_id: str | None = None, recruiter_id: str | None = None,
    source: str | None = None, date_from: date | None = None, date_to: date | None = None,
):
    return collect_metrics(supabase, user, property_id=property_id, department_id=department_id,
                           job_id=job_id, recruiter_id=recruiter_id, source=source,
                           date_from=date_from, date_to=date_to)


@router.get("/filters")
async def analytics_filters(user: CurrentUser, supabase: SupabaseClient):
    context = build_access_context(supabase, user)
    authorize(context, "reports.read")
    jobs = rows(supabase.table("jobs").select(
        "id,title,property_id,department_id,recruiter_id"
    ).eq("org_id", context.org_id).order("title").execute())
    departments = rows(supabase.table("property_departments").select(
        "id,name,property_id"
    ).eq("org_id", context.org_id).order("name").execute())
    recruiters = rows(supabase.table("users").select("id,full_name,email").eq(
        "org_id", context.org_id
    ).in_("role", ["recruiter", "hr_manager", "hiring_manager", "RECRUITER", "HR_MANAGER"]).execute())
    app_sources = rows(supabase.table("applications").select("source").eq("org_id", context.org_id).execute())
    sources = sorted({str(item["source"]).upper() for item in app_sources if item.get("source")})
    return {"jobs": jobs, "departments": departments, "recruiters": recruiters, "sources": sources}


@router.post("/costs", status_code=201)
async def create_recruitment_cost(body: CostBody, user: CurrentUser, supabase: SupabaseClient):
    context = build_access_context(supabase, user)
    authorize(context, "reports.financial", property_id=body.property_id, department_id=body.department_id)
    payload = {**body.model_dump(mode="json"), "org_id": context.org_id, "created_by": context.user_id}
    saved = rows(supabase.table("recruitment_cost_entries").insert(payload).execute())
    return saved[0] if saved else payload


@router.get("/costs")
async def list_recruitment_costs(user: CurrentUser, supabase: SupabaseClient):
    context = build_access_context(supabase, user)
    authorize(context, "reports.financial")
    return rows(supabase.table("recruitment_cost_entries").select("*").eq(
        "org_id", context.org_id
    ).order("incurred_on", desc=True).execute())


# Compatibility endpoints retained for existing dashboard consumers.
@router.get("/manager-dashboard")
async def manager_dashboard(user: CurrentUser, supabase: SupabaseClient):
    return collect_metrics(supabase, user)


@router.get("/job/{job_id}/pipeline")
async def job_pipeline(job_id: str, user: CurrentUser, supabase: SupabaseClient):
    metrics = collect_metrics(supabase, user, job_id=job_id)
    return {"job_id": job_id, "funnel": metrics["funnel"], "data_source": metrics["data_source"]}


@router.get("/cost-per-hire")
async def cost_per_hire(user: CurrentUser, supabase: SupabaseClient, days: int = Query(90, ge=1, le=730)):
    metrics = collect_metrics(supabase, user, date_from=date.today() - timedelta(days=days))
    return {**metrics["cost"], "currency": "INR", "period_days": days, "data_source": "LIVE_DATABASE"}


@router.get("/no-show-analysis")
async def no_show_analysis(user: CurrentUser, supabase: SupabaseClient, days: int = Query(30, ge=1, le=730)):
    metrics = collect_metrics(supabase, user, date_from=date.today() - timedelta(days=days))
    return {"ghosting": metrics["ghosting"], "period_days": days, "data_source": "LIVE_DATABASE",
            "note": "Ghosting risk is not presented as an observed interview no-show."}


@router.get("/workforce")
async def workforce_analytics(
    user: CurrentUser, supabase: SupabaseClient,
    property_id: str | None = None, department_id: str | None = None,
    role: str | None = None, employee_id: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
):
    """Authoritative workforce metrics with scoped hierarchy drilldowns."""
    context = build_access_context(supabase, user)
    authorize(context, "reports.read", property_id=property_id, department_id=department_id)
    authorize(context, "employees.read", property_id=property_id, department_id=department_id)
    include_financial = "reports.financial" in context.permissions

    employees = rows(supabase.table("users").select(
        "id,full_name,employee_code,role,job_title,employment_status,active_property_id,department_id"
    ).eq("org_id", context.org_id).execute())
    employee_ids = [item["id"] for item in employees]
    properties = rows(supabase.table("properties").select("id,name").eq("org_id", context.org_id).execute())
    departments = rows(supabase.table("property_departments").select(
        "id,name,property_id"
    ).eq("org_id", context.org_id).execute())
    jobs = rows(supabase.table("jobs").select(
        "id,title,role_type,status,openings_count,positions_available,property_id,department_id"
    ).eq("org_id", context.org_id).execute())
    if context.role not in {"OWNER", "GROUP_ADMIN_HR"}:
        allowed_properties = set(context.property_ids)
        if context.active_property_id:
            allowed_properties.add(context.active_property_id)
        employees = [item for item in employees if item.get("active_property_id") in allowed_properties]
        properties = [item for item in properties if item.get("id") in allowed_properties]
        departments = [item for item in departments if item.get("property_id") in allowed_properties]
        jobs = [item for item in jobs if item.get("property_id") in allowed_properties]
    job_ids = [item["id"] for item in jobs]
    applications = []
    if job_ids:
        applications = rows(supabase.table("applications").select("job_id,status").in_("job_id", job_ids).execute())

    attendance_query = supabase.table("attendance_daily_records").select(
        "employee_id,property_id,attendance_date,status,validation_status,overtime_minutes"
    ).eq("org_id", context.org_id).eq("validation_status", "VALIDATED")
    turnover_query = supabase.table("employee_turnover_history").select(
        "employee_id,property_id,department_id,event_type,effective_date"
    ).eq("org_id", context.org_id)
    if date_from:
        attendance_query = attendance_query.gte("attendance_date", date_from.isoformat())
        turnover_query = turnover_query.gte("effective_date", date_from.isoformat())
    if date_to:
        attendance_query = attendance_query.lte("attendance_date", date_to.isoformat())
        turnover_query = turnover_query.lte("effective_date", date_to.isoformat())
    attendance = rows(attendance_query.limit(50000).execute())
    turnover = rows(turnover_query.limit(10000).execute())

    engagement = rows(supabase.table("employee_engagement_scores").select(
        "employee_id,engagement_score"
    ).eq("org_id", context.org_id).is_("superseded_at", "null").execute())
    risks = rows(supabase.table("employee_retention_risk_scores").select(
        "employee_id,risk_score,risk_level"
    ).eq("org_id", context.org_id).is_("superseded_at", "null").execute())
    performance = rows(supabase.table("employee_performance_reviews").select(
        "employee_id,overall_score,rating,status,reviewed_at,created_at"
    ).eq("org_id", context.org_id).in_("status", ["SHARED", "ACKNOWLEDGED", "CLOSED"]).order(
        "reviewed_at", desc=True
    ).execute())

    payroll_items = []
    if include_financial:
        run_query = supabase.table("payroll_runs").select("id,period_year,period_month").eq(
            "org_id", context.org_id
        ).in_("status", ["APPROVED", "FINALIZED"])
        runs = rows(run_query.execute())
        selected_runs = []
        for run in runs:
            period = date(int(run["period_year"]), int(run["period_month"]), 1)
            if date_from and period < date_from.replace(day=1):
                continue
            if date_to and period > date_to.replace(day=1):
                continue
            selected_runs.append(run["id"])
        if selected_runs:
            payroll_items = rows(supabase.table("payroll_run_items").select(
                "employee_id,status,gross_inr,net_inr,employer_cost_inr,lop_inr,overtime_inr"
            ).in_("payroll_run_id", selected_runs).eq("status", "FINALIZED").execute())

    output = aggregate_workforce(
        employees=employees, jobs=jobs, applications=applications, attendance=attendance,
        payroll_items=payroll_items, turnover=turnover, engagement=engagement, risks=risks,
        performance=performance, properties=properties, departments=departments,
        include_financial=include_financial, property_id=property_id,
        department_id=department_id, role=role, employee_id=employee_id,
    )
    output.update({
        "data_source": "LIVE_DATABASE", "financial_visible": include_financial,
        "filters_applied": {"property_id": property_id, "department_id": department_id,
                            "role": role, "employee_id": employee_id,
                            "date_from": date_from, "date_to": date_to},
    })
    return output


@router.get("/executive-dashboard")
async def executive_dashboard(
    user: CurrentUser, supabase: SupabaseClient,
    property_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
):
    context = build_access_context(supabase, user)
    authorize(context, "reports.read", property_id=property_id)
    authorize(context, "employees.read", property_id=property_id)
    end = date_to or date.today()
    start = date_from or end - timedelta(days=29)
    if start > end:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    workforce = await workforce_analytics(user=user, supabase=supabase, property_id=property_id,
                                          date_from=start, date_to=end)
    financial_visible = bool(workforce["financial_visible"])
    employee_ids = [item["id"] for item in workforce.get("employees", [])]
    today = __import__("datetime").datetime.now(ZoneInfo("Asia/Kolkata")).date()

    attendance = []
    leave = []
    certificates = []
    if employee_ids:
        attendance = rows(supabase.table("attendance_daily_records").select(
            "employee_id,status,validation_status"
        ).in_("employee_id", employee_ids).eq("attendance_date", today.isoformat()).eq(
            "validation_status", "VALIDATED"
        ).execute())
        leave = rows(supabase.table("leave_requests").select(
            "employee_id,status,start_date,end_date"
        ).in_("employee_id", employee_ids).eq("status", "APPROVED").lte(
            "start_date", today.isoformat()
        ).gte("end_date", today.isoformat()).execute())
        certificates = rows(supabase.table("employee_certifications").select(
            "id,employee_id,expiry_date,status"
        ).in_("employee_id", employee_ids).in_("status", ["VERIFIED", "RENEWAL_DUE", "EXPIRED"]).lte(
            "expiry_date", (today + timedelta(days=30)).isoformat()
        ).execute())

    job_query = supabase.table("jobs").select("id").eq("org_id", context.org_id)
    if property_id:
        job_query = job_query.eq("property_id", property_id)
    elif context.role not in {"OWNER", "GROUP_ADMIN_HR"}:
        allowed = list(set(context.property_ids) | ({context.active_property_id} if context.active_property_id else set()))
        if allowed:
            job_query = job_query.in_("property_id", allowed)
    job_ids = [item["id"] for item in rows(job_query.execute())]
    compliance = []
    if job_ids:
        compliance = rows(supabase.table("compliance_tasks").select(
            "id,job_id,status,due_date,task_type"
        ).in_("job_id", job_ids).in_("status", ["pending", "PENDING", "in_progress", "IN_PROGRESS"]).execute())

    revenue = []
    if financial_visible:
        revenue_query = supabase.table("property_revenue_entries").select("property_id,amount_inr,revenue_date").eq(
            "org_id", context.org_id
        ).gte("revenue_date", start.isoformat()).lte("revenue_date", end.isoformat())
        if property_id:
            revenue_query = revenue_query.eq("property_id", property_id)
        revenue = rows(revenue_query.execute())

    app_query = supabase.table("applications").select("source,status,created_at").eq("org_id", context.org_id).gte(
        "created_at", start.isoformat()
    ).lt("created_at", (end + timedelta(days=1)).isoformat())
    if property_id:
        app_query = app_query.eq("property_id", property_id)
    elif context.role not in {"OWNER", "GROUP_ADMIN_HR"}:
        allowed = list(set(context.property_ids) | ({context.active_property_id} if context.active_property_id else set()))
        if allowed:
            app_query = app_query.in_("property_id", allowed)
    applications = rows(app_query.execute())
    dashboard = compose_executive_dashboard(
        workforce=workforce, today_attendance=attendance, approved_leave=leave,
        compliance_tasks=compliance, expiring_certificates=certificates,
        revenue_entries=revenue, applications=applications, financial_visible=financial_visible,
    )
    preferences = rows(supabase.table("executive_dashboard_preferences").select("*").eq(
        "org_id", context.org_id
    ).eq("user_id", context.user_id).limit(1).execute())
    dashboard.update({"data_source": "LIVE_DATABASE", "date_from": start, "date_to": end,
                      "scope": "GROUP" if context.role in {"OWNER", "GROUP_ADMIN_HR"} and not property_id else "PROPERTY",
                      "preferences": preferences[0] if preferences else {"visible_widgets": DEFAULT_WIDGETS, "widget_order": [], "default_date_range_days": 30}})
    return dashboard


@router.put("/executive-dashboard/preferences")
async def save_executive_preferences(body: WidgetPreferencesBody, user: CurrentUser, supabase: SupabaseClient):
    context = build_access_context(supabase, user)
    authorize(context, "reports.read", property_id=body.default_property_id)
    invalid = (set(body.visible_widgets) | set(body.widget_order)) - set(DEFAULT_WIDGETS)
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown dashboard widgets: {', '.join(sorted(invalid))}")
    payload = {**body.model_dump(), "org_id": context.org_id, "user_id": context.user_id,
               "updated_at": __import__("datetime").datetime.now().isoformat()}
    saved = rows(supabase.table("executive_dashboard_preferences").upsert(
        payload, on_conflict="org_id,user_id"
    ).execute())
    return saved[0] if saved else payload


@router.post("/executive-dashboard/revenue", status_code=201)
async def create_revenue_entry(body: RevenueBody, user: CurrentUser, supabase: SupabaseClient):
    context = build_access_context(supabase, user)
    authorize(context, "financial.manage", property_id=body.property_id)
    payload = {**body.model_dump(mode="json"), "org_id": context.org_id, "created_by": context.user_id}
    saved = rows(supabase.table("property_revenue_entries").insert(payload).execute())
    return saved[0] if saved else payload
