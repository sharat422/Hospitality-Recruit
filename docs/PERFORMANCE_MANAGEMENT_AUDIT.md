# Performance Management Audit

Audit date: 2026-08-28

## Existing Before This Change

- `employee_performance_reviews` stored a period, optional 1-5 rating, goals and manager comments.
- `POST /api/v1/employees/{employee_id}/performance` allowed a manager to append that basic record.
- Employee 360 displayed a read-only list of reviews.
- No appraisal cycle, configurable KPI, self-review, peer-review, guest feedback, scoring or outcome workflow existed.

## Feature Coverage

| Capability | Status | Implemented | Remaining gap |
|---|---|---|---|
| Appraisal cycles | COMPLETE | Draft/active/calibration/closed lifecycle, dates, property scope and thresholds | Bulk employee enrollment is not included |
| Self-review | COMPLETE | Employee-only submission, comments and KPI evidence | Reminder automation is not included |
| Manager review | COMPLETE | Property/department-authorized review and score publication | Calibration committee UI is a future enhancement |
| Peer review | COMPLETE | Manager-assigned peer access, separate contribution and KPI scores; peer count cannot inflate weight | Multi-step peer nomination approval is not included |
| KPIs | COMPLETE | Configurable templates by department and optional role; cycle snapshots prevent later template edits changing historical reviews | Direct PMS/POS operational metric ingestion is not integrated |
| Guest feedback | COMPLETE | Attributable rating, complaint and compliment records linked to employee/review | External review-platform/PMS ingestion is not integrated |
| Performance score | COMPLETE | Deterministic 0-100 normalization, reviewer-category weighting and KPI weighting with breakdown | No AI scoring is used or needed |
| Increment | PARTIAL | Eligibility threshold, recommendation and explicit approval state | Approval deliberately does not mutate payroll; payroll-effective changes need a separate compensation workflow |
| Promotion eligibility | COMPLETE | Configurable threshold and advisory eligibility; recommendation requires human approval | Approved promotion does not automatically change employment/job title |
| Employee 360 | COMPLETE | Existing tab now shows 0-100 score and eligibility flags | Historical 1-5 records remain supported without conversion |
| RBAC/RLS | COMPLETE | New `performance.read/manage`, self access, tenant/property/department enforcement | Must be validated after applying migration to the target Supabase project |

## Hospitality KPI Templates

Templates are database records, not UI constants. Migration 046 seeds editable defaults:

- Front Office: check-in performance, guest complaint rate, guest service rating.
- Housekeeping: room quality audit, room turnaround, room complaints.
- Kitchen: food cost control, food waste, food quality audit.
- F&B: upsell performance, guest rating, order accuracy.

Organizations can add templates for any department or role through the API/UI. A cycle copies template values and weights into `performance_cycle_kpis`, preserving the historical score contract.

## Database Changes

- Extended `employee_performance_reviews`; did not create a duplicate employee-review table.
- Added `performance_appraisal_cycles`.
- Added `performance_kpi_templates` and `performance_cycle_kpis`.
- Added `performance_review_contributions` and `performance_kpi_scores`.
- Added `performance_peer_assignments` so peer access is explicit and review-scoped.
- Added `performance_guest_feedback`.
- Added `performance_outcome_recommendations`.
- Added tenant/property/department-aware RLS and narrow performance permissions.

Migration: `supabase/migrations/046_performance_management.sql`.

## API

- `GET|POST /api/v1/performance/kpi-templates`
- `GET|POST /api/v1/performance/cycles`
- `GET /api/v1/performance/cycles/{cycle_id}`
- `PATCH /api/v1/performance/cycles/{cycle_id}/activate`
- `POST /api/v1/performance/cycles/{cycle_id}/reviews`
- `GET /api/v1/performance/reviews/{review_id}`
- `PATCH /api/v1/performance/reviews/{review_id}/self-review`
- `POST /api/v1/performance/reviews/{review_id}/peer-review`
- `PATCH /api/v1/performance/reviews/{review_id}/manager-review`
- `POST /api/v1/performance/guest-feedback`
- `GET /api/v1/performance/employees/{employee_id}`
- `POST /api/v1/performance/reviews/{review_id}/outcome`
- `PATCH /api/v1/performance/outcomes/{outcome_id}`

## UI and Services

- `frontend/src/pages/PerformanceManagement.tsx`: cycles, templates and reviews.
- `frontend/src/pages/Employee360.tsx`: richer performance summary.
- `backend/app/services/performance_service.py`: deterministic scoring and eligibility.
- `backend/app/routers/performance.py`: workflow and authorization.

## Governance

- KPI definitions, targets, direction and weights are configurable and snapshotted.
- Peer reviewers are averaged as one reviewer category, preventing many peer reviews from overpowering the manager category.
- Eligibility is advisory. No endpoint automatically changes salary, payroll, role or employment status.
- Outcome approval is a recorded HR decision but still does not mutate payroll/employment records.
- Existing 1-5 performance records remain valid and visible.
