# Staff Ops — Integration Plan

**Audience:** developers building Staff Ops inside the existing HospRecruit product.
**Date:** 29 October 2026 · Companion to [CODEBASE_REPORT.md](CODEBASE_REPORT.md).
**Status:** plan only. No feature code written.

---

## 0. The headline: most of Staff Ops already exists

Before planning new work, the honest finding from the codebase survey:

| Staff Ops capability | Already built? | Where |
|---|---|---|
| Duty rosters, shift templates | ✅ | `workforce_schedules`, `shifts`, `shift_templates`, `employee_shift_assignments` |
| Rotating weekly offs | ✅ | `employee_weekly_offs` |
| Daily attendance + biometric import | ✅ | `attendance_daily_records`, `attendance_punches`, `services/biometric_adapters.py` |
| Attendance codes (P/WO/H/CL/SL/EL/CO/HD/OD/LWP/A) | ✅ | `attendance_codes`, `services/attendance_codes_service.py` |
| Comp-off earning and expiry | ✅ | `comp_off_ledger` |
| Leave | ✅ | `routers/leave_management.py`, `leave_audit_logs` |
| Overtime | ✅ | `attendance_daily_records.overtime_minutes` |
| Month-end payroll inputs | ✅ | `routers/payroll.py`, `payroll_rules`, `services/payroll_service.py` |
| Absence replacement / shift swaps | ⚠️ partial | `shift_swap_requests` exists; no "find a replacement" flow |
| Casual (daily-wage) workers | ❌ | mentioned in analytics and the bot only; no module |
| Agency staff compliance | ❌ | no agency model at all |
| Supervisor role | ❌ | not in the role system |
| Security / Time-office role | ❌ | not in the role system |
| Split shifts | ❌ | only morning/evening/night/general |
| Hindi and South Indian languages | ❌ | six European languages, no Indian language |

**Staff Ops is therefore an extension, not a greenfield module.** The plan below
is written on that basis: reuse aggressively, add only the genuine gaps.

---

## 0b. Decisions taken (29 October 2026)

Answers to the open questions. These are now settled; the rest of this document
reflects them.

| # | Question | Decision |
|---|---|---|
| 1 | Who settles a disputed attendance mark? | **Department Head** |
| 2 | Can a Supervisor approve leave? | **Both** — they may approve, or pass it up to the Department Head |
| 3 | What can Time-office do? | View today's expected staff, record a manual punch, **mark late arrivals, flag no-shows** |
| 4 | Candidate documents on hire | **Copy** them to the employee record |
| 5 | Two API prefixes | **Agreed** — new work under `/api/v1/staff-ops/`, existing prefixes unchanged |
| 6 | Audit log | **New log for new features only** — the nine existing audit tables stay as they are |
| 7 | Spanish/French/German/Italian/Portuguese | **Remove them** |
| 8 | Language choice | **Per person**, not per hotel |
| 9 | WhatsApp replies, payslips, letters in 5 languages | **Yes** |
| 10 | Casual worker pay | **Configurable** — offer every option and let the hotel choose |
| 11 | Agency staff wages | **Not calculated** — the agency invoices the hotel; we track contracts and compliance only |
| 12 | Fix `Asia/Kolkata` timezone default | **Yes**, as part of step 0 |

---

## 0c. Progress as of 4 November 2026

This plan was written on 29 October. What has actually been built since:

### Done, with working code
| Area | What exists |
|---|---|
| **Roles** (step 1) | `SUPERVISOR` + `TIME_OFFICE` in `rbac_service.py` **and** migration `066`. 30 tests, including one that parses the migration so the Python matrix and the RLS function cannot drift |
| **Languages** (step 4) | 36 locale files (en/hi/te/ta/kn × 7 namespaces, 135 keys), `staffOpsI18n.ts`, `useStaffOpsTranslation`, `format.ts`, `staff-ops-fonts.css`, `LanguagePicker`, `LanguageGate`, 3 translator scripts, `users.preferred_language`. Verified at 360px in all five languages |
| **Exit revokes access** | `rbac_service` + migration `068`. Per-request, so it takes effect on the next call |
| **Business dates** | `app/core/business_date.py`; 3 Celery workers fixed (they were wrong on *every* run) |
| **Migration ordering** | `069_migration_tracking.sql`, preflight guards, `CHECK_APPLIED.sql`, `README.md` |

### Schema built, no code yet
Migrations `062`–`064` created **13 Staff Ops tables**. **No backend code reads
or writes any of them** — the only Staff Ops router is `staff_ops_i18n.py`.

`staff_ops_designations` · `staff_ops_employee_profiles` ·
`staff_ops_employee_documents` · `staff_ops_agencies` ·
`staff_ops_agency_monthly_compliance` · `staff_ops_ot_records` ·
`staff_ops_shift_offers` · `staff_ops_shift_offer_recipients` ·
`staff_ops_casual_workers` · `staff_ops_casual_engagements` ·
`staff_ops_settings` · `staff_ops_audit_log` · `staff_ops_month_close`

> **The main risk right now is this gap.** Schema is cheap to write and easy to
> get subtly wrong; only code exercises it. Nothing has yet inserted a single
> row into any of these tables, so the constraints, RLS policies and no-delete
> rules are unverified against real use.

### Not started
`properties.staff_ops_enabled` exists but **nothing reads it**, so the feature
flag does not yet gate anything. Likewise `staff_ops_audit_log` has no service
writing to it, and the hire → employee conversion has a `candidate_id` column
but no conversion code.

---

## 1. Reuse list

### Authentication — reuse as-is, no changes
| What | File |
|---|---|
| JWT verification (HS256 against `SUPABASE_JWT_SECRET`) | `backend/app/core/security.py` |
| Supabase client DI | `backend/app/core/dependencies.py` |
| Manager login (email + password) | `frontend/src/pages/AuthPage.tsx` |
| Staff login (phone OTP, `+91` validated) | `frontend/src/pages/EmployeeLogin.tsx` |
| Backend OTP issue/verify, phone normalisation | `backend/app/services/otp_service.py` |
| Token attach + 401 refresh + `X-Property-ID` header | `frontend/src/lib/api.ts` |
| Session state | `frontend/src/lib/AuthContext.tsx` |

Staff Ops needs **no new login path**. Supervisors and Time-office staff sign in
the same way managers do; staff use the existing phone OTP.

### Users and employees — reuse the `users` table
There is **no separate `employees` table**. An employee is a `users` row:
37 tables declare `employee_id UUID REFERENCES users(id)`.

`users` already carries the employee fields Staff Ops needs:

```
id, org_id, email, full_name, role          -- 000_auth_setup.sql
phone                                        -- 011_retention_bonus_payout.sql
active_property_id                           -- 028_hotel_multi_property_management.sql
department_id                                -- (RBAC migration)
employee_code, job_title, employment_type,
employment_status, joining_date, manager_id  -- 035_employee_360.sql
```

**Gap:** there is no `photo_url` column. Section 3 needs one.

### Roles and permissions — reuse the engine, add two roles
| What | File / object |
|---|---|
| Canonical roles, aliases, permission matrix | `backend/app/services/rbac_service.py` |
| Request-time check | `build_access_context()` → `authorize(ctx, "perm", property_id=…)` |
| Database enforcement | RLS helpers `current_user_org_id()`, `has_property_access()`, `rbac_has_permission()` |
| Frontend gating | `frontend/src/lib/RBACContext.tsx`, `components/ProtectedRoute.tsx` |

### Hotels and organisations — reuse, no schema change
`organizations` → `properties` → `property_departments` + `property_memberships`.
Active hotel flows through `users.active_property_id` and the `X-Property-ID`
header, surfaced by `frontend/src/lib/PropertyContext.tsx`.

### UI — reuse the shell
`components/AppLayout.tsx` (nav + property switcher), `components/ProtectedRoute.tsx`,
`components/ui/*` (shadcn/Radix primitives), Tailwind tokens in `index.css`,
`lucide-react` icons, `recharts`.

> Do **not** add MUI usage. Two component systems already ship; Staff Ops should
> use shadcn/Radix only.

### Notifications — reuse, extend one abstraction
| Channel | File |
|---|---|
| WhatsApp (Twilio + Meta Cloud parser) | `backend/app/routers/whatsapp.py`, `services/hr_bot_service.py`, `services/command_parser.py` |
| SMS | Twilio, via the same gateway |
| Email | `backend/app/services/email_service.py` (raw `smtplib`) |

The WhatsApp HR bot already handles leave, payslip, shift and complaint commands
in English and Hindi. Staff Ops roster and replacement messages should be new
**commands on the existing bot**, not a second bot.

### File storage — reuse as-is
`backend/app/services/s3_service.py` — presigned uploads to S3 `ap-south-1`,
KMS/AES256 encryption, `local://` sandbox fallback.
`backend/app/services/data_localization.py` enforces India residency at startup
and bars Aadhaar/PAN/biometrics from leaving the country. Staff Ops documents
(agency contracts, ID proofs) go through this path unchanged.

### i18n — reuse the library, replace the content
`frontend/src/i18n.ts` wires `i18next` + `react-i18next` + browser language
detection. Keep the wiring; the resources themselves must be rebuilt (section 7).

---

## 2. Roles

Six of the seven requested roles already exist. **Two are genuinely new.**

| Requested | Existing canonical role | Action |
|---|---|---|
| Owner | `OWNER` | reuse |
| General Manager | `GENERAL_MANAGER` | reuse |
| HR | `HR_MANAGER` (+ `GROUP_ADMIN_HR` for multi-hotel HR) | reuse |
| Department Head | `DEPARTMENT_HEAD` | reuse |
| **Supervisor** | — | **add** |
| Staff (employee) | `EMPLOYEE` | reuse |
| **Security / Time office** | — | **add** |

### How to add them
Three edits in `backend/app/services/rbac_service.py`, plus RLS is unaffected
because policies check *permissions*, not role names:

1. `PERMISSION_MATRIX` — add `SUPERVISOR` and `TIME_OFFICE` entries.
2. `ROLE_ALIASES` — map the spellings people will actually store
   (`supervisor`, `shift_incharge`, `captain`; `time_office`, `security`, `gate`).
3. Nothing else. `canonical_role()` already fails closed to `CANDIDATE` for
   unknown values, so a typo cannot silently grant access.

### Proposed permissions

**SUPERVISOR** — runs a department's floor, cannot change pay.
```
attendance.read, attendance.manage      (mark and correct attendance)
leave.read, leave.manage                (may approve, or escalate — decision 2)
employees.read                          (their department only)
properties.read
```
Scoped to their `department_id` by the existing `DEPARTMENT_HEAD` branch in
`build_access_context()` — reuse that scoping rather than writing new logic.

A supervisor opening a leave request sees **two actions: Approve, or Send to
Department Head.** Escalation is a first-class outcome, not a fallback, so the
leave record needs an `escalated_to` / `decided_by` pair rather than a single
approver column. Which route a supervisor takes is their judgement; the hotel may
later constrain it by leave type through settings.

**Attendance disputes** (decision 1): when a staff member contests a mark, the
case routes to the **Department Head**, never back to the supervisor who made it.
The existing `attendance_corrections` table already models a correction request
with an approver — reuse it, pointing the approver at the Department Head.

**TIME_OFFICE** — the staff entrance desk.
```
attendance.read                         (today's expected staff list)
attendance.manage                       (manual punch; mark late; flag no-show)
employees.read                          (name + photo to verify identity)
```
Per decision 3 they may **mark a late arrival and flag someone who never showed
up**. Both write to attendance, so both are audited like any other attendance
change. They still have no leave, payroll or roster access.

A no-show flag is a *signal*, not a verdict — it marks the day for the
Department Head to resolve, rather than directly setting unpaid absence. This
keeps pay decisions with the people accountable for them.

---

## 3. Link with recruiting

### What "Hired" means today
There is **no automated hire → employee conversion**. `candidates.pipeline_stage`
and `applications.status` reach `HIRED`, and `services/india_onboarding_service.py`
generates appointment letters from a `candidate_id`, but nothing creates the
employee record.

### Proposed conversion
Because an employee *is* a `users` row, converting a hire means:

1. Create a Supabase `auth.users` entry for their mobile number (so they can log
   in with the existing phone OTP).
2. Insert the matching `users` row.
3. Insert a `property_memberships` row binding them to the hotel, department and
   role.
4. Record the link so the two records stay traceable.

### Field mapping

| Candidate source | Employee target | Note |
|---|---|---|
| `candidates.first_name` + `last_name` | `users.full_name` | |
| `candidates.phone` | `users.phone` | already E.164-normalised by `otp_service` |
| `candidates.email` | `users.email` | optional; many staff have none |
| job title / `job_roles.title` | `users.job_title` | |
| offer joining date | `users.joining_date` | |
| — | `users.employment_type` | `FULL_TIME` / `CASUAL` / `AGENCY` / `TRAINEE` |
| — | `users.employee_code` | generated; unique per org |
| — | `users.role` | `EMPLOYEE` |
| candidate photo | **`users.photo_url` — column does not exist** | must be added |
| `candidate_documents` | **copied** to the employee (decision 4) | originals stay on the candidate record for recruiting history |

### New tables needed

```sql
-- Traceability both ways: which candidate became which employee.
staff_ops_hire_conversions (
  id, org_id, property_id,
  candidate_id  -> candidates(id),
  application_id -> applications(id),
  employee_id   -> users(id),
  converted_by  -> users(id),
  converted_at, source  -- 'RECRUITING' | 'DIRECT' | 'CASUAL_POOL'
)

-- Daily-wage workers who are not permanent employees.
staff_ops_casual_pool (
  id, org_id, property_id,
  employee_id -> users(id),        -- still a users row, employment_type='CASUAL'
  day_rate_inr, skills, preferred_departments,
  availability, last_worked_on, rating, is_active
)
```

Copying rather than moving means a document exists twice in S3. That is
deliberate: recruiting must keep its audit trail intact, and an employee's
document set must not change when a candidate record is purged under DPDP
retention. The copy records `source_document_id` so the lineage is traceable.

**Casual-worker candidates** skip the full onboarding: a candidate flagged as
casual converts straight into `staff_ops_casual_pool` with
`employment_type = 'CASUAL'` and no appointment letter.

### Casual worker pay — configurable (decision 10)
Every option is offered and the hotel picks, stored in `staff_ops_settings`:

| Setting | Options |
|---|---|
| `casual_payment_mode` | `IN_PAYROLL_RUN` · `SEPARATE_DAILY` · `SEPARATE_WEEKLY` |
| `casual_rate_basis` | `PER_DAY` · `PER_SHIFT` · `PER_HOUR` |
| `casual_leave_accrual` | `NONE` · `STATUTORY_ONLY` · `SAME_AS_PERMANENT` |
| `casual_payout_channel` | `CASH` · `BANK_TRANSFER` · `RAZORPAY_PAYOUT` |

`RAZORPAY_PAYOUT` can reuse the existing Node payout service in `services/`.
Defaults should be the most common Indian practice (`SEPARATE_DAILY`,
`PER_SHIFT`, `NONE`, `CASH`) but nothing is hard-coded.

### Agency staff — compliance only, no wage calculation (decision 11)
The agency invoices the hotel directly. Staff Ops therefore **never computes
agency worker pay** and agency workers are **excluded from payroll runs**.
What is tracked:

```sql
staff_ops_agencies (
  id, org_id, property_id, name, gstin, pan,
  contact_name, contact_phone, contract_start, contract_end,
  licence_number, licence_expiry,      -- Contract Labour Act registration
  is_active
)

staff_ops_agency_workers (
  id, org_id, property_id,
  agency_id -> staff_ops_agencies(id),
  employee_id -> users(id),            -- employment_type='AGENCY'
  deployed_from, deployed_to, department_id, is_active
)

staff_ops_agency_compliance_docs (
  id, org_id, agency_id, doc_type,     -- PF_CHALLAN | ESI_CHALLAN | LICENCE | POLICE_VERIFICATION | WAGE_REGISTER
  document_url, period_month, expires_on,
  verified_by -> users(id), verified_at, status
)
```

Agency workers still appear on rosters and attendance — the hotel needs to know
who is on the floor — they simply never reach the payroll calculation.

### Important constraint
Recruiting screens must keep working unchanged. The conversion is **additive** —
it reads `candidates` and writes new rows. No existing recruiting table is
modified.

---

## 4. Folder, naming and route conventions

### Recommendation: do **not** create `src/modules/staff-ops/`

The repo is flat — 55 files in `routers/`, 82 in `services/`, 63 in `pages/`.
More importantly, **half of Staff Ops already lives in that flat structure**
(`routers/attendance.py`, `leave_management.py`, `payroll.py`,
`workforce_schedules.py`). A `modules/staff-ops/` folder would split one domain
across two conventions and make "where does this go?" ambiguous forever.

**Proposed instead — prefix new files, leave existing ones alone:**

```
backend/app/routers/staff_ops_casual.py        new
backend/app/routers/staff_ops_agency.py        new
backend/app/services/staff_ops_casual_service.py
backend/app/services/staff_ops_roster_service.py
backend/tests/test_staff_ops_*.py
frontend/src/pages/StaffOps*.tsx               e.g. StaffOpsCasualPool.tsx
supabase/migrations/061_staff_ops_*.sql        continue the numbering
```

### API prefix
Mount **new** Staff Ops routers under `/api/v1/staff-ops/…`.
Do **not** move the existing `/api/v1/attendance`, `/api/v1/leave`,
`/api/v1/payroll` or `/api/v1/workforce-schedules` prefixes — that would break
the employee PWA and every existing frontend call for no benefit.

> This leaves Staff Ops split across two prefixes. **Agreed (decision 5):** the
> cost of a tidy prefix would be a breaking change to the shipped employee PWA,
> which is not worth paying.

### Table prefix
`staff_ops_` for genuinely new tables (`staff_ops_casual_pool`,
`staff_ops_agency_contracts`). Existing tables keep their names.

---

## 5. Navigation

`components/AppLayout.tsx` supports two shapes: a flat `NAV_LINKS` list and
`FEATURE_GROUPS` (a `NavGroup` with a label, icon and `items[]`). A per-path
permission map gates visibility.

**Proposal — add one collapsible group, move nothing:**

```ts
const STAFF_OPS_GROUP: NavGroup = {
  label: 'Staff Ops',
  icon: <ClipboardList className="w-4 h-4" />,
  items: [
    { label: 'Duty Roster',      to: '/staff-ops/roster' },
    { label: 'Today at a Glance', to: '/staff-ops/today' },
    { label: 'Casual Pool',      to: '/staff-ops/casual' },
    { label: 'Agency Staff',     to: '/staff-ops/agency' },
    { label: 'Replacements',     to: '/staff-ops/replacements' },
  ],
}
```

Existing Attendance, Leave and Payroll links **stay where they are**. Recruiting
screens are untouched. Each new path gets a permission-map entry and a
`<ProtectedRoute permission="…">` wrapper, exactly like every current route.

**Staff-facing screens** go into the existing employee PWA (`/employee-app`,
`pages/EmployeeApp.tsx`) rather than the manager console — that is already
installable, already mobile-first, and already the thing staff log into.

**Time-office screen** (`/staff-ops/today`) is a single read-only list of who is
expected at the staff entrance today. It should be reachable without the full nav.

---

## 6. Feature flag — per hotel

### Reuse the existing per-property settings mechanism
`properties` carries JSONB settings columns, mapped in
`routers/hotel_management.py`:

```python
SETTING_FIELDS = {
    "hr": "hr_settings",
    "payroll": "payroll_settings",
    "compliance": "compliance_settings",
    "branding": "branding_settings",
}
```

**Proposal — two levels, matching the `BILLING_ENABLED` precedent set in
`core/config.py`:**

1. **Per hotel (primary):** add `"staff_ops": "staff_ops_settings"` to
   `SETTING_FIELDS` and a `staff_ops_settings JSONB` column on `properties`,
   holding `{"enabled": false, …}` plus the hotel's labour-law settings.
   Default **off**, so enabling Staff Ops is an explicit per-hotel decision.
2. **Per deployment (kill switch):** `STAFF_OPS_ENABLED: bool = False` in
   `core/config.py`, gating router registration in `main.py` — the same shape
   as `BILLING_ENABLED`.

The frontend reads the per-hotel flag through `PropertyContext` (which already
loads the active property) and hides the nav group when off. Because the backend
also checks it per request, a stale frontend cannot reach disabled endpoints.

---

## 7. Languages

**Target:** English, Hindi, Telugu, Tamil, Kannada.

**Current state:** `frontend/src/i18n.ts` defines **en, es, fr, de, it, pt** —
six European languages left over from the pre-India product — with all strings
inline in one 254-line file, one namespace (`candidate`), used by 2 of 63 pages.
Hindi exists only as hard-coded ternaries in components and literals in Python.

### Proposed work
1. Extract resources out of `i18n.ts` into per-language files:
   `src/locales/{en,hi,te,ta,kn}/{common,staffOps,attendance,leave}.json`.
2. **Delete es/fr/de/it/pt** (decision 7). They serve no Indian hotel and their
   presence makes the language picker misleading.
3. Set `supportedLngs: ['en','hi','te','ta','kn']`, `fallbackLng: 'en'`.
4. Staff Ops ships **no hard-coded user-facing string**. Every label goes through
   `t()` from day one — this is cheap now and expensive to retrofit.
5. **Per person** (decision 8): add `users.preferred_language VARCHAR(5)`
   defaulting to `'en'`. A Tamil-speaking steward gets Tamil in a Bengaluru
   hotel. The staff member sets it themselves on first login; the browser
   detector only supplies the initial guess.
6. Scripts: Devanagari, Telugu, Tamil and Kannada all render from system fonts on
   modern Android, but labels run **30–50% longer** than English. Buttons and
   table headers must not be fixed-width.
7. **Server-generated text is translated too** (decision 9): WhatsApp bot
   replies, payslip PDFs and appointment letters, in all five languages, chosen
   by the recipient's `preferred_language`. This is the largest single piece of
   the language work and needs its own backend catalogue — currently those
   strings are hard-coded English/Hindi literals across
   `services/hr_bot_service.py`, `services/india_onboarding_service.py` and
   `services/payslip_pdf.py`.

   Two practical constraints:
   - **`reportlab` cannot render Devanagari, Telugu, Tamil or Kannada with its
     built-in fonts.** A Unicode TTF (e.g. Noto Sans for each script) must be
     registered and embedded, which increases PDF size.
   - **WhatsApp template messages must be pre-approved by Meta per language.**
     Five languages means five approvals per template, with lead time. Free-form
     replies inside the 24-hour service window are unaffected.

---

## 8. Global rules and how each is enforced

| Rule | Status | Mechanism |
|---|---|---|
| **Hotel data separation** | ✅ already enforced | RLS on every table: `org_id=current_user_org_id() AND has_property_access(property_id)`. New Staff Ops tables must carry `org_id` + `property_id` and copy this policy block. |
| **Labour-law values are settings** | ⚠️ mostly | `payroll_rules` is per org *and* per property with `effective_from` dating — correct. But module constants survive: `EPF_EMPLOYER_CONTRIB_PCT` in `india_compliance_service.py`; `OT_RATE_MULTIPLIER`, `MAX_OT_PER_DAY_H`, `DAILY_STANDARD_HOURS` in `labour_compliance_service.py`. Staff Ops must read from settings, never constants. |
| **Audit log on attendance/roster/leave/pay** | ⚠️ fragmented | Nine audit tables already exist. **Decision 6: leave them alone.** Staff Ops adds one `staff_ops_audit_log` (actor, action, entity, entity_id, old_value, new_value, property_id, at) used by **new** features only. Trade-off accepted: "every change is audited" remains true per-feature but still cannot be answered from a single table — a reporting view over all ten can be added later if an auditor asks. |
| **Dates DD-MM-YYYY** | ❌ no standard | Pages format ad hoc. Needs one shared formatter. |
| **INR, Indian digit grouping (1,00,000)** | ⚠️ partial | `Intl.NumberFormat('en-IN')` used in places, not consistently. |
| **Timezone Asia/Kolkata** | 🔧 fix in step 0 | `properties.timezone` defaults to `'UTC'` (`004_seasonal.sql`) and early tables use `TIMESTAMP` not `TIMESTAMPTZ`. **Decision 12: fix the default to `Asia/Kolkata`** and backfill existing rows before any roster work. Critical because a 22:00–06:00 night shift books to its **start** date, which is only correct if the hotel's timezone is right. |
| **Mobile-first** | ✅ foundation exists | Employee PWA complete: `manifest.webmanifest`, `sw.js`, offline page, registered in `main.tsx` (production only). |

**Proposed shared helpers** (new, small, used by every Staff Ops screen):
`frontend/src/lib/format.ts` — `formatDate()` (DD-MM-YYYY), `formatINR()`
(en-IN grouping), `formatTime()`, all pinned to `Asia/Kolkata`.

---

## 9. Risks

1. **Nothing is in version control.** One commit, one tracked file; ~72,000 lines
   untracked. Building a module this size on top of that is the single biggest
   risk here. *Fix before writing Staff Ops code.*
2. **54 failing tests** mask new regressions — a Staff Ops break would hide in the
   noise. Root cause is five stale duplicate `TableChain` test doubles.
3. **No CI and no deploy config**, so nothing verifies the module automatically.
4. **Timezone default is `UTC`** on an India-only product. Night shifts crossing
   midnight will be wrong until this is corrected, and attendance is the heart of
   Staff Ops.
5. **Audit requirement vs. nine scattered audit tables** — "every change is
   audited" cannot be demonstrated today without a unifying layer.
6. **Two job models** (`jobs`, `job_roles`), neither carrying `property_id`.
   Hire-to-employee conversion must pick one and will inherit the ambiguity.
7. **`users` has no `photo_url`**, which the hire conversion requires.
8. **Hindi is not merely missing — the i18n content is the wrong six languages.**
   Five Indian languages is a real workstream, not a config change.
9. **Scope.** Casual workers, agency compliance, split shifts, replacements,
   two new roles and five languages is a large surface. Sequencing matters more
   than breadth.

---

## Suggested build order

Each step is shippable on its own and sized for the "one feature at a time" rule.

| # | Feature | Status (4 Nov 2026) |
|---|---|---|
| 0 | Commit the repo to git · fix the 54 tests · fix the `Asia/Kolkata` default | ⚠️ **partial** — timezone fixed in `064`; **git still untracked, 54 tests still failing** |
| 1 | `SUPERVISOR` + `TIME_OFFICE` roles, approve-or-escalate on leave | ✅ **done** — `rbac_service.py` + `066`, 30 tests |
| 2 | Per-hotel Staff Ops feature flag | 🔶 **schema only** — `properties.staff_ops_enabled` and `staff_ops_settings` exist; nothing reads them |
| 3 | `staff_ops_audit_log` for new features | 🔶 **schema only** — no service writes to it |
| 4 | i18n: five languages, picker, formats, fonts | ✅ **done** — 36 locale files, verified at 360px |
| 5 | Hire → Employee conversion | 🔶 **schema only** — `candidate_id` column exists, no conversion code. **`users.photo_url` still missing** |
| 6 | Casual worker pool + the four pay settings | 🔶 **schema only** |
| 7 | Agency compliance tracking | 🔶 **schema only** |
| 8 | Absence replacement flow | 🔶 **schema only** (`shift_offers` + recipients) |
| 9 | Time-office screen: late marks, no-show flags | ⬜ not started |
| 10 | Server-side translation: bot replies, payslip PDFs, letters | ⬜ not started — resolver and SMS segment maths ready |
| 11 | Telugu/Tamil/Kannada · split shifts | 🔶 translations exist (unreviewed); split shifts not started |

**Suggested next step:** pick one 🔶 row and write the service, router, tests and
screen for it end to end. Step 2 (the feature flag) is the smallest and unblocks
shipping everything else dark; step 5 is the one that connects recruiting to
Staff Ops and makes the module useful at all.
