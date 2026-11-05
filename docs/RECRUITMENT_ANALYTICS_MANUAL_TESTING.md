# Recruitment Analytics Manual Testing

## Setup

1. Apply migrations through `054_recruitment_analytics.sql`.
2. Start FastAPI and React, sign in as Owner or Group Admin/HR, and open **Features > Analytics**.
3. Prepare two properties, departments and jobs plus applications at multiple pipeline stages.

## Live Data and Funnel

1. Confirm the page badge says **Live database**.
2. Compare Applications with Supabase for the same property/date range.
3. Move one application from Applied to Shortlisted and refresh.
4. Confirm Applied remains cumulative and Shortlisted increases.
5. Confirm an empty property shows no demo or hard-coded values.

## Filters and Isolation

1. Apply property, department, job, recruiter, source, From and To filters; confirm every KPI/chart changes.
2. Confirm both date boundary days are included.
3. Sign in as a manager assigned only to Property A and request Property B through DevTools/curl.
4. Expect 403/404 with no Property B data. Repeat for a Department Head outside their department.

## Known Calculations

1. Create a two-opening job. Hire two candidates 10 and 20 days after application; confirm time to hire is 15 days.
2. Confirm time to fill ends on the second hire, not the first.
3. Record ₹6,000 and ₹4,000 costs for a cohort with two hires; confirm total ₹10,000 and cost/hire ₹5,000.
4. As Recruiter, attempt `POST /api/v1/analytics/costs`; expect 403.
5. Prepare four interviewed candidates and select three; confirm 75% interview conversion.
6. Prepare three offered candidates and accept two; confirm 66.7% acceptance.
7. Link two applied referrals and hire one; confirm 50% referral conversion.
8. Create HIGH and LOW ghosting assessments; confirm 50% high-risk rate and no claim of observed no-show.
9. Give a hired employee an 80/100 performance review; confirm quality 80. Select an unreviewed cohort and confirm `—`.

## Source Attribution and Regression

1. Open a distributed job link, apply, and verify `applications.source`/`source_ref`.
2. Hire the application and confirm its source row updates.
3. Verify property switching, candidate pipeline, job management, manager dashboard and job pipeline still load.
