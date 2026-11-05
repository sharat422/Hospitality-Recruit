# DPDP Privacy Audit

Audit date: 2026-08-28

This audit covers the India Digital Personal Data Protection Act workflow. It
does not treat GDPR, CCPA, I-9, EEO, or Fair Workweek implementations as DPDP
substitutes.

## Feature Coverage

| Requirement | Status | Evidence | Remaining gap |
|---|---|---|---|
| Consent | COMPLETE | One immutable `dpdp_consent_records` event per decision | Legal must approve production notice text |
| Consent purpose | COMPLETE | Seven separate purpose codes; one toggle/request, no bundling | Purpose catalogue requires change control |
| Consent version | COMPLETE | `consent_text_version` and sequence metadata | Version bump is currently a release process |
| Timestamp/evidence | COMPLETE | Timestamp, IP, user agent, mechanism, fiduciary and region | Reverse-proxy trusted-IP configuration is deployment work |
| Withdrawal | COMPLETE | New withdrawal event, audit row and retention action | Required core-service withdrawal ends service and needs support procedure |
| Data access | COMPLETE | Token-authenticated `/privacy-centre/{token}/data-access`; masked KYC and no storage keys | Machine-readable JSON only; PDF export is optional |
| Erasure | COMPLETE with statutory carve-outs | App data anonymisation, S3 deletion, KYC cleanup, evidence manifest | Backup/provider deletion remains an operational runbook |
| Retention | COMPLETE engine | Effective schedule, document classification, legal holds, action ledger and daily worker | Legal periods must be reviewed when Indian rules change |
| Audit trail | COMPLETE | Consent, access workflow, erasure, hold, upload and retention deletion evidence | Long-term audit export/monitoring is operational |
| Privacy Center | COMPLETE | Public token portal, bilingual purposes, consent, requests and retention explanation | Brand-specific grievance officer details should be configurable |
| Secure documents | COMPLETE for application paths | Private India S3, short-lived URLs, SSE-KMS/SSE-S3, scoped keys, upload audit | Bucket policy/KMS rotation must be enforced in AWS IaC |
| Aadhaar/PAN masking | COMPLETE | Aadhaar last four only; PAN `ABCDE****F`; DB constraints | Migrations 043 and 044 must be applied |

## Existing Architecture

- API: `backend/app/routers/dpdp.py` and India compatibility endpoints in
  `backend/app/routers/india_compliance.py`.
- Services: `dpdp_service.py`, `india_compliance_service.py`, `s3_service.py`,
  `data_localization.py`.
- UI: `PrivacyCenter.tsx` for candidates and `DPDPPrivacyCenter.tsx` for admins.
- Database: migrations 014, 018, 019, 029, 043 and 044.
- Worker: `app.workers.dpdp_retention.process_dpdp_retention`, daily 09:30 IST.

## Implemented During This Audit

1. Added `dpdp_retention_actions`, effective retention rules and document-level
   `retention_until`, `legal_hold`, `legal_hold_basis`, region and encryption
   metadata.
2. Replaced blanket document erasure with a retention plan. EPF/UAN, ESIC,
   Form 16/PAN, Professional Tax and legally held medical records are retained;
   ordinary recruitment documents are erased.
3. Added a legal-hold API and a preview endpoint showing retain/delete decisions.
4. Added daily deletion for expired, non-held documents with S3 deletion,
   status update, action evidence and compliance audit logging.
5. Added candidate data-access JSON with masked Aadhaar/PAN and no storage keys.
6. Added encrypted, private candidate-document upload URLs. Arbitrary public
   document URLs are rejected.
7. Added explicit encryption to resume, FSSAI and payslip S3 writes. FSSAI
   records now store private `s3://` references and use presigned downloads.
8. Added erasure manifests and hardened DPDP RLS in migration 043.

## Retention Decisions

| Data category | Default action | Retention |
|---|---|---|
| Recruitment/application/interview data | Anonymise/delete after purpose period or approved erasure | 1 year reference rule |
| Marketing and third-party sharing | Schedule removal on withdrawal | Immediate |
| AI screening/profiling | Anonymise after purpose period | 1 year |
| EPF/UAN | Legal hold | 8 years |
| ESIC | Legal hold | 8 years |
| PAN/Form 16 | Legal hold; full PAN is never exposed | 8 years |
| Professional Tax | Legal hold | 5 years |
| Medical/occupational health | Legal hold only when applicable law requires it | Rule-specific |
| Ordinary resume/supporting document | Delete on approved erasure | No statutory hold |

These are application defaults, not legal advice. The active rows in
`dpdp_retention_schedule` are the governed reference and must be reviewed by
the organisation's DPO/legal adviser.

## Security Notes

- `SUPABASE_SERVICE_ROLE_KEY` is backend/worker only.
- All candidate document keys include organisation and candidate IDs.
- Download links are short-lived; the S3 bucket must block public access.
- `AWS_REGION` is hard-validated as `ap-south-1`.
- Set `AWS_KMS_KEY_ID` for customer-managed encryption; otherwise SSE-S3 AES256
  is required on writes.
- Erasure does not remove statutory contribution/payroll evidence before its
  legal period expires.

## Remaining Priorities

P0: apply migrations 043/044; configure private S3 block-public-access, KMS and
service-role worker credentials.

P1: obtain legal approval for all retention periods and notice version `v2.0`;
configure branded grievance officer details; monitor worker failures.

P2: add signed PDF data-access export and automated backup-deletion evidence.

## Verification Status

- Python syntax compilation: passed.
- Pure retention classification smoke test: passed (Form 16 retained to 2034;
  resume erasable).
- Pytest execution: blocked because the checked-in `backend/venv` references a
  removed Python executable and the bundled runtime does not contain pytest.
  Regression tests were added to `test_india_compliance_hardening.py` and must
  run after recreating the environment.

