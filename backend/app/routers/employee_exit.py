"""Property-scoped resignation, exit clearance, settlement and alumni APIs."""
from __future__ import annotations
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Annotated, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.employee_exit_service import DEFAULT_CLEARANCE, append_lifecycle, calculate_final_settlement, clearance_summary, experience_letter_html
from app.services.rbac_service import authorize, build_access_context

router=APIRouter(tags=["Employee Exit"]);CurrentUser=Annotated[dict,Depends(get_current_user)]
def rows(r):
    d=getattr(r,"data",None);return d if isinstance(d,list) else ([d] if isinstance(d,dict) else [])
def now():return datetime.now(timezone.utc).isoformat()

class ResignationBody(BaseModel):
    employee_id:Optional[str]=None;requested_last_working_date:date;primary_reason:str=Field(min_length=2,max_length=50)
    reason_details:Optional[str]=Field(None,max_length=3000);destination_company:Optional[str]=Field(None,max_length=180);destination_role:Optional[str]=Field(None,max_length=180)
class AcknowledgeBody(BaseModel):
    approved_last_working_date:date;notice_period_days:int=Field(30,ge=0,le=365);notice_waiver_days:int=Field(0,ge=0,le=365)
    rehire_eligible:Optional[bool]=None;rehire_notes:Optional[str]=Field(None,max_length=1000)
class InterviewBody(BaseModel):
    overall_experience:Optional[int]=Field(None,ge=1,le=5);manager_relationship:Optional[int]=Field(None,ge=1,le=5);work_environment:Optional[int]=Field(None,ge=1,le=5)
    compensation_satisfaction:Optional[int]=Field(None,ge=1,le=5);growth_opportunities:Optional[int]=Field(None,ge=1,le=5)
    reason_for_leaving:Optional[str]=None;what_went_well:Optional[str]=None;improvements:Optional[str]=None;would_recommend:Optional[bool]=None;consent_to_contact:bool=False;declined:bool=False
class ClearanceUpdate(BaseModel):
    status:Literal["CLEARED","NOT_APPLICABLE","BLOCKED"];amount_due_inr:float=Field(0,ge=0);notes:Optional[str]=None
class SettlementBody(BaseModel):
    payable_days:int=Field(ge=0,le=31);leave_encashment_inr:float=Field(0,ge=0);gratuity_inr:float=Field(0,ge=0);bonus_inr:float=Field(0,ge=0);reimbursements_inr:float=Field(0,ge=0);other_earnings_inr:float=Field(0,ge=0)
    notice_recovery_inr:float=Field(0,ge=0);loan_recovery_inr:float=Field(0,ge=0);asset_recovery_inr:float=Field(0,ge=0);tax_inr:float=Field(0,ge=0);other_deductions_inr:float=Field(0,ge=0)
class PaymentBody(BaseModel):payment_reference:str=Field(min_length=3,max_length=120)

def employee_or_404(db,context,employee_id):
    found=rows(db.table("users").select("id,org_id,full_name,email,employee_code,job_title,joining_date,employment_status,active_property_id,department_id,manager_id").eq("id",employee_id).eq("org_id",context.org_id).limit(1).execute())
    if not found:raise HTTPException(404,"Employee not found")
    return found[0]
def case_or_404(db,context,case_id,manage=False):
    found=rows(db.table("employee_exit_cases").select("*").eq("id",case_id).eq("org_id",context.org_id).limit(1).execute())
    if not found:raise HTTPException(404,"Exit case not found")
    case=found[0]
    if manage:authorize(context,"employees.manage",property_id=case.get("property_id"),department_id=case.get("department_id"))
    elif case["employee_id"]!=context.user_id:authorize(context,"employees.read",property_id=case.get("property_id"),department_id=case.get("department_id"))
    return case

@router.post("/resignations",status_code=201)
async def submit_resignation(body:ResignationBody,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);employee_id=body.employee_id or c.user_id;employee=employee_or_404(supabase,c,employee_id)
    if employee_id!=c.user_id:authorize(c,"employees.manage",property_id=employee.get("active_property_id"),department_id=employee.get("department_id"))
    if body.requested_last_working_date<date.today():raise HTTPException(422,"Last working date cannot be in the past")
    open_case=rows(supabase.table("employee_exit_cases").select("id").eq("employee_id",employee_id).in_("status",["DRAFT","SUBMITTED","ACKNOWLEDGED","NOTICE_PERIOD","CLEARANCE","SETTLEMENT_PENDING"]).limit(1).execute())
    if open_case:raise HTTPException(409,"Employee already has an active exit case")
    payload={"org_id":c.org_id,"employee_id":employee_id,"property_id":employee.get("active_property_id"),"department_id":employee.get("department_id"),"manager_id":employee.get("manager_id"),"resignation_date":date.today().isoformat(),**body.model_dump(exclude={"employee_id"},mode="json"),"submitted_by":c.user_id}
    saved=rows(supabase.table("employee_exit_cases").insert(payload).execute());case=saved[0] if saved else payload
    append_lifecycle(supabase,org_id=c.org_id,employee=employee,event_type="RESIGNATION_SUBMITTED",title="Resignation submitted",source_table="employee_exit_cases",source_id=case.get("id"),created_by=c.user_id,description=f"Requested last working date: {body.requested_last_working_date}")
    return case

@router.get("/cases")
async def list_cases(supabase:SupabaseClient,user:CurrentUser,status:Optional[str]=Query(None),property_id:Optional[str]=Query(None)):
    c=build_access_context(supabase,user);authorize(c,"employees.read",property_id=property_id)
    q=supabase.table("employee_exit_cases").select("*").eq("org_id",c.org_id)
    if status:q=q.eq("status",status.upper())
    if property_id:q=q.eq("property_id",property_id)
    output=rows(q.order("created_at",desc=True).execute());ids=list({x["employee_id"] for x in output})
    people=rows(supabase.table("users").select("id,full_name,employee_code,job_title").in_("id",ids).execute()) if ids else [];names={x["id"]:x for x in people}
    return [{**x,"employee":names.get(x["employee_id"],{})} for x in output]

@router.get("/my-case")
async def my_case(supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user)
    found=rows(supabase.table("employee_exit_cases").select("*").eq("employee_id",c.user_id).eq("org_id",c.org_id).order("created_at",desc=True).limit(1).execute())
    return found[0] if found else None

@router.get("/cases/{case_id}")
async def case_detail(case_id:str,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);case=case_or_404(supabase,c,case_id)
    clearance=rows(supabase.table("employee_exit_clearance_items").select("*").eq("exit_case_id",case_id).order("created_at").execute())
    interviews=rows(supabase.table("employee_exit_interviews").select("*").eq("exit_case_id",case_id).limit(1).execute())
    settlements=rows(supabase.table("employee_final_settlements").select("*").eq("exit_case_id",case_id).limit(1).execute())
    documents=rows(supabase.table("employee_exit_documents").select("id,document_type,generated_at,document_hash").eq("exit_case_id",case_id).execute())
    return {**case,"clearance":clearance,"clearance_summary":clearance_summary(clearance),"exit_interview":interviews[0] if interviews else None,"final_settlement":settlements[0] if settlements else None,"documents":documents}

@router.patch("/cases/{case_id}/acknowledge")
async def acknowledge(case_id:str,body:AcknowledgeBody,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);case=case_or_404(supabase,c,case_id,True);employee=employee_or_404(supabase,c,case["employee_id"])
    if body.approved_last_working_date<date.fromisoformat(str(case["resignation_date"])[:10]):raise HTTPException(422,"Approved last working date is invalid")
    update={**body.model_dump(mode="json"),"status":"NOTICE_PERIOD","acknowledged_by":c.user_id,"acknowledged_at":now(),"updated_at":now()}
    saved=rows(supabase.table("employee_exit_cases").update(update).eq("id",case_id).execute())
    existing=rows(supabase.table("employee_exit_clearance_items").select("id").eq("exit_case_id",case_id).execute())
    if not existing:supabase.table("employee_exit_clearance_items").insert([{"org_id":c.org_id,"exit_case_id":case_id,"employee_id":case["employee_id"],"clearance_type":kind,"label":label} for kind,label in DEFAULT_CLEARANCE]).execute()
    append_lifecycle(supabase,org_id=c.org_id,employee=employee,event_type="NOTICE_PERIOD_STARTED",title="Notice period started",source_table="employee_exit_cases",source_id=case_id,created_by=c.user_id,metadata={"last_working_date":str(body.approved_last_working_date),"notice_period_days":body.notice_period_days})
    return saved[0] if saved else update

@router.put("/cases/{case_id}/exit-interview")
async def exit_interview(case_id:str,body:InterviewBody,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);case=case_or_404(supabase,c,case_id)
    if case["employee_id"]!=c.user_id:authorize(c,"employees.manage",property_id=case.get("property_id"),department_id=case.get("department_id"))
    payload={"org_id":c.org_id,"exit_case_id":case_id,"employee_id":case["employee_id"],**body.model_dump(exclude={"declined"}),"status":"DECLINED" if body.declined else "SUBMITTED","submitted_at":now()}
    saved=rows(supabase.table("employee_exit_interviews").upsert(payload,on_conflict="exit_case_id").execute());return saved[0] if saved else payload

@router.patch("/clearance/{item_id}")
async def update_clearance(item_id:str,body:ClearanceUpdate,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);found=rows(supabase.table("employee_exit_clearance_items").select("*,employee_exit_cases(property_id,department_id)").eq("id",item_id).eq("org_id",c.org_id).limit(1).execute())
    if not found:raise HTTPException(404,"Clearance item not found")
    scope=found[0].get("employee_exit_cases") or {};authorize(c,"employees.manage",property_id=scope.get("property_id"),department_id=scope.get("department_id"))
    update={**body.model_dump(),"cleared_by":c.user_id if body.status in {"CLEARED","NOT_APPLICABLE"} else None,"cleared_at":now() if body.status in {"CLEARED","NOT_APPLICABLE"} else None,"updated_at":now()}
    saved=rows(supabase.table("employee_exit_clearance_items").update(update).eq("id",item_id).execute());return saved[0] if saved else update

@router.post("/cases/{case_id}/settlement/calculate")
async def settlement(case_id:str,body:SettlementBody,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);case=case_or_404(supabase,c,case_id,True)
    comp=rows(supabase.table("employee_compensation_structures").select("monthly_gross_inr,id").eq("employee_id",case["employee_id"]).order("effective_from",desc=True).limit(1).execute())
    if not comp:raise HTTPException(409,"Active compensation structure is required")
    calculation=calculate_final_settlement({"monthly_gross_inr":comp[0]["monthly_gross_inr"],"compensation_structure_id":comp[0]["id"],**body.model_dump()})
    payload={"org_id":c.org_id,"exit_case_id":case_id,"employee_id":case["employee_id"],"property_id":case.get("property_id"),"status":"CALCULATED",**calculation,"calculated_by":c.user_id,"calculated_at":now(),"updated_at":now()}
    saved=rows(supabase.table("employee_final_settlements").upsert(payload,on_conflict="exit_case_id").execute());supabase.table("employee_exit_cases").update({"status":"SETTLEMENT_PENDING","updated_at":now()}).eq("id",case_id).execute()
    return saved[0] if saved else payload

@router.post("/cases/{case_id}/settlement/approve")
async def approve_settlement(case_id:str,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);case=case_or_404(supabase,c,case_id,True);authorize(c,"payroll.manage",property_id=case.get("property_id"))
    saved=rows(supabase.table("employee_final_settlements").update({"status":"APPROVED","approved_by":c.user_id,"approved_at":now(),"updated_at":now()}).eq("exit_case_id",case_id).eq("status","CALCULATED").execute())
    if not saved:raise HTTPException(409,"Settlement must be calculated before approval")
    return saved[0]

@router.post("/cases/{case_id}/settlement/pay")
async def pay_settlement(case_id:str,body:PaymentBody,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);case=case_or_404(supabase,c,case_id,True);authorize(c,"payroll.manage",property_id=case.get("property_id"))
    saved=rows(supabase.table("employee_final_settlements").update({"status":"PAID","payment_reference":body.payment_reference,"paid_by":c.user_id,"paid_at":now(),"updated_at":now()}).eq("exit_case_id",case_id).eq("status","APPROVED").execute())
    if not saved:raise HTTPException(409,"Only an approved settlement can be paid")
    return saved[0]

@router.post("/cases/{case_id}/experience-letter",status_code=201)
async def experience_letter(case_id:str,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);case=case_or_404(supabase,c,case_id,True);employee=employee_or_404(supabase,c,case["employee_id"])
    props=rows(supabase.table("properties").select("name").eq("id",case.get("property_id")).limit(1).execute()) if case.get("property_id") else []
    html=experience_letter_html(employee,case,props[0]["name"] if props else "the organization");digest=sha256(html.encode()).hexdigest()
    payload={"org_id":c.org_id,"exit_case_id":case_id,"employee_id":case["employee_id"],"document_type":"EXPERIENCE_LETTER","document_html":html,"document_hash":digest,"generated_by":c.user_id}
    saved=rows(supabase.table("employee_exit_documents").upsert(payload,on_conflict="exit_case_id,document_type").execute());return saved[0] if saved else payload

@router.get("/documents/{document_id}")
async def exit_document(document_id:str,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);found=rows(supabase.table("employee_exit_documents").select("*").eq("id",document_id).eq("org_id",c.org_id).limit(1).execute())
    if not found:raise HTTPException(404,"Exit document not found")
    if found[0]["employee_id"]!=c.user_id:
        case_or_404(supabase,c,found[0]["exit_case_id"],True)
    return found[0]

@router.post("/cases/{case_id}/complete")
async def complete_exit(case_id:str,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user);case=case_or_404(supabase,c,case_id,True);employee=employee_or_404(supabase,c,case["employee_id"])
    if case["status"]=="COMPLETED":return {"case_id":case_id,"status":"COMPLETED","employment_status":"ALUMNI","idempotent":True}
    items=rows(supabase.table("employee_exit_clearance_items").select("status,amount_due_inr").eq("exit_case_id",case_id).execute());summary=clearance_summary(items)
    if not items or not summary["ready"]:raise HTTPException(409,"All clearance items must be cleared or not applicable")
    settlement_rows=rows(supabase.table("employee_final_settlements").select("status").eq("exit_case_id",case_id).limit(1).execute())
    if not settlement_rows or settlement_rows[0]["status"]!="PAID":raise HTTPException(409,"Final settlement must be paid")
    exit_date=case.get("approved_last_working_date") or case["requested_last_working_date"]
    supabase.table("employee_exit_cases").update({"status":"COMPLETED","completed_by":c.user_id,"completed_at":now(),"updated_at":now()}).eq("id",case_id).execute()
    supabase.table("users").update({"employment_status":"ALUMNI"}).eq("id",case["employee_id"]).eq("org_id",c.org_id).execute()
    supabase.table("employee_turnover_history").upsert({"org_id":c.org_id,"employee_id":case["employee_id"],"property_id":case.get("property_id"),"department_id":case.get("department_id"),"event_type":"RESIGNED" if case["voluntary"] else "TERMINATED","effective_date":exit_date,"reason_category":case["primary_reason"],"reason_notes":case.get("reason_details"),"voluntary":case["voluntary"],"eligible_for_rehire":case.get("rehire_eligible"),"recorded_by":c.user_id},on_conflict="employee_id,event_type,effective_date").execute()
    supabase.table("employee_alumni_profiles").upsert({"org_id":c.org_id,"employee_id":case["employee_id"],"last_property_id":case.get("property_id"),"last_department_id":case.get("department_id"),"last_job_title":employee.get("job_title"),"joining_date":employee.get("joining_date"),"exit_date":exit_date,"exit_reason":case["primary_reason"],"rehire_eligible":case.get("rehire_eligible"),"rehire_notes":case.get("rehire_notes"),"consent_to_contact":False},on_conflict="employee_id").execute()
    append_lifecycle(supabase,org_id=c.org_id,employee=employee,event_type="EXIT_COMPLETED",title="Employment completed; alumni profile created",source_table="employee_exit_cases",source_id=case_id,created_by=c.user_id,metadata={"exit_date":exit_date,"rehire_eligible":case.get("rehire_eligible")})
    return {"case_id":case_id,"status":"COMPLETED","employment_status":"ALUMNI","clearance":summary}

@router.get("/alumni")
async def alumni(supabase:SupabaseClient,user:CurrentUser,rehire_eligible:Optional[bool]=None,property_id:Optional[str]=None):
    c=build_access_context(supabase,user);authorize(c,"employees.read",property_id=property_id)
    q=supabase.table("employee_alumni_profiles").select("*").eq("org_id",c.org_id)
    if property_id:q=q.eq("last_property_id",property_id)
    if rehire_eligible is not None:q=q.eq("rehire_eligible",rehire_eligible)
    return rows(q.order("exit_date",desc=True).execute())
