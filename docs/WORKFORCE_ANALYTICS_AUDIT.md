# Workforce Analytics Audit

Audit date: 2026-08-31. All metrics use the existing Supabase HRMS schema; no analytics database or duplicate employee table was created.

## Coverage

| Capability | Before | Current | Authoritative source |
|---|---|---|---|
| Headcount | PARTIAL/MANUAL | COMPLETE | Active employment records in `users`; excludes owner/group/candidate accounts |
| Vacancies | PARTIAL | COMPLETE | Open `jobs.openings_count` less actual hired applications |
| Absence | BACKEND ONLY | COMPLETE | Validated `attendance_daily_records` only |
| Overtime | BACKEND ONLY | COMPLETE | Validated attendance minutes; payroll OT separately shown in INR |
| Payroll | BACKEND ONLY | COMPLETE | Immutable FINALIZED `payroll_run_items`; permission restricted |
| Attrition | PARTIAL | COMPLETE | `employee_turnover_history` exit events / period average headcount |
| Engagement | PARTIAL | COMPLETE | Current non-superseded `employee_engagement_scores` |
| Turnover risk | PARTIAL | COMPLETE | Current transparent `employee_retention_risk_scores` |
| Productivity | MISSING | COMPLETE WITH DATA GUARD | Latest completed performance/KPI score, with sample size |
| Department comparison | MANUAL COUNTERS | COMPLETE | Recalculated from employee-level authoritative records |
| Property comparison | PARTIAL | COMPLETE | Recalculated from employee property assignments |
| Hierarchical drilldown | MISSING | COMPLETE | Group → Property → Department → Role → Employee filters |

## Security and Integrity

- API requires both `reports.read` and `employees.read`; property and department authorization is enforced server-side.
- Supabase RLS remains an independent tenant/property/department boundary.
- Payroll values are omitted unless the actor has `reports.financial`.
- Pending/rejected attendance and draft payroll are excluded.
- Missing engagement, performance or rate samples return `null` and render as `—`; no mock values are substituted.
- Productivity is explicitly a completed performance/KPI score, not an unsupported statistical estimate.

## Files

- `backend/app/services/workforce_analytics_service.py`
- `backend/app/routers/analytics.py` (`GET /api/v1/analytics/workforce`)
- `frontend/src/pages/WorkforceAnalytics.tsx`
- `backend/tests/test_workforce_analytics.py`

## Remaining Gaps

- Historic platform accounts need correct employment status/property assignment to be counted accurately.
- Vacancy accuracy depends on applications being advanced to HIRED and linked to canonical jobs.
- Operational productivity measures such as rooms cleaned, covers served and check-ins handled require PMS/POS integrations; the app currently reports validated performance KPI scores instead.
- Payroll comparisons require finalized runs; draft and calculated runs are intentionally excluded.
- Point-in-time historical headcount needs employment effective-dating beyond the currently stored joining/exit events.
