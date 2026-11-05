# Salary Advance Manual Testing

## Setup

1. Back up Supabase and apply migrations through `052_salary_advance_management.sql`.
2. Create Employee A with active property, joining date and monthly gross INR 30,000.
3. Create a property policy: tenure 90 days, maximum 50%, cap INR 20,000, maximum 6 months.
4. Prepare Employee, Payroll Manager, unrelated Property Manager and Group HR accounts.

## Eligibility and Request

1. Sign in as Employee A and call `GET /api/v1/salary-advances/eligibility`; expect eligible and maximum INR 15,000.
2. Request INR 15,001; expect HTTP 422. Request INR 10,000 over 3 months; expect PENDING.
3. Confirm immutable REQUESTED audit and payroll-team WhatsApp notification.
4. Submit another request while the first is active; expect HTTP 409/422.
5. Test an employee below 90 days and one without compensation; both must be ineligible with reasons.

## Authorization

1. As Employee A try to update `status`, `approved_amount_inr`, `outstanding_balance_inr` or repayment rows directly; RLS must deny it.
2. As Employee B request Employee A's ledger; expect 403/404.
3. As an unrelated Property Manager approve the request; expect 403.
4. As Payroll Manager for the correct property approve INR 9,000 over 3 months; expect APPROVED, audit and employee WhatsApp.
5. Retry approval; expect 409 and no duplicate audit decision.

## Disbursement and Ledger

1. Try to disburse a PENDING or REJECTED request; expect 409.
2. Disburse the approved request with a bank/UPI reference and next payroll month.
3. Confirm three installments totaling exactly INR 9,000, status REPAYING and outstanding INR 9,000.
4. Retry disbursement; expect 409 and no duplicate schedules.

## Payroll Integration

1. Create the due-month payroll run and calculate it twice.
2. Confirm exactly one DEDUCTION adjustment exists for the installment despite recalculation.
3. Confirm employee cannot edit the generated adjustment.
4. Submit and approve payroll using separate maker/checker users, then finalize.
5. Confirm installment becomes DEDUCTED, outstanding falls by that exact amount, an audit row is written, and WhatsApp states deduction and balance.
6. Repeat each month. After the last installment confirm outstanding INR 0, status REPAID and closed timestamp.

## Regression

1. Verify normal payroll bonus, arrear, LOP, EPF, ESIC, professional tax and payslip generation remain unchanged.
2. Verify PWA displays request status and outstanding balance on 360px viewport.
3. Verify leave, payslip, grievance and WhatsApp HR commands still operate.
