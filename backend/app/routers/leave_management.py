"""Unified leave APIs used by web/PWA; WhatsApp calls the same service."""
from datetime import date, datetime, timezone
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.leave_service import review_leave_request, restore_balance, submit_leave_request
from app.services.rbac_service import authorize, build_access_context

router=APIRouter(); CurrentUser=Annotated[dict,Depends(get_current_user)]
def rows(r):
    d=getattr(r,"data",None); return d if isinstance(d,list) else ([d] if isinstance(d,dict) else [])

class LeaveRequestBody(BaseModel):
    property_id:str; start_date:date; end_date:date; leave_type:str=Field(min_length=2,max_length=30)
    reason:str=Field(min_length=3,max_length=1000); source:Literal["WEB","PWA"]="WEB"; attachment_url:str|None=None
class ReviewBody(BaseModel): action:Literal["APPROVE","REJECT"]; note:str|None=Field(None,max_length=1000)
class HolidayBody(BaseModel): property_id:str; holiday_date:date; name:str=Field(min_length=2,max_length=160); holiday_type:Literal["PUBLIC","RESTRICTED","PROPERTY"]="PUBLIC"; is_paid:bool=True

@router.get("/types")
async def leave_types(supabase:SupabaseClient,user:CurrentUser):
    ctx=build_access_context(supabase,user);authorize(ctx,"leave.read")
    return rows(supabase.table("leave_types").select("*").eq("org_id",ctx.org_id).eq("is_active",True).order("name").execute())

@router.get("/balances/me")
async def my_balances(supabase:SupabaseClient,user:CurrentUser,year:int|None=Query(None)):
    ctx=build_access_context(supabase,user);authorize(ctx,"leave.read",owner_user_id=ctx.user_id)
    return rows(supabase.table("leave_balances").select("*").eq("org_id",ctx.org_id).eq("employee_id",ctx.user_id).eq("year",year or date.today().year).execute())

@router.post("/requests",status_code=201)
async def create_request(body:LeaveRequestBody,supabase:SupabaseClient,user:CurrentUser):
    ctx=build_access_context(supabase,user);authorize(ctx,"leave.read",property_id=body.property_id,owner_user_id=ctx.user_id)
    actor=rows(supabase.table("users").select("department_id").eq("id",ctx.user_id).limit(1).execute())
    return submit_leave_request(supabase,org_id=ctx.org_id,employee_id=ctx.user_id,property_id=body.property_id,
      department_id=actor[0].get("department_id") if actor else None,start_date=body.start_date,end_date=body.end_date,
      leave_type=body.leave_type,reason=body.reason,source=body.source,attachment_url=body.attachment_url)

@router.get("/requests")
async def list_requests(supabase:SupabaseClient,user:CurrentUser,status:str|None=None,employee_id:str|None=None,property_id:str|None=None):
    ctx=build_access_context(supabase,user);target=employee_id or ctx.user_id
    authorize(ctx,"leave.read",property_id=property_id,owner_user_id=target)
    q=supabase.table("leave_requests").select("*").eq("org_id",ctx.org_id)
    if ctx.role in {"EMPLOYEE","CANDIDATE"}:q=q.eq("employee_id",ctx.user_id)
    elif employee_id:q=q.eq("employee_id",employee_id)
    if property_id:q=q.eq("property_id",property_id)
    if status:q=q.eq("status",status.upper())
    return rows(q.order("start_date",desc=True).execute())

@router.get("/calendar")
async def leave_calendar(property_id:str,date_from:date,date_to:date,supabase:SupabaseClient,user:CurrentUser):
    ctx=build_access_context(supabase,user);authorize(ctx,"leave.read",property_id=property_id)
    requests=rows(supabase.table("leave_requests").select("id,employee_id,start_date,end_date,leave_type,status").eq("org_id",ctx.org_id).eq("property_id",property_id).in_("status",["PENDING","APPROVED"]).lte("start_date",date_to.isoformat()).gte("end_date",date_from.isoformat()).execute())
    holidays=rows(supabase.table("property_holidays").select("*").eq("org_id",ctx.org_id).eq("property_id",property_id).gte("holiday_date",date_from.isoformat()).lte("holiday_date",date_to.isoformat()).execute())
    return {"leave_requests":requests,"holidays":holidays}

@router.post("/holidays",status_code=201)
async def create_holiday(body:HolidayBody,supabase:SupabaseClient,user:CurrentUser):
    ctx=build_access_context(supabase,user);authorize(ctx,"leave.manage",property_id=body.property_id)
    saved=rows(supabase.table("property_holidays").insert({**body.model_dump(mode="json"),"org_id":ctx.org_id,"created_by":ctx.user_id}).execute());return saved[0] if saved else body.model_dump(mode="json")

@router.patch("/requests/{request_id}/review")
async def review(request_id:str,body:ReviewBody,supabase:SupabaseClient,user:CurrentUser):
    ctx=build_access_context(supabase,user);found=rows(supabase.table("leave_requests").select("*").eq("id",request_id).eq("org_id",ctx.org_id).limit(1).execute())
    if not found:raise HTTPException(404,"Leave request not found")
    req=found[0];authorize(ctx,"leave.manage",property_id=req.get("property_id"),department_id=req.get("department_id"))
    return review_leave_request(supabase,request=req,actor_id=ctx.user_id,actor_role=ctx.role,action=body.action,note=body.note)

@router.patch("/requests/{request_id}/cancel")
async def cancel(request_id:str,supabase:SupabaseClient,user:CurrentUser):
    ctx=build_access_context(supabase,user);found=rows(supabase.table("leave_requests").select("*").eq("id",request_id).eq("org_id",ctx.org_id).eq("employee_id",ctx.user_id).limit(1).execute())
    if not found:raise HTTPException(404,"Leave request not found")
    req=found[0]
    if req["status"]!="PENDING":raise HTTPException(409,"Only pending leave may be cancelled")
    stamp=datetime.now(timezone.utc).isoformat();supabase.table("leave_requests").update({"status":"CANCELLED","cancelled_at":stamp,"updated_at":stamp}).eq("id",request_id).execute();restore_balance(supabase,req)
    supabase.table("leave_audit_logs").insert({"org_id":ctx.org_id,"leave_request_id":request_id,"actor_id":ctx.user_id,"action":"CANCELLED","source":"WEB","before_data":req,"after_data":{"status":"CANCELLED"}}).execute()
    return {"status":"CANCELLED"}
