# Workforce Analytics Manual Testing

## Setup

1. Apply all migrations through `054_recruitment_analytics.sql` and start FastAPI and React.
2. Sign in as Owner or Group Admin/HR and open **Features → Workforce Analytics**.
3. Create two properties, departments, roles and employees with correct property/department assignments.
4. Select a From/To period containing known attendance, payroll and exit records.

## Headcount and Vacancies

1. Create two ACTIVE employee records in one department and one OWNER account.
2. Confirm headcount is 2, not 3.
3. Create an open job with three vacancies and one linked HIRED application.
4. Confirm Vacancies is 2. Close the job and confirm it is excluded.

## Attendance and Overtime

1. Add one VALIDATED ABSENT day and one VALIDATED PRESENT day with 120 overtime minutes.
2. Add a PENDING absent row with overtime and refresh.
3. Confirm absence is one day, absence rate 50%, overtime 2 hours, and the pending row is ignored.
4. Approve the pending row through Attendance and confirm analytics then changes.

## Payroll Security

1. Finalize a payroll snapshot and confirm Gross, Net, Employer Cost, LOP and Overtime Pay match Payroll.
2. Confirm draft/calculated payroll is excluded.
3. Sign in as HR Manager without `reports.financial`; confirm payroll values are hidden.
4. Call `/api/v1/analytics/workforce` directly and confirm the JSON also contains `payroll: null`.

## Attrition, Engagement, Risk and Productivity

1. Record one exit event in the selected period and verify turnover count/rate.
2. Move the date range outside the exit date and confirm it is excluded.
3. Calculate current engagement scores of 60 and 80; confirm group score 70.
4. Create HIGH and LOW current retention risk scores; confirm high-risk count one.
5. Complete performance scores of 70 and 80; confirm productivity 75 with sample two.
6. Select a cohort without scores and confirm the UI shows `—`, not zero.

## Drilldown and Isolation

1. Start at Group and compare both properties.
2. Select Property → Department → Role → Employee in order; confirm each metric narrows consistently.
3. Switch to a Property Manager assigned only to Property A and request Property B via URL/API.
4. Expect 403/404 and no Property B employee or payroll data.
5. Repeat with a Department Head against another department.

## Regression

1. Verify Attendance, Payroll, Retention, Engagement, Performance and Hotel Management still load.
2. Confirm property switching still scopes records.
3. Verify `/analytics` recruitment analytics remains separate and functional.
