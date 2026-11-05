# Employee Exit Management Audit

Date: 2026-08-30

## Coverage

| Capability | Before | Current | Evidence |
|---|---|---|---|
| Resignation | DATABASE FRAGMENT | COMPLETE | Employee PWA and API create one scoped exit case |
| Notice period | PARTIAL | COMPLETE | Requested/approved dates, days, waiver and acknowledgement |
| Exit interview | MISSING | COMPLETE | Optional ratings, reasons, feedback, recommendation and contact consent |
| Exit reason | PARTIAL | COMPLETE | Structured primary reason plus details and destination fields |
| Clearance | MISSING | COMPLETE | Department, IT, finance, payroll, accommodation, security, uniform and documents |
| Final settlement | MISSING | COMPLETE | Server calculation, approval/payment workflow and immutable paid snapshot |
| Experience letter | MISSING | COMPLETE (HTML artifact) | Escaped, hashed and persisted employee document |
| Rehire eligibility | PARTIAL | COMPLETE | Exit decision, turnover history and alumni profile |
| Alumni database | MISSING | COMPLETE | Property-scoped alumni registry with contact consent |
| Lifecycle timeline | PARTIAL | COMPLETE FOR EXIT | Resignation, notice and exit completion append existing Employee 360 events |

## Existing Components Reused

- `users` remains the canonical employee record; `employment_status` becomes `ALUMNI` at completion.
- `employee_lifecycle_events` remains the canonical Employee 360 timeline.
- `employee_turnover_history` remains the normalized resignation/termination history.
- `employee_compensation_structures` supplies monthly gross for settlement calculation.
- Existing RBAC permissions and `rbac_employee_access` enforce organization, property and department scope.
- Existing onboarding, applications, candidate ATS, performance and transfer events form the earlier lifecycle stages.

## Complete Lifecycle Mapping

1. Recruitment: candidate and application records.
2. Hire: application `HIRED` transition.
3. Onboarding: India onboarding flow and checklist.
4. Employment: `users` Employee 360 record.
5. Promotion: performance outcome and `PROMOTION` lifecycle event.
6. Transfer: property membership/employment update and lifecycle event.
7. Resignation: `employee_exit_cases` submission.
8. Exit: notice, interview, clearance, settlement and documents.
9. Alumni: employment status update, turnover record and `employee_alumni_profiles`.

## Security and Integrity

- Employees can submit and read only their own exit case/interview/documents.
- HR actions require `employees.manage`; settlement approval/payment additionally requires `payroll.manage`.
- Property and department scope is checked server-side and by RLS.
- Paid final-settlement snapshots cannot be updated or deleted.
- Letter content is HTML-escaped and hashed.
- Alumni contact requires explicit `consent_to_contact`; no automatic outreach is performed.

## Files

- `supabase/migrations/050_employee_exit_management.sql`
- `backend/app/services/employee_exit_service.py`
- `backend/app/routers/employee_exit.py`
- `frontend/src/pages/EmployeeExitManagement.tsx`
- `frontend/src/pages/EmployeeApp.tsx`
- `backend/tests/test_employee_exit.py`

## Remaining Gaps

- Experience letters are persisted as secure HTML artifacts; PDF rendering/e-signing and S3 upload are deployment enhancements.
- Bank payment is recorded by reference; direct bank/UPI payroll disbursement is not automated.
- Clearance owners are not automatically notified over WhatsApp.
- Exit interview aggregate analytics and alumni re-engagement campaigns are not included.
- Existing employees are not retroactively backfilled into lifecycle history.
