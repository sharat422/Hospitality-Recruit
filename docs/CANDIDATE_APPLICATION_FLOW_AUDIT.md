# Candidate Application Flow Audit

Audit date: 2026-08-26  
Scope: public India application flow, WhatsApp/QR entry, uploads, and candidate status.

## Coverage

| Capability | Classification | Verified implementation | Remaining gap |
|---|---|---|---|
| Mobile responsiveness | COMPLETE | `IndiaApplyForm.tsx` uses a 360px-safe single column, `max-w-sm`, 48px actions, numeric keyboards, and no fixed desktop layout. | Physical low-end Android validation remains a release test. |
| OTP authentication | COMPLETE | `/api/v1/recruit/apply/otp/send`, `/check`, `/verify`; normalized Indian phone; hashed OTP; expiry; three-attempt limit; one-time form token. | Production SMS requires valid Twilio credentials and migration 034. |
| Minimal entry fields | COMPLETE | Phone/OTP plus name, experience and city. Source is inferred from tracked links and only asked for unknown traffic. | Role-tier expansion is intentionally outside the entry-level flow. |
| Resume upload | COMPLETE | Optional post-submit PDF/DOCX/JPG/PNG upload, 5 MB limit, S3 `ap-south-1`, candidate resume link update. | Malware scanning is not integrated. |
| Supporting document upload | COMPLETE | Optional post-submit certificate/ID upload to canonical `candidate_documents`, token scoped to candidate/application. | Sensitive KYC documents should continue through the dedicated KYC portal, not this generic upload. |
| Hindi/English | COMPLETE | Explicit language switch on apply and status screens; bilingual OTP and workflow copy; language persisted on application. | Full translation catalog coverage is separate from this focused flow. |
| Low-bandwidth experience | PARTIAL | No media assets, compact API payloads, save-data/2G detection, offline warning, application submits before uploads. | No service worker/offline submission queue; OTP necessarily needs connectivity. |
| WhatsApp application | COMPLETE | Job detail returns a prefilled `APPLY <job UUID>` URL; Meta/Interakt and Twilio webhooks run a name/city/experience conversation and create canonical candidate/application records. | Provider templates and production webhook credentials require external setup. |
| QR-code application | COMPLETE | QR source scan is logged; distribution token is validated; source carries through application and hire attribution. | Print quality/device camera testing is manual. |
| Application status | COMPLETE | Unguessable tracking token; public portal; canonical 9-stage ATS timeline; legacy stage aliases; Hindi/English switch. | Recruiter stage updates must be timely for accurate status. |
| Approximately 60 seconds | COMPLETE BY DESIGN | Three short application fields after OTP; optional source and documents deferred; completion seconds stored for analytics. | Validate the p50/p90 with production telemetry after launch. |

## Data and Security

- Canonical tables remain `candidates`, `applications`, and `candidate_documents`; no duplicate candidate/application model was added.
- OTP values are SHA-256 hashed at rest. Migration 034 preserves legacy plaintext sessions only for their ten-minute lifetime.
- Post-submit uploads require both the unguessable tracking token and matching application ID. The security-definer RPC derives candidate and organization IDs server-side.
- Files use the existing India-localized S3 service (`ap-south-1`) and upload audit log.
- WhatsApp provider webhooks use `SUPABASE_SERVICE_ROLE_KEY` server-side. Meta HMAC is enforced when configured. This key must never be exposed to Vite/frontend variables.
- Existing permissive RLS in legacy migration `004_mobile_experience.sql` remains technical debt outside this focused change.
- Twilio inbound signature validation is not currently enforced by the legacy HR-bot webhook and remains a P0 production hardening item.

## Files

- `supabase/migrations/034_candidate_application_flow.sql`
- `backend/app/services/smart_recruitment_service.py`
- `backend/app/services/whatsapp_apply_service.py`
- `backend/app/routers/smart_recruitment.py`
- `backend/app/routers/whatsapp.py`
- `backend/app/routers/hr_bot.py`
- `backend/app/core/config.py`
- `backend/app/core/dependencies.py`
- `frontend/src/pages/IndiaApplyForm.tsx`
- `frontend/src/pages/CandidateStatusPortal.tsx`
- `backend/tests/test_candidate_application_flow.py`

## Known Repository Blockers

- The checked-in Windows virtual environment references a Python installation that no longer exists, so backend tests cannot run until the environment is recreated.
- The full frontend build is blocked by pre-existing syntax errors in `SchedulerDashboard.tsx`, `BillingDashboard.tsx`, `PricingPage.tsx`, and `queryConfig.ts`. The two changed candidate pages pass isolated TypeScript transpilation.
