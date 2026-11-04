"""Policy, ledger and payroll integration for employee salary advances."""
from __future__ import annotations
from calendar import monthrange
from datetime import date,datetime,timezone
from decimal import Decimal,ROUND_HALF_UP
from fastapi import HTTPException
from app.services.twilio_service import twilio_service

def rows(result):
 data=getattr(result,"data",None);return data if isinstance(data,list) else ([data] if isinstance(data,dict) else [])
def money(value):return Decimal(str(value or 0)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
def now():return datetime.now(timezone.utc).isoformat()
def add_month(year,month,offset):
 total=year*12+(month-1)+offset;return total//12,total%12+1

def get_policy(sb,org_id,property_id):
 found=rows(sb.table("salary_advance_policies").select("*").eq("org_id",org_id).eq("property_id",property_id).eq("is_active",True).limit(1).execute()) if property_id else []
 if not found:found=rows(sb.table("salary_advance_policies").select("*").eq("org_id",org_id).is_("property_id","null").eq("is_active",True).limit(1).execute())
 return found[0] if found else {"minimum_tenure_days":90,"maximum_advance_pct":50,"maximum_amount_inr":50000,"maximum_repayment_months":6,"require_manager_approval":True,"require_payroll_approval":True}

def eligibility(sb,*,org_id,property_id,employee_id,as_of=None):
 as_of=as_of or date.today();policy=get_policy(sb,org_id,property_id)
 comp=rows(sb.table("employee_compensation_structures").select("monthly_gross_inr,joining_date,effective_from").eq("org_id",org_id).eq("employee_id",employee_id).lte("effective_from",as_of.isoformat()).order("effective_from",desc=True).limit(1).execute())
 active=rows(sb.table("employee_salary_advance_requests").select("id,status,outstanding_balance_inr").eq("org_id",org_id).eq("employee_id",employee_id).in_("status",["PENDING","APPROVED","DISBURSED","REPAYING"]).limit(1).execute())
 reasons=[]
 if not comp:reasons.append("No active compensation structure")
 joining=(comp[0].get("joining_date") or comp[0].get("effective_from")) if comp else None
 tenure=(as_of-date.fromisoformat(str(joining)[:10])).days if joining else 0
 if tenure<int(policy["minimum_tenure_days"]):reasons.append(f"Minimum tenure is {policy['minimum_tenure_days']} days")
 if active:reasons.append("An active salary advance already exists")
 gross=money(comp[0].get("monthly_gross_inr")) if comp else Decimal(0)
 limit=min(gross*money(policy["maximum_advance_pct"])/100,money(policy["maximum_amount_inr"]))
 return {"eligible":not reasons,"reasons":reasons,"maximum_eligible_amount_inr":float(limit),"maximum_repayment_months":int(policy["maximum_repayment_months"]),"tenure_days":tenure,"policy":policy}

def audit(sb,*,org_id,advance_id,actor_id,action,before_status=None,after_status=None,amount=None,metadata=None):
 saved=rows(sb.table("salary_advance_audit_logs").insert({"org_id":org_id,"advance_id":advance_id,"actor_id":actor_id,"action":action,"before_status":before_status,"after_status":after_status,"amount_inr":float(money(amount)) if amount is not None else None,"metadata":metadata or {}}).execute())
 if not saved:raise HTTPException(503,"Salary advance action stopped because audit logging is unavailable")
 return saved[0]

def build_schedule(amount,months,start_year,start_month):
 total=money(amount);base=(total/Decimal(months)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP);out=[];used=Decimal(0)
 for i in range(1,months+1):
  year,month=add_month(start_year,start_month,i-1);part=total-used if i==months else base;used+=part
  out.append({"installment_number":i,"due_year":year,"due_month":month,"amount_inr":float(part)})
 return out

def notify(sb,employee_id,message):
 try:
  found=rows(sb.table("users").select("phone").eq("id",employee_id).limit(1).execute())
  if found and found[0].get("phone"):return twilio_service.send_sms(found[0]["phone"],message,channel="whatsapp")
 except Exception:return None

def notify_payroll_team(sb,org_id,property_id,message):
 try:
  q=sb.table("users").select("phone,role,active_property_id").eq("org_id",org_id).in_("role",["OWNER","GROUP_ADMIN_HR","HR_MANAGER"])
  for person in rows(q.execute()):
   if person.get("phone") and (not property_id or person.get("role") in {"OWNER","GROUP_ADMIN_HR"} or person.get("active_property_id")==property_id):twilio_service.send_sms(person["phone"],message,channel="whatsapp")
 except Exception:return None

def review(sb,*,item,actor_id,action,note=None,approved_amount=None,repayment_months=None):
 if item["status"]!="PENDING":raise HTTPException(409,"Request has already been reviewed")
 approved=action=="APPROVE";amount=money(approved_amount if approved_amount is not None else item["amount_inr"]);months=int(repayment_months or item["requested_repayment_months"])
 if approved and (amount<=0 or amount>money(item["amount_inr"])):raise HTTPException(422,"Approved amount must be positive and cannot exceed the requested amount")
 values={"status":"APPROVED" if approved else "REJECTED","reviewed_by":actor_id,"reviewed_at":now(),"review_note":note,"approved_amount_inr":float(amount) if approved else None,"approved_repayment_months":months if approved else None,"updated_at":now()}
 audit(sb,org_id=item["org_id"],advance_id=item["id"],actor_id=actor_id,action="APPROVED" if approved else "REJECTED",before_status="PENDING",after_status=values["status"],amount=amount,metadata={"note":note,"repayment_months":months})
 saved=rows(sb.table("employee_salary_advance_requests").update(values).eq("id",item["id"]).eq("status","PENDING").execute())
 if not saved:raise HTTPException(409,"Request changed while it was being reviewed")
 notify(sb,item["employee_id"],f"Salary advance {values['status'].lower()}: ₹{amount:,.2f}. / वेतन अग्रिम {values['status'].lower()}।")
 return saved[0]

def disburse(sb,*,item,actor_id,reference,first_year,first_month):
 if item["status"]!="APPROVED":raise HTTPException(409,"Only an approved advance can be disbursed")
 amount=money(item["approved_amount_inr"]);months=int(item["approved_repayment_months"])
 schedule=build_schedule(amount,months,first_year,first_month)
 audit(sb,org_id=item["org_id"],advance_id=item["id"],actor_id=actor_id,action="DISBURSED",before_status="APPROVED",after_status="REPAYING",amount=amount,metadata={"reference":reference})
 payloads=[{**x,"org_id":item["org_id"],"advance_id":item["id"],"employee_id":item["employee_id"]} for x in schedule]
 sb.table("salary_advance_repayments").insert(payloads).execute()
 values={"status":"REPAYING","outstanding_balance_inr":float(amount),"disbursed_at":now(),"paid_at":now(),"disbursed_by":actor_id,"disbursement_reference":reference,"updated_at":now()}
 saved=rows(sb.table("employee_salary_advance_requests").update(values).eq("id",item["id"]).eq("status","APPROVED").execute())
 if not saved:raise HTTPException(409,"Advance changed before disbursement")
 notify(sb,item["employee_id"],f"₹{amount:,.2f} salary advance disbursed. Repayment: {months} payroll deductions. / वेतन अग्रिम जारी हुआ।")
 return {"advance":saved[0],"repayment_schedule":payloads}

def sync_due_repayment(sb,*,run,employee_id,actor_id):
 due=rows(sb.table("salary_advance_repayments").select("*").eq("org_id",run["org_id"]).eq("employee_id",employee_id).eq("due_year",run["period_year"]).eq("due_month",run["period_month"]).in_("status",["SCHEDULED","IN_PAYROLL"]).execute())
 for installment in due:
  existing=rows(sb.table("payroll_adjustments").select("id").eq("salary_advance_repayment_id",installment["id"]).limit(1).execute())
  if existing:adjustment_id=existing[0]["id"]
  else:
   saved=rows(sb.table("payroll_adjustments").insert({"org_id":run["org_id"],"payroll_run_id":run["id"],"employee_id":employee_id,"adjustment_type":"DEDUCTION","amount_inr":installment["amount_inr"],"narration":f"Salary advance installment {installment['installment_number']}","created_by":actor_id,"salary_advance_repayment_id":installment["id"]}).execute());adjustment_id=saved[0]["id"] if saved else None
  sb.table("salary_advance_repayments").update({"status":"IN_PAYROLL","payroll_run_id":run["id"],"payroll_adjustment_id":adjustment_id,"updated_at":now()}).eq("id",installment["id"]).execute()

def finalize_repayments(sb,*,run,actor_id):
 due=rows(sb.table("salary_advance_repayments").select("*").eq("payroll_run_id",run["id"]).eq("status","IN_PAYROLL").execute())
 for installment in due:
  sb.table("salary_advance_repayments").update({"status":"DEDUCTED","deducted_at":now(),"updated_at":now()}).eq("id",installment["id"]).eq("status","IN_PAYROLL").execute()
  remaining=rows(sb.table("salary_advance_repayments").select("amount_inr").eq("advance_id",installment["advance_id"]).in_("status",["SCHEDULED","IN_PAYROLL","FAILED"]).execute());balance=sum(money(x["amount_inr"]) for x in remaining)
  values={"outstanding_balance_inr":float(balance),"status":"REPAID" if balance==0 else "REPAYING","closed_at":now() if balance==0 else None,"updated_at":now()}
  sb.table("employee_salary_advance_requests").update(values).eq("id",installment["advance_id"]).execute()
  audit(sb,org_id=run["org_id"],advance_id=installment["advance_id"],actor_id=actor_id,action="PAYROLL_DEDUCTION_POSTED",before_status="REPAYING",after_status=values["status"],amount=installment["amount_inr"],metadata={"payroll_run_id":run["id"],"installment_id":installment["id"]})
  advance=rows(sb.table("employee_salary_advance_requests").select("employee_id").eq("id",installment["advance_id"]).limit(1).execute())
  if advance:notify(sb,advance[0]["employee_id"],f"Salary advance deduction ₹{money(installment['amount_inr']):,.2f} posted. Balance ₹{balance:,.2f}. / वेतन अग्रिम कटौती दर्ज हुई।")
