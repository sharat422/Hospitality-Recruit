-- Leaving the hotel revokes Staff Ops access immediately.
--
-- Two status columns exist and neither is going away:
--   users.employment_status            -- 'ALUMNI', set by the exit flow
--   staff_ops_employee_profiles.status -- 'ACTIVE'|'ON_NOTICE'|'LEFT'|'ABSCONDING'
--
-- build_access_context() re-reads the users row on every request, so if the
-- Staff Ops status is mirrored onto users.employment_status the auth path
-- needs no extra query and revocation is effective on the very next call.
-- This migration installs that mirror as a trigger, so the two cannot drift
-- no matter which code path marks someone as having left.
--
-- ON_NOTICE is deliberately NOT a revoking status: someone serving notice is
-- still working and still needs their roster and attendance.
BEGIN;

-- Preflight. Without this the failure is a bare "relation ... does not exist"
-- on the CREATE TRIGGER below, and because the whole file is one transaction
-- the RLS changes further down roll back too — so the feature looks installed
-- and is not.
DO $$ BEGIN
    IF to_regclass('public.staff_ops_employee_profiles') IS NULL THEN
        RAISE EXCEPTION
          E'Migration 062_staff_ops_core.sql has not been applied.\n'
          '068 installs a trigger on staff_ops_employee_profiles, which 062 creates.\n'
          'Apply in order: 062 -> 063 -> 064 -> 066 -> 067 -> 068 (065 is an optional demo seed).\n'
          'Run supabase/migrations/CHECK_APPLIED.sql to see what is already in place.';
    END IF;
END $$;

CREATE OR REPLACE FUNCTION staff_ops_sync_employment_status()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status IN ('LEFT', 'ABSCONDING') THEN
        -- Mirror the Staff Ops verdict onto the column the auth path reads.
        UPDATE users
           SET employment_status = NEW.status,
               updated_at = NOW()
         WHERE id = NEW.employee_id
           AND COALESCE(employment_status, '') <> NEW.status;

    ELSIF NEW.status IN ('ACTIVE', 'ON_NOTICE')
          AND COALESCE(OLD.status, '') IN ('LEFT', 'ABSCONDING') THEN
        -- Reinstated (a rehire, or a correction to a wrong exit).
        UPDATE users
           SET employment_status = 'ACTIVE',
               updated_at = NOW()
         WHERE id = NEW.employee_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS staff_ops_sync_employment_status_trg ON staff_ops_employee_profiles;
CREATE TRIGGER staff_ops_sync_employment_status_trg
    AFTER INSERT OR UPDATE OF status ON staff_ops_employee_profiles
    FOR EACH ROW EXECUTE FUNCTION staff_ops_sync_employment_status();

-- Backfill anyone already marked as having left before this trigger existed.
UPDATE users u
   SET employment_status = p.status
  FROM staff_ops_employee_profiles p
 WHERE p.employee_id = u.id
   AND p.status IN ('LEFT', 'ABSCONDING')
   AND COALESCE(u.employment_status, '') <> p.status;

-- The same rule inside the database, so RLS agrees with the API. An exited
-- user is denied every permission except their own payslips and documents.
CREATE OR REPLACE FUNCTION current_user_has_exited()
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
    SELECT COALESCE(
        (SELECT upper(COALESCE(employment_status, 'ACTIVE'))
           IN ('ALUMNI','LEFT','ABSCONDING','TERMINATED','RESIGNED','INACTIVE','SUSPENDED')
           FROM users WHERE id = auth.uid()),
        FALSE);
$$;

-- Wraps the existing check rather than replacing it: the permission matrix in
-- rbac_has_permission() is untouched, an exit just narrows the result.
CREATE OR REPLACE FUNCTION rbac_has_permission(permission TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public AS $$
DECLARE r TEXT := current_user_role();
BEGIN
 IF current_user_has_exited() THEN
   RETURN permission = ANY(ARRAY['payroll.read','documents.read']);
 END IF;
 IF r = 'OWNER' THEN RETURN TRUE; END IF;
 IF r = 'GROUP_ADMIN_HR' THEN RETURN permission <> 'financial.manage'; END IF;
 IF r = 'GENERAL_MANAGER' THEN RETURN permission = ANY(ARRAY['candidates.read','employees.read','employees.manage','jobs.read','jobs.manage','applications.read','applications.manage','payroll.read','attendance.read','attendance.manage','leave.read','leave.manage','compliance.read','documents.read','documents.manage','reports.read','reports.financial','complaints.create','complaints.read','complaints.manage','properties.read','financial.read']); END IF;
 IF r = 'HR_MANAGER' THEN RETURN permission = ANY(ARRAY['candidates.read','candidates.manage','employees.read','employees.manage','jobs.read','jobs.manage','applications.read','applications.manage','payroll.read','attendance.read','leave.read','leave.manage','compliance.read','compliance.manage','documents.read','documents.manage','reports.read','complaints.create','complaints.read','complaints.manage','properties.read']); END IF;
 IF r = 'DEPARTMENT_HEAD' THEN RETURN permission = ANY(ARRAY['candidates.read','employees.read','jobs.read','applications.read','applications.manage','attendance.read','attendance.manage','leave.read','leave.manage','documents.read','reports.read','complaints.create','properties.read']); END IF;
 IF r = 'SUPERVISOR' THEN RETURN permission = ANY(ARRAY['employees.read','attendance.read','attendance.manage','leave.read','leave.manage','documents.read','reports.read','complaints.create','properties.read']); END IF;
 IF r = 'TIME_OFFICE' THEN RETURN permission = ANY(ARRAY['employees.read','attendance.read','attendance.manage','complaints.create','properties.read']); END IF;
 IF r = 'RECRUITER' THEN RETURN permission = ANY(ARRAY['candidates.read','candidates.manage','jobs.read','jobs.manage','applications.read','applications.manage','documents.read','documents.manage','reports.read','complaints.create','properties.read']); END IF;
 IF r = 'EMPLOYEE' THEN RETURN permission = ANY(ARRAY['payroll.read','attendance.read','leave.read','complaints.create','documents.read','properties.read']); END IF;
 RETURN permission = ANY(ARRAY['applications.read','documents.read']);
END $$;

COMMENT ON FUNCTION current_user_has_exited IS
    'True when the signed-in user has left. Mirrors EXITED_EMPLOYMENT_STATUSES in app/services/rbac_service.py.';

COMMIT;
