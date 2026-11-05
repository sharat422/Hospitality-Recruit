# Staff Ops — Pending Tasks

Running backlog, one section per prompt. Newest at the top. A task leaves this
file only when it is done and verified, or when you decide to drop it.

**Legend:** 🔴 blocker · 🟠 needed soon · 🟡 nice to have · ⏳ waiting on you

---

## Prompt 5 — Languages (en, hi, te, ta, kn) · 29 Oct 2026

### Done
- 35 locale files, 7 namespaces × 5 languages, 135 keys each
- Bundle registration that leaves `src/i18n.ts` untouched
- `useStaffOpsTranslation` with English fallback + missing-key recording
- `format.ts` — Latin digits, Indian grouping, DD-MM-YYYY, 12-hour IST
- `staff-ops-fonts.css` — Noto Sans per script, Indic line-height, 360px rules
- `LanguagePicker` — first-login and profile variants
- `users.preferred_language` + `/api/v1/staff-ops/me/language`
- `check-keys.mjs`, `export-csv.mjs`, `import-csv.mjs` — all verified working
- 32 backend tests for language resolution and SMS segment cost

### Decisions taken (29 Oct 2026, follow-up)
| # | Question | Decision |
|---|---|---|
| 2 | es/fr/de/it/pt | **Excluded from Staff Ops**, left untouched in recruiting. No code change needed — `STAFF_OPS_LANGUAGES` only ever listed the five. |
| 3 | Machine translations | **Keep flagged** `needs_review` indefinitely until a native speaker approves |
| 4 | Wire the picker | **Yes** — done: first-login gate + profile section |
| 5 | AM/PM | **Latin AM/PM only**; local meridiem words removed from `format.ts` |

### Pending
| | Task | Note |
|---|---|---|
| 🔴 | **Native-speaker review of all 540 strings** | Decision 3: stays flagged. Telugu and Kannada are highest risk — vowel-sign combinations are easy to get subtly wrong. |
| 🟠 | Replace the proposed glossary with yours | The starter glossary did not come through in the prompt |
| 🟠 | Visual check at 360px in Tamil | CSS rules written but unverified on a real screen — the only wired screens so far are the picker and profile |
| 🟠 | Backfill `preferred_language` for existing users | Currently NULL for everyone, so all fall back to hotel state and every existing user sees the picker once |
| ⏳ | **Scope the first-login gate?** | It currently fires for *every* signed-in user, recruiters included. See open questions. |
| 🟡 | Add `check-keys --ci` to a CI pipeline | No CI exists yet |
| 🟡 | Frontend unit tests for `format.ts` | Repo has zero frontend tests; would be the first |

### Deferred to later prompts
| | Task | Why |
|---|---|---|
| 🟠 | Server-side translation: WhatsApp replies, payslip PDFs, appointment letters | PLAN.md step 10. `staff_ops_language.py` has the resolver and SMS segment maths ready |
| 🟠 | Embed Noto TTFs in `reportlab` | PDFs cannot render Indic scripts without this |
| 🟠 | Meta template approval, 5 languages × each template | Long external lead time — start early |

---

---

## Business dates not in the hotel's calendar — 50 sites remain · 03 Nov 2026

**Corrected count:** an earlier note said 16 sites. The real figure is ~54,
because the first grep looked only for `datetime.now(timezone.utc).date()` and
missed ~38 uses of `date.today()`. Four are now fixed.

A business date ("has this expired?", "what is today's roster?") must be the
hotel's calendar, not UTC. Between **00:00 and 05:30 IST the UTC date is still
yesterday**, so `datetime.now(timezone.utc).date()` is wrong for 5h30m a day.

`app/core/business_date.py` now provides `business_today()`, `business_now()`,
`days_until()` and `business_date_range()`. One site is converted; these are not.

### ✅ Fixed 03 Nov 2026 — the three Celery workers
Each fired between 03:30 and 04:00 IST = **22:00–22:30 UTC the previous day**,
so `today` was yesterday on *every single run*. All now use `business_today()`.

| File | Was | Effect of the bug |
|---|---|---|
| `workers/fssai_expiry.py` | line 93 | FSSAI expiry alerts measured against the wrong day |
| `workers/identity_document_expiry.py` | line 71 | Same, for ID documents |
| `workers/dpdp_retention.py` | line 27 | Retention cutoff a day early — documents deleted a day sooner than policy allowed |

`updated_at` / `sent_at` writes were deliberately **left as UTC**: those are
timestamps, not business dates, and changing them would be the opposite bug.

### 🔴 Two more Celery workers, same beat window, different spelling
`date.today()` reads the **machine's** timezone: correct on an IST server,
wrong on a UTC one. My first grep searched only for the `timezone.utc` form
and missed these.

| File | Line | Note |
|---|---|---|
| `workers/certification_expiry.py` | 102 | Same 03:30 IST job family as fssai_expiry |
| `workers/scheduled_reports.py` | 15 | Runs every 15 minutes; report period boundaries |

### 🟠 Wrong for 5h30m daily — user-visible
| File | Line | Effect |
|---|---|---|
| `services/command_parser.py` | 305 | "tomorrow"/"kal" in a WhatsApp leave request resolves to the wrong date overnight |
| `services/hr_bot_service.py` | 753, 1502, 1504 | "my shifts this week" over WhatsApp |
| `services/employee_self_service.py` | 17 | Shift list in the employee app |
| `routers/hr_bot.py` | 762 | Bot's idea of today |

### 🟡 Lower risk — review individually
| File | Line |
|---|---|
| `services/india_compliance_service.py` | 157, 624 |
| `services/dpdp_service.py` | 135, 200, 405 |
| `services/onboarding_orchestration_service.py` | 71 |

> `routers/analytics.py:338` and `services/attendance_service.py` already do
> this correctly — the right pattern exists in the repo, it just was not used
> consistently.


## From PLAN.md build order — not yet started

| Step | Task | |
|---|---|---|
| 0 | **Commit the repo to git** | 🔴 ~72k lines untracked, 1 commit, 1 tracked file |
| 0 | **Fix the 54 failing tests** | 🔴 five stale duplicate `TableChain` doubles |
| 0 | **Fix `properties.timezone` default to Asia/Kolkata** | 🔴 decision 12; currently `'UTC'` |
| 1 | Add `SUPERVISOR` + `TIME_OFFICE` roles | 🟠 everything else gates on these |
| 2 | Per-hotel Staff Ops feature flag (`staff_ops_settings`) | 🟠 |
| 3 | `staff_ops_audit_log` for new features | 🟠 decision 6 |
| 5 | Hire → Employee conversion, `users.photo_url`, document copy | 🟠 |
| 6 | Casual worker pool + 4 pay settings | 🟠 largest gap |
| 7 | Agency compliance tracking (no wage calculation) | 🟠 |
| 8 | Absence replacement flow | 🟡 needs step 6 |
| 9 | Time-office screen: late marks, no-show flags | 🟡 |
| 11 | Split shifts | 🟡 |

---

## Standing risks (from CODEBASE_REPORT.md)

| | Risk |
|---|---|
| 🔴 | Nothing in version control — no restore point for the whole codebase |
| 🔴 | 54 failing tests mask new regressions |
| 🟠 | No CI, no Dockerfile, no deploy config |
| 🟠 | Hard-coded statutory values: `EPF_EMPLOYER_CONTRIB_PCT`, `OT_RATE_MULTIPLIER`, `MAX_OT_PER_DAY_H`, `DAILY_STANDARD_HOURS` |
| 🟠 | Two job models (`jobs`, `job_roles`), neither carrying `property_id` |
| 🟡 | Two classes named `BillingService` in different modules |
| 🟡 | `App.tsx` and the two billing pages are unrouted dead code |
