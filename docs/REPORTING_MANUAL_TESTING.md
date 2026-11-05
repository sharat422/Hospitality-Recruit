# Reporting Manual Testing

## Setup

1. Apply migration `056_reporting_engine.sql`.
2. Install backend dependencies so ReportLab and Celery are available.
3. Configure SMTP, WhatsApp provider, Redis and `SUPABASE_SERVICE_ROLE_KEY`.
4. Start FastAPI, the Celery worker, Celery beat and React; open **Features → Reporting Center**.

## Report Data

1. Generate each of the eight report types for a known property and period.
2. Compare Daily HR with validated attendance and approved leave; pending attendance must be absent.
3. Compare Weekly Recruitment and Source with canonical application stages/sources.
4. Confirm Payroll includes only FINALIZED payroll snapshots in selected months.
5. Confirm Compliance uses property jobs/employees and does not include another property.
6. Confirm Attrition uses period exit events and current risk scores.
7. Confirm Monthly Workforce and Property Comparison match active employee assignments.

## PDF

1. Download each run and verify `%PDF`/browser rendering, title, period, sections and live-data label.
2. Change source data after generation and download the old run again; confirm its snapshot does not change.
3. Open the public token link before expiry, then set expiry to the past in a test database and expect 404.

## Email and WhatsApp

1. Generate a report with an email recipient; confirm email contains the expiring PDF link and delivery is SENT.
2. Repeat with an E.164 WhatsApp recipient; confirm the PDF document opens.
3. Use invalid provider credentials and confirm the run/delivery records FAILED or PARTIAL rather than claiming success.
4. As a Recruiter without `reports.financial`, attempt external delivery; expect 403.

## Schedules

1. Create daily, weekly and monthly schedules with future `next_run_at` values.
2. Move each to the past in a test database and run `run_scheduled_reports`.
3. Confirm one immutable run, one delivery per recipient and an advanced `next_run_at`.
4. Run the worker again immediately and confirm no duplicate report is generated.
5. Stop Redis/provider temporarily and confirm Celery retries and records failure.

## Authorization

1. Owner: generate group and property reports.
2. Property Manager A: generate Property A only; direct Property B requests must return 403/404.
3. Confirm a Property A user cannot list/download a Property B report run.
4. Confirm payroll and delivery controls are unavailable without financial permission at API level, not only UI.

## Regression

1. Verify Executive, Recruitment and Workforce Analytics still work.
2. Verify payroll PDF and compliance exports still work independently.
3. Verify WhatsApp HR Bot and email demo notifications remain operational.
