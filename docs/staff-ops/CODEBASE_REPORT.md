# Codebase Report — HospRecruit AI

**Audience:** a senior full-stack developer joining this project.
**Date:** 29 October 2026 · **Branch:** `main`
**Status:** survey findings, updated after the Stripe billing flag was added
(risk 10 below). Everything else is as surveyed.

HospRecruit AI is a hospitality recruiting **and workforce management** platform for
hotels in India. It began life as a US/EU product and has been substantially
rebuilt for India (DPDP Act, Aadhaar/PAN KYC, EPF/ESIC payroll, WhatsApp).
Traces of the original product remain and are flagged throughout.

**Scale:** ~45,000 lines of Python · ~27,000 lines of TypeScript · 218 database
tables · 68 migrations · 519 API routes · 55 routers · 82 services · 63 pages.

---

## 1. Tech stack

| Layer | Choice |
|---|---|
| Backend | Python ≥3.11, FastAPI 0.109, Pydantic v2, uvicorn |
| Frontend | React 18.3, TypeScript 5.2, Vite 5 |
| Database | PostgreSQL via Supabase (hosted) |
| Data access | `supabase-py` query builder — **no ORM in practice** |
| Auth | Supabase Auth (GoTrue), JWT HS256 |
| Background | Celery 5.3 + Redis |
| Package managers | **Poetry** (backend, `pyproject.toml`) · **npm** (frontend) |
| AI | Anthropic `claude-sonnet-4-6` (primary), OpenAI GPT-4o (secondary) |

### No ORM, despite appearances
`sqlalchemy ^2.0` and `alembic ^1.13` are declared in `pyproject.toml`, but:

- only **3 files** import SQLAlchemy — all Stripe/billing (`routers/billing.py`,
  `services/stripe_service.py`, `services/stripe_webhooks.py`)
- there is **no `alembic/` directory** and no Alembic config
- `backend/app/models/` is **empty**

All real data access goes through the Supabase client, e.g.
`supabase.table("candidates").select("*").eq("org_id", ctx.org_id).execute()`.
Schema changes are hand-written SQL in `supabase/migrations/`, applied manually
through the Supabase SQL editor. There is no migration runner.

### No deployment configuration
There is **no `Dockerfile`, no `docker-compose.yml`, no `render.yaml`, no
`vercel.json`, no `Procfile`, and no `.github/workflows`**. `GETTING_STARTED.md`
suggests Render (backend) + Vercel (frontend), but nothing is configured.
Deployment today is manual.

---

## 2. Folder structure

```
backend/
  app/
    core/          config.py (Pydantic Settings), security.py (JWT), dependencies.py
    routers/       55 files — HTTP layer, one per domain
    services/      82 files — business logic; most testable logic lives here
    repositories/  thin Supabase data-access helpers (used inconsistently)
    schemas/       Pydantic request/response models
    workers/       5 Celery tasks
    models/        EMPTY
    main.py        app construction + router registration
  tests/           53 pytest files (~1,340 tests)
  venv/            a committed virtualenv (see Risks)
  run.py           uvicorn entrypoint, port 8000, reload on

frontend/
  src/
    pages/         63 route-level screens
    components/    11 shared components (AppLayout, ProtectedRoute, …)
    components/ui/ shadcn/ui primitives
    lib/           api.ts (axios), supabase.ts, AuthContext, RBACContext, PropertyContext
    hooks/         React Query hooks
    i18n.ts        all translations, inline
    AppRouter.tsx  every route
  public/          PWA manifest, service worker, offline page, icons

supabase/migrations/   68 numbered .sql files — the real schema source of truth
payroll/, services/    two standalone Node packages (Razorpay payouts, referral queue)
docs/                  ENDPOINTS.md, TECH_INTEGRATION.md, this report
```

**Where to add things:** a new feature is normally a migration + a service (pure
logic) + a router + a page, with the router registered in `app/main.py` and the
page in `AppRouter.tsx` and `components/AppLayout.tsx` (nav).

**Note:** `App.tsx` is dead code. `main.tsx` mounts `AppRouter`, not `App`.
`App.tsx` defines `/login`, `/dashboard`, `/screening` — none reachable.

---

## 3. Authentication

Supabase Auth throughout. The backend never issues tokens; it only verifies them.

**Verification** — `backend/app/core/security.py`:
`HTTPBearer` → `jose.jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"],
audience="authenticated")`. `get_current_user` returns the decoded claims;
`get_optional_user` allows anonymous access.

**Login paths:**

| Who | Method | Where |
|---|---|---|
| Staff / employees | **Phone OTP** — `signInWithOtp` → `verifyOtp` | `pages/EmployeeLogin.tsx` |
| Managers / HR | **Email + password** — `signInWithPassword`, `signUp` | `pages/AuthPage.tsx` |
| Candidates | Separate OTP flow, backend-issued | `services/otp_service.py`, `candidate_otp_sessions` |

Phone numbers are validated as Indian: `^\+91[6-9]\d{9}$`. The backend OTP
service hashes OTPs before storage and normalises numbers to E.164.

**Token handling** — `frontend/src/lib/api.ts`: an axios request interceptor
attaches the Supabase access token plus an `X-Property-ID` header from
`localStorage`. A response interceptor retries once on `401` after
`refreshSession()`, then redirects to login.

**Gaps:**
- **No password reset.** `resetPasswordForEmail` appears nowhere. A manager who
  forgets their password must be reset manually in Supabase.
- `signInWithOAuth` is called in exactly one place with no provider configured —
  social login is effectively absent.

---

## 4. Users and roles

Single `users` table (`org_id`, `role`, `department_id`, `active_property_id`),
mirroring Supabase `auth.users`.

**Eight canonical roles** — `services/rbac_service.py`:

`OWNER` · `GROUP_ADMIN_HR` · `GENERAL_MANAGER` · `HR_MANAGER` ·
`DEPARTMENT_HEAD` · `RECRUITER` · `EMPLOYEE` · `CANDIDATE`

`ROLE_ALIASES` maps legacy spellings (`gm`, `super_admin`, `property_recruiter`,
`hiring_manager`, `viewer`…) onto these eight, so stored values vary.
`canonical_role()` defaults to `CANDIDATE` — **unknown roles fail closed**.

**Permissions** are `domain.action` strings (`candidates.read`,
`attendance.manage`, `payroll.read`, `properties.manage`, …) held in a
`PERMISSION_MATRIX` keyed by role.

**Two enforcement layers — both matter:**

1. **Application** — every protected endpoint runs
   `ctx = build_access_context(supabase, user)` then
   `authorize(ctx, "attendance.read", property_id=...)`.
   `OWNER` and `GROUP_ADMIN_HR` see all properties; `DEPARTMENT_HEAD` is scoped
   to its department; `EMPLOYEE`/`CANDIDATE` only to their own rows.
2. **Database** — Postgres RLS on every table, using SQL helpers
   `current_user_org_id()`, `has_property_access(property_id)` and
   `rbac_has_permission('…')`.

Frontend mirrors this with `RBACContext.can(permission)` and
`<ProtectedRoute permission="…">`. This is presentation only — the server is
authoritative.

> For the Hotel Staff Ops brief: there is **no `SUPERVISOR` role** and no
> **Security / Time-office** role. Both would need adding.

---

## 5. Organisation model

Yes — multi-hotel is supported and is a first-class concern.

```
organizations (the group / owner company)
  └── properties            (individual hotels; org_id, type, location, timezone, brand_color)
        ├── property_departments   (code, name, budgeted_headcount, head_user_id)
        └── property_memberships   (user_id, role, department_id, is_default, is_active)
```

One organisation can own many properties; one user can belong to several
properties with a different role in each. The active hotel is carried in
`users.active_property_id` and the `X-Property-ID` request header, and surfaced
in the UI through `PropertyContext` with a property switcher.

**Caveat:** `properties` was created early (`004_seasonal.sql`) with loose typing
(`TIMESTAMP` not `TIMESTAMPTZ`, `timezone` defaulting to `'UTC'` rather than
`Asia/Kolkata`). The richer multi-property layer arrived later in
`028_hotel_multi_property_management.sql`.

---

## 6. Recruiting data

**There are two parallel job models.** This is the most significant schema
problem in the repository.

| | `jobs` (`001_init_schema.sql`) | `job_roles` (`007_ai_matching.sql`) |
|---|---|---|
| Scope | `org_id` | `org_id` |
| Fields | title, role_type, description, status, positions_available; later openings_count, salary/CTC ranges, approval workflow (`030`) | title, department, required_skills, preferred_skills, salary_min/max, seniority_level, work_pattern |
| Referenced by | `shifts.job_id`, `candidates.job_id` | `applications.job_role_id`, `candidate_matches` |

**Neither table has a `property_id`.** In a multi-hotel product, a vacancy cannot
currently be tied to the hotel it is for — only to the owning organisation.

### Key tables

- **`candidates`** — `org_id`, `job_id`, name, email, phone, location, `source`,
  `pipeline_stage` (default `applied`), `qualified`, `screening_result` JSONB,
  `raw_data`, `availability`, `screened_at`, `accepted_at`
- **`candidate_profiles`**, **`candidate_documents`**, **`candidate_notes`**,
  **`candidate_screening_results`**, **`candidate_matches`**
- **`applications`** — `candidate_id`, `job_role_id`, `campaign_id`, `source`,
  `status` (default `SUBMITTED`), `applied_via`, `completion_time_seconds`,
  `form_data` JSONB
- **`application_stage_history`** — the stage audit trail
- **`interview_slots`**, **`video_interviews`** (questions JSONB, recording_url)
- **`appointment_letters`** — the nearest thing to an offer record
- **`hiring_campaigns`**, **`campaign_roles`** — seasonal recruitment drives

### Pipeline stages
`APPLIED` → `SHORTLISTED` → `INTERVIEW` → `OFFER` / `OFFERED` → `HIRED`,
plus `REJECTED` and `WITHDRAWN`.

Both `OFFER` and `OFFERED` exist in the schema — inconsistent, and worth
normalising. Stage values are also lower-case on `candidates.pipeline_stage`
but upper-case on `applications.status`.

**There is no dedicated `offers` table.** An offer is a status plus an
appointment letter.

Beyond recruiting, the schema covers the full employee lifecycle: attendance,
rosters, leave, payroll, performance, training, grievances, exit, accommodation
and transport.

---

## 7. Internationalisation

**Library:** `i18next` + `react-i18next` + `i18next-browser-languagedetector`.

**This is the weakest area relative to the product's market.**

- Languages present: **en, es, fr, de, it, pt** — six European languages,
  left over from the pre-India product.
- **There is no Hindi locale.**
- All strings live **inline** in `frontend/src/i18n.ts` (254 lines). There are
  **no translation files**.
- Exactly **one namespace** (`candidate`), consumed by **2 of 63 pages**.

Hindi text *does* exist in the product, but hard-coded rather than translated:

- inline ternaries in components, e.g. `lang==='hi' ? 'सही भारतीय मोबाइल नंबर दर्ज करें।' : '…'`
  in `pages/EmployeeLogin.tsx`
- Hindi strings embedded in Python — the WhatsApp HR bot, job descriptions,
  onboarding letters
- `label_hi` columns on newer tables such as `attendance_codes`

Delivering "English and Hindi from day one, all text from translation files" is
real unbuilt work: extract to per-language files, add `hi`, and wire the
remaining 61 pages.

---

## 8. UI

- **Styling:** Tailwind CSS 3.4, with shadcn/ui conventions — HSL CSS custom
  properties (`--border`, `--background`, `--primary`…) defined in `index.css`
  and mapped in `tailwind.config.js`. Light/dark themable by design.
- **Primitives:** Radix UI (dialog, dropdown, popover, select, label, slot) under
  `components/ui/`, `class-variance-authority` + `tailwind-merge` for variants.
- **Also installed:** **MUI v9** and Emotion. Two full component systems ship in
  the same bundle (see Risks).
- **Icons:** `lucide-react`. **Charts:** `recharts`.
- **Brand colour:** purple (`#7C3AED`), also the `properties.brand_color` default.
- **Fonts:** system stack; no webfont is loaded.
- **Responsiveness:** mobile-first Tailwind breakpoints; `AppLayout` collapses to
  a drawer. The staff-facing screens are built for phones.

### PWA — complete, for the employee app only
`frontend/public/` contains `manifest.webmanifest`, `sw.js`, `offline.html`, and
both standard and maskable icons. `index.html` links the manifest;
`main.tsx:25` registers the service worker **in production builds only**.
The cache shell is `/`, `/employee-login`, `/employee-app`, `/offline.html` —
so the installable experience is scoped to staff, not the manager console.
The worker uses network-first for navigation and cache-first for static assets,
and correctly skips `/api/` and non-GET requests.

---

## 9. Notifications

| Channel | Provider | Notes |
|---|---|---|
| SMS | **Twilio** | 28 files reference it |
| WhatsApp | **Twilio WhatsApp** | 40 files; sandbox number `whatsapp:+14155238886` by default. A full conversational HR bot (`hr_bot_service.py`, `command_parser.py`) handles leave, payslip, shift and complaint commands in English and Hindi |
| Email | **raw `smtplib`** | `services/email_service.py`; defaults to `smtp.gmail.com:587`, silently skips sending when `SMTP_USER`/`SMTP_PASSWORD` are unset |
| Push | — | none (no FCM/APNs), despite the service worker |

There is a `whatsapp_gateway` abstraction with a Meta Cloud API parser alongside
Twilio, so the provider is swappable. Email has no such abstraction and no
transactional provider (SendGrid/SES/Resend are absent).

---

## 10. File uploads

**AWS S3, pinned to `ap-south-1` (Mumbai)** for DPDP Act data-residency.
`services/s3_service.py` plus `fssai_s3_service.py`.

- **Presigned URLs** for direct browser upload (`ExpiresIn=300`), so files do not
  pass through the API.
- Server-side encryption: `aws:kms` when `AWS_KMS_KEY_ID` is set, otherwise
  `AES256`.
- **Sandbox fallback:** when `AWS_S3_BUCKET` is unset the service returns
  `local://` paths and logs a warning at startup, so the app runs without AWS.
- A startup check in `services/data_localization.py` hard-fails if `AWS_REGION`
  is moved away from `ap-south-1`, and classifies Aadhaar, PAN, biometrics and
  face photos as **never** transmissible to non-India services.

Stored: resumes, candidate documents, compliance and FSSAI certificates,
appointment letters, payslip PDFs (`reportlab`), video interview recordings.

---

## 11. Background jobs

**Celery 5.3 + Redis** — `backend/app/celery_app.py`. Configured sensibly:
`task_acks_late=True` (re-queue on worker crash), `worker_prefetch_multiplier=1`.

Beat schedule:

| Task | Schedule |
|---|---|
| `certification_expiry` | daily 03:30 |
| `identity_document_expiry` | daily 03:45 |
| `dpdp_retention` | daily 04:00 |
| `scheduled_reports` | every 15 minutes |
| `fssai_expiry` | (worker present) |

Separately, `services/` and `payroll/` at the repo root are standalone **Node**
packages running a BullMQ-style referral payout queue, worker and scheduler
against Razorpay. Two runtimes, two job systems.

---

## 12. Running it locally

**Prerequisites:** Python ≥3.11, Node, a Supabase project, Redis (for Celery).

```bash
# Backend
cd backend
python -m venv venv && source venv/Scripts/activate   # Windows: venv\Scripts\activate
poetry install            # NOT pip install -r requirements.txt — that file does not exist
cp .env.example .env      # then fill in Supabase, Anthropic, Twilio keys
python run.py             # http://localhost:8000 — docs at /docs

# Frontend
cd frontend
npm install
cp .env.example .env.local   # VITE_API_BASE_URL=http://localhost:8000/api/v1
npm run dev                  # http://localhost:5173
```

Database: run the 68 files in `supabase/migrations/` **in numeric order** through
the Supabase SQL editor. There is no automated runner.

**Tests:**

```bash
cd backend && python -m pytest -q        # 53 files, ~1,340 tests
cd frontend && npm run type-check        # tsc --noEmit — currently clean
cd payroll  && npm test                  # Jest
cd services && npm test                  # Jest
```

**Current state:** `1,286 pass · 54 fail` (see Risks). `npm run type-check`
passes cleanly. There are **no frontend unit tests** and **no E2E tests**.

---

## 13. Code quality issues and risks

Ordered by how much damage each could do.

### Critical

1. **Almost nothing is in version control.** `git log` shows **one commit**;
   `git ls-files` shows **one tracked file** (`README.md`). All of `backend/`,
   `frontend/` and `supabase/` — roughly 72,000 lines — is untracked. There is
   no restore point and no way to review a diff. *Fix first.*

2. **A virtualenv is committed into the tree.** `backend/venv/` sits inside the
   repo. It is untracked today only because nothing is tracked; it must be in
   `.gitignore` before the first real commit or it will be added wholesale.

3. **54 failing tests.** Root cause is copy-paste drift, not product bugs: a
   `TableChain` Supabase test double is defined **six times** — once in
   `tests/conftest.py` with 19 methods, and five more times inside individual
   test files with 11–15 methods. The stale copies lack `.lte()`, so the code
   under test throws `'TableChain' object has no attribute 'lte'` and returns its
   error branch. Deleting the five duplicates so they inherit the `conftest`
   version fixes most of them. The remainder are date-dependent leave tests and
   webhook signature `403`s.

### High

4. **No CI, no containers, no deploy config.** Nothing runs the tests
   automatically; nothing reproduces the environment. Combined with (1), the
   project has no safety net at all.

5. **Two parallel job models, neither hotel-scoped.** `jobs` and `job_roles`
   overlap, are referenced by different parts of the app, and neither carries a
   `property_id`. Vacancies cannot be attributed to a specific hotel. Decide on
   one model and add property scoping before building more on top.

6. **Hard-coded statutory values.** The repo mostly does this correctly — the
   `payroll_rules` table is scoped per org *and* per property with
   `effective_from` dating. But module-level constants survive and will silently
   produce wrong pay when a rate changes or differs by state:
   - `services/india_compliance_service.py` — `EPF_EMPLOYER_CONTRIB_PCT = 12.0`
   - `services/labour_compliance_service.py` — `OT_RATE_MULTIPLIER`,
     `MAX_OT_PER_DAY_H`, `DAILY_STANDARD_HOURS`

7. **No password reset.** Managers locked out need manual Supabase intervention.

### Medium

8. **Broken onboarding instructions.** `GETTING_STARTED.md` says
   `pip install -r requirements.txt`; that file does not exist (the project uses
   Poetry). `pytest` is declared in `pyproject.toml` but was absent from the
   checked-in venv, so the suite would not run as shipped.

9. **Two UI component systems.** MUI v9 + Emotion *and* shadcn/Radix are both
   dependencies. This inflates the bundle and invites inconsistent screens. Pick
   one; shadcn/Radix is the more used of the two.

10. **Payment rails are split.** The codebase carries **Stripe** (the original
    US rail) alongside **Razorpay**, which is what the India payout path in the
    Node `services/` package actually uses.

    *Resolved 29 Oct 2026:* Stripe keys were previously typed as required in
    `core/config.py`, so the app would not boot without them. They are now
    `Optional[str] = None` behind a **`BILLING_ENABLED: bool = False`** flag,
    and `main.py` mounts the billing router only when it is true. The app boots
    with no Stripe account at all. Turning the flag on restores all 9 billing
    routes — but see risk 11: the billing *UI* is not routed, so the flag alone
    surfaces nothing.

11. **Dead code and colliding names.**
    - `frontend/src/App.tsx` is unreachable (`main.tsx` mounts `AppRouter`), and
      its `/login` route misleads — the live path is `/auth`.
    - `pages/BillingDashboard.tsx` and `pages/PricingPage.tsx` are **never
      imported or routed**. A nav link to `/billing` used to point at them; it
      fell through to the `*` catch-all and redirected to `/`. That link was
      removed on 29 Oct 2026. Enabling billing therefore needs those two pages
      routed first — the flag does not surface them.
    - **Two classes are named `BillingService`**, in `services/stripe_service.py`
      (`__init__(stripe_service: StripeService)`, the one `routers/billing.py`
      imports) and in `services/billing_service.py`
      (`__init__(billing_repo: BillingRepository)`, unused by that router).
      They have different constructors and different methods. Reading the wrong
      one makes correct code look broken — worth renaming.

12. **Schema inconsistency.** Early migrations use `TIMESTAMP` and lower-case
    status values; later ones use `TIMESTAMPTZ` and upper-case. `OFFER` and
    `OFFERED` coexist. `properties.timezone` defaults to `'UTC'` in an
    India-only product.

13. **Readability.** `routers/payroll.py` and `services/payroll_service.py` are
    written in an extremely dense one-line-per-statement style with
    semicolon-separated expressions. It is correct and well tested, but it is the
    hardest code in the repo to review — notable given it computes people's pay.

14. **Email has no abstraction.** Raw `smtplib` against Gmail, failing silently
    when unconfigured. Unlike WhatsApp, there is no provider interface.

15. **Large surface area.** 218 tables, 519 routes, 82 services. Much is
    genuinely built and tested, but the breadth makes onboarding slow and raises
    the odds of duplicate implementations like the `jobs`/`job_roles` split.

### What is genuinely good

Worth saying plainly, because the risk list is long:

- **RLS is applied consistently**, with permission checks in the policies
  themselves rather than only in application code.
- **Data-residency enforcement is real** — a startup check hard-fails on a
  non-India region, and Aadhaar/PAN/biometrics are explicitly barred from
  crossing borders.
- **Vendor-neutral adapter patterns** for biometrics and PMS keep vendor payload
  shapes out of domain code.
- **The payroll engine is deterministic**, uses `Decimal` with explicit rounding,
  and hashes a snapshot of every calculation for audit.
- **~1,286 passing tests** concentrated on business logic.
- Integrations are **honestly labelled** — unsupported job boards are marked
  `MANUAL_EXPORT` and unverified PMS field maps carry `verified: false`, rather
  than pretending to work.
