# Staff Ops — Database Design (for review)

**Status:** APPROVED 29 Oct 2026. Step 1 of 4 written
(`062_staff_ops_core.sql`); steps 2–4 pending.
**Date:** 29 October 2026 · Follows [PLAN.md](PLAN.md).

---

## 0. Two corrections to the brief

### There is no ORM and no migration tool
The brief says "using our existing ORM and migration tool". There isn't one:

- `sqlalchemy` and `alembic` are declared in `pyproject.toml`, but only **3
  files** import SQLAlchemy (all Stripe/billing) and there is **no `alembic/`
  directory**. `backend/app/models/` is empty.
- All real data access is the Supabase query builder:
  `supabase.table("x").select("*").eq("org_id", ctx.org_id).execute()`
- Migrations are **hand-written SQL** in `supabase/migrations/`, numbered
  `000`–`061`, applied manually through the Supabase SQL editor.

So "the migration tool" = a new numbered `.sql` file following the existing
house style. I'll continue that unless you want Alembic introduced, which
would be a much larger change.

### "hotels" is `properties`, and "employees" is `users`
These already exist and must not be duplicated:

- **`properties`** is the hotel table. It already has `room_count`, `state`,
  `city`, `timezone`, `star_rating`, address and contact fields.
- **`users` is the employee table.** **37 tables** declare
  `employee_id UUID REFERENCES users(id)`. Creating a separate `employees`
  table would fork the identity model and break attendance, leave, payroll,
  performance and exit — all of which point at `users`.

---

## 1. What already exists

**About 60% of the requested tables are already built.** Mapping:

| You asked for | Already exists as | Verdict |
|---|---|---|
| hotels extension | `properties` — `room_count`, `state`, `timezone` all present | extend: 1 column |
| departments | `property_departments` (code, name, head_user_id, budgeted_headcount) | reuse |
| designations | — `users.job_title` is free text | **new** |
| employees | **`users`** (+ `employee_code`, `job_title`, `employment_type`, `employment_status`, `joining_date`, `manager_id`, `department_id`, `active_property_id`, `phone`, `preferred_language`) | extend |
| employee_documents | `candidate_documents` exists, but for candidates only | **new** |
| shift_templates | `shift_templates` | reuse |
| rosters | `workforce_schedules` | reuse |
| roster_entries | `shifts` + `employee_shift_assignments` | reuse |
| min_staffing_rules | `department_staffing_ratios` | reuse |
| punches | `attendance_punches` | reuse |
| attendance_days | `attendance_daily_records` | reuse |
| leave_types | `leave_types` | reuse |
| leave_balances | `leave_balances` | reuse |
| leave_requests | `leave_requests` | **extend** — see 3.1 |
| holidays | `property_holidays` | reuse |
| comp_offs | `comp_off_ledger` | reuse |
| ot_records | — only an `overtime_minutes` column | **new** |
| shift_offers / recipients | `shift_swap_requests` is person-to-person, not a broadcast | **new** |
| casual_workers / engagements | — | **new** |
| agencies / agency_monthly_compliance | — | **new** |
| occupancy_forecast | `pms_occupancy_forecasts` | reuse |
| settings | `properties.*_settings` JSONB, no key/value/valid_from | **new** |
| audit_log | 9 feature-specific audit tables; decision 6 says add one for new features | **new** |
| month_close | `payroll_runs` is payroll-only | **new** |

**Already satisfied without any work:**
- *Aadhaar last 4 only* — `india_identity_verifications.aadhaar_last4 CHAR(4)`
  with a DB CHECK `~ '^[0-9]{4}$'`, plus PAN masked `^[A-Z]{5}\*{4}[A-Z]$`
  (migration 043).
- *UAN / ESI numbers* — `epf_esic_registrations.epf_uan`,
  `.esic_ip_number`. **But it is keyed to `candidate_id`, not employee** —
  see open question 4.

---

## 2. New tables (12)

Every one carries `org_id` **and** `property_id`, with the standard RLS block.

### 2.1 `staff_ops_designations`
`users.job_title` is free text, so "Steward", "steward" and "F&B Steward" are
three different jobs and no report can group them.

```
id, org_id, property_id
department_id    -> property_departments(id)
code             VARCHAR(40)    -- STEWARD, HK_ATTENDANT, FO_AGENT
name             VARCHAR(120)
grade            VARCHAR(20)    -- for seniority and wage bands
default_shift_template_id -> shift_templates(id)   NULL
is_active, created_at, updated_at
UNIQUE (property_id, code)
```

### 2.2 `staff_ops_employee_profiles`
The Staff Ops fields that do **not** belong on `users`. Kept separate so the
recruiting side of `users` is untouched and so this row can carry its own RLS.

```
id, org_id, property_id
employee_id      -> users(id)                    UNIQUE
candidate_id     -> candidates(id)      NULL     -- set when hired via recruiting
designation_id   -> staff_ops_designations(id)   NULL
staff_type       VARCHAR(20) CHECK IN (PERMANENT, TRAINEE, INDUSTRIAL_TRAINEE, AGENCY, CASUAL)
agency_id        -> staff_ops_agencies(id)       NULL  -- required when staff_type=AGENCY
status           VARCHAR(20) CHECK IN (ACTIVE, ON_NOTICE, LEFT, ABSCONDING)
joining_date     DATE
leaving_date     DATE
notice_start_date DATE
default_weekly_off SMALLINT CHECK 0..6           -- 0=Sunday
default_shift_template_id -> shift_templates(id) NULL
skills           JSONB  -- [{department_id, designation_id, proficiency}]
biometric_id     VARCHAR(50)                     -- device enrolment id
supervisor_id    -> users(id)          NULL
wage_type        VARCHAR(12) CHECK IN (MONTHLY, DAILY, HOURLY, PER_SHIFT)
wage_amount_inr  NUMERIC(12,2)
uan              VARCHAR(15)
esic_ip_number   VARCHAR(20)
created_at, updated_at
CHECK (leaving_date IS NULL OR leaving_date >= joining_date)
CHECK (staff_type <> 'AGENCY' OR agency_id IS NOT NULL)
```

**Why `skills` is JSONB:** a steward who can cover Banquets and Room Service
is a short list read whole, never queried field-by-field. A join table would
be three tables and a join for something always fetched as a blob.

**Why not `users.supervisor_id`:** `users.manager_id` already exists. See
open question 2 — reuse or separate?

### 2.3 `staff_ops_employee_documents`
Reuses the existing S3 path (`services/s3_service.py`, presigned uploads,
`ap-south-1`). Mirrors `candidate_documents` rather than inventing a new
storage mechanism.

```
id, org_id, property_id
employee_id      -> users(id)
source_document_id -> candidate_documents(id) NULL  -- lineage when copied on hire
doc_type         VARCHAR(40)  -- ID_PROOF, ADDRESS_PROOF, CERTIFICATE, CONTRACT, PHOTO
document_url     TEXT         -- S3 key, never a public URL
file_name, mime_type, size_bytes
expires_on       DATE NULL
verified_by -> users(id), verified_at
status           VARCHAR(20) CHECK IN (PENDING, VERIFIED, REJECTED, EXPIRED)
uploaded_by -> users(id), created_at
```

### 2.4 `staff_ops_agencies` and 2.5 `staff_ops_agency_monthly_compliance`
Per PLAN decision 11, the agency invoices the hotel — **we never compute
agency wages.** Agency workers appear on rosters and attendance but are
excluded from payroll runs.

```
staff_ops_agencies
  id, org_id, property_id
  name, gstin VARCHAR(15), pan VARCHAR(10)
  contact_name, contact_phone, contact_email
  contract_start DATE, contract_end DATE
  clra_licence_number VARCHAR(50)      -- Contract Labour (R&A) Act
  clra_licence_expiry DATE
  is_active, created_at, updated_at

staff_ops_agency_monthly_compliance
  id, org_id, property_id
  agency_id -> staff_ops_agencies(id)
  period_year SMALLINT, period_month SMALLINT CHECK 1..12
  doc_type VARCHAR(30) CHECK IN (PF_CHALLAN, ESI_CHALLAN, WAGE_REGISTER,
                                 POLICE_VERIFICATION, LICENCE_RENEWAL)
  document_url TEXT, workers_covered INT, amount_inr NUMERIC(12,2)
  status VARCHAR(20) CHECK IN (PENDING, SUBMITTED, VERIFIED, REJECTED)
  verified_by -> users(id), verified_at, due_date DATE
  UNIQUE (agency_id, period_year, period_month, doc_type)
```

### 2.6 `staff_ops_casual_workers` and 2.7 `staff_ops_casual_engagements`
```
staff_ops_casual_workers
  id, org_id, property_id
  employee_id -> users(id)  NULL   -- NULL until they have a login
  candidate_id -> candidates(id) NULL
  full_name, phone VARCHAR(20)
  day_rate_inr NUMERIC(10,2)
  skills JSONB, preferred_departments JSONB
  availability JSONB               -- {"mon":true,...}
  last_worked_on DATE, total_shifts INT, rating NUMERIC(2,1)
  is_blacklisted BOOLEAN, blacklist_reason TEXT
  is_active, created_at, updated_at
  CHECK (employee_id IS NOT NULL OR phone IS NOT NULL)

staff_ops_casual_engagements
  id, org_id, property_id
  casual_worker_id -> staff_ops_casual_workers(id)
  work_date DATE, department_id, shift_template_id
  hours_worked NUMERIC(4,2)
  rate_basis VARCHAR(12) CHECK IN (PER_DAY, PER_SHIFT, PER_HOUR)
  amount_inr NUMERIC(10,2)
  payment_mode VARCHAR(20) CHECK IN (CASH, BANK_TRANSFER, RAZORPAY_PAYOUT)
  payment_status VARCHAR(20) CHECK IN (PENDING, APPROVED, PAID, CANCELLED)
  approved_by, approved_at, paid_at, payout_reference
  created_at, updated_at
  UNIQUE (casual_worker_id, work_date, shift_template_id)
```

A casual may exist with only a phone number — they are often hired at the gate
before any account exists. Hence `employee_id` nullable.

### 2.8 `staff_ops_ot_records`
`attendance_daily_records.overtime_minutes` records that OT *happened*. It
cannot record who authorised it, at what multiplier, or whether it was paid —
all of which a labour inspector asks for.

```
id, org_id, property_id
employee_id -> users(id)
attendance_date DATE
attendance_record_id -> attendance_daily_records(id) NULL
ot_minutes INT CHECK >= 0
ot_multiplier NUMERIC(4,2)        -- from settings, NOT hard-coded
hourly_rate_inr NUMERIC(10,2)
ot_amount_inr NUMERIC(12,2)
reason TEXT
status VARCHAR(20) CHECK IN (PENDING, APPROVED, REJECTED, PAID, CANCELLED)
requested_by, approved_by, approved_at
payroll_run_id -> payroll_runs(id) NULL
created_at, updated_at
UNIQUE (employee_id, attendance_date)
```

### 2.9 `staff_ops_shift_offers` and 2.10 `staff_ops_shift_offer_recipients`
`shift_swap_requests` is A-asks-B. This is "someone called in sick, broadcast
the gap and take the first acceptance".

```
staff_ops_shift_offers
  id, org_id, property_id
  shift_id -> shifts(id)
  department_id, designation_id
  reason VARCHAR(30) CHECK IN (ABSENCE, LEAVE, RESIGNATION, EXTRA_DEMAND, NO_SHOW)
  absent_employee_id -> users(id) NULL
  work_date DATE, offered_rate_inr NUMERIC(10,2) NULL   -- incentive if any
  status VARCHAR(20) CHECK IN (OPEN, FILLED, EXPIRED, CANCELLED)
  filled_by -> users(id) NULL, filled_at TIMESTAMPTZ
  expires_at TIMESTAMPTZ
  created_by, created_at, updated_at

staff_ops_shift_offer_recipients
  id, org_id, property_id
  offer_id -> staff_ops_shift_offers(id) ON DELETE CASCADE
  employee_id -> users(id) NULL
  casual_worker_id -> staff_ops_casual_workers(id) NULL
  channel VARCHAR(20) CHECK IN (WHATSAPP, SMS, PUSH, IN_APP)
  sent_at, delivered_at, responded_at
  response VARCHAR(20) CHECK IN (PENDING, ACCEPTED, DECLINED, NO_RESPONSE)
  UNIQUE (offer_id, employee_id, casual_worker_id)
  CHECK (employee_id IS NOT NULL OR casual_worker_id IS NOT NULL)
```

Recipients may be permanent staff **or** the casual pool — that is the point
of the replacement flow.

### 2.11 `staff_ops_settings`
Key/value with `valid_from`, so a labour-law change is a new row and last
month's payroll still recomputes with the rate that applied then. The existing
`properties.*_settings` JSONB cannot do this — it has no history.

```
id, org_id
property_id -> properties(id) NULL    -- NULL = org-wide default
key VARCHAR(80)      -- ot_multiplier, max_ot_hours_per_day, casual_payment_mode…
value JSONB
value_type VARCHAR(12) CHECK IN (NUMBER, STRING, BOOLEAN, JSON)
description TEXT
valid_from DATE, valid_to DATE NULL
created_by, created_at
UNIQUE (property_id, key, valid_from)
```

Resolution: most specific wins — property + newest `valid_from` ≤ today,
else org-wide, else the code default. **This is where every labour-law value
lives**, replacing the module constants `OT_RATE_MULTIPLIER`,
`MAX_OT_PER_DAY_H`, `DAILY_STANDARD_HOURS`, `EPF_EMPLOYER_CONTRIB_PCT`.

### 2.12 `staff_ops_audit_log` and 2.13 `staff_ops_month_close`
```
staff_ops_audit_log
  id, org_id, property_id
  actor_id -> users(id) NULL          -- NULL for system/cron actions
  action VARCHAR(40)                  -- CREATE, UPDATE, DELETE, APPROVE, REJECT, ESCALATE
  entity_type VARCHAR(60), entity_id UUID
  employee_id -> users(id) NULL       -- whose record was affected
  old_value JSONB, new_value JSONB, changed_fields TEXT[]
  reason TEXT, source VARCHAR(20)     -- WEB, MOBILE, WHATSAPP, BIOMETRIC, SYSTEM
  ip_address INET, created_at TIMESTAMPTZ
  INDEX (property_id, entity_type, entity_id, created_at DESC)
  INDEX (employee_id, created_at DESC)

staff_ops_month_close
  id, org_id, property_id
  period_year SMALLINT, period_month SMALLINT CHECK 1..12
  status VARCHAR(20) CHECK IN (OPEN, ATTENDANCE_LOCKED, CLOSED, REOPENED)
  attendance_locked_at, attendance_locked_by
  closed_at, closed_by, reopened_at, reopened_by, reopen_reason TEXT
  totals JSONB                        -- headcount, LOP days, OT hours, casual spend
  payroll_run_id -> payroll_runs(id) NULL
  UNIQUE (property_id, period_year, period_month)
```

Once a month is `CLOSED`, attendance, leave, OT and casual engagement rows for
that period are refused at the API layer. Reopening is a logged, deliberate act.

---

## 3. Changes to existing tables

### 3.1 `leave_requests` — three problems
```sql
ALTER TABLE leave_requests
  ADD COLUMN property_id UUID REFERENCES properties(id),   -- rule: every table has hotel_id
  ADD COLUMN from_date DATE,                                -- today only `leave_date`
  ADD COLUMN to_date DATE,
  ADD COLUMN days_requested NUMERIC(4,1),                   -- half days
  ADD COLUMN escalated_to UUID REFERENCES users(id),        -- PLAN decision 2
  ADD COLUMN escalated_at TIMESTAMPTZ,
  ADD COLUMN decided_by UUID REFERENCES users(id);
-- status gains ESCALATED
```
1. No `property_id` — breaks the hotel-isolation rule.
2. `leave_date` is a **single day**; a three-day leave is impossible.
3. No escalation path, which decision 2 requires.

`from_date`/`to_date` backfill from `leave_date`; the old column stays until
callers are migrated.

### 3.2 `properties`
```sql
ALTER TABLE properties
  ADD COLUMN staff_ops_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ALTER COLUMN timezone SET DEFAULT 'Asia/Kolkata';
UPDATE properties SET timezone = 'Asia/Kolkata'
 WHERE timezone IN ('UTC','') OR timezone IS NULL;
```
`room_count` and `state` already exist. Timezone fix is decision 12.

### 3.3 `users` — nothing
Everything else goes in `staff_ops_employee_profiles`, so recruiting's view of
`users` is unchanged.

---

## 4. The rules, and how each is enforced

| Rule | How |
|---|---|
| Every table has `hotel_id` | `property_id NOT NULL` on all 13 new tables (nullable only on `staff_ops_settings` for org-wide defaults) |
| Users see only their hotels | Standard RLS block: `org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('…')` |
| **Never hard-delete** attendance/leave/OT/payment | Every such table has a `status` with a CANCELLED value and **no delete path**. Enforced in the database by `CREATE RULE … ON DELETE DO INSTEAD NOTHING` on the four tables, so even direct SQL cannot drop a row. |
| Times in UTC, display IST | All timestamps `TIMESTAMPTZ` (Postgres stores UTC). Business dates stay `DATE`. Display via `frontend/src/lib/format.ts`, already pinned to `Asia/Kolkata` |
| Aadhaar last 4 only | Already enforced on `india_identity_verifications` with a CHECK. **No new table stores Aadhaar at all** |
| Encrypt bank account numbers | See open question 1 — needs your decision |

---

## 5. Seed data — one demo hotel

A separate migration so it can be skipped in production:

- 1 organisation, 1 property — *Grand Sarovar Residency, Hyderabad, Telangana*,
  120 rooms, `Asia/Kolkata`, `staff_ops_enabled = true`
  (Telangana so the language default resolves to Telugu)
- 6 departments: Front Office, Housekeeping, Kitchen, F&B Service, Engineering, Security
- 10 designations across them
- 4 shift templates: Morning 07–15, Evening 15–23, Night 23–07, General 09–18
- 12 employees: 8 permanent, 1 trainee, 1 industrial trainee, 1 agency, 1 casual
  — one supervisor, one department head, one time-office user
- 1 agency with a valid CLRA licence and 3 months of compliance docs
- 5 casual workers with varied skills and availability
- 30 days of attendance covering every code: P, WO, H, CL, SL, EL, CO, HD, OD, LWP, A
- 14 days of occupancy forecast
- Settings rows: `ot_multiplier`, `max_ot_hours_per_day`, `casual_payment_mode`

---

## 6. Migration plan — 4 files

| File | Contents |
|---|---|
| `062_staff_ops_core.sql` | designations, employee_profiles, employee_documents + RLS |
| `063_staff_ops_operations.sql` | ot_records, shift_offers, shift_offer_recipients, casual_workers, casual_engagements, agencies, agency_monthly_compliance + RLS |
| `064_staff_ops_governance.sql` | settings, audit_log, month_close, the no-delete rules, `leave_requests` and `properties` changes |
| `065_staff_ops_demo_seed.sql` | demo hotel (skippable) |

---

## 7. Decisions taken (29 Oct 2026)

| # | Question | Decision | Effect |
|---|---|---|---|
| 1 | Bank encryption | **Approved option (c)** — never store the account number | `bank_account_last4 CHAR(4)` + `payout_token`; no `pgcrypto` needed |
| 2 | `supervisor_id` vs `manager_id` | **Both, different people** | Separate `supervisor_id` column, with a CHECK that nobody supervises themselves |
| 3 | Grace window after attendance lock | **No** | Once `ATTENDANCE_LOCKED`, corrections are refused. Hard lock, no grace period. Lands in step 3 (`064`) |
| 4 | Where UAN/ESI live | **My call → on `staff_ops_employee_profiles`** | `epf_esic_registrations.candidate_id` is `NOT NULL`, so reusing it would mean making that column nullable on a recruiting-owned table. Direct hires have no candidate row at all. Hire conversion copies the numbers across instead. **No recruiting table is touched.** |
| 5 | Casuals without a login | *(no clear answer — proceeding with the proposal)* | `casual_workers.employee_id` stays nullable so a gate hire can be recorded from a phone number. Lands in step 2 (`063`); say the word if you want it required. |
| 6 | Too many tables in one step | **Yes, split** | Step 1 (`062`) written and verified; steps 2–4 await your go-ahead |

### Adjustment made during implementation
`staff_ops_agencies` moved from step 2 into step 1, because
`staff_ops_employee_profiles.agency_id` references it and a forward reference
would not apply. `agency_monthly_compliance` stays in step 2.

---

## 8. Superseded — original open questions

**1. How should bank account numbers be encrypted?**
`pgcrypto` is **not enabled** (only `pg_trgm`). Options:
- (a) `CREATE EXTENSION pgcrypto` and `pgp_sym_encrypt` with a key in Supabase
  Vault — encrypted at rest in the column, decryptable in SQL.
- (b) Encrypt in Python before insert — the database never sees plaintext, but
  no SQL-side decryption and key management becomes ours.
- (c) Don't store it at all — keep only the last 4 digits plus a payout token
  from Razorpay, which already holds the real account.

I'd pick **(c)**: the Razorpay payout service already exists, and the safest
bank number is one you never hold.

**2. `supervisor_id` or reuse `users.manager_id`?**
`users.manager_id` already exists. Is a hotel supervisor the same person as the
reporting manager, or genuinely different? Duplicating risks the two drifting.

**3. Lock the month at ATTENDANCE_LOCKED or only at CLOSED?**
Can a supervisor still correct attendance after HR locks it but before payroll
closes? Common practice is a grace window.

**4. `epf_esic_registrations` is keyed to `candidate_id`, not employee.**
UAN and ESI numbers live there, attached to the candidate record. Should I
(a) add a nullable `employee_id` to that table, or (b) hold UAN/ESI on
`staff_ops_employee_profiles` as proposed? (b) duplicates; (a) changes a
recruiting-owned table — which needs your permission.

**5. Casual workers without a login — confirm.**
I've allowed `employee_id` NULL so a gate hire can be recorded from a phone
number alone. Correct, or must every casual have an account first?

**6. 13 new tables plus 2 altered — too many for one step?**
I can split into: core employee model first (062), operations second (063),
governance third (064). You could approve and ship 062 alone.
