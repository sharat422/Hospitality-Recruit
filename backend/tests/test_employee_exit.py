from app.services.employee_exit_service import calculate_final_settlement, clearance_summary, experience_letter_html

def test_final_settlement_known_example():
    result=calculate_final_settlement({"monthly_gross_inr":30000,"payable_days":15,"leave_encashment_inr":5000,"gratuity_inr":10000,"bonus_inr":2000,"reimbursements_inr":1000,"notice_recovery_inr":3000,"loan_recovery_inr":1000,"tax_inr":500})
    assert result["gross_payable_inr"]==33000
    assert result["total_deductions_inr"]==4500
    assert result["net_payable_inr"]==28500
    assert len(result["snapshot_hash"])==64

def test_settlement_is_deterministic():
    data={"monthly_gross_inr":24000,"payable_days":30,"leave_encashment_inr":1200}
    assert calculate_final_settlement(data)["snapshot_hash"]==calculate_final_settlement(data)["snapshot_hash"]

def test_clearance_requires_every_item():
    blocked=clearance_summary([{"status":"CLEARED","amount_due_inr":0},{"status":"PENDING","amount_due_inr":250}])
    assert blocked=={"total":2,"cleared":1,"blocked":1,"ready":False,"amount_due_inr":250.0}
    ready=clearance_summary([{"status":"CLEARED"},{"status":"NOT_APPLICABLE"}])
    assert ready["ready"] is True

def test_experience_letter_escapes_untrusted_content():
    html=experience_letter_html({"full_name":"<script>x</script>","job_title":"Chef","joining_date":"2024-01-01"},{"approved_last_working_date":"2026-08-31"},"Hotel & Spa")
    assert "<script>" not in html and "&lt;script&gt;" in html and "Hotel &amp; Spa" in html
