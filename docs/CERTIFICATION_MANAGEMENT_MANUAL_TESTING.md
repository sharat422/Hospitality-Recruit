# Certification Management Manual Testing

## 1. Prerequisites

1. Apply migrations through `045_certification_management.sql` in order.
2. Start Redis, Celery worker, Celery beat, FastAPI and the React app.
3. Configure `AWS_REGION=ap-south-1`; for live uploads also set the S3 bucket and optional KMS key.
4. Configure Twilio SMS/WhatsApp credentials for live reminders. Without them, verify failed reminder records instead.
5. Create two organizations, an admin/compliance user, manager, employee, property, department and employee job title.
6. Sign in and copy the access token from the browser session. Open `/certifications`.

## 2. Taxonomy

1. Call `GET /api/v1/certifications/types`.
2. Confirm these active codes: `FSSAI_LICENSE`, `BASIC_FOOD_HYGIENE`, `FOSTAC`, `FIRE_SAFETY`, `FIRST_AID`, `MEDICAL_FITNESS`, `POLICE_VERIFICATION`.
3. Confirm FSSAI-managed types are not offered by the general certificate form.

## 3. Role Requirements

1. In Requirements, enter the employee's exact job title and select First Aid.
2. Mark it mandatory and create the requirement.
3. Repeat for Fire Safety and scope it to the employee's property.
4. Call `GET /api/v1/certifications/employees/{employeeId}/compliance`.
5. Confirm both requirements are missing and `compliant=false`.
6. Attempt the same requirement again; expect HTTP 409.
7. Change the employee to a different property; confirm the property-scoped requirement no longer applies.

## 4. General Certificate Upload

1. Enter the employee UUID, select First Aid, dates, number and a PDF.
2. Submit. Confirm the record is `PENDING_VERIFICATION` and the browser PUT succeeds.
3. Inspect the PUT request: region is `ap-south-1` and server-side-encryption headers are present.
4. Confirm `upload_confirmed_at`, `storage_key` and a `file_upload_audit_log` row exist.
5. Try an EXE file; expect client rejection or HTTP 400.
6. Request `GET /api/v1/certifications/{id}/download-url`; confirm a short-lived URL, not a permanent public URL.

## 5. Verification

1. As compliance manager, open the pending record and click Verify.
2. Confirm status, `verified_by`, `verified_at` and compliance audit log.
3. Upload another certificate and reject it with notes; confirm it does not satisfy role compliance.
4. Sign in as the employee; confirm own records/download work but verification returns 403.
5. Sign in as an unrelated employee; confirm another employee's record/download returns 403 or 404.
6. Use an admin from organization B; confirm organization A records are inaccessible.

## 6. FSSAI/Food Hygiene/FoSTaC

1. Create each certificate through the existing FSSAI form/API with a document.
2. Confirm the initial status is `PENDING_VERIFICATION`.
3. Verify through `PATCH /api/v1/fssai/certificates/{id}/verify` with `ACTIVE`.
4. Confirm each appears in the unified employee certificate list through candidate-to-employee mapping.
5. Reject one certificate and confirm it does not meet a mandatory role requirement.

## 7. Renewal

1. Click Renew on a general verified certificate and submit new dates/document.
2. Confirm the old record becomes `RENEWED`, the new record references `renewal_of`, and the new record waits for verification.
3. For FSSAI, call `POST /api/v1/fssai/certificates/{id}/renew` with the new expiry and document metadata.
4. Confirm the same lineage and verification behavior.
5. Confirm an old/rejected renewal is not counted as current role compliance.

## 8. Expiry and Configurable Reminders

1. Save intervals `90,60,30,7,0`, employee+manager enabled, channel BOTH.
2. Create verified certificates expiring in 90, 60, 30, 7 and 0 days, plus one yesterday.
3. Run `scan_certification_expiry()` from the worker or trigger the scheduled task.
4. Confirm one reminder per applicable recipient/channel and a `certification_reminders` row.
5. Confirm the 30-day record changes to `RENEWAL_DUE`; yesterday's changes to `EXPIRED`.
6. Run the worker again. Confirm successful reminders are not duplicated.
7. Force provider failure, rerun, and confirm the same unique reminder row is updated rather than duplicated.
8. Add a missing phone after a skipped send and rerun; confirm delivery can retry.
9. Change settings to `45,14,3,0`; create matching dates and verify the custom thresholds are used.

## 9. Manager Notification

1. Set `users.manager_id` for the employee and add phone numbers to both users.
2. Run a due reminder with manager notifications enabled.
3. Confirm both recipient records and messages.
4. Disable manager notifications and repeat with a different threshold; confirm employee only.

## 10. Employee 360 and UI

1. Open Employee 360 > Certifications.
2. Confirm general and FSSAI records appear once, with status and expiry.
3. Open `/certifications` at 360px width; confirm tabs, form, tables and actions remain usable without horizontal page overflow.
4. Confirm expired, renewal-due, verified and pending states have distinct labels.

## 11. Regression

1. Re-run existing FSSAI upload/download tests.
2. Verify KYC, Employee 360, onboarding certification tasks and India Compliance still load.
3. Verify candidate FSSAI records created before migration remain readable.
4. Verify no existing users, candidates, jobs, applications or properties were modified by migration 045.

