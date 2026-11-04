"""Configurable onboarding selection, completion and non-decisional risk signals."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable, Optional


STAGE_ORDER = ("documents", "kyc", "certifications", "payroll", "ready")


def _as_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        try:
            return date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None


def select_most_specific_template(
    templates: Iterable[dict], *, org_id: str, property_id: str | None,
    department_id: str | None, role_template_id: str | None,
) -> Optional[dict]:
    """Mirror the SQL template precedence so it remains deterministic and testable."""
    candidates = []
    for item in templates:
        if not item.get("is_active", True) or not item.get("auto_start", True):
            continue
        if item.get("org_id") not in (None, org_id):
            continue
        if item.get("property_id") not in (None, property_id):
            continue
        if item.get("department_id") not in (None, department_id):
            continue
        if item.get("role_template_id") not in (None, role_template_id):
            continue
        specificity = sum(bool(item.get(key)) for key in
                          ("org_id", "property_id", "department_id", "role_template_id"))
        candidates.append((specificity, int(item.get("version") or 1), str(item.get("created_at") or ""), item))
    return max(candidates, key=lambda row: row[:3])[3] if candidates else None


def compute_onboarding_progress(tasks: Iterable[dict]) -> dict:
    mandatory = [task for task in tasks if task.get("is_mandatory", True)]
    done_states = {"completed", "waived"}
    total_weight = sum(float(task.get("weight") or 1) for task in mandatory)
    done_weight = sum(float(task.get("weight") or 1) for task in mandatory
                      if str(task.get("status", "")).lower() in done_states)
    completion = round(done_weight / total_weight * 100, 2) if total_weight else 0.0
    stages = {}
    for stage in STAGE_ORDER:
        subset = [task for task in mandatory if task.get("stage") == stage]
        weight = sum(float(task.get("weight") or 1) for task in subset)
        done = sum(float(task.get("weight") or 1) for task in subset
                   if str(task.get("status", "")).lower() in done_states)
        stages[stage] = round(done / weight * 100) if weight else 0
    current = next((stage for stage in STAGE_ORDER if stages[stage] < 100), "ready")
    return {"completion_pct": completion, "stage_completion": stages,
            "current_stage": current, "completed": bool(mandatory) and completion == 100}


def calculate_onboarding_ghosting_risk(
    flow: dict, tasks: Iterable[dict], *, today: date | None = None,
) -> dict:
    """Explainable outreach priority only; it never changes a hiring decision."""
    today = today or datetime.now(timezone.utc).date()
    tasks = list(tasks)
    progress = compute_onboarding_progress(tasks)
    score, signals = 0.0, []
    joining = _as_date(flow.get("joining_date"))
    activity = _as_date(flow.get("last_candidate_activity_at") or flow.get("offer_accepted_at") or flow.get("created_at"))
    pending = [t for t in tasks if t.get("is_mandatory", True) and
               str(t.get("status", "pending")).lower() not in ("completed", "waived")]
    overdue = [t for t in pending if (_as_date(t.get("due_date")) or date.max) < today]

    if activity and (today - activity).days >= 3:
        score += 0.25; signals.append({"code": "NO_ACTIVITY_3_DAYS", "weight": 0.25,
                                      "message": f"No candidate activity for {(today-activity).days} days"})
    if overdue:
        weight = min(0.30, 0.08 * len(overdue)); score += weight
        signals.append({"code": "OVERDUE_REQUIRED_TASKS", "weight": weight,
                        "message": f"{len(overdue)} required task(s) overdue"})
    if joining:
        days = (joining - today).days
        if 0 <= days <= 7 and progress["completion_pct"] < 50:
            score += 0.30; signals.append({"code": "JOINING_SOON_LOW_PROGRESS", "weight": 0.30,
                                          "message": f"Joining in {days} days at {progress['completion_pct']:.0f}% completion"})
        if days < 0 and not progress["completed"]:
            score += 0.40; signals.append({"code": "JOINING_DATE_PASSED", "weight": 0.40,
                                          "message": "Joining date passed with onboarding incomplete"})
    if not flow.get("manager_id"):
        score += 0.10; signals.append({"code": "NO_MANAGER", "weight": 0.10,
                                      "message": "Reporting manager is not assigned"})
    if not flow.get("appointment_signed", False) and any(t.get("task_type") == "appointment_esign" for t in pending):
        score += 0.15; signals.append({"code": "LETTER_NOT_SIGNED", "weight": 0.15,
                                      "message": "Appointment letter is not signed"})
    score = round(min(score, 1.0), 4)
    level = "CRITICAL" if score >= .75 else "HIGH" if score >= .5 else "MEDIUM" if score >= .3 else "LOW"
    return {"ghosting_risk_score": score, "ghosting_risk_level": level,
            "ghosting_risk_signals": signals, **progress}


def recalculate_and_persist(supabase, flow: dict, tasks: list[dict]) -> dict:
    result = calculate_onboarding_ghosting_risk(flow, tasks)
    values = {key: result[key] for key in ("completion_pct", "stage_completion", "current_stage",
              "ghosting_risk_score", "ghosting_risk_level", "ghosting_risk_signals")}
    if result["completed"]:
        values.update(status="completed", completed_at=datetime.now(timezone.utc).isoformat())
    supabase.table("onboarding_flows").update(values).eq("id", flow["id"]).eq("org_id", flow["org_id"]).execute()
    return {**flow, **values}
