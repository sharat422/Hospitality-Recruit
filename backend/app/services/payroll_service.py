"""Configurable deterministic India payroll calculations and statutory exports."""
from __future__ import annotations
from calendar import monthrange
from datetime import date
from decimal import Decimal,ROUND_HALF_UP
import csv,hashlib,io,json

D=lambda x:Decimal(str(x or 0)); Q=lambda x:x.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
DEFAULT_RULES={"basic_pct":.5,"hra_pct_of_basic":.5,"epf_employee_pct":.12,"epf_employer_pct":.12,"epf_wage_cap_inr":15000,"epf_cap_enabled":True,"esic_employee_pct":.0075,"esic_employer_pct":.0325,"esic_wage_limit_inr":21000,"overtime_multiplier":2}

def calculate_payroll(*,year:int,month:int,compensation:dict,rules:dict|None=None,attendance:dict|None=None,adjustments:list[dict]|None=None,professional_tax_inr=0,tds_inr=None)->dict:
 r={**DEFAULT_RULES,**(rules or {})};a=attendance or {};adj=adjustments or []
 monthly=D(compensation["monthly_gross_inr"]);days=monthrange(year,month)[1]
 join=compensation.get("joining_date");join=date.fromisoformat(str(join)[:10]) if join else date(year,month,1)
 eligible=max(0,days-max(0,(join-date(year,month,1)).days));proration=D(eligible)/D(days)
 basic_full=D(compensation.get("basic_inr")) or Q(monthly*D(r["basic_pct"]));hra_full=D(compensation.get("hra_inr")) or Q(basic_full*D(r["hra_pct_of_basic"]))
 allowances_full=sum((D(v) for v in (compensation.get("allowances") or {}).values()),D(0));special_full=max(D(0),monthly-basic_full-hra_full-allowances_full)
 lop_days=D(a.get("lop_days",0));lop=Q(monthly/D(days)*lop_days);fixed=Q(monthly*proration);ot=Q(D(a.get("overtime_hours",0))*(monthly/D(days)/D(8))*D(r["overtime_multiplier"]))
 values={k:sum((D(x["amount_inr"]) for x in adj if x["adjustment_type"]==k),D(0)) for k in ['BONUS','INCENTIVE','ARREAR','DEDUCTION','REIMBURSEMENT']}
 gross=Q(fixed-lop+ot+values['BONUS']+values['INCENTIVE']+values['ARREAR']+values['REIMBURSEMENT'])
 basic=Q(basic_full*proration-Q(basic_full/D(days)*lop_days));hra=Q(hra_full*proration-Q(hra_full/D(days)*lop_days))
 epf_base=min(basic,D(r["epf_wage_cap_inr"])) if r.get("epf_cap_enabled") else basic
 epf_emp=Q(epf_base*D(r["epf_employee_pct"])) if compensation.get("epf_applicable",True) else D(0);epf_er=Q(epf_base*D(r["epf_employer_pct"])) if compensation.get("epf_applicable",True) else D(0)
 esic_ok=compensation.get("esic_applicable",True) and gross<=D(r["esic_wage_limit_inr"]);esic_emp=Q(gross*D(r["esic_employee_pct"])) if esic_ok else D(0);esic_er=Q(gross*D(r["esic_employer_pct"])) if esic_ok else D(0)
 tds=D(compensation.get("tds_monthly_inr",0) if tds_inr is None else tds_inr);pt=D(professional_tax_inr);ded=Q(epf_emp+esic_emp+pt+tds+values['DEDUCTION']);net=Q(gross-ded);employer=Q(gross+epf_er+esic_er)
 out={"year":year,"month":month,"calendar_days":days,"eligible_days":eligible,"proration_factor":round(float(proration),6),"basic_inr":float(basic),"hra_inr":float(hra),"special_allowance_inr":float(Q(special_full*proration)),"allowances_inr":float(Q(allowances_full*proration)),"gross_inr":float(gross),"lop_inr":float(lop),"overtime_inr":float(ot),"bonus_inr":float(values['BONUS']),"incentive_inr":float(values['INCENTIVE']),"arrears_inr":float(values['ARREAR']),"epf_employee_inr":float(epf_emp),"epf_employer_inr":float(epf_er),"esic_employee_inr":float(esic_emp),"esic_employer_inr":float(esic_er),"professional_tax_inr":float(pt),"tds_inr":float(tds),"other_deductions_inr":float(values['DEDUCTION']),"net_inr":float(net),"employer_cost_inr":float(employer),"annual_ctc_inr":float(D(compensation.get("annual_ctc_inr",0))),"esic_applicable":esic_ok}
 out["snapshot_hash"]=hashlib.sha256(json.dumps(out,sort_keys=True,separators=(',',':')).encode()).hexdigest();return out

def generate_statutory_export(export_type:str,items:list[dict])->bytes:
 export_type=export_type.upper();buf=io.StringIO(newline='')
 if export_type=='EPF_ECR':
  for x in items:buf.write(f"{x.get('uan','')}#~#{x.get('employee_name','')}#~#{x['calculation_snapshot'].get('gross_inr',0):.0f}#~#{x['calculation_snapshot'].get('epf_employee_inr',0):.0f}#~#{x['calculation_snapshot'].get('epf_employer_inr',0):.0f}\n")
 elif export_type in {'ESIC','FORM16_DATA'}:
  fields=['employee_id','employee_name','gross_inr','esic_employee_inr','esic_employer_inr'] if export_type=='ESIC' else ['employee_id','employee_name','gross_inr','tds_inr','professional_tax_inr']
  w=csv.DictWriter(buf,fieldnames=fields);w.writeheader()
  for x in items:w.writerow({f:x.get(f,x.get('calculation_snapshot',{}).get(f,'')) for f in fields})
 else:raise ValueError('Unsupported export type')
 return buf.getvalue().encode()
