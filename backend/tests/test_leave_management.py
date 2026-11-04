from datetime import date
import pytest
from fastapi import HTTPException
from app.services.leave_service import calculate_leave_days, review_leave_request, submit_leave_request
from tests.conftest import MockSupabase

ORG="11111111-1111-1111-1111-111111111111"; EMP="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"; PROP="22222222-2222-2222-2222-222222222222"

def configured_submission(source="WEB",remaining=12):
    sb=MockSupabase()
    sb.configure("leave_types",[{"code":"CASUAL","requires_hr_approval":False,"allow_negative_balance":False}])
    sb.configure("property_holidays",[])
    sb.configure("leave_requests",[],[{"id":"lr1","ticket_number":"LV-1","status":"PENDING","source":source}])
    sb.configure("leave_balances",[{"id":"b1","casual_total":remaining,"casual_used":0}],[])
    sb.configure("leave_audit_logs",[])
    return sb

def submit(sb,source="WEB"):
    return submit_leave_request(sb,org_id=ORG,employee_id=EMP,property_id=PROP,start_date=date(2026,9,7),end_date=date(2026,9,7),leave_type="CASUAL",reason="Family work",source=source)

def test_working_days_exclude_sunday_and_holiday():
    assert calculate_leave_days(date(2026,9,5),date(2026,9,8),["2026-09-07"])==2

@pytest.mark.parametrize("source",["WEB","PWA","WHATSAPP"])
def test_all_channels_use_same_submission(source):
    assert submit(configured_submission(source),source)["status"]=="PENDING"

def test_insufficient_balance_is_blocked():
    with pytest.raises(HTTPException) as exc: submit(configured_submission(remaining=0))
    assert exc.value.status_code==409

def test_manager_approval_finishes_standard_leave():
    sb=MockSupabase();sb.configure("leave_requests",[{"id":"lr1","status":"APPROVED"}]);sb.configure("leave_audit_logs",[])
    request={"id":"lr1","org_id":ORG,"employee_id":EMP,"status":"PENDING","manager_status":"PENDING","hr_status":"NOT_REQUIRED","leave_type":"CASUAL","start_date":"2026-09-07","total_days":1}
    assert review_leave_request(sb,request=request,actor_id="mgr",actor_role="DEPARTMENT_HEAD",action="APPROVE")["status"]=="APPROVED"

def test_manager_approval_routes_earned_leave_to_hr():
    sb=MockSupabase();sb.configure("leave_requests",[{"id":"lr1","status":"PENDING","manager_status":"APPROVED","hr_status":"PENDING"}]);sb.configure("leave_audit_logs",[])
    request={"id":"lr1","org_id":ORG,"employee_id":EMP,"status":"PENDING","manager_status":"PENDING","hr_status":"PENDING","leave_type":"EARNED","start_date":"2026-09-07","total_days":1}
    assert review_leave_request(sb,request=request,actor_id="mgr",actor_role="DEPARTMENT_HEAD",action="APPROVE")["hr_status"]=="PENDING"

def test_non_hr_cannot_perform_second_stage():
    sb=MockSupabase();request={"id":"lr1","org_id":ORG,"employee_id":EMP,"status":"PENDING","manager_status":"APPROVED","hr_status":"PENDING","leave_type":"EARNED","start_date":"2026-09-07","total_days":1}
    with pytest.raises(HTTPException) as exc: review_leave_request(sb,request=request,actor_id="mgr",actor_role="DEPARTMENT_HEAD",action="APPROVE")
    assert exc.value.status_code==403
