# Automated backend results — 5 September 2026

Executed with Python 3.12 and `backend/requirements-audit.txt`. These are local tests using mocked database/provider dependencies; passing does not establish deployed database, RLS or provider readiness.

| Test module | Passed | Failed | Skipped |
|---|---:|---:|---:|
| test_accommodation_transport | 5 | 0 | 0 |
| test_ai_screening_governance | 8 | 0 | 0 |
| test_attendance | 11 | 0 | 0 |
| test_candidate_application_flow | 4 | 0 | 0 |
| test_candidate_ats | 13 | 0 | 0 |
| test_career_command | 82 | 0 | 0 |
| test_certification_management | 10 | 0 | 0 |
| test_command_parser | 169 | 0 | 0 |
| test_complaint_command | 55 | 15 | 0 |
| test_data_localization | 59 | 0 | 0 |
| test_diversity | 47 | 0 | 0 |
| test_dpdp | 39 | 0 | 0 |
| test_employee_360 | 5 | 0 | 0 |
| test_employee_engagement | 5 | 0 | 0 |
| test_employee_exit | 4 | 0 | 0 |
| test_employee_retention | 3 | 0 | 0 |
| test_employee_self_service | 6 | 0 | 0 |
| test_executive_dashboard | 3 | 0 | 0 |
| test_fssai_upload | 26 | 0 | 0 |
| test_global_search | 7 | 0 | 0 |
| test_grievance_management | 5 | 0 | 0 |
| test_hospitality_ai_assistant | 12 | 0 | 0 |
| test_hotel_management | 12 | 0 | 0 |
| test_hr_bot | 66 | 6 | 0 |
| test_india_compliance_hardening | 9 | 0 | 0 |
| test_job_distribution | 5 | 0 | 0 |
| test_job_management | 8 | 0 | 0 |
| test_kyc | 36 | 0 | 0 |
| test_labour_compliance | 59 | 0 | 0 |
| test_leave_command | 33 | 30 | 0 |
| test_leave_management | 8 | 0 | 0 |
| test_onboarding_orchestration | 5 | 0 | 0 |
| test_payroll_service | 8 | 0 | 0 |
| test_payslip_command | 66 | 0 | 1 |
| test_performance_management | 12 | 0 | 0 |
| test_razorpay_payout | 45 | 0 | 0 |
| test_rbac | 14 | 0 | 0 |
| test_recruitment_analytics | 3 | 0 | 0 |
| test_referral_create | 19 | 0 | 0 |
| test_referral_lifecycle | 5 | 0 | 0 |
| test_reporting_service | 4 | 0 | 0 |
| test_salary_advance_service | 5 | 0 | 0 |
| test_security_audit | 8 | 0 | 0 |
| test_shift_command | 68 | 0 | 0 |
| test_training_career | 3 | 0 | 0 |
| test_upi | 36 | 0 | 0 |
| test_whatsapp_message_audit | 2 | 0 | 0 |
| test_whatsapp_sharing | 32 | 0 | 0 |
| test_whatsapp_webhook | 45 | 3 | 0 |
| test_workforce_analytics | 4 | 0 | 0 |
| test_workforce_scheduling | 12 | 0 | 0 |

## Failures retained for follow-up

- `tests.test_complaint_command.TestIdentityHiding::test_named_complaint_dual_write_to_employee_complaints` — assert 0 == 1
- `tests.test_complaint_command.TestIdentityAccess::test_privileged_roles_allowed[hr_admin]` — fastapi.exceptions.HTTPException: 410: Use GET /api/v1/grievances/cases/{complaint_id}/identity with a purpose. The legacy identity endpoint is retired.
- `tests.test_complaint_command.TestIdentityAccess::test_privileged_roles_allowed[super_admin]` — fastapi.exceptions.HTTPException: 410: Use GET /api/v1/grievances/cases/{complaint_id}/identity with a purpose. The legacy identity endpoint is retired.
- `tests.test_complaint_command.TestIdentityAccess::test_privileged_roles_allowed[admin]` — fastapi.exceptions.HTTPException: 410: Use GET /api/v1/grievances/cases/{complaint_id}/identity with a purpose. The legacy identity endpoint is retired.
- `tests.test_complaint_command.TestIdentityAccess::test_non_privileged_roles_blocked[manager]` — AssertionError: assert 410 == 403
- `tests.test_complaint_command.TestIdentityAccess::test_non_privileged_roles_blocked[recruiter]` — AssertionError: assert 410 == 403
- `tests.test_complaint_command.TestIdentityAccess::test_non_privileged_roles_blocked[employee]` — AssertionError: assert 410 == 403
- `tests.test_complaint_command.TestIdentityAccess::test_non_privileged_roles_blocked[hiring_manager]` — AssertionError: assert 410 == 403
- `tests.test_complaint_command.TestIdentityAccess::test_403_message_contains_required_roles` — AssertionError: assert ('admin' in 'use get /api/v1/grievances/cases/{complaint_id}/identity with a purpose. the legacy identity endpoint is retired.' or 'hr' in 'use get /api/v1/grievances/cases/{complaint_id}/identity with a purpose. the legacy identity endpoint is retired.')
- `tests.test_complaint_command.TestIdentityAccess::test_complaint_not_found_returns_404` — AssertionError: assert 410 == 404
- `tests.test_complaint_command.TestIdentityAccess::test_response_contains_identity_fields` — fastapi.exceptions.HTTPException: 410: Use GET /api/v1/grievances/cases/{complaint_id}/identity with a purpose. The legacy identity endpoint is retired.
- `tests.test_complaint_command.TestIdentityAccess::test_purpose_recorded_in_result` — fastapi.exceptions.HTTPException: 410: Use GET /api/v1/grievances/cases/{complaint_id}/identity with a purpose. The legacy identity endpoint is retired.
- `tests.test_complaint_command.TestIdentityAccess::test_audit_log_written_on_access` — fastapi.exceptions.HTTPException: 410: Use GET /api/v1/grievances/cases/{complaint_id}/identity with a purpose. The legacy identity endpoint is retired.
- `tests.test_complaint_command.TestIdentityAccess::test_audit_log_contains_viewer_info` — fastapi.exceptions.HTTPException: 410: Use GET /api/v1/grievances/cases/{complaint_id}/identity with a purpose. The legacy identity endpoint is retired.
- `tests.test_complaint_command.TestIdentityAccess::test_audit_failure_does_not_block_response` — fastapi.exceptions.HTTPException: 410: Use GET /api/v1/grievances/cases/{complaint_id}/identity with a purpose. The legacy identity endpoint is retired.
- `tests.test_hr_bot.TestLeaveHandler::test_leave_sick_type_inferred` — AssertionError: assert ('SICK' in '🤖 HospBot\n❌ Selected dates contain no working leave days' or 'sick' in '🤖 hospbot\n❌ selected dates contain no working leave days')
- `tests.test_hr_bot.TestHRBotEndpoints::test_list_leave_requests` — assert 403 == 200
- `tests.test_hr_bot.TestHRBotEndpoints::test_approve_leave` — assert 403 == 200
- `tests.test_hr_bot.TestHRBotEndpoints::test_approve_already_approved_409` — assert 403 == 409
- `tests.test_hr_bot.TestHRBotEndpoints::test_reject_leave` — assert 403 == 200
- `tests.test_hr_bot.TestHRBotEndpoints::test_resolve_complaint` — assert 410 == 200
- `tests.test_leave_command.TestDateValidation::test_iso_date_accepted` — AssertionError: assert ('✅' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or 'submitted' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestDateValidation::test_dmy_slash_accepted` — AssertionError: assert ('✅' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or 'submitted' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestDateValidation::test_dmy_dash_accepted` — AssertionError: assert ('✅' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or 'submitted' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestDateValidation::test_natural_two_token_date` — AssertionError: assert ('✅' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or 'submitted' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestDateValidation::test_ordinal_date` — AssertionError: assert ('✅' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or 'submitted' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestDateValidation::test_relative_today` — AssertionError: assert ('✅' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or 'submitted' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestDateValidation::test_relative_tomorrow` — AssertionError: assert ('✅' in '🤖 HospBot\n❌ Selected dates contain no working leave days' or 'submitted' in '🤖 hospbot\n❌ selected dates contain no working leave days')
- `tests.test_leave_command.TestDateValidation::test_relative_kal` — AssertionError: assert ('✅' in '🤖 HospBot\n❌ Selected dates contain no working leave days' or 'submitted' in '🤖 hospbot\n❌ selected dates contain no working leave days')
- `tests.test_leave_command.TestDateValidation::test_hindi_aaj` — AssertionError: assert ('✅' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or 'submitted' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestLeaveBalanceCheck::test_sufficient_balance_allowed` — AssertionError: assert ('✅' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or 'submitted' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestLeaveBalanceCheck::test_exhausted_casual_blocked` — AssertionError: assert ('0' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or 'no' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.' or 'remaining' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestLeaveBalanceCheck::test_exhausted_balance_reply_shows_other_types` — AssertionError: assert ('sick' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.' or '12' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.')
- `tests.test_leave_command.TestLeaveBalanceCheck::test_remaining_balance_shown_in_confirmation` — AssertionError: assert ('remaining' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.' or 'day' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestLeaveRequestCreation::test_ticket_number_in_reply` — AssertionError: assert None
- `tests.test_leave_command.TestLeaveRequestCreation::test_status_pending_in_reply` — AssertionError: assert 'pending' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.'
- `tests.test_leave_command.TestLeaveRequestCreation::test_date_shown_in_reply` — AssertionError: assert ('Jun' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or '2026-06-10' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or '10' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.')
- `tests.test_leave_command.TestLeaveRequestCreation::test_sla_deadline_3_days` — AssertionError: assert ('3' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.')
- `tests.test_leave_command.TestDuplicateGuard::test_duplicate_pending_blocked` — AssertionError: assert ('already' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.' or 'existing' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestDuplicateGuard::test_duplicate_approved_blocked` — AssertionError: assert 'already' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.'
- `tests.test_leave_command.TestDuplicateGuard::test_no_duplicate_proceeds` — AssertionError: assert ('✅' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or 'submitted' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestManagerNotification::test_manager_notified_on_new_request` — AssertionError: assert False
- `tests.test_leave_command.TestManagerNotification::test_manager_message_contains_ticket` — assert 0 >= 1
- `tests.test_leave_command.TestManagerNotification::test_manager_message_contains_date_type_reason` — assert 0 >= 1
- `tests.test_leave_command.TestManagerNotification::test_multiple_managers_each_notified` — AssertionError: assert '+919000000001' in []
- `tests.test_leave_command.TestManagerNotification::test_no_managers_does_not_crash` — AssertionError: assert ('✅' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.' or 'submitted' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.')
- `tests.test_leave_command.TestManagerNotification::test_manager_without_phone_skipped` — AssertionError: assert '+919000000001' in []
- `tests.test_leave_command.TestWhatsAppReply::test_reply_contains_employee_name` — AssertionError: assert 'Priya' in '🤖 HospBot\n❌ Failed to submit leave. Please contact HR.'
- `tests.test_leave_command.TestWhatsAppReply::test_reply_contains_ticket` — AssertionError: assert None
- `tests.test_leave_command.TestWhatsAppReply::test_reply_contains_hindi` — assert 0 > 0
- `tests.test_leave_command.TestWhatsAppReply::test_reply_pending_status` — AssertionError: assert 'pending' in '🤖 hospbot\n❌ failed to submit leave. please contact hr.'
- `tests.test_whatsapp_webhook.TestMetaParser::test_image_message` — AssertionError: assert 'image/jpeg' == 'image'
- `tests.test_whatsapp_webhook.TestWhatsAppGatewaySend::test_twilio_send_success` — AttributeError: <module 'app.services.whatsapp_gateway' from 'C:\\Users\\tapaw\\repos\\Hospitality-Recruit\\backend\\app\\services\\whatsapp_gateway.py'> does not have the attribute 'Client'
- `tests.test_whatsapp_webhook.TestProcessMessage::test_text_message_dispatches_to_hr_bot` — ValueError: Invalid isoformat string: "<MagicMock name='mock.table().select().eq().in_().order().limit().execute().data.__getitem__().__getitem__()' id='1865674392688'>"
