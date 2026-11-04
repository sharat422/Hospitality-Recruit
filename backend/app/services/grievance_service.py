"""Strict grievance access decisions and fail-closed audit helpers."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import HTTPException

def member_for(members:list[dict],user_id:str):
    return next((m for m in members if m.get("user_id")==user_id and not m.get("revoked_at")),None)

def authorize_case(context,complaint:dict,members:list[dict],*,manage=False,identity=False):
    member=member_for(members,context.user_id);is_posh=complaint.get("complaint_type")=="POSH"
    if not manage and not identity and complaint.get("employee_id")==context.user_id and not complaint.get("is_anonymous"):
        return "REPORTER"
    if identity:
        if member and member.get("can_view_identity"):return member.get("case_role")
        raise HTTPException(403,"Complaint identity access requires an explicit case assignment")
    if member:
        if is_posh and member.get("case_role") not in {"POSH_COMMITTEE","INVESTIGATOR","LEGAL","AUDITOR"}:raise HTTPException(403,"POSH case requires committee or investigator assignment")
        if manage and member.get("case_role") not in {"POSH_COMMITTEE","INVESTIGATOR","LEGAL","HR_CASEWORKER"}:raise HTTPException(403,"Case role cannot modify this complaint")
        return member.get("case_role")
    if not is_posh and context.role in {"OWNER","GROUP_ADMIN_HR"}:return context.role
    raise HTTPException(404,"Complaint not found")

def audit_access(db,context,complaint_id,action,purpose,*,granted=True,denial_reason=None,resource_type=None,resource_id=None,ip_address=None):
    if not purpose or len(purpose.strip())<5:raise HTTPException(422,"A specific access purpose is required")
    payload={"org_id":context.org_id,"complaint_id":complaint_id,"actor_id":context.user_id,"action":action,"purpose":purpose.strip(),"resource_type":resource_type,"resource_id":resource_id,"access_granted":granted,"denial_reason":denial_reason,"actor_role":context.role,"ip_address":ip_address,"occurred_at":datetime.now(timezone.utc).isoformat()}
    try:
        saved=db.table("complaint_access_audit").insert(payload).execute()
        if not getattr(saved,"data",None):raise RuntimeError("No audit row returned")
    except HTTPException:raise
    except Exception as exc:raise HTTPException(503,"Sensitive access denied because audit logging is unavailable") from exc
    return payload
