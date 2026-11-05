# Reporting Functionality Audit

Audit date: 2026-08-31. Existing modules had isolated CSV/PDF exports and dashboard views, but there was no reusable report registry, immutable run history, delivery audit, or schedule processor.

## Coverage

| Capability | Before | Current |
|---|---|---|
| Daily HR report | MISSING | COMPLETE |
| Weekly recruitment report | MISSING | COMPLETE |
| Monthly workforce report | MISSING | COMPLETE |
| Payroll report | PARTIAL/SCREEN EXPORTS | COMPLETE from finalized snapshots |
| Compliance report | PARTIAL | COMPLETE |
| Attrition report | UI/API FRAGMENTS | COMPLETE |
| Source report | UI/API FRAGMENTS | COMPLETE |
| Property comparison | PARTIAL | COMPLETE |
| PDF generation | SEPARATE/INCONSISTENT | COMPLETE via shared ReportLab renderer |
| Email delivery | SERVICE EXISTED | COMPLETE via shared delivery pipeline |
| WhatsApp delivery | GATEWAY EXISTED | COMPLETE with PDF document link |
| Scheduled reports | MISSING | COMPLETE via Celery + Redis every 15 minutes |

## Architecture

- `reporting_service.py` owns report definitions, collection, PDF rendering, immutable run creation and delivery.
- `reports.py` exposes definitions, generation, run history/download, schedules and public expiring PDF links.
- `scheduled_reports.py` calls the same `execute_report` function as manual generation.
- `report_runs.report_data` is an immutable data snapshot; later database changes do not silently change an issued report.
- `report_deliveries` records channel, recipient, provider reference, status and attempts.
- No separate analytics database was created.

## Security

- Reads require `reports.read` and remain property-scoped through API authorization and RLS.
- Payroll report generation requires `reports.financial`.
- Any external delivery requires `reports.financial` because it can export data outside the application.
- Schedule management requires `reports.financial`.
- Public PDF links use random UUID tokens and expire after seven days.
- The public token endpoint uses the server-only Supabase service role; the service-role key must never enter frontend configuration.

## Database

Migration `056_reporting_engine.sql` adds `report_schedules`, `report_runs`, and `report_deliveries`. Existing attendance, leave, applications, payroll, compliance, retention, engagement, employee and property tables remain authoritative.

## Remaining Gaps

- SMTP, WhatsApp provider, Redis/Celery and `SUPABASE_SERVICE_ROLE_KEY` must be configured for production delivery.
- Scheduled recipients are entered directly; organization-managed distribution lists are not yet implemented.
- ReportLab currently uses standard Latin fonts. Full Hindi PDF typography requires bundling and registering an approved Devanagari font.
- PMS/accounting integrations remain necessary for richer revenue and operational productivity reports.
- Delivery retries are handled by the scheduled task retry and recorded status; a dedicated per-delivery retry queue would improve high-volume operations.
