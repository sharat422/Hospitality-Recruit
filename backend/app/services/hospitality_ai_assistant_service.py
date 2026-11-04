"""Read-only assistant tools over authoritative, RBAC-scoped application data."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import anthropic

from app.core.config import settings
from app.services.rbac_service import AccessContext, authorize
from app.services.recruitment_analytics_service import aggregate as aggregate_recruitment


def rows(result: Any) -> list[dict]:
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])


@dataclass(frozen=True)
class AssistantTool:
    name: str
    description: str
    permission: str
    handler: Callable[..., dict]
    read_only: bool = True


def classify_question(question: str) -> str | None:
    text = re.sub(r"\s+", " ", question.strip().lower())
    rules = (
        ("attrition_analysis", ("attrition", "turnover", "leaving", "resignation")),
        ("property_overtime", ("highest overtime", "most overtime", "overtime by property")),
        ("hardest_jobs", ("hardest to fill", "difficult to fill", "hardest jobs")),
        ("retention_risk", ("highest-risk employee", "highest risk employee", "turnover risk", "at risk employee")),
        ("aged_vacancies", ("open for more than", "older than 30", "vacancies", "open jobs")),
        ("recruitment_performance", ("recruitment performance", "hiring performance", "this month's recruitment", "recruitment this month")),
    )
    for tool, phrases in rules:
        if any(phrase in text for phrase in phrases):
            return tool
    return None


def _scope(context: AccessContext, property_id: str | None, department_id: str | None = None) -> None:
    authorize(context, "reports.read", property_id=property_id, department_id=department_id)


def _allowed_property_ids(context: AccessContext) -> set[str] | None:
    if context.role in {"OWNER", "GROUP_ADMIN_HR"}:
        return None
    allowed = set(context.property_ids)
    if context.active_property_id:
        allowed.add(context.active_property_id)
    return allowed


def _property_filter(context: AccessContext, records: list[dict], property_id: str | None) -> list[dict]:
    allowed = _allowed_property_ids(context)
    output = records
    if allowed is not None:
        output = [item for item in output if str(item.get("property_id")) in allowed]
    if property_id:
        output = [item for item in output if str(item.get("property_id")) == property_id]
    return output


def _department_filter(context: AccessContext, records: list[dict], department_id: str | None) -> list[dict]:
    output = records
    if context.role == "DEPARTMENT_HEAD":
        allowed = set(context.department_ids) | ({context.department_id} if context.department_id else set())
        output = [item for item in output if not item.get("department_id") or str(item.get("department_id")) in allowed]
    if department_id:
        output = [item for item in output if str(item.get("department_id")) == department_id]
    return output


def _sources(*items: tuple[str, str, int]) -> list[dict]:
    return [{"table": table, "description": description, "rowCount": count} for table, description, count in items]


def tool_property_overtime(db, context: AccessContext, *, property_id=None, department_id=None, days=30, **_) -> dict:
    _scope(context, property_id, department_id)
    authorize(context, "attendance.read", property_id=property_id, department_id=department_id)
    start = date.today() - timedelta(days=max(1, min(days, 366)) - 1)
    attendance = rows(db.table("attendance_daily_records").select(
        "employee_id,property_id,overtime_minutes,validation_status,attendance_date"
    ).eq("org_id", context.org_id).eq("validation_status", "VALIDATED").gte(
        "attendance_date", start.isoformat()).execute())
    attendance = _property_filter(context, attendance, property_id)
    if department_id or context.role == "DEPARTMENT_HEAD":
        employees = rows(db.table("users").select("id,department_id").eq("org_id", context.org_id).execute())
        employee_departments = {str(item["id"]): item.get("department_id") for item in employees}
        attendance = _department_filter(context, [{**item, "department_id": employee_departments.get(str(item.get("employee_id")))} for item in attendance], department_id)
    properties = rows(db.table("properties").select("id,name").eq("org_id", context.org_id).execute())
    names = {str(item["id"]): item.get("name") or str(item["id"]) for item in properties}
    totals = defaultdict(int)
    for item in attendance:
        totals[str(item.get("property_id"))] += int(item.get("overtime_minutes") or 0)
    ranking = [{"propertyId": key, "property": names.get(key, key), "overtimeHours": round(value / 60, 1)}
               for key, value in sorted(totals.items(), key=lambda pair: pair[1], reverse=True)]
    leader = ranking[0] if ranking else None
    answer = (f"{leader['property']} has the highest validated overtime at {leader['overtimeHours']} hours in the last {days} days."
              if leader else "No validated overtime records were available for the selected scope and period.")
    return {"answer": answer, "metrics": {"periodDays": days, "propertiesCompared": len(ranking), "highest": leader},
            "rows": ranking[:10], "sources": _sources(("attendance_daily_records", "Validated attendance overtime only", len(attendance)), ("properties", "Authorized property names", len(properties))),
            "methodology": "Sum overtime_minutes from VALIDATED attendance records, grouped by authorized property.", "row_count": len(attendance)}


def tool_aged_vacancies(db, context: AccessContext, *, property_id=None, department_id=None, days=30, **_) -> dict:
    _scope(context, property_id, department_id); authorize(context, "jobs.read", property_id=property_id, department_id=department_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 730)))
    jobs = rows(db.table("jobs").select("id,title,status,openings_count,positions_available,created_at,approved_at,property_id,department_id").eq("org_id", context.org_id).execute())
    jobs = _department_filter(context, _property_filter(context, jobs, property_id), department_id)
    result = []
    for item in jobs:
        if str(item.get("status") or "").lower() not in {"open", "active"}: continue
        opened_raw = item.get("approved_at") or item.get("created_at")
        if not opened_raw: continue
        opened = datetime.fromisoformat(str(opened_raw).replace("Z", "+00:00"))
        if opened.tzinfo is None: opened = opened.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - opened).days
        if age > days:
            result.append({"jobId": item["id"], "title": item.get("title"), "openDays": age,
                           "vacancies": int(item.get("openings_count") or item.get("positions_available") or 1),
                           "propertyId": item.get("property_id")})
    result.sort(key=lambda x: x["openDays"], reverse=True)
    return {"answer": f"{len(result)} open vacancies have been open for more than {days} days.",
            "metrics": {"thresholdDays": days, "agedVacancyCount": len(result)}, "rows": result[:25],
            "sources": _sources(("jobs", "Authorized open job records", len(jobs))),
            "methodology": "Open days are measured from approval time, falling back to creation time; only OPEN/ACTIVE jobs are included.", "row_count": len(jobs)}


def tool_hardest_jobs(db, context: AccessContext, *, property_id=None, department_id=None, **_) -> dict:
    _scope(context, property_id, department_id); authorize(context, "jobs.read", property_id=property_id, department_id=department_id); authorize(context, "applications.read", property_id=property_id, department_id=department_id)
    jobs = rows(db.table("jobs").select("id,title,status,openings_count,positions_available,approved_at,created_at,property_id,department_id").eq("org_id", context.org_id).execute())
    jobs = _department_filter(context, _property_filter(context, jobs, property_id), department_id)
    job_ids = [item["id"] for item in jobs]
    applications = rows(db.table("applications").select("job_id,status").in_("job_id", job_ids).execute()) if job_ids else []
    counts = defaultdict(lambda: {"applications": 0, "hires": 0})
    for app in applications:
        counts[str(app.get("job_id"))]["applications"] += 1
        counts[str(app.get("job_id"))]["hires"] += str(app.get("status")).upper() == "HIRED"
    today = datetime.now(timezone.utc)
    ranked = []
    for job in jobs:
        if str(job.get("status") or "").lower() not in {"open", "active"}: continue
        opened_raw = job.get("approved_at") or job.get("created_at")
        if not opened_raw: continue
        opened = datetime.fromisoformat(str(opened_raw).replace("Z", "+00:00"))
        if opened.tzinfo is None: opened = opened.replace(tzinfo=timezone.utc)
        stat = counts[str(job["id"])]
        target = int(job.get("openings_count") or job.get("positions_available") or 1)
        remaining = max(0, target - stat["hires"])
        open_days = max(0, (today - opened).days)
        difficulty = round(min(100, open_days * 1.2 + remaining * 8 + (20 if stat["applications"] == 0 else max(0, 20 - stat["applications"] * 2))), 1)
        ranked.append({"jobId": job["id"], "title": job.get("title"), "difficultyScore": difficulty,
                       "openDays": open_days, "applications": stat["applications"], "hires": stat["hires"], "vacanciesRemaining": remaining})
    ranked.sort(key=lambda x: (-x["difficultyScore"], -x["openDays"]))
    top = ranked[0] if ranked else None
    answer = (f"{top['title']} is currently hardest to fill (difficulty {top['difficultyScore']}/100, {top['openDays']} open days, {top['vacanciesRemaining']} vacancies remaining)." if top else "No active jobs were available in the selected scope.")
    return {"answer": answer, "metrics": {"jobsAssessed": len(ranked), "hardestJob": top}, "rows": ranked[:15],
            "sources": _sources(("jobs", "Authorized active jobs", len(jobs)), ("applications", "Persisted application and hire statuses", len(applications))),
            "methodology": "Transparent operational index using open age, unfilled vacancies and application volume; it is not an AI prediction.", "row_count": len(jobs) + len(applications)}


def tool_retention_risk(db, context: AccessContext, *, property_id=None, department_id=None, **_) -> dict:
    _scope(context, property_id, department_id); authorize(context, "employees.read", property_id=property_id, department_id=department_id)
    risks = rows(db.table("employee_retention_risk_scores").select("employee_id,property_id,department_id,risk_score,risk_level,risk_factors,recommended_actions,model_type,model_version,data_quality,calculated_at").eq("org_id", context.org_id).is_("superseded_at", "null").execute())
    risks = _department_filter(context, _property_filter(context, risks, property_id), department_id)
    employee_ids = [r["employee_id"] for r in risks]
    employees = rows(db.table("users").select("id,full_name,employee_code,job_title").in_("id", employee_ids).execute()) if employee_ids else []
    employee_map = {str(e["id"]): e for e in employees}
    output = []
    for risk in sorted(risks, key=lambda r: float(r.get("risk_score") or 0), reverse=True):
        employee = employee_map.get(str(risk["employee_id"]), {})
        output.append({"employeeId": risk["employee_id"], "employee": employee.get("full_name") or employee.get("employee_code") or "Employee",
                       "employeeCode": employee.get("employee_code"), "role": employee.get("job_title"), "riskScore": float(risk.get("risk_score") or 0),
                       "riskLevel": risk.get("risk_level"), "riskFactors": risk.get("risk_factors") or [], "recommendedActions": risk.get("recommended_actions") or [],
                       "modelType": risk.get("model_type"), "dataQuality": risk.get("data_quality")})
    high = [x for x in output if x["riskLevel"] in {"HIGH", "CRITICAL"}]
    return {"answer": f"{len(high)} employees are currently HIGH or CRITICAL retention risk. The list is based on transparent persisted rules, not an irreversible employment decision.",
            "metrics": {"assessed": len(output), "highOrCritical": len(high)}, "rows": output[:20],
            "sources": _sources(("employee_retention_risk_scores", "Current explainable risk scores", len(risks)), ("users", "Authorized employee display fields", len(employees))),
            "methodology": "Current non-superseded rules-based scores, sorted descending. Factors and recommended actions are shown for review.",
            "allow_llm_narrative": False, "row_count": len(risks)}


def tool_attrition_analysis(db, context: AccessContext, *, property_id=None, department_id=None, days=90, question="", **_) -> dict:
    _scope(context, property_id, department_id); authorize(context, "employees.read", property_id=property_id, department_id=department_id)
    end = date.today(); current_start = end - timedelta(days=days - 1); previous_start = current_start - timedelta(days=days)
    departments = rows(db.table("property_departments").select("id,name,property_id").eq("org_id", context.org_id).execute())
    requested_name = "housekeeping" if "housekeeping" in question.lower() else None
    matching_departments = {str(d["id"]) for d in departments if not requested_name or requested_name in str(d.get("name") or "").lower()}
    turnover = rows(db.table("employee_turnover_history").select("property_id,department_id,event_type,effective_date,reason_category,voluntary").eq("org_id", context.org_id).gte("effective_date", previous_start.isoformat()).lte("effective_date", end.isoformat()).execute())
    turnover = _department_filter(context, _property_filter(context, turnover, property_id), department_id)
    if requested_name:
        turnover = [r for r in turnover if str(r.get("department_id")) in matching_departments]
    exits = {"current": [], "previous": []}
    for item in turnover:
        when = date.fromisoformat(str(item["effective_date"])[:10])
        bucket = "current" if when >= current_start else "previous"
        exits[bucket].append(item)
    current = len(exits["current"]); previous = len(exits["previous"])
    change_pct = round((current - previous) * 100 / previous, 1) if previous else None
    reasons = Counter(str(x.get("reason_category") or "UNSPECIFIED") for x in exits["current"])
    trend = "increased" if current > previous else "decreased" if current < previous else "was unchanged"
    comparison = f"{change_pct:+.1f}%" if change_pct is not None else "not percentage-comparable because the previous period had zero exits"
    return {"answer": f"Attrition {trend}: {current} exits in the current {days}-day period versus {previous} previously ({comparison}). The leading recorded reasons are shown below; this is descriptive, not causal proof.",
            "metrics": {"currentExits": current, "previousExits": previous, "changePct": change_pct, "topReasons": dict(reasons.most_common(5)), "periodDays": days},
            "rows": [{"reason": reason, "exits": count} for reason, count in reasons.most_common(10)],
            "sources": _sources(("employee_turnover_history", "Authorized recorded exit events and reason categories", len(turnover)), ("property_departments", "Department scope mapping", len(departments))),
            "methodology": "Compare recorded exit counts in equal current and preceding periods. Reasons are manager-recorded categories and indicate correlation, not proven cause.", "row_count": len(turnover)}


def tool_recruitment_performance(db, context: AccessContext, *, property_id=None, department_id=None, **_) -> dict:
    _scope(context, property_id, department_id); authorize(context, "applications.read", property_id=property_id, department_id=department_id); authorize(context, "jobs.read", property_id=property_id, department_id=department_id)
    start = date.today().replace(day=1)
    jobs = rows(db.table("jobs").select("id,status,openings_count,created_at,approved_at,filled_at,property_id,department_id").eq("org_id", context.org_id).execute())
    jobs = _department_filter(context, _property_filter(context, jobs, property_id), department_id); job_ids = [j["id"] for j in jobs]
    applications = rows(db.table("applications").select("id,candidate_id,job_id,source,status,created_at,hired_at,selected_at,offer_accepted_at").eq("org_id", context.org_id).gte("created_at", start.isoformat()).in_("job_id", job_ids).execute()) if job_ids else []
    metrics = aggregate_recruitment(applications=applications, jobs=jobs)
    summary = {key: metrics.get(key) for key in ("applications", "hires", "active_jobs", "time_to_hire_days", "interview_conversion_pct", "offer_acceptance_pct")}
    return {"answer": f"This month has {metrics['applications']} applications and {metrics['hires']} hires across {metrics['active_jobs']} active jobs. Interview conversion is {metrics['interview_conversion_pct']}% and offer acceptance is {metrics['offer_acceptance_pct']}%.",
            "metrics": summary, "rows": metrics.get("source_performance", [])[:10],
            "sources": _sources(("applications", "Applications created this calendar month", len(applications)), ("jobs", "Authorized job records", len(jobs))),
            "methodology": "Uses the canonical deterministic recruitment analytics service over persisted application stages and job dates.", "row_count": len(applications) + len(jobs)}


TOOLS = {
    tool.name: tool for tool in (
        AssistantTool("attrition_analysis", "Compare attrition periods and recorded reasons", "employees.read", tool_attrition_analysis),
        AssistantTool("property_overtime", "Compare validated overtime by property", "attendance.read", tool_property_overtime),
        AssistantTool("hardest_jobs", "Rank active jobs using transparent fill difficulty", "jobs.read", tool_hardest_jobs),
        AssistantTool("retention_risk", "List current explainable employee retention risks", "employees.read", tool_retention_risk),
        AssistantTool("aged_vacancies", "List vacancies open beyond a day threshold", "jobs.read", tool_aged_vacancies),
        AssistantTool("recruitment_performance", "Summarize current recruitment performance", "reports.read", tool_recruitment_performance),
    )
}


def public_tool_catalog(context: AccessContext) -> list[dict]:
    return [{"name": t.name, "description": t.description, "permission": t.permission, "readOnly": t.read_only}
            for t in TOOLS.values() if t.permission in context.permissions and "reports.read" in context.permissions]


def execute_tool(db, context: AccessContext, tool_name: str, **kwargs) -> dict:
    tool = TOOLS.get(tool_name)
    if not tool: raise ValueError("Unsupported assistant question")
    authorize(context, "reports.read", property_id=kwargs.get("property_id"), department_id=kwargs.get("department_id"))
    authorize(context, tool.permission, property_id=kwargs.get("property_id"), department_id=kwargs.get("department_id"))
    if not tool.read_only: raise PermissionError("Mutating tools require explicit confirmation and are not enabled")
    return tool.handler(db, context, **kwargs)


def _numeric_values(value: Any) -> set[float]:
    found: set[float] = set()
    if isinstance(value, bool) or value is None:
        return found
    if isinstance(value, (int, float)):
        found.add(round(float(value), 4)); return found
    if isinstance(value, dict):
        for child in value.values(): found.update(_numeric_values(child))
    elif isinstance(value, (list, tuple)):
        for child in value: found.update(_numeric_values(child))
    return found


def narrative_numbers_supported(text: str, verified_payload: dict) -> bool:
    """Reject Claude wording that introduces a numeric claim absent from tool output."""
    allowed = _numeric_values(verified_payload)
    claims = {round(float(raw.replace(",", "")), 4) for raw in re.findall(r"(?<![\w])\d[\d,]*(?:\.\d+)?", text)}
    return all(any(abs(claim - value) < 0.0001 for value in allowed) for claim in claims)


def claude_narrative(question: str, result: dict) -> tuple[str, str]:
    """Optional wording only. Numeric/entity output remains backend-owned."""
    if result.get("allow_llm_narrative") is False:
        return result["answer"], "DETERMINISTIC"
    key = settings.ANTHROPIC_API_KEY
    if not key or key.lower().startswith(("placeholder", "test", "your_")):
        return result["answer"], "DETERMINISTIC"
    safe_payload = {"metrics": result.get("metrics"), "methodology": result.get("methodology"),
                    "rows": [{k: v for k, v in row.items() if k not in {"employee", "employeeCode", "employeeId"}}
                             for row in result.get("rows", [])[:10]]}
    prompt = f"""You are a hospitality analytics narrator. Answer the question using ONLY the JSON supplied.
Do not infer causes not present in the data. Distinguish correlation from causation. Do not invent names, metrics, dates, or recommendations.
Keep the answer under 140 words. The application displays source tables separately.
Question: {question}
Verified backend result: {json.dumps(safe_payload, default=str)}"""
    try:
        response = anthropic.Anthropic(api_key=key).messages.create(
            model=settings.CLAUDE_MODEL, max_tokens=260,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()
        if text and narrative_numbers_supported(text, safe_payload):
            return text, "CLAUDE_NARRATIVE"
        return result["answer"], "DETERMINISTIC"
    except Exception:
        return result["answer"], "DETERMINISTIC"
