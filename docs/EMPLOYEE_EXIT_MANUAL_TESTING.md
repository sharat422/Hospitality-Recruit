# Employee Exit Management Manual Testing

## Setup

1. Back up Supabase and apply migrations through `050_employee_exit_management.sql` in order.
2. Prepare an Employee with property, department, manager, joining date and active compensation.
3. Prepare HR Manager (`employees.manage`) and payroll approver (`payroll.manage`) accounts scoped to the same property.

## Employee Resignation

1. Sign in as Employee and open `/employee-app` → Help.
2. Enter last working date, reason and optional details; submit.
3. Expected: one `SUBMITTED` case and `RESIGNATION_SUBMITTED` Employee 360 timeline entry.
4. Submit again; expected HTTP `409` and no duplicate open case.
5. Attempt to specify another employee ID through the API; expected authorization failure unless the caller is scoped HR.

## Notice and Clearance

1. As HR Manager open `/employee-exit`, select the case and acknowledge it.
2. Set approved last day, 30-day notice and rehire decision.
3. Expected: status `NOTICE_PERIOD`, default clearance checklist and timeline event.
4. Mark each item cleared or not applicable. Set one to blocked with an amount due.
5. Attempt exit completion; expected HTTP `409` until every item is cleared/not applicable.

## Exit Interview

1. PUT `/api/v1/employee-exit/cases/{id}/exit-interview` as the employee with ratings and comments.
2. Expected: one interview row linked to the employee's own case.
3. As another employee attempt the same case; expected no access.
4. Test `declined=true`; expected status `DECLINED` without forcing feedback.

## Final Settlement Known Example

1. Use monthly gross ₹30,000 and submit: 15 payable days, ₹5,000 leave encashment, ₹10,000 gratuity, ₹2,000 bonus, ₹1,000 reimbursement, ₹3,000 notice recovery, ₹1,000 loan and ₹500 tax.
2. Expected earned salary ₹15,000; gross ₹33,000; deductions ₹4,500; net ₹28,500.
3. As HR without `payroll.manage`, try approval; expected HTTP `403`.
4. As payroll approver, approve then mark paid with a payment reference.
5. Attempt to edit/delete the paid database row; expected immutable-snapshot database error.

## Documents and Completion

1. Generate the experience letter.
2. Expected: hashed `EXPERIENCE_LETTER` artifact using employee name, role, hotel and service dates.
3. Complete all clearance and pay settlement, then click **Complete exit**.
4. Expected: case `COMPLETED`, user `employment_status=ALUMNI`, turnover row, alumni profile and `EXIT_COMPLETED` lifecycle event.
5. Retry completion; verify no duplicate turnover/alumni records.

## Isolation and Regression

1. A Property A manager must not read or modify a Property B exit case.
2. A Department Head must not access another department where RBAC denies it.
3. Employee can read only own exit data and cannot approve clearance or settlement.
4. Verify Employee 360, payroll snapshots, onboarding, retention, performance and applications still load.
5. Confirm the completed lifecycle reads Recruitment → Hire → Onboarding → Employment → Promotion/Transfer → Resignation → Exit → Alumni.
