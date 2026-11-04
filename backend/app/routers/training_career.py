"""Learning catalog, assessments, skill gaps, career pathways and internal jobs."""
from datetime import datetime
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.rbac_service import authorize, build_access_context
from app.services.training_career_service import calculate_promotion_readiness, score_quiz

router = APIRouter(tags=["Training & Career"])
CurrentUser = Annotated[dict, Depends(get_current_user)]
def rows(result): return getattr(result, "data", None) or []
def now(): return datetime.utcnow().isoformat()

class CourseCreate(BaseModel):
    title: str = Field(min_length=2); description: Optional[str]=None; property_id: Optional[str]=None
    department_id: Optional[str]=None; category: str="ROLE_SKILL"; delivery_type: str="VIDEO"
    content_url: Optional[str]=None; duration_minutes: int=Field(0,ge=0); pass_score: float=Field(70,ge=0,le=100)
class AssignCourse(BaseModel): employee_id: str; due_date: Optional[str]=None
class ProgressUpdate(BaseModel): progress_pct: float=Field(ge=0,le=100)
class QuizSubmit(BaseModel): answers: dict[str,str]
class PathwayCreate(BaseModel):
    name: str; department_name: str; property_id: Optional[str]=None; department_id: Optional[str]=None
class StepCreate(BaseModel):
    step_order: int=Field(ge=1); current_role_title: str; target_role_title: str
    minimum_performance_score: float=Field(70,ge=0,le=100); minimum_tenure_months: int=Field(0,ge=0)
    required_skills: list[dict]=Field(default_factory=list); required_course_ids: list[str]=Field(default_factory=list)
class PlanCreate(BaseModel): employee_id: str; pathway_id: str; target_step_id: str

def employee(db, org, employee_id):
    data=rows(db.table("users").select("id,org_id,active_property_id,department_id,job_title,joining_date").eq("id",employee_id).eq("org_id",org).limit(1).execute())
    if not data: raise HTTPException(404,"Employee not found")
    return data[0]

def award_course_skills(db, org_id, employee_id, course_id):
    mappings=rows(db.table("training_course_skills").select("skill_id,proficiency_awarded").eq("course_id",course_id).execute())
    for item in mappings:
        db.table("employee_skills").upsert({"org_id":org_id,"employee_id":employee_id,"skill_id":item["skill_id"],
            "proficiency":item["proficiency_awarded"],"source":"TRAINING","evidence_id":course_id,"verified_at":now()},on_conflict="employee_id,skill_id").execute()

@router.get("/courses")
async def courses(supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"training.read")
    return rows(supabase.table("training_courses").select("*").or_(f"org_id.is.null,org_id.eq.{c.org_id}").eq("is_active",True).order("title").execute())

@router.post("/courses",status_code=201)
async def create_course(body:CourseCreate,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"training.manage",property_id=body.property_id,department_id=body.department_id)
    payload={"org_id":c.org_id,**body.model_dump(),"delivery_type":body.delivery_type.upper(),"created_by":c.user_id}
    data=rows(supabase.table("training_courses").insert(payload).execute()); return data[0] if data else payload

@router.post("/assign",status_code=201)
async def assign(body:AssignCourse,course_id:str,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"training.manage")
    emp=employee(supabase,c.org_id,body.employee_id); course=rows(supabase.table("training_courses").select("*").eq("id",course_id).limit(1).execute())
    if not course: raise HTTPException(404,"Course not found")
    payload={"org_id":c.org_id,"employee_id":emp["id"],"property_id":emp.get("active_property_id"),"department_id":emp.get("department_id"),"course_id":course_id,"training_name":course[0]["title"],"provider":"Internal Learning","category":course[0]["category"],"due_date":body.due_date,"created_by":c.user_id}
    try: data=rows(supabase.table("employee_training_records").insert(payload).execute())
    except Exception as exc:
        if "unique" in str(exc).lower(): raise HTTPException(409,"Employee already has this active course")
        raise
    return data[0] if data else payload

@router.get("/my-learning")
async def my_learning(supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"training.read",owner_user_id=c.user_id)
    return rows(supabase.table("employee_training_records").select("*,training_courses(*)").eq("employee_id",c.user_id).order("assigned_at",desc=True).execute())

@router.patch("/enrollments/{enrollment_id}/progress")
async def progress(enrollment_id:str,body:ProgressUpdate,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"training.read")
    found=rows(supabase.table("employee_training_records").select("*").eq("id",enrollment_id).eq("employee_id",c.user_id).limit(1).execute())
    if not found: raise HTTPException(404,"Enrollment not found")
    status="IN_PROGRESS" if body.progress_pct<100 else ("COMPLETED" if found[0].get("quiz_passed") is not False else "IN_PROGRESS")
    payload={"progress_pct":body.progress_pct,"status":status,"last_activity_at":now(),"completed_at":now() if status=="COMPLETED" else None}
    data=rows(supabase.table("employee_training_records").update(payload).eq("id",enrollment_id).eq("employee_id",c.user_id).execute())
    if status=="COMPLETED" and found[0].get("course_id"): award_course_skills(supabase,c.org_id,c.user_id,found[0]["course_id"])
    return data[0] if data else payload

@router.get("/enrollments/{enrollment_id}/quiz")
async def get_quiz(enrollment_id:str,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"training.read")
    enrollment=rows(supabase.table("employee_training_records").select("course_id").eq("id",enrollment_id).eq("employee_id",c.user_id).limit(1).execute())
    if not enrollment or not enrollment[0].get("course_id"): raise HTTPException(404,"Course enrollment not found")
    quiz=rows(supabase.table("training_quizzes").select("id,title,pass_score,max_attempts").eq("course_id",enrollment[0]["course_id"]).eq("is_active",True).limit(1).execute())
    if not quiz: raise HTTPException(404,"Quiz not found")
    questions=rows(supabase.table("training_quiz_questions").select("id,question_text,options,order_index").eq("quiz_id",quiz[0]["id"]).order("order_index").execute())
    return {**quiz[0],"questions":questions}

@router.post("/enrollments/{enrollment_id}/quiz")
async def submit_quiz(enrollment_id:str,body:QuizSubmit,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"training.read")
    enrollment=rows(supabase.table("employee_training_records").select("*").eq("id",enrollment_id).eq("employee_id",c.user_id).limit(1).execute())
    if not enrollment or not enrollment[0].get("course_id"): raise HTTPException(404,"Course enrollment not found")
    quizzes=rows(supabase.table("training_quizzes").select("*").eq("course_id",enrollment[0]["course_id"]).eq("is_active",True).limit(1).execute())
    if not quizzes: raise HTTPException(404,"Quiz not found")
    prior=rows(supabase.table("training_quiz_attempts").select("id").eq("quiz_id",quizzes[0]["id"]).eq("employee_id",c.user_id).execute())
    if len(prior)>=int(quizzes[0].get("max_attempts") or 3): raise HTTPException(409,"Maximum quiz attempts reached")
    questions=rows(supabase.table("training_quiz_questions").select("id,correct_option").eq("quiz_id",quizzes[0]["id"]).execute())
    result=score_quiz(questions,body.answers); passed=result["score"]>=float(quizzes[0]["pass_score"])
    attempt={"org_id":c.org_id,"enrollment_id":enrollment_id,"employee_id":c.user_id,"quiz_id":quizzes[0]["id"],"answers":body.answers,"score":result["score"],"passed":passed}
    supabase.table("training_quiz_attempts").insert(attempt).execute()
    update={"score":result["score"],"quiz_passed":passed,"last_activity_at":now()}
    if passed and float(enrollment[0].get("progress_pct") or 0)>=100: update|={"status":"COMPLETED","completed_at":now()}
    supabase.table("employee_training_records").update(update).eq("id",enrollment_id).execute()
    if update.get("status")=="COMPLETED": award_course_skills(supabase,c.org_id,c.user_id,enrollment[0]["course_id"])
    return {**result,"passed":passed}

@router.get("/pathways")
async def pathways(supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"career.read")
    return rows(supabase.table("career_pathways").select("*,career_pathway_steps(*)").or_(f"org_id.is.null,org_id.eq.{c.org_id}").eq("is_active",True).order("department_name").execute())

@router.post("/pathways",status_code=201)
async def create_pathway(body:PathwayCreate,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"career.manage",property_id=body.property_id,department_id=body.department_id)
    payload={"org_id":c.org_id,**body.model_dump(),"created_by":c.user_id}; data=rows(supabase.table("career_pathways").insert(payload).execute()); return data[0] if data else payload

@router.post("/pathways/{pathway_id}/steps",status_code=201)
async def create_step(pathway_id:str,body:StepCreate,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"career.manage")
    payload={"pathway_id":pathway_id,**body.model_dump()}; data=rows(supabase.table("career_pathway_steps").insert(payload).execute()); return data[0] if data else payload

@router.post("/plans",status_code=201)
async def create_plan(body:PlanCreate,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"career.manage"); employee(supabase,c.org_id,body.employee_id)
    payload={"org_id":c.org_id,**body.model_dump(),"created_by":c.user_id}; data=rows(supabase.table("employee_career_plans").insert(payload).execute()); return data[0] if data else payload

@router.get("/employees/{employee_id}/readiness")
async def readiness(employee_id:str,supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"career.read",owner_user_id=employee_id); emp=employee(supabase,c.org_id,employee_id)
    plans=rows(supabase.table("employee_career_plans").select("*").eq("employee_id",employee_id).eq("status","ACTIVE").limit(1).execute())
    if not plans: raise HTTPException(404,"No active career plan")
    step=rows(supabase.table("career_pathway_steps").select("*").eq("id",plans[0]["target_step_id"]).limit(1).execute())
    skills=rows(supabase.table("employee_skills").select("*,skill_definitions(name,code)").eq("employee_id",employee_id).execute())
    training=rows(supabase.table("employee_training_records").select("course_id").eq("employee_id",employee_id).eq("status","COMPLETED").execute())
    reviews=rows(supabase.table("employee_performance_reviews").select("overall_score,outcome_status").eq("employee_id",employee_id).order("review_period_end",desc=True).limit(1).execute())
    result=calculate_promotion_readiness(step=step[0],employee_skills=skills,completed_course_ids={str(x["course_id"]) for x in training if x.get("course_id")},performance_score=reviews[0].get("overall_score") if reviews else None,joining_date=emp.get("joining_date"))
    result["manager_outcome_approved"]=bool(reviews and reviews[0].get("outcome_status")=="APPROVED")
    result["promotion_action_allowed"]=result["ready"] and result["manager_outcome_approved"]
    return result

@router.get("/internal-jobs")
async def internal_jobs(supabase:SupabaseClient,user:CurrentUser):
    c=build_access_context(supabase,user); authorize(c,"career.read")
    return rows(supabase.table("jobs").select("id,title,department_id,property_id,salary_min_inr,salary_max_inr,required_skills,status,visibility").eq("org_id",c.org_id).in_("visibility",["INTERNAL","BOTH"]).eq("status","open").execute())
