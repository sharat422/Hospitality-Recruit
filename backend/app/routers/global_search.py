"""Permission-aware, cross-domain application search."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import SupabaseAdminClient, SupabaseClient
from app.core.security import get_current_user
from app.services.global_search_service import (
    SEARCH_CATEGORIES, allowed_categories, complaint_search_allowed, department_allowed, make_result,
    normalize_query, property_allowed,
)
from app.services.rbac_service import build_access_context

router = APIRouter(tags=["Global Search"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


def rows(result) -> list[dict]:
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


def scoped(context, row: dict) -> bool:
    return property_allowed(context, str(row.get("property_id")) if row.get("property_id") else None) and department_allowed(
        context, str(row.get("department_id")) if row.get("department_id") else None
    )


def _fetch(db, table: str, columns: str, org_id: str, limit: int = 250) -> list[dict]:
    return rows(db.table(table).select(columns).eq("org_id", org_id).limit(limit).execute())


def collect_results(db, admin, context, query: str, categories: list[str]) -> list[dict]:
    found = []
    apps: list[dict] = []
    candidates: list[dict] = []
    jobs: list[dict] = []

    if set(categories) & {"applications", "candidates", "documents"}:
        apps = [r for r in _fetch(db, "applications", "id,candidate_id,job_id,job_role_id,status,source,property_id,department_id,created_at", context.org_id) if scoped(context, r)]
    scoped_candidate_ids = {str(r["candidate_id"]) for r in apps if r.get("candidate_id")}
    if set(categories) & {"candidates", "applications"}:
        candidates = _fetch(db, "candidates", "id,user_id,first_name,last_name,email,phone,city,location,pipeline_stage,source,org_id", context.org_id)
        if context.role not in {"OWNER", "GROUP_ADMIN_HR"}:
            candidates = [r for r in candidates if str(r.get("id")) in scoped_candidate_ids or r.get("user_id") == context.user_id]
    candidate_map = {str(r["id"]): r for r in candidates}

    if set(categories) & {"jobs", "applications"}:
        jobs = [r for r in _fetch(db, "jobs", "id,title,status,approval_status,property_id,department_id,org_id", context.org_id) if scoped(context, r)]
    job_map = {str(r["id"]): r for r in jobs}

    if "candidates" in categories:
        for r in candidates:
            name = f"{r.get('first_name') or ''} {r.get('last_name') or ''}".strip() or "Unnamed candidate"
            item = make_result(query=query, category="candidates", row_id=r["id"], title=name,
                subtitle=" · ".join(filter(None, [r.get("email"), r.get("phone"), r.get("city") or r.get("location")])),
                status=r.get("pipeline_stage"), url=f"/pipeline?candidate={r['id']}",
                searchable=[r.get("email"), r.get("phone"), r.get("source")])
            if item: found.append(item)

    if "employees" in categories:
        for r in _fetch(db, "users", "id,full_name,email,phone,employee_code,job_title,employment_status,active_property_id,department_id,org_id", context.org_id):
            scoped_row = {**r, "property_id": r.get("active_property_id")}
            if not scoped(context, scoped_row): continue
            item = make_result(query=query, category="employees", row_id=r["id"], title=r.get("full_name") or "Unnamed employee",
                subtitle=" · ".join(filter(None, [r.get("employee_code"), r.get("job_title"), r.get("email")])),
                status=r.get("employment_status"), url=f"/employees/{r['id']}",
                searchable=[r.get("phone"), r.get("employee_code"), r.get("job_title")])
            if item: found.append(item)

    if "jobs" in categories:
        for r in jobs:
            item = make_result(query=query, category="jobs", row_id=r["id"], title=r.get("title") or "Untitled job",
                subtitle="Job opening", status=r.get("status") or r.get("approval_status"),
                url=f"/smart-recruitment?job={r['id']}", searchable=[r.get("approval_status")])
            if item: found.append(item)

    if "applications" in categories:
        for r in apps:
            candidate = candidate_map.get(str(r.get("candidate_id")), {})
            job = job_map.get(str(r.get("job_id") or r.get("job_role_id")), {})
            name = f"{candidate.get('first_name') or ''} {candidate.get('last_name') or ''}".strip() or "Candidate"
            title = f"{name} → {job.get('title') or 'Job application'}"
            item = make_result(query=query, category="applications", row_id=r["id"], title=title,
                subtitle=f"Source: {r.get('source') or 'DIRECT'}", status=r.get("status"),
                url=f"/pipeline?application={r['id']}", searchable=[candidate.get("email"), r.get("source")])
            if item: found.append(item)

    if "referrals" in categories:
        referral_rows = _fetch(db, "referrals", "id,referrer_id,referral_code,candidate_email,status,reward_status,job_role_id,org_id", context.org_id)
        if context.role == "EMPLOYEE": referral_rows = [r for r in referral_rows if str(r.get("referrer_id")) == context.user_id]
        for r in referral_rows:
            item = make_result(query=query, category="referrals", row_id=r["id"], title=r.get("referral_code") or "Referral",
                subtitle=r.get("candidate_email") or "Candidate not yet linked", status=r.get("status"),
                url=f"/referrals?referral={r['id']}", searchable=[r.get("candidate_email"), r.get("reward_status")])
            if item: found.append(item)

    if "documents" in categories:
        document_rows = _fetch(db, "candidate_documents", "id,candidate_id,application_id,document_type,file_name,status,expiry_date,org_id", context.org_id)
        if context.role not in {"OWNER", "GROUP_ADMIN_HR"}:
            document_rows = [r for r in document_rows if str(r.get("candidate_id")) in scoped_candidate_ids]
        for r in document_rows:
            item = make_result(query=query, category="documents", row_id=r["id"], title=r.get("file_name") or r.get("document_type") or "Document",
                subtitle=r.get("document_type") or "Candidate document", status=r.get("status"),
                url=f"/pipeline?candidate={r['candidate_id']}&tab=documents", searchable=[r.get("expiry_date")])
            if item: found.append(item)

    if "properties" in categories:
        for r in _fetch(db, "properties", "id,name,code,type,city,state,is_active,org_id", context.org_id):
            if not property_allowed(context, str(r["id"])): continue
            item = make_result(query=query, category="properties", row_id=r["id"], title=r.get("name") or "Property",
                subtitle=" · ".join(filter(None, [r.get("code"), r.get("city"), r.get("state")])),
                status="ACTIVE" if r.get("is_active", True) else "INACTIVE", url=f"/hotels?property={r['id']}", searchable=[r.get("type")])
            if item: found.append(item)

    if "departments" in categories:
        for r in _fetch(db, "property_departments", "id,name,code,property_id,is_active,org_id", context.org_id):
            if not scoped(context, r): continue
            item = make_result(query=query, category="departments", row_id=r["id"], title=r.get("name") or "Department",
                subtitle=r.get("code") or "Property department", status="ACTIVE" if r.get("is_active", True) else "INACTIVE",
                url=f"/hotels?department={r['id']}", searchable=[r.get("code")])
            if item: found.append(item)

    if "complaints" in categories:
        cases = _fetch(admin, "hr_complaints", "id,ticket_number,complaint_type,category,severity,status,org_id", context.org_id)
        memberships = rows(admin.table("complaint_case_members").select("complaint_id,user_id,case_role,revoked_at").eq("org_id", context.org_id).eq("user_id", context.user_id).is_("revoked_at", "null").execute())
        assigned = {str(r["complaint_id"]) for r in memberships}
        for r in cases:
            case_id = str(r["id"])
            if not complaint_search_allowed(context, r, assigned): continue
            item = make_result(query=query, category="complaints", row_id=case_id, title=r.get("ticket_number") or "Confidential complaint",
                subtitle=f"{r.get('category') or 'GENERAL'} · {r.get('severity') or 'MEDIUM'}", status=r.get("status"),
                url=f"/grievances?case={case_id}", searchable=[r.get("category")])
            if item: found.append(item)

    return [item.as_dict() for item in sorted(found, key=lambda x: (-x.score, x.title.lower()))]


def parse_categories(raw: str | None) -> list[str]:
    if not raw: return list(SEARCH_CATEGORIES)
    values = [part.strip().lower() for part in raw.split(",") if part.strip()]
    unknown = sorted(set(values) - set(SEARCH_CATEGORIES))
    if unknown: raise HTTPException(422, f"Unknown search categories: {', '.join(unknown)}")
    return list(dict.fromkeys(values))


@router.get("")
async def search(supabase: SupabaseClient, admin: SupabaseAdminClient, user: CurrentUser,
                 q: str = Query(min_length=2, max_length=100), categories: str | None = None,
                 limit: int = Query(20, ge=1, le=50)):
    context = build_access_context(supabase, user)
    normalized = normalize_query(q)
    permitted = allowed_categories(context, parse_categories(categories))
    results = collect_results(supabase, admin, context, normalized, permitted)[:limit]
    payload = {"query": q.strip(), "categories": permitted, "results": results, "total": len(results)}
    supabase.table("user_recent_searches").upsert({"org_id": context.org_id, "user_id": context.user_id,
        "query": q.strip(), "normalized_query": normalized, "categories": permitted,
        "result_count": len(results), "searched_at": datetime.now(timezone.utc).isoformat()},
        on_conflict="user_id,normalized_query,categories").execute()
    return payload


@router.get("/autocomplete")
async def autocomplete(supabase: SupabaseClient, admin: SupabaseAdminClient, user: CurrentUser,
                       q: str = Query(min_length=2, max_length=100), categories: str | None = None,
                       limit: int = Query(8, ge=1, le=12)):
    context = build_access_context(supabase, user)
    permitted = allowed_categories(context, parse_categories(categories))
    results = collect_results(supabase, admin, context, normalize_query(q), permitted)[:limit]
    return {"query": q.strip(), "categories": permitted, "results": results}


@router.get("/recent")
async def recent(supabase: SupabaseClient, user: CurrentUser, limit: int = Query(8, ge=1, le=20)):
    context = build_access_context(supabase, user)
    data = rows(supabase.table("user_recent_searches").select("id,query,categories,result_count,searched_at").eq("user_id", context.user_id).eq("org_id", context.org_id).order("searched_at", desc=True).limit(limit).execute())
    return {"recent": data}


@router.delete("/recent", status_code=204)
async def clear_recent(supabase: SupabaseClient, user: CurrentUser):
    context = build_access_context(supabase, user)
    supabase.table("user_recent_searches").delete().eq("user_id", context.user_id).eq("org_id", context.org_id).execute()
