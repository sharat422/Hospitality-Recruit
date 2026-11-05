# Workforce Shift Scheduling Audit

## Scope and result

The repository previously had two unrelated concepts named scheduling: candidate-to-seasonal-shift matching and candidate interview slots. Neither was an employee roster. Migration `037_workforce_shift_scheduling.sql`, the workforce scheduling API, and the `/shifts` UI add the missing roster workflow while preserving both legacy systems.

| Capability | Before | After | Evidence |
|---|---|---|---|
| Shift templates | MISSING | BACKEND ONLY | `shift_templates`, template APIs; dedicated template editor remains |
| Weekly schedules | MISSING | COMPLETE | `workforce_schedules.period_type`, `/schedules`, `/calendar` |
| Monthly schedules | MISSING | COMPLETE | Same canonical schedule model and calendar API |
| Drag/drop | MISSING | COMPLETE | `WorkforceScheduler.tsx`, assignment move API |
| Employee availability | PARTIAL (candidate JSON only) | BACKEND ONLY | `employee_availability_windows`, self-service API; employee UI remains |
| Conflict prevention | PARTIAL | COMPLETE | deterministic service plus PostgreSQL trigger |
| Weekly off | PARTIAL (attendance policy only) | BACKEND ONLY | employee-level dated weekly offs; manager UI remains |
| Rest periods | BACKEND ONLY utility | COMPLETE | 12-hour API and database enforcement |
| Shift swaps | MISSING | BACKEND ONLY | peer and manager approval workflow; inbox UI remains |
| Manager approval | MISSING | COMPLETE | DRAFT → PENDING_APPROVAL → APPROVED → PUBLISHED |
| WhatsApp notifications | READ ONLY | COMPLETE | publish notifications and notification audit log |
| Attendance connection | PARTIAL | COMPLETE | attendance reads published workforce roster first |
| Leave connection | MISSING | COMPLETE | assignment validation and database trigger block approved leave |
| Compliance connection | PARTIAL | COMPLETE | 12-hour rest and 48-hour week enforced deterministically |

## Security

- Every new row carries `org_id`; property and department access is checked in FastAPI and PostgreSQL RLS.
- Employees can manage only their availability and own swap requests. Managers require `attendance.manage`.
- Schedule audit records identify actor and affected schedule, shift, assignment, or swap.
- Database triggers independently prevent overlap, approved-leave assignment, weekly-off assignment, insufficient rest, and more than 48 scheduled hours per week.
- Existing recruitment shifts remain supported. Workforce shifts may have a null `job_id` and must instead have authorized property/department ownership.

## Remaining gaps

- Recurring template expansion is intentionally manual; templates prefill shifts but do not silently generate rosters.
- Dedicated template management, employee availability, weekly-off management, and swap inbox screens remain UI gaps. Their APIs, RLS, validation, and manual test procedures are implemented.
- WhatsApp delivery callbacks are logged at send time; provider webhook reconciliation can be added later.
- Payroll remains isolated from unvalidated attendance by design.
