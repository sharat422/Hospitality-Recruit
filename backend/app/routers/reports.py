"""Reusable reporting API: generation, PDF, delivery and schedules."""
from datetime import date,datetime,timedelta,timezone
from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from pydantic import BaseModel,Field,model_validator
from app.core.dependencies import SupabaseClient,SupabaseAdminClient
from app.core.security import get_current_user
from app.services.rbac_service import authorize,build_access_context
from app.services.reporting_service import REPORT_TYPES,FINANCIAL_REPORTS,execute_report,render_pdf,rows

router=APIRouter();CurrentUser=Annotated[dict,Depends(get_current_user)]
class Recipient(BaseModel):channel:str=Field(pattern="^(EMAIL|WHATSAPP)$");recipient:str=Field(min_length=5,max_length=255)
class GenerateBody(BaseModel):
 report_type:str;property_id:str|None=None;period_start:date;period_end:date;recipients:list[Recipient]=Field(default_factory=list)
 @model_validator(mode="after")
 def valid(self):
  if self.report_type not in REPORT_TYPES:raise ValueError("Unsupported report type")
  if self.period_start>self.period_end:raise ValueError("period_start must precede period_end")
  return self
class ScheduleBody(BaseModel):
 name:str=Field(min_length=2,max_length=160);report_type:str;property_id:str|None=None;frequency:str=Field(pattern="^(DAILY|WEEKLY|MONTHLY)$");timezone:str="Asia/Kolkata";delivery_hour:int=Field(9,ge=0,le=23);day_of_week:int|None=Field(None,ge=0,le=6);day_of_month:int|None=Field(None,ge=1,le=28);recipients:list[Recipient];is_active:bool=True;next_run_at:datetime

@router.get("/definitions")
async def definitions(user:CurrentUser,supabase:SupabaseClient):
 c=build_access_context(supabase,user);authorize(c,"reports.read");return {"types":sorted(REPORT_TYPES),"channels":["EMAIL","WHATSAPP"],"formats":["PDF"]}
@router.post("/generate",status_code=201)
async def generate(body:GenerateBody,user:CurrentUser,supabase:SupabaseClient):
 c=build_access_context(supabase,user);authorize(c,"reports.read",property_id=body.property_id)
 if body.report_type in FINANCIAL_REPORTS:authorize(c,"reports.financial",property_id=body.property_id)
 if body.recipients:authorize(c,"reports.financial",property_id=body.property_id)
 return execute_report(supabase,org_id=c.org_id,report_type=body.report_type,property_id=body.property_id,generated_by=c.user_id,period_start=body.period_start,period_end=body.period_end,recipients=[x.model_dump() for x in body.recipients])
@router.get("/runs")
async def runs(user:CurrentUser,supabase:SupabaseClient,report_type:str|None=None,property_id:str|None=None):
 c=build_access_context(supabase,user);authorize(c,"reports.read",property_id=property_id);q=supabase.table("report_runs").select("id,report_type,property_id,period_start,period_end,status,created_at,completed_at,download_token").eq("org_id",c.org_id)
 if report_type:q=q.eq("report_type",report_type)
 if property_id:q=q.eq("property_id",property_id)
 return rows(q.order("created_at",desc=True).limit(200).execute())
@router.get("/runs/{run_id}/pdf")
async def download(run_id:str,user:CurrentUser,supabase:SupabaseClient):
 c=build_access_context(supabase,user);authorize(c,"reports.read");found=rows(supabase.table("report_runs").select("report_type,property_id,report_data").eq("id",run_id).eq("org_id",c.org_id).limit(1).execute())
 if not found:raise HTTPException(404,"Report not found")
 authorize(c,"reports.read",property_id=found[0].get("property_id"));return Response(render_pdf(found[0]["report_data"]),media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="{found[0]["report_type"].lower()}.pdf"'})
@router.get("/public/{token}.pdf")
async def public_pdf(token:str,supabase:SupabaseAdminClient):
 found=rows(supabase.table("report_runs").select("report_type,report_data,download_expires_at").eq("download_token",token).limit(1).execute())
 if not found or datetime.fromisoformat(str(found[0]["download_expires_at"]).replace("Z","+00:00"))<datetime.now(timezone.utc):raise HTTPException(404,"Report link expired")
 return Response(render_pdf(found[0]["report_data"]),media_type="application/pdf",headers={"Content-Disposition":f'inline; filename="{found[0]["report_type"].lower()}.pdf"'})
@router.get("/schedules")
async def schedules(user:CurrentUser,supabase:SupabaseClient):
 c=build_access_context(supabase,user);authorize(c,"reports.read");return rows(supabase.table("report_schedules").select("*").eq("org_id",c.org_id).order("next_run_at").execute())
@router.post("/schedules",status_code=201)
async def schedule(body:ScheduleBody,user:CurrentUser,supabase:SupabaseClient):
 c=build_access_context(supabase,user);authorize(c,"reports.financial",property_id=body.property_id)
 if body.report_type not in REPORT_TYPES:raise HTTPException(422,"Unsupported report type")
 payload={**body.model_dump(mode="json",exclude={"recipients"}),"channels":sorted({x.channel for x in body.recipients}),"recipients":[x.model_dump() for x in body.recipients],"org_id":c.org_id,"created_by":c.user_id};saved=rows(supabase.table("report_schedules").insert(payload).execute());return saved[0] if saved else payload
@router.patch("/schedules/{schedule_id}/status")
async def schedule_status(schedule_id:str,active:bool,user:CurrentUser,supabase:SupabaseClient):
 c=build_access_context(supabase,user);authorize(c,"reports.financial");found=rows(supabase.table("report_schedules").update({"is_active":active,"updated_at":datetime.now(timezone.utc).isoformat()}).eq("id",schedule_id).eq("org_id",c.org_id).execute());
 if not found:raise HTTPException(404,"Schedule not found")
 return found[0]
