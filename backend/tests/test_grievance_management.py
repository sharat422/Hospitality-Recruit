import pytest
from fastapi import HTTPException
from app.services.grievance_service import authorize_case

class Context:
    def __init__(self,user_id="u1",role="GENERAL_MANAGER"):self.user_id,self.role=user_id,role

def test_normal_manager_has_no_automatic_confidential_access():
    with pytest.raises(HTTPException) as exc:authorize_case(Context(),{"employee_id":"employee","is_anonymous":False,"complaint_type":"GRIEVANCE"},[])
    assert exc.value.status_code==404

def test_group_hr_can_triage_grievance_but_not_posh():
    assert authorize_case(Context(role="GROUP_ADMIN_HR"),{"complaint_type":"GRIEVANCE"},[])=="GROUP_ADMIN_HR"
    with pytest.raises(HTTPException):authorize_case(Context(role="GROUP_ADMIN_HR"),{"complaint_type":"POSH"},[])

def test_explicit_posh_committee_member_can_access_and_manage():
    members=[{"user_id":"u1","case_role":"POSH_COMMITTEE","can_view_identity":False,"revoked_at":None}]
    assert authorize_case(Context(),{"complaint_type":"POSH"},members,manage=True)=="POSH_COMMITTEE"

def test_identity_requires_separate_explicit_permission():
    members=[{"user_id":"u1","case_role":"INVESTIGATOR","can_view_identity":False,"revoked_at":None}]
    with pytest.raises(HTTPException):authorize_case(Context(),{"complaint_type":"GRIEVANCE"},members,identity=True)
    members[0]["can_view_identity"]=True
    assert authorize_case(Context(),{"complaint_type":"GRIEVANCE"},members,identity=True)=="INVESTIGATOR"

def test_named_reporter_can_read_own_base_case_but_not_manage():
    complaint={"employee_id":"u1","is_anonymous":False,"complaint_type":"GRIEVANCE"}
    assert authorize_case(Context(role="EMPLOYEE"),complaint,[])=="REPORTER"
    with pytest.raises(HTTPException):authorize_case(Context(role="EMPLOYEE"),complaint,[],manage=True)
