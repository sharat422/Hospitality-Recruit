# Employee Engagement Manual Testing

## Prerequisites

1. Apply migrations through `049_employee_engagement.sql` in order.
2. Start FastAPI and React.
3. Prepare one HR Manager and six Employees; assign four to Department A and two to Department B.
4. Confirm WhatsApp test employees have registered phone numbers.

## Create and Answer a Survey

1. As HR Manager, open **Employee Engagement**.
2. Create an anonymous survey with minimum reporting group `5` and PWA + WhatsApp channels.
3. As Employee 1, open `/employee-app`, select **Pulse / सर्वे**, choose 1-5, add a comment and submit.
4. Expected: the form becomes a recorded confirmation; a repeat returns HTTP `409`.
5. From registered employee phones send `SURVEY 4 Good team support` and `सर्वे 5 अच्छा सहयोग`.
6. Expected: bilingual confirmation. `SURVEY 8` must return the valid 1-5 format.

## Verify Anonymous Privacy

1. As HR Manager call `GET /api/v1/employee-engagement/surveys/{id}/analytics`.
2. Expected: counts, distribution, trend, and comparisons only.
3. Confirm there are no comments, employee IDs, names, phones, or fingerprints.
4. Attempt direct Supabase SELECT on `employee_pulse_responses` using the manager JWT.
5. Expected: RLS returns no raw response rows.
6. With a service role inspect storage: anonymous response `employee_id` is null; participation identity is in a separate table.

## Cohort Suppression

1. Submit four Department A and two Department B responses.
2. Expected: both department averages are suppressed.
3. Add a fifth Department A response.
4. Expected: A average appears; B remains suppressed.

## Recognition and Employee of Month

1. POST `/api/v1/employee-engagement/recognitions` with employee, category and a 10+ character reason.
2. Approve it in the manager dashboard.
3. POST `/api/v1/employee-engagement/employee-of-month` for the employee/property/month.
4. Expected: award includes recognition count and points summary.
5. Repeat the same property/department/month; expected unique-constraint rejection.

## Engagement Score and Authorization

1. Give an employee validated attendance, training, approved recognition and an identified pulse response.
2. POST `/api/v1/employee-engagement/scores/{employeeId}/calculate` as HR Manager.
3. Expected: score 0-100, level, components, data quality, `RULES_BASED`, and disclaimer.
4. Recalculate; expected previous row gets `superseded_at` and only one current score remains.
5. As Employee attempt survey creation, recognition review and score calculation; expected HTTP `403`.
6. As a Property A manager request Property B data; expected HTTP `404` or no rows.
