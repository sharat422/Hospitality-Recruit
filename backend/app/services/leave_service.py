"""Canonical leave logic shared by web, PWA, WhatsApp and admin APIs."""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from fastapi import HTTPException

BALANCE_COLUMNS={"CASUAL":"casual_used","EMERGENCY":"casual_used","SICK":"sick_used","EARNED":"earned_used"}
TOTAL_COLUMNS={"CASUAL":"casual_total","EMERGENCY":"casual_total","SICK":"sick_total","EARNED":"earned_total"}

def _rows(result):
    d=getattr(result,"data",None); return d if isinstance(d,list) else ([d] if isinstance(d,dict) else [])
def _now(): return datetime.now(timezone.utc).isoformat()
def _ticket(): return f"LV-{datetime.now():%Y%m%d}-{uuid4().hex[:6].upper()}"

def calculate_leave_days(start:date,end:date,holidays:list[str]|None=None)->float:
    if end<start: raise ValueError("End date must be on or after start date")
    holiday_set={str(x)[:10] for x in holidays or []}; days=0; cursor=start
    while cursor<=end:
        if cursor.isoweekday()<=6 and cursor.isoformat() not in holiday_set: days+=1
        cursor+=timedelta(days=1)
    return float(days)

def ensure_balance(sb,org_id,employee_id,year):
    found=_rows(sb.table("leave_balances").select("*").eq("employee_id",employee_id).eq("year",year).limit(1).execute())
    if found:return found[0]
    saved=_rows(sb.table("leave_balances").insert({"org_id":org_id,"employee_id":employee_id,"year":year}).execute())
    return saved[0] if saved else {"casual_total":12,"casual_used":0,"sick_total":12,"sick_used":0,"earned_total":15,"earned_used":0}

def submit_leave_request(sb,*,org_id,employee_id,property_id,start_date,end_date,leave_type,reason,source,department_id=None,whatsapp_message_id=None,attachment_url=None):
    leave_type=leave_type.upper(); source=source.upper()
    if source not in {"WEB","PWA","WHATSAPP","ADMIN"}: raise HTTPException(422,"Invalid leave source")
    if len(reason.strip())<3: raise HTTPException(422,"Leave reason is required")
    types=_rows(sb.table("leave_types").select("*").eq("org_id",org_id).eq("code",leave_type).eq("is_active",True).limit(1).execute())
    config=types[0] if types else {"code":leave_type,"requires_hr_approval":leave_type in {"EARNED","LWP"},"allow_negative_balance":leave_type=="LWP"}
    holidays=[]
    if property_id:
        holidays=_rows(sb.table("property_holidays").select("holiday_date").eq("property_id",property_id).gte("holiday_date",start_date.isoformat()).lte("holiday_date",end_date.isoformat()).execute())
    total=calculate_leave_days(start_date,end_date,[x["holiday_date"] for x in holidays])
    if total<=0: raise HTTPException(422,"Selected dates contain no working leave days")
    overlap=_rows(sb.table("leave_requests").select("id").eq("employee_id",employee_id).in_("status",["PENDING","APPROVED"]).lte("start_date",end_date.isoformat()).gte("end_date",start_date.isoformat()).limit(1).execute())
    if overlap: raise HTTPException(409,"An active leave request already covers these dates")
    balance=ensure_balance(sb,org_id,employee_id,start_date.year); used_col=BALANCE_COLUMNS.get(leave_type); total_col=TOTAL_COLUMNS.get(leave_type)
    if used_col and total_col and not config.get("allow_negative_balance"):
        remaining=float(balance.get(total_col,0) or 0)-float(balance.get(used_col,0) or 0)
        if remaining<total: raise HTTPException(409,f"Insufficient {leave_type.lower()} leave balance")
    payload={"org_id":org_id,"employee_id":employee_id,"property_id":property_id,"department_id":department_id,
      "leave_date":start_date.isoformat(),"start_date":start_date.isoformat(),"end_date":end_date.isoformat(),"total_days":total,
      "duration_days":int(total),"leave_type":leave_type,"reason":reason.strip(),"status":"PENDING","manager_status":"PENDING",
      "hr_status":"PENDING" if config.get("requires_hr_approval") else "NOT_REQUIRED","ticket_number":_ticket(),
      "channel":source,"source":source,"whatsapp_message_id":whatsapp_message_id,"attachment_url":attachment_url,
      "sla_deadline":(datetime.now(timezone.utc)+timedelta(days=3)).isoformat(),"updated_at":_now()}
    saved=_rows(sb.table("leave_requests").insert(payload).execute()); request=saved[0] if saved else payload
    if used_col:
        sb.table("leave_balances").update({used_col:float(balance.get(used_col,0) or 0)+total,"updated_at":_now()}).eq("id",balance.get("id")).execute()
    if request.get("id"): sb.table("leave_audit_logs").insert({"org_id":org_id,"leave_request_id":request["id"],"actor_id":employee_id,"action":"SUBMITTED","source":source,"after_data":payload}).execute()
    return request

def review_leave_request(sb,*,request,actor_id,actor_role,action,note=None):
    action=action.upper(); before=dict(request)
    if action not in {"APPROVE","REJECT"}: raise HTTPException(422,"Invalid action")
    if request["status"] not in {"PENDING"}: raise HTTPException(409,f"Request already {request['status'].lower()}")
    is_hr=actor_role in {"OWNER","GROUP_ADMIN_HR","HR_MANAGER"}; payload={"updated_at":_now()}
    manager_status=request.get("manager_status") or ("PENDING" if request.get("status")=="PENDING" else request.get("status"))
    hr_status=request.get("hr_status") or "NOT_REQUIRED"
    if manager_status=="PENDING":
        payload.update(manager_status="APPROVED" if action=="APPROVE" else "REJECTED",manager_reviewed_by=actor_id,manager_reviewed_at=_now())
        if action=="REJECT": payload.update(status="REJECTED",rejection_reason=note)
        elif hr_status=="PENDING": payload["status"]="PENDING"
        else: payload.update(status="APPROVED",approved_by=actor_id,approved_at=_now())
    elif hr_status=="PENDING" and is_hr:
        payload.update(hr_status="APPROVED" if action=="APPROVE" else "REJECTED",hr_reviewed_by=actor_id,hr_reviewed_at=_now(),status="APPROVED" if action=="APPROVE" else "REJECTED")
        if action=="APPROVE": payload.update(approved_by=actor_id,approved_at=_now())
        else: payload["rejection_reason"]=note
    else: raise HTTPException(403,"HR approval is required or this step is already complete")
    saved=_rows(sb.table("leave_requests").update(payload).eq("id",request["id"]).execute())
    if payload.get("status")=="REJECTED": restore_balance(sb,request)
    sb.table("leave_audit_logs").insert({"org_id":request["org_id"],"leave_request_id":request["id"],"actor_id":actor_id,"action":payload.get("status",payload.get("manager_status")),"source":"ADMIN","before_data":before,"after_data":payload}).execute()
    return saved[0] if saved else {**request,**payload}

def restore_balance(sb,request):
    col=BALANCE_COLUMNS.get(request.get("leave_type",""));
    if not col:return
    rows=_rows(sb.table("leave_balances").select(f"id,{col}").eq("employee_id",request["employee_id"]).eq("year",int(str(request.get("start_date") or request["leave_date"])[:4])).limit(1).execute())
    if rows: sb.table("leave_balances").update({col:max(0,float(rows[0].get(col,0))-float(request.get("total_days",1))),"updated_at":_now()}).eq("id",rows[0]["id"]).execute()
