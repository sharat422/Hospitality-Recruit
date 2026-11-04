"""Confidential grievance and POSH case-management APIs."""
from __future__ import annotations
from datetime import date,datetime,timezone
from hashlib import sha256
from typing import Annotated,Literal,Optional
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from pydantic import BaseModel,Field,model_validator
from app.core.dependencies import SupabaseAdminClient,SupabaseClient
from app.core.security import get_current_user
from app.services.grievance_service import audit_access,authorize_case
from app.services.rbac_service import authorize,build_access_context
from app.services.s3_service import S3Service

router=APIRouter(tags=["Grievance Management"]);CurrentUser=Annotated[dict,Depends(get_current_user)]
def rows(r):
 d=getattr(r,"data",None);return d if isinstance(d,list) else ([d] if isinstance(d,dict) else [])
def now():return datetime.now(timezone.utc).isoformat()
def complaint(admin,c,complaint_id):
 found=rows(admin.table("hr_complaints").select("*").eq("id",complaint_id).eq("org_id",c.org_id).limit(1).execute())
 if not found:raise HTTPException(404,"Complaint not found")
 return found[0]
def members(admin,c,complaint_id):return rows(admin.table("complaint_case_members").select("*").eq("complaint_id",complaint_id).eq("org_id",c.org_id).is_("revoked_at","null").execute())
def ip(request):return request.client.host if request.client else None

class MemberBody(BaseModel):
 user_id:str;case_role:Literal["TRIAGE","INVESTIGATOR","POSH_COMMITTEE","HR_CASEWORKER","LEGAL","AUDITOR"];can_view_identity:bool=False
class InvestigationBody(BaseModel):
 title:str=Field(min_length=3,max_length=200);scope:str=Field(min_length=10,max_length=5000);methodology:Optional[str]=None;investigator_id:str
class InvestigationUpdate(BaseModel):
 status:Literal["PLANNING","IN_PROGRESS","FINDINGS_REVIEW","COMPLETED","CANCELLED"];findings:Optional[str]=None;recommendations:Optional[str]=None
class EvidenceBody(BaseModel):
 evidence_type:Literal["DOCUMENT","IMAGE","VIDEO","AUDIO","MESSAGE","STATEMENT","OTHER"];description:Optional[str]=None;investigation_id:Optional[str]=None
 file_name:Optional[str]=None;content_type:Optional[str]=None;storage_key:Optional[str]=None;text_evidence:Optional[str]=None;sha256_hash:Optional[str]=Field(None,pattern="^[a-fA-F0-9]{64}$")
 @model_validator(mode="after")
 def one_source(self):
  if not self.storage_key and not self.text_evidence:raise ValueError("storage_key or text_evidence is required")
  return self
class UploadRequest(BaseModel):filename:str=Field(min_length=1,max_length=255);content_type:Literal["application/pdf","image/jpeg","image/png","image/webp"]
class EscalationBody(BaseModel):escalated_to:str;reason:str=Field(min_length=10,max_length=3000);priority:Literal["MEDIUM","HIGH","CRITICAL"]="HIGH"
class ResolutionBody(BaseModel):
 outcome:Literal["SUBSTANTIATED","PARTIALLY_SUBSTANTIATED","UNSUBSTANTIATED","INCONCLUSIVE","WITHDRAWN"]
 resolution_summary:str=Field(min_length=20,max_length=10000);corrective_actions:list[dict|str]=Field(default_factory=list);disciplinary_action_reference:Optional[str]=None;appeal_deadline:Optional[date]=None

@router.get("/cases")
async def list_cases(supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser,status:Optional[str]=None,complaint_type:Optional[str]=None):
 c=build_access_context(supabase,user);authorize(c,"complaints.read")
 q=admin.table("hr_complaints").select("id,org_id,ticket_number,property_id,complaint_type,category,severity,status,confidentiality_level,investigation_status,escalated,sla_deadline,sla_breached,created_at").eq("org_id",c.org_id)
 if status:q=q.eq("status",status.upper())
 if complaint_type:q=q.eq("complaint_type",complaint_type.upper())
 candidates=rows(q.order("created_at",desc=True).execute());assigned=rows(admin.table("complaint_case_members").select("complaint_id,user_id,case_role,can_view_identity,revoked_at").eq("org_id",c.org_id).eq("user_id",c.user_id).is_("revoked_at","null").execute());by_case={x["complaint_id"]:x for x in assigned}
 output=[]
 for item in candidates:
  if item["complaint_type"]=="POSH" and item["id"] not in by_case:continue
  if item["complaint_type"]!="POSH" and c.role not in {"OWNER","GROUP_ADMIN_HR"} and item["id"] not in by_case:continue
  output.append({**item,"case_role":by_case.get(item["id"],{}).get("case_role")})
 return output

@router.get("/cases/{complaint_id}")
async def case_detail(complaint_id:str,request:Request,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser,purpose:str=Query(min_length=5)):
 c=build_access_context(supabase,user);item=complaint(admin,c,complaint_id);authorize_case(c,item,members(admin,c,complaint_id));audit_access(supabase,c,complaint_id,"VIEW_CASE",purpose,ip_address=ip(request))
 base={k:v for k,v in item.items() if k not in {"phone","anonymous_token","employee_id"}}
 if item.get("employee_id")==c.user_id:return {"case":base,"reporter_view":True}
 return {"case":base,"members":[{k:m.get(k) for k in ("user_id","case_role","can_view_identity","assigned_at")} for m in members(admin,c,complaint_id)],"investigations":rows(admin.table("complaint_investigations").select("*").eq("complaint_id",complaint_id).execute()),"evidence":rows(admin.table("complaint_evidence").select("id,evidence_type,file_name,content_type,description,sha256_hash,collected_by,collected_at,is_redacted").eq("complaint_id",complaint_id).execute()),"escalations":rows(admin.table("complaint_escalations").select("*").eq("complaint_id",complaint_id).execute()),"resolution":(rows(admin.table("complaint_resolutions").select("*").eq("complaint_id",complaint_id).limit(1).execute()) or [None])[0]}

@router.post("/cases/{complaint_id}/members",status_code=201)
async def add_member(complaint_id:str,body:MemberBody,request:Request,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser):
 c=build_access_context(supabase,user)
 if c.role not in {"OWNER","GROUP_ADMIN_HR"}:raise HTTPException(403,"Only Owner or Group HR may assign confidential case access")
 item=complaint(admin,c,complaint_id)
 if item["complaint_type"]=="POSH" and body.case_role not in {"POSH_COMMITTEE","INVESTIGATOR","LEGAL","AUDITOR"}:raise HTTPException(422,"POSH access must use a committee, investigator, legal or auditor role")
 payload={"org_id":c.org_id,"complaint_id":complaint_id,**body.model_dump(),"assigned_by":c.user_id}
 saved=rows(supabase.table("complaint_case_members").upsert(payload,on_conflict="complaint_id,user_id,case_role").execute());audit_access(supabase,c,complaint_id,"ASSIGN_CASE_MEMBER",f"Assigned {body.case_role}",resource_type="CASE_MEMBER",resource_id=(saved[0].get("id") if saved else None),ip_address=ip(request));return saved[0] if saved else payload

@router.get("/cases/{complaint_id}/identity")
async def reveal_identity(complaint_id:str,request:Request,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser,purpose:str=Query(min_length=10)):
 c=build_access_context(supabase,user);item=complaint(admin,c,complaint_id);authorize_case(c,item,members(admin,c,complaint_id),identity=True);audit_access(supabase,c,complaint_id,"VIEW_REPORTER_IDENTITY",purpose,ip_address=ip(request))
 person=None
 if item.get("employee_id"):person=(rows(admin.table("users").select("id,full_name,email,phone").eq("id",item["employee_id"]).limit(1).execute()) or [None])[0]
 return {"complaint_id":complaint_id,"is_anonymous":item.get("is_anonymous"),"employee":person,"phone":item.get("phone")}

@router.post("/cases/{complaint_id}/investigations",status_code=201)
async def start_investigation(complaint_id:str,body:InvestigationBody,request:Request,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser):
 c=build_access_context(supabase,user);item=complaint(admin,c,complaint_id);case_members=members(admin,c,complaint_id);authorize_case(c,item,case_members,manage=True)
 investigator=next((member for member in case_members if member.get("user_id")==body.investigator_id and member.get("case_role") in {"INVESTIGATOR","POSH_COMMITTEE","LEGAL"} and not member.get("revoked_at")),None)
 if not investigator:raise HTTPException(422,"Investigator must have an active investigator, POSH committee or legal assignment on this case")
 payload={"org_id":c.org_id,"complaint_id":complaint_id,**body.model_dump(),"created_by":c.user_id,"started_at":now(),"status":"IN_PROGRESS"};saved=rows(supabase.table("complaint_investigations").insert(payload).execute());supabase.table("hr_complaints").update({"status":"UNDER_REVIEW","investigation_status":"IN_PROGRESS"}).eq("id",complaint_id).execute();audit_access(supabase,c,complaint_id,"START_INVESTIGATION",body.title,resource_type="INVESTIGATION",resource_id=(saved[0].get("id") if saved else None),ip_address=ip(request));return saved[0] if saved else payload

@router.patch("/investigations/{investigation_id}")
async def update_investigation(investigation_id:str,body:InvestigationUpdate,request:Request,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser):
 c=build_access_context(supabase,user);found=rows(admin.table("complaint_investigations").select("*").eq("id",investigation_id).eq("org_id",c.org_id).limit(1).execute())
 if not found:raise HTTPException(404,"Investigation not found")
 item=complaint(admin,c,found[0]["complaint_id"]);authorize_case(c,item,members(admin,c,item["id"]),manage=True);update={**body.model_dump(),"completed_at":now() if body.status=="COMPLETED" else None,"updated_at":now()};saved=rows(supabase.table("complaint_investigations").update(update).eq("id",investigation_id).execute());supabase.table("hr_complaints").update({"investigation_status":body.status}).eq("id",item["id"]).execute();audit_access(supabase,c,item["id"],"UPDATE_INVESTIGATION",f"Status changed to {body.status}",resource_type="INVESTIGATION",resource_id=investigation_id,ip_address=ip(request));return saved[0] if saved else update

@router.post("/cases/{complaint_id}/evidence/upload-url")
async def evidence_upload(complaint_id:str,body:UploadRequest,request:Request,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser):
 c=build_access_context(supabase,user);item=complaint(admin,c,complaint_id);authorize_case(c,item,members(admin,c,complaint_id),manage=True);audit_access(supabase,c,complaint_id,"REQUEST_EVIDENCE_UPLOAD","Upload encrypted case evidence",ip_address=ip(request));return S3Service().generate_grievance_evidence_upload_url(c.org_id,complaint_id,body.filename,body.content_type)

@router.post("/cases/{complaint_id}/evidence",status_code=201)
async def add_evidence(complaint_id:str,body:EvidenceBody,request:Request,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser):
 c=build_access_context(supabase,user);item=complaint(admin,c,complaint_id);authorize_case(c,item,members(admin,c,complaint_id),manage=True)
 if body.storage_key and not body.storage_key.startswith(f"grievance-evidence/{c.org_id}/{complaint_id}/"):raise HTTPException(422,"Evidence storage key is outside the case scope")
 payload={"org_id":c.org_id,"complaint_id":complaint_id,**body.model_dump(),"collected_by":c.user_id,"chain_of_custody":[{"action":"COLLECTED","actor_id":c.user_id,"at":now()}]};saved=rows(supabase.table("complaint_evidence").insert(payload).execute());audit_access(supabase,c,complaint_id,"ADD_EVIDENCE","Added investigation evidence",resource_type="EVIDENCE",resource_id=(saved[0].get("id") if saved else None),ip_address=ip(request));return saved[0] if saved else payload

@router.get("/evidence/{evidence_id}/download")
async def download_evidence(evidence_id:str,request:Request,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser,purpose:str=Query(min_length=5)):
 c=build_access_context(supabase,user);found=rows(admin.table("complaint_evidence").select("*").eq("id",evidence_id).eq("org_id",c.org_id).limit(1).execute())
 if not found:raise HTTPException(404,"Evidence not found")
 item=complaint(admin,c,found[0]["complaint_id"]);authorize_case(c,item,members(admin,c,item["id"]));audit_access(supabase,c,item["id"],"DOWNLOAD_EVIDENCE",purpose,resource_type="EVIDENCE",resource_id=evidence_id,ip_address=ip(request))
 if not found[0].get("storage_key"):raise HTTPException(409,"Evidence does not contain a file")
 return S3Service().generate_private_download_url(found[0]["storage_key"],300)

@router.post("/cases/{complaint_id}/escalations",status_code=201)
async def escalate(complaint_id:str,body:EscalationBody,request:Request,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser):
 c=build_access_context(supabase,user);item=complaint(admin,c,complaint_id);authorize_case(c,item,members(admin,c,complaint_id),manage=True);payload={"org_id":c.org_id,"complaint_id":complaint_id,"escalated_by":c.user_id,**body.model_dump()};saved=rows(supabase.table("complaint_escalations").insert(payload).execute());supabase.table("hr_complaints").update({"status":"ESCALATED","escalated":True,"escalated_at":now(),"escalated_to":body.escalated_to,"escalation_reason":body.reason}).eq("id",complaint_id).execute();audit_access(supabase,c,complaint_id,"ESCALATE_CASE",body.reason,resource_type="ESCALATION",resource_id=(saved[0].get("id") if saved else None),ip_address=ip(request));return saved[0] if saved else payload

@router.post("/cases/{complaint_id}/resolve",status_code=201)
async def resolve(complaint_id:str,body:ResolutionBody,request:Request,supabase:SupabaseClient,admin:SupabaseAdminClient,user:CurrentUser):
 c=build_access_context(supabase,user);item=complaint(admin,c,complaint_id);role=authorize_case(c,item,members(admin,c,complaint_id),manage=True)
 if item["complaint_type"]=="POSH" and role not in {"POSH_COMMITTEE","LEGAL"}:raise HTTPException(403,"Only assigned POSH committee or legal members may resolve a POSH case")
 payload={"org_id":c.org_id,"complaint_id":complaint_id,**body.model_dump(mode="json"),"approved_by":c.user_id,"closed_at":now()};saved=rows(supabase.table("complaint_resolutions").insert(payload).execute());supabase.table("hr_complaints").update({"status":"RESOLVED","outcome":body.outcome,"resolution_notes":body.resolution_summary,"resolved_at":now(),"investigation_status":"COMPLETED"}).eq("id",complaint_id).execute();audit_access(supabase,c,complaint_id,"RESOLVE_CASE",body.resolution_summary[:500],resource_type="RESOLUTION",resource_id=(saved[0].get("id") if saved else None),ip_address=ip(request));return saved[0] if saved else payload

@router.get("/access-audit")
async def access_audit(supabase:SupabaseClient,user:CurrentUser,complaint_id:Optional[str]=None):
 c=build_access_context(supabase,user)
 if c.role not in {"OWNER","GROUP_ADMIN_HR"}:raise HTTPException(403,"Only Owner or Group HR may review complaint access logs")
 q=supabase.table("complaint_access_audit").select("*").eq("org_id",c.org_id)
 if complaint_id:q=q.eq("complaint_id",complaint_id)
 return rows(q.order("occurred_at",desc=True).limit(500).execute())
