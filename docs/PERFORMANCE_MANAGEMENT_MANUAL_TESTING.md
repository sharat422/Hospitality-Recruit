# Performance Management Manual Testing

## 1. Setup

1. Apply migrations through `046_performance_management.sql` in order.
2. Start FastAPI and the React frontend.
3. Prepare two organizations. In organization A create Owner, HR Manager, Department Head, Employee A, Employee B and Recruiter users.
4. Assign both employees to the same property/department and set job titles. Create a second property/department for isolation tests.
5. Sign in as HR Manager and open `/performance`.

## 2. Seeded Hospitality KPIs

1. Open Templates.
2. Confirm Front Office includes check-in performance and guest complaints.
3. Confirm Housekeeping includes room quality and turnaround.
4. Confirm Kitchen includes food cost and waste.
5. Confirm F&B includes upsell and guest rating.
6. Confirm templates are rows returned by `GET /api/v1/performance/kpi-templates`, not frontend constants.

## 3. Configurable KPI

1. Create `Banquet Setup Accuracy` for Events, target 95, higher-is-better, weight 40.
2. Create two more Events KPIs whose weights make 100.
3. Confirm duplicate department/role/metric key returns HTTP 409.
4. Create a role-specific KPI and confirm the role field persists.
5. Sign in as Employee; confirm template creation controls are hidden and POST returns 403.

## 4. Appraisal Cycle

1. Select KPI templates whose weights total exactly 100.
2. Enter cycle name and valid period, then create.
3. Confirm cycle is DRAFT and its KPI snapshots match the selected templates.
4. Change a source template target. Confirm the existing cycle snapshot does not change.
5. Try weights totaling 95 or 105; expect HTTP 422 and confirm no orphan cycle was created.
6. Activate the cycle and confirm status ACTIVE.

## 5. Employee Enrollment

1. Open Reviews, enter Employee A UUID, select the active cycle and click Enroll.
2. Confirm one `employee_performance_reviews` row links the existing employee and cycle.
3. Enroll the same employee again; expect HTTP 409.
4. Attempt enrollment in a closed cycle; expect HTTP 409.

## 6. Self-Review

1. Sign in as Employee A and open Performance > Reviews.
2. Confirm employee UUID is fixed to their own user ID.
3. Open the review, enter actual values, comments, strengths, development areas and submit Self review.
4. Confirm SELF contribution and scores, `self_submitted_at`, and no overall manager score yet.
5. Attempt Employee A self-review against Employee B review ID; expect HTTP 403.

## 7. Peer Review

1. As manager, open Employee A's review and assign Employee B's UUID as peer reviewer.
2. Sign in as Employee B, open the assigned review, enter scores/evidence and submit Peer review.
3. Confirm a PEER contribution separate from SELF and MANAGER.
4. Attempt to submit peer review on your own review; expect HTTP 409.
5. Submit a second peer score. Confirm peer values are averaged before applying the 25% peer-category weight.
6. Use an unassigned employee token against the peer-review endpoint; expect HTTP 403 and no review disclosure.

## 8. Guest Feedback

1. As manager, select Employee A's review.
2. Record rating 4.6, one complaint and three compliments.
3. Confirm the feedback is linked to employee, property and review.
4. Enter rating 0 or 6; expect HTTP 422.
5. Sign in as another tenant; confirm the record is inaccessible.

## 9. Manager Review and Score

1. Enter KPI actuals and manager comments, then submit Manager review.
2. Confirm each actual is normalized according to direction:
   - Higher-better reaches 100 at target.
   - Lower-better reaches 100 at or below target.
   - Target reaches 100 at target and declines toward either configured bound.
3. Confirm overall score uses configured KPI weights.
4. Confirm reviewer categories are manager 60%, peer 25%, self 15% among categories present.
5. Confirm status SHARED, reviewer/timestamp and Employee 360 lifecycle event.
6. Confirm Employee 360 shows score out of 100 and eligibility flags.

## 10. Increment and Promotion

1. Configure cycle thresholds: promotion 80, increment 70.
2. Submit scores of 82; confirm both eligibility flags true.
3. Submit scores of 75 in another review; confirm increment true and promotion false.
4. Add an increment/promotion recommendation with a reason.
5. Confirm response says `advisory_only=true`, `payroll_updated=false`, `employment_updated=false`.
6. Approve or reject via `PATCH /api/v1/performance/outcomes/{id}`.
7. Confirm approval still does not alter payslips, salary structure or `users.job_title`.

## 11. Authorization and Isolation

1. Employee can read and self-review only their own appraisal.
2. Recruiter cannot open `/performance` or call performance APIs.
3. Department Head can manage only their department.
4. Property-scoped manager cannot access another property; expect 404 rather than data disclosure.
5. Organization B cannot read or mutate organization A cycles, reviews, KPIs, feedback or outcomes.
6. Call Supabase directly with each user's JWT and repeat key reads/writes to verify RLS, not only frontend hiding.

## 12. Mobile and Regression

1. Test `/performance` at 360px width; tabs, fields and scorecard must remain usable.
2. Confirm existing historical 1-5 reviews still display in Employee 360.
3. Confirm employee profile, training, certification, payroll and lifecycle tabs still load.
4. Confirm no review action directly changes payroll or employment records.
5. Run `backend/tests/test_performance_management.py` and the existing Employee 360/RBAC tests.
