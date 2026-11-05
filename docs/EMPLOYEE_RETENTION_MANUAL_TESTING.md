# Employee Retention Manual Testing

## 1. Setup and migration safety

1. Back up Supabase and record counts for users, attendance, compensation, performance, training and lifecycle tables.
2. Apply migrations through `048_employee_retention.sql` in order.
3. Confirm all existing counts are unchanged and existing employee workflows still load.
4. Prepare Owner, HR Manager, Department Head A, Employee A, Employee B in another property/department, and Candidate accounts.

## 2. Baseline rules result

1. Use an active employee with no recent adverse signals.
2. POST `/api/v1/employee-retention/employees/{id}/calculate` as HR.
3. Expect `model_type=RULES_BASED`, version `RETENTION_RULES_V1`, LOW level, factors/actions arrays and disclaimer.
4. Confirm no employee, payroll, attendance, performance, shift or job record changed.

## 3. Attendance signals

1. Create 90 days of attendance with manager-validated normal days, six ABSENT days and eight late days.
2. Recalculate and confirm REPEATED_ABSENCE and REPEATED_LATENESS factors show counts, window and points.
3. Change those records to PENDING validation and recalculate; they must not be counted.
4. Confirm approved leave and weekly-off records are not treated as absence.

## 4. Salary and promotion signals

1. Add two effective compensation structures with a lower latest gross salary; recalculate and expect PAY_REDUCTION.
2. Test an unchanged structure older than 24 months; expect PAY_STAGNATION.
3. Add a latest performance score of 85 with no PROMOTION lifecycle event for 18 months; expect HIGH_PERFORMER_NO_PROGRESSION.
4. Add a recent PROMOTION lifecycle event and recalculate; that factor must disappear.
5. Confirm finalized payroll snapshots remain unchanged.

## 5. Pulse surveys and anonymity

1. As HR, POST `/pulse-surveys` with an anonymous survey.
2. As Employee A, respond once; repeat and expect 409.
3. Verify the stored response has `employee_id=NULL` and a hashed fingerprint.
4. GET results as HR and verify count, average and distribution without respondent identity.
5. Recalculate Employee A and confirm the anonymous response is not used in the individual score.
6. Create a clearly identified non-anonymous pulse survey, collect several responses, and verify low/declining employee-linked scores produce explained factors.

## 6. Training and rehire signals

1. Give Employee A two overdue ASSIGNED/IN_PROGRESS courses; recalculate and expect TRAINING_DISENGAGEMENT.
2. Complete/cancel the courses; recalculate and confirm the factor disappears.
3. POST a prior RESIGNED or ABSCONDED turnover event, then REHIRED; expect PRIOR_EMPLOYMENT_EXIT with a supportive check-in action.

## 7. Score history and interventions

1. Calculate Employee A twice after changing source signals.
2. Verify only one row has `superseded_at IS NULL`; the earlier score remains as history.
3. POST `/risks/{riskId}/interventions` with a wellbeing check-in.
4. Confirm the intervention is linked to the score and employee, with owner and status.
5. Confirm no recommended action is executed automatically.

## 8. Dashboard

1. Open `/employee-retention` at desktop and 360px width.
2. Verify cards show employee, role, score, level, data quality, reasons and actions without overlap.
3. Test ALL, CRITICAL, HIGH, MEDIUM and LOW filters.
4. Switch active property and verify results update to that property only.
5. Trigger Refresh and confirm new current scores replace current rows while retaining history.

## 9. Authorization and privacy

1. Employee and Candidate call `/risks`; expect 403.
2. Department Head A requests Property/Department B data; expect 404/no rows.
3. HR from another organization requests known IDs; expect 404/no rows.
4. Employee A tries to respond as Employee B; the API must derive identity from the token.
5. Verify free-text pulse comments, complaint content and protected demographic/KYC fields never appear in risk factors.
6. Manipulate the frontend to expose the route; confirm server/RLS still deny access.

## 10. Regression

1. Run attendance normal/late/absence/correction tests.
2. Open payroll, performance, Learning & Career, Employee 360 and WhatsApp HR Bot.
3. Confirm compensation, promotion, training and pulse source records are read-only inputs during scoring.
4. Verify employees remain active regardless of risk score.
