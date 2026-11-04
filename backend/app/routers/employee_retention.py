"""Employee retention signals, pulse surveys and explainable rules-based risk."""
from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from app.core.dependencies import SupabaseAdminClient, SupabaseClient
from app.core.security import get_current_user
from app.services.employee_retention_service import calculate_retention_risk
from app.services.employee_engagement_service import submit_pulse_response
from app.services.rbac_service import authorize, build_access_context

router=APIRouter(tags=["Employee Retention"])
CurrentUser=Annotated[dict,Depends(get_current_user)]
def rows(result): return getattr(result,"data",None) or []
def now(): return datetime.utcnow().isoformat()

class SurveyCreate(BaseModel):
    title:str=Field(min_length=2,max_length=180); question_text:str=Field(min_length=5)
    property_id:Optional[str]=None; department_id:Optional[str]=None; closes_at:Optional[str]=None
    is_anonymous:bool=True
class SurveyResponse(BaseModel): score:int=Field(ge=1,le=5); comment:Optional[str]=Field(None,max_length=1000)
class InterventionCreate(BaseModel):
    action_type:str=Field(min_length=2,max_length=40); notes:Optional[str]=None; owner_id:Optional[str]=None; due_at:Optional[str]=None
class TurnoverCreate(BaseModel):
    employee_id:str; event_type:str; effective_date:str; reason_category:Optional[str]=None
    reason_notes:Optional[str]=None; voluntary:Optional[bool]=None; eligible_for_rehire:Optional[bool]=None
    @field_validator("event_type")
    @classmethod
    def valid_event(cls,value):
        value=value.upper()
        if value not in {"RESIGNED","TERMINATED","ABSCONDED","RETIREMENT","TRANSFERRED_OUT","REHIRED"}:raise ValueError("Invalid turnover event")
        return value

def get_employee(db,context,employee_id):
    found=rows(db.table("users").select("id,org_id,active_property_id,department_id,joining_date,employment_status").eq("id",employee_id).eq("org_id",context.org_id).limit(1).execute())
    if not found: raise HTTPException(404,"Employee not found")
    authorize(context,"employees.read",property_id=found[0].get("active_property_id"),department_id=found[0].get("department_id"))
    return found[0]

def months_between(earlier,later=None):
    if not earlier:return 0
    a=date.fromisoformat(str(earlier)[:10]); b=later or date.today()
    return max(0,(b.year-a.year)*12+b.month-a.month-(b.day<a.day))

def collect_inputs(db,context,employee):
    employee_id=employee["id"]; since=(date.today()-timedelta(days=90)).isoformat()
    attendance=rows(db.table("attendance_daily_records").select("status,late_minutes,validation_status,attendance_date")
        .eq("employee_id",employee_id).gte("attendance_date",since).eq("validation_status","VALIDATED").execute())
    compensation=rows(db.table("employee_compensation_structures").select("monthly_gross_inr,effective_from")
        .eq("employee_id",employee_id).order("effective_from",desc=True).limit(2).execute())
    reviews=rows(db.table("employee_performance_reviews").select("overall_score,review_period_end")
        .eq("employee_id",employee_id).order("review_period_end",desc=True).limit(1).execute())
    promotion_since=(date.today()-timedelta(days=548)).isoformat()
    promotions=rows(db.table("employee_lifecycle_events").select("id,event_at").eq("employee_id",employee_id)
        .eq("event_type","PROMOTION").gte("event_at",promotion_since).execute())
    pulse=rows(db.table("employee_pulse_responses").select("score,submitted_at").eq("employee_id",employee_id)
        .order("submitted_at",desc=True).limit(6).execute())
    overdue=rows(db.table("employee_training_records").select("id").eq("employee_id",employee_id)
        .in_("status",["ASSIGNED","IN_PROGRESS"]).lt("due_date",date.today().isoformat()).execute())
    turnover=rows(db.table("employee_turnover_history").select("event_type,effective_date").eq("employee_id",employee_id).order("effective_date",desc=True).execute())
    salary={}
    if compensation:
        latest=float(compensation[0].get("monthly_gross_inr") or 0); previous=float(compensation[1].get("monthly_gross_inr") or 0) if len(compensation)>1 else 0
        salary={"latest_monthly_gross_inr":latest,"latest_change_pct":round((latest-previous)*100/previous,2) if previous else 0,
                "months_since_increase":months_between(compensation[0].get("effective_from"))}
    pulse_data={}
    if pulse:
        recent=[float(x["score"]) for x in pulse[:3]]; older=[float(x["score"]) for x in pulse[3:6]]
        pulse_data={"average":round(sum(recent)/len(recent),2),"responses":len(pulse),
                    "decline":round(sum(older)/len(older)-sum(recent)/len(recent),2) if older else 0}
    return {"attendance":{"absence_days":sum(x.get("status")=="ABSENT" for x in attendance),"late_days":sum(int(x.get("late_minutes") or 0)>0 for x in attendance),"validated_days":len(attendance)},
            "salary":salary,"performance":{"score":reviews[0].get("overall_score") if reviews else None,"promotion_last_18_months":bool(promotions)},
            "pulse":pulse_data,"training":{"overdue_count":len(overdue)},"turnover":{"prior_events":[x["event_type"] for x in turnover]},
            "tenure_months":months_between(employee.get("joining_date"))}

def calculate_and_store(db,context,employee):
    inputs=collect_inputs(db,context,employee); result=calculate_retention_risk(inputs)
    db.table("employee_retention_risk_scores").update({"superseded_at":now()}).eq("employee_id",employee["id"]).is_("superseded_at","null").execute()
    payload={"org_id":context.org_id,"employee_id":employee["id"],"property_id":employee.get("active_property_id"),"department_id":employee.get("department_id"),
             **{k:result[k] for k in ("risk_score","risk_level","risk_factors","recommended_actions","model_type","model_version","data_quality")},
             "input_snapshot":inputs,"calculated_by":context.user_id}
    saved=rows(db.table("employee_retention_risk_scores").insert(payload).execute())
    return {**(saved[0] if saved else payload),"disclaimer":result["disclaimer"]}

@router.get("/risks")
async def list_risks(supabase:SupabaseClient,user:CurrentUser,risk_level:Optional[str]=Query(None),property_id:Optional[str]=Query(None)):
    c=build_access_context(supabase,user);authorize(c,"employees.read",property_id=property_id)
    q=supabase.table("employee_retention_risk_scores").select("*").eq("org_id",c.org_id).is_("superseded_at","null")
    if risk_level:q=q.eq("risk_level",risk_level.upper())
    if property_id:q=q.eq("property_id",property_id)
    output=rows(q.order("risk_score",desc=True).execute());ids=list({x["employee_id"] for x in output})
    people=rows(supabase.table("users").select("id,full_name,job_title").eq("org_id",c.org_id).in_("id",ids).execute()) if ids else []
    by_id={x["id"]:x for x in people}
    return [{**x,"users":by_id.get(x["employee_id"],{})} for x in output]

@router.post("/employees/{employee_id}/calculate")
async def calculate(employee_id:str,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);authorize(c,"employees.manage");return calculate_and_store(supabase,c,get_employee(supabase,c,employee_id))

@router.post("/calculate-all")
async def calculate_all(supabase:SupabaseClient,user:CurrentUser,property_id:Optional[str]=Query(None)):
    c=build_access_context(supabase,user);authorize(c,"employees.manage",property_id=property_id)
    q=supabase.table("users").select("id,org_id,active_property_id,department_id,joining_date,employment_status").eq("org_id",c.org_id).eq("employment_status","ACTIVE")
    if property_id:q=q.eq("active_property_id",property_id)
    output=[]
    for employee in rows(q.execute()):
        try:
            authorize(c,"employees.read",property_id=employee.get("active_property_id"),department_id=employee.get("department_id"));output.append(calculate_and_store(supabase,c,employee))
        except HTTPException: continue
    return {"calculated":len(output),"results":output,"model_type":"RULES_BASED"}

@router.get("/pulse-surveys")
async def surveys(supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user)
    return rows(supabase.table("employee_pulse_surveys").select("*").eq("org_id",c.org_id).eq("status","ACTIVE").order("opens_at",desc=True).execute())

@router.post("/pulse-surveys",status_code=201)
async def create_survey(body:SurveyCreate,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);authorize(c,"employees.manage",property_id=body.property_id,department_id=body.department_id)
    payload={"org_id":c.org_id,**body.model_dump(),"created_by":c.user_id};saved=rows(supabase.table("employee_pulse_surveys").insert(payload).execute());return saved[0] if saved else payload

@router.post("/pulse-surveys/{survey_id}/respond",status_code=201)
async def respond(survey_id:str,body:SurveyResponse,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);survey=rows(supabase.table("employee_pulse_surveys").select("*").eq("id",survey_id).eq("org_id",c.org_id).eq("status","ACTIVE").limit(1).execute())
    if not survey:raise HTTPException(404,"Active pulse survey not found")
    employee=rows(supabase.table("users").select("id,org_id,active_property_id,department_id").eq("id",c.user_id).eq("org_id",c.org_id).limit(1).execute())
    if not employee:raise HTTPException(403,"Employee profile not found")
    return submit_pulse_response(supabase,survey=survey[0],employee=employee[0],score=body.score,comment=body.comment,source="PWA")

@router.get("/pulse-surveys/{survey_id}/results")
async def survey_results(survey_id:str,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser):
    c=build_access_context(supabase,user);authorize(c,"employees.read")
    survey=rows(supabase.table("employee_pulse_surveys").select("*").eq("id",survey_id).eq("org_id",c.org_id).limit(1).execute())
    if not survey:raise HTTPException(404,"Pulse survey not found")
    responses=rows(admin.table("employee_pulse_responses").select("score,submitted_at").eq("survey_id",survey_id).eq("org_id",c.org_id).execute())
    distribution={str(value):sum(int(x["score"])==value for x in responses) for value in range(survey[0]["scale_min"],survey[0]["scale_max"]+1)}
    return {"survey_id":survey_id,"response_count":len(responses),"average_score":round(sum(float(x["score"]) for x in responses)/len(responses),2) if responses else None,"distribution":distribution,"anonymous":survey[0]["is_anonymous"],"raw_responses_exposed":False}

@router.post("/risks/{risk_id}/interventions",status_code=201)
async def intervention(risk_id:str,body:InterventionCreate,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);authorize(c,"employees.manage")
    risk=rows(supabase.table("employee_retention_risk_scores").select("id,employee_id").eq("id",risk_id).eq("org_id",c.org_id).limit(1).execute())
    if not risk:raise HTTPException(404,"Risk score not found")
    payload={"org_id":c.org_id,"risk_score_id":risk_id,"employee_id":risk[0]["employee_id"],**body.model_dump(),"created_by":c.user_id}
    saved=rows(supabase.table("employee_retention_interventions").insert(payload).execute());return saved[0] if saved else payload

@router.post("/turnover",status_code=201)
async def record_turnover(body:TurnoverCreate,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);authorize(c,"employees.manage");employee=get_employee(supabase,c,body.employee_id)
    payload={"org_id":c.org_id,"property_id":employee.get("active_property_id"),"department_id":employee.get("department_id"),**body.model_dump(),"event_type":body.event_type.upper(),"recorded_by":c.user_id}
    saved=rows(supabase.table("employee_turnover_history").insert(payload).execute());return saved[0] if saved else payload

@router.get("/turnover")
async def turnover_history(supabase:SupabaseClient,user:CurrentUser,property_id:Optional[str]=Query(None)):
    c=build_access_context(supabase,user);authorize(c,"employees.read",property_id=property_id)
    q=supabase.table("employee_turnover_history").select("*").eq("org_id",c.org_id)
    if property_id:q=q.eq("property_id",property_id)
    output=rows(q.order("effective_date",desc=True).execute());ids=list({x["employee_id"] for x in output})
    people=rows(supabase.table("users").select("id,full_name,job_title").eq("org_id",c.org_id).in_("id",ids).execute()) if ids else []
    by_id={x["id"]:x for x in people}
    return [{**x,"users":by_id.get(x["employee_id"],{})} for x in output]
