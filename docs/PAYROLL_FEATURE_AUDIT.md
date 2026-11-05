# Payroll Feature Audit

## Production-readiness verdict

Before this change payroll was **PARTIAL / NOT PRODUCTION-READY**. The application stored manually supplied payslips, exposed them through WhatsApp, had an optional PDF generator and separate statutory calculators. It did not have payroll runs, attendance ingestion, approvals, immutable snapshots, CTC structures or statutory files. Referral payroll adapters are genuine adapter implementations but are unrelated to monthly salary payroll.

## Coverage

| Capability | Before | After |
|---|---|---|
| CTC | PARTIAL onboarding calculation | COMPLETE configurable compensation + snapshot |
| Basic/HRA/allowances/gross/net | Manual payslip fields | COMPLETE backend calculation |
| EPF/ESIC | Standalone calculators | COMPLETE configurable effective rules |
| Professional tax | State slab service | COMPLETE reused by payroll engine |
| TDS | Manual field | PARTIAL configured monthly input; no income-tax declaration engine |
| LOP | MISSING | COMPLETE from validated absence input |
| Overtime | Attendance calculated only | COMPLETE from validated overtime hours and configurable multiplier |
| Bonus/incentive/arrears | Bonus only | COMPLETE adjustment ledger |
| Mid-month joining | MISSING | COMPLETE calendar-day proration |
| Payslip PDF | PARTIAL optional fpdf/S3 | COMPLETE generation endpoint; dependency/storage still environment-dependent |
| Approval | MISSING | COMPLETE maker-checker workflow |
| Immutable snapshots | MISSING | COMPLETE hashes and DB mutation guards |
| EPF ECR | MISSING | COMPLETE data-file generation; validate against current EPFO utility before filing |
| ESIC file | MISSING | COMPLETE CSV data export; validate against current ESIC portal format before filing |
| Form 16 | MISSING | PARTIAL `FORM16_DATA` export only; official certificate must come from TRACES/authorized process |

## Security and accounting controls

- Every run is organization/property scoped through FastAPI authorization and RLS.
- Only `VALIDATED` attendance enters payroll. Payroll never validates attendance itself.
- The creator cannot approve their own run. Finalization requires approval.
- Rules, compensation, attendance and calculations are copied into immutable item snapshots with SHA-256 hashes.
- Finalized items and payslips reject update/delete at database level.
- Payslip access is self-only for employees and permission-scoped for payroll users.
- No Razorpay, payroll-provider or tax credentials are exposed to the frontend.

## Remaining gaps before production filing/payment

- Configure organization-specific rules, salary structures, PT state and actual payroll roles before use.
- Add investment declarations and an income-tax/TDS engine or integrate a certified tax provider.
- Validate EPFO/ESIC export formats against the portals' current schemas before filing.
- Integrate official Form 16/TRACES issuance; the application deliberately does not fabricate Form 16.
- Add bank advice/payment integration, reconciliation, fpdf2, private S3 configuration and signed-URL rotation.
- Add employee-level payroll item review UI and adjustment entry UI; current dashboard manages run lifecycle and exports.
