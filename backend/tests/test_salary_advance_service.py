from datetime import date
from fastapi import HTTPException
import pytest
from app.services.salary_advance_service import build_schedule,eligibility,review
from tests.conftest import MockSupabase

ORG="11111111-1111-1111-1111-111111111111";PROP="22222222-2222-2222-2222-222222222222";EMP="33333333-3333-3333-3333-333333333333"

def test_repayment_schedule_rounding_and_month_rollover():
 rows=build_schedule(10000,3,2026,12)
 assert [(x["due_year"],x["due_month"]) for x in rows]==[(2026,12),(2027,1),(2027,2)]
 assert sum(x["amount_inr"] for x in rows)==10000

def test_eligibility_uses_property_policy_and_compensation():
 sb=MockSupabase();sb.configure("salary_advance_policies",[{"minimum_tenure_days":90,"maximum_advance_pct":50,"maximum_amount_inr":20000,"maximum_repayment_months":6}]);sb.configure("employee_compensation_structures",[{"monthly_gross_inr":30000,"joining_date":"2025-01-01","effective_from":"2025-01-01"}]);sb.configure("employee_salary_advance_requests",[])
 result=eligibility(sb,org_id=ORG,property_id=PROP,employee_id=EMP,as_of=date(2026,1,1))
 assert result["eligible"] is True and result["maximum_eligible_amount_inr"]==15000

def test_active_advance_blocks_eligibility():
 sb=MockSupabase();sb.configure("salary_advance_policies",[],[]);sb.configure("employee_compensation_structures",[{"monthly_gross_inr":30000,"joining_date":"2025-01-01","effective_from":"2025-01-01"}]);sb.configure("employee_salary_advance_requests",[{"id":"active","status":"REPAYING","outstanding_balance_inr":5000}])
 assert eligibility(sb,org_id=ORG,property_id=PROP,employee_id=EMP,as_of=date(2026,1,1))["eligible"] is False

def test_review_is_fail_closed_when_audit_unavailable():
 item={"id":"a1","org_id":ORG,"employee_id":EMP,"status":"PENDING","amount_inr":5000,"requested_repayment_months":2}
 sb=MockSupabase();sb.configure("salary_advance_audit_logs",[])
 with pytest.raises(HTTPException) as exc:review(sb,item=item,actor_id="admin",action="APPROVE")
 assert exc.value.status_code==503

def test_approved_amount_cannot_exceed_request():
 item={"id":"a1","org_id":ORG,"employee_id":EMP,"status":"PENDING","amount_inr":5000,"requested_repayment_months":2}
 with pytest.raises(HTTPException) as exc:review(MockSupabase(),item=item,actor_id="admin",action="APPROVE",approved_amount=6000)
 assert exc.value.status_code==422
