# Staff Ops — Testing Scenarios

One section per feature. Each scenario says what to do, what should happen, and
how to tell it went wrong. Scenarios marked **automated** already run in the
test suite; the rest are manual until someone writes them.

---

## S1. Languages (en, hi, te, ta, kn)

### S1.1 Translation files
| # | Scenario | Expected | Automated |
|---|---|---|---|
| 1.1.1 | `node scripts/i18n/check-keys.mjs` | All four languages show **100% coverage, 0 missing, 0 orphan** | no |
| 1.1.2 | Every language has all 7 namespaces | 35 files under `frontend/src/locales/` | no |
| 1.1.3 | Delete a key from `ta/common.json`, re-run check-keys | Reports it under "ta missing" | no |
| 1.1.4 | Add a key to `en/common.json` only | Reported missing for hi, te, ta, kn | no |
| 1.1.5 | Add a key to `ta/` that is not in `en/` | Reported as **orphan** | no |
| 1.1.6 | `check-keys.mjs --ci` with a missing key | Exits **1** | no |

### S1.2 Language resolution — **automated** (`test_staff_ops_language.py`)
| # | Scenario | Expected |
|---|---|---|
| 1.2.1 | Hotel in Telangana, user has no preference | Telugu |
| 1.2.2 | Hotel in Tamil Nadu, no preference | Tamil |
| 1.2.3 | Hotel in Karnataka, no preference | Kannada |
| 1.2.4 | Hotel in Bihar, no preference | Hindi |
| 1.2.5 | Hotel in **Maharashtra**, no preference | **English** — no Marathi, so fall back, do not guess |
| 1.2.6 | Hotel in Kerala or Goa | English |
| 1.2.7 | Tamil-speaking user in a **Karnataka** hotel | **Tamil** — person beats hotel |
| 1.2.8 | User preference is `es` (stale) | Hotel default, not Spanish |
| 1.2.9 | State written `"  tamil nadu  "` or `"KARNATAKA"` | Still resolves — case and padding tolerated |
| 1.2.10 | State given as code `TS`, `AP`, `TN`, `KA`, `UP` | Resolves correctly |
| 1.2.11 | No state, no preference | English |

### S1.3 Fallback and missing keys
| # | Scenario | Expected | Automated |
|---|---|---|---|
| 1.3.1 | Render a key present in en but missing in ta, in Tamil | **English text shows** — never the raw key | no |
| 1.3.2 | Same, in dev mode | Console warns `[i18n] missing "<key>" in ta/<ns>` | no |
| 1.3.3 | `getMissingKeys()` after the above | Contains one entry for that key | no |
| 1.3.4 | Trigger the same missing key 50 times | Recorded **once**, not 50 times | no |

### S1.4 Language picker
| # | Scenario | Expected | Automated |
|---|---|---|---|
| 1.4.1 | First login, hotel in Chennai, no preference saved | Picker opens with **Tamil preselected** | no |
| 1.4.2 | Choose Kannada | UI switches immediately; `PUT /staff-ops/me/language` sends `kn` | no |
| 1.4.3 | Log out, log in on another device | Still Kannada — preference is on the user, not the browser | no |
| 1.4.4 | Choose a language while offline / API down | **UI still switches**; an error line appears saying only the save failed | no |
| 1.4.5 | Private browsing with localStorage blocked | Does not crash; server copy still works | no |
| 1.4.6 | Each option shows its own script | हिंदी, తెలుగు, தமிழ், ಕನ್ನಡ — each with `lang` set correctly | no |
| 1.4.7 | Picker option list | **Exactly five** — no Spanish/French/German/Italian/Portuguese (decision 2) | no |

### S1.4b First-login gate (`LanguageGate` inside `ProtectedRoute`)
| # | Scenario | Expected | Automated |
|---|---|---|---|
| 1.4b.1 | Sign in with `preferred_language` NULL | Full-screen picker appears **once** | no |
| 1.4b.2 | Choose a language | Picker closes, the app renders underneath | no |
| 1.4b.3 | Sign out and back in | **No picker** — the choice was saved | no |
| 1.4b.4 | `/staff-ops/me/language` returns 500 | **App still opens** — gate fails open, never traps the user | no |
| 1.4b.5 | Migration 061 not yet applied | App still opens (same fail-open path) | no |
| 1.4b.6 | Open `/employee-app` (no AppLayout) | Gate still fires — it sits in ProtectedRoute | no |
| 1.4b.7 | Open a **public** candidate link `/apply/:jobRoleId` | **No gate** — not wrapped by ProtectedRoute | no |
| 1.4b.8 | Slow network | ProtectedRoute's spinner shows; no flash of untranslated UI | no |

### S1.5 Fonts and layout — **the 360px Tamil test**
| # | Scenario | Expected | Automated |
|---|---|---|---|
| 1.5.1 | Every Staff Ops screen at **360px wide in Tamil** | No horizontal scrollbar anywhere | **VERIFIED 30-10-2026** |
| 1.5.2 | Same in Telugu | No clipped vowel signs above or below any line | no |
| 1.5.3 | Kannada button labels | Buttons **wrap to two lines**, never truncate with "…" | no |
| 1.5.4 | Table headers in Tamil | Headers wrap; the table does not overflow its container | no |
| 1.5.5 | Tap targets in any language | At least 44px tall | no |
| 1.5.6 | Devanagari matras on a crowded row | Not cut off by a fixed-height ancestor | no |
| 1.5.7 | Cheap Android without Telugu system font | Noto Sans Telugu webfont loads; no tofu boxes (▯) | no |
| 1.5.8 | A wide table at 360px in Tamil | Headers read **horizontally on one line**; the table scrolls inside `.table-scroll` while the page does not | **VERIFIED 30-10-2026** |
| 1.5.9 | `formatNumber(10000000, 'kn')` | `1,00,00,000` — one crore, not `10,000,000` | **VERIFIED 30-10-2026** |

> **Audit of 30-10-2026** (ta, te, kn, hi, en at 360px): zero page overflow,
> zero clipped vowel signs, zero ellipsised labels, every button ≥44px tall,
> Indian grouping identical in all five. Two defects were found and fixed:
> ICU's `kn-IN` locale grouped Western-style, and `overflow-wrap: anywhere`
> broke Tamil table headers one glyph per line. The second passed the
> automated check and was only visible in the screenshot.

> How to run 1.5.1: Chrome DevTools → device toolbar → set width 360 → switch
> language to Tamil → scroll the whole page. Any sideways movement is a failure.

### S1.6 Numbers, dates, times
| # | Scenario | Expected | Automated |
|---|---|---|---|
| 1.6.1 | `formatNumber(100000, 'hi')` | `1,00,000` — Indian grouping, **Latin digits** | no |
| 1.6.2 | Same in te, ta, kn | Identical digits; no native numerals (`೧`, `௧`, `౧`) | no |
| 1.6.3 | `formatINR(12500.5)` | `₹12,500.50` | no |
| 1.6.4 | `formatINR(100000)` | `₹1,00,000` — no decimals on a whole number | no |
| 1.6.5 | `formatDate('2026-10-29')` | `29-10-2026` | no |
| 1.6.6 | `formatTime` for 21:30 UTC | `03:00 AM` next day in IST — timezone is applied | no |
| 1.6.7 | `formatTime` in Hindi, Tamil, Telugu, Kannada | `09:30 AM` — **Latin AM/PM in every language** (decision 5) | no |
| 1.6.8 | `formatDate(null)` / invalid string | `—`, never `Invalid Date` or a crash | no |
| 1.6.9 | `formatDuration(510)` | `8h 30m` | no |

### S1.7 Translator CSV round-trip
| # | Scenario | Expected | Automated |
|---|---|---|---|
| 1.7.1 | `export-csv.mjs` | 540 rows, all `needs_review` | no |
| 1.7.2 | Open the CSV in Excel on Windows | Indic scripts render correctly (BOM present) | no |
| 1.7.3 | Edit a translation, set `status=approved`, import | File updated; key recorded in `_status.json` | no |
| 1.7.4 | Re-run `check-keys.mjs` | needs-review count drops by exactly the number approved | no |
| 1.7.5 | Import with a **blank** translation cell | Row **skipped** — never writes an empty string | no |
| 1.7.6 | Import a row for a key deleted from English | Reported as a problem, skipped | no |
| 1.7.7 | Import a row with `language=en` | **Refused** — English is the source | no |
| 1.7.8 | Import with `--dry-run` | Reports counts, writes nothing | no |
| 1.7.9 | Translation containing a comma and a `"` | Survives export and import unchanged | no |
| 1.7.10 | `export-csv.mjs --needs-review` after approvals | Approved rows excluded | no |

### S1.8 Notifications per language
| # | Scenario | Expected | Automated |
|---|---|---|---|
| 1.8.1 | `requires_unicode_sms` for hi/te/ta/kn | `True` | **yes** |
| 1.8.2 | Same for en | `False` | **yes** |
| 1.8.3 | 100-character English SMS | 1 segment | **yes** |
| 1.8.4 | 100-character Tamil SMS | **2 segments** — UCS-2 is 70/67 per part | **yes** |
| 1.8.5 | 70-character Hindi SMS | Exactly 1 segment | **yes** |
| 1.8.6 | 71-character Hindi SMS | 2 segments | **yes** |
| 1.8.7 | Empty message | 0 segments | **yes** |

### S1.9 Recruiting must not regress — **run before merging**
| # | Scenario | Expected | Automated |
|---|---|---|---|
| 1.9.1 | Open the candidate job application form | Loads and renders as before | no |
| 1.9.2 | Its language picker still lists en, es, fr, de, it, pt | Unchanged — Staff Ops added nothing to it | no |
| 1.9.3 | Switch it to Spanish | Still works | no |
| 1.9.4 | Video interview recorder | Unchanged | no |
| 1.9.5 | `git diff frontend/src/i18n.ts` | **Empty** — the file must not be touched | no |


---

## S5. Staff Ops core schema (migration 062)

Run after applying `062_staff_ops_core.sql` in the Supabase SQL editor.

### S5.1 Constraints that must reject bad data
| # | Try to insert | Expected |
|---|---|---|
| 5.1.1 | `staff_type='AGENCY'` with `agency_id` NULL | **Rejected** — `employee_profile_agency_required` |
| 5.1.2 | `staff_type='PERMANENT'` **with** an `agency_id` | **Rejected** — same constraint works both ways |
| 5.1.3 | `leaving_date` earlier than `joining_date` | Rejected |
| 5.1.4 | `status='LEFT'` with no `leaving_date` | Rejected |
| 5.1.5 | `supervisor_id` = the employee's own id | Rejected |
| 5.1.6 | `default_weekly_off = 7` | Rejected (valid range 0–6) |
| 5.1.7 | `uan = '12345'` | Rejected — must be 12 digits |
| 5.1.8 | `bank_ifsc = 'ABCD1234567'` | Rejected — 5th character must be `0` |
| 5.1.9 | `bank_account_last4 = '12345'` | Rejected — exactly 4 digits |
| 5.1.10 | Designation `code = 'steward'` (lower case) | Rejected — must match `^[A-Z][A-Z0-9_]{1,39}$` |
| 5.1.11 | Two designations with the same `code` in one hotel | Rejected — `UNIQUE(property_id, code)` |
| 5.1.12 | Two profiles for the same employee at the same hotel | Rejected |
| 5.1.13 | Two profiles pointing at the same `candidate_id` | Rejected — one candidate converts once |
| 5.1.14 | Two employees sharing a `biometric_id` at one hotel | Rejected |
| 5.1.15 | Document `status='VERIFIED'` with no `verified_by` | Rejected |

### S5.2 No hard deletes
| # | Scenario | Expected |
|---|---|---|
| 5.2.1 | `DELETE FROM staff_ops_employee_profiles WHERE id = …` | **Zero rows deleted**, row still present — the rule silently discards it |
| 5.2.2 | `DELETE FROM staff_ops_employee_documents WHERE id = …` | Same |
| 5.2.3 | Mark someone as having left | `status='LEFT'` + `leaving_date` set; row retained |

> Note 5.2.1 reports success with 0 rows affected, not an error. Application
> code must therefore never rely on a delete returning a count.

### S5.3 Hotel isolation (RLS)
| # | Scenario | Expected |
|---|---|---|
| 5.3.1 | HR at hotel A queries profiles | Only hotel A rows |
| 5.3.2 | HR at hotel A reads a hotel B profile by id | No row |
| 5.3.3 | Staff member with no `employees.read` reads **own** profile | **Succeeds** — self-read policy |
| 5.3.4 | Same person reads a colleague's profile | No row |
| 5.3.5 | Staff member reads own documents | Succeeds |
| 5.3.6 | OWNER across several hotels | Sees all their hotels |

### S5.4 Links to existing tables
| # | Scenario | Expected |
|---|---|---|
| 5.4.1 | Profile for a `users` row | Works — no separate employees table |
| 5.4.2 | Direct hire with `candidate_id` NULL | Allowed |
| 5.4.3 | Hire from recruiting with `candidate_id` set | Allowed; unique per candidate |
| 5.4.4 | Delete the candidate | Profile survives, `candidate_id` becomes NULL |
| 5.4.5 | Document with `source_document_id` → `candidate_documents` | Lineage preserved after a copy-on-hire |
| 5.4.6 | Designation referencing `property_departments` | Works |
| 5.4.7 | Profile referencing `shift_templates` | Works |
| 5.4.8 | **Aadhaar** anywhere in these four tables | **No such column** — by design |
| 5.4.9 | Full bank account number column | **Does not exist** — only last 4 + payout token |

### S5.5 Recruiting untouched
| # | Scenario | Expected |
|---|---|---|
| 5.5.1 | `candidates`, `candidate_documents`, `epf_esic_registrations` schemas | **Unchanged by 062** |
| 5.5.2 | Existing candidate flows | Unaffected |

---

## S2. Attendance codes *(built earlier — regression set)*

| # | Scenario | Expected | Automated |
|---|---|---|---|
| 2.1 | Month of 20×P, 4×WO, 2×CL, 1×H, 1×A, 1×HD, 1×LWP | `lop_days` = **2.5** | **yes** |
| 2.2 | Half day | 0.5 LOP, **no** leave deducted | **yes** |
| 2.3 | Unrecognised status (`MISSING_PUNCH`, `INVALID`) | Treated as **fully unpaid**, surfaces as a query | **yes** |
| 2.4 | Legacy `PRESENT` / `ABSENT` / `WEEKLY_OFF` | Still cost the right amount | **yes** |
| 2.5 | Hotel overrides `A` to `lop_factor 0` | Absence becomes paid for that hotel only | **yes** |
| 2.6 | Work a rostered weekly off | Earns 1 comp-off, expires in 30 days | **yes** |
| 2.7 | Weekly off actually taken as rest | Earns nothing | **yes** |
| 2.8 | 4 light days + 1 festival spike | Recommends the **median**, not the peak | **yes** |

---

## S3. PMS staffing *(built earlier — regression set)*

| # | Scenario | Expected | Automated |
|---|---|---|---|
| 3.1 | 101 rooms sold ÷ 16 per attendant | 7 housekeeping staff required | **yes** |
| 3.2 | Zero occupancy, front office `min_staff` 3 | Still 3 | **yes** |
| 3.3 | PMS reports sold > available | Clamped, sync not rejected | **yes** |
| 3.4 | Same property and date synced twice | Identical result — deterministic | **yes** |
| 3.5 | Department short 1 day | **No** hiring signal | **yes** |
| 3.6 | Department short 5 days | Hiring signal, urgency MEDIUM | **yes** |

---

## S4. Billing flag *(built earlier — regression set)*

| # | Scenario | Expected | Automated |
|---|---|---|---|
| 4.1 | No Stripe keys, `BILLING_ENABLED` unset | App boots; 0 billing routes | **yes** |
| 4.2 | `BILLING_ENABLED=true` + keys | 9 billing routes mounted | **yes** |
| 4.3 | `GET /api/v1/billing/pricing/tiers` while disabled | **404**, not a 500 | **yes** |

---

## How to run everything

```bash
# Backend — 1,318 pass, 54 known pre-existing failures
cd backend && ./venv/Scripts/python.exe -m pytest -q

# Just the language tests
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_staff_ops_language.py -q

# Frontend types
cd frontend && npm run type-check

# Translation coverage
node scripts/i18n/check-keys.mjs

# Translator CSV
node scripts/i18n/export-csv.mjs
node scripts/i18n/import-csv.mjs staff-ops-strings.csv --dry-run
```

> **Known baseline:** 54 backend tests fail for a pre-existing reason (five
> stale duplicate `TableChain` test doubles). Any count above 54 means
> something new broke.
