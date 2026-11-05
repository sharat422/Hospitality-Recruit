# Training and Career Feature Audit

Audit date: 2026-08-28

## Coverage

| Capability | Before | Current | Evidence / limitation |
|---|---|---|---|
| Training assignments | PARTIAL | COMPLETE | Existing `employee_training_records`; catalog assignment API added |
| Course catalog | MISSING | COMPLETE | `training_courses`, APIs, Learning & Career UI |
| Videos/content | DATABASE ONLY | PARTIAL | URL and delivery type supported; no transcoding, DRM or offline package |
| Quizzes | MISSING | COMPLETE | Sanitized question API, deterministic scoring and attempts |
| Certificates | PARTIAL | PARTIAL | Existing certificate URL and certification link retained; signed PDF issuance is pending |
| Completion tracking | PARTIAL | COMPLETE | Progress, activity, score, pass state and completion timestamp |
| Skills and gaps | PARTIAL | COMPLETE | Verified employee skills and pathway-based gap calculation |
| Career pathways | PLACEHOLDER/MOCK | COMPLETE | Configurable DB pathways; hard-coded WhatsApp helper remains a fallback |
| Promotion readiness | PARTIAL | COMPLETE | Performance + skills + courses + tenure; advisory and human-gated |
| Internal jobs | PARTIAL | COMPLETE | Existing `jobs` reused with PUBLIC/INTERNAL/BOTH visibility |
| Employee 360 | PARTIAL | PARTIAL | Summary tabs remain; full workflow is `/learning-career` |

## Reused architecture

- `employee_training_records` remains the single enrollment/completion ledger.
- `employee_performance_reviews` supplies performance evidence and the approved human outcome.
- `jobs` remains the only vacancy table; no duplicate internal-job table was created.
- `employee_certifications` remains the canonical certificate register.
- `career_service.py` remains the WhatsApp CAREER fallback where no pathway is configured.

## Added implementation

Migration `supabase/migrations/047_training_and_career.sql` adds normalized skills, course content, quizzes and attempts, course-skill mappings, pathway steps, employee plans, progress fields, and `jobs.visibility`. It is additive and does not rewrite users, candidates, jobs, applications, old training rows, reviews, or certificates.

API prefix `/api/v1/learning-career`:

- `GET/POST /courses`
- `POST /assign?course_id=...`
- `GET /my-learning`
- `PATCH /enrollments/{id}/progress`
- `GET/POST /enrollments/{id}/quiz`
- `GET/POST /pathways`
- `POST /pathways/{id}/steps`
- `POST /plans`
- `GET /employees/{id}/readiness`
- `GET /internal-jobs`

The `/learning-career` React page provides My Learning, Course Catalog, Skills & Gaps, Career Path, and Internal Jobs tabs.

## Security and decision controls

- Organization, property, department, and self-access are enforced by API RBAC and database RLS.
- Duplicate active course assignments are blocked by a partial unique index.
- Employees cannot modify another employee's enrollment.
- Quiz answer keys require `training.manage` and are omitted from employee API responses.
- Course completion upserts skill evidence instead of duplicating it.
- Readiness never modifies job title, salary, application, or employment status. `promotion_action_allowed` requires both all configured thresholds and an approved performance outcome.

## Remaining gaps

- Signed/revocable course certificate PDF generation.
- Private adaptive video streaming and offline learning packages.
- Visual manager builders for courses, quizzes, and pathways; configuration is API-first.
- Scheduled training reminders and escalation worker.
- DB-configured pathway lookup in the WhatsApp CAREER response before its fallback.
- Browser E2E tests after unrelated malformed legacy TypeScript files are repaired.
