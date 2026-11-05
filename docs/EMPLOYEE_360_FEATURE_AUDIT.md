# Employee 360 Feature Audit

Audit date: 2026-08-26  
Canonical employee key: `users.id`  
Pre-hire linkage: `candidates.user_id` (email/org fallback for legacy rows)

## End-to-End Coverage

| Section | Before | After | Existing entities/services reused | Remaining gap |
|---|---|---|---|---|
| Personal | DATABASE ONLY | COMPLETE | `users`, linked `candidates` | Employee self-edit workflow is not included. |
| Employment | PARTIAL | COMPLETE | `users`, `properties`, `property_departments`, `property_memberships` | Historical transfers before migration are not backfilled. |
| Financial | PARTIAL | COMPLETE | `employee_upi_details`, candidate CTC | Bank account management remains intentionally outside Employee 360. |
| Statutory | BACKEND ONLY | COMPLETE | `india_identity_verifications`, `epf_esic_registrations` | Full identifiers are intentionally never returned; edits remain in Compliance Center. |
| Documents | BACKEND ONLY | COMPLETE | `candidate_documents`, India-localized S3 | Malware scanning remains missing. |
| Certifications | PARTIAL | PARTIAL | `fssai_certificates` | Generic non-FSSAI certification taxonomy/renewal workflow is missing. |
| Performance | MISSING | PARTIAL | New `employee_performance_reviews` | Manager create API exists; review-form UI, calibration and goal workflow remain. |
| Attendance | PARTIAL | COMPLETE | `attendance_punches`, `attendance_daily_records`, corrections, existing `working_hours_compliance` and `v_employee_shifts` | Monthly export and offline punch queue remain. |
| Leave | COMPLETE | COMPLETE | `leave_balances`, `leave_requests`, WhatsApp HR bot | Multi-day request model and holiday calendar are still limited. |
| Payroll | PARTIAL | COMPLETE (read) | `payslips`, protected payroll permission | Monthly calculation/run workflow is implemented separately in migration 039 and `/payroll`. |
| Training | MISSING | PARTIAL | New `employee_training_records` | Assignment API and profile view exist; course catalog, enrollment UI, reminders and LMS integration remain. |
| Career | PARTIAL | PARTIAL | Candidate skills/work history and application history, internal job service | Promotion plan, succession plan, career preferences and mentor workflow are missing. |
| Disciplinary/HR events | MISSING | PARTIAL | New `employee_hr_events` | HR create API/profile view exist; investigation workflow, attachments and approval chain remain. |
| Lifecycle timeline | MISSING | PARTIAL | New `employee_lifecycle_events`; employment/performance/training/HR writes append events | Existing historical events are not automatically backfilled; leave/payroll/onboarding triggers remain to add. |

## Unified API and UI

- `GET /api/v1/employees/me/360`: employee self-service view.
- `GET /api/v1/employees/{employeeId}/360`: scoped manager/HR view.
- `PATCH /api/v1/employees/{employeeId}/employment`: authorized employment update and lifecycle entry.
- `POST /api/v1/employees/{employeeId}/performance`: performance record and lifecycle entry.
- `POST /api/v1/employees/{employeeId}/training`: training record and lifecycle entry.
- `POST /api/v1/employees/{employeeId}/hr-events`: confidential HR event and HR-only lifecycle entry.
- `/employee-profile`: self view.
- `/employees/:employeeId`: manager view protected by `employees.read`.

The response includes `visible_sections`. The frontend renders only sections the backend assembled; it does not calculate sensitive access from UI role names.

## Security and Isolation

- Employees can call only their own aggregate endpoint. A different employee ID returns 403 even if guessed.
- Managers require `employees.read`, organization match, property membership and department scope.
- Financial/payroll sections require self-view or `payroll.read`.
- Statutory sections require self-view or `compliance.read`; Aadhaar/PAN/EPF/ESIC values are masked before serialization.
- Documents require self-view or `documents.read`.
- Disciplinary events require `employees.manage` and are never included in employee self-view.
- Manager UPI values are masked; bank account number and IFSC are never returned by Employee 360.
- RLS mirrors server checks for the four new tables. Employee self-select applies only to performance/training and employee-visible lifecycle entries; HR events have no self policy.
- Service-role credentials are not used by Employee 360. Queries carry the caller JWT so Supabase RLS remains authoritative.

## Database Changes

Migration `035_employee_360.sql`:

- Adds employment metadata to `users`: employee code, title, employment type/status, joining date and manager.
- Adds `employee_performance_reviews`.
- Adds `employee_training_records`.
- Adds `employee_hr_events`.
- Adds `employee_lifecycle_events`.
- Adds scoped indexes and RLS policies.

No duplicate `employees`, payroll, attendance, leave, document, candidate or certification master table was created.

## Files

- `supabase/migrations/035_employee_360.sql`
- `backend/app/services/employee_360_service.py`
- `backend/app/routers/employees.py`
- `backend/tests/test_employee_360.py`
- `frontend/src/pages/Employee360.tsx`
- `frontend/src/AppRouter.tsx`
- `frontend/src/components/AppLayout.tsx`
- `MANUAL_TESTING_GUIDE.md`

## Priorities

- **P0**: Apply migration 035; restore Python environment; fix existing frontend syntax corruption; run authorization tests.
- **P1**: Commercial biometric vendor adapters, generic certifications, review/training management forms, lifecycle backfill/triggers.
- **P2**: Career development plans, succession, LMS integration, attendance summaries.
- **P3**: Predictive retention and performance intelligence after reliable operational data exists.
