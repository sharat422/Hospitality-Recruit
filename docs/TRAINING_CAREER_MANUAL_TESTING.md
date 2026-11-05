# Training and Career Manual Testing

## Prerequisites

1. Back up Supabase and record counts for `users`, `jobs`, `applications`, and `employee_training_records`.
2. Apply migrations through `047_training_and_career.sql` in order.
3. Start FastAPI and React. Prepare Owner, HR Manager, Department Head, Employee A, Employee B, and Candidate accounts.
4. Put Employee A in Property A / Front Office and Employee B in Property B / Kitchen.
5. Complete a performance review for Employee A with score 85.

## Migration safety

1. Confirm pre-migration row counts are unchanged.
2. Confirm an old training row without `course_id` still renders in Employee 360.
3. Confirm old jobs have `visibility=PUBLIC`.

## Catalog, assignment and video content

1. As HR, POST `/api/v1/learning-career/courses` with VIDEO delivery, HTTPS content URL, duration and pass score.
2. GET `/courses` and confirm it appears.
3. POST `/assign?course_id={id}` for Employee A; repeat and expect 409.
4. As Employee A, GET `/my-learning`; check title, due date and progress.
5. As Candidate, call `/courses`; expect 403.
6. Open `/learning-career` at 360px; verify tabs scroll and cards do not overflow.

## Completion and quiz security

1. PATCH Employee A's progress to 25, 50 and 100; verify activity timestamps.
2. As Employee B, PATCH Employee A's enrollment; expect 404.
3. Configure a two-question quiz. GET `/enrollments/{id}/quiz` as Employee A.
4. Confirm `correct_option` and explanation are absent.
5. Submit one correct answer; verify deterministic score and failed status when below threshold.
6. Submit all correct with progress at 100%; verify COMPLETED.
7. Verify attempt answers, score and timestamp in `training_quiz_attempts`.
8. Attempt direct employee selection of quiz question rows; RLS must deny it.

## Skills and gaps

1. Map the completed course to a skill at proficiency 3.
2. Complete the course and verify one `employee_skills` row with source TRAINING and course evidence.
3. Retry completion; verify no duplicate employee-skill row.
4. Configure a pathway requiring proficiency 4; verify the skill remains a gap.
5. Have a manager verify level 4; verify the gap disappears.

## Pathway and promotion readiness

1. Create a Front Office pathway and a `Front Desk Agent -> Front Desk Supervisor` step.
2. Configure score 80, tenure 12 months, required skills and courses.
3. Create Employee A's career plan targeting the step.
4. GET `/employees/{A}/readiness`; confirm every missing item is explained.
5. Meet all requirements without approving the review outcome: expect `ready=true` and `promotion_action_allowed=false`.
6. Approve the performance outcome: expect `promotion_action_allowed=true`.
7. Confirm the employee job title and salary did not change automatically.

## Internal jobs and isolation

1. Mark an approved open job INTERNAL, another BOTH, and another PUBLIC.
2. GET `/internal-jobs`; only INTERNAL/BOTH open jobs should appear.
3. Close the internal job and confirm it disappears.
4. Employee A requests Employee B readiness: expect 403/404.
5. Department Head A creates a course in Department B: expect 404.
6. A user from another organization requests IDs from this test: expect 404 or no rows.
7. Confirm DOM/sidebar manipulation cannot bypass API or RLS controls.

## Regression

1. Verify Employee 360 Training and Career tabs still load old and new records.
2. Verify performance review data is read but never mutated by readiness.
3. Verify WhatsApp CAREER still returns its fallback guidance.
4. Smoke-test public jobs, candidate applications, certifications, payroll, leave and attendance.
