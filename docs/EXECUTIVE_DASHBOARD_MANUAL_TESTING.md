# Owner and Executive Dashboard Manual Testing

## Setup

1. Apply migration `055_executive_dashboard.sql`.
2. Start the backend and frontend, sign in as Owner, and open `/dashboard`.
3. Prepare two properties with active employees, validated attendance, finalized payroll, jobs, applications and risk scores.

## Today and Operational KPIs

1. Add one PRESENT, one ABSENT and one MISSING_PUNCH validated attendance record for today.
2. Add one approved leave spanning today.
3. Refresh and confirm Present 1, Absent 1 and On leave 1; verify the missing-punch alert.
4. Add a pending attendance record and confirm it is excluded.
5. Open a three-position job with one linked hire; confirm two vacancies.

## Financial KPIs

1. Finalize payroll and verify Gross, Net, Employer Cost, LOP and Overtime against Payroll.
2. POST actual property revenue to `/api/v1/analytics/executive-dashboard/revenue`.
3. For ₹5,00,000 revenue and 10 active employees, confirm revenue/employee is ₹50,000.
4. Sign in as HR Manager without financial-report permission; verify payroll, labour cost and revenue are absent in both UI and JSON.
5. Attempt revenue creation without `financial.manage`; expect 403.

## Compliance, Risk, Source and Alerts

1. Create an overdue compliance task and a certificate expiring within 30 days.
2. Confirm compliance counts and two corresponding alerts.
3. Create one HIGH retention risk and confirm its count/alert.
4. Create two Naukri applications and hire one; confirm 50% source conversion.
5. Resolve each condition and confirm its alert disappears after refresh.

## Filters and Widget Configuration

1. Filter by each property and verify all operational and financial KPIs change together.
2. Set From/To and verify payroll, revenue, source and workforce period metrics use that range.
3. Open widget settings, hide Payroll and Source Performance, save, reload and confirm preferences persist.

## Authorization and Regression

1. As Owner, select all properties and confirm group scope.
2. As Property Manager for Property A, omit the property filter and confirm only Property A is returned.
3. Request Property B directly; expect 403/404 with no employee, revenue or payroll leakage.
4. Verify `/analytics`, `/workforce-analytics`, Attendance, Payroll, Compliance and Retention still load.
