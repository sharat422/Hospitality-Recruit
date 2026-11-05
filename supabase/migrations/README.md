# Migrations

There is no migration runner. Files are pasted into the **Supabase SQL editor**
by hand, in numeric order. `069_migration_tracking.sql` adds a record of what
has run and a guard so a missed file fails with a readable message rather than
`relation "..." does not exist`.

## Before you start

```sql
-- What is already applied? (schema probes — correct even with no tracking)
\i CHECK_APPLIED.sql

-- Or, once 069 has run, just read the history:
SELECT * FROM v_migration_status;
```

## Applying

Run files in numeric order, each one **completely** before the next. Every file
is a single transaction, so a failure rolls the whole file back — a half-applied
migration is not possible, but a *skipped* one is.

Current Staff Ops chain and what each needs:

| File | Requires | Notes |
|---|---|---|
| `060_attendance_codes` | — | |
| `061_staff_ops_user_language` | — | |
| `062_staff_ops_core` | — | agencies, designations, employee profiles, documents |
| `063_staff_ops_operations` | **062** | OT, shift offers, casuals, agency compliance |
| `064_staff_ops_governance` | — | settings, audit log, month close, leave date range |
| `065_staff_ops_demo_seed` | **062, 063, 064** | **optional — skip in production** |
| `066_staff_ops_roles` | — | SUPERVISOR + TIME_OFFICE |
| `067_leave_property_not_null` | **064** | self-checking; safe to re-run |
| `068_staff_ops_exit_revokes_access` | **062** | trigger + RLS |
| `069_migration_tracking` | — | run last, or any time; back-fills itself |

## Writing a new migration

Two things, both small.

**1. Guard your dependencies at the top.** Use raw `to_regclass` /
`information_schema` rather than `migration_requires()`, so the file works even
if `069` has not been applied:

```sql
BEGIN;

DO $$ BEGIN
    IF to_regclass('public.staff_ops_agencies') IS NULL THEN
        RAISE EXCEPTION
          E'Migration 062_staff_ops_core.sql has not been applied.\n'
          '070 references staff_ops_agencies, which 062 creates.';
    END IF;
END $$;
```

**2. Record it at the bottom**, tolerating `069` not being there yet:

```sql
DO $$ BEGIN
    IF to_regproc('migration_applied(text,text,text)') IS NOT NULL THEN
        PERFORM migration_applied('070', '070_your_migration');
    END IF;
END $$;

COMMIT;
```

## Why two mechanisms

- **Schema probes are the enforcement.** They ask the database what exists. A
  bookkeeping table can be edited, or drift from reality; the schema cannot.
- **The table is the history.** It answers "what ran, when, by whom" without a
  hand-maintained probe list, and is best-effort by design.

## House style

- One transaction per file: `BEGIN;` … `COMMIT;`
- `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, `ON CONFLICT DO NOTHING`
  — every file should survive being run twice
- Wrap `ADD CONSTRAINT` in `DO $$ … EXCEPTION WHEN duplicate_object THEN NULL; END $$;`
- Every property-scoped table carries `org_id` **and** `property_id`, plus the
  standard RLS block (see `062` for the pattern)
- Never hard-delete attendance, leave, OT or payment rows — use a status column,
  and `CREATE RULE … ON DELETE DO INSTEAD NOTHING` to enforce it in the database
