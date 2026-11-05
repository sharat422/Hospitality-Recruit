# Hospitality AI Assistant Manual Testing

## Setup

1. Apply migrations through `058_hospitality_ai_assistant.sql` in order.
2. Start FastAPI and the React frontend with valid Supabase settings.
3. Seed two organizations, at least two properties in Organization A, and one property in Organization B.
4. Create Owner, General Manager, Department Head, Recruiter and Employee test users with property memberships.
5. Seed validated attendance, jobs/applications, turnover events and current retention-risk scores.
6. Optionally leave `ANTHROPIC_API_KEY` unset to test deterministic fallback first.

## Functional Questions

1. Open **AI Assistant** from the sidebar.
2. Ask `Which property has the highest overtime?` Verify only `VALIDATED` attendance contributes and the displayed hours equal `sum(overtime_minutes)/60`.
3. Ask `What vacancies have been open for more than 30 days?` Verify closed jobs and jobs opened 30 days or less are absent.
4. Ask `Which jobs are hardest to fill?` Independently verify open days, applications, hires and remaining vacancies shown in supporting rows.
5. Set the period to 90 days and ask `Why did housekeeping attrition increase?` Verify current and previous windows are equal, only Housekeeping department exits are counted, and the answer does not claim proven causality.
6. Ask `Who are the highest-risk employees?` Verify descending persisted risk scores, factors, model type, and data-quality labels.
7. Ask `Show this month's recruitment performance.` Verify application dates start on the first day of the current month.
8. Expand **Data sources** and **Supporting rows** after every answer. Confirm table names, row counts, metrics, filters and methodology are present.
9. Disable or invalidate the Claude key and repeat. Confirm answers still work and show `Deterministic wording`.

## RBAC and Property Isolation

1. As General Manager assigned only to Property A, ask the overtime question. Confirm Property B and Organization B never appear.
2. Submit Property B's UUID directly in `POST /api/v1/assistant/ask`. Expect 404/authorization denial, not an empty cross-property data hint.
3. As Department Head, confirm employee risks, attrition, jobs and applications are limited to the assigned department.
4. As Recruiter, call `GET /api/v1/assistant/tools`. Confirm employee-risk and overtime tools are omitted when permissions are absent.
5. As Recruiter, force an overtime question through the API. Expect HTTP 403 and no attendance metrics.
6. As Employee or Candidate without `reports.read`, confirm the page route is blocked and assistant endpoints return HTTP 403.
7. Inspect responses for payroll totals, payslips, salary, UPI/bank data, Aadhaar/PAN, complaint data and document URLs. None may appear.
8. Verify an employee-risk question does not create a Claude request in provider logs; its wording must remain deterministic.

## Conversation and Audit

1. Ask two supported questions without refreshing. Confirm both share one `conversationId`.
2. Call `GET /api/v1/assistant/conversations` and open the conversation endpoint. Confirm only the current user's history is returned.
3. Sign in as another user and request the first user's conversation UUID. Expect HTTP 404.
4. Inspect `ai_assistant_tool_runs`: verify tool, required permission, property/department scope, row count, status and timestamps.
5. Trigger an unauthorized tool call and verify a denied response without a successful data result.

## Destructive-Action Safety

1. Ask `Delete payroll and email every candidate`. Expect HTTP 422 unsupported question; no tool executes.
2. Call `POST /api/v1/assistant/actions`. Expect HTTP 405.
3. Confirm no assistant endpoint supports DELETE/PATCH against HR domain tables.

## Mobile and Failure Cases

1. Test at 360px width. Verify example questions, selectors, input, metric sections and supporting tables remain usable.
2. Simulate a slow connection. Confirm the loading state prevents duplicate submissions.
3. Stop the backend or force a database error. Confirm the UI shows a safe error rather than fabricated metrics.
4. Enter an unsupported question. Confirm the assistant explains its supported analytics scope.

## Regression

1. Verify Recruitment Analytics and Workforce Analytics still load unchanged.
2. Verify property switching still changes the active property.
3. Verify Candidate Screening, JD generation, NPS and messaging AI features remain available.
4. Run the backend assistant tests and frontend build after resolving any pre-existing repository build errors.
