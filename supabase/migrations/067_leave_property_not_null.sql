-- Tighten leave_requests.property_id to NOT NULL (design review Q3).
--
-- 064 added the column and backfilled it from users.active_property_id. Rows
-- whose employee had no active property could not be filled in, so this runs
-- as a self-checking step: it reports what is left, fills what it safely can,
-- and only adds the constraint when nothing remains NULL.
--
-- Running it twice is harmless. If it reports rows still unresolved, fix
-- those rows and run it again.
BEGIN;

-- Preflight: 064 adds leave_requests.property_id, which this file tightens.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'leave_requests' AND column_name = 'property_id') THEN
        RAISE EXCEPTION
          E'Migration 064_staff_ops_governance.sql has not been applied.\n'
          '067 tightens leave_requests.property_id, which 064 adds.\n'
          'Apply 064 first. Run supabase/migrations/CHECK_APPLIED.sql to see what is in place.';
    END IF;
END $$;

DO $$
DECLARE
    remaining BIGINT;
    repaired  BIGINT;
BEGIN
    -- Second chance: some employees gained an active property since 064 ran.
    UPDATE leave_requests lr
       SET property_id = u.active_property_id
      FROM users u
     WHERE lr.employee_id = u.id
       AND lr.property_id IS NULL
       AND u.active_property_id IS NOT NULL;
    GET DIAGNOSTICS repaired = ROW_COUNT;

    -- Third chance: a single-property organisation has only one answer.
    UPDATE leave_requests lr
       SET property_id = p.id
      FROM properties p
     WHERE lr.property_id IS NULL
       AND p.org_id = lr.org_id
       AND (SELECT COUNT(*) FROM properties p2 WHERE p2.org_id = lr.org_id) = 1;

    SELECT COUNT(*) INTO remaining FROM leave_requests WHERE property_id IS NULL;

    IF remaining = 0 THEN
        ALTER TABLE leave_requests ALTER COLUMN property_id SET NOT NULL;
        RAISE NOTICE 'leave_requests.property_id is now NOT NULL (% row(s) repaired in this run).', repaired;
    ELSE
        -- Deliberately not failing: an unfillable historical row must not
        -- block the migration. The constraint is simply not added yet.
        RAISE NOTICE
          'leave_requests.property_id left NULLABLE: % row(s) still have no hotel. '
          'Resolve them (see query in the comment below) and re-run this migration.',
          remaining;
    END IF;
END $$;

-- To inspect what is unresolved:
--   SELECT lr.id, lr.employee_id, lr.leave_date, u.full_name, u.active_property_id
--     FROM leave_requests lr LEFT JOIN users u ON u.id = lr.employee_id
--    WHERE lr.property_id IS NULL;

COMMIT;
