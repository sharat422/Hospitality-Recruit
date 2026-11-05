-- Canonical RBAC for hotel groups, properties, departments and self-service.
BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL;
ALTER TABLE property_memberships ADD COLUMN IF NOT EXISTS department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS property_id UUID REFERENCES properties(id) ON DELETE SET NULL;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS candidates_user_id_unique ON candidates(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS applications_scope_idx ON applications(org_id, property_id, department_id);
CREATE INDEX IF NOT EXISTS users_department_idx ON users(department_id);

UPDATE candidates c SET user_id = u.id FROM users u
WHERE c.user_id IS NULL AND lower(c.email) = lower(u.email) AND c.org_id = u.org_id;
UPDATE applications a SET org_id = c.org_id FROM candidates c
WHERE a.candidate_id = c.id AND a.org_id IS NULL;
UPDATE applications a SET property_id = j.property_id, department_id = j.department_id
FROM jobs j WHERE a.job_role_id = j.id AND a.property_id IS NULL;

CREATE OR REPLACE FUNCTION canonical_user_role(raw_role TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
 SELECT CASE lower(COALESCE(raw_role, 'candidate'))
  WHEN 'owner' THEN 'OWNER' WHEN 'super_admin' THEN 'OWNER'
  WHEN 'group_admin' THEN 'GROUP_ADMIN_HR' WHEN 'admin' THEN 'GROUP_ADMIN_HR' WHEN 'hr_admin' THEN 'GROUP_ADMIN_HR'
  WHEN 'general_manager' THEN 'GENERAL_MANAGER' WHEN 'gm' THEN 'GENERAL_MANAGER' WHEN 'property_manager' THEN 'GENERAL_MANAGER'
  WHEN 'hr_manager' THEN 'HR_MANAGER' WHEN 'hiring_manager' THEN 'HR_MANAGER' WHEN 'property_hr' THEN 'HR_MANAGER'
  WHEN 'department_head' THEN 'DEPARTMENT_HEAD' WHEN 'department_manager' THEN 'DEPARTMENT_HEAD'
  WHEN 'recruiter' THEN 'RECRUITER' WHEN 'property_recruiter' THEN 'RECRUITER'
  WHEN 'employee' THEN 'EMPLOYEE' WHEN 'viewer' THEN 'EMPLOYEE'
  ELSE CASE WHEN upper(raw_role) IN ('OWNER','GROUP_ADMIN_HR','GENERAL_MANAGER','HR_MANAGER','DEPARTMENT_HEAD','RECRUITER','EMPLOYEE','CANDIDATE') THEN upper(raw_role) ELSE 'CANDIDATE' END
 END
$$;

CREATE OR REPLACE FUNCTION current_user_role()
RETURNS TEXT LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
 SELECT canonical_user_role(role) FROM users WHERE id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION current_user_department_id()
RETURNS UUID LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
 SELECT department_id FROM users WHERE id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION rbac_has_permission(permission TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public AS $$
DECLARE r TEXT := current_user_role();
BEGIN
 IF r = 'OWNER' THEN RETURN TRUE; END IF;
 IF r = 'GROUP_ADMIN_HR' THEN RETURN permission <> 'financial.manage'; END IF;
 IF r = 'GENERAL_MANAGER' THEN RETURN permission = ANY(ARRAY['candidates.read','employees.read','employees.manage','jobs.read','jobs.manage','applications.read','applications.manage','payroll.read','attendance.read','attendance.manage','leave.read','leave.manage','compliance.read','documents.read','documents.manage','reports.read','reports.financial','complaints.create','complaints.read','complaints.manage','properties.read','financial.read']); END IF;
 IF r = 'HR_MANAGER' THEN RETURN permission = ANY(ARRAY['candidates.read','candidates.manage','employees.read','employees.manage','jobs.read','jobs.manage','applications.read','applications.manage','payroll.read','attendance.read','leave.read','leave.manage','compliance.read','compliance.manage','documents.read','documents.manage','reports.read','complaints.create','complaints.read','complaints.manage','properties.read']); END IF;
 IF r = 'DEPARTMENT_HEAD' THEN RETURN permission = ANY(ARRAY['candidates.read','employees.read','jobs.read','applications.read','applications.manage','attendance.read','attendance.manage','leave.read','leave.manage','documents.read','reports.read','complaints.create','properties.read']); END IF;
 IF r = 'RECRUITER' THEN RETURN permission = ANY(ARRAY['candidates.read','candidates.manage','jobs.read','jobs.manage','applications.read','applications.manage','documents.read','documents.manage','reports.read','complaints.create','properties.read']); END IF;
 IF r = 'EMPLOYEE' THEN RETURN permission = ANY(ARRAY['payroll.read','attendance.read','leave.read','complaints.create','documents.read','properties.read']); END IF;
 RETURN permission = ANY(ARRAY['applications.read','documents.read']);
END $$;

CREATE OR REPLACE FUNCTION rbac_department_access(target UUID)
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
 SELECT current_user_role() <> 'DEPARTMENT_HEAD' OR target IS NULL OR target = current_user_department_id()
$$;

-- Users: self-readable; staff management is tenant-scoped. Financial fields must stay in payroll tables.
DROP POLICY IF EXISTS users_own_row ON users;
DROP POLICY IF EXISTS users_rbac_select ON users;
DROP POLICY IF EXISTS users_rbac_update ON users;
CREATE POLICY users_rbac_select ON users FOR SELECT USING (
 id = auth.uid() OR (org_id = current_user_org_id() AND rbac_has_permission('employees.read') AND rbac_department_access(department_id))
);
CREATE POLICY users_rbac_update ON users FOR UPDATE USING (
 id = auth.uid() OR (org_id = current_user_org_id() AND rbac_has_permission('employees.manage') AND rbac_department_access(department_id))
) WITH CHECK (org_id = current_user_org_id());

DROP POLICY IF EXISTS candidates_org_isolation ON candidates;
DROP POLICY IF EXISTS candidates_rbac ON candidates;
CREATE POLICY candidates_rbac ON candidates FOR ALL USING (
 user_id = auth.uid() OR (org_id = current_user_org_id() AND rbac_has_permission('candidates.read'))
) WITH CHECK (org_id = current_user_org_id() AND rbac_has_permission('candidates.manage'));

DROP POLICY IF EXISTS applications_policy ON applications;
DROP POLICY IF EXISTS applications_rbac ON applications;
CREATE POLICY applications_rbac ON applications FOR ALL USING (
 EXISTS (SELECT 1 FROM candidates c WHERE c.id=applications.candidate_id AND c.user_id=auth.uid())
 OR (org_id=current_user_org_id() AND (property_id IS NULL OR has_property_access(property_id))
     AND rbac_department_access(department_id) AND rbac_has_permission('applications.read'))
) WITH CHECK (
 EXISTS (SELECT 1 FROM candidates c WHERE c.id=applications.candidate_id AND c.user_id=auth.uid())
 OR (org_id=current_user_org_id() AND (property_id IS NULL OR has_property_access(property_id))
     AND rbac_department_access(department_id) AND rbac_has_permission('applications.manage'))
);

DROP POLICY IF EXISTS jobs_property_isolation ON jobs;
CREATE POLICY jobs_property_isolation ON jobs FOR ALL USING (
 org_id=current_user_org_id() AND (property_id IS NULL OR has_property_access(property_id))
 AND rbac_department_access(department_id) AND rbac_has_permission('jobs.read')
) WITH CHECK (
 org_id=current_user_org_id() AND (property_id IS NULL OR has_property_access(property_id))
 AND rbac_department_access(department_id) AND rbac_has_permission('jobs.manage')
);

DROP POLICY IF EXISTS ps_policy ON payslips;
CREATE POLICY payslips_self_select ON payslips FOR SELECT USING (
 employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_has_permission('payroll.read'))
);
CREATE POLICY payslips_manage ON payslips FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('payroll.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('payroll.manage'));

DROP POLICY IF EXISTS lr_policy ON leave_requests;
CREATE POLICY leave_self_select ON leave_requests FOR SELECT USING (
 employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_has_permission('leave.read'))
);
CREATE POLICY leave_self_insert ON leave_requests FOR INSERT WITH CHECK (employee_id=auth.uid() AND org_id=current_user_org_id());
CREATE POLICY leave_manage ON leave_requests FOR UPDATE USING (
 org_id=current_user_org_id() AND rbac_has_permission('leave.manage')
) WITH CHECK (org_id=current_user_org_id());

DROP POLICY IF EXISTS ec_policy ON employee_complaints;
CREATE POLICY employee_complaints_self ON employee_complaints FOR SELECT USING (
 employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_has_permission('complaints.read'))
);
CREATE POLICY employee_complaints_create ON employee_complaints FOR INSERT WITH CHECK (
 employee_id=auth.uid() AND org_id=current_user_org_id() AND rbac_has_permission('complaints.create')
);
CREATE POLICY employee_complaints_manage ON employee_complaints FOR UPDATE USING (
 org_id=current_user_org_id() AND rbac_has_permission('complaints.manage')
);

DROP POLICY IF EXISTS hc_policy ON hr_complaints;
CREATE POLICY hr_complaints_self ON hr_complaints FOR SELECT USING (
 employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_has_permission('complaints.read'))
);
CREATE POLICY hr_complaints_create ON hr_complaints FOR INSERT WITH CHECK (
 org_id=current_user_org_id() AND rbac_has_permission('complaints.create')
);
CREATE POLICY hr_complaints_manage ON hr_complaints FOR UPDATE USING (
 org_id=current_user_org_id() AND rbac_has_permission('complaints.manage')
);

-- Tighten property mutation: group admins/owners only; scoped users keep read access.
DROP POLICY IF EXISTS properties_manage_policy ON properties;
CREATE POLICY properties_manage_policy ON properties FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('properties.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('properties.manage'));

-- Attendance and shift data follows the job's property/department. Employees
-- may read only shift matches attached to their linked candidate profile.
DROP POLICY IF EXISTS shifts_org_isolation ON shifts;
CREATE POLICY shifts_rbac ON shifts FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('attendance.read')
 AND EXISTS (SELECT 1 FROM jobs j WHERE j.id=shifts.job_id
   AND (j.property_id IS NULL OR has_property_access(j.property_id))
   AND rbac_department_access(j.department_id))
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('attendance.manage'));

DROP POLICY IF EXISTS shift_matches_org_isolation ON shift_matches;
CREATE POLICY shift_matches_rbac ON shift_matches FOR SELECT USING (
 EXISTS (SELECT 1 FROM candidates c WHERE c.id=shift_matches.candidate_id AND c.user_id=auth.uid())
 OR (org_id=current_user_org_id() AND rbac_has_permission('attendance.read'))
);
CREATE POLICY shift_matches_manage ON shift_matches FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('attendance.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('attendance.manage'));

-- India compliance records contain KYC, statutory identifiers and wages.
DROP POLICY IF EXISTS india_identity_verif_policy ON india_identity_verifications;
CREATE POLICY india_identity_rbac ON india_identity_verifications FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('compliance.read')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('compliance.manage'));
DROP POLICY IF EXISTS epf_esic_policy ON epf_esic_registrations;
CREATE POLICY epf_esic_rbac ON epf_esic_registrations FOR ALL USING (
 org_id=current_user_org_id() AND (
   EXISTS (SELECT 1 FROM candidates c WHERE c.id=epf_esic_registrations.candidate_id AND c.user_id=auth.uid())
   OR rbac_has_permission('compliance.read'))
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('compliance.manage'));
DROP POLICY IF EXISTS labour_code_policy ON labour_code_compliance;
CREATE POLICY labour_code_rbac ON labour_code_compliance FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('compliance.read')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('compliance.manage'));
DROP POLICY IF EXISTS working_hours_policy ON working_hours_compliance;
CREATE POLICY working_hours_rbac ON working_hours_compliance FOR ALL USING (
 org_id=current_user_org_id() AND (employee_id=auth.uid() OR rbac_has_permission('attendance.read'))
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('attendance.manage'));
DROP POLICY IF EXISTS pt_records_policy ON professional_tax_records;
CREATE POLICY professional_tax_rbac ON professional_tax_records FOR ALL USING (
 org_id=current_user_org_id() AND (
   EXISTS (SELECT 1 FROM candidates c WHERE c.id=professional_tax_records.candidate_id AND c.user_id=auth.uid())
   OR rbac_has_permission('payroll.read'))
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('payroll.manage'));
DROP POLICY IF EXISTS fssai_policy ON fssai_certificates;
CREATE POLICY fssai_rbac ON fssai_certificates FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('compliance.read')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('compliance.manage'));
DROP POLICY IF EXISTS india_audit_select_policy ON india_compliance_audit_logs;
CREATE POLICY india_audit_rbac ON india_compliance_audit_logs FOR SELECT USING (
 org_id=current_user_org_id() AND rbac_has_permission('compliance.read')
);

-- Financial and payout details: UPI is self-service; organization-wide payout
-- visibility requires explicit financial permission.
DROP POLICY IF EXISTS employee_upi_policy ON employee_upi_details;
CREATE POLICY employee_upi_self ON employee_upi_details FOR SELECT USING (
 user_id=auth.uid() OR rbac_has_permission('financial.read')
);
CREATE POLICY employee_upi_self_update ON employee_upi_details FOR ALL USING (
 user_id=auth.uid() OR rbac_has_permission('financial.manage')
) WITH CHECK (user_id=auth.uid() OR rbac_has_permission('financial.manage'));
DROP POLICY IF EXISTS referral_programs_policy ON referral_programs;
CREATE POLICY referral_programs_read ON referral_programs FOR SELECT USING (
 org_id=current_user_org_id()
);
CREATE POLICY referral_programs_manage ON referral_programs FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('financial.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('financial.manage'));
DROP POLICY IF EXISTS referral_campaigns_policy ON referral_campaigns;
CREATE POLICY referral_campaigns_read ON referral_campaigns FOR SELECT USING (org_id=current_user_org_id());
CREATE POLICY referral_campaigns_manage ON referral_campaigns FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('financial.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('financial.manage'));
DROP POLICY IF EXISTS employee_badges_policy ON employee_badges;
CREATE POLICY employee_badges_rbac ON employee_badges FOR SELECT USING (
 user_id=auth.uid() OR rbac_has_permission('reports.read')
);

COMMIT;
