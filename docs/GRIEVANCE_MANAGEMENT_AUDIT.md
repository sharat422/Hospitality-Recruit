# Grievance and POSH Management Audit

Date: 2026-08-30

## Coverage

| Capability | Before | Current | Evidence |
|---|---|---|---|
| HR complaints | PARTIAL | COMPLETE | Shared PWA/WhatsApp submission and restricted case API |
| Anonymous complaints | PARTIAL / LEAK RISK | COMPLETE | No employee ID or phone; transport log body/identity redacted |
| Complaint reference | COMPLETE | COMPLETE | Unique `HR-YYYYMMDD-XXXXXX` ticket and anonymous token |
| Confidential access | BROKEN | COMPLETE | Complaint-level membership, POSH committee roles and strict RLS |
| Investigation | MISSING | COMPLETE | Scope, investigator, status, findings and recommendations |
| Evidence | MISSING | COMPLETE | Text/file evidence, hashes, chain of custody and encrypted India S3 upload |
| Escalation | PARTIAL | COMPLETE | Immutable escalation record plus case status update |
| Resolution | PARTIAL | COMPLETE | Structured outcome, corrective actions, approval and appeal deadline |
| POSH workflow | PARTIAL | COMPLETE CORE WORKFLOW | Restricted committee assignment, investigation and committee/legal resolution |
| Audit logs | PARTIAL / FAIL OPEN | COMPLETE CORE | Case-detail, evidence, identity and workflow actions are purpose-bound and fail-closed; metadata queue reads are deliberately content-free |

## Critical Findings Corrected

1. Earlier `hr_complaints` policies allowed anyone with broad `complaints.read` to query raw complaint content. Normal General Managers inherited that permission.
2. The legacy masked view could execute with view-owner privileges instead of caller RLS.
3. Identity access continued when audit insertion failed.
4. Anonymous complaints stored the reporter phone, and anonymous WhatsApp text/phone linkage remained in message logs.
5. The old resolve endpoint bypassed investigation, structured outcome and access auditing.

Migration 051 replaces these paths. Normal managers receive no case content unless explicitly assigned. POSH access always requires a committee, investigator, legal or auditor assignment. Identity access requires a separate `can_view_identity` grant.

## Architecture

- `hr_complaints` remains the canonical complaint record used by PWA and WhatsApp.
- `complaint_case_members` grants complaint-specific roles.
- `complaint_investigations`, `complaint_evidence`, `complaint_escalations` and `complaint_resolutions` extend the canonical case.
- `complaint_access_audit` is immutable access evidence. Sensitive reads fail with HTTP 503 if audit writing fails.
- Evidence objects use encrypted private S3 in `ap-south-1` and five-minute upload/download URLs.
- Legacy `employee_complaints` remains unused database-only history and should not receive new writes.

## Files

- `supabase/migrations/051_grievance_management.sql`
- `backend/app/services/grievance_service.py`
- `backend/app/routers/grievance_management.py`
- `backend/app/services/employee_self_service.py`
- `backend/app/services/hr_bot_service.py`
- `backend/app/services/s3_service.py`
- `frontend/src/pages/GrievanceManagement.tsx`
- `backend/tests/test_grievance_management.py`

## Remaining Operational Gaps

- Tenant administrators must configure the legally constituted POSH Internal Committee and escalation contacts.
- File malware scanning and legal-hold export are deployment integrations.
- WhatsApp delivery receipts for case updates are not part of the investigation workflow.
- Appeal review is represented by a deadline but a separate appeal-case workflow is not implemented.
- Statistical grievance reporting must remain aggregate-only and is not included in this release.
- The case queue exposes restricted metadata only and does not create one audit row per listed case; opening any case content is purpose-bound and audited.
