# Onboarding Feature Audit

Audit date: 2026-08-28. Canonical records are `onboarding_flows` and `onboarding_tasks`; this implementation does not create a second onboarding system.

## Coverage

| Capability | Status | Existing implementation | Remaining production dependency |
|---|---|---|---|
| Offer and offer acceptance | COMPLETE | ATS application stages, offer timestamps, appointment letter generation, migration 040 offer-acceptance trigger | Apply migration 040 |
| Appointment letter | COMPLETE | `appointment_letters`, HTML generation, stored CTC snapshot, `/appointment-letter` APIs | Configure private PDF storage for production |
| Document collection | COMPLETE | Checklist document tasks, candidate document records, task document URLs | Configure S3 compliance bucket and retention policy |
| KYC | COMPLETE | Aadhaar OTP, PAN, DigiLocker and India KYC manager; onboarding KYC task | Live Surepass/DigiLocker credentials |
| eSign | PARTIAL | Provider adapter, request/status storage and demo adapter | Contract and credentials for Digio/Leegality/SignDesk |
| PF and ESIC | COMPLETE | PF Form 2 and ESIC declaration records/APIs; statutory onboarding tasks | Employer establishment codes and production filing process |
| Certifications | COMPLETE | FSSAI/certification services and checklist stage | Live S3 and certificate verification operations |
| Payroll setup | COMPLETE | Payroll checklist plus canonical compensation/payroll engine | Payroll administrator configuration |
| Manager assignment | COMPLETE | Persisted `manager_id`, same-tenant validation, manager name/phone snapshot | Assign managers in property data |
| Joining date | COMPLETE | Persisted joining date, assignment API, due-date calculation | None |
| Onboarding checklist | COMPLETE | Configurable weighted tasks, stage progress and task completion API | None |
| Pre-boarding | COMPLETE | Six-message India sequence, scheduling and due-message sender | Configure a scheduler to call due-message sender |
| WhatsApp reminders | PARTIAL | Message persistence, WhatsApp gateway and due-send endpoint exist; offer acceptance queues a welcome message | Meta/Interakt credentials and production periodic scheduler |
| Completion | COMPLETE | Weighted percentage, per-stage percentage and automatic completion timestamp | None |
| Ghosting risk | COMPLETE | Explainable deterministic score/level/signals; no automated hiring decision | Schedule recalculation for inactive flows |
| Scoped templates | COMPLETE | Organization/property/department/role precedence, template API and UI | Replace UUID text fields with selectors as a UX enhancement |
| Automatic start | COMPLETE | Database trigger on transition to `OFFER_ACCEPTED`; unique application index prevents duplicate flows | Apply migration 040 |

## End-to-End Flow

1. Recruiter changes an application to `OFFER_ACCEPTED` using the ATS.
2. `trg_application_offer_onboarding` selects the most specific active template.
3. One flow is created for the application and template tasks are expanded with joining-relative due dates.
4. A welcome WhatsApp message is queued when the candidate has a phone number.
5. HR assigns the manager/joining details, generates the appointment letter and initiates eSign.
6. Candidate/HR complete KYC, documents, certifications, PF/ESIC and payroll tasks.
7. Task completion recalculates weighted completion; the risk endpoint persists explainable outreach signals.
8. When all mandatory tasks are complete, the flow becomes `completed` with `completed_at`.

## Security

- Template, flow and task RLS is tenant scoped and respects property and department access.
- Template mutation and flow/task management require `employees.manage`; reads require `employees.read`.
- Manager assignment rejects a manager outside the organization.
- `application_id` uniqueness provides idempotency across repeated stage writes.
- Ghosting risk is advisory. It cannot reject, withdraw, hire or alter an application stage.
- Aadhaar/PAN data remains in the India compliance subsystem; onboarding stores task state, not full identity numbers.

## Files

- `supabase/migrations/027_india_onboarding.sql`: existing core flow, tasks, letters, PF/ESIC and pre-boarding.
- `supabase/migrations/040_onboarding_orchestration.sql`: scoped templates, automatic start, RLS and risk fields.
- `backend/app/services/india_onboarding_service.py`: letters, statutory forms, checklist and WhatsApp sequence.
- `backend/app/services/onboarding_orchestration_service.py`: template precedence, weighted progress and risk.
- `backend/app/routers/india_onboarding.py`: onboarding, template, assignment and recalculation APIs.
- `frontend/src/pages/IndiaOnboarding.tsx`: dashboard, risk indicator, letter/pre-boarding and template UI.
- `backend/tests/test_onboarding_orchestration.py`: deterministic service coverage.

## Known Gaps

- Live Aadhaar eSign is provider-dependent; the demo adapter is not production eSign.
- Message dispatch needs an external scheduler/worker deployment and a configured WhatsApp provider.
- Appointment-letter PDF archival requires private India-region storage configuration.
- Template scope inputs currently accept UUIDs; searchable property/department/role selectors are a P2 usability improvement.
