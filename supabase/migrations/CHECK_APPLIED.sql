-- Which Staff Ops migrations have actually been applied?
--
-- Probes the schema directly, so it is correct even if nothing has been
-- recorded. Run it any time; it changes nothing.
--
-- Once 069_migration_tracking.sql has been applied you can also just read the
-- history, which needs no hand-maintained probe list:
--
--     SELECT * FROM v_migration_status;

SELECT
    m.migration,
    m.creates,
    CASE WHEN m.present THEN '✅ applied' ELSE '❌ NOT APPLIED' END AS status
FROM (
    VALUES
      ('060_attendance_codes',
       'attendance_codes, comp_off_ledger',
       to_regclass('public.attendance_codes') IS NOT NULL),

      ('061_staff_ops_user_language',
       'users.preferred_language',
       EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'preferred_language')),

      ('062_staff_ops_core',
       'staff_ops_employee_profiles, designations, agencies, employee_documents',
       to_regclass('public.staff_ops_employee_profiles') IS NOT NULL),

      ('063_staff_ops_operations',
       'ot_records, shift_offers, casual_workers, agency_compliance',
       to_regclass('public.staff_ops_ot_records') IS NOT NULL),

      ('064_staff_ops_governance',
       'settings, audit_log, month_close, leave date range',
       to_regclass('public.staff_ops_settings') IS NOT NULL),

      ('065_staff_ops_demo_seed',
       'demo hotel (optional — skip in production)',
       EXISTS (SELECT 1 FROM pg_class WHERE relname = 'properties')
         AND EXISTS (SELECT 1 FROM properties
                      WHERE id = 'd0000000-0000-4000-a000-000000000010')),

      ('066_staff_ops_roles',
       'SUPERVISOR + TIME_OFFICE roles',
       EXISTS (SELECT 1 FROM pg_proc
                WHERE proname = 'canonical_user_role'
                  AND prosrc LIKE '%SUPERVISOR%')),

      ('067_leave_property_not_null',
       'leave_requests.property_id NOT NULL',
       EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name = 'leave_requests'
                  AND column_name = 'property_id'
                  AND is_nullable = 'NO')),

      ('068_staff_ops_exit_revokes_access',
       'exit revokes access (trigger + RLS)',
       EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'current_user_has_exited'))
) AS m(migration, creates, present)
ORDER BY m.migration;
