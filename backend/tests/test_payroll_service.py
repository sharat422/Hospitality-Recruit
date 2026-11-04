from datetime import date
from app.services.payroll_service import calculate_payroll,generate_statutory_export

def comp(gross,**kw):return {'monthly_gross_inr':gross,'annual_ctc_inr':gross*13,'joining_date':date(2026,1,1),'epf_applicable':True,'esic_applicable':True,'allowances':{},**kw}

def test_known_20000_example():
 r=calculate_payroll(year=2026,month=4,compensation=comp(20000),professional_tax_inr=200)
 assert r['basic_inr']==10000 and r['hra_inr']==5000
 assert r['epf_employee_inr']==1200 and r['esic_employee_inr']==150
 assert r['professional_tax_inr']==200 and r['net_inr']==18450
 assert r['employer_cost_inr']==21850

def test_esic_not_applicable_above_limit():
 r=calculate_payroll(year=2026,month=4,compensation=comp(30000),professional_tax_inr=200)
 assert not r['esic_applicable'] and r['esic_employee_inr']==0 and r['net_inr']==28000

def test_epf_wage_cap_is_configurable():
 capped=calculate_payroll(year=2026,month=4,compensation=comp(50000))
 actual=calculate_payroll(year=2026,month=4,compensation=comp(50000),rules={'epf_cap_enabled':False})
 assert capped['epf_employee_inr']==1800 and actual['epf_employee_inr']==3000

def test_mid_month_joining_proration():
 r=calculate_payroll(year=2026,month=7,compensation=comp(30000,joining_date=date(2026,7,16)))
 assert r['eligible_days']==16 and r['gross_inr']==15483.87

def test_lop_uses_validated_absence_input():
 r=calculate_payroll(year=2026,month=4,compensation=comp(20000),attendance={'lop_days':2})
 assert r['lop_inr']==1333.33 and r['gross_inr']==18666.67

def test_overtime_bonus_incentive_arrears_and_deduction():
 adjustments=[{'adjustment_type':'BONUS','amount_inr':1000},{'adjustment_type':'INCENTIVE','amount_inr':500},{'adjustment_type':'ARREAR','amount_inr':250},{'adjustment_type':'DEDUCTION','amount_inr':100}]
 r=calculate_payroll(year=2026,month=4,compensation=comp(30000),attendance={'overtime_hours':8},adjustments=adjustments)
 assert r['overtime_inr']==2000 and r['bonus_inr']==1000 and r['incentive_inr']==500 and r['arrears_inr']==250 and r['other_deductions_inr']==100

def test_snapshot_hash_is_deterministic_and_changes_with_input():
 a=calculate_payroll(year=2026,month=4,compensation=comp(20000));b=calculate_payroll(year=2026,month=4,compensation=comp(20000));c=calculate_payroll(year=2026,month=4,compensation=comp(21000))
 assert a['snapshot_hash']==b['snapshot_hash'] and a['snapshot_hash']!=c['snapshot_hash']

def test_statutory_exports():
 items=[{'employee_id':'e1','employee_name':'A','uan':'100','calculation_snapshot':{'gross_inr':20000,'epf_employee_inr':1200,'epf_employer_inr':1200,'esic_employee_inr':150,'esic_employer_inr':650,'tds_inr':0,'professional_tax_inr':200}}]
 assert b'#~#' in generate_statutory_export('EPF_ECR',items)
 assert b'esic_employee_inr' in generate_statutory_export('ESIC',items)
 assert b'tds_inr' in generate_statutory_export('FORM16_DATA',items)
