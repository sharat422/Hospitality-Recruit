"""Employee and payroll-admin salary advance APIs."""
from datetime import date
from typing import Annotated,Literal,Optional
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from app.core.dependencies import SupabaseAdminClient,SupabaseClient
from app.core.security import get_current_user
from app.services.rbac_service import authorize,build_access_context
from app.services.salary_advance_service import disburse,eligibility,review,rows

router=APIRouter();CurrentUser=Annotated[dict,Depends(get_current_user)]
class PolicyBody(BaseModel):
 property_id:Optional[str]=None;minimum_tenure_days:int=Field(90,ge=0,le=3650);maximum_advance_pct:float=Field(50,gt=0,le=100);maximum_amount_inr:float=Field(50000,gt=0);maximum_repayment_months:int=Field(6,ge=1,le=24);require_manager_approval:bool=True;require_payroll_approval:bool=True;is_active:bool=True
class ReviewBody(BaseModel):
 action:Literal["APPROVE","REJECT"];note:Optional[str]=Field(None,max_length=1000);approved_amount_inr:Optional[float]=Field(None,gt=0);repayment_months:Optional[int]=Field(None,ge=1,le=24)
class DisburseBody(BaseModel):
 disbursement_reference:str=Field(min_length=3,max_length=200);first_repayment_year:int=Field(ge=2020,le=2100);first_repayment_month:int=Field(ge=1,le=12)
def find(admin,context,request_id):
 found=rows(admin.table("employee_salary_advance_requests").select("*").eq("id",request_id).eq("org_id",context.org_id).limit(1).execute())
 if not found:raise HTTPException(404,"Salary advance request not found")
 return found[0]

@router.get("/eligibility")
async def my_eligibility(supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);authorize(c,"payroll.read",owner_user_id=c.user_id)
 employee=rows(supabase.table("users").select("active_property_id").eq("id",c.user_id).limit(1).execute())
 return eligibility(supabase,org_id=c.org_id,property_id=employee[0].get("active_property_id") if employee else None,employee_id=c.user_id)

@router.get("")
async def list_requests(supabase:SupabaseClient,user:CurrentUser,property_id:Optional[str]=None,status:Optional[str]=None,employee_id:Optional[str]=None):
 c=build_access_context(supabase,user);authorize(c,"payroll.read",property_id=property_id)
 q=supabase.table("employee_salary_advance_requests").select("*").eq("org_id",c.org_id)
 if property_id:q=q.eq("property_id",property_id)
 if status:q=q.eq("status",status.upper())
 if employee_id:q=q.eq("employee_id",employee_id)
 return rows(q.order("created_at",desc=True).limit(500).execute())

@router.put("/policy")
async def save_policy(body:PolicyBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);authorize(c,"payroll.manage",property_id=body.property_id)
 payload={**body.model_dump(),"org_id":c.org_id,"updated_by":c.user_id,"created_by":c.user_id}
 saved=rows(supabase.table("salary_advance_policies").upsert(payload,on_conflict="org_id,property_id").execute());return saved[0] if saved else payload

@router.post("/{request_id}/review")
async def review_request(request_id:str,body:ReviewBody,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser):
 c=build_access_context(supabase,user);item=find(admin,c,request_id);authorize(c,"payroll.manage",property_id=item.get("property_id"))
 policy=eligibility(admin,org_id=c.org_id,property_id=item.get("property_id"),employee_id=item["employee_id"])["policy"]
 months=body.repayment_months or item["requested_repayment_months"]
 if body.action=="APPROVE" and months>int(policy["maximum_repayment_months"]):raise HTTPException(422,"Repayment period exceeds property policy")
 return review(supabase,item=item,actor_id=c.user_id,action=body.action,note=body.note,approved_amount=body.approved_amount_inr,repayment_months=months)

@router.post("/{request_id}/disburse")
async def disburse_request(request_id:str,body:DisburseBody,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser):
 c=build_access_context(supabase,user);item=find(admin,c,request_id);authorize(c,"payroll.manage",property_id=item.get("property_id"))
 return disburse(supabase,item=item,actor_id=c.user_id,reference=body.disbursement_reference,first_year=body.first_repayment_year,first_month=body.first_repayment_month)

@router.get("/{request_id}/ledger")
async def ledger(request_id:str,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser):
 c=build_access_context(supabase,user);item=find(admin,c,request_id)
 if item["employee_id"]!=c.user_id:authorize(c,"payroll.read",property_id=item.get("property_id"))
 repayments=rows(supabase.table("salary_advance_repayments").select("*").eq("advance_id",request_id).order("installment_number").execute())
 audits=rows(supabase.table("salary_advance_audit_logs").select("action,before_status,after_status,amount_inr,metadata,created_at").eq("advance_id",request_id).order("created_at").execute())
 return {"advance":item,"repayments":repayments,"audit":audits}
