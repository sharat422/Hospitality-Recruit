"""Property-scoped payroll runs, approvals, payslips and statutory exports."""
from datetime import date,datetime,timezone
from hashlib import sha256
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import Response
from pydantic import BaseModel,Field
from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.payroll_service import DEFAULT_RULES,calculate_payroll,generate_statutory_export
from app.services.attendance_codes_service import DEFAULT_CODES,code_from_row,lop_days
from app.services.payslip_pdf import generate_payslip_pdf
from app.services.rbac_service import authorize,build_access_context
from app.services.india_compliance_service import get_professional_tax
from app.services.salary_advance_service import finalize_repayments,sync_due_repayment

router=APIRouter();CurrentUser=Annotated[dict,Depends(get_current_user)]
def rows(r):d=getattr(r,'data',None);return d if isinstance(d,list) else ([d] if isinstance(d,dict) else [])
def now():return datetime.now(timezone.utc).isoformat()
class RuleBody(BaseModel):
 property_id:str|None=None;name:str='Default India Payroll';effective_from:date;effective_to:date|None=None
 basic_pct:float=Field(.5,ge=0,le=1);hra_pct_of_basic:float=Field(.5,ge=0,le=1);epf_employee_pct:float=Field(.12,ge=0,le=1);epf_employer_pct:float=Field(.12,ge=0,le=1);epf_wage_cap_inr:float=Field(15000,ge=0);epf_cap_enabled:bool=True;esic_employee_pct:float=Field(.0075,ge=0,le=1);esic_employer_pct:float=Field(.0325,ge=0,le=1);esic_wage_limit_inr:float=Field(21000,ge=0);overtime_multiplier:float=Field(2,ge=1);settings:dict={}
class CompensationBody(BaseModel):
 employee_id:str;property_id:str;effective_from:date;effective_to:date|None=None;annual_ctc_inr:float|None=Field(None,ge=0);monthly_gross_inr:float=Field(gt=0);basic_inr:float|None=Field(None,ge=0);hra_inr:float|None=Field(None,ge=0);allowances:dict[str,float]={};state_code:str=Field(min_length=2,max_length=3);joining_date:date|None=None;epf_applicable:bool=True;esic_applicable:bool=True;tds_monthly_inr:float=Field(0,ge=0)
class RunBody(BaseModel):property_id:str;period_year:int=Field(ge=2020,le=2100);period_month:int=Field(ge=1,le=12);rule_id:str|None=None
class AdjustmentBody(BaseModel):employee_id:str;adjustment_type:Literal['BONUS','INCENTIVE','ARREAR','DEDUCTION','REIMBURSEMENT'];amount_inr:float;narration:str=Field(min_length=3)
class NoteBody(BaseModel):note:str|None=None

@router.get('/rules')
async def rules(property_id:str,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);authorize(c,'payroll.read',property_id=property_id);return rows(supabase.table('payroll_rules').select('*').eq('org_id',c.org_id).or_(f'property_id.eq.{property_id},property_id.is.null').order('effective_from',desc=True).execute())
@router.post('/rules',status_code=201)
async def create_rule(body:RuleBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);authorize(c,'payroll.manage',property_id=body.property_id);saved=rows(supabase.table('payroll_rules').insert({**body.model_dump(mode='json'),'org_id':c.org_id,'created_by':c.user_id}).execute());return saved[0] if saved else body.model_dump(mode='json')
@router.post('/compensation',status_code=201)
async def compensation(body:CompensationBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);authorize(c,'payroll.manage',property_id=body.property_id);saved=rows(supabase.table('employee_compensation_structures').insert({**body.model_dump(mode='json'),'org_id':c.org_id,'created_by':c.user_id}).execute());return saved[0] if saved else body.model_dump(mode='json')
@router.post('/preview')
async def preview(body:CompensationBody,supabase:SupabaseClient,user:CurrentUser,year:int,month:int):
 c=build_access_context(supabase,user);authorize(c,'payroll.manage',property_id=body.property_id);return calculate_payroll(year=year,month=month,compensation=body.model_dump(mode='json'))
@router.post('/runs',status_code=201)
async def create_run(body:RunBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);authorize(c,'payroll.manage',property_id=body.property_id);payload={**body.model_dump(),'org_id':c.org_id,'created_by':c.user_id};saved=rows(supabase.table('payroll_runs').insert(payload).execute());return saved[0] if saved else payload
@router.get('/runs')
async def list_runs(property_id:str,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);authorize(c,'payroll.read',property_id=property_id);return rows(supabase.table('payroll_runs').select('*').eq('org_id',c.org_id).eq('property_id',property_id).order('period_year',desc=True).order('period_month',desc=True).execute())
@router.post('/runs/{run_id}/adjustments',status_code=201)
async def adjustment(run_id:str,body:AdjustmentBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);run=_run(supabase,c,run_id,'payroll.manage');_draft(run);saved=rows(supabase.table('payroll_adjustments').insert({**body.model_dump(),'org_id':c.org_id,'payroll_run_id':run_id,'created_by':c.user_id}).execute());return saved[0] if saved else body.model_dump()
@router.post('/runs/{run_id}/calculate')
async def calculate_run(run_id:str,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);run=_run(supabase,c,run_id,'payroll.manage');_draft(run)
 comps=rows(supabase.table('employee_compensation_structures').select('*').eq('org_id',c.org_id).eq('property_id',run['property_id']).lte('effective_from',f"{run['period_year']}-{run['period_month']:02d}-28").execute())
 rule_rows=rows(supabase.table('payroll_rules').select('*').eq('id',run.get('rule_id')).limit(1).execute()) if run.get('rule_id') else [];rule=rule_rows[0] if rule_rows else DEFAULT_RULES
 code_rows=rows(supabase.table('attendance_codes').select('*').eq('org_id',c.org_id).eq('property_id',run['property_id']).eq('is_active',True).execute())
 att_codes=[code_from_row(r) for r in code_rows] if code_rows else list(DEFAULT_CODES)
 items=[]
 for comp in comps:
  att=rows(supabase.table('validated_attendance_for_payroll').select('*').eq('employee_id',comp['employee_id']).gte('attendance_date',f"{run['period_year']}-{run['period_month']:02d}-01").lte('attendance_date',f"{run['period_year']}-{run['period_month']:02d}-31").execute())
  attendance={'lop_days':lop_days(att,att_codes),'overtime_hours':sum(float(x.get('overtime_minutes') or 0) for x in att)/60,'validated_days':len(att)}
  sync_due_repayment(supabase,run=run,employee_id=comp['employee_id'],actor_id=c.user_id)
  adjustments=rows(supabase.table('payroll_adjustments').select('*').eq('payroll_run_id',run_id).eq('employee_id',comp['employee_id']).execute())
  pt=get_professional_tax(supabase,comp['state_code'],float(comp['monthly_gross_inr']),run['period_month']).get('pt_inr',0)
  calc=calculate_payroll(year=run['period_year'],month=run['period_month'],compensation=comp,rules=rule,attendance=attendance,adjustments=adjustments,professional_tax_inr=pt)
  payload={'org_id':c.org_id,'payroll_run_id':run_id,'employee_id':comp['employee_id'],'compensation_structure_id':comp['id'],'attendance_snapshot':attendance,'rule_snapshot':rule,'calculation_snapshot':calc,'snapshot_hash':calc['snapshot_hash'],'gross_inr':calc['gross_inr'],'net_inr':calc['net_inr'],'employer_cost_inr':calc['employer_cost_inr'],'lop_inr':calc['lop_inr'],'overtime_inr':calc['overtime_inr'],'bonus_inr':calc['bonus_inr'],'incentive_inr':calc['incentive_inr'],'arrears_inr':calc['arrears_inr']}
  saved=rows(supabase.table('payroll_run_items').upsert(payload,on_conflict='payroll_run_id,employee_id').execute());items.append(saved[0] if saved else payload)
 totals={'employees':len(items),'gross_inr':sum(x['gross_inr'] for x in items),'net_inr':sum(x['net_inr'] for x in items),'employer_cost_inr':sum(x['employer_cost_inr'] for x in items)};supabase.table('payroll_runs').update({'status':'CALCULATED','totals':totals,'updated_at':now()}).eq('id',run_id).execute();return {'items':items,'totals':totals}
@router.post('/runs/{run_id}/submit')
async def submit_run(run_id:str,body:NoteBody,supabase:SupabaseClient,user:CurrentUser):return _transition(supabase,user,run_id,'CALCULATED','PENDING_APPROVAL','SUBMITTED',body.note)
@router.post('/runs/{run_id}/approve')
async def approve_run(run_id:str,body:NoteBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);run=_run(supabase,c,run_id,'payroll.manage')
 if run['created_by']==c.user_id:raise HTTPException(409,'Maker-checker violation: payroll creator cannot approve the run')
 return _transition_ctx(supabase,c,run,'PENDING_APPROVAL','APPROVED','APPROVED',body.note)
@router.post('/runs/{run_id}/finalize')
async def finalize(run_id:str,body:NoteBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);run=_run(supabase,c,run_id,'payroll.manage')
 if run['status']!='APPROVED':raise HTTPException(409,'Payroll must be approved before finalization')
 items=rows(supabase.table('payroll_run_items').select('*').eq('payroll_run_id',run_id).execute())
 for item in items:
  calc=item['calculation_snapshot'];slip={'org_id':c.org_id,'employee_id':item['employee_id'],'month':run['period_month'],'year':run['period_year'],'payroll_run_item_id':item['id'],'annual_ctc_inr':calc.get('annual_ctc_inr'),'gross_salary_inr':calc['gross_inr'],'basic_salary_inr':calc['basic_inr'],'hra_inr':calc['hra_inr'],'allowances_inr':calc['allowances_inr'],'overtime_inr':calc['overtime_inr'],'bonus_inr':calc['bonus_inr'],'incentives_inr':calc['incentive_inr'],'arrears_inr':calc['arrears_inr'],'lop_inr':calc['lop_inr'],'epf_deduction_inr':calc['epf_employee_inr'],'esic_deduction_inr':calc['esic_employee_inr'],'professional_tax_inr':calc['professional_tax_inr'],'tds_inr':calc['tds_inr'],'other_deductions_inr':calc['other_deductions_inr'],'net_salary_inr':calc['net_inr'],'snapshot_hash':item['snapshot_hash'],'status':'FINALIZED'}
  existing=rows(supabase.table('payslips').select('id,snapshot_hash,status').eq('employee_id',item['employee_id']).eq('month',run['period_month']).eq('year',run['period_year']).limit(1).execute())
  if existing and existing[0].get('snapshot_hash')!=item['snapshot_hash']:raise HTTPException(409,f"A different finalized payslip already exists for employee {item['employee_id']}")
  if not existing:supabase.table('payslips').insert(slip).execute()
  if item.get('status')!='FINALIZED':supabase.table('payroll_run_items').update({'status':'FINALIZED'}).eq('id',item['id']).execute()
 finalize_repayments(supabase,run=run,actor_id=c.user_id)
 return _transition_ctx(supabase,c,run,'APPROVED','FINALIZED','FINALIZED',body.note)
@router.get('/runs/{run_id}/exports/{export_type}')
async def export(run_id:str,export_type:Literal['EPF_ECR','ESIC','FORM16_DATA'],supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);run=_run(supabase,c,run_id,'payroll.manage')
 if run['status']!='FINALIZED':raise HTTPException(409,'Finalize payroll before statutory export')
 items=rows(supabase.table('payroll_run_items').select('*').eq('payroll_run_id',run_id).execute());content=generate_statutory_export(export_type,items);checksum=sha256(content).hexdigest();supabase.table('payroll_statutory_exports').upsert({'org_id':c.org_id,'payroll_run_id':run_id,'export_type':export_type,'checksum':checksum,'generated_by':c.user_id},on_conflict='payroll_run_id,export_type').execute();ext='txt' if export_type=='EPF_ECR' else 'csv';return Response(content,media_type='text/plain' if ext=='txt' else 'text/csv',headers={'Content-Disposition':f'attachment; filename={export_type.lower()}_{run_id}.{ext}'})
@router.get('/payslips/{payslip_id}/pdf')
async def payslip_pdf(payslip_id:str,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);found=rows(supabase.table('payslips').select('*').eq('id',payslip_id).eq('org_id',c.org_id).limit(1).execute())
 if not found:raise HTTPException(404,'Payslip not found')
 slip=found[0];authorize(c,'payroll.read',owner_user_id=slip['employee_id'])
 emp=rows(supabase.table('users').select('full_name').eq('id',slip['employee_id']).limit(1).execute())
 pdf=generate_payslip_pdf(slip,emp[0].get('full_name','Employee') if emp else 'Employee')
 if not pdf:raise HTTPException(503,'PDF generator is not installed')
 return Response(pdf,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename=payslip-{slip["year"]}-{slip["month"]:02d}.pdf'})

@router.get('/payslips')
async def list_payslips(supabase:SupabaseClient,user:CurrentUser,employee_id:str|None=None):
 c=build_access_context(supabase,user);target=employee_id or c.user_id;authorize(c,'payroll.read',owner_user_id=target)
 q=supabase.table('payslips').select('*').eq('org_id',c.org_id)
 if c.role in {'EMPLOYEE','CANDIDATE'} or employee_id:q=q.eq('employee_id',target)
 return rows(q.order('year',desc=True).order('month',desc=True).execute())

def _run(sb,c,run_id,permission):
 found=rows(sb.table('payroll_runs').select('*').eq('id',run_id).eq('org_id',c.org_id).limit(1).execute())
 if not found:raise HTTPException(404,'Payroll run not found')
 authorize(c,permission,property_id=found[0]['property_id']);return found[0]
def _draft(run):
 if run['status'] not in {'DRAFT','CALCULATED'}:raise HTTPException(409,'Payroll run is not editable')
def _transition(sb,user,run_id,expected,target,action,note):
 c=build_access_context(sb,user);run=_run(sb,c,run_id,'payroll.manage');return _transition_ctx(sb,c,run,expected,target,action,note)
def _transition_ctx(sb,c,run,expected,target,action,note):
 if run['status']!=expected:raise HTTPException(409,f'Payroll must be {expected}')
 stamp=now();payload={'status':target,'updated_at':stamp}
 if action=='SUBMITTED':payload.update(submitted_by=c.user_id,submitted_at=stamp)
 elif action=='APPROVED':payload.update(approved_by=c.user_id,approved_at=stamp)
 elif action=='FINALIZED':payload.update(finalized_by=c.user_id,finalized_at=stamp)
 saved=rows(sb.table('payroll_runs').update(payload).eq('id',run['id']).execute());sb.table('payroll_approval_logs').insert({'org_id':c.org_id,'payroll_run_id':run['id'],'actor_id':c.user_id,'action':action,'note':note,'before_status':expected,'after_status':target}).execute();return saved[0] if saved else {**run,**payload}
