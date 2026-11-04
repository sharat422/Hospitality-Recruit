from datetime import date
from unittest.mock import patch
from app.services.reporting_service import period_for,render_pdf,deliver_report


def test_report_periods_are_deterministic():
    day=date(2026,8,31)
    assert period_for("DAILY_HR",day)==(day,day)
    assert period_for("WEEKLY_RECRUITMENT",day)==(date(2026,8,25),day)
    assert period_for("MONTHLY_WORKFORCE",day)==(date(2026,8,1),day)


def test_pdf_is_valid_and_contains_pages():
    data={"title":"Daily HR Report","period":{"start":"2026-08-31","end":"2026-08-31"},"sections":[{"title":"Attendance","metrics":{"Present":10,"Absent":2}}]}
    pdf=render_pdf(data)
    assert pdf.startswith(b"%PDF")
    assert len(pdf)>500


@patch("app.services.reporting_service.send_document",return_value="wamid-1")
@patch("app.services.reporting_service.send_email_sync",return_value=True)
def test_shared_delivery_pipeline_supports_email_and_whatsapp(email,whatsapp):
    run={"download_token":"token","report_type":"DAILY_HR"}
    result=deliver_report(run,[{"channel":"EMAIL","recipient":"owner@example.com"},{"channel":"WHATSAPP","recipient":"+919999999999"}])
    assert [x["status"] for x in result]==["SENT","SENT"]
    email.assert_called_once();whatsapp.assert_called_once()


@patch("app.services.reporting_service.send_email_sync",return_value=False)
def test_delivery_failure_is_explicit(email):
    result=deliver_report({"download_token":"token","report_type":"PAYROLL"},[{"channel":"EMAIL","recipient":"owner@example.com"}])
    assert result[0]["status"]=="FAILED"
