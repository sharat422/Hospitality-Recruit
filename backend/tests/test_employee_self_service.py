import pytest
from fastapi import HTTPException

from app.services.employee_self_service import employee_shifts, submit_grievance, submit_salary_advance
from tests.conftest import MockSupabase

ORG="11111111-1111-1111-1111-111111111111"; EMP="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"; PROP="22222222-2222-2222-2222-222222222222"


def test_pwa_and_whatsapp_share_published_shift_query():
    sb=MockSupabase(); expected=[{"assignment_id":"a1","employee_id":EMP,"assignment_status":"PUBLISHED"}]
    sb.configure("v_workforce_schedule",expected)
    assert employee_shifts(sb,EMP,days=7)==expected


def test_salary_advance_created_as_pwa_request():
    sb=MockSupabase();sb.configure("employee_salary_advance_requests",[],[{"id":"sa1","status":"PENDING","source":"PWA"}])
    result=submit_salary_advance(sb,org_id=ORG,property_id=PROP,employee_id=EMP,amount_inr=5000,
                                 reason="Medical emergency",repayment_months=2,source="PWA")
    assert result["status"]=="PENDING" and result["source"]=="PWA"


def test_second_active_salary_advance_is_blocked():
    sb=MockSupabase();sb.configure("employee_salary_advance_requests",[{"id":"existing"}])
    with pytest.raises(HTTPException) as exc:
        submit_salary_advance(sb,org_id=ORG,property_id=PROP,employee_id=EMP,amount_inr=5000,
                              reason="Medical emergency",repayment_months=2)
    assert exc.value.status_code==409


def test_anonymous_posh_complaint_has_no_employee_identity():
    sb=MockSupabase();sb.configure("hr_complaints",[{
        "ticket_number":"HR-1","status":"OPEN","category":"HARASSMENT","severity":"HIGH",
        "complaint_type":"POSH","employee_id":None,"is_anonymous":True,"anonymous_token":"secret"
    }])
    result=submit_grievance(sb,org_id=ORG,employee_id=EMP,phone="+919999999999",
        text="Inappropriate conduct at work",anonymous=True,complaint_type="POSH")
    assert result["employee_id"] is None
    assert result["category"]=="HARASSMENT" and result["anonymous_token"]


def test_short_grievance_is_rejected():
    with pytest.raises(HTTPException) as exc:
        submit_grievance(MockSupabase(),org_id=ORG,employee_id=EMP,phone=None,text="short")
    assert exc.value.status_code==422


def test_whatsapp_balance_uses_shared_pwa_leave_snapshot(monkeypatch):
    from app.services.hr_bot_service import handle_balance
    shared={"balance":{"casual_remaining":8,"casual_used":4,"sick_remaining":10,"sick_used":2,
                       "earned_remaining":15,"earned_used":0},"requests":[]}
    monkeypatch.setattr("app.services.employee_self_service.leave_snapshot",lambda sb,employee_id:shared)
    reply=handle_balance(MockSupabase(),{"employee_id":EMP,"name":"Asha"},[])
    assert "8 remaining" in reply and "33 days" in reply
