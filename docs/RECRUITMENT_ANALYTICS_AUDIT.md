# Recruitment Analytics Coverage Audit

Audit date: 2026-08-31. Source of truth: existing Supabase/PostgreSQL ATS tables. No separate analytics database was introduced.

## Coverage

| Metric | Before audit | Current | Persisted source/calculation |
|---|---|---|---|
| Applications | PARTIAL | COMPLETE | `applications`, filtered by `created_at` |
| Source | PARTIAL | COMPLETE | `applications.source`; missing values remain UNKNOWN |
| Funnel conversion | BROKEN | COMPLETE | Cumulative canonical stages from Applied through Hired |
| Time to hire | BROKEN | COMPLETE | Application creation to `hired_at`; incomplete rows excluded |
| Time to fill | PLACEHOLDER | COMPLETE | Job approval/creation to the Nth hire for N openings |
| Cost per hire | MOCK | COMPLETE | Actual INR `recruitment_cost_entries` divided by hires |
| Interview conversion | MISSING | COMPLETE | Selected-or-later / Interview-or-later |
| Offer acceptance | MISSING | COMPLETE | Offer Accepted-or-later / Offer-or-later |
| Ghosting | PARTIAL | COMPLETE | High/Critical `ghosting_risk_scores`; not mislabeled as no-shows |
| Referral conversion | MISSING | COMPLETE | Hired / applied referrals linked to filtered applications |
| Quality of hire | MISSING | COMPLETE | Latest performance review for hired candidate-employees |
| Required filters | MISSING | COMPLETE | Property, department, job, recruiter, source, date range |

## Problems Found and Corrected

- The legacy service returned hard-coded zeros, empty arrays and fabricated USD cost values.
- Its repository treated a user ID as an organization ID and read jobs from candidates instead of applications.
- `/analytics` existed in the sidebar but had no React route.
- Metrics lacked canonical RBAC property and department scope.

The new endpoints are `GET /analytics/recruitment`, `GET /analytics/filters`, `POST/GET /analytics/costs`. Compatibility endpoints now use the same live aggregator. Cost writes require `reports.financial`; all analytics reads require `reports.read`. Database RLS independently enforces organization, property and department isolation.

## Remaining Gaps

- Cost entry is manual until accounting and job-board billing adapters are connected.
- Quality is unavailable until hired employees have completed performance reviews; the UI shows a dash rather than inventing a score.
- Historic rows missing source or milestone timestamps require an explicit backfill.
- Cohort benchmarks and predictive forecasting remain future enhancements and must not be represented as statistically valid without sufficient history.
