# DPDP Privacy Manual Testing

Use fake candidates and provider-approved test identifiers only.

## 1. Setup

1. Apply migrations through `044_dpdp_retention_enforcement.sql` in order.
2. Configure a private S3 bucket in `ap-south-1`; enable block-public-access.
3. Set backend-only `SUPABASE_SERVICE_ROLE_KEY` and optional `AWS_KMS_KEY_ID`.
4. Start FastAPI, React, Redis, Celery worker and Celery Beat.
5. Create users with `compliance.read`, `compliance.manage`, candidate-self and
   a user in another organisation.

## 2. Purpose-Specific Consent

1. Call `GET /api/v1/dpdp/purposes`; expect seven independent purposes.
2. Grant `MARKETING` with `POST /api/v1/dpdp/consent`.
3. Confirm one DB row contains purpose, boolean decision, text version,
   timestamp, IP, user agent, mechanism, fiduciary and `ap-south-1`.
4. Confirm no other purpose changed.
5. Withdraw `MARKETING`; verify a new immutable event and a pending retention
   action scheduled immediately.
6. Try withdrawing required `RECRUITMENT_DATA`; expect rejection and no mutation.

## 3. Privacy Center

1. Issue a token using `POST /api/v1/dpdp/privacy-centre/token`.
2. Open `/privacy-centre/<token>` on a mobile viewport.
3. Verify English/Hindi purpose text, current decisions, request history,
   grievance contact and India data region.
4. Toggle one optional purpose and reload; verify only that purpose changed.
5. Test an expired/invalid token; expect HTTP 401.

## 4. Candidate Data Access

1. Call `GET /api/v1/dpdp/privacy-centre/<token>/data-access`.
2. Verify candidate, applications, document metadata, KYC status and consents.
3. Confirm the response contains no `storage_key`, provider token, AWS secret,
   12-digit Aadhaar or full PAN.
4. Confirm Aadhaar resembles `XXXX XXXX 1234` and PAN `ABCDE****F`.
5. Use another candidate's token and confirm no cross-candidate data appears.

## 5. Secure Document Upload

1. Request `POST /api/v1/ats/candidates/<id>/documents/upload-url`.
2. Confirm region `ap-south-1`, five-minute expiry, candidate-scoped storage key
   and SSE header (`AES256` or `aws:kms`).
3. PUT the file with every returned `upload_headers` value.
4. Register metadata using the issued storage key; verify `file_url` is null.
5. Try an arbitrary HTTPS URL or another candidate's key; expect HTTP 400.
6. Download only through an authenticated short-lived URL; direct public access
   to the bucket must return AccessDenied.

## 6. Retention Plan and Legal Hold

1. Add documents typed `RESUME`, `FORM_16`, `ESIC`, `EPF_UAN` and `MEDICAL`.
2. Call `GET /api/v1/dpdp/retention-plan/<candidate_id>`.
3. Expect RESUME=DELETE; Form 16/ESIC/EPF=RETAIN with law and date.
4. Put the resume on hold with
   `PATCH /api/v1/dpdp/documents/<id>/legal-hold` and a reason.
5. Re-run the plan; expect the resume retained.
6. Release the hold and verify both hold/release action-ledger rows.
7. Attempt hold changes from another organisation; expect 404/no mutation.

## 7. Erasure With Statutory Retention

1. Create application PII, resume, Form 16, EPF/ESIC/PT records and KYC sessions.
2. Submit an erasure request in Privacy Center; verify WhatsApp acknowledgement
   and the 30-day deadline.
3. Preview the retention plan before approval.
4. Process COMPLETE as `compliance.manage`.
5. Confirm candidate PII is anonymised, application form data cleared, KYC
   references cleared and ordinary resume object deleted.
6. Confirm Form 16/EPF/ESIC/PT evidence remains and has legal basis/retention.
7. Inspect `erasure_manifest`, storage result and `dpdp_retention_actions`.
8. Reprocess the request; expect HTTP 409.
9. Reject a separate request without a legal reason; expect HTTP 422.

## 8. Scheduled Retention Worker

1. Create an ordinary document with `retention_until` yesterday and no hold.
2. Create another expired document with `legal_hold=true`.
3. Invoke `app.workers.dpdp_retention.process_dpdp_retention`.
4. Confirm only the non-held S3 object is deleted and status becomes ERASED.
5. Confirm action and `DPDP_RETENTION_DOCUMENT_DELETED` audit rows.
6. Run again; expect no duplicate deletion.
7. Confirm Celery Beat schedules it daily at 09:30 IST.

## 9. RLS and Privilege Escalation

1. Candidate-self: read own consent/access data; cannot process requests.
2. `compliance.read`: view records/plan; cannot set holds or complete erasure.
3. `compliance.manage`: manage only its organisation.
4. Replace candidate/document/request IDs with another organisation's IDs on
   every endpoint; expect 404/403/no rows and no mutation.
5. Verify anon users can access only a valid privacy token surface.

## 10. Automated Tests

After recreating the backend environment:

```powershell
cd backend
python -m pytest tests/test_dpdp.py tests/test_data_localization.py `
  tests/test_india_compliance_hardening.py -q
```

Then run the complete backend suite and the frontend production build.
