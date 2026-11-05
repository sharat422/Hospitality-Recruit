# Owner and Executive Dashboard Audit

Audit date: 2026-08-31. The existing `/dashboard` was a welcome/setup page. A separate legacy `Dashboard` component depended on placeholder analytics and was not the routed executive dashboard. The existing route was enhanced rather than creating a competing dashboard.

## Coverage

| KPI | Before | Current | Source |
|---|---|---|---|
| Today's attendance | MISSING | COMPLETE | Today’s validated `attendance_daily_records` |
| Leave | MISSING | COMPLETE | Approved `leave_requests` covering today |
| Absence | MISSING | COMPLETE | Validated ABSENT records |
| Open vacancies | PARTIAL | COMPLETE | Open job openings less linked HIRED applications |
| Payroll | PLACEHOLDER | COMPLETE | FINALIZED immutable payroll snapshots |
| Compliance | PARTIAL | COMPLETE | Open/overdue compliance tasks and certificate expiry |
| Turnover risk | MISSING | COMPLETE | Current high/critical retention risk scores |
| Property comparison | PARTIAL/MANUAL | COMPLETE | Live workforce and vacancy calculations by property |
| Labour cost | MISSING | COMPLETE | Finalized payroll employer cost in INR |
| Overtime | PARTIAL | COMPLETE | Validated attendance hours and finalized payroll OT cost |
| Revenue per employee | MISSING | COMPLETE WITH INPUT LEDGER | Actual property revenue / active headcount |
| Source performance | PLACEHOLDER | COMPLETE | Persisted application source and status |
| Alerts | PLACEHOLDER | COMPLETE | Deterministic absence, punch, vacancy, retention and compliance rules |
| Configurable widgets | MISSING | COMPLETE | Per-user `executive_dashboard_preferences` |
| Property/date filters | MISSING | COMPLETE | Server-scoped property and inclusive date filtering |

## Security

- Group scope is available only to Owner and Group Admin/HR.
- Other managers are explicitly limited to active property memberships, even when no property query is supplied.
- API requires `reports.read` and `employees.read`.
- Payroll, labour cost, revenue and revenue-per-employee are removed server-side without `reports.financial`.
- Revenue creation requires `financial.manage` and property authorization.
- RLS independently enforces organization and property boundaries on revenue and preference rows.

## Database Changes

Migration `055_executive_dashboard.sql` adds only:

- `property_revenue_entries`: actual INR property revenue from manual/PMS/POS/accounting imports.
- `executive_dashboard_preferences`: per-user widget visibility/order/default scope.

No employee, attendance, payroll, recruitment or compliance data was duplicated.

## Remaining Gaps

- PMS/POS/accounting adapters are not connected; revenue entries currently require API/import input.
- Revenue per employee is unavailable until actual revenue is recorded and active headcount exists.
- Compliance alerts cover persisted compliance tasks and employee certificates; deeper statutory filing alerts require filing-calendar data.
- Widget visibility is configurable; drag-and-drop ordering is stored by the API but the current UI uses selection order rather than a drag interaction.
