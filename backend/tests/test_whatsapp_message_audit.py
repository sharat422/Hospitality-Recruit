from unittest.mock import MagicMock, patch

from app.services.hr_bot_service import log_outbound_message


def _database():
    sb=MagicMock()
    chain=sb.table.return_value
    chain.insert.return_value.execute.return_value.data=[{"id":"out-1"}]
    chain.update.return_value.eq.return_value.execute.return_value.data=[]
    return sb


def test_successful_outbound_reply_is_persisted():
    sb=_database()
    employee={"employee_id":"emp-1","org_id":"org-1","whatsapp_user_id":"wu-1"}
    with patch("app.services.hr_bot_service.resolve_employee",return_value=employee):
        result=log_outbound_message(sb,"+919876543210","Namaste","wamid.out",
                                    provider="meta",inbound_message_id="in-1")
    assert result=="out-1"
    payload=sb.table.return_value.insert.call_args.args[0]
    assert payload["direction"]=="OUTBOUND"
    assert payload["twilio_sid"]=="wamid.out"
    assert payload["twilio_status"]=="sent"


def test_failed_outbound_reply_is_audited_without_fake_provider_id():
    sb=_database()
    with patch("app.services.hr_bot_service.resolve_employee",return_value=None):
        log_outbound_message(sb,"+919876543210","Retry later",None,provider="interakt")
    payload=sb.table.return_value.insert.call_args.args[0]
    assert payload["direction"]=="OUTBOUND"
    assert payload["twilio_sid"] is None
    assert payload["twilio_status"]=="failed"
