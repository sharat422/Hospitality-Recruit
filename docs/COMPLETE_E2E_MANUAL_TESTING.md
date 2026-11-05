# Hospitality Recruit: Complete End-to-End Manual Testing

**Date:** 2026-09-01  
**Companion audit:** [COMPLETE_PRODUCT_CAPABILITY_AUDIT.md](COMPLETE_PRODUCT_CAPABILITY_AUDIT.md)

## 0. Mandatory Test Gate

Do not begin feature acceptance until all gate checks pass.

1. Create a fresh backend virtual environment and install `backend/requirements.txt`.
2. Create a disposable Supabase/PostgreSQL project.
3. Apply the finalized migration ledger from zero; save the migration output.
4. Run `pytest -q`; record passed, failed and skipped counts.
5. Run `npm ci` and `npm run build` in `frontend`; require zero TypeScript/Vite errors.
6. Start backend and frontend; confirm `/health`, `/docs`, `/auth` and `/dashboard` load.
7. Confirm `/health.localization_ok` is true in production-like configuration.
8. Create two organizations, two properties in organization A, and one property in organization B.
9. Create one user for every RBAC role and one employee/candidate self-service identity.
10. Seed distinguishable records in every property so accidental cross-tenant results are obvious.

**Current checkout:** steps 4 and 5 cannot pass yet. The backend venv references a removed Python executable; the frontend has syntax errors documented in the audit.

## 1. Security Matrix Used for Every Feature

For each authenticated endpoint and screen:

1. Call without a token; expect 401 except documented public token/webhook routes.
2. Call with an expired/invalid token; expect 401.
3. Call as Candidate and Employee; verify self-only records.
4. Call as Recruiter/Department Head; verify permission and department/property scope.
5. Call as HR Manager/GM; verify only assigned properties.
6. Call as Group Admin/Owner; verify intended group scope.
7. Replace a URL/body UUID with another property’s record; expect 403 or 404, never data.
8. Repeat direct Supabase queries using anon and user JWTs; verify RLS matches API behavior.
9. Verify denied access is audited for sensitive payroll, complaints, KYC and documents.
10. Inspect API responses and browser network logs for secrets, full Aadhaar/PAN, signed URLs with excessive lifetime, or unauthorized PII.

## 2. Feature Tests

### 1. Hotel & Multi-Property

1. Create group, two properties, departments, headcount, branding and HR/payroll/compliance settings.
2. Switch active property; verify dashboard, employees, jobs and analytics refresh.
3. Open a copied URL from property A after switching to B; verify denial.
4. Verify Owner sees group totals and Property Manager sees only assigned property.

### 2. RBAC

1. Sign in as each required role and record visible navigation/actions.
2. Invoke the same protected APIs directly; UI and API decisions must match.
3. Attempt vertical escalation by changing role/property/department IDs in requests.
4. Attempt horizontal access to peer employee/candidate/payroll records.

### 3. Job Management

1. Create a job with property, department, role, manager, CTC, requirements and benefits.
2. Generate English/Hindi JD; edit, submit for approval, approve, publish, close, reopen and duplicate.
3. Verify invalid salary/openings/date combinations are rejected.
4. Verify applications link to the canonical job and property.

### 4. Job Distribution

1. Publish to website, WhatsApp, referral, QR and walk-in channels.
2. Export CSV for every unsupported board; verify content/INR/expiry fields.
3. Open tracked URL, submit application, move to hire; verify click/application/hire attribution.
4. Unpublish and expire posts; verify links/status/analytics.

### 5. Candidate ATS

1. Create candidate with resume, skills, languages, salary, notice, availability, tags and documents.
2. Submit application and move through Applied → Screened → Shortlisted → Interview → Selected → Offer → Offer Accepted → Onboarding → Hired.
3. Test search, filters, Kanban, notes, bulk actions, interview feedback and timeline.
4. Submit same email/phone for same job; verify duplicate detection and controlled merge.

### 6. AI Screening

1. Test realistic waiter, housekeeper, chef, front-office and cross-industry resumes.
2. Verify deterministic skill/language/location/salary/availability/experience scores and total math.
3. Disable Claude; verify fallback is labeled and no fabricated AI explanation appears.
4. Override recommendation; verify reason/audit. Confirm AI cannot auto-reject or irreversibly hire.
5. Enable blind screening and verify identity/photo/hometown are hidden.

### 7. Candidate Mobile Application

1. At 360px, start Tier 1 application by OTP and complete essential fields in approximately 60 seconds.
2. Test Hindi/English, resume/document upload, draft resume and status link.
3. Apply via WhatsApp and QR; verify source/referral attribution.
4. Repeat with browser throttled to Slow 3G and intermittent offline; verify recoverable progress and no duplicate submission.

### 8–9. Referral and UPI Payout

1. Create program/campaign, collect and verify employee UPI, create link and share by WhatsApp.
2. Apply as referred candidate; verify referral → application → hire linkage.
3. Try same employee/job/candidate and a competing referrer; verify duplicate prevention.
4. Advance hired date past 90 days; run eligibility and manual payout.
5. Replay payout request/job/webhook; verify one payout only.
6. Test pending, failed, reversed and successful Razorpay responses; verify payroll reference and INR totals.
7. Verify mock mode cannot mark production data paid.

### 10. WhatsApp HR Bot

1. Complete provider webhook verification/signature tests and send inbound messages from a mapped employee phone.
2. Test LEAVE, PAYSLIP, SHIFT, BALANCE, COMPLAINT, CAREER and HELP in English, lowercase and Hindi aliases.
3. Verify inbound/outbound message records and provider IDs.
4. Request another employee’s payslip; expect denial.
5. Submit anonymous complaint; verify managers cannot identify reporter and confidential access is audited.
6. Verify web/PWA/WhatsApp leave produces the same canonical leave record and rules.

### 11–12. Onboarding and Appointment Letters

1. Accept offer; verify onboarding auto-starts from property/department/role template.
2. Complete documents, KYC, PF/ESIC, payroll setup, manager/joining and checklist tasks.
3. Generate appointment letter, verify template values, PDF, eSign callback and immutable signed URL.
4. Test reminders, completion percentage and ghosting risk.

### 13–18. India Compliance, Certifications, Labour, Statutory, DPDP and Localization

1. Run Aadhaar OTP and verify only last four digits are stored; run PAN and verify masked value only.
2. Connect DigiLocker and inspect audit records; confirm sandbox is visibly labeled.
3. Upload each certificate type; verify secure ap-south-1 URL, role requirement, verification and renewal.
4. Test expiry at 90/60/30/7/expired and verify idempotent alerts.
5. Check wages for multiple states/skills/effective dates; test below/equal/above minimum.
6. Test 8h/day, 48h/week, 12h rest and overtime violations.
7. Validate EPF/ESIC/PT examples against approved statutory fixtures.
8. Record each DPDP purpose separately; withdraw optional consent; request access/erasure.
9. Apply legal hold and retention rule; verify erasure anonymizes only eligible data and preserves required records.
10. Set S3 region outside India in production-like config; startup/deployment must fail.
11. Attempt sending Aadhaar/PAN to a non-India service; expect hard denial and audit.

### 19. Employee 360

1. Open every profile tab and reconcile values to authoritative tables.
2. Update permitted personal fields and verify lifecycle event.
3. As employee, attempt another employee UUID and sensitive financial/statutory fields; expect denial/masking.

### 20. Attendance

1. Test normal day, valid GPS/geofence punch, late arrival, early departure and overtime.
2. Test outside geofence, missing punch and double punch.
3. Submit correction; approve/reject as manager and verify audit before payroll validation.
4. Test biometric adapter contract and unavailable-provider response.

### 21. Shift Management

1. Create templates and weekly/monthly rosters; drag/drop assignments.
2. Attempt overlap, insufficient rest, excessive weekly hours, leave conflict and unavailable employee.
3. Publish schedule; verify WhatsApp and attendance linkage.
4. Request/approve/reject swap and verify both employees’ schedules.

### 22. Leave Management

1. Configure types, balances, holidays and approval chain.
2. Submit equivalent leave through web, PWA and WhatsApp; verify one shared schema/service.
3. Test insufficient balance, overlap, holiday/week-off, manager and HR decisions.
4. Verify calendars/history/balances and notifications update once.

### 23. Indian Payroll

1. Configure effective-dated CTC, Basic, HRA, allowances, PT/TDS/EPF/ESIC rules.
2. Calculate known examples: full month, mid-month join, LOP, overtime, bonus/incentive/arrear and salary advance.
3. Reconcile gross, deductions and net; approve and lock immutable snapshot.
4. Generate payslip PDF, ECR/ESIC/PT/Form 16 outputs and verify employee self-only access.
5. Attempt recalculation after approval; require reversal/version workflow, never silent mutation.

### 24–25. Performance, Training and Career

1. Configure department/role KPI templates; run self, peer and manager reviews.
2. Record guest feedback; verify scores and advisory increment/promotion outcome.
3. Identify skill gap, assign course, play video, complete quiz and issue certificate.
4. Verify career pathway/readiness/internal job; require separate approval for promotion/pay change.

### 26–27. Retention and Engagement

1. Seed absence, lateness, pay/promotion, training and pulse data; recalculate transparent risk.
2. Verify score, level, factors and actions without claiming statistical prediction.
3. Send PWA/WhatsApp pulse survey; submit anonymous and identified responses.
4. Verify small cohorts are suppressed in APIs/UI/exports and trends compare authorized departments/properties.
5. Test recognition and Employee of Month workflow.

### 28. Exit & Alumni

1. Submit resignation; calculate notice and approvals.
2. Complete exit interview, clearance, settlement and experience/relieving letter.
3. Verify rehire eligibility and alumni record.
4. Confirm lifecycle links recruitment → hire → onboarding → employment → promotion/transfer → exit → alumni.

### 29. Employee PWA

1. OTP-login on low-cost Android/360px and verify own shift, leave, balance, payslip, EPF/ESIC, grievance and facilities.
2. Test poor/offline network, retry and duplicate-action prevention.
3. Verify PWA and bot call the same domain services and return consistent balances/status.

### 30. Grievance/POSH

1. Submit named, anonymous, confidential and POSH complaints with evidence.
2. Verify reference, investigation, assignment, escalation and resolution.
3. Confirm normal managers cannot list/open confidential complaints.
4. Verify every sensitive read/change is audited and audit failure denies access.

### 31. Salary Advance

1. Configure eligibility; submit valid/invalid requests.
2. Approve/reject/disburse as authorized roles; employee must not change amount/balance/status.
3. Run payroll deduction and verify installment/outstanding balance/audit/WhatsApp.

### 32–33. Accommodation and Transport

1. Create building/room/bed; allocate, check in/out and log maintenance.
2. Prevent double allocation and cross-property assignment.
3. Create route/stops/vehicle/driver/schedule; assign employees and enforce capacity/property.
4. Verify Employee 360/PWA links and changes after transfer/exit.

### 34–36. Analytics and Owner Dashboard

1. Seed known application, attendance, payroll, referral, engagement and exit fixtures.
2. Recalculate every KPI manually and reconcile source rows.
3. Test property/department/job/recruiter/source/date filters and Group → Property → Department → Role → Employee drilldown.
4. Verify Owner group scope and Property Manager isolation.
5. Confirm no placeholder cost or mock values appear as real metrics.

### 37. Automated Reports

1. Generate daily HR, recruitment, workforce, payroll, compliance, attrition, source and property reports.
2. Verify PDF/CSV values match screens and authoritative data.
3. Schedule email and WhatsApp delivery; run worker twice and verify idempotency.
4. Test failed provider, retry, delivery log and unauthorized download URL.

### 38. Notification Engine

1. Trigger messages from recruitment, shift, leave, payroll, onboarding, referral, compliance and reports.
2. Verify template/language, consent/preference, provider ID, delivery transitions and audit.
3. Simulate timeout/429/5xx; verify bounded retry, idempotency and dead-letter/manual retry.
4. Ensure the same business event never sends duplicate messages.

### 39. Unified Search

1. Search exact/fuzzy names, phone, job, application, referral, document, property, department and complaint.
2. Test category filters, autocomplete and recent searches.
3. Repeat as every role; verify no unauthorized result title, snippet, count or URL leaks.
4. Test large data volume and response latency.

### 40. Hospitality AI Assistant

1. Ask each supported business question using fixtures with known answers.
2. Reconcile answer, metric values, date/property filters and cited sources.
3. Repeat as restricted property manager and employee; verify no unauthorized payroll/employee data.
4. Ask destructive commands; require refusal or explicit confirmation with no mutation.
5. Disable Claude; verify graceful error, not fabricated results.
6. Verify business calculations come from backend tools and cross-border consent/logging is enforced.

## 3. Regression Exit Criteria

Release only when:

1. Fresh migration replay succeeds with no duplicate-version ambiguity.
2. No unintended permissive RLS policies remain.
3. Backend, frontend build and E2E suites pass in CI.
4. Cross-tenant, cross-property, cross-department and self-only tests pass.
5. Production mode refuses sandbox KYC/storage/payout results.
6. Webhook signatures, idempotency and replay protection pass.
7. All financial/statutory values reconcile to approved examples.
8. Notification and scheduled-job retries are observable and idempotent.
9. 360px/Slow 3G/Hindi testing passes.
10. Audit logs cover sensitive reads and writes without storing unmasked secrets or identity numbers.
