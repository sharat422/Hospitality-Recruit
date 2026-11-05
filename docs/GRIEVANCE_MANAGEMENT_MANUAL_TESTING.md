# Grievance and POSH Manual Testing

## Setup

1. Back up Supabase and apply migrations through `051_grievance_management.sql`.
2. Prepare Employee A, Employee B, General Manager, HR Manager, Group HR and Owner accounts.
3. Prepare one user assigned as POSH Committee and one unassigned HR Manager.

## Submission and References

1. In Employee PWA submit a named grievance. Confirm `employee_id` is Employee A and a unique ticket is returned.
2. Submit an anonymous grievance. Confirm `employee_id IS NULL`, `phone IS NULL`, random token exists and only the token can track status.
3. Send `COMPLAINT manager threatened me during shift` through WhatsApp (anonymous is default).
4. Confirm `hr_complaints` has no phone/employee ID and `whatsapp_messages` stores `ANONYMOUS`, `[REDACTED ANONYMOUS COMPLAINT]`, no employee link and no WhatsApp-user link.
5. Submit POSH through PWA. Confirm `complaint_type=POSH`, `confidentiality_level=RESTRICTED`, category HARASSMENT and severity HIGH or CRITICAL.

## Confidential Access and Escalation Attacks

1. As General Manager call `GET /api/v1/grievances/cases`; expected empty unless explicitly assigned.
2. Directly query `hr_complaints` with the same JWT; expected no raw rows.
3. As unassigned HR Manager attempt a known grievance UUID and POSH UUID; expected HTTP 404.
4. As Group HR list cases; grievance metadata is visible, POSH metadata is absent until assignment.
5. Assign an HR caseworker to a grievance and POSH Committee member to POSH.
6. Confirm each sees only assigned cases. Assigning TRIAGE to POSH must return HTTP 422.
7. Attempt reporter identity access without `can_view_identity`; expected HTTP 403. Grant it, provide a 10+ character purpose and retry.
8. Confirm the identity access audit row exists before identity data is returned.

## Fail-Closed Audit

1. Temporarily deny INSERT on `complaint_access_audit` for the test user.
2. Open an assigned case or download evidence.
3. Expected HTTP 503 and no sensitive payload or download URL.
4. Restore INSERT and verify every case view, evidence upload/download, assignment, investigation update, escalation and resolution creates an audit row.

## Investigation and Evidence

1. Try to start an investigation with an unassigned investigator; expect HTTP 422. Assign the user as INVESTIGATOR, POSH_COMMITTEE or LEGAL, then start it with title and scope.
2. Confirm complaint status `UNDER_REVIEW` and investigation `IN_PROGRESS`.
3. Add a text statement and verify chain of custody contains collector and timestamp.
4. Request a PDF/image evidence upload URL. Confirm key starts `grievance-evidence/{org}/{complaint}/`, region `ap-south-1`, private encryption headers and five-minute expiry.
5. Attempt a storage key belonging to another case; expected HTTP 422.
6. Download evidence with a purpose. Confirm short-lived private URL and audit entry.

## Escalation, Resolution and POSH

1. Escalate a grievance with target, priority and reason. Confirm both escalation history and case status.
2. Complete investigation findings and recommendations.
3. Resolve with structured outcome, 20+ character summary, corrective actions and appeal deadline.
4. Attempt POSH resolution as HR caseworker; expected HTTP 403.
5. Resolve as explicitly assigned POSH Committee or Legal member; expected success and immutable resolution record.
6. Call the legacy HR Bot resolve endpoint; expected HTTP 410 directing callers to the audited workflow.

## Reporter and Regression Tests

1. Named reporter can see only their base case, not investigation notes, evidence or member identities.
2. Anonymous reporter can track only with the random token and cannot retrieve complaint text or identity.
3. Verify PWA and WhatsApp still call the shared `submit_grievance` service.
4. Verify leave, payslip, shift, payroll, employee profile and WhatsApp HELP continue to work.
