# Certification Management Audit

Audit date: 2026-08-28

## Coverage

| Capability | Status | Implementation | Remaining operational gap |
|---|---|---|---|
| FSSAI Licence | COMPLETE | Existing `fssai_certificates`, FSSAI API, encrypted S3 upload, verification, renewal and unified expiry worker | Issuer authenticity is recruiter-reviewed; no FSSAI registry API integration |
| Basic Food Hygiene | COMPLETE | Existing FSSAI flow plus unified employee compliance view | Same manual authenticity check |
| FoSTaC | COMPLETE | Existing FSSAI flow plus role requirement mapping | Same manual authenticity check |
| Fire Safety | COMPLETE | `certification_types`, `employee_certifications`, upload, review, expiry and renewal | Issuer authenticity is manual |
| First Aid | COMPLETE | General certificate workflow | Issuer authenticity is manual |
| Medical Fitness | COMPLETE | General certificate workflow | Medical document access must be limited to compliance-authorized users |
| Police Verification | COMPLETE | General certificate workflow | Police-provider API verification is not integrated |
| Certificate upload | COMPLETE | Private presigned PUT, PDF/JPEG/PNG/WebP, SSE-KMS or SSE-S3, `ap-south-1`, upload audit | Live AWS credentials and bucket policy are deployment prerequisites |
| Verification | COMPLETE | Pending, verified and rejected states; verifier, timestamp, notes and audit log | Manual review only |
| Expiry | COMPLETE | Effective status and daily worker; expired records are updated automatically | Celery beat and Redis must be running |
| Renewal | COMPLETE | General and FSSAI renewal lineage (`renewal_of`, `renewed_by`) | Renewal document still requires reviewer approval |
| Reminders | COMPLETE | Organization-configurable intervals, default 90/60/30/7/expired; SMS, WhatsApp or both; employee and manager | Live Twilio sender configuration required |
| Role requirements | COMPLETE | Mandatory/optional requirements scoped by organization, property and department; Employee 360 compliance result | Role matching currently uses exact normalized `users.job_title`; canonical role IDs should be populated where available |
| Employee self-access | COMPLETE | Employee may read their own certificate records and private document link | Upload/verification remains manager/compliance controlled |
| Tenant isolation | COMPLETE | Org/property-aware FastAPI authorization and RLS on all new tables | Must be verified after applying migration in the target Supabase project |

## Architecture

- Migration: `supabase/migrations/045_certification_management.sql`
- API: `backend/app/routers/certifications.py`
- FSSAI API: `backend/app/routers/fssai.py`
- Domain service: `backend/app/services/certification_service.py`
- Storage: `backend/app/services/s3_service.py`, `backend/app/services/fssai_s3_service.py`
- Worker: `backend/app/workers/certification_expiry.py`
- Scheduler: `backend/app/celery_app.py`
- UI: `frontend/src/pages/CertificationManager.tsx`
- Employee profile integration: `backend/app/services/employee_360_service.py`, `frontend/src/pages/Employee360.tsx`

## API Surface

- `GET /api/v1/certifications/types`
- `GET|POST /api/v1/certifications/requirements`
- `GET|PUT /api/v1/certifications/alert-settings`
- `POST /api/v1/certifications/employees/{employee_id}`
- `PATCH /api/v1/certifications/{certificate_id}/confirm-upload`
- `GET /api/v1/certifications/{certificate_id}/download-url`
- `PATCH /api/v1/certifications/{certificate_id}/verify`
- `GET /api/v1/certifications/employees/{employee_id}`
- `GET /api/v1/certifications/employees/{employee_id}/compliance`
- `GET /api/v1/certifications/expiring?days=90`
- Existing FSSAI endpoints now include `PATCH /certificates/{id}/verify` and `POST /certificates/{id}/renew`.

## Security Notes

- Documents are not exposed as public S3 URLs. Download links expire after five minutes.
- Storage keys are scoped by organization and employee; traversal keys are rejected.
- Full document access requires self-access or `compliance.read`; modifications require `compliance.manage`.
- RLS uses `current_user_org_id()`, `rbac_employee_access()` and the RBAC permission functions established by earlier migrations.
- Reminder delivery is idempotent per certificate, threshold, channel and recipient. Failed or skipped sends are upserted and may retry; successful sends do not repeat.

## Remaining Enhancements

1. Integrate official/approved issuer verification APIs when commercial contracts are available.
2. Replace exact job-title matching with canonical `job_role_id` on all employee assignments.
3. Add email as a third reminder channel if required.
4. Add bulk certificate import after defining a trusted source and validation format.

