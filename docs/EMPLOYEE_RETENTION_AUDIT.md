# Employee Retention and Attrition Audit

Audit date: 2026-08-29

## Coverage result

| Capability | Before | Current | Evidence / limitation |
|---|---|---|---|
| Employee turnover history | PARTIAL | COMPLETE | Lifecycle events existed; normalized turnover events now support reason, voluntary exit and rehire eligibility |
| Absence signals | COMPLETE | COMPLETE | Only validated `attendance_daily_records` in a 90-day window are scored |
| Late attendance | COMPLETE | COMPLETE | Validated late days are counted; raw punches are not used |
| Salary changes | COMPLETE | COMPLETE | Effective-dated `employee_compensation_structures` are compared; payroll snapshots remain immutable |
| Promotion history | PARTIAL | COMPLETE | Existing performance outcomes plus `PROMOTION` lifecycle events are used |
| Pulse surveys | MISSING | COMPLETE | Scoped surveys, anonymous/non-anonymous responses, duplicate prevention and aggregate results |
| Engagement | PARTIAL | COMPLETE | Employee-linked pulse trend is an individual signal; anonymous pulse remains aggregate-only |
| Training | COMPLETE | COMPLETE | Overdue assignments from the existing training ledger are scored |
| Turnover risk | MISSING | COMPLETE | Versioned, transparent rules score with factors, actions and input snapshot |
| AI recommendations | MISSING | RULES-BASED | No predictive-AI claim; deterministic action library only |
| Manager explanation UI | MISSING | COMPLETE | `/employee-retention` shows score, level, data quality, factors and actions |

## Why this is not predictive AI

The repository does not contain enough clean, longitudinal employee exit outcomes to train and validate a statistical attrition model. The implementation therefore stores `model_type=RULES_BASED`, `model_version=RETENTION_RULES_V1`, a disclaimer, source snapshots, and point-level explanations. A statistical model must not be enabled until there is sufficient historical coverage, a holdout evaluation, calibration, bias review, and documented approval.

## Existing data reused

- `attendance_daily_records`: validated absence and lateness only.
- `employee_compensation_structures`: effective-dated salary change and stagnation.
- `employee_performance_reviews`: latest overall performance score.
- `employee_lifecycle_events`: promotion history.
- `employee_training_records`: overdue training.
- `users`: active employment, property, department, joining date.

No parallel attendance, payroll, performance, training, employee, or promotion system was created.

## Added database objects

Migration `supabase/migrations/048_employee_retention.sql` adds:

- `employee_turnover_history`
- `employee_pulse_surveys`
- `employee_pulse_responses`
- `employee_retention_risk_scores`
- `employee_retention_interventions`

Current scores are unique per employee while prior scores remain immutable history via `superseded_at`. All tables have organization RLS. Risk and turnover records require scoped `employees.read/manage`; employees can submit one pulse response but cannot read manager risk records.

## Rules V1

The score is capped at 100 and maps to LOW `<25`, MEDIUM `25-49`, HIGH `50-69`, CRITICAL `70+`. Current factors include:

- validated absence frequency
- validated late-arrival frequency
- pay reduction or 24+ months without a recorded increase
- high performance without promotion in 18 months
- low or declining non-anonymous pulse responses
- two or more overdue training assignments
- early-tenure window
- prior resignation/absconding for a rehired employee

Each factor records code, points, observed value/window, and explanation. Recommended actions are supportive manager steps, not disciplinary decisions.

## APIs and UI

API prefix: `/api/v1/employee-retention`

- `GET /risks`
- `POST /employees/{id}/calculate`
- `POST /calculate-all`
- `GET/POST /pulse-surveys`
- `POST /pulse-surveys/{id}/respond`
- `GET /pulse-surveys/{id}/results`
- `POST /risks/{id}/interventions`
- `GET/POST /turnover`

The protected `/employee-retention` dashboard supports property scope, level filters, data-quality visibility, reasons and recommended actions.

## Security and fairness controls

- Employees cannot see manager-only risk scores through API or RLS.
- Cross-organization, property and department access is constrained.
- Anonymous pulse responses store no employee ID and are excluded from individual scoring.
- Sensitive free-text pulse comments are not copied into risk factors or UI.
- The model does not use gender, caste/category, disability, religion, age, Aadhaar/PAN, medical data or complaint content.
- No score triggers termination, discipline, pay, scheduling, promotion or messaging automatically.

## Remaining gaps

- Scheduled daily/weekly recalculation worker; calculation is currently manager/API initiated.
- Configurable rule weights and windows per organization with change audit.
- Aggregate turnover-rate/cohort trends and intervention effectiveness analytics.
- Pulse survey creation/response UI; APIs are complete, manager dashboard currently focuses on risks.
- Validated statistical model, intentionally not implemented due to insufficient historical outcomes.
- Full browser E2E validation remains blocked by unrelated malformed legacy TypeScript files identified in prior audits.
