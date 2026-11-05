# HospRecruit AI — Manual Testing Guide

> **Complete product audit (2026-09-01):** Start with [docs/COMPLETE_PRODUCT_CAPABILITY_AUDIT.md](docs/COMPLETE_PRODUCT_CAPABILITY_AUDIT.md) for the evidence-based status of all 40 product capabilities, consolidation risks, security findings and implementation order. Use [docs/COMPLETE_E2E_MANUAL_TESTING.md](docs/COMPLETE_E2E_MANUAL_TESTING.md) for the consolidated end-to-end, RBAC/RLS, integration and regression test sequence. These documents supersede feature-level claims where repository-wide evidence conflicts.

> **Reporting update (2026-08-31):** See [docs/REPORTING_FUNCTIONALITY_AUDIT.md](docs/REPORTING_FUNCTIONALITY_AUDIT.md) for report, PDF, delivery and scheduler coverage, and [docs/REPORTING_MANUAL_TESTING.md](docs/REPORTING_MANUAL_TESTING.md) for data validation, security, scheduling and regression tests.

> **Owner dashboard update (2026-08-31):** See [docs/EXECUTIVE_DASHBOARD_AUDIT.md](docs/EXECUTIVE_DASHBOARD_AUDIT.md) for KPI coverage, security and remaining integrations, and [docs/EXECUTIVE_DASHBOARD_MANUAL_TESTING.md](docs/EXECUTIVE_DASHBOARD_MANUAL_TESTING.md) for operational, financial, widget and cross-property tests.

> **Workforce analytics update (2026-08-31):** See [docs/WORKFORCE_ANALYTICS_AUDIT.md](docs/WORKFORCE_ANALYTICS_AUDIT.md) for authoritative data coverage and remaining gaps, and [docs/WORKFORCE_ANALYTICS_MANUAL_TESTING.md](docs/WORKFORCE_ANALYTICS_MANUAL_TESTING.md) for metric, drilldown, payroll-security and isolation tests.

> **Recruitment analytics update (2026-08-31):** See [docs/RECRUITMENT_ANALYTICS_AUDIT.md](docs/RECRUITMENT_ANALYTICS_AUDIT.md) for verified coverage and remaining gaps, and [docs/RECRUITMENT_ANALYTICS_MANUAL_TESTING.md](docs/RECRUITMENT_ANALYTICS_MANUAL_TESTING.md) for metric calculations, filters, RBAC isolation and regression tests.

> **Accommodation and transport update (2026-08-30):** See
> [docs/ACCOMMODATION_TRANSPORT_AUDIT.md](docs/ACCOMMODATION_TRANSPORT_AUDIT.md) for verified coverage, property isolation and remaining integrations, and
> [docs/ACCOMMODATION_TRANSPORT_MANUAL_TESTING.md](docs/ACCOMMODATION_TRANSPORT_MANUAL_TESTING.md) for inventory, occupancy, check-in/out, maintenance, routes, capacity, employee assignment and regression tests.

> **Salary advance update (2026-08-30):** See
> [docs/SALARY_ADVANCE_AUDIT.md](docs/SALARY_ADVANCE_AUDIT.md) for verified coverage, security controls and remaining gaps, and
> [docs/SALARY_ADVANCE_MANUAL_TESTING.md](docs/SALARY_ADVANCE_MANUAL_TESTING.md) for eligibility, RBAC, disbursement, payroll deduction, outstanding balance, WhatsApp and regression tests.

> **Grievance and POSH update (2026-08-30):** See
> [docs/GRIEVANCE_MANAGEMENT_AUDIT.md](docs/GRIEVANCE_MANAGEMENT_AUDIT.md) for verified coverage, corrected security risks and remaining gaps, and
> [docs/GRIEVANCE_MANAGEMENT_MANUAL_TESTING.md](docs/GRIEVANCE_MANAGEMENT_MANUAL_TESTING.md) for anonymous submission, privilege escalation, fail-closed audit, investigation, evidence, POSH and regression tests.

> **Employee exit update (2026-08-30):** See
> [docs/EMPLOYEE_EXIT_MANAGEMENT_AUDIT.md](docs/EMPLOYEE_EXIT_MANAGEMENT_AUDIT.md) for lifecycle coverage and remaining gaps, and
> [docs/EMPLOYEE_EXIT_MANUAL_TESTING.md](docs/EMPLOYEE_EXIT_MANUAL_TESTING.md) for resignation, notice, interview, clearance, settlement, documents, alumni, RBAC/RLS and regression tests.

> **Employee engagement update (2026-08-30):** See
> [docs/EMPLOYEE_ENGAGEMENT_AUDIT.md](docs/EMPLOYEE_ENGAGEMENT_AUDIT.md) for verified coverage, privacy controls and remaining gaps, and
> [docs/EMPLOYEE_ENGAGEMENT_MANUAL_TESTING.md](docs/EMPLOYEE_ENGAGEMENT_MANUAL_TESTING.md) for PWA, WhatsApp, anonymity, cohort suppression, recognition, Employee of the Month, scoring and RBAC tests.

> **Employee retention update (2026-08-29):** See
> [docs/EMPLOYEE_RETENTION_AUDIT.md](docs/EMPLOYEE_RETENTION_AUDIT.md) for verified coverage, rules and remaining gaps, and
> [docs/EMPLOYEE_RETENTION_MANUAL_TESTING.md](docs/EMPLOYEE_RETENTION_MANUAL_TESTING.md) for signal, pulse, history, intervention, privacy, RBAC/RLS and regression tests.

> **Training and career update (2026-08-28):** See
> [docs/TRAINING_CAREER_AUDIT.md](docs/TRAINING_CAREER_AUDIT.md) for coverage and remaining gaps, and
> [docs/TRAINING_CAREER_MANUAL_TESTING.md](docs/TRAINING_CAREER_MANUAL_TESTING.md) for migration, course, quiz, skill-gap, pathway, internal-job, RBAC/RLS and regression testing.

> **DPDP update (2026-08-28):** See
> [docs/DPDP_PRIVACY_AUDIT.md](docs/DPDP_PRIVACY_AUDIT.md) for implemented and
> missing coverage, and
> [docs/DPDP_PRIVACY_MANUAL_TESTING.md](docs/DPDP_PRIVACY_MANUAL_TESTING.md) for
> consent, data access, secure documents, legal holds, partial erasure,
> retention-worker, masking and RLS test procedures.

> **Certification management update (2026-08-28):** See
> [docs/CERTIFICATION_MANAGEMENT_AUDIT.md](docs/CERTIFICATION_MANAGEMENT_AUDIT.md)
> for implemented and remaining coverage, and
> [docs/CERTIFICATION_MANAGEMENT_MANUAL_TESTING.md](docs/CERTIFICATION_MANAGEMENT_MANUAL_TESTING.md)
> for role requirements, secure uploads, verification, renewal, configurable
> expiry reminders, Employee 360 and tenant-isolation testing.

> **Performance management update (2026-08-28):** See
> [docs/PERFORMANCE_MANAGEMENT_AUDIT.md](docs/PERFORMANCE_MANAGEMENT_AUDIT.md)
> for existing, implemented and remaining coverage, and
> [docs/PERFORMANCE_MANAGEMENT_MANUAL_TESTING.md](docs/PERFORMANCE_MANAGEMENT_MANUAL_TESTING.md)
> for appraisal cycles, configurable hospitality KPIs, self/peer/manager review,
> guest feedback, scoring, outcome governance and RLS tests.

> **Scope**: Every implemented feature across backend API, frontend UI, and WhatsApp bot.
> **Prerequisites**: Backend running on `http://localhost:8000`, Frontend on `http://localhost:5173`.
> **API Docs**: `http://localhost:8000/docs` (Swagger UI — test any endpoint interactively).

---

## Table of Contents

1. [Environment Setup](#1-environment-setup)
2. [Health & Startup Checks](#2-health--startup-checks)
3. [Authentication & Multi-Tenancy](#3-authentication--multi-tenancy)
4. [Candidate Management](#4-candidate-management)
5. [AI Screening Chatbot](#5-ai-screening-chatbot)
6. [Shift Management & Matching](#6-shift-management--matching)
7. [Interview Scheduling](#7-interview-scheduling)
8. [Engagement — Ghosting Risk & NPS](#8-engagement--ghosting-risk--nps)
9. [Drip Sequences & Messaging](#9-drip-sequences--messaging)
10. [ATS Integration (Merge.dev)](#10-ats-integration-mergedev)
11. [Talent Pool & Retention](#11-talent-pool--retention)
12. [Onboarding & Compliance (RTW)](#12-onboarding--compliance-rtw)
13. [Analytics Dashboard](#13-analytics-dashboard)
14. [Billing & Subscriptions](#14-billing--subscriptions)
15. [Referral Programs](#15-referral-programs)
16. [India KYC Verification](#16-india-kyc-verification)
17. [FSSAI Certificate Tracking](#17-fssai-certificate-tracking)
18. [Indian Labour Compliance Engine](#18-indian-labour-compliance-engine)
19. [DPDP Act 2023 Privacy Center](#19-dpdp-act-2023-privacy-center)
20. [Data Localization Enforcement](#20-data-localization-enforcement)
21. [Indian Diversity Reporting](#21-indian-diversity-reporting)
22. [WhatsApp HR Bot](#22-whatsapp-hr-bot)
23. [Mobile Experience & QR Codes](#23-mobile-experience--qr-codes)
24. [AI Matching & JD Generation](#24-ai-matching--jd-generation)
25. [Frontend UI Smoke Test](#25-frontend-ui-smoke-test)
26. [Hotel & Multi-Property Management](#26-hotel--multi-property-management)
27. [Job Management End-to-End](#27-job-management-end-to-end)
28. [Multi-Channel Job Distribution](#28-multi-channel-job-distribution)
29. [Candidate ATS & Recruitment Pipeline](#29-candidate-ats--recruitment-pipeline)
30. [AI Candidate Screening Governance](#30-ai-candidate-screening-governance)
31. [Candidate Application Flow](#31-candidate-application-flow)
32. [Employee 360](#32-employee-360)
33. [Attendance Engine](#33-attendance-engine)
34. [Workforce Shift Scheduling](#34-workforce-shift-scheduling)
35. [Unified Leave Management](#35-unified-leave-management)
36. [Payroll Engine](#36-payroll-engine)

---

## 1. Environment Setup

### 1.1 Backend — start server

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
python run.py
```

**Expected**: Terminal shows `Uvicorn running on http://localhost:8000`.

### 1.2 Frontend — start dev server

```bash
cd frontend
npm install
npm run dev
```

**Expected**: `VITE ready on http://localhost:5173`.

### 1.3 Environment variables checklist

Create `backend/.env` and fill in all required values:

| Variable | Required | Notes |
|---|---|---|
| `SUPABASE_URL` | ✅ | From Supabase dashboard |
| `SUPABASE_KEY` | ✅ | Anon key |
| `SUPABASE_JWT_SECRET` | ✅ | JWT secret |
| `ANTHROPIC_API_KEY` | ✅ | Claude API |
| `TWILIO_ACCOUNT_SID` | ✅ | SMS + WhatsApp |
| `TWILIO_AUTH_TOKEN` | ✅ | |
| `TWILIO_PHONE_NUMBER` | ✅ | E.164 format |
| `TWILIO_WHATSAPP_NUMBER` | ✅ | `whatsapp:+14155238886` for sandbox |
| `MERGE_DEV_API_KEY` | ✅ | ATS integration |
| `STRIPE_SECRET_KEY` | ✅ | Billing |
| `STRIPE_WEBHOOK_SECRET` | ✅ | |
| `AWS_REGION` | ✅ | Must be `ap-south-1` |
| `AWS_S3_BUCKET` | optional | For file uploads |
| `SUREPASS_API_TOKEN` | optional | KYC — omit for sandbox mode |
| `RAZORPAY_KEY_ID` | optional | UPI payouts |

### 1.4 Database migrations

In Supabase SQL Editor, run migrations in order:

```
supabase/migrations/000_auth_setup.sql
supabase/migrations/001_init_schema.sql
supabase/migrations/002_screening_chatbot.sql
... (continue in filename order through 036_attendance_engine.sql)
```

---

## 2. Health & Startup Checks

### 2.1 Root endpoint

```bash
curl http://localhost:8000/
```

**Expected response**:
```json
{
  "name": "HospRecruit AI",
  "version": "v1",
  "docs": "/docs"
}
```

### 2.2 Health check with data localization

```bash
curl http://localhost:8000/health
```

**Expected**:
```json
{
  "status": "ok",
  "data_localization": { ... },
  "localization_ok": true,
  "localization_issues": []
}
```

**Failure case**: Set `AWS_REGION=us-east-1` in `.env` and restart. Health check should show `"localization_ok": false` and the startup log should print `[STARTUP] DATA LOCALISATION VIOLATION`.

### 2.3 Data localization status endpoint

```bash
curl http://localhost:8000/data-localization
```

**Expected**: JSON with `"ok": true`, `"issues": []`, `"warnings": []`.

### 2.4 Swagger UI

Open `http://localhost:8000/docs` in browser.

**Expected**: Full API documentation loads with all routers visible (candidates, shifts, screening, hr-bot, kyc, fssai, labour, dpdp, diversity, etc.).

---

## 3. Authentication & Multi-Tenancy

### 3.1 Obtain a JWT token (Supabase Auth)

Using the Supabase Dashboard or via API:

```bash
curl -X POST "https://YOUR_PROJECT.supabase.co/auth/v1/token?grant_type=password" \
  -H "apikey: YOUR_SUPABASE_ANON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "password123"}'
```

**Expected**: Response contains `access_token`. Save it as `TOKEN`.

### 3.2 Authenticated request

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/analytics/manager-dashboard
```

**Expected**: Dashboard data for the authenticated user's org only.

### 3.3 Multi-tenancy isolation
//How to login as an Organizatio - create a login button login as organizer and make able to create a candidate
1. Create two organizations in Supabase (org A and org B).
2. Log in as a user from org A, create a candidate.
3. Log in as a user from org B and call `GET /api/v1/candidates/job/{job_id}` for a job that belongs to org A.

**Expected**: Returns empty list — Row Level Security prevents cross-org data access.

### 3.4 Frontend login

1. Open `http://localhost:5173`.
2. Enter email and password.
3. Click **Sign In**.

**Expected**: Redirected to dashboard. JWT stored in browser session.

---

## 4. Candidate Management

Base URL: `POST/GET /api/v1/candidates`

### 4.1 Create a candidate

```bash
curl -X POST http://localhost:8000/api/v1/candidates/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Priya",
    "last_name": "Sharma",
    "email": "priya.sharma@example.com",
    "phone": "+919876543210",
    "job_id": "YOUR_JOB_UUID"
  }'
```

**Expected**: `201 Created` with candidate UUID.

### 4.2 Get candidate by ID

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/candidates/{candidate_id}
```

**Expected**: Full candidate profile including `pipeline_stage`, `screening_score`.

### 4.3 List candidates for a job

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/candidates/job/{job_id}"
```

**Expected**: Array of candidates for that job.

### 4.4 Get qualified candidates only

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/candidates/job/{job_id}/qualified"
```

**Expected**: Only candidates with `screening_score >= threshold`.

### 4.5 Update candidate availability

```bash
curl -X PUT http://localhost:8000/api/v1/candidates/{candidate_id}/availability \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"available_from": "2026-06-01", "shift_preference": "morning"}'
```

**Expected**: `200 OK` with updated candidate.

---

## 5. AI Screening Chatbot

Base URL: `/api/v1/screening`

### 5.1 Start a screening session

```bash
curl -X POST http://localhost:8000/api/v1/screening/chatbot/sessions/initiate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "CANDIDATE_UUID",
    "job_id": "JOB_UUID",
    "phone": "+919876543210"
  }'
```

**Expected**: Session created. Twilio sends first SMS question to candidate's phone.

### 5.2 Get session status

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/screening/chatbot/sessions/{session_id}
```

**Expected**: `status`, `current_question`, `score`, `turns_count`.

### 5.3 Get full transcript

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/screening/chatbot/sessions/{session_id}/transcript
```

**Expected**: Array of `{question, answer, score}` turns.

### 5.4 Twilio SMS webhook (simulate inbound SMS)

```bash
curl -X POST http://localhost:8000/api/v1/screening/webhook/twilio \
  -d "From=+919876543210&Body=I have 3 years experience in fine dining&To=+14155238886"
```

**Expected**: Bot processes candidate reply, sends next question via Twilio, returns 200.

### 5.5 Shortlist candidate

```bash
curl -X POST http://localhost:8000/api/v1/screening/candidate/{candidate_id}/shortlist \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: Candidate `pipeline_stage` updated to `shortlisted`.

### 5.6 Get screening metrics for a job

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/screening/job/{job_id}/metrics
```

**Expected**: `qualified_pct`, `avg_score`, `completion_rate`, `total_screened`.

### 5.7 Screening Chatbot Dashboard (frontend)

1. Open `http://localhost:5173/screening`.
2. Verify active sessions list with live scores.
3. Click a session to view full transcript.

---

## 6. Shift Management & Matching

Base URL: `/api/v1/shifts`

### 6.1 Create a shift

```bash
curl -X POST http://localhost:8000/api/v1/shifts/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "Banquet Waiter",
    "shift_type": "weekend_evening",
    "start_date": "2026-06-15",
    "end_date": "2026-08-31",
    "hours_per_week": 20,
    "urgency": "high"
  }'
```

**Expected**: `201` with shift UUID.

### 6.2 List open shifts

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/shifts/open
```

**Expected**: Array of shifts with `status: open`.

### 6.3 Match candidate to shifts

```bash
curl -X POST http://localhost:8000/api/v1/shifts/{candidate_id}/match \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: Array of matched shifts with `match_score`, sorted by score descending.

### 6.4 Get shifts by season

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/shifts/season/summer_2026"
```

**Expected**: Only shifts tagged with `summer_2026`.

### 6.5 Bulk match

```bash
curl -X POST "http://localhost:8000/api/v1/shifts/bulk-match?shift_id=SHIFT_UUID" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: All qualified candidates matched to the shift; returns match count.

---

## 7. Interview Scheduling

Base URL: `/api/v1/scheduler`

### 7.1 Initiate scheduling

```bash
curl -X POST http://localhost:8000/api/v1/scheduler/scheduler/initiate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "CANDIDATE_UUID",
    "job_id": "JOB_UUID",
    "manager_id": "MANAGER_UUID"
  }'
```

**Expected**: SMS sent to candidate with 3 available time slots.

### 7.2 Process candidate availability response (webhook)

```bash
curl -X POST http://localhost:8000/api/v1/scheduler/scheduler/webhook/twilio \
  -d "From=+919876543210&Body=Option 2"
```

**Expected**: Candidate's preferred slot recorded; manager gets SMS for one-click approval.

### 7.3 Manager approves interview

```bash
curl -X POST http://localhost:8000/api/v1/scheduler/scheduler/interviews/{interview_id}/manager/approve \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: Interview confirmed; calendar invite created; confirmation SMS sent to candidate.

### 7.4 Mark no-show

```bash
curl -X POST http://localhost:8000/api/v1/scheduler/scheduler/interviews/{interview_id}/mark-no-show \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: Status set to `no_show`; rescheduling SMS triggered.

### 7.5 Manager dashboard — pending approvals

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/scheduler/scheduler/dashboard/pending
```

**Expected**: Array of interviews awaiting manager approval.

### 7.6 Scheduler metrics

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/scheduler/scheduler/dashboard/metrics
```

**Expected**: `avg_time_to_hire_hours`, `no_show_rate`, `fill_rate`.

---

## 8. Engagement — Ghosting Risk & NPS

Base URL: `/api/v1/engagement`

### 8.1 Calculate ghosting risk for all candidates

```bash
curl -X POST http://localhost:8000/api/v1/engagement/ghosting-risk/calculate-all \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: Risk scores computed for all active candidates.

### 8.2 Get ghosting risk list

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/engagement/ghosting-risk
```

**Expected**: Candidates ranked by risk score (high → low) with `risk_level`, `last_contact`, `days_since_contact`.

### 8.3 Send outreach to at-risk candidate

```bash
curl -X POST http://localhost:8000/api/v1/engagement/ghosting-risk/{candidate_id}/outreach \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel": "sms", "template": "check_in"}'
```

**Expected**: SMS sent to candidate; `last_contact` updated.

### 8.4 Send NPS survey

```bash
curl -X POST http://localhost:8000/api/v1/engagement/nps/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"candidate_id": "CANDIDATE_UUID"}'
```

**Expected**: NPS survey SMS sent with unique response link.

### 8.5 Record NPS response (candidate-facing, no auth)

```bash
curl -X POST "http://localhost:8000/api/v1/engagement/nps/respond/{token}" \
  -H "Content-Type: application/json" \
  -d '{"score": 9, "feedback": "The process was smooth and fast!"}'
```

**Expected**: Response saved; score categorized (9–10 = Promoter).

### 8.6 NPS analytics

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/engagement/nps/analytics
```

**Expected**: `nps_score`, `promoters`, `passives`, `detractors`, `response_count`.

### 8.7 NPS feedback themes

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/engagement/nps/themes
```

**Expected**: Clustered themes (e.g., "Communication", "Speed", "Process").

---

## 9. Drip Sequences & Messaging

### 9.1 List drip sequences

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/engagement/drip/sequences
```

**Expected**: Array of sequences with `name`, `steps_count`, `enrolled_count`.

### 9.2 Create a drip sequence

```bash
curl -X POST http://localhost:8000/api/v1/engagement/drip/sequences \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Post-Interview Follow-up",
    "steps": [
      {"day": 1, "channel": "sms", "template": "interview_thanks"},
      {"day": 3, "channel": "sms", "template": "status_update"},
      {"day": 7, "channel": "email", "template": "final_offer"}
    ]
  }'
```

**Expected**: `201` with sequence UUID.

### 9.3 Enroll candidate in drip

```bash
curl -X POST http://localhost:8000/api/v1/engagement/drip/enroll \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"candidate_id": "CANDIDATE_UUID", "sequence_id": "SEQUENCE_UUID"}'
```

**Expected**: Enrollment created; first message scheduled.

### 9.4 Send message to candidate

```bash
curl -X POST http://localhost:8000/api/v1/engagement/messages/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "CANDIDATE_UUID",
    "channel": "sms",
    "content": "Hi Priya, just checking in about your application!"
  }'
```

**Expected**: SMS delivered via Twilio; message recorded in conversation history.

### 9.5 View messaging inbox

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/engagement/conversations
```

**Expected**: Conversations list with `unread_count`, `last_message`, `candidate_name`.

---

## 10. ATS Integration (Merge.dev)

Base URL: `/api/v1/ats` (no prefix in main router — check exact path in `/docs`)

### 10.1 Get ATS status

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/ats/status
```

**Expected**: `connected: true/false`, `ats_name`, `last_sync_at`.

### 10.2 Get ATS OAuth URL

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/ats/oauth-url
```

**Expected**: Authorization URL to redirect HR admin for ATS connection.

### 10.3 Sync jobs from ATS

```bash
curl -X POST http://localhost:8000/api/v1/ats/jobs/sync \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: Jobs pulled from ATS (e.g., Bullhorn) into local `jobs` table.

### 10.4 Push candidate to ATS

```bash
curl -X POST http://localhost:8000/api/v1/ats/candidates/{candidate_id}/push \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: Candidate synced to connected ATS with screened score and notes.

### 10.5 View sync logs

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/ats/sync-logs
```

**Expected**: Log entries with `operation`, `status`, `records_synced`, `timestamp`.

---

## 11. Talent Pool & Retention

Base URL: `/api/v1/talent-pool`

### 11.1 Create a seasonal cohort

```bash
curl -X POST http://localhost:8000/api/v1/talent-pool/cohort/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Summer 2026 Pool", "season": "summer_2026"}'
```

**Expected**: `201` with cohort UUID.

### 11.2 Get cohort candidates

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/talent-pool/cohort/{cohort_id}/candidates
```

**Expected**: Candidates in cohort with `retention_score`, `last_season_role`.

### 11.3 Launch re-engagement campaign

```bash
curl -X POST http://localhost:8000/api/v1/talent-pool/campaign/launch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cohort_id": "COHORT_UUID",
    "message": "Hey! Summer season is here. We have shifts for you 🏨"
  }'
```

**Expected**: Bulk SMS sent to all cohort members; `sent_count` returned.

### 11.4 Retention metrics

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/talent-pool/retention-metrics
```

**Expected**: `return_rate`, `avg_tenure_days`, `top_performers`.

---

## 12. Onboarding & Compliance (RTW)

### 12.1 Initialize onboarding flow

```bash
curl -X POST "http://localhost:8000/api/v1/onboarding/{candidate_id}/{job_id}/init-flow" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: Onboarding checklist created with auto-populated compliance tasks (RTW, background check, training).

### 12.2 Get onboarding status

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/onboarding/{candidate_id}/status
```

**Expected**: List of tasks with `status: pending/complete`, `due_date`, `required: true/false`.

### 12.3 Complete a task

```bash
curl -X POST http://localhost:8000/api/v1/onboarding/task/{task_id}/complete \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"result": "passed", "notes": "Background check cleared"}'
```

**Expected**: Task marked complete; next required task highlighted.

### 12.4 Request RTW verification

```bash
curl -X POST http://localhost:8000/api/v1/compliance/rtw/request \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"candidate_id": "CANDIDATE_UUID", "document_type": "passport"}'
```

**Expected**: SMS sent to candidate with secure upload link.

### 12.5 List expiring work authorizations

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/compliance/rtw/expiring
```

**Expected**: Candidates whose visa/work permit expires within 90 days.

---

## 13. Analytics Dashboard

Base URL: `/api/v1/analytics`

### 13.1 Manager dashboard

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/analytics/manager-dashboard
```

**Expected**:
```json
{
  "active_jobs": 5,
  "total_applications": 120,
  "avg_fill_time_days": 8,
  "no_show_rate": 0.22,
  "qualified_rate": 0.45
}
```

### 13.2 Pipeline visualization for a job

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/analytics/job/{job_id}/pipeline"
```

**Expected**: Counts at each stage: `applied → screened → interviewed → offered → hired`.

### 13.3 Cost-per-hire analysis

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/analytics/cost-per-hire
```

**Expected**: `avg_cost_per_hire`, `industry_benchmark`, `savings_vs_agency`.

### 13.4 No-show analysis

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/analytics/no-show-analysis
```

**Expected**: No-show rate by role, time of day, season, and trend over time.

### 13.5 Frontend dashboard

1. Open `http://localhost:5173/dashboard`.
2. Verify KPI tiles (active jobs, applications, fill time, no-show rate).
3. Verify bar chart with pipeline stages.

---

## 14. Billing & Subscriptions

Base URL: `/api/v1/billing`

### 14.1 View pricing tiers

```bash
curl http://localhost:8000/api/v1/billing/billing/pricing/tiers
```

**Expected**: Starter, Growth, Enterprise tiers with `price_monthly`, `features`, `ai_credits`.

### 14.2 Create checkout session

```bash
curl -X POST http://localhost:8000/api/v1/billing/billing/checkout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tier": "growth", "billing_cycle": "monthly"}'
```

**Expected**: Stripe `checkout_url` to redirect user to Stripe payment page.

### 14.3 Get subscription status

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/billing/billing/status
```

**Expected**: `tier`, `status: active`, `credits_remaining`, `renewal_date`.

### 14.4 Get invoices

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/billing/billing/invoices
```

**Expected**: Array of past invoices with `amount`, `status: paid`, PDF download URL.

### 14.5 Purchase credits

```bash
curl -X POST http://localhost:8000/api/v1/billing/billing/checkout/credits \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"credits": 500}'
```

**Expected**: Stripe checkout session for credit pack purchase.

---

## 15. Referral Programs

### 15.1 Global referral — create referral

```bash
curl -X POST http://localhost:8000/api/v1/referrals/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "referee_name": "Rahul Mehta",
    "referee_phone": "+919000000001",
    "job_id": "JOB_UUID"
  }'
```

**Expected**: Referral created with unique `referral_code`. Referral link generated.

### 15.2 Track referral link

```bash
curl http://localhost:8000/api/v1/referrals/track/{referral_code}
```

**Expected**: Referral marked as viewed; redirect URL returned.

### 15.3 Share via WhatsApp

```bash
curl -X POST http://localhost:8000/api/v1/referrals/referrals/{referral_id}/share/whatsapp \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: WhatsApp deep link returned with pre-filled message.

### 15.4 Mark referral paid

```bash
curl -X POST http://localhost:8000/api/v1/referrals/{referral_id}/mark-paid \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: `bonus_paid: true`; date recorded.

### 15.5 India referral — create with UPI

```bash
curl -X POST http://localhost:8000/api/v1/india-referrals/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "referee_name": "Rahul Mehta",
    "referee_phone": "+919000000001",
    "referrer_upi": "rahul.mehta@paytm",
    "job_id": "JOB_UUID"
  }'
```

**Expected**: Referral created with UPI ID for payout.

### 15.6 Leaderboard

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/india-referrals/leaderboard
```

**Expected**: Employees ranked by referrals with status `hired`.

### 15.7 Trigger UPI payout

```bash
curl -X POST "http://localhost:8000/api/v1/india-referrals/referrals/{referral_id}/pay-upi" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: Razorpay payout initiated; `payout_status: processing`.

### 15.8 Admin referral dashboard

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin-referrals/dashboard
```

**Expected**: Total referrals, hire rate, total bonuses paid, pending payouts.

---

## 16. India KYC Verification

Base URL: `/api/v1/kyc`

> Note: Without `SUREPASS_API_TOKEN` set, the system runs in **sandbox mode** (simulated responses).

### 16.1 Initiate Aadhaar OTP

```bash
curl -X POST http://localhost:8000/api/v1/kyc/aadhaar/initiate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "CANDIDATE_UUID",
    "aadhaar_number": "999900001111"
  }'
```

**Expected**:
- OTP sent to candidate's Aadhaar-linked mobile.
- Response contains `reference_id` (no Aadhaar number echoed back).
- Full 12-digit Aadhaar number **must not** appear in response body.

**Failure case**: Send `"aadhaar_number": "099900001111"` (starts with 0).

**Expected**: `422 Unprocessable Entity` — Aadhaar cannot start with 0.

### 16.2 Verify Aadhaar OTP

```bash
curl -X POST http://localhost:8000/api/v1/kyc/aadhaar/verify \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "CANDIDATE_UUID",
    "reference_id": "REF_ID_FROM_INITIATE",
    "otp": "123456"
  }'
```

**Expected**:
- `"verified": true`
- `"aadhaar_last4": "1111"` (last 4 digits only — full number discarded)
- DB stores only `aadhaar_last4`, never full Aadhaar
- Audit log entry created in `kyc_audit_log`

### 16.3 Verify PAN

```bash
curl -X POST http://localhost:8000/api/v1/kyc/pan/verify \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "CANDIDATE_UUID",
    "pan_number": "ABCDE1234F"
  }'
```

**Expected**:
- `"pan_masked": "ABCDE****F"` (middle 4 digits masked)
- DB stores masked PAN only
- `"aadhaar_pan_linked": true/false`

**Validation test**: Send `"pan_number": "abc123"` — expect `422` (invalid PAN format).

### 16.4 DigiLocker — get auth URL

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/kyc/digilocker/auth-url?candidate_id=CANDIDATE_UUID"
```

**Expected**: OAuth URL for candidate to authorize DigiLocker document sharing.

### 16.5 Get KYC verification status

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/kyc/identity-verification/{candidate_id}
```

**Expected**:
```json
{
  "aadhaar_verified": true,
  "pan_verified": true,
  "digilocker_connected": false,
  "aadhaar_last4": "1111",
  "pan_masked": "ABCDE****F"
}
```

### 16.6 Frontend — KYC Manager

1. Open `http://localhost:5173/kyc`.
2. Enter a candidate UUID.
3. Test Aadhaar OTP flow (initiate → enter OTP → verify).
4. Test PAN verification (enter valid PAN → verify → see masked result).
5. Test DigiLocker section (click Get Auth URL → copy URL).

---

## 17. FSSAI Certificate Tracking

Base URL: `/api/v1/fssai`

### 17.1 Get upload URL (S3 presigned)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/fssai/fssai?candidate_id=CANDIDATE_UUID"
```

**Expected**: Array of certificates (empty on first call).

### 17.2 Upload a certificate

```bash
curl -X POST http://localhost:8000/api/v1/fssai/fssai \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "CANDIDATE_UUID",
    "cert_type": "BASIC_FOOD_HYGIENE",
    "expiry_date": "2027-03-31",
    "file_name": "food_hygiene_cert.pdf"
  }'
```

**Expected**:
- `201` with `upload_url` (S3 presigned PUT URL, region `ap-south-1`)
- Certificate record created with `status: pending_upload`
- `cert_type` must be one of: `BASIC_FOOD_HYGIENE`, `FOSTAC`, `FSSAI_LICENSE`, `ALCOHOL_LICENSE_FORM_FL`

**Failure case**: `"cert_type": "INVALID_TYPE"` → `422 Unprocessable Entity`.

### 17.3 Get expiring certificates

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/fssai/fssai/expiring
```

**Expected**: Certificates expiring within 30 days with `days_remaining`, `candidate_name`.

### 17.4 Test all 4 certificate types

Repeat step 17.2 with each cert type:
- `BASIC_FOOD_HYGIENE` (required for all food handlers)
- `FOSTAC` (Food Safety Training and Certification)
- `FSSAI_LICENSE` (establishment license)
- `ALCOHOL_LICENSE_FORM_FL` (liquor service)

### 17.5 Expiry worker (Celery)

If Celery is installed and Redis is running:

```bash
celery -A app.celery_app worker --loglevel=info
celery -A app.celery_app beat --loglevel=info
```

Set a test certificate expiry to 25 days from today. At midnight the next day, check for SMS alert sent to candidate and recruiter.

**Expected**: Twilio SMS received: "Your FSSAI [cert_type] expires in 25 days. Please renew."

### 17.6 Frontend — FSSAI in KYC Manager

1. Open `http://localhost:5173/kyc`.
2. Scroll to FSSAI Certificate section.
3. Select cert type, enter expiry date, drag-drop a PDF.
4. Click Upload — verify presigned URL flow (3 steps: create record → get URL → upload file).

---

## 18. Indian Labour Compliance Engine

Base URL: `/api/v1/india-compliance` and `/api/v1/labour`

### 18.1 Get minimum wage for a state/role

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/india-compliance/minimum-wages/lookup" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "state": "Maharashtra",
    "skill_category": "semi_skilled",
    "industry": "hotels_restaurants"
  }'
```

**Expected**:
```json
{
  "state": "Maharashtra",
  "daily_rate_inr": 645,
  "monthly_rate_inr": 16770,
  "effective_date": "2025-10-01",
  "source": "Maharashtra Minimum Wages Act"
}
```

### 18.2 Check salary compliance

```bash
curl -X POST http://localhost:8000/api/v1/india-compliance/minimum-wages/check \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "state": "Delhi",
    "skill_category": "unskilled",
    "proposed_monthly_salary": 12000
  }'
```

**Expected**: `"compliant": true/false`, `"minimum_required": 14000`, `"shortfall": 2000`.

### 18.3 Working hours — shift analysis

```bash
curl -X POST http://localhost:8000/api/v1/india-compliance/working-hours/check \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "shift_start": "2026-06-01T09:00:00",
    "shift_end": "2026-06-01T19:00:00",
    "break_hours": 0.5,
    "establishment_type": "hotel"
  }'
```

**Expected**:
- `actual_hours: 9.5`
- `overtime_flag: true` (>8 hours per OSH Code 2020)
- `spread_over_ok: true` (≤10.5h spread)

**Violation test**: Send a 13-hour shift:

```bash
-d '{"shift_start": "2026-06-01T06:00:00", "shift_end": "2026-06-01T19:00:00", "break_hours": 0}'
```

**Expected**: `"hard_violation": true`, `"violation_reason": "Exceeds 12h spread-over limit (OSH Code 2020)"`.

### 18.4 Rest period check (12-hour rule)

```bash
curl -X POST http://localhost:8000/api/v1/india-compliance/working-hours/check-rest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "previous_shift_end": "2026-06-01T23:00:00",
    "next_shift_start": "2026-06-02T08:00:00"
  }'
```

**Expected**: `"rest_hours": 9`, `"compliant": false`, `"minimum_required_hours": 12`.

### 18.5 Weekly hours check

```bash
curl -X POST http://localhost:8000/api/v1/india-compliance/working-hours/check-weekly \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"weekly_hours": 52}'
```

**Expected**: `"compliant": false`, `"limit": 48`, `"overtime_hours": 4`.

### 18.6 EPF/ESIC calculation

```bash
curl -X POST http://localhost:8000/api/v1/india-compliance/epf-esic/calculate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"gross_salary_inr": 18000}'
```

**Expected**:
```json
{
  "employee_epf": 1800,
  "employer_epf": 661,
  "employer_eps": 1250,
  "esic_employee": 135,
  "esic_employer": 585,
  "total_ctc": 19246,
  "esic_applicable": true
}
```

**No ESIC case**: Send `"gross_salary_inr": 22000` — `"esic_applicable": false` (>₹21,000 threshold).

### 18.7 Gratuity calculation

```bash
curl -X POST http://localhost:8000/api/v1/india-compliance/gratuity/calculate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"last_drawn_salary": 25000, "years_of_service": 6}'
```

**Expected**: `"gratuity_amount": 72115` (formula: salary × 15/26 × years).

**Ineligible case**: `"years_of_service": 4` → `"eligible": false` (minimum 5 years).

### 18.8 Professional tax

```bash
curl -X POST http://localhost:8000/api/v1/india-compliance/professional-tax/calculate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"state": "Karnataka", "monthly_salary": 20000}'
```

**Expected**: `"professional_tax_inr": 200`.

### 18.9 List all states with minimum wages

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/india-compliance/minimum-wages/states
```

**Expected**: All 36 states/UTs seeded (verified by count).

### 18.10 Frontend — India Compliance Center

1. Open `http://localhost:5173/india-compliance`.
2. **Minimum Wages tab**: Select state "Maharashtra", skill "semi_skilled" → check wage.
3. **EPF/ESIC tab**: Enter gross salary ₹18,000 → verify all deduction breakdowns.
4. **Work Hours tab**: Enter shift start/end → verify violation badges appear for overtime.
5. **DPDP tab**: Should link or redirect to DPDP Privacy Center.
6. **Audit Trail tab**: Verify compliance check history is displayed.

---

## 19. DPDP Act 2023 Privacy Center

Base URL: `/api/v1/dpdp`

### 19.1 Get purpose codes (public reference)

```bash
curl http://localhost:8000/api/v1/dpdp/purposes
```

**Expected**: All 7 DPDP purpose codes:
- `RECRUITMENT` (required)
- `SCREENING_AI`
- `SMS_COMMUNICATION`
- `DOCUMENT_STORAGE`
- `ANALYTICS`
- `THIRD_PARTY_ATS`
- `CROSS_BORDER`

### 19.2 Record consent for one purpose

```bash
curl -X POST http://localhost:8000/api/v1/dpdp/consent \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "CANDIDATE_UUID",
    "purpose_code": "SCREENING_AI",
    "granted": true,
    "ip_address": "192.168.1.1",
    "consent_text_version": "v2.1"
  }'
```

**Expected**: `201 Created`, consent record with `timestamp`, `purpose_code`.

**No-bundling test**: Send an array of purposes in a single call — should be rejected with `422`.

**Required consent withdrawal test**: Try to withdraw `RECRUITMENT` consent:

```bash
-d '{"candidate_id": "CANDIDATE_UUID", "purpose_code": "RECRUITMENT", "granted": false}'
```

**Expected**: `400 Bad Request` — required consents cannot be withdrawn.

### 19.3 Get consent summary for candidate

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/dpdp/consent/{candidate_id}
```

**Expected**: Per-purpose consent status with `granted_at`, `ip_address`, `version`.

### 19.4 Create erasure request

```bash
curl -X POST http://localhost:8000/api/v1/dpdp/erasure-request \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "CANDIDATE_UUID",
    "request_type": "full_erasure",
    "reason": "Candidate requested data deletion under DPDP s.13"
  }'
```

**Expected**:
- `201` with `ticket_number`, `sla_deadline` (30 days)
- WhatsApp acknowledgment sent to candidate's phone in Hindi + English
- DB record created with `status: PENDING`

### 19.5 Process erasure request

```bash
curl -X POST "http://localhost:8000/api/v1/dpdp/erasure/{request_id}/process" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: PII fields nulled out; `status: COMPLETED`; audit log updated.

### 19.6 Candidate-facing Privacy Center (token-based, no auth)

1. Generate a privacy token from admin side (check the dpdp router for the token endpoint).
2. Open `http://localhost:5173/privacy-centre/{TOKEN}`.
3. Verify all 7 purpose toggles are displayed.
4. Toggle `SCREENING_AI` off — verify consent withdrawal recorded.
5. Submit erasure request — verify 30-day SLA notice and WhatsApp acknowledgment.

### 19.7 Frontend — DPDP Admin

1. Open `http://localhost:5173/dpdp-admin`.
2. Verify pending erasure requests with days-remaining countdown.
3. Verify consent audit trail per candidate.

---

## 20. Data Localization Enforcement

### 20.1 S3 region validation on startup

Set `AWS_REGION=eu-west-1` in `.env`, restart server.

**Expected** in logs:
```
[STARTUP] DATA LOCALISATION VIOLATION: AWS_REGION is eu-west-1, must be ap-south-1
```

Revert to `AWS_REGION=ap-south-1`.

### 20.2 File upload region guard

Attempt to create an FSSAI certificate and confirm that the presigned URL domain contains `ap-south-1`:

```
https://s3.ap-south-1.amazonaws.com/{bucket}/{key}
```

**Expected**: URL region matches `ap-south-1`.

### 20.3 Aadhaar to non-India service — hard block

The data localization guard (`DataLocalizationGuard`) rejects any attempt to send Aadhaar data to external non-India services (e.g., OpenAI, Twilio's US endpoints).

**Verify** by checking `backend/app/services/data_localization.py` — `NEVER_CROSS_BORDER` frozenset includes `AADHAAR`, `PAN`, `BIOMETRIC`.

### 20.4 Cross-border PII config warning

In `.env`, set:
```
ALLOW_PII_CROSS_BORDER=true
```
(without `PII_CROSS_BORDER_JUSTIFICATION`)

**Expected** in startup:
```
[STARTUP] WARNING: ALLOW_PII_CROSS_BORDER=true without justification
```

### 20.5 Audit log per upload

After uploading a file (FSSAI, RTW, resume):

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/compliance/audit-log
```

**Expected**: Audit entry with `file_key`, `s3_region: ap-south-1`, `uploaded_by`, `timestamp`.

---

## 21. Indian Diversity Reporting

Base URL: `/api/v1/diversity`

### 21.1 Collect diversity data (optional fields only)

```bash
curl -X POST http://localhost:8000/api/v1/diversity/eeo/collect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "CANDIDATE_UUID",
    "gender": "female",
    "is_pwd": false
  }'
```

**Expected**: `201 Created`. Fields `gender` and `is_pwd` stored.

**No religion field test**: Include `"religion": "Hindu"` in the body.

**Expected**: `422 Unprocessable Entity` — religion field is not accepted.

### 21.2 Social category — gated on statutory flag

```bash
curl -X POST http://localhost:8000/api/v1/diversity/eeo/collect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "CANDIDATE_UUID",
    "social_category": "SC"
  }'
```

**Expected**: `403 Forbidden` if org does not have `statutory_reporting_required = true`.

Set `statutory_reporting_required = true` on the org in Supabase, then retry.

**Expected**: `201 Created`.

### 21.3 Gender breakdown

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/diversity/gender-breakdown
```

**Expected**:
```json
{
  "male": 45,
  "female": 38,
  "non_binary": 3,
  "not_disclosed": 14
}
```

### 21.4 PwD metrics

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/diversity/pwd-metrics
```

**Expected**: `pwd_applicants`, `pwd_hired`, `pwd_hire_rate`.

### 21.5 Pay gap analysis

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/diversity/pay-gap
```

**Expected**: Pay gap by gender and role category.

### 21.6 Blind screening mode

```bash
curl -X POST http://localhost:8000/api/v1/ai-screening/blind-screening/{candidate_id} \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**:
- `first_name` replaced with `"Candidate #XXXXXX"` (hashed)
- `email` hashed to opaque token
- `phone`, `location`, `profile_photo` → `null`
- **DB is NOT modified** — only the response object is transformed

**Verify DB unchanged**: Immediately call `GET /api/v1/candidates/{candidate_id}` and confirm original name still present.

### 21.7 Frontend — Diversity Dashboard

1. Open `http://localhost:5173/diversity`.
2. Verify gender breakdown donut chart.
3. Verify PwD metrics section.
4. Verify pay gap table by role.
5. Confirm no religion field appears anywhere in the UI.
6. If org has `statutory_reporting_required = false`, confirm SC/ST/OBC/EWS section is hidden.

---

## 22. WhatsApp HR Bot

Base URL: `/api/v1/hr-bot`

### Setup

1. Configure Twilio WhatsApp sandbox: point **"When a message comes in"** to `https://YOUR_DOMAIN/api/v1/hr-bot/webhook`.
2. Ensure an employee exists in the `users` or `candidates` table with a phone number you control.
3. From that phone, join the Twilio WhatsApp sandbox by sending `join [sandbox-word]` to `+1 415 523 8886`.

---

### 22.1 HELP command

From WhatsApp, send: `HELP`

**Expected response** (Hinglish, formatted):
```
🤖 HospBot | नमस्ते [Name]! 👋
━━━━━━━━━━━━━━━━━
Available Commands / उपलब्ध कमांड:

📅 *LEAVE [date] [reason]*
💰 *PAYSLIP [month]*
🕐 *SHIFT*
📊 *BALANCE*
📋 *COMPLAINT [text]*
🌟 *CAREER*
❓ *HELP*
━━━━━━━━━━━━━━━━━
All data is secure 🔒 | DPDP Act 2023 compliant
```

### 22.2 LEAVE command — submit a leave request

Send: `LEAVE 2026-06-20 not feeling well`

**Expected**:
- Leave request created in `leave_requests` table
- Ticket number format: `LV-20260519-XXXXXX`
- Leave type auto-inferred: `CASUAL` (no sick/emergency keywords)
- Status: `PENDING`
- Bot replies with ticket number and confirmation

**Test leave type inference**:
- `LEAVE 2026-06-21 fever and cough` → type `SICK`
- `LEAVE 2026-06-22 family emergency` → type `EMERGENCY`

**Error cases**:
- `LEAVE` (no date) → "Please provide a date and reason."
- `LEAVE 2026-06-20` (no reason) → "Please add a reason after the date."
- `LEAVE 99-99-9999 sick` → "Invalid date '99-99-9999'."

### 22.3 LEAVE — date format variants

Send each of these (all should be accepted):
- `LEAVE 2026-06-20 headache` (ISO format)
- `LEAVE 20-06-2026 headache` (DMY with dash)
- `LEAVE 20/06/2026 headache` (DMY with slash)
- `LEAVE 20 June headache` (natural language)
- `LEAVE June 20 headache` (reversed natural)
- `LEAVE 20th June headache` (ordinal)

### 22.4 BALANCE command

Send: `BALANCE`

**Expected**:
```
🤖 HospBot | Leave Balance 2026
━━━━━━━━━━━━━━━━━
👤 [Employee Name]

📅 Casual Leave:   12 remaining (0 used)
🤒 Sick Leave:     12 remaining (0 used)
🌴 Earned Leave:   15 remaining (0 used)
━━━━━━━━━━━━━━━━━
✅ Total Remaining: 39 days
   Total Used:      0 days

To apply: LEAVE [date] [reason]
```

After submitting 2 leave requests, send `BALANCE` again — verify used count increases.

### 22.5 PAYSLIP command

First, create a payslip via admin API:

```bash
curl -X POST http://localhost:8000/api/v1/hr-bot/payslips \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "employee_id": "EMPLOYEE_UUID",
    "month": 4,
    "year": 2026,
    "gross_salary_inr": 18000,
    "net_salary_inr": 15750,
    "basic_salary_inr": 9000,
    "hra_inr": 3600,
    "epf_deduction_inr": 1440,
    "esic_deduction_inr": 135,
    "professional_tax_inr": 200,
    "working_days": 26,
    "present_days": 25
  }'
```

**Expected**: Payslip created + employee receives WhatsApp notification: "Your April 2026 payslip is ready."

Then from WhatsApp, send: `PAYSLIP April`

**Expected**:
```
🤖 HospBot | Payslip — April 2026
━━━━━━━━━━━━━━━━━
👤 [Employee Name]

💼 Earnings:
   Gross Salary:    ₹18,000
   Basic:           ₹9,000
   HRA:             ₹3,600

📉 Deductions:
   EPF:             ₹1,440
   ESIC:            ₹135
   Professional Tax:₹200
━━━━━━━━━━━━━━━━━
✅ Net Pay:         ₹15,750
📅 Attendance:      25/26 days
```

**Month format variants** (all should work):
- `PAYSLIP April`
- `PAYSLIP apr`
- `PAYSLIP 4`
- `PAYSLIP April 2026`
- `PAYSLIP` (no arg) → fetches previous month automatically

### 22.6 SHIFT command

Ensure the employee has a `shift_match` in `confirmed` or `matched` status linked to an open shift.

Send: `SHIFT`

**Expected**:
```
🤖 HospBot | Your Upcoming Shifts
━━━━━━━━━━━━━━━━━
🔹 Sun, 15 Jun 2026
   Role: Banquet Waiter
   Type: Weekend Evening
━━━━━━━━━━━━━━━━━
Reply HELP for all commands.
```

**No shifts case**: Remove all shift assignments → send `SHIFT`.

**Expected**: "No upcoming shifts scheduled. Contact your supervisor for roster details."

### 22.7 COMPLAINT command

Send: `COMPLAINT I have not received my salary for this month`

**Expected**:
- Ticket: `HR-YYYYMMDD-XXXXXX`
- Category auto-inferred: `Payroll`
- Bot replies with ticket number and 3-working-day SLA notice

**Category inference tests**:
- `COMPLAINT my manager is bullying me` → `Harassment`
- `COMPLAINT the kitchen equipment is dangerous` → `Safety`
- `COMPLAINT I feel there is discrimination in promotions` → `Discrimination`
- `COMPLAINT the wifi is slow` → `General`

**Too-short complaint** (< 10 chars):
Send: `COMPLAINT bad`

**Expected**: "Please describe your complaint in detail."

### 22.8 CAREER command

Create an open job via Supabase SQL:
```sql
INSERT INTO jobs (org_id, title, role_type, status) 
VALUES ('ORG_UUID', 'Senior Chef', 'full_time', 'open');
```

Send: `CAREER`

**Expected**:
```
🤖 HospBot | Career Opportunities 🌟
━━━━━━━━━━━━━━━━━
🔹 *Senior Chef*
   Type: Full Time
   [description if any]
━━━━━━━━━━━━━━━━━
Interested? Contact your HR manager or apply via the portal.
```

**No openings case**: Set all jobs to `status: closed` → send `CAREER`.

**Expected**: "No open positions at the moment."

### 22.9 Unregistered number

Send any message from a phone number NOT in `users` or `candidates`.

**Expected**:
```
🤖 HospBot
Your number (+91XXXXXXXXXX) is not registered in our system.
Please ask your HR manager to link your WhatsApp number.
कृपया अपने HR मैनेजर से अपना WhatsApp नंबर लिंक करवाएं।
```

### 22.10 Unknown command / typo

Send: `HALP` (typo for HELP)

**Expected**: Fuzzy match recognizes it as `HELP` and shows the full command menu.

Send: `XYZABC`

**Expected**: "Sorry, I didn't understand that. Type *HELP* to see all available commands."

### 22.11 Media-only message

Send an image or document without any text from WhatsApp.

**Expected**: "I can only process text commands. Please type HELP to see available commands."

### 22.12 Admin — approve leave request

```bash
curl -X PATCH "http://localhost:8000/api/v1/hr-bot/leave-requests/{request_id}/approve" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Approved - get well soon"}'
```

**Expected**:
- `{"approved": true}`
- Employee receives WhatsApp: "Leave Approved! Ticket: LV-... Date: ... ✅ Approved"

**Double-approve test**: Call approve again on the same request.

**Expected**: `409 Conflict — Request already approved`.

### 22.13 Admin — reject leave request

```bash
curl -X PATCH "http://localhost:8000/api/v1/hr-bot/leave-requests/{request_id}/reject" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"rejection_reason": "Short staffed on that day"}'
```

**Expected**:
- Employee receives WhatsApp with rejection reason
- Message includes: "You can apply for another date using: LEAVE [date] [reason]"

### 22.14 Admin — resolve complaint

```bash
curl -X PATCH "http://localhost:8000/api/v1/hr-bot/complaints/{complaint_id}/resolve" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"resolution_notes": "Salary disbursed. Payment slip sent to your email."}'
```

**Expected**:
- Complaint status → `RESOLVED`
- Employee WhatsApp: "Complaint Resolved. Resolution: Salary disbursed..."

### 22.15 Admin — list leave requests with filter

```bash
# All pending requests
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/hr-bot/leave-requests?status=PENDING"

# All approved requests
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/hr-bot/leave-requests?status=APPROVED"
```

**Expected**: Filtered list with correct statuses.

### 22.16 Admin — list complaints with filters

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/hr-bot/complaints?status=OPEN&category=PAYROLL"
```

**Expected**: Only open payroll complaints.

### 22.17 Admin — send manual WhatsApp

```bash
curl -X POST http://localhost:8000/api/v1/hr-bot/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone": "+919876543210", "message": "Your roster for next week is ready. Type SHIFT to view."}'
```

**Expected**: `{"sent": true, "sid": "SM..."}`.

### 22.18 Bot usage statistics

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/hr-bot/stats
```

**Expected**:
```json
{
  "active_sessions": 5,
  "leave_requests_pending": 3,
  "leave_requests_total": 12,
  "complaints_open": 2,
  "complaints_total": 7,
  "payslips_this_month": 45
}
```

### 22.19 Session tracking

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/hr-bot/sessions
```

**Expected**: Active sessions with `phone`, `last_command`, `last_message_at`, `message_count`.

After sending several WhatsApp messages, verify `message_count` increments on each message.

---

## 23. Mobile Experience & QR Codes

### 23.1 Apply via referral link (no auth)

```bash
curl -X POST "http://localhost:8000/api/v1/mobile/apply/{referral_code}" \
  -H "Content-Type: application/json" \
  -d '{"first_name": "Raj", "last_name": "Kumar", "phone": "+919000000002"}'
```

**Expected**: Application created; referral tracked.

### 23.2 Start mobile application

```bash
curl -X POST http://localhost:8000/api/v1/mobile/applications/start \
  -H "Content-Type: application/json" \
  -d '{"job_id": "JOB_UUID", "phone": "+919000000002"}'
```

**Expected**: Application session created with `application_id` and `resume_token`.

### 23.3 Frontend — mobile application form

1. Open `http://localhost:5173/mobile-apply`.
2. Fill in name, phone, availability.
3. Submit — verify application created.

---

## 24. AI Matching & JD Generation

Base URL: `/api/v1/matching`

### 24.1 Parse resume

```bash
curl -X POST http://localhost:8000/api/v1/matching/parse-resume \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "resume_text": "5 years experience as a sous chef in Marriott hotels. Skills: French cuisine, HACCP certified, team management.",
    "job_id": "JOB_UUID"
  }'
```

**Expected**: Extracted `skills`, `years_experience`, `match_score` (0–100).

### 24.2 Rank candidates

```bash
curl -X POST http://localhost:8000/api/v1/matching/rank-candidates \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_id": "JOB_UUID"}'
```

**Expected**: Candidates ranked by `match_score`, with `strengths` and `gaps` per candidate.

### 24.3 Generate bias-free JD

```bash
curl -X POST http://localhost:8000/api/v1/matching/generate-jd \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "Restaurant Manager",
    "property_type": "boutique hotel",
    "location": "Mumbai"
  }'
```

**Expected**: Full JD text with gender-neutral language, no age/race bias.

### 24.4 Reactivation scoring

```bash
curl -X POST http://localhost:8000/api/v1/matching/reactivation-candidates \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_id": "JOB_UUID", "lookback_days": 180}'
```

**Expected**: Past candidates re-scored against current job with `reactivation_likelihood`.

---

## 25. Frontend UI Smoke Test

Run through each page and verify it loads without console errors.

| URL | Page | What to Check |
|---|---|---|
| `/` | Landing | Marketing copy loads |
| `/login` | Auth | Login form renders, Supabase auth works |
| `/dashboard` | Dashboard | KPI tiles, charts, no 401 errors |
| `/screening` | Screening | Active sessions list loads |
| `/candidates` | Pipeline | Kanban/table view with candidate cards |
| `/scheduling` | Scheduler | Pending approvals count shows |
| `/engagement` | Ghosting Risk | Risk scores visible |
| `/nps` | NPS | Survey results chart renders |
| `/referrals` | Referral | Referral table loads |
| `/india-referrals` | India Referral | Leaderboard visible |
| `/compliance` | RTW | Compliance tasks list |
| `/billing` | Billing | Current plan and usage |
| `/kyc` | KYC Manager | All 4 sections (Aadhaar, PAN, DigiLocker, FSSAI) visible |
| `/india-compliance` | India Compliance | All tabs (Wages, EPF, Hours, DPDP, Audit) |
| `/dpdp-admin` | DPDP Admin | Erasure requests with countdown |
| `/diversity` | Diversity | Gender chart, PwD metrics |
| `/privacy-centre/{token}` | Privacy Center | 7 purpose toggles, erasure form |
| `/hotels` | Hotel & Properties | Property switcher, profile, departments, settings, group report |

---

## 26. Hotel & Multi-Property Management

### 26.1 Apply the migration

Run `supabase/migrations/028_hotel_multi_property_management.sql` in the Supabase SQL Editor after all migrations through `027_india_onboarding.sql`.

Verify:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'properties'
  AND column_name IN ('star_rating','address_line1','hr_settings','payroll_settings','compliance_settings');

SELECT table_name FROM information_schema.tables
WHERE table_name IN ('property_memberships','property_departments');
```

**Expected:** Five property columns and both new tables are returned.

### 26.2 Create a second property

1. Sign in as a user whose `users.role` is `admin`, `super_admin`, `owner`, or `group_admin`.
2. Open `http://localhost:5173/hotels`.
3. In **Add property**, enter `Goa Beach Resort`, code `GOA01`, type `RESORT`, city `Panaji`, state `Goa`, and rating `5`.
4. Select **Create property**.
5. Refresh the page.

**Expected:** The property appears in the property selector and retains its address, type, and rating.

### 26.3 Test property switching

1. Ensure the test user has active memberships for two properties.
2. Select the second property in the left-sidebar **Active property** selector.
3. Reload the browser.
4. Call:

```bash
curl http://localhost:8000/api/v1/hotels/properties \
  -H "Authorization: Bearer $TOKEN"
```

**Expected:** `active_property_id` matches the selected property after reload. The `/hotels` profile and department tabs show the selected property only.

### 26.4 Test department headcount

1. Open `/hotels`, select a property, then select **Departments**.
2. Add `FNB` / `Food & Beverage` with budgeted headcount `30`.
3. Set current headcount to `24` and save.
4. Open **Report**.

**Expected:** The department shows a gap of `6`; group reporting includes the updated budgeted/current totals.

### 26.5 Test property-specific settings

Open **Settings** and save each JSON object separately:

```json
{"probation_days":90,"weekly_off_policy":"ROTATIONAL"}
```

```json
{"pay_cycle":"MONTHLY","pay_day":7,"currency":"INR"}
```

```json
{"state_code":"GA","fssai_required":true,"minimum_rest_hours":12}
```

**Expected:** HR, payroll, and compliance values remain isolated in their respective setting types and persist after reload.

### 26.6 Test cross-property authorization

1. Create User A and User B in the same organization.
2. Give User A membership only to Property A and User B membership only to Property B.
3. Sign in as User A and list properties.
4. Attempt to switch to or read Property B directly:

```bash
curl -X POST http://localhost:8000/api/v1/hotels/properties/PROPERTY_B_UUID/switch \
  -H "Authorization: Bearer $USER_A_TOKEN"

curl http://localhost:8000/api/v1/hotels/properties/PROPERTY_B_UUID \
  -H "Authorization: Bearer $USER_A_TOKEN"
```

**Expected:** Property B is absent from User A's list and direct access returns `403`. A property from another organization returns `404` to avoid disclosing its existence.

### 26.7 Test group-level reporting authorization

```bash
curl http://localhost:8000/api/v1/hotels/reports/group \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected:** Group admin receives per-property headcount, open-job, and campaign totals. A property recruiter receives `403`.

### 26.8 Run focused automated tests

```bash
cd backend
python -m pytest tests/test_hotel_management.py -v --tb=short
```

**Expected:** All property profile, switching, membership, tenant-isolation, department, settings, and reporting tests pass.

---

## Appendix A — Quick Test Data Setup

Run this SQL in Supabase to create a test org + employee:

```sql
-- Create test org
INSERT INTO organizations (id, name) VALUES 
  ('00000000-0000-0000-0000-000000000001', 'Test Hotel Group');

-- Create test employee (for HR bot)
INSERT INTO users (id, org_id, email, phone, role) VALUES 
  ('00000000-0000-0000-0000-000000000002', 
   '00000000-0000-0000-0000-000000000001',
   'employee@testhotel.com',
   '+919876543210',
   'employee');

-- Seed leave balance for 2026
INSERT INTO leave_balances (org_id, employee_id, year)
VALUES ('00000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000002', 2026);

-- Create test job opening
INSERT INTO jobs (id, org_id, title, role_type, status) VALUES
  ('00000000-0000-0000-0000-000000000003',
   '00000000-0000-0000-0000-000000000001',
   'Senior Banquet Waiter', 'full_time', 'open');
```

---

## Appendix B — Automated Tests

Run full test suite to verify all service logic:

```bash
cd backend
python -m pytest tests/ -v --tb=short
```

**Expected**: All discovered tests pass. Do not use a hard-coded test count because the suite grows with each feature.

Run specific module tests:

```bash
python -m pytest tests/test_hr_bot.py -v          # 72 tests
python -m pytest tests/test_kyc.py -v             # KYC tests
python -m pytest tests/test_fssai_upload.py -v    # FSSAI tests
python -m pytest tests/test_labour_compliance.py -v
python -m pytest tests/test_dpdp.py -v
python -m pytest tests/test_data_localization.py -v
python -m pytest tests/test_diversity.py -v
python -m pytest tests/test_hotel_management.py -v
```

---

## Appendix C — Common Error Reference

| Error | Cause | Fix |
|---|---|---|
| `401 Unauthorized` | Missing or expired JWT | Re-authenticate, get new token |
| `403 Forbidden` | RLS policy blocking access | Ensure user's org_id matches data org_id |
| `404 Not Found` | Wrong UUID or record belongs to another org | Verify UUID from correct org |
| `409 Conflict` | Duplicate record (e.g., double-approve) | Check current status before acting |
| `422 Unprocessable Entity` | Pydantic validation failed | Check field types and formats |
| `500 Internal Server Error` | Service error | Check backend logs; verify `.env` keys |
| Bot: "not registered" | Phone not in users or candidates table | Add phone to users table |
| WhatsApp not received | Twilio webhook not configured | Point Twilio sandbox to `/api/v1/hr-bot/webhook` |
| S3 upload fails | Wrong region or missing credentials | Verify `AWS_REGION=ap-south-1` and keys |
| ESIC not calculated | Salary above ₹21,000 threshold | Expected behavior — ESIC only for ≤₹21,000 |
# Role-Based Access Control Manual Testing

> Apply `supabase/migrations/029_role_based_access_control.sql` before these tests. Use separate browser profiles for each account and never reuse an Owner token for lower-role tests.

## RBAC setup

1. Create or select one organization with two properties: Property A and Property B.
2. Create users for Owner, Group Admin/HR, General Manager, HR Manager, Department Head, Recruiter, Employee, and Candidate.
3. Set `users.role` to the canonical values shown above. Legacy values such as `admin`, `hiring_manager`, and `PROPERTY_RECRUITER` are supported during migration.
4. Assign the GM, HR Manager, Department Head, Recruiter, and Employee only to Property A in `property_memberships`.
5. Assign the Department Head to Department A using `users.department_id` and `property_memberships.department_id`.
6. Create candidate, job, application, leave, complaint, payslip, and shift records in both properties. Create records in two departments at Property A.

## Frontend route protection

1. Sign in as Recruiter. Confirm candidate, job, application, and screening pages are visible.
2. Enter `/india-compliance`, `/dpdp-admin`, `/admin-referrals`, and `/hotels` directly.
3. Confirm unauthorized pages redirect to Dashboard and restricted navigation items are absent.
4. Sign in as Employee. Confirm only self-service navigation remains and staff candidate screens cannot be opened directly.
5. Sign in as Owner. Confirm all administrative routes are available.

## Vertical privilege escalation

1. Capture an authenticated Recruiter request and replay it against `GET /api/v1/rbac/check/payroll.read`.
2. Confirm HTTP 403. Repeat for `financial.manage`, `compliance.manage`, and `employees.manage`.
3. As Employee, request `GET /api/v1/rbac/check/candidates.read`; confirm HTTP 403.
4. As Group Admin/HR, request `financial.manage`; confirm HTTP 403. As Owner, confirm HTTP 200.
5. Modify a JWT payload locally to claim `OWNER` without re-signing it. Confirm HTTP 401; role decisions must come from `public.users`, not JWT metadata.

## Horizontal property and department escalation

1. Sign in as the Property A Recruiter and set `X-Property-ID` to Property B in a captured request.
2. Query Property B candidates, jobs, applications, reports, and employee records. Confirm empty result/404 and no identifiers or counts leak.
3. Replace a Property A resource UUID with a known Property B UUID. Confirm 404 or an empty RLS result, not 403 with resource details.
4. Sign in as Department Head A and query an application or employee assigned to Department B. Confirm it is hidden.
5. Confirm the same Department Head can view and update permitted Application and Leave records in Department A.

## Self-service and sensitive data

1. As Employee A, fetch Employee A's payslip, leave, attendance, documents, and complaint status.
2. Replace Employee A's UUID with Employee B's UUID. Confirm no payroll/document/complaint data is returned.
3. Confirm Employee A can create their own leave request and complaint but cannot approve leave or resolve complaints.
4. Submit an anonymous complaint and verify non-complaint managers cannot reveal phone or employee identity.
5. As Candidate, verify only the candidate's linked application/documents are readable; candidate directory and other applications must be inaccessible.

## Automated RBAC regression

```powershell
cd backend
python -m pytest tests/test_rbac.py tests/test_hotel_management.py -q
```

Expected: all tests pass, including cross-property concealment and vertical escalation cases.

---

## 27. Job Management End-to-End

### 27.1 Setup

1. Apply migrations through `030_job_management_completion.sql`.
2. Create Property A and Property B. Add one department to each property.
3. Create an HR Manager, Recruiter, and Hiring Manager in the same organization. Give the recruiter access only to Property A.
4. Start the backend and frontend, sign in as the recruiter, and open **Smart Recruitment**.

### 27.2 Create and validate a structured job

1. Click **Create New Job** and select Property A, its department, and a hospitality role template.
2. Enter vacancies, monthly INR salary range, annual CTC range, min/max experience, education, skills, Hindi/English languages, and shift type.
3. Enable accommodation, food, and transportation. Select urgency, hiring manager, and recruiter.
4. Click **Preview JD**. Confirm English and Hindi appear and no new job card/database row is created.
5. Click **Create Job**. Confirm the job appears as `DRAFT` and has a unique apply URL and QR code.
6. In Supabase, verify the job stores canonical `property_id`, `department_id`, `role_template_id`, manager/recruiter IDs, JSON requirement fields, and benefits.
7. Negative checks: set salary min above max, CTC min above max, max experience below min, or vacancies to zero. Confirm HTTP 422 and no row is created.

### 27.3 Edit assignments and requirements

1. Click the edit icon on the draft job.
2. Change vacancies, compensation, experience, education, skills, languages, benefits, and both JDs; save.
3. Reopen edit and confirm all values persisted.
4. Change the property from A to B without selecting a new department. Confirm the old Property A department is cleared.
5. Select Property B's department and save. Confirm a Property A-only recruiter receives 403/404 because they lack access.
6. Attempt a direct API PATCH pairing Property A with Property B's department. Confirm HTTP 422.
7. Attempt to assign a manager/recruiter UUID from another organization. Confirm HTTP 422.

### 27.4 Approval lifecycle

1. As Recruiter, click **Submit for approval**. Confirm status becomes `PENDING_APPROVAL`.
2. Attempt `POST /api/v1/recruit/jobs/{id}/approval` as Recruiter. Confirm HTTP 403.
3. Sign in as HR Manager and approve. Confirm status is `OPEN`, approval is `APPROVED`, and the public apply endpoint returns the job.
4. Repeat with another draft and reject it. Confirm it returns to draft with `REJECTED` approval and notes retained.
5. Confirm `job_status_history` contains CREATE, SUBMIT_APPROVAL, and APPROVE/REJECT records with actor and timestamps.

### 27.5 Close, reopen, and duplicate

1. Close an approved open job. Confirm it disappears from public apply and records `closed_at`/`closed_by`.
2. Reopen it. Confirm status returns to `OPEN` and public apply works again.
3. Try reopening a rejected or draft job through the API. Confirm HTTP 409.
4. Duplicate the approved job. Confirm the copy is a new `DRAFT`, has `duplicated_from_job_id`, and receives a different apply URL/QR.
5. Confirm the copied job did not inherit approval/close actors or timestamps.

### 27.6 AI JD and job-board variants

1. Open a job and regenerate its JD. With a valid Anthropic key, confirm new English and Hindi content; without one, confirm the deterministic bilingual fallback is usable.
2. Call `POST /api/v1/recruit/jobs/{id}/job-board-versions`.
3. Confirm `job_board_versions` contains `naukri`, `apna`, `indeed_india`, `linkedin`, and `whatsapp`, each with English/Hindi content where applicable.
4. Confirm salary is formatted in INR and the WhatsApp/Apna copy contains the apply URL.
5. Note: this verifies generation and storage only. External job-board publishing is not implemented.

### 27.7 Candidate/application relationships and isolation

1. Apply through the public link. Confirm the resulting candidate/application links to the same job (`applications.job_id`; legacy `candidates.applied_job_id` remains supported).
2. Confirm the candidate appears in that job's pipeline counts.
3. As a Property A-only recruiter, try listing/getting/updating a known Property B job ID. Confirm no Property B data is exposed.
4. As an HR Manager with both properties, switch active property and confirm the appropriate jobs and department choices load.

### 27.8 Automated regression

```powershell
cd backend
python -m pytest tests/test_job_management.py tests/test_rbac.py tests/test_hotel_management.py -q
```

Expected: all focused tests pass. Also run the frontend build or at minimum parse `SmartRecruitment.tsx` before release.

---

## 28. Multi-Channel Job Distribution

### 28.1 Prerequisites

1. Apply migrations through `031_job_distribution.sql`.
2. Set `APP_BASE_URL` to the public frontend origin and `API_PUBLIC_BASE_URL` to the public backend origin. For local testing use `http://localhost:5173` and `http://localhost:8000`.
3. Create and approve an open job using section 27.
4. Open **Smart Recruitment**, find the job card, and click the share/distribution icon.

### 28.2 Channel configuration and preparation

1. Call `GET /api/v1/distribution/channels` and confirm all 12 channels are returned.
2. Confirm Naukri, Apna, WorkIndia, Shine, Indeed, LinkedIn, and Hospitality Job Boards show `MANUAL_EXPORT`, not API.
3. Disable a test channel with `PATCH /api/v1/distribution/channels/{channel}` and confirm it cannot be selected in the UI. Re-enable it.
4. Select Website, WhatsApp, Referral, Naukri, Apna, WorkIndia, Shine, Indeed, LinkedIn, Hospitality Board, QR, and Walk-in; click **Prepare selected**.
5. Confirm one `DRAFT` distribution exists per channel and repeated preparation updates rather than duplicates it.
6. Inspect English/Hindi content. Confirm role, property, INR salary, location, and apply call-to-action are appropriate for each platform.

### 28.3 Publish, manual export, and unpublish

1. Publish Website, WhatsApp, QR, and Walk-in. Confirm each receives a posting URL and `PUBLISHED` status.
2. Open the WhatsApp posting URL. Confirm WhatsApp opens with prefilled job content and tracked link; no message is sent without user action.
3. Publish a Naukri distribution. Confirm the response says `requires_manual_posting=true`; it must not claim a remote Naukri post was created.
4. Click **Export CSV** and verify rows for all selected boards, English/Hindi content, salary, vacancies, posting URL, and expiry.
5. Manually post one row to a test board, then publish again with its real `posting_url`/`external_post_id`. Confirm these values persist.
6. Unpublish a channel. Opening its tracked link must return 404 and no click event should be recorded.
7. Attempt to publish a draft, rejected, closed, or unapproved job. Confirm HTTP 409.

### 28.4 Click to application attribution

1. Copy a published tracked URL and open it in a private browser window.
2. Confirm HTTP 302 redirects to `/india-apply/{jobId}` with `org`, `src`, and `dist` query parameters.
3. Submit the mobile OTP application.
4. Verify the candidate stores the normalized source and `distribution_id`.
5. Verify `applications` contains the same job, candidate, organization, property, department, source, distribution ID, and attribution token.
6. Verify one `CLICK` and one `APPLICATION` event exist. Confirm the click stores a hashed IP, never the raw address.
7. Alter the `dist` token or use an unpublished token and submit. Confirm application attribution is rejected rather than accepting a spoofed source.

### 28.5 Hire conversion and analytics

1. Move the attributed candidate through screening/interview/offer to `hired`.
2. Confirm exactly one `HIRE` event is recorded and `hire_count` increments once.
3. Repeat the hired-stage action and confirm the unique event constraint prevents double attribution.
4. Call `GET /api/v1/distribution/analytics/summary?job_id={jobId}`.
5. Confirm click, application, hire, application-conversion %, and hire-conversion % match the event ledger.
6. Confirm a recruiter from another organization/property cannot view configuration, distributions, exports, or analytics.

### 28.6 Expiration

1. Set a test distribution `expires_at` in the past.
2. Open its tracked URL. Confirm HTTP 410 and status changes to `EXPIRED`.
3. Confirm no application can claim that expired token.

### 28.7 Automated regression

```powershell
cd backend
python -m pytest tests/test_job_distribution.py tests/test_job_management.py tests/test_rbac.py tests/test_hotel_management.py -q
```

Expected: all distribution, click-to-application-to-hire attribution, RBAC, and property-isolation tests pass.

---

## 29. Candidate ATS & Recruitment Pipeline

### 29.1 Prerequisites

1. Apply migrations through `032_candidate_ats_completion.sql` in filename order.
2. Start the backend and frontend, then sign in as an HR Manager or Recruiter with candidate permissions.
3. Create an approved open job and submit two applications using different names.
4. Confirm the same existing `candidates` and `applications` tables are used; no second candidate/application table should exist.

### 29.2 Candidate directory and profile

1. Open **Smart Recruitment** and select **Candidates**.
2. Confirm the directory displays name, phone/email, location, experience, skills, source, stage, and tags.
3. Search by partial name, phone digits, and email. Confirm only matching candidates remain.
4. Filter by job, stage, source, and location; combine filters and confirm all conditions apply.
5. Via Swagger, test `GET /api/v1/ats/candidates` with repeated `tags`, `skills`, and `languages` parameters plus `min_experience`.
6. Open a candidate profile. Verify salary/CTC, notice period, availability, resume, skills, languages, applications, referrals, documents, interview history, and timeline.
7. Add a recruiter note and refresh. Confirm it persists with author/time metadata.

### 29.3 Candidate profile update and documents

1. Call `PATCH /api/v1/ats/candidates/{candidateId}` with `expected_salary_inr`, `notice_period`, `languages`, `tags`, and `profile_summary`.
2. Confirm negative salary or experience returns HTTP 422.
3. Upload a candidate document using the existing protected S3/compliance upload flow.
4. Register its metadata with `POST /api/v1/ats/candidates/{candidateId}/documents`.
5. Reopen the profile and confirm the document link, type, status, and expiry are shown.
6. Confirm a user from another organization receives HTTP 404 and cannot read the candidate, notes, or document metadata.

### 29.4 Nine-stage Kanban

1. Open a job's **Pipeline** tab.
2. Confirm active columns appear in this order: Applied, Screened, Shortlisted, Interview, Selected, Offer, Offer Accepted, Onboarding, Hired.
3. Move one candidate through every stage in order.
4. After each move, verify `candidates.pipeline_stage`, `applications.status`, the matching timestamp, and a new `application_stage_history` row.
5. Reject a test candidate and confirm the candidate is removed from active columns while retaining history.
6. Try an unknown stage through the API and confirm HTTP 422.

### 29.5 Bulk actions

1. Select multiple Kanban cards and run shortlist, reject, and WhatsApp invite actions.
2. Call `POST /api/v1/ats/candidates/bulk-action` with `action=stage`; confirm candidate and latest application move together and history is written for each successful candidate.
3. Repeat with `action=tag` and verify tags merge without duplicates.
4. Repeat with `action=note` and verify one note is added per candidate.
5. Include one candidate ID from another organization. Confirm it is listed in `errors` and no cross-tenant update occurs.

### 29.6 Duplicate detection

1. Create a second candidate in the same organization using the same email with different letter case.
2. Call `GET /api/v1/ats/candidates/{candidateId}/duplicates`; confirm `matched_on` includes `email`.
3. Repeat with `+91 98765 43210` versus `9876543210`; confirm `matched_on` includes `phone`.
4. Repeat in another organization and confirm no cross-tenant duplicate is returned.
5. Confirm no automatic merge or deletion occurs; duplicate detection is advisory.

### 29.7 Interviews and feedback

1. Create slots with `POST /api/v1/engagement/interviews/slots`, invite a candidate, and open the token confirmation page.
2. Confirm the interview and reminder flow works and the slot appears in the candidate profile history.
3. Complete an async video interview and confirm it also appears in interview history.
4. Submit `PATCH /api/v1/ats/interviews/{interviewId}/feedback` with rating 1–5, notes, recommendation, and competency scores.
5. Confirm status becomes completed and feedback appears after reopening the profile.
6. Submit rating 0 or 6 and confirm HTTP 422.

### 29.8 Timeline and isolation

1. Move a stage, add a note, and complete an interview in a known order.
2. Open the candidate timeline and verify those events are ordered by timestamp.
3. Log in as an equivalent user in another organization and directly request the candidate/profile/application IDs.
4. Confirm HTTP 404/403 and verify no PII, notes, documents, referrals, interviews, or history leak.

### 29.9 Automated regression

```powershell
cd backend
python -m pytest tests/test_candidate_ats.py tests/test_job_distribution.py tests/test_job_management.py tests/test_rbac.py tests/test_hotel_management.py -q
```

Expected: ATS, job distribution, job management, RBAC, and multi-property isolation tests pass. Before release, parse/build `frontend/src/pages/SmartRecruitment.tsx` and smoke-test at 360px and desktop widths.

---

## 30. AI Candidate Screening Governance

### 30.1 Prerequisites and migration

1. Apply migrations through `033_ai_screening_governance.sql`.
2. Sign in as an HR Manager or Recruiter with candidate management permission.
3. Create a Mumbai Senior Waiter job with required skills `table service`, `POS systems`, and `guest relations`; Hindi and English; ₹18,000–₹24,000; two years' experience; evening/weekend shifts.
4. Create candidates representing a matching hotel waiter, BPO agent, domestic housekeeper, and salary/availability mismatch.

### 30.2 Resume parsing

1. Open **Resume Parsing** and upload one PDF and one DOCX resume.
2. Confirm name, contact data, skills, languages, work history, hospitality years, and total experience are extracted.
3. Confirm the original resume URL and parsed fields are stored on the existing candidate record.
4. Upload an unreadable file and confirm it is rejected or flagged for manual review rather than producing invented facts.

### 30.3 Deterministic screening

1. Open **AI Candidate Screening**, select the test job, and click **Run Screening**.
2. Confirm each result contains skill, experience, language, location, salary, and availability scores with reasons.
3. Run screening twice without changing facts or weights. Confirm every numeric score and rank is identical.
4. Disable the Anthropic key and repeat. Confirm scores remain identical and deterministic explanations remain available.
5. Confirm `candidate_screening_results` stores `deterministic_score`, `scoring_weights`, `scoring_version`, `score_breakdown`, `recommendation_reasons`, and `explanation_source`.

### 30.4 Hospitality and cross-industry scenarios

1. Confirm the hotel waiter scores strongly for matching experience, languages, salary, location, and shifts.
2. Screen the BPO candidate for Front Desk and confirm a call-center transfer explanation appears.
3. Screen that same BPO candidate for Commis Chef and confirm no BPO cross-industry boost is applied.
4. Confirm domestic cleaning can map to Housekeeping but not Front Desk or Chef.
5. Change expected salary above the job maximum and shifts to morning only. Confirm salary and availability scores decrease with exact reasons.

### 30.5 Blind screening

1. Enable **Blind Mode** and rerun screening.
2. Confirm the UI uses a stable blind ID and does not expose name, email, phone, photo, hometown/current city, gender, age, caste, religion, company names, or exact dates.
3. Call another organization's candidate blind-profile URL directly. Confirm HTTP 404/403.
4. Disable blind mode and confirm authorized identity fields return without changing the stored score.

### 30.6 Configurable weights

1. Call `GET /api/v1/ai-screening/screen/weights?job_id={jobId}` and record defaults.
2. `PUT` a valid set totaling exactly `1.0`, such as salary `0.50` with the other dimensions adjusted down.
3. Rerun screening and confirm the saved weights and resulting total reflect the new configuration.
4. Submit weights totaling `0.90` or `1.10`; confirm HTTP 422.
5. Set reject threshold equal to or above shortlist threshold; confirm HTTP 422.
6. Confirm another organization cannot read or update these weights.

### 30.7 AI explanation safety

1. Run with Anthropic enabled and confirm `explanation_source=CLAUDE` where successful.
2. Verify Claude wording cites candidate/job evidence and describes an advisory recommendation.
3. Simulate Claude failure and confirm deterministic scores/reasons persist.
4. Confirm no model-provided numeric score or recommendation can overwrite `deterministic_score`.

### 30.8 Recruiter confirmation and override

1. Call the shortlist endpoint without `confirmed=true` and a reason. Confirm HTTP 409 and no stage changes.
2. Click **Confirm Top 10**, provide a meaningful reason, and approve the confirmation dialog.
3. Confirm only then do candidate/application stages become `shortlisted`; verify application history and audit rows.
4. Expand a result, click **Override recommendation**, choose another recommendation, and provide a reason.
5. Confirm the recruiter override is displayed while deterministic score and original recommendation remain stored unchanged.
6. Clear/reverse an override through the API and confirm another audit record is appended.
7. Confirm screening alone never changes status to rejected, selected, offered, hired, or any other irreversible state.

### 30.9 Audit and isolation

1. Call `GET /api/v1/ai-screening/screen/audit?job_id={jobId}`.
2. Confirm SCREENED, WEIGHTS_CHANGED, SHORTLIST_CONFIRMED, and RECRUITER_OVERRIDE entries contain actor, time, reason, previous/new values, job, and candidate where applicable.
3. Sign in to another organization and repeat. Confirm no results, weights, or audit records leak.

### 30.10 Automated regression

```powershell
cd backend
python -m pytest tests/test_ai_screening_governance.py tests/test_candidate_ats.py tests/test_diversity.py tests/test_rbac.py -q
```

Expected: deterministic scoring, AI isolation, blind screening, ATS stages, diversity redaction, and RBAC tests pass. Parse `CandidateScreening.tsx` before release and smoke-test the table at desktop width and expanded cards at 360px.

---

## 31. Candidate Application Flow

Run migration `034_candidate_application_flow.sql` first. Set `SUPABASE_SERVICE_ROLE_KEY` only in `backend/.env`; never expose it through a `VITE_` variable. Use an open job UUID and its organization UUID.

### 31.1 Entry-level 60-second application

1. Open `/india-apply/{jobId}?org={orgId}&src=website` in a private window at 360 x 640.
2. Start a stopwatch. Enter a valid Indian mobile number and select **Send OTP**.
3. Enter a wrong OTP; confirm the form stays closed. Enter the correct OTP; confirm server verification opens the form.
4. Enter name, experience and city. Source should not be asked because the tracked link supplied it.
5. Submit and stop the timer. Target: under 60 seconds excluding SMS delivery.
6. Confirm one candidate and one application exist, status is `SUBMITTED`, completion time is stored, and source is `WEBSITE`.
7. Repeat with the same phone/job; confirm no duplicate candidate or application.

### 31.2 OTP security

1. Inspect the latest `mobile_otp_sessions` row. `otp_hash` must be populated and `otp` null.
2. Submit an invalid code three times; confirm further attempts are blocked.
3. Use an expired session; confirm it is rejected.
4. Complete the form with a valid `verification_token`, then try to reuse it; confirm no second application.
5. Submit an invalid/non-Indian phone; confirm validation feedback and no session row.

### 31.3 Resume and documents

1. Submit first; confirm success appears before any file is requested.
2. Upload a PDF/DOCX resume under 5 MB. Confirm a `candidate_documents` RESUME row and `candidates.resume_url` update.
3. Upload a JPG/PNG certificate. Confirm it links to the same candidate/application.
4. Try TXT/EXE (expect 415), over 5 MB (expect 413), a changed application ID (expect rejection), and random tracking token (expect 404).
5. Confirm S3 is `ap-south-1` and upload audit exists. Aadhaar/PAN must use the dedicated KYC flow.

### 31.4 Hindi/English and accessibility

1. Switch language on the apply and status pages; submit once in each language.
2. Confirm `preferred_language` stores `hi` or `en`.
3. At 360px and 200% text zoom, confirm labels/buttons remain visible, keyboard focus is clear, and there is no horizontal scroll.

### 31.5 Slow/interrupted network

1. In Chrome DevTools use Fast 3G with cache disabled. Reload and confirm no large media is required.
2. Use Slow 3G/data saver; submit and confirm `low_bandwidth_mode=true`.
3. Go offline while entering details. Confirm the warning appears and inputs remain in memory.
4. Reconnect and submit; confirm retry does not duplicate the application.
5. Throttle an optional upload; confirm a failed upload does not undo the submitted application and can be retried.

### 31.6 WhatsApp application

1. Configure Meta/Interakt at `/api/whatsapp/webhook`, or Twilio at `/api/v1/hr-bot/webhook`.
2. Select **Apply on WhatsApp**; the prefilled message must be `APPLY {jobId}`.
3. Answer name, city and experience. Confirm canonical candidate/application records with source `WHATSAPP` and `applied_via=WHATSAPP_BOT`.
4. Send non-numeric experience; confirm it asks again. Send `CANCEL`; confirm no application is created.
5. Repeat the same phone/job; confirm duplicate prevention.
6. Confirm webhook signature verification and that the service-role key is absent from browser bundles/logs.

### 31.7 QR source attribution

1. Scan a generated QR on iOS and Android; confirm the correct open job loads and scan analytics increment.
2. Submit and confirm source `QR_CODE`, `applied_via=QR_SCAN`, and distribution token linkage.
3. Replace the distribution token with a random UUID; submission must fail.
4. Move to hired and confirm QR attribution remains in distribution analytics.

### 31.8 Status portal

1. Select **Track application status** after submission.
2. Confirm all nine stages: Applied, Screened, Shortlisted, Interview, Selected, Offer, Offer Accepted, Onboarding, Hired.
3. Advance stages in ATS and refresh; the marker must advance. Confirm legacy stage aliases also display correctly.
4. Use a random token; no candidate data should be returned.

### 31.9 Automated and viewport regression

```powershell
cd backend
python -m pytest tests/test_candidate_application_flow.py tests/test_job_distribution.py tests/test_candidate_ats.py -q

cd ..\frontend
npm run build
```

Test 360x640, 375x667, 390x844, 412x915, 768x1024 and 1440x900. Verify no horizontal scroll/overlap and primary actions are at least 48px high.

---

## 32. Employee 360

Apply `035_employee_360.sql`. Prepare two properties, two departments, an employee in each, a department head, HR manager, general manager, group admin and owner. Link at least one employee to a hired candidate through `candidates.user_id`.

### 32.1 Canonical identity and profile assembly

1. Sign in as an employee and open `/employee-profile`.
2. Confirm the header and Personal tab use `users.id`, name, email and phone.
3. Confirm pre-hire location/language, skills, work history and application history come from the linked candidate without creating another employee row.
4. In Supabase, confirm no `employees` master table was introduced; `users.id` is referenced by all employee HR records.
5. Remove `candidates.user_id` on a legacy test record while retaining the same normalized email/org. Confirm the profile resolves the legacy candidate fallback.

### 32.2 Tab and empty-state coverage

1. Verify the permitted tabs: Personal, Employment, Financial, Statutory, Documents, Certifications, Performance, Attendance, Leave, Payroll, Training, Career, HR Events and Lifecycle.
2. Confirm sections with no rows show an empty state rather than a crash or mock data.
3. Confirm unavailable sensitive sections are absent from the API `visible_sections`, not merely hidden with CSS.
4. At 360x640, confirm tabs scroll horizontally, profile text does not overlap, and Refresh remains reachable.

### 32.3 Employment management

1. As HR Manager, call `PATCH /api/v1/employees/{id}/employment` with employee code, title, type, status, joining date, manager, property and department.
2. Refresh the profile and confirm the Employment tab updates.
3. Confirm an `EMPLOYMENT_UPDATED` lifecycle row was created.
4. Attempt the update as Employee, Recruiter and Candidate; expect 403.
5. As Department Head, attempt an employee in another department/property; expect 404 without revealing the employee.

### 32.4 Financial and payroll protection

1. As the employee, confirm only their own UPI/payslips appear.
2. Confirm Employee 360 never returns bank account number or IFSC.
3. As General Manager with `payroll.read`, view a scoped employee; confirm UPI username is masked and payslips are available.
4. As Recruiter or Department Head without `payroll.read`, confirm Financial and Payroll are absent.
5. Directly call another employee’s payslip/profile endpoint as Employee; expect 403/RLS denial.

### 32.5 Statutory and document protection

1. Seed Aadhaar last four, PAN, EPF UAN/member ID and ESIC IP number.
2. View as employee and authorized compliance staff. Confirm only masked identifiers leave the API.
3. Search the JSON response for full seeded identifiers; none should occur.
4. As a role without `compliance.read`, view another employee; Statutory must be absent.
5. Confirm Documents and Certifications show only the linked candidate’s records.
6. Try another organization’s employee/document IDs; expect 404/RLS denial.

### 32.6 Performance

1. As HR Manager, `POST /api/v1/employees/{id}/performance` with period, rating, goals and comments.
2. Confirm the profile Performance tab and lifecycle timeline update.
3. Confirm rating below 1 or above 5 fails at database validation.
4. As employee, confirm shared/permitted reviews can be read but disciplinary data remains absent.
5. Attempt creation as Employee or Recruiter; expect 403.

### 32.7 Attendance and leave

1. Seed working-hours compliance rows and shift assignments for employee A and B.
2. Confirm employee A sees only A’s hours, violations and shifts.
3. Confirm leave balances and requests match the employee and latest year.
4. As Department Head, confirm only department/property-scoped employees are visible.
5. Create leave through WhatsApp and refresh; confirm it appears without duplicate storage.

### 32.8 Training and certifications

1. As HR Manager, `POST /api/v1/employees/{id}/training` with name, provider, category and due date.
2. Confirm Training tab and lifecycle entry.
3. Complete training and attach certificate URL through the API/database; confirm status and score render.
4. Confirm FSSAI items remain under Certifications and are not copied into training rows.
5. Attempt cross-property assignment as a scoped manager; expect 404/403.

### 32.9 Disciplinary and HR events

1. As HR Manager, `POST /api/v1/employees/{id}/hr-events` with a warning/PIP/appreciation record.
2. Confirm it appears for authorized HR in HR Events and as `HR_ONLY` in lifecycle.
3. Sign in as the employee. Confirm HR Events is absent and the HR-only lifecycle row is absent.
4. Confirm Recruiter and Department Head cannot retrieve confidential HR events without `employees.manage` and scope.
5. Attempt direct Supabase SELECT as employee; RLS must return no HR event rows.

### 32.10 Horizontal and vertical escalation

1. Employee A requests `/api/v1/employees/{employeeB}/360`; expect 403.
2. Department Head A requests an employee in Department B; expect 404.
3. General Manager A requests another property without membership; expect 404.
4. Recruiter requests payroll/statutory/disciplinary sections; confirm they are absent.
5. Modify frontend state or call APIs directly; server/RLS results must remain unchanged.
6. Change `org_id`, property ID or department ID in requests; confirm no cross-tenant records.

### 32.11 Automated regression

```powershell
cd backend
python -m pytest tests/test_employee_360.py tests/test_rbac.py tests/test_hr_bot.py tests/test_labour_compliance.py -q

cd ..\frontend
npm run build
```

Expected: self-access, horizontal/property/department isolation, masking and disciplinary suppression pass. Also smoke-test `/employee-profile` at 360, 390, 768 and 1440 widths.

---

## 33. Attendance Engine

Apply `036_attendance_engine.sql`. Assign Employee A to Property A with `active_property_id`, employee code and a shift from 09:00 to 17:00. Create an attendance policy for Property A with its real coordinates, 150 m radius, 10-minute late grace, 5-minute early grace, 480-minute overtime threshold and Sunday (`7`) weekly off.

### 33.1 Policy and geofence setup

1. Sign in as General Manager or Department Head with Property A membership.
2. Call `POST /api/v1/attendance/policies` with Property A coordinates and `require_geofence=true`.
3. Confirm a radius below 25 m or above 5,000 m returns 422.
4. Omit coordinates while geofencing is enabled; expect 422.
5. Use Property B without membership; expect 404/403.
6. Verify employees cannot create/update policies through API or direct Supabase access.

### 33.2 Normal day

1. Sign in as Employee A and open `/attendance` on a phone.
2. Grant location permission while physically inside the configured geofence.
3. At 09:00 select **Punch In**, then at 17:00 select **Punch Out**.
4. Confirm two immutable `attendance_punches` rows and one `attendance_daily_records` row.
5. Expected: `PRESENT`, 480 worked minutes, 0 late/early/overtime and `validation_status=PENDING`.
6. Confirm the response says `payroll_ready=false` and the day is absent from `validated_attendance_for_payroll`.
7. As the scoped manager, call `PATCH /attendance/daily/{id}/validate` with `VALIDATE`; confirm it becomes payroll-visible.
8. Attempt to validate a missing/double-punch day without correction; expect 422.

### 33.3 GPS and geofence rejection

1. Deny browser location permission; confirm the UI reports that location is required.
2. Submit coordinates outside the radius directly to `POST /attendance/punch`; expect 422.
3. Confirm no punch row was created.
4. Submit coordinates inside the radius; confirm `geofence_status=INSIDE`, distance and GPS accuracy are stored.
5. Confirm another property ID or organization cannot be used by Employee A.

### 33.4 Late arrival

1. Use a 09:00 scheduled start and punch in at 09:25.
2. Punch out normally at 17:00.
3. Expected: `late_minutes=15` because the first 10 minutes are grace.
4. Confirm status remains `PRESENT` and validation remains `PENDING`.

### 33.5 Early departure

1. Punch in at 09:00 and out at 16:30 for a 17:00 shift.
2. Expected: `early_departure_minutes=25` after 5-minute grace.
3. Confirm worked minutes reflect actual paired time.

### 33.6 Overtime

1. Punch in at 09:00 and out at 19:00.
2. Expected: 600 worked minutes and 120 overtime minutes.
3. Confirm this does not create or alter a payslip.
4. Confirm overtime remains pending until attendance validation and separate payroll approval.

### 33.7 Missing punch

1. Punch in but do not punch out.
2. Expected: status `MISSING_PUNCH`, anomaly `MISSING_OUT`, validation `PENDING`.
3. Confirm a new punch-in on the next calendar date is allowed; yesterday's missing punch does not block today.
4. Request a correction with the missing out time and a reason of at least five characters.

### 33.8 Double punch

1. Punch in twice on the same date without punching out.
2. Expected: second API request returns 409 and no second raw punch is inserted.
3. For imported legacy/device data containing IN, IN, OUT, recalculate and confirm anomaly `DOUBLE_IN` and status `MISSING_PUNCH`.
4. Repeat with OUT, OUT and confirm `DOUBLE_OUT`.

### 33.9 Absence, leave and weekly off

1. Materialize a scheduled day with no punches; expect `ABSENT`.
2. Add an approved leave request for that date; recalculate and expect `LEAVE`, not absence.
3. Test Sunday with policy weekly off `[7]`; expect `WEEKLY_OFF`.
4. Confirm these statuses remain distinct in history and Employee 360.

### 33.10 Employee correction and manager approval

1. As Employee A, call `POST /api/v1/attendance/corrections` for A's daily record.
2. Try Employee B's daily record; expect 404/API denial and RLS rejection.
3. Confirm duplicate pending correction for the same day is rejected by the unique constraint.
4. As Property/Department A manager, open `/attendance`, approve the request and optionally add a review note.
5. Expected: correction becomes `APPROVED`; daily times and metrics are recalculated; `validation_status=VALIDATED` with reviewer/time.
6. Confirm the validated row now appears in `validated_attendance_for_payroll`.
7. Approve it a second time; expect 409.
8. As a manager in Property B or another department, attempt approval; expect 404/403.
9. Repeat with Reject; daily record must remain unvalidated.

### 33.11 Correction audit trail

1. Inspect `attendance_correction_audit_logs` after request and approval/rejection.
2. Confirm `REQUESTED` and final status actions contain before/after JSON, actor and timestamp.
3. Attempt update/delete/insert of audit rows as employee and manager; RLS must deny it.
4. Confirm authorized attendance readers can view only audit records for scoped employees.

### 33.12 Biometric adapter

1. Set `BIOMETRIC_WEBHOOK_SECRET` only in backend environment; never in Vite/frontend variables.
2. POST canonical events to `/api/v1/attendance/biometric/GENERIC_JSON/webhook` with matching `X-Attendance-Token`.
3. Verify employee mapping uses `users.employee_code`, not name or phone.
4. Confirm a normalized BIOMETRIC punch and a `PROCESSED` sync event are stored.
5. Send the same provider event ID twice; confirm no duplicate punch and duplicate response/error.
6. Use an unknown employee code; confirm a `FAILED` sync event with mapping error.
7. Use a wrong token; expect 401. Remove secret configuration; expect 503.
8. Use an unsupported provider code; confirm it is rejected. Do not label it integrated until a concrete adapter and vendor contract are tested.

### 33.13 History and responsive UI

1. Confirm Employee A sees only A's history and corrections.
2. Confirm manager filters remain property/department scoped at API and RLS layers.
3. Check `/attendance` and Employee 360 Attendance at 360, 390, 768 and 1440 px.
4. Confirm buttons are at least 48 px, tables scroll rather than overlap and GPS errors are readable.

### 33.14 Automated regression

```powershell
cd backend
python -m pytest tests/test_attendance.py tests/test_employee_360.py tests/test_rbac.py tests/test_labour_compliance.py tests/test_hr_bot.py -q

cd ..\frontend
npm run build
```

Expected attendance cases: normal, late, early departure, overtime, absence, weekly off, missing punch, double punch, geofence and manager correction pass. Existing payroll records must not change during these tests.
# 34. Workforce Shift Scheduling

## Setup

1. Apply Supabase migrations through `037_workforce_shift_scheduling.sql` in numeric order.
2. Sign in as an Owner, Group Admin, General Manager, or Department Head with `attendance.manage` and membership for the test property.
3. Ensure two employee users belong to that property and have phone numbers. Configure Twilio WhatsApp credentials, or use the service's mock mode.
4. Open **Features → Shift Scheduling** (`/shifts`) and select the test property.

## Weekly and monthly roster

1. Select **Week**, move to the required week, and click **Create roster**.
2. Create templates through `POST /api/v1/workforce-schedules/templates` for Morning (09:00–17:30) and Evening (17:30–02:00), including breaks.
3. Add assignments through `POST /api/v1/workforce-schedules/schedules/{scheduleId}/shifts`.
4. Confirm each assignment appears on the correct day. Drag one card to another day and confirm it persists after refresh.
5. Switch to **Month**, create a monthly roster, and confirm every date is visible and returned by `/calendar`.

## Availability, leave, weekly off, and conflict prevention

1. As an employee, post availability with `POST /api/v1/workforce-schedules/availability/me`.
2. As a manager, create the employee's weekly off with `POST /api/v1/workforce-schedules/weekly-offs`.
3. Attempt a shift outside availability. Expect HTTP 409 with `OUTSIDE_AVAILABILITY`.
4. Attempt a shift on the weekly off. Expect HTTP 409 with `WEEKLY_OFF`.
5. Approve leave for a date, then assign a shift on it. Expect HTTP 409 with `APPROVED_LEAVE`.
6. Assign 09:00–17:00, then attempt 16:00–23:00. Expect `OVERLAP`.
7. Assign an ending shift at 23:00, then attempt the next shift at 08:00. Expect `INSUFFICIENT_REST`.
8. Schedule more than 48 net hours in one ISO week. Expect `EXCESSIVE_WEEKLY_HOURS`.
9. Verify a direct database insert that violates the same constraints is rejected by `employee_shift_assignment_guard`.

## Approval, publication, attendance, and WhatsApp

1. Click **Submit**, then **Approve**. Confirm invalid state transitions return HTTP 409.
2. Click **Publish & notify**. Confirm schedule status is `PUBLISHED`, assignments are `PUBLISHED`, and notification rows exist in `shift_notification_logs`.
3. From the employee WhatsApp number send `SHIFT`. Confirm the published roster is returned before any legacy candidate shift matches.
4. Punch in/out on a roster date. Confirm attendance uses the published scheduled start/end and calculates late arrival, early departure, and overtime against it.
5. Confirm payroll remains `payroll_ready=false` until attendance validation.

## Shift swap and authorization

1. As the assigned employee, create a swap request. A different employee must not be able to create it for them.
2. If a target employee is selected, sign in as that employee and approve the peer step.
3. As a manager, approve the swap. Confirm the target is revalidated for overlap, leave, weekly off, rest, availability, and weekly hours.
4. Confirm the original employee, unrelated-property manager, recruiter, and candidate cannot approve the swap.
5. Verify users from another organization/property receive 404/403 and cannot read roster, availability, audit, or notification rows.

## Expected audit evidence

Check `shift_schedule_audit_logs` for `SHIFT_ASSIGNED`, `SHIFT_MOVED`, `SCHEDULE_SUBMITTED`, `SCHEDULE_APPROVED`, `SCHEDULE_PUBLISHED`, and `SWAP_APPROVED`/`SWAP_REJECTED` with the authenticated actor ID.

# 35. Unified Leave Management

## 35.1 Setup

1. Apply migrations through `038_unified_leave_management.sql` in numeric order.
2. Ensure the employee has a `property_memberships` row, active property, phone number and current-year `leave_balances` row.
3. Open `/leave` as the employee. Confirm Casual, Sick and Earned balances match the database.
4. Confirm seeded leave types exist for CASUAL, SICK, EARNED, EMERGENCY and LWP.

## 35.2 Web and PWA parity

1. Submit a one-day Casual request on `/leave` with source WEB.
2. Repeat from an installed PWA/browser session with source PWA.
3. Confirm both records use `leave_requests`, have `PENDING` status, reserve the same balance and differ only in `source`.
4. Submit a multi-day request spanning Sunday and a configured property holiday. Confirm `total_days` excludes Sunday and the holiday.
5. Attempt an end date before start date; expect 422.
6. Attempt overlapping pending/approved dates; expect 409 and no second balance reservation.
7. Exhaust a balance and request another paid leave day; expect 409. Confirm LWP follows its configured negative-balance policy.

## 35.3 WhatsApp parity

1. From the employee's registered number send `LEAVE 2026-09-10 fever`.
2. Confirm the bot resolves the employee and calls the canonical leave service.
3. Verify the resulting row has `source=WHATSAPP`, the inbound `whatsapp_message_id`, the same status fields and the same balance behavior as web/PWA.
4. Send the same request again; expect duplicate-date rejection and no second balance change.
5. Confirm manager notification and employee confirmation include the ticket number.

## 35.4 Manager and HR approvals

1. Submit Casual leave. As the scoped Department Head/manager, approve it. Expect manager status and overall status `APPROVED`.
2. Submit Earned leave where `requires_hr_approval=true`. Manager approval must set `manager_status=APPROVED`, leave `hr_status=PENDING`, and keep overall status `PENDING`.
3. As HR Manager, Group Admin or Owner, approve the second stage. Expect overall `APPROVED`.
4. As Department Head, Recruiter or Employee, attempt the HR stage. Expect 403.
5. Reject at either valid stage with a reason. Expect overall `REJECTED`, balance restored exactly once and WhatsApp notification.
6. Repeat a decision on a final request. Expect 409 and no balance change.

## 35.5 Calendar, history and cancellation

1. Add a property holiday with `POST /api/v1/leave/holidays`; confirm it appears in `/leave` for that month.
2. Call `/api/v1/leave/calendar` for the property/date range. Confirm only scoped pending/approved leave and property holidays are returned.
3. Confirm Employee A sees only their history. Managers see only allowed property/department data.
4. Cancel a pending own request; expect `CANCELLED` and balance restoration. Cancelling approved/rejected leave must return 409.

## 35.6 Security and audit

1. As Employee A, request or cancel leave for Employee B by changing IDs; expect denial/RLS rejection.
2. As a manager in Property B, review Property A leave; expect 404/403.
3. As Recruiter or Candidate, call review endpoints; expect 403.
4. Inspect `leave_audit_logs` for `SUBMITTED`, approval/rejection stage and `CANCELLED`, including actor, source, before and after data.
5. Confirm changing `source` never bypasses balance, duplicate, approval or authorization checks.

## 35.7 Automated checks

```powershell
cd backend
python -m pytest tests/test_leave_management.py tests/test_leave_command.py tests/test_hr_bot.py tests/test_workforce_scheduling.py tests/test_attendance.py -q
```

Expected: WEB, PWA and WHATSAPP use the same service; duplicate ranges, insufficient balances and unauthorized approval are rejected.

# 36. Payroll Engine

## 36.1 Setup and configuration

1. Apply migrations through `039_payroll_engine.sql`.
2. Configure a property with state, payroll administrators and validated attendance policy.
3. Create an effective-dated payroll rule using `POST /api/v1/payroll/rules`. Verify percentages and thresholds are not present in frontend source or requests unless entered as configuration.
4. Create employee compensation structures with monthly gross, annual CTC, Basic/HRA overrides if applicable, allowances, state, joining date and EPF/ESIC applicability.
5. Confirm another property/organization cannot read or modify rules, compensation, runs or exports.

## 36.2 Known calculation examples

1. Gross ₹20,000, Basic 50%, HRA 50% of Basic, PT ₹200, no TDS/LOP/variables:
   - Basic ₹10,000; HRA ₹5,000; EPF employee ₹1,200; ESIC employee ₹150.
   - Net ₹18,450; employer cost ₹21,850.
2. Gross ₹30,000: ESIC must be zero because wages exceed configured ₹21,000 limit. With Basic ₹15,000, EPF ₹1,800 and PT ₹200, net is ₹28,000.
3. Gross ₹50,000 with EPF cap enabled: employee EPF ₹1,800. Disable cap in a test rule: employee EPF becomes ₹3,000 on ₹25,000 Basic.
4. Join 16 July on ₹30,000 gross: verify 16/31 proration and gross ₹15,483.87.
5. April gross ₹20,000 with two validated absence/LOP days: verify LOP ₹1,333.33 and gross ₹18,666.67.
6. Add 8 overtime hours, bonus, incentive, arrear and deduction. Verify each remains a separate snapshot component and net arithmetic reconciles.

## 36.3 Attendance and payroll safety

1. Create pending/unvalidated attendance and calculate payroll. Confirm it is absent from `validated_attendance_for_payroll` and cannot contribute overtime or LOP.
2. Manager-validates attendance, recalculate a DRAFT/CALCULATED run and confirm attendance snapshot includes validated days, absences and overtime.
3. Attempt to calculate after submission/approval; expect 409.
4. Change attendance after finalization and confirm the finalized snapshot and payslip do not change.

## 36.4 Run approval and immutability

1. Open `/payroll`, create a run and calculate it.
2. Add BONUS, INCENTIVE, ARREAR, DEDUCTION and REIMBURSEMENT through the adjustments API; recalculate and reconcile totals.
3. Submit the run. Sign in as the same creator and attempt approval; expect maker-checker 409.
4. Sign in as a different authorized payroll approver, approve, then finalize.
5. Confirm finalized payslips are created once and item/payslip hashes match their snapshots.
6. Attempt update/delete of finalized `payroll_run_items` and `payslips` directly; database trigger must reject it.
7. Inspect `payroll_approval_logs` for actor, note, before and after status.

## 36.5 Payslip and employee privacy

1. Download `GET /api/v1/payroll/payslips/{id}/pdf`; verify earnings, EPF, ESIC, PT, TDS, LOP, overtime, variables and net pay.
2. Confirm the PDF is private and delivered through an authenticated endpoint or expiring India-region S3 URL.
3. From the registered employee WhatsApp number send `PAYSLIP April`; confirm only that employee's finalized payslip is returned.
4. Change the payslip/employee ID to another employee as an Employee role; expect 403/RLS denial.

## 36.6 Statutory exports

1. Before finalization request EPF ECR, ESIC or Form 16 data; expect 409.
2. After finalization download all three exports and verify checksum rows in `payroll_statutory_exports`.
3. Reconcile EPF ECR UAN, wages and contributions against the finalized snapshot.
4. Reconcile ESIC IP data, gross and employee/employer contribution.
5. Treat `FORM16_DATA` as preparation data only. Do not present it as official Form 16; issue the certificate through TRACES/authorized process.
6. Validate ECR/ESIC files in the current official portal test utility before production filing.

## 36.7 Automated checks

```powershell
cd backend
python -m pytest tests/test_payroll_service.py tests/test_attendance.py tests/test_employee_360.py tests/test_hr_bot.py -q
```

Expected: known examples, ESIC threshold, EPF cap, joining proration, LOP, overtime, variables, deterministic hashes and export generation pass.

# 37. Offer-to-Onboarding

## 37.1 Setup and template precedence

1. Apply migrations through `040_onboarding_orchestration.sql` in numeric order.
2. Sign in as HR Manager/Group Admin and open `/india-onboarding`.
3. Select **Manage Templates** and create an organization-wide template with all scope UUIDs blank.
4. Create a second template for Property A, then a third for Property A + Department A + Role A.
5. Confirm an Employee, Candidate or Recruiter without employee-management permission cannot create templates.
6. Query `onboarding_templates` and `onboarding_template_tasks`; verify organization ownership and task uniqueness.

## 37.2 Automatic offer-accepted trigger and idempotency

1. Choose an application in Property A/Department A/Role A with no onboarding flow.
2. Move it to `OFFER_ACCEPTED` through the ATS stage API/UI.
3. Verify exactly one `onboarding_flows` row exists with the application, candidate, job, property, department and most-specific template IDs.
4. Verify tasks were copied from that template and due dates are relative to joining date.
5. Confirm one `offer_accepted_welcome` pre-boarding message is queued when the candidate has a phone.
6. Write `OFFER_ACCEPTED` again or retry the request. Confirm no duplicate flow, tasks or welcome message.
7. Accept an offer with no organization template. Confirm the global India Standard template is used.

## 37.3 Assignment, appointment letter and eSign

1. Assign a same-organization manager, joining date, reporting location and time using `PATCH /api/v1/india-onboarding/flows/{id}/assignment`.
2. Attempt to assign a manager from another organization; expect 400 and no change.
3. Generate an appointment letter with gross monthly INR, probation and notice period. Verify persisted CTC breakup and HTML.
4. Request demo eSign and verify status becomes `requested`; mark/callback as signed and confirm the appointment task can be completed.
5. In production, repeat using the contracted eSign provider and verify signed PDF storage URL is private and in India.

## 37.4 Documents, KYC, PF/ESIC and certifications

1. Complete Aadhaar/PAN through KYC Manager. Confirm full Aadhaar/PAN values never appear in onboarding tables.
2. Attach candidate documents and complete document tasks with document URLs.
3. Upload/verify required FSSAI or role certificates and complete certification tasks.
4. Generate PF Form 2 and ESIC declaration, submit each and complete corresponding tasks.
5. Configure employee compensation/payroll setup and complete the payroll setup task.
6. Verify optional/waived tasks do not block completion and failed/pending mandatory tasks do.

## 37.5 Completion and ghosting risk

1. Complete weighted mandatory tasks one by one; verify overall and stage percentages after every update.
2. Call `POST /api/v1/india-onboarding/flows/{id}/recalculate`.
3. For a joining date within seven days, completion below 50%, no activity for three days, no manager and unsigned letter, verify HIGH/CRITICAL risk with each reason listed.
4. Update activity, manager, signature and overdue tasks; recalculate and verify risk falls deterministically.
5. Complete all mandatory tasks; verify 100%, `status=completed` and `completed_at` is set.
6. Confirm risk recalculation does not change the candidate/application hiring stage.

## 37.6 Pre-boarding and WhatsApp reminders

1. Schedule the standard six-message sequence from the dashboard.
2. Confirm messages use offer/joining-relative timestamps and duplicate scheduling is rejected or does not duplicate rows.
3. Run `POST /api/v1/india-onboarding/send-preboarding` when a message is due.
4. With test WhatsApp credentials, verify outbound delivery ID and `sent` status. Force provider failure and verify `failed` plus error detail.
5. Confirm messages for Property A cannot be viewed or sent by a Property B-only user.

## 37.7 Empty/error states and authorization

1. In an organization with no flows, open `/india-onboarding`; verify a true empty state, not demo candidates.
2. Stop the backend and refresh; verify the API error is visible and no mock rows appear.
3. As Department Head A, request Department B flow/task IDs directly; expect 403/404 or RLS denial.
4. As a different tenant, request a known flow ID; expect 404/RLS denial.
5. As a read-only role, attempt task completion, assignment and template creation; expect 403.

## 37.8 Automated checks

```powershell
cd backend
python -m pytest tests/test_onboarding_orchestration.py tests/test_candidate_ats.py tests/test_kyc.py tests/test_payroll_service.py -q
```

Expected: template precedence, weighted completion, explainable risk and existing ATS/KYC/payroll behavior pass without regressions.

# 38. Employee PWA and WhatsApp Parity

## 38.1 Setup and OTP

1. Apply migrations through `041_employee_pwa_self_service.sql`.
2. Configure Supabase phone authentication with an India-capable SMS provider and use HTTPS in production.
3. Ensure the employee's Supabase Auth phone and `users.phone` are the same verified `+91XXXXXXXXXX` number.
4. Open `/employee-login` at 360×640, switch between English and Hindi, request OTP and verify it.
5. Try an unregistered phone. Confirm `shouldCreateUser=false` prevents account creation.
6. Enter an invalid number, expired OTP and incorrect OTP; verify clear errors and no session.
7. Confirm successful OTP opens `/employee-app` and `/api/v1/rbac/me` identifies role `EMPLOYEE`.

## 38.2 PWA installation and poor network

1. Build and serve the frontend over HTTPS; confirm the browser detects `manifest.webmanifest` and `sw.js`.
2. Install to a low-cost Android device or Chrome Android emulator and launch standalone.
3. In DevTools use a 360px viewport, 4× CPU slowdown and Slow 3G. Confirm navigation remains responsive and controls do not overflow.
4. Load the employee app once, enable offline mode and relaunch. Confirm the shell/offline page loads.
5. Confirm leave, advance and grievance submit buttons are disabled offline.
6. Inspect Cache Storage. Confirm `/api/`, payslip PDFs, salary data and authenticated responses are not cached.

## 38.3 Shift and swap parity

1. Publish two shifts for Employee A and one for Employee B.
2. Open Employee A's PWA. Confirm only A's published/confirmed shifts appear; draft and B's shifts must not.
3. Send `SHIFT` from A's registered WhatsApp. Confirm the dates/times match the PWA because both call `employee_shifts()`.
4. Request a swap from the PWA. Confirm one `shift_swap_requests` row enters `PENDING_MANAGER` when no peer is selected.
5. Attempt another active swap for the same assignment; expect conflict/unique-index rejection.
6. Approve as the scoped manager and verify overlap, leave, weekly-off, 12-hour-rest and 48-hour checks still run.

## 38.4 Leave and balance parity

1. Note Casual/Sick/Earned balances in the PWA, then send WhatsApp `BALANCE`; values must match.
2. Submit leave from the PWA. Verify `source=PWA`, status `PENDING`, balance reservation and audit log.
3. Submit the same dates using WhatsApp `LEAVE`; expect duplicate-date rejection from the same service.
4. Approve/reject through the existing manager/HR workflow and refresh the PWA. Confirm status and restored/consumed balance.

## 38.5 Salary, EPF and payslips

1. Finalize payroll for Employee A with EPF/ESIC deductions and an effective compensation structure.
2. Open Pay in the PWA. Verify monthly gross, annual CTC, EPF/ESIC applicability and latest net pay.
3. Download the payslip. Confirm the authenticated PDF belongs to A.
4. Send `PAYSLIP <month>` on WhatsApp. Reconcile gross, EPF, ESIC and net values with the PWA PDF.
5. Change a payslip ID to Employee B's ID; expect 403/RLS denial.

## 38.6 Salary advance

1. Submit ₹5,000 with a reason and two repayment months. Verify status `PENDING`, source `PWA` and employee/property scope.
2. Submit another while pending; expect 409.
3. As payroll manager review it through `PATCH /api/v1/employee-self-service/salary-advances/{id}/review`.
4. As another employee attempt to read/review it; expect RLS/403 denial.
5. Verify approval does not silently mutate finalized payroll. Add recovery/disbursement only through an explicit payroll adjustment.

## 38.7 Accommodation, transport, benefits and ESIC clinic

1. As HR, configure Property A with `PUT /api/v1/employee-self-service/support/{propertyId}`.
2. Enter accommodation details, transport contact/routes, benefits, ESIC clinic and emergency/POSH contacts.
3. Confirm Property A employees see them in Help and Property B employees do not.
4. Remove optional values and verify the PWA shows a truthful “Not listed/Contact HR” state rather than mock data.

## 38.8 Grievance and POSH

1. Submit a named grievance in the PWA; verify `hr_complaints.source=APP`, employee ID and property ID.
2. Submit an anonymous grievance; verify `employee_id IS NULL`, a random token is returned and saved for tracking.
3. Submit an anonymous POSH complaint. Verify `complaint_type=POSH`, category `HARASSMENT`, severity at least `HIGH`, and no employee ID.
4. Send `COMPLAINT ANON <text>` through WhatsApp. Verify it uses the same `submit_grievance()` service and table.
5. As a normal manager attempt to reveal anonymous identity/phone; expect denial and masked display.
6. Follow the configured Internal Committee procedure outside the application; the app must not auto-resolve POSH cases.

## 38.9 Automated checks

```powershell
cd backend
python -m pytest tests/test_employee_self_service.py tests/test_leave_management.py tests/test_hr_bot.py tests/test_workforce_scheduling.py tests/test_payroll_service.py -q
```

Expected: shared shift/grievance services, channel-consistent leave, own-data authorization, salary-advance idempotency and existing WhatsApp behavior pass.

---

# 39. WhatsApp HR Bot End-to-End Audit

## 39.1 Provider and webhook verification

1. Choose exactly one `WHATSAPP_PROVIDER`: `meta`, `interakt`, or `twilio`.
2. For Meta, configure `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`, and `WHATSAPP_PHONE_NUMBER_ID`.
3. Call `GET /api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=TOKEN&hub.challenge=12345`. Expect plain text `12345`.
4. Repeat with a wrong token. Expect 403.
5. POST a signed Meta text payload or Interakt text payload to `/api/whatsapp/webhook`. Expect HTTP 200 with `queued=1`.
6. For Twilio, configure the inbound URL as `/api/v1/hr-bot/webhook` and send a sandbox message.
7. Open `/api/whatsapp/webhook/status`; confirm only presence flags are returned and no secret value appears.

## 39.2 Employee phone verification and isolation

1. Create Employee A with a unique E.164 phone and active organization membership.
2. Link or allow first verified phone match to create `whatsapp_users` with `employee_id`, `org_id`, `is_verified=true`.
3. Send `HELP` from A. Confirm the response greets A and the message row is scoped to A's organization.
4. Send from an unknown number. Confirm no HR data is returned and the response asks HR to link the number.
5. Set `opt_out=true`; retry a sensitive command. Confirm no employee data is returned.
6. Give Employee B a payslip and request it from A's number. Confirm A cannot retrieve B's payslip.

## 39.3 Shared-service parity

1. In the PWA record A's leave balance, then send `BALANCE`; all three buckets must match because both call `leave_snapshot()`.
2. Submit PWA leave and WhatsApp leave for overlapping dates. Confirm the second request is rejected by `submit_leave_request()`.
3. Publish a roster and compare PWA Shifts with WhatsApp `SHIFT`; both must match `employee_shifts()` output.
4. Submit equivalent PWA and WhatsApp complaints. Confirm both write only `hr_complaints` through `submit_grievance()`.
5. Confirm the webhook source contains no leave deduction, payroll calculation, shift selection, or complaint classification logic.

## 39.4 Commands and Hindi aliases

1. Test: `LEAVE 2026-09-10 fever`, `PAYSLIP April 2026`, `SHIFT`, `BALANCE`, `COMPLAINT ANON unsafe kitchen equipment`, `CAREER`, `HELP`.
2. Test Hindi aliases: `छुट्टी 2026-09-11 बुखार`, `वेतन अप्रैल 2026`, `पाली`, `बकाया`, `शिकायत रसोई सुरक्षित नहीं है`, `नौकरी`, `मदद`.
3. For every command verify a bilingual or Hindi-understandable response, correct domain record and no cross-employee data.
4. Test malformed dates/months, missing reasons, short complaints and unknown commands. Expect validation guidance, not a server error.

## 39.5 Message and audit persistence

1. Send `HELP` with provider message ID `IN-001`.
2. Confirm an `INBOUND` `whatsapp_messages` row contains phone, org, command, body, source, provider ID and processing status.
3. Confirm a separate `OUTBOUND` row contains the reply body, provider response ID and `twilio_status=sent`.
4. Confirm the inbound row's `response_sid` links to the outbound provider ID.
5. Force provider failure. Confirm an outbound row still exists with no fake provider ID and `twilio_status=failed`; inbound status becomes `FAILED`.
6. Send media without text and start a WhatsApp job application. Confirm both inbound and outbound legs are audited.
7. Submit leave, payslip and complaint commands. Confirm their domain rows retain `source=WHATSAPP` and inbound-message linkage.

## 39.6 Anonymous complaint protection

1. Send `COMPLAINT ANON manager threatened me during shift`.
2. Confirm `hr_complaints.employee_id IS NULL`, `is_anonymous=true`, a random `anonymous_token` exists, and the response contains only a shortened tracking ID.
3. Query through the masked complaint view as a normal manager. Confirm reporter identity is hidden.
4. Verify only the authorized legal/admin identity endpoint can disclose protected metadata and that access is audited.

## 39.7 Automated regression suite

```powershell
cd backend
python -m pytest tests/test_command_parser.py tests/test_hr_bot.py tests/test_whatsapp_webhook.py tests/test_whatsapp_message_audit.py tests/test_employee_self_service.py tests/test_leave_management.py tests/test_career_command.py -q
```

Expected: all command parsing, transport verification, employee isolation, shared-service parity, outbound audit and anonymous complaint tests pass.

---

# 40. India Employee Referral Program End-to-End

Use `docs/REFERRAL_TESTING.md` for the detailed procedure. The mandatory critical path is:

1. Employee saves a Razorpay-verified UPI ID.
2. Employee creates and shares a secure referral link over WhatsApp.
3. Candidate submits through the link; verify `source=REFERRAL_LINK` and referral/application linkage.
4. Recruiter moves that application through SHORTLISTED to HIRED.
5. Verify hire and 90-day retention timestamps are created automatically.
6. Before day 90 payout must fail; at/after day 90 the worker may create one Razorpay payout.
7. A queued payout remains pending; only a processed payout becomes `BONUS_PAID`.
8. Retry worker and manual payout concurrently; verify one payout reference and one paid timestamp.
9. Refer the same candidate/job from two employees; verify first-referrer credit is retained.
10. Verify own-UPI access, financial-role payout authorization, cross-org isolation, campaigns, badges, leaderboard and payroll sync.

The deprecated direct mark-paid endpoint intentionally returns HTTP 410.
# Latest Module Guides

- Hospitality AI Assistant audit: `docs/HOSPITALITY_AI_ASSISTANT_AUDIT.md`
- Hospitality AI Assistant manual tests: `docs/HOSPITALITY_AI_ASSISTANT_MANUAL_TESTING.md`
- Application-wide search audit: `docs/GLOBAL_SEARCH_AUDIT.md`
- Application-wide search manual tests: `docs/GLOBAL_SEARCH_MANUAL_TESTING.md`
