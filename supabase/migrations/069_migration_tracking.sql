-- Migration tracking: record what has run, and refuse to run out of order.
--
-- This project has no migration runner. Files are pasted into the Supabase SQL
-- editor by hand, nothing records what was applied, and the first sign of a
-- missed file is a cryptic "relation ... does not exist" — after which the
-- whole transaction rolls back, so a half-installed feature looks installed.
--
-- Two mechanisms, deliberately:
--
--   1. SCHEMA PROBES are the enforcement. `migration_requires()` asks the
--      database what actually exists. A bookkeeping table can be edited or
--      drift; the schema cannot lie.
--   2. THE TABLE is the history. It answers "what has been run, when, by whom"
--      without twenty hand-written probes, and it is best-effort by design.
--
-- Safe to run at any point. It back-fills itself from what it finds.
BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_by  TEXT NOT NULL DEFAULT current_user,
    notes       TEXT
);

COMMENT ON TABLE schema_migrations IS
    'History of applied migrations. Enforcement is by schema probe in migration_requires(), not by this table.';

-- Record that a migration ran. Idempotent, so re-running a file is harmless.
CREATE OR REPLACE FUNCTION migration_applied(p_version TEXT, p_name TEXT, p_notes TEXT DEFAULT NULL)
RETURNS VOID LANGUAGE sql AS $$
    INSERT INTO schema_migrations (version, name, notes)
    VALUES (p_version, p_name, p_notes)
    ON CONFLICT (version) DO UPDATE
        SET name = EXCLUDED.name,
            applied_at = NOW(),
            applied_by = current_user;
$$;

-- Does this object exist? Covers tables, views, functions and columns, which
-- is everything a migration in this project creates.
CREATE OR REPLACE FUNCTION migration_object_exists(p_kind TEXT, p_name TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE AS $$
DECLARE parts TEXT[];
BEGIN
    CASE lower(p_kind)
        WHEN 'table' THEN
            RETURN to_regclass('public.' || p_name) IS NOT NULL;
        WHEN 'function' THEN
            RETURN EXISTS (SELECT 1 FROM pg_proc WHERE proname = p_name);
        WHEN 'column' THEN
            parts := string_to_array(p_name, '.');
            RETURN EXISTS (SELECT 1 FROM information_schema.columns
                            WHERE table_name = parts[1] AND column_name = parts[2]);
        ELSE
            RAISE EXCEPTION 'migration_object_exists: unknown kind %', p_kind;
    END CASE;
END $$;

-- The guard. Call this at the TOP of a migration, naming what must already
-- exist. Raises a message that says which file to run, instead of leaving the
-- reader to decode a missing-relation error.
--
--   SELECT migration_requires('063', ARRAY['table:staff_ops_agencies'],
--                             '062_staff_ops_core.sql');
CREATE OR REPLACE FUNCTION migration_requires(
    p_self TEXT,
    p_objects TEXT[],
    p_hint TEXT DEFAULT NULL
) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    spec TEXT;
    kind TEXT;
    name TEXT;
    missing TEXT[] := '{}';
BEGIN
    FOREACH spec IN ARRAY p_objects LOOP
        kind := split_part(spec, ':', 1);
        name := split_part(spec, ':', 2);
        IF NOT migration_object_exists(kind, name) THEN
            missing := missing || spec;
        END IF;
    END LOOP;

    IF array_length(missing, 1) > 0 THEN
        RAISE EXCEPTION
          E'Migration % cannot run yet.\n'
          'Missing: %\n'
          '%'
          E'\nRun supabase/migrations/CHECK_APPLIED.sql to see what is in place.',
          p_self,
          array_to_string(missing, ', '),
          COALESCE('Apply first: ' || p_hint, 'Apply the earlier migration that creates these.');
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Back-fill from what is actually present
-- ---------------------------------------------------------------------------
-- Everything applied before tracking existed. Probes only — nothing is assumed.
DO $$
DECLARE
    probe RECORD;
BEGIN
    FOR probe IN
        SELECT * FROM (VALUES
          ('000', '000_auth_setup',                  'table:users'),
          ('001', '001_init_schema',                 'table:candidates'),
          ('028', '028_hotel_multi_property',        'table:property_memberships'),
          ('029', '029_role_based_access_control',   'function:rbac_has_permission'),
          ('035', '035_employee_360',                'column:users.employment_status'),
          ('036', '036_attendance_engine',           'table:attendance_daily_records'),
          ('037', '037_workforce_shift_scheduling',  'table:shift_templates'),
          ('039', '039_payroll_engine',              'table:payroll_runs'),
          ('050', '050_employee_exit_management',    'table:employee_alumni_profiles'),
          ('059', '059_pms_integration',             'table:pms_connections'),
          ('060', '060_attendance_codes',            'table:attendance_codes'),
          ('061', '061_staff_ops_user_language',     'column:users.preferred_language'),
          ('062', '062_staff_ops_core',              'table:staff_ops_employee_profiles'),
          ('063', '063_staff_ops_operations',        'table:staff_ops_ot_records'),
          ('064', '064_staff_ops_governance',        'table:staff_ops_settings'),
          ('066', '066_staff_ops_roles',             'function:canonical_user_role'),
          ('067', '067_leave_property_not_null',     'table:leave_requests'),
          ('068', '068_staff_ops_exit_revokes',      'function:current_user_has_exited')
        ) AS t(version, name, spec)
    LOOP
        IF migration_object_exists(split_part(probe.spec, ':', 1),
                                   split_part(probe.spec, ':', 2)) THEN
            PERFORM migration_applied(probe.version, probe.name,
                                      'back-filled by probe on ' || NOW()::date);
        END IF;
    END LOOP;
END $$;

-- Two probes above are not specific enough on their own, so confirm by content.

-- canonical_user_role() also exists in 029; only 066 teaches it SUPERVISOR.
DELETE FROM schema_migrations
 WHERE version = '066'
   AND NOT EXISTS (SELECT 1 FROM pg_proc
                    WHERE proname = 'canonical_user_role' AND prosrc LIKE '%SUPERVISOR%');

-- leave_requests predates 067; the migration is only done once property_id
-- is actually NOT NULL, which it leaves nullable when rows are unresolved.
DELETE FROM schema_migrations
 WHERE version = '067'
   AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'leave_requests'
                      AND column_name = 'property_id'
                      AND is_nullable = 'NO');

-- 065 is the optional demo seed: present only if its demo hotel row exists.
DO $$ BEGIN
    IF to_regclass('public.properties') IS NOT NULL
       AND EXISTS (SELECT 1 FROM properties
                    WHERE id = 'd0000000-0000-4000-a000-000000000010') THEN
        PERFORM migration_applied('065', '065_staff_ops_demo_seed', 'optional demo data');
    END IF;
END $$;

SELECT migration_applied('069', '069_migration_tracking');

-- Readable status, newest first.
CREATE OR REPLACE VIEW v_migration_status AS
SELECT version, name, applied_at, applied_by, notes
  FROM schema_migrations
 ORDER BY version;

COMMENT ON FUNCTION migration_requires IS
    'Call at the top of a migration with the objects it depends on, e.g. ARRAY[''table:foo'',''column:bar.baz''].';

COMMIT;
