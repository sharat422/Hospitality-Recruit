-- Add the SUPERVISOR and TIME_OFFICE roles (PLAN.md step 1).
--
-- The permission matrix exists TWICE: in Python (services/rbac_service.py)
-- for API checks, and here in rbac_has_permission() for row-level security.
-- They must agree. This migration is the SQL half; the Python half changed in
-- the same commit, and tests assert the two stay in step.
--
-- Until this runs, a user whose role is SUPERVISOR or TIME_OFFICE falls
-- through canonical_user_role()'s ELSE branch to CANDIDATE and can see almost
-- nothing. That is a safe failure, but it is a failure.
BEGIN;

-- ---------------------------------------------------------------------------
-- Role canonicalisation
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION canonical_user_role(raw_role TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
 SELECT CASE lower(COALESCE(raw_role, 'candidate'))
  WHEN 'owner' THEN 'OWNER' WHEN 'super_admin' THEN 'OWNER'
  WHEN 'group_admin' THEN 'GROUP_ADMIN_HR' WHEN 'admin' THEN 'GROUP_ADMIN_HR' WHEN 'hr_admin' THEN 'GROUP_ADMIN_HR'
  WHEN 'general_manager' THEN 'GENERAL_MANAGER' WHEN 'gm' THEN 'GENERAL_MANAGER' WHEN 'property_manager' THEN 'GENERAL_MANAGER'
  WHEN 'hr_manager' THEN 'HR_MANAGER' WHEN 'hiring_manager' THEN 'HR_MANAGER' WHEN 'property_hr' THEN 'HR_MANAGER'
  WHEN 'department_head' THEN 'DEPARTMENT_HEAD' WHEN 'department_manager' THEN 'DEPARTMENT_HEAD'
  WHEN 'supervisor' THEN 'SUPERVISOR' WHEN 'shift_incharge' THEN 'SUPERVISOR'
  WHEN 'captain' THEN 'SUPERVISOR' WHEN 'floor_supervisor' THEN 'SUPERVISOR'
  WHEN 'time_office' THEN 'TIME_OFFICE' WHEN 'security' THEN 'TIME_OFFICE'
  WHEN 'gate' THEN 'TIME_OFFICE' WHEN 'security_desk' THEN 'TIME_OFFICE'
  WHEN 'recruiter' THEN 'RECRUITER' WHEN 'property_recruiter' THEN 'RECRUITER'
  WHEN 'employee' THEN 'EMPLOYEE' WHEN 'viewer' THEN 'EMPLOYEE'
  ELSE CASE WHEN upper(raw_role) IN ('OWNER','GROUP_ADMIN_HR','GENERAL_MANAGER','HR_MANAGER',
                                     'DEPARTMENT_HEAD','SUPERVISOR','TIME_OFFICE','RECRUITER',
                                     'EMPLOYEE','CANDIDATE')
            THEN upper(raw_role) ELSE 'CANDIDATE' END
 END
$$;

-- ---------------------------------------------------------------------------
-- Permissions — must mirror PERMISSION_MATRIX in services/rbac_service.py
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION rbac_has_permission(permission TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public AS $$
DECLARE r TEXT := current_user_role();
BEGIN
 IF r = 'OWNER' THEN RETURN TRUE; END IF;
 IF r = 'GROUP_ADMIN_HR' THEN RETURN permission <> 'financial.manage'; END IF;
 IF r = 'GENERAL_MANAGER' THEN RETURN permission = ANY(ARRAY['candidates.read','employees.read','employees.manage','jobs.read','jobs.manage','applications.read','applications.manage','payroll.read','attendance.read','attendance.manage','leave.read','leave.manage','compliance.read','documents.read','documents.manage','reports.read','reports.financial','complaints.create','complaints.read','complaints.manage','properties.read','financial.read']); END IF;
 IF r = 'HR_MANAGER' THEN RETURN permission = ANY(ARRAY['candidates.read','candidates.manage','employees.read','employees.manage','jobs.read','jobs.manage','applications.read','applications.manage','payroll.read','attendance.read','leave.read','leave.manage','compliance.read','compliance.manage','documents.read','documents.manage','reports.read','complaints.create','complaints.read','complaints.manage','properties.read']); END IF;
 IF r = 'DEPARTMENT_HEAD' THEN RETURN permission = ANY(ARRAY['candidates.read','employees.read','jobs.read','applications.read','applications.manage','attendance.read','attendance.manage','leave.read','leave.manage','documents.read','reports.read','complaints.create','properties.read']); END IF;
 -- Runs a department floor: attendance and leave, never pay.
 IF r = 'SUPERVISOR' THEN RETURN permission = ANY(ARRAY['employees.read','attendance.read','attendance.manage','leave.read','leave.manage','documents.read','reports.read','complaints.create','properties.read']); END IF;
 -- Staff entrance desk: manual punch, late marks, no-show flags. Nothing else.
 IF r = 'TIME_OFFICE' THEN RETURN permission = ANY(ARRAY['employees.read','attendance.read','attendance.manage','complaints.create','properties.read']); END IF;
 IF r = 'RECRUITER' THEN RETURN permission = ANY(ARRAY['candidates.read','candidates.manage','jobs.read','jobs.manage','applications.read','applications.manage','documents.read','documents.manage','reports.read','complaints.create','properties.read']); END IF;
 IF r = 'EMPLOYEE' THEN RETURN permission = ANY(ARRAY['payroll.read','attendance.read','leave.read','complaints.create','documents.read','properties.read']); END IF;
 RETURN permission = ANY(ARRAY['applications.read','documents.read']);
END $$;

-- ---------------------------------------------------------------------------
-- Department scoping
-- ---------------------------------------------------------------------------
-- A supervisor is confined to their own department exactly as a department
-- head is. Without this they would see every department in the hotel.
CREATE OR REPLACE FUNCTION rbac_department_access(target UUID)
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
 SELECT current_user_role() NOT IN ('DEPARTMENT_HEAD','SUPERVISOR')
     OR target IS NULL
     OR target = current_user_department_id()
$$;

-- ---------------------------------------------------------------------------
-- Property membership vocabulary
-- ---------------------------------------------------------------------------
-- property_memberships.role is a different vocabulary from users.role and is
-- informational — permissions come from users.role. Two values are added so a
-- supervisor or gate desk can be recorded honestly instead of being filed as
-- PROPERTY_MANAGER.
ALTER TABLE property_memberships
    DROP CONSTRAINT IF EXISTS property_membership_role_check;
ALTER TABLE property_memberships
    ADD CONSTRAINT property_membership_role_check CHECK (role IN (
        'PROPERTY_ADMIN','PROPERTY_HR','PROPERTY_RECRUITER','PROPERTY_MANAGER',
        'PROPERTY_SUPERVISOR','TIME_OFFICE',
        'PAYROLL_ADMIN','COMPLIANCE_ADMIN','VIEWER'
    ));

COMMENT ON FUNCTION rbac_has_permission IS
    'RLS permission check. MUST mirror PERMISSION_MATRIX in app/services/rbac_service.py.';

COMMIT;
