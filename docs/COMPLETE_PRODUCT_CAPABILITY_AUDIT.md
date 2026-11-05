# Hospitality Recruit: Complete Product Capability Audit

**Audit date:** 2026-09-01  
**Scope:** Repository evidence only. No product code or database was changed.  
**Method:** Each capability was traced through UI, API registration, service/business logic, migrations/RLS, authorization, integrations, notifications/audit, and tests.

## Classification Rules

- **COMPLETE**: verified end to end with production dependencies and passing tests.
- **PARTIAL**: meaningful layers exist, but one or more end-to-end links, production integrations, security controls, or runtime verification are missing.
- **UI ONLY / BACKEND ONLY / DATABASE ONLY**: only the named layer is materially present.
- **MOCK**: the primary flow returns simulated results or depends on sandbox data.
- **BROKEN**: intended flow cannot currently run.
- **MISSING**: no meaningful implementation was found.

## Executive Result

No capability can be classified **COMPLETE** in the current checkout. The repository contains substantial implementations for all 40 mapped areas, but the frontend does not compile, the checked-in backend virtual environment cannot execute, migrations are not proven applied to the target Supabase project, and several production integrations fall back to mocks.

| Result | Count |
|---|---:|
| PARTIAL | 39 |
| BROKEN | 1 |
| COMPLETE / UI ONLY / BACKEND ONLY / DATABASE ONLY / MOCK / MISSING | 0 |

The single **BROKEN** classification is Shift Management because the repository-level frontend build is blocked first by malformed `SchedulerDashboard.tsx`; the newer workforce scheduler implementation is substantial but cannot be shipped from this checkout until the build is repaired.

## Runtime Verification

- `npm run build` in `frontend`: **FAILED**. Primary syntax failures are in `src/components/SchedulerDashboard.tsx`, `src/lib/queryConfig.ts`, `src/pages/BillingDashboard.tsx`, and `src/pages/PricingPage.tsx`.
- `backend/venv/Scripts/python.exe -m pytest -q`: **NOT RUN**. The virtual environment points to a removed Python 3.11 executable.
- Supabase migrations: **NOT APPLIED OR VERIFIED** during this audit. Repository SQL does not prove the deployed database state.
- Historical feature documents report passing tests in earlier environments; those results are not treated as current verification.

## Capability Matrix

### 1. Hotel & Multi-Property — PARTIAL

- **Evidence:** `HotelManagement.tsx`; `/api/v1/hotels`; `hotel_management_service.py`; migrations `028_hotel_multi_property.sql`, `029_rbac.sql`; hotel tests.
- **Implemented:** groups, properties, departments, headcount/settings/branding, active-property context, portfolio data, property access checks.
- **Missing/risk:** current UI cannot build; deployed migrations and switch behavior are unverified; old `properties` schema from `004_seasonal.sql` used permissive RLS before later hardening.
- **Recommendation:** establish one canonical property model, apply ordered migrations to a disposable DB, then run cross-property isolation tests.

### 2. RBAC — PARTIAL

- **Evidence:** `ProtectedRoute.tsx`, `RBACContext.tsx`; `/api/v1/rbac`; `rbac_service.py`; migration `029_rbac.sql`; RBAC tests.
- **Implemented:** Owner, Group Admin/HR, GM, HR Manager, Department Head, Recruiter, Employee, Candidate; permission matrix; property and department scope helpers; frontend route gates.
- **Missing/risk:** not every legacy router uses canonical authorization; frontend hiding is inconsistent on referral routes; permissive legacy RLS policies remain in migration history; no current privilege-escalation test run.
- **Recommendation:** make canonical authorization mandatory at router boundaries and replace every permissive policy by final-state tenant policies.

### 3. Job Management — PARTIAL

- **Evidence:** `SmartRecruitment.tsx`; `/api/v1/recruit`; `smart_recruitment_service.py`; migration `030_job_management_completion.sql`; job tests.
- **Implemented:** lifecycle, approval, duplication, hotel/department/role relations, India salary/CTC, requirements, benefits, vacancies, urgency, manager, English/Hindi JD generation.
- **Missing/risk:** both `jobs` and `job_roles` are active concepts; AI JD also exists under matching/screening routes; board content depends on AI/provider availability.
- **Recommendation:** declare `jobs` canonical and provide a compatibility view/migration for `job_roles` consumers.

### 4. Multi-Channel Job Distribution — PARTIAL

- **Evidence:** `/api/v1/distribution`; `job_distribution_service.py`; migration `031_job_distribution.sql`; distribution tests.
- **Implemented:** website, WhatsApp, referrals, QR, walk-in, tracking links, attribution, publish/unpublish, status, expiry, analytics, CSV export.
- **Integration truth:** Naukri, Apna, WorkIndia, Shine, Indeed, LinkedIn and hospitality boards are **manual CSV exports**, not APIs.
- **Missing/risk:** no native external-board adapters or status callbacks.

### 5. Candidate ATS — PARTIAL

- **Evidence:** `CandidatePipeline.tsx`, `SmartRecruitment.tsx`; `/api/v1/ats` and `/api/v1/recruit`; candidate ATS services; migration `032_candidate_ats_completion.sql`; tests.
- **Implemented:** profile, applications, notes/tags/documents, search/filters, pipeline, bulk actions, duplicate detection/merge, interview scheduling/feedback, timeline.
- **Missing/risk:** duplicate ATS implementation in unregistered `routers/ats.py`; dual `applications.job_id`/`job_role_id`; pipeline stage vocabularies differ across legacy and new modules.

### 6. AI Candidate Screening — PARTIAL

- **Evidence:** `CandidateScreening.tsx`, `MatchingDashboard.tsx`; `/api/v1/ai-screening`, `/api/v1/matching`; `candidate_screening_service.py`, `ai_matching_service.py`; migrations `007_ai_matching.sql`, `033_ai_screening_governance.sql`; tests.
- **Implemented:** resume parsing, deterministic component scoring, configurable weights, explanation, recruiter override, blind view, recommendation audit; no irreversible automatic decision in governed flow.
- **Missing/risk:** overlapping legacy scoring paths; Claude fallback can mask outages; not every AI call demonstrably passes through DPDP cross-border consent guard.

### 7. Candidate Mobile Application — PARTIAL

- **Evidence:** `IndiaApplyForm.tsx`, `MobileApplicationForm.tsx`, status/QR/video pages; `/api/v1/mobile`, recruitment apply routes; mobile services; migrations `004_mobile_experience.sql`, `007_india_mobile.sql`, `034_candidate_application_completion.sql`; tests.
- **Implemented:** tiered fields, OTP, resume/doc upload paths, Hindi/English, WhatsApp/QR attribution, draft/status flows, low-bandwidth-oriented UI.
- **Missing/risk:** MSG91/Naukri/translation/video storage may be sandbox or stub; 360px/slow-network test not currently executable; early mobile tables have open RLS policies.

### 8. Employee Referral Engine — PARTIAL

- **Evidence:** `ReferralPortal.tsx`, `IndiaReferralProgram.tsx`, admin dashboard; `/api/v1/india-referrals`, `/api/v1/admin-referrals`, legacy `/api/v1/referrals`; referral services; migrations `006_referrals.sql`, `008_india_referrals.sql`, `042_referral_lifecycle_completion.sql`; tests.
- **Implemented:** programs, links/codes, candidate/application linking, duplicate checks, WhatsApp sharing, campaigns, leaderboard, badges, status lifecycle.
- **Missing/risk:** three overlapping referral surfaces/APIs; old tables/policies are permissive; canonical referral identifier and candidate/job relationship are not consistently used.

### 9. Referral UPI Payouts — PARTIAL

- **Evidence:** UPI routes in India referrals/employees; `razorpay_payout_service.py`; payroll adapters; referral lifecycle migration; payout/UPI tests.
- **Implemented:** regex/VPA validation, employee/admin access intent, INR-to-paise, 90-day eligibility, idempotency header, payout IDs/statuses, payroll reference.
- **Missing/risk:** missing credentials produce a deterministic mock that reports `PAID`; no verified daily Bull worker in the Python deployment; webhook authenticity and reconciliation require production validation.

### 10. WhatsApp HR Bot — PARTIAL

- **Evidence:** `WhatsAppBotDashboard.tsx`; `/api/whatsapp` and `/api/v1/hr-bot`; `whatsapp_gateway.py`, `hr_bot_service.py`; migrations `021_hr_bot_tables.sql` plus later shared-domain migrations; command/webhook tests.
- **Implemented:** LEAVE, PAYSLIP, SHIFT, BALANCE, COMPLAINT, CAREER, HELP; English/simple Hindi parsing; phone resolution; inbound/outbound storage; manager notifications; anonymous complaint support.
- **Missing/risk:** two webhook/router surfaces; some business logic remains in `hr_bot_service` instead of fully shared domain services; real Meta/Interakt credentials and signatures not end-to-end verified.

### 11. Digital Onboarding — PARTIAL

- **Evidence:** `IndiaOnboarding.tsx`; `/api/v1/india-onboarding` and legacy `/api/v1/onboarding`; onboarding service; migrations `013_india_onboarding.sql`, `040_onboarding_orchestration.sql`; tests.
- **Implemented:** offer acceptance trigger, templates by property/department/role, documents/KYC/PF/ESIC/payroll/manager/joining/checklists, completion and ghosting risk, reminders.
- **Missing/risk:** duplicate legacy flow; provider eSign may fall back to demo.

### 12. Indian Appointment Letters — PARTIAL

- **Evidence:** India onboarding letter/template endpoints and PDF/eSign service; onboarding migrations/tests.
- **Implemented:** template rendering, appointment-letter records, PDF path, sign workflow.
- **Missing/risk:** SignDesk is a stub; Leegality/Digio require credentials; legal template review and immutable signed artifact verification are outstanding.

### 13. India Compliance/KYC — PARTIAL

- **Evidence:** `KYCManager.tsx`, `IndiaComplianceCenter.tsx`; `/api/v1/kyc`, `/api/v1/india-compliance`; KYC/India compliance services; migrations `014_india_compliance.sql`, `043_india_compliance_hardening.sql`; tests.
- **Implemented:** Aadhaar OTP last-four storage, masked PAN, DigiLocker flow, audit records, expiry tracking.
- **Missing/risk:** Surepass and DigiLocker automatically run in sandbox without credentials; Western `/api/v1/compliance` remains registered.

### 14. FSSAI/Certification Management — PARTIAL

- **Evidence:** `CertificationManager.tsx`, KYC FSSAI panel; `/api/v1/fssai`, `/api/v1/certifications`; certification/FSSAI services and workers; migrations `015_fssai_certifications.sql`, `045_certification_management.sql`; tests/docs.
- **Implemented:** role requirements, uploads, verification, expiry/renewal, 90/60/30/7/expired intervals, notifications and Employee 360 links.
- **Missing/risk:** S3 returns fake sandbox URLs without configuration; worker execution/scheduler not currently verified.

### 15. Labour Compliance — PARTIAL

- **Evidence:** India compliance UI; `/api/v1/labour` and overlapping India-compliance routes; `labour_compliance_service.py`; migrations/seeds; tests.
- **Implemented:** state wage lookup, salary checks, daily/weekly/rest/overtime checks and audit.
- **Missing/risk:** duplicate endpoints/rule implementations; statutory rates are seeded snapshots and need effective-date governance and legal ownership.

### 16. EPF/ESIC/PT — PARTIAL

- **Evidence:** India compliance/payroll UI and APIs; labour/payroll services; migrations `014`, `039`; tests.
- **Implemented:** EPF/ESIC calculation and PT slab data, payroll integration and exports.
- **Missing/risk:** no production filing integration; configuration/date/version handling must be reconciled with payroll snapshots.

### 17. DPDP Privacy — PARTIAL

- **Evidence:** `PrivacyCenter.tsx`, `DPDPPrivacyCenter.tsx`; `/api/v1/dpdp`; `dpdp_service.py`; migrations `016_dpdp_privacy.sql`, `044_dpdp_retention_hardening.sql`; retention worker/tests.
- **Implemented:** purpose/version/time/IP consent, withdrawal, access, erasure requests, legal holds/retention rules, privacy tokens, audit.
- **Missing/risk:** legacy GDPR/CCPA endpoints/tables remain reachable; deployed retention worker and secure deletion are unverified.

### 18. Data Localization/Security — PARTIAL

- **Evidence:** `data_localization.py`; startup/health checks; India upload services; migrations/audit tables; tests.
- **Implemented:** ap-south-1 per-upload guard, hard block for Aadhaar/PAN to non-India services, upload/transmission logs.
- **Missing/risk:** startup detects hard violations but deliberately continues; not every AI/SMS/file path uses the central guard; `/data-localization` always returns HTTP 200.

### 19. Employee 360 — PARTIAL

- **Evidence:** `Employee360.tsx`; employee APIs/services; migration `035_employee_360.sql`; tests.
- **Implemented:** consolidated personal, employment, statutory, financial, documents, certificates, performance, attendance, leave, payroll, training, career, events and timeline tabs.
- **Missing/risk:** source data still spans users/candidates and compatibility joins; self-only and sensitive field tests not currently run.

### 20. Attendance — PARTIAL

- **Evidence:** `AttendanceDashboard.tsx`; `/api/v1/attendance`; attendance service; migration `036_attendance.sql`; tests.
- **Implemented:** punch, GPS/geofence, late/absence/early/overtime, corrections/approval/history and audit.
- **Missing/risk:** biometric webhook explicitly returns 503 when no adapter configured; payroll gating relies on validation status but production integration is absent.

### 21. Shift Management — BROKEN

- **Evidence:** `WorkforceScheduler.tsx`; `/api/v1/workforce-schedules`; workforce service; migration `037_workforce_schedules.sql`; tests. Legacy `/api/v1/shifts`, dead `routers/scheduler.py`, and malformed `SchedulerDashboard.tsx` also exist.
- **Implemented in newer path:** templates, rosters, conflict/rest/hours rules, swaps/approval, leave/attendance/compliance links, WhatsApp publishing.
- **Why broken:** repository frontend build fails on malformed legacy scheduler component before any production bundle can be produced.
- **Recommendation:** remove/quarantine dead scheduler code after proving no imports, then make workforce scheduling canonical.

### 22. Leave Management — PARTIAL

- **Evidence:** `LeaveManagement.tsx`, Employee PWA and bot; `/api/v1/leave`; shared leave service; migrations `021`, `038_unified_leave_management.sql`; tests.
- **Implemented:** types, balances, requests, approvals, calendar/holidays/history, manager/HR flow, web/PWA/WhatsApp channels.
- **Missing/risk:** legacy HR-bot tables predate canonical leave schema; verify every bot command delegates to shared service and deprecate duplicate columns.

### 23. Indian Payroll — PARTIAL

- **Evidence:** `PayrollDashboard.tsx`; `/api/v1/payroll`; payroll service/PDF; migration `039_indian_payroll.sql`; tests.
- **Implemented:** configurable CTC components, EPF/ESIC/PT/TDS/LOP/OT/bonus/incentive/arrears/proration, approval, immutable snapshots, payslip, statutory exports.
- **Missing/risk:** checked-in `get_db()` is a stub for legacy billing; external filing and bank disbursement are not integrated; current tests cannot run.

### 24. Performance Management — PARTIAL

- **Evidence:** `PerformanceManagement.tsx`; `/api/v1/performance`; service; migration `046_performance_management.sql`; tests.
- **Implemented:** configurable cycles/KPIs by department/role, self/peer/manager reviews, guest feedback, scoring, increment/promotion recommendations.
- **Missing/risk:** no verified downstream approval into payroll/promotion lifecycle.

### 25. Training & Career Development — PARTIAL

- **Evidence:** `LearningCareer.tsx`; `/api/v1/learning-career`; service; migration `047_training_career.sql`; tests.
- **Implemented:** courses/video/quiz/certification/completion, skills/gaps, pathways/readiness, internal jobs and links from performance.
- **Missing/risk:** learning content hosting/provider and automatic promotion execution remain external/manual.

### 26. Retention Intelligence — PARTIAL

- **Evidence:** `EmployeeRetention.tsx`; `/api/v1/employee-retention`; transparent risk service; migration `048`; tests.
- **Implemented:** turnover/attendance/pay/promotion/pulse/training signals, risk score/level/factors/actions and intervention tracking.
- **Missing/risk:** rules are not a statistically validated predictive model, correctly so; data quality and scheduled recalculation need production validation.

### 27. Pulse Surveys/Engagement — PARTIAL

- **Evidence:** `EmployeeEngagement.tsx`; `/api/v1/employee-engagement`; service; migration `049`; tests.
- **Implemented:** PWA/WhatsApp surveys, anonymity/cohort suppression, scores/trends/comparisons, recognition and Employee of Month.
- **Missing/risk:** provider delivery is configuration-dependent; small-cohort privacy must be verified against all export/report paths.

### 28. Exit & Alumni — PARTIAL

- **Evidence:** `EmployeeExitManagement.tsx`; `/api/v1/employee-exit`; service; migration `050`; tests.
- **Implemented:** resignation, notice, interview/reason, clearance, settlement, letters, rehire status, alumni and lifecycle events.
- **Missing/risk:** settlement posting into approved payroll and eSigned letters need production integration verification.

### 29. Employee PWA — PARTIAL

- **Evidence:** `EmployeeApp.tsx`, `EmployeeLogin.tsx`; `/api/v1/employee-self-service`; migration `041`; tests.
- **Implemented:** OTP-oriented self-service for shifts, leave/balance, payslip/pay, EPF/ESIC and other employee modules through shared APIs.
- **Missing/risk:** no verified installable PWA manifest/service-worker/offline queue in this audit; low-cost Android and poor-network testing is outstanding.

### 30. Grievance/POSH — PARTIAL

- **Evidence:** `GrievanceManagement.tsx`; `/api/v1/grievances`; service; migration `051`; tests.
- **Implemented:** anonymous/confidential reports, references, evidence, investigation/escalation/resolution/POSH, access auditing.
- **Missing/risk:** uses admin client for sensitive workflows, so application-side fail-closed authorization and audit durability are critical; current escalation tests not run.

### 31. Salary Advance — PARTIAL

- **Evidence:** `SalaryAdvanceManagement.tsx`; `/api/v1/salary-advances`; service; migration `052`; tests.
- **Implemented:** eligibility/request/approval/disbursement/repayment/payroll deductions/balance/WhatsApp/audit.
- **Missing/risk:** no payment-provider disbursement integration; payroll posting must be transactionally tested.

### 32. Accommodation — PARTIAL

- **Evidence:** `AccommodationTransport.tsx`; `/api/v1/facilities`; service; migration `053`; tests.
- **Implemented:** buildings/rooms/beds, allocation, occupancy, check-in/out, maintenance and property/employee links.
- **Missing/risk:** operational notification and external facility integrations are absent.

### 33. Transport — PARTIAL

- **Evidence:** same facilities UI/API/service/migration/tests.
- **Implemented:** routes, stops, vehicles, drivers, schedules, assignments and capacity/property checks.
- **Missing/risk:** no GPS/fleet provider integration; schedule notifications are not centralized.

### 34. Recruitment Analytics — PARTIAL

- **Evidence:** `RecruitmentAnalytics.tsx`; analytics APIs/services; migration `054`; tests.
- **Implemented:** application/source/funnel/time/cost/interview/offer/ghosting/referral/quality metrics and filters.
- **Missing/risk:** legacy analytics service contains placeholder cost-per-hire; canonical analytics must exclude that path and validate source lineage.

### 35. Workforce Analytics — PARTIAL

- **Evidence:** `WorkforceAnalytics.tsx`; analytics APIs/services; migration `054`; tests.
- **Implemented:** headcount/vacancy/absence/OT/payroll/attrition/engagement/risk/productivity comparisons and drilldowns.
- **Missing/risk:** authoritative-source guarantees depend on migrations/views being deployed; productivity definition needs business ownership.

### 36. Owner Intelligence Dashboard — PARTIAL

- **Evidence:** `DashboardPage.tsx`; analytics dashboard endpoints; migration `055`; tests.
- **Implemented:** attendance/leave/absence/vacancy/payroll/compliance/risk/property/labour/OT/revenue/source/alerts, widgets and filters.
- **Missing/risk:** group/property authorization cannot be trusted until RLS and deployed views are tested; frontend build blocks delivery.

### 37. Automated Reports — PARTIAL

- **Evidence:** `ReportingCenter.tsx`; `/api/v1/reports`; `reporting_service.py`; scheduled worker; migration `056`; tests.
- **Implemented:** reusable report definitions/runs/schedules, PDF/CSV, email/WhatsApp delivery metadata.
- **Missing/risk:** SMTP/WhatsApp/S3 may skip or fallback when unconfigured; scheduler runtime and delivery reconciliation are unverified.

### 38. Notification Engine — PARTIAL

- **Evidence:** Twilio/email/WhatsApp gateways and domain-specific notification logs across scheduling, referrals, onboarding, HR bot, reports and salary advances.
- **Implemented:** multiple SMS/WhatsApp/email sends, provider IDs and selected retry/log behavior.
- **Missing/risk:** no single notification outbox, preference/consent model, retry/dead-letter policy, template/version registry or unified delivery webhook. Logic is duplicated across routers/services.

### 39. Unified Search — PARTIAL

- **Evidence:** global search router/service, migration `057`, tests and UI search integration.
- **Implemented:** candidates/employees/jobs/applications/referrals/documents/properties/departments/complaints, categories, autocomplete, recent search, fuzzy/exact matching and permission context.
- **Missing/risk:** migration and tests not currently run; client-side/in-memory fuzzy matching will not scale; sensitive complaint/document result filtering needs production escalation tests.

### 40. Hospitality AI Assistant — PARTIAL

- **Evidence:** `HospitalityAIAssistant.tsx`; `/api/v1/assistant`; `hospitality_ai_assistant_service.py`; migration `058`; tests.
- **Implemented:** read-only, permission-aware metric tools for attrition/overtime/hard-to-fill jobs/risk/vacancies/recruitment performance; citations/source metadata; destructive requests require confirmation/refusal.
- **Missing/risk:** real Claude execution depends on credentials; database views/migration are not verified; cross-border PII consent and prompt-output redaction need end-to-end testing.

## Cross-Cutting Gaps

### Duplicate Functionality and Models

1. **Jobs:** `jobs` and `job_roles`; APIs split between smart recruitment, matching and mobile modules.
2. **Applications:** legacy `job_role_id` plus newer `job_id`; stage vocabularies differ.
3. **Referrals:** legacy `/referrals`, India `/india-referrals`, admin routes and multiple migrations.
4. **Compliance/privacy:** Western `/compliance` remains live beside India KYC/labour/DPDP modules.
5. **Shifts:** legacy `/shifts`, newer `/workforce-schedules`, dead `/scheduler`, two scheduler UIs.
6. **Onboarding:** legacy `/onboarding` and India orchestration.
7. **AI matching:** `/matching` and `/ai-screening` overlap scoring/JD generation.
8. **WhatsApp:** `/api/whatsapp` and `/api/v1/hr-bot` overlap webhook/message handling.
9. **Labour:** minimum wage, EPF/ESIC and working-hours endpoints exist in both labour and India-compliance routers.

### Duplicate Migration Numbers

The migration folder contains duplicate numeric prefixes: `003`, `004`, `005`, `006`, `007`, and `008`. A migration tool that treats numeric versions as unique or lexically ordered may skip, reorder, or fail these files. Establish a migration ledger and renumber before production rollout.

### Dead or Unreachable Code

- `backend/app/routers/ats.py`
- `backend/app/routers/scheduler.py`
- `backend/app/routers/screening_chatbot.py`
- Malformed legacy frontend files that block compilation: `SchedulerDashboard.tsx`, `queryConfig.ts`, `BillingDashboard.tsx`, `PricingPage.tsx`.

### Mock and Incomplete Integrations

- Surepass Aadhaar/PAN and DigiLocker: sandbox without credentials.
- FSSAI/compliance S3: fake sandbox URLs without bucket credentials.
- Razorpay payout: mock can return `PAID` without credentials.
- eSign: demo fallback; SignDesk stub.
- Biometric attendance: adapter endpoint reports 503 when unconfigured.
- External job boards: CSV/manual export, not APIs.
- SMTP/Twilio/WhatsApp/report delivery: skipped or simulated when unconfigured.
- Video upload/thumbnail/duration paths contain local/file-size stubs.
- Legacy analytics cost-per-hire is estimated placeholder data.
- Billing SQLAlchemy dependency is explicitly `NotImplementedError`.

### Security Findings

1. **P0:** many early RLS policies use `USING (true)`, including conversations/messages, applications/video, seasonal campaigns, legacy compliance, OTP/bot sessions and referrals. Later migrations do not demonstrably replace every named policy.
2. **P0:** data-localization startup detects hard violations but intentionally lets the application start; health endpoint returns 200 even when non-compliant.
3. **P0:** frontend cannot compile, preventing route-guard and UI regression verification.
4. **P0:** production DB migration state is unknown; code and SQL cannot establish actual RLS state.
5. **P1:** admin/service-role clients bypass RLS. Sensitive complaint/webhook/worker paths require explicit authorization and fail-closed audit logging.
6. **P1:** legacy Western compliance APIs remain reachable despite India UI redirects.
7. **P1:** mock payouts must never transition production referrals to paid.
8. **P1:** cross-border AI and messaging calls are not proven to all use the localization/consent guard.
9. **P1:** webhook signature verification and replay protection need provider-level integration tests.

## Priority Plan

### P0 — Must Fix

1. Freeze feature development; repair frontend syntax/build and create a clean backend virtual environment.
2. Build an authoritative migration ledger, renumber duplicate versions, and test from an empty PostgreSQL database.
3. Inventory effective RLS in a migrated database; remove every unintended `USING (true)` policy and add tenant/property/department/self tests.
4. Select canonical models/APIs for jobs, applications, referrals, shifts, leave, onboarding, compliance and WhatsApp; put legacy routes behind deprecation flags.
5. Make production startup fail closed for data-localization violations and disable all “successful mock” behavior in production.

### P1 — Important

6. Restore backend tests, run the full suite, add frontend component/E2E tests, and enforce both in CI.
7. Centralize notifications into an outbox with templates, consent, retries, idempotency, provider callbacks and dead-letter handling.
8. Complete production provider validation: S3/KMS, Surepass/DigiLocker, Razorpay, WhatsApp, SMTP, eSign and scheduler workers.
9. Normalize pipeline statuses and foreign keys; backfill data and add compatibility views before removing old columns.
10. Run horizontal/vertical privilege escalation tests across every service-role and public-token endpoint.

### P2 — Enhancement

11. Replace in-memory search with indexed Postgres full-text/trigram search.
12. Add observability for queues, notifications, AI usage, provider failures and scheduled jobs.
13. Add data lineage and freshness metadata to executive/recruitment/workforce analytics.
14. Validate mobile/PWA accessibility, 360px layouts, offline/slow-network behavior and Hindi/Indic rendering.

### P3 — Future

15. Add external board APIs only where contracts and official APIs exist.
16. Add biometric/fleet/LMS/payroll-filing adapters behind stable interfaces.
17. Statistically validate retention models only after enough clean historical outcomes exist.

## Exact Implementation Order

1. Build/runtime repair.
2. Migration ledger and clean-database replay.
3. RLS/RBAC security baseline.
4. Canonical identity, organization, property, department and employee models.
5. Canonical jobs, candidates and applications model plus stage taxonomy.
6. Canonical attendance, shifts and leave services shared by web/PWA/WhatsApp.
7. Canonical payroll/statutory snapshots and approval boundary.
8. Canonical referrals and payout lifecycle.
9. India compliance, DPDP, secure documents and localization hardening.
10. Central notification/outbox and worker runtime.
11. Onboarding, performance, training, retention, engagement and exit integrations.
12. Analytics, reports, unified search and AI assistant on authoritative views.
13. Production third-party integrations and final mobile/browser E2E certification.

This order deliberately resolves shared models and security before adding providers or UI behavior, preventing new work from reinforcing duplicate systems.
