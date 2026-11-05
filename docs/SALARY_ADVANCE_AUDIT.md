# Salary Advance Audit

Date: 2026-08-30

| Capability | Before | Current | Implementation |
|---|---|---|---|
| Employee request | COMPLETE | COMPLETE | Existing PWA request and canonical request table retained |
| Eligibility | MISSING | COMPLETE | Property policy, tenure, compensation limit and active-advance checks |
| Approval/rejection | PARTIAL | COMPLETE | RBAC, approved amount/months and immutable audit |
| Amount controls | PARTIAL | COMPLETE | Requested amount capped by gross-pay percentage and property maximum |
| Disbursement | MISSING | COMPLETE | Authorized disbursement reference and repayment schedule |
| Repayment | MISSING | COMPLETE | Installment ledger with scheduled/in-payroll/deducted states |
| Payroll deduction | MISSING | COMPLETE | Idempotent payroll adjustment per installment; posted only on finalization |
| Outstanding balance | MISSING | COMPLETE | Server-maintained balance and automatic REPAID closure |
| WhatsApp notifications | MISSING | COMPLETE CORE | Payroll-team request alert and employee decision/disbursement/deduction alerts |
| Audit trail | MISSING | COMPLETE | Immutable request, decision, disbursement and deduction events |

## Security

- Employees can create requests and read only their own request/repayment data.
- Employees receive no API that writes approval, disbursement, installment state or outstanding balance.
- Payroll managers require `payroll.manage` and property access for every mutation.
- The unique active-advance index prevents simultaneous requests and the repayment-to-adjustment unique index prevents duplicate payroll deductions.
- Approval and disbursement fail closed when the audit record cannot be written.
- Payroll calculations consume server-created repayment rows; the UI never supplies deduction amounts.

## Files

- `supabase/migrations/052_salary_advance_management.sql`
- `backend/app/services/salary_advance_service.py`
- `backend/app/routers/salary_advances.py`
- `backend/app/routers/employee_self_service.py`
- `backend/app/routers/payroll.py`
- `frontend/src/pages/SalaryAdvanceManagement.tsx`
- `frontend/src/pages/EmployeeApp.tsx`
- `backend/tests/test_salary_advance_service.py`

## Remaining Operational Gaps

- Actual bank/UPI disbursement remains an external finance operation; the system records its verified reference.
- Failed payroll recovery rescheduling and final-settlement recovery require an HR/payroll operating policy.
- WhatsApp delivery receipts depend on the configured provider webhook.
