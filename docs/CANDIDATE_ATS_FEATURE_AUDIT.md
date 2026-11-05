# Candidate & ATS Feature Coverage Audit

**Audit date:** 25 August 2026  
**Scope:** Candidate records, applications, recruitment pipeline, search, bulk actions, interviews, and timeline.  
**Canonical records:** Existing `candidates` and `applications` tables are reused. Migration `032_candidate_ats_completion.sql` adds only missing columns and supporting records.

## Classification Key

- **COMPLETE:** Database, protected API, and usable UI or established integrated flow exist.
- **PARTIAL:** Core flow works but a documented enhancement remains.
- **BACKEND ONLY / UI ONLY / DATABASE ONLY:** Only that layer exists.
- **MOCK:** Integration deliberately uses a fallback or fixture.
- **MISSING / BROKEN:** No working end-to-end flow or an existing flow is unusable.

## Candidate Profile Coverage

| Capability | Status | Evidence | Notes / remaining gap |
|---|---|---|---|
| Candidate profile | COMPLETE | `candidates`; `GET/PATCH /api/v1/ats/candidates/{id}`; Candidates tab and profile modal in `SmartRecruitment.tsx` | Tenant-scoped by `org_id`. |
| Resume | COMPLETE | `candidates.resume_url`; AI resume upload/parser in `ai_screening.py`; profile Resume link | Parsing falls back when configured AI/storage providers are unavailable. |
| Phone and email | COMPLETE | `candidates.phone/email`; candidate directory and profile | Duplicate check normalizes Indian phone formatting and email case. |
| Location | COMPLETE | `location`, `state`, `city`; location filter | Free-text and India state/city values coexist for legacy compatibility. |
| Experience | COMPLETE | `years_experience`, `work_history`; UI and minimum-experience filter | Parsed and recruiter-editable API data. |
| Skills | COMPLETE | `parsed_skills`; AI parser/matching; skills filter and profile tags | Supports JSON array and legacy object shapes. |
| Languages | COMPLETE | `languages`; language filter and profile | Existing multilingual application flow populates this data. |
| Salary | COMPLETE | Existing `current_ctc`, `expected_ctc`; new `expected_salary_inr` with INR constraint | Legacy CTC retained; no duplicate salary table. |
| Notice period | COMPLETE | Existing `notice_period`; profile endpoint/UI | India application flow remains the main capture point. |
| Availability | COMPLETE | Existing `availability`; profile summary | Structured legacy JSON is preserved. |
| Source | COMPLETE | Candidate/application `source`, distribution and attribution IDs | Click → application → hire attribution is covered by distribution tests. |
| Referral | COMPLETE | Existing `referrals` and referral engines; profile aggregates referral records | Referral program remains independently managed. |
| Documents | COMPLETE | New `candidate_documents`; `POST /api/v1/ats/candidates/{id}/documents`; profile list | Stores metadata for files uploaded through existing S3/compliance flows. |
| Notes | COMPLETE | New `candidate_notes`; protected create endpoint; profile note composer | Supports private flag and optional application link. |
| Tags | COMPLETE | New `candidates.tags`; profile update, filter, and bulk tag endpoint | Tags are JSONB to avoid a duplicate taxonomy table. |
| Applications | COMPLETE | Existing canonical `applications`; profile aggregate; synchronized stage mutation | No candidate/application duplication introduced. |
| Interview history | COMPLETE | Existing `interviews`, `interview_slots`, `video_interviews`; profile aggregate | Supports both legacy scheduler and mounted engagement slot shapes. |

## Recruitment Pipeline

The canonical active sequence is:

`Applied → Screened → Shortlisted → Interview → Selected → Offer → Offer Accepted → Onboarding → Hired`

`Rejected` and `Withdrawn` are terminal outcomes and do not appear as active Kanban columns.

| Capability | Status | Evidence |
|---|---|---|
| Exact nine stages | COMPLETE | `candidate_ats_service.PIPELINE_STAGES`; migration check constraints; Smart Recruitment Kanban |
| Candidate/application synchronization | COMPLETE | ATS single and bulk stage APIs update both records and write `application_stage_history` |
| Stage timestamps | COMPLETE | Candidate and application timestamp columns; `stage_update()` |
| Kanban | COMPLETE | Smart Recruitment Pipeline tab; all nine columns; per-card movement |
| Candidate search | COMPLETE | `/api/v1/ats/candidates?search=`; Candidates tab debounced search |
| Filters | COMPLETE | Job, stage, source, location in UI; tags, skills, languages, minimum experience in API |
| Bulk actions | COMPLETE | Existing shortlist/reject/message actions plus ATS bulk stage/tag/note API |
| Duplicate detection | COMPLETE | `/candidates/{id}/duplicates`; exact normalized email/phone comparison within organization |
| Interview scheduling | COMPLETE | Mounted engagement interview slot/invite/confirm/reminder endpoints |
| Interview feedback | COMPLETE | `PATCH /api/v1/ats/interviews/{id}/feedback`; rating, notes, recommendation, competencies |
| Candidate timeline | COMPLETE | Aggregates stage history, interviews, and notes in timestamp order; profile UI |

## Files and Endpoints

### Database

- `supabase/migrations/001_init_schema.sql`: canonical candidates and jobs.
- `supabase/migrations/004_mobile_experience.sql`: canonical applications and video interviews.
- `supabase/migrations/032_candidate_ats_completion.sql`: missing profile columns, notes, documents, history, status constraints, interview feedback.

### Backend

- `backend/app/services/candidate_ats_service.py`: stages, filtering, normalization, duplicate detection.
- `backend/app/routers/candidate_ats.py`: ATS search/profile/update/notes/documents/duplicates/stages/bulk/feedback APIs.
- `backend/app/services/smart_recruitment_service.py`: existing Kanban and stage movement.
- `backend/app/routers/smart_recruitment.py`: existing jobs, pipeline, cards, bulk communication.
- `backend/app/routers/engagement.py`: interview slots, invitations, confirmations, reminders.
- `backend/app/routers/mobile_experience.py`: applications and async video interviews.
- `backend/app/routers/ai_screening.py`: resume parsing and AI screening.

### Frontend

- `frontend/src/pages/SmartRecruitment.tsx`: job management, nine-stage Kanban, candidate directory, search/filters, profile, resume, notes, documents, interviews, timeline.
- Existing mobile application, resume parsing, scheduling, and video interview pages remain connected to their feature routers.

## Security Review

- API queries derive organization from the authenticated Supabase user and constrain candidate/application access by `org_id`.
- New support tables use RLS and existing RBAC permission functions.
- Interview slot feedback verifies the slot's candidate belongs to the current organization before updating schemas without `org_id`.
- Duplicate results never cross organization boundaries.
- Document records contain metadata/storage keys; sensitive documents remain in existing protected S3/compliance storage.
- Frontend visibility is not treated as authorization; backend and RLS checks remain authoritative.

## Remaining Enhancements

These are not blockers for the requested ATS flow:

1. **Fuzzy duplicate suggestions:** current detection intentionally requires exact normalized phone or email. Name similarity and resume fingerprinting can be added with a review/merge workflow.
2. **Candidate merge:** duplicates are reported, but automatic merging is intentionally omitted to avoid destructive history changes.
3. **Saved searches:** filters work but cannot yet be saved per recruiter.
4. **Bulk action UI expansion:** backend supports stage/tag/note; the current Kanban exposes shortlist, reject, and messaging. A generic bulk drawer would improve discoverability.
5. **Legacy interview schema consolidation:** two historical `interview_slots` definitions remain in old migrations. Runtime compatibility is implemented, but a future clean installation should squash migrations into one canonical scheduling schema.

## Automated Coverage

`backend/tests/test_candidate_ats.py` covers stage order, contact normalization, filtering, duplicate detection, tenant isolation, single and bulk stage synchronization, history creation, tags, and feedback for both interview shapes.

