# Multi-Channel Job Distribution Audit

Audit date: 2026-08-25

## Classification

No external job-board posting API was found. Existing Naukri, Apna, Indeed, and LinkedIn code generated copy only; it did not authenticate with or publish to those platforms. The completed implementation therefore uses tracked first-party channels and honest CSV/manual export for unsupported boards.

| Channel | Classification | Current implementation |
|---|---|---|
| Careers website | API integration (first-party) | Approved jobs publish to the existing public application route through a tracked URL. |
| WhatsApp | Manual share + existing messaging integration | Platform-specific bilingual copy and a prefilled `wa.me` URL; job sharing is user-initiated. Existing Meta/Interakt/Twilio messaging is not misrepresented as a job-board posting API. |
| Employee referrals | API integration (first-party) | Existing referral-code/link APIs, WhatsApp share tracking, application linkage, rewards, and the new distribution attribution ledger. |
| Naukri | Manual export | English/Hindi content, tracked apply URL, posting status/URL/expiry, CSV export. No Naukri API credentials or posting adapter exists. |
| Apna | Manual export | Short-form bilingual content, tracked URL, status/expiry, CSV export. No posting API exists. |
| WorkIndia | Manual export | WorkIndia-ready row and tracked URL exported as CSV. No posting API exists. |
| Shine | Manual export | Shine-ready row and tracked URL exported as CSV. No posting API exists. |
| Indeed India | Manual export | Indeed-ready content, tracked URL, external posting URL field, CSV export. No Indeed Publisher API exists. |
| LinkedIn | Manual export | LinkedIn-ready copy, tracked URL, external posting URL field, CSV export. LinkedIn profile-fill text elsewhere is not a posting integration. |
| Hospitality job boards | Manual export | Generic hospitality-board CSV row. A board can be recorded via its returned posting URL; no vendor-specific API is claimed. |
| QR codes | API integration (first-party) | Existing QR generation and scan ledger plus channel distribution click/application/hire attribution. |
| Walk-in campaigns | API integration (first-party) + manual materials | Tracked campaign URL/source and CSV content for posters or walk-in registers. |

## Implemented components

- Channel configuration with enabled state, delivery mode, default expiry, and non-secret settings.
- One canonical distribution record per job/channel.
- Platform-specific English/Hindi content sourced from the existing JD generator.
- Prepare, publish, unpublish, expiration, posting URL, external post ID, and failure fields.
- Authenticated CSV export for every unsupported board.
- Public attribution tokens with hashed click IPs and user-agent audit data.
- Canonical application creation with `applications.job_id`, `distribution_id`, `source`, and `source_ref`.
- Candidate attribution retained through pipeline stages and recorded on hire.
- Click, application, hire counts and conversion-rate analytics.
- Security-definer database functions for narrow public event recording; no broad anonymous update policy.
- Recruiter distribution modal in Smart Recruitment with channel selection, statuses, analytics counters, publish/unpublish, posting links, and CSV download.

## Database

Migration `031_job_distribution.sql` adds:

- `distribution_channels`
- `job_distributions`
- `job_distribution_events`
- `applications.distribution_id`
- `applications.attribution_token`
- `candidates.distribution_id`
- Atomic `record_distribution_click` and `record_distribution_conversion` functions

All administrative tables use organization/RBAC RLS. Published tracked links expose only live posting metadata and use narrow functions to write events.

## API inventory

- `GET /api/v1/distribution/channels`
- `PATCH /api/v1/distribution/channels/{channel}`
- `POST /api/v1/distribution/jobs/{jobId}/prepare`
- `GET /api/v1/distribution/jobs/{jobId}`
- `POST /api/v1/distribution/{distributionId}/publish`
- `POST /api/v1/distribution/{distributionId}/unpublish`
- `GET /api/v1/distribution/export.csv`
- `GET /api/v1/distribution/analytics/summary`
- `GET /api/v1/distribution/t/{token}` (public tracked redirect)

## Remaining gaps

1. Real external posting requires contracts, approved API access, credentials, adapters, rate-limit handling, and webhooks for each board. None are currently configured.
2. The CSV schema is a normalized export; individual boards may require column mapping changes when their current import templates are obtained.
3. WhatsApp campaign broadcasts require approved Meta templates and recipient consent. Current job sharing is a safe prefilled share action.
4. Automated expiration is enforced when a tracked link is opened. A scheduled cleanup job could proactively mark all elapsed rows `EXPIRED`.
5. Source counters use atomic database functions after migration 031; migration must be applied before production attribution testing.

