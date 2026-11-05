# Job Management Feature Audit

Audit date: 2026-08-25

## Scope and architecture

The application uses the existing `jobs` table as the canonical vacancy record. Migration `030_job_management_completion.sql` extends that table; it does not introduce a competing job model. Jobs are tenant-owned through `org_id` and connect to canonical properties, property departments, hospitality role templates, users, applications, and candidates.

Primary implementation files:

- `supabase/migrations/030_job_management_completion.sql`
- `backend/app/routers/smart_recruitment.py`
- `backend/app/services/smart_recruitment_service.py`
- `frontend/src/pages/SmartRecruitment.tsx`
- `backend/tests/test_job_management.py`

## Feature coverage

| Capability | Status | Evidence and behavior |
|---|---|---|
| Job creation | COMPLETE | `POST /api/v1/recruit/jobs`; mobile-responsive create modal; creates draft and audit history. |
| Job editing | COMPLETE | `PATCH /api/v1/recruit/jobs/{id}`; edit modal covers assignments, requirements, compensation, benefits, vacancies, urgency and bilingual JD. |
| Close/reopen | COMPLETE | Dedicated close and reopen endpoints and card actions; reopen requires prior approval. |
| Duplication | COMPLETE | Duplicate endpoint copies the existing job into a new draft, records `duplicated_from_job_id`, and generates a new apply URL/QR. |
| Approval | COMPLETE | Draft submission plus approve/reject endpoints; only HR Manager/GM/Group Admin/Owner can decide; status history is retained. |
| Property assignment | COMPLETE | `jobs.property_id` FK with property-access validation and property-aware UI selector. |
| Department assignment | COMPLETE | `jobs.department_id` FK; API verifies the department belongs to the selected property. Property changes clear stale departments. |
| Hospitality role assignment | COMPLETE | `role_template_id` FK plus legacy role key; values validated against seeded `role_templates`. |
| Salary range | COMPLETE | INR min/max with API and database range constraints and salary period. |
| Annual CTC | COMPLETE | `ctc_min_inr`/`ctc_max_inr`, UI inputs, API checks and DB range constraint. |
| Experience | COMPLETE | Min/max years with 0-60 API bounds and DB ordering constraint. |
| Education | COMPLETE | Structured `education_level` field in create/edit/public job payload. |
| Skills | COMPLETE | Required/preferred JSON arrays; template defaults; create/edit forms. |
| Languages | COMPLETE | Required-language JSON array; create/edit/public job payload. |
| Shift requirements | COMPLETE | JSON object supports shift type and future schedule detail without schema churn. |
| Accommodation, food, transport | COMPLETE | Separate booleans shown in create/edit and included in generated JD context. |
| Vacancies | COMPLETE | Positive `openings_count`, synchronized to legacy `positions_available`. |
| Urgency | COMPLETE | NORMAL/HIGH/URGENT/CRITICAL plus legacy `is_urgent` synchronization. |
| Hiring manager/recruiter | COMPLETE | Both reference `users`; API prevents cross-organization assignment; create UI lists property members. |
| Applications | COMPLETE | `applications.job_id` FK added and existing candidate links backfilled. Legacy `candidates.applied_job_id` remains supported. |
| English/Hindi AI JD | COMPLETE | Claude generation with deterministic bilingual fallback; preview no longer creates a job. |
| Board-specific versions | COMPLETE | Generates and stores English/Hindi variants for Naukri, Apna, Indeed India, LinkedIn and WhatsApp. |
| External board publishing | NOT IMPLEMENTED | Copy is ready and stored, but posting requires provider credentials, provider APIs, retry workers and delivery-status webhooks. |

## Security and validation

- Organization isolation is enforced in API queries and jobs RLS.
- Property access is checked before assigning or moving a job.
- Department/property relationships are validated server-side.
- Hiring-manager and recruiter IDs must belong to the same organization.
- Job approval is enforced server-side; frontend button visibility is not the security boundary.
- Database constraints protect salary, CTC, experience, vacancy, urgency, and approval-state integrity.
- `job_status_history` is append-only through its API usage and has tenant-aware RLS.

## API inventory

- `POST /api/v1/recruit/jobs`
- `POST /api/v1/recruit/jobs/preview-jd`
- `GET /api/v1/recruit/jobs`
- `GET /api/v1/recruit/jobs/{jobId}`
- `PATCH /api/v1/recruit/jobs/{jobId}`
- `POST /api/v1/recruit/jobs/{jobId}/submit-approval`
- `POST /api/v1/recruit/jobs/{jobId}/approval`
- `POST /api/v1/recruit/jobs/{jobId}/close`
- `POST /api/v1/recruit/jobs/{jobId}/reopen`
- `POST /api/v1/recruit/jobs/{jobId}/duplicate`
- `POST /api/v1/recruit/jobs/{jobId}/regenerate-jd`
- `POST /api/v1/recruit/jobs/{jobId}/job-board-versions`
- `POST /api/v1/recruit/jobs/{jobId}/qr-code`
- `GET /api/v1/recruit/apply/job/{jobId}` (public, open approved jobs only)

## Remaining recommended enhancements

1. Add real Naukri/Apna/Indeed/LinkedIn publishing adapters and webhook-driven posting status.
2. Add approval notifications and optional multi-step approval policies for large hotel groups.
3. Add a dedicated history drawer in the UI for `job_status_history`.
4. Add manager/recruiter display-name joins to list responses instead of displaying stored identifiers in technical views.

