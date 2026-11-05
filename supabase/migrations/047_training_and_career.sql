-- Configurable learning and career development. Extends existing HR records/jobs.
BEGIN;

CREATE OR REPLACE FUNCTION rbac_has_permission(permission TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public AS $$
DECLARE r TEXT := current_user_role();
BEGIN
 IF r='OWNER' THEN RETURN TRUE; END IF;
 IF r='GROUP_ADMIN_HR' THEN RETURN permission <> 'financial.manage'; END IF;
 IF r IN ('GENERAL_MANAGER','HR_MANAGER') AND permission IN ('training.read','training.manage','career.read','career.manage') THEN RETURN TRUE; END IF;
 IF r='DEPARTMENT_HEAD' AND permission IN ('training.read','training.manage','career.read','career.manage') THEN RETURN TRUE; END IF;
 IF r='EMPLOYEE' AND permission IN ('training.read','career.read') THEN RETURN TRUE; END IF;
 IF r='GENERAL_MANAGER' THEN RETURN permission = ANY(ARRAY['candidates.read','employees.read','employees.manage','jobs.read','jobs.manage','applications.read','applications.manage','payroll.read','attendance.read','attendance.manage','leave.read','leave.manage','compliance.read','documents.read','documents.manage','reports.read','reports.financial','complaints.create','complaints.read','complaints.manage','properties.read','financial.read','performance.read','performance.manage']); END IF;
 IF r='HR_MANAGER' THEN RETURN permission = ANY(ARRAY['candidates.read','candidates.manage','employees.read','employees.manage','jobs.read','jobs.manage','applications.read','applications.manage','payroll.read','attendance.read','leave.read','leave.manage','compliance.read','compliance.manage','documents.read','documents.manage','reports.read','complaints.create','complaints.read','complaints.manage','properties.read','performance.read','performance.manage']); END IF;
 IF r='DEPARTMENT_HEAD' THEN RETURN permission = ANY(ARRAY['candidates.read','employees.read','jobs.read','applications.read','applications.manage','attendance.read','attendance.manage','leave.read','leave.manage','documents.read','reports.read','complaints.create','properties.read','performance.read','performance.manage']); END IF;
 IF r='RECRUITER' THEN RETURN permission = ANY(ARRAY['candidates.read','candidates.manage','jobs.read','jobs.manage','applications.read','applications.manage','documents.read','documents.manage','reports.read','complaints.create','properties.read']); END IF;
 IF r='EMPLOYEE' THEN RETURN permission = ANY(ARRAY['payroll.read','attendance.read','leave.read','complaints.create','documents.read','properties.read','performance.read']); END IF;
 RETURN permission = ANY(ARRAY['applications.read','documents.read']);
END $$;

CREATE TABLE IF NOT EXISTS skill_definitions (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
 code VARCHAR(80) NOT NULL, name VARCHAR(160) NOT NULL, department_name VARCHAR(120), description TEXT,
 is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE NULLS NOT DISTINCT (org_id, code)
);

CREATE TABLE IF NOT EXISTS training_courses (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
 property_id UUID REFERENCES properties(id) ON DELETE SET NULL, department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
 title VARCHAR(255) NOT NULL, description TEXT, category VARCHAR(50) NOT NULL DEFAULT 'ROLE_SKILL',
 delivery_type VARCHAR(20) NOT NULL DEFAULT 'VIDEO' CHECK (delivery_type IN ('VIDEO','DOCUMENT','CLASSROOM','BLENDED')),
 content_url TEXT, duration_minutes INT NOT NULL DEFAULT 0 CHECK (duration_minutes >= 0), pass_score NUMERIC(5,2) NOT NULL DEFAULT 70,
 certificate_type_id UUID REFERENCES certification_types(id) ON DELETE SET NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE,
 created_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS training_course_skills (
 course_id UUID NOT NULL REFERENCES training_courses(id) ON DELETE CASCADE,
 skill_id UUID NOT NULL REFERENCES skill_definitions(id) ON DELETE CASCADE,
 proficiency_awarded SMALLINT NOT NULL DEFAULT 1 CHECK (proficiency_awarded BETWEEN 1 AND 5), PRIMARY KEY(course_id, skill_id)
);

CREATE TABLE IF NOT EXISTS training_quizzes (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), course_id UUID NOT NULL UNIQUE REFERENCES training_courses(id) ON DELETE CASCADE,
 title VARCHAR(200) NOT NULL, pass_score NUMERIC(5,2) NOT NULL DEFAULT 70, max_attempts INT NOT NULL DEFAULT 3 CHECK(max_attempts > 0), is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS training_quiz_questions (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), quiz_id UUID NOT NULL REFERENCES training_quizzes(id) ON DELETE CASCADE,
 question_text TEXT NOT NULL, options JSONB NOT NULL, correct_option VARCHAR(20) NOT NULL, explanation TEXT, order_index INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS training_quiz_attempts (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 enrollment_id UUID NOT NULL REFERENCES employee_training_records(id) ON DELETE CASCADE, employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 quiz_id UUID NOT NULL REFERENCES training_quizzes(id) ON DELETE CASCADE, answers JSONB NOT NULL DEFAULT '{}', score NUMERIC(5,2) NOT NULL,
 passed BOOLEAN NOT NULL, attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE employee_training_records
 ADD COLUMN IF NOT EXISTS course_id UUID REFERENCES training_courses(id) ON DELETE SET NULL,
 ADD COLUMN IF NOT EXISTS progress_pct NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK(progress_pct BETWEEN 0 AND 100),
 ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS quiz_passed BOOLEAN,
 ADD COLUMN IF NOT EXISTS certificate_id UUID REFERENCES employee_certifications(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS training_one_active_course_employee ON employee_training_records(employee_id,course_id)
 WHERE course_id IS NOT NULL AND status IN ('ASSIGNED','IN_PROGRESS','COMPLETED');

CREATE TABLE IF NOT EXISTS employee_skills (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, skill_id UUID NOT NULL REFERENCES skill_definitions(id) ON DELETE CASCADE,
 proficiency SMALLINT NOT NULL DEFAULT 1 CHECK(proficiency BETWEEN 1 AND 5), source VARCHAR(30) NOT NULL DEFAULT 'MANAGER',
 evidence_id UUID, verified_by UUID REFERENCES users(id) ON DELETE SET NULL, verified_at TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(employee_id,skill_id)
);

CREATE TABLE IF NOT EXISTS career_pathways (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
 property_id UUID REFERENCES properties(id) ON DELETE SET NULL, department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
 department_name VARCHAR(120) NOT NULL, name VARCHAR(200) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE,
 created_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE NULLS NOT DISTINCT(org_id,property_id,department_id,name)
);

CREATE TABLE IF NOT EXISTS career_pathway_steps (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), pathway_id UUID NOT NULL REFERENCES career_pathways(id) ON DELETE CASCADE,
 step_order INT NOT NULL, current_role_title VARCHAR(180) NOT NULL, target_role_title VARCHAR(180) NOT NULL,
 minimum_performance_score NUMERIC(5,2) NOT NULL DEFAULT 70, minimum_tenure_months INT NOT NULL DEFAULT 0,
 required_skills JSONB NOT NULL DEFAULT '[]', required_course_ids JSONB NOT NULL DEFAULT '[]', is_active BOOLEAN NOT NULL DEFAULT TRUE,
 UNIQUE(pathway_id,step_order)
);

CREATE TABLE IF NOT EXISTS employee_career_plans (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, pathway_id UUID NOT NULL REFERENCES career_pathways(id) ON DELETE CASCADE,
 target_step_id UUID REFERENCES career_pathway_steps(id) ON DELETE SET NULL, status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','READY','PROMOTED','PAUSED','CANCELLED')),
 manager_notes TEXT, created_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(employee_id,pathway_id)
);

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS visibility VARCHAR(20) NOT NULL DEFAULT 'PUBLIC' CHECK(visibility IN ('PUBLIC','INTERNAL','BOTH'));
CREATE INDEX IF NOT EXISTS jobs_internal_idx ON jobs(org_id,status,visibility);

-- Global starter templates can be copied/customised by each organization.
INSERT INTO career_pathways(org_id,department_name,name) VALUES
 (NULL,'Front Office','Front Office Operations Path'),
 (NULL,'Housekeeping','Housekeeping Leadership Path'),
 (NULL,'Kitchen','Culinary Career Path'),
 (NULL,'Food & Beverage','Food & Beverage Service Path')
ON CONFLICT DO NOTHING;
INSERT INTO career_pathway_steps(pathway_id,step_order,current_role_title,target_role_title,minimum_performance_score,minimum_tenure_months,required_skills)
SELECT p.id,v.step_order,v.current_role,v.target_role,v.score,v.tenure,v.skills::jsonb
FROM (VALUES
 ('Front Office Operations Path',1,'Front Desk Agent','Front Desk Supervisor',75,12,'[{"name":"Guest relations","min_proficiency":3},{"name":"PMS operations","min_proficiency":3}]'),
 ('Housekeeping Leadership Path',1,'Room Attendant','Housekeeping Supervisor',75,12,'[{"name":"Room quality inspection","min_proficiency":3},{"name":"Chemical safety","min_proficiency":3}]'),
 ('Culinary Career Path',1,'Commis Chef','Chef de Partie',80,18,'[{"name":"Station management","min_proficiency":3},{"name":"Food safety","min_proficiency":4}]'),
 ('Food & Beverage Service Path',1,'Waiter / Server','F&B Supervisor',75,12,'[{"name":"Upselling","min_proficiency":3},{"name":"Guest complaint handling","min_proficiency":3}]')
) AS v(path_name,step_order,current_role,target_role,score,tenure,skills)
JOIN career_pathways p ON p.org_id IS NULL AND p.name=v.path_name
ON CONFLICT(pathway_id,step_order) DO NOTHING;

-- Tenant-safe RLS. Public templates (org_id NULL) are read-only.
ALTER TABLE skill_definitions ENABLE ROW LEVEL SECURITY; ALTER TABLE training_courses ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_course_skills ENABLE ROW LEVEL SECURITY; ALTER TABLE training_quizzes ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_quiz_questions ENABLE ROW LEVEL SECURITY; ALTER TABLE training_quiz_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_skills ENABLE ROW LEVEL SECURITY; ALTER TABLE career_pathways ENABLE ROW LEVEL SECURITY;
ALTER TABLE career_pathway_steps ENABLE ROW LEVEL SECURITY; ALTER TABLE employee_career_plans ENABLE ROW LEVEL SECURITY;

CREATE POLICY skill_read ON skill_definitions FOR SELECT USING (org_id IS NULL OR org_id=current_user_org_id());
CREATE POLICY skill_manage ON skill_definitions FOR ALL USING (org_id=current_user_org_id() AND rbac_has_permission('training.manage')) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('training.manage'));
CREATE POLICY course_read ON training_courses FOR SELECT USING (org_id IS NULL OR (org_id=current_user_org_id() AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id)));
CREATE POLICY course_manage ON training_courses FOR ALL USING (org_id=current_user_org_id() AND rbac_has_permission('training.manage') AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id)) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('training.manage') AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id));
CREATE POLICY course_skill_read ON training_course_skills FOR SELECT USING (EXISTS(SELECT 1 FROM training_courses c WHERE c.id=course_id AND (c.org_id IS NULL OR c.org_id=current_user_org_id())));
CREATE POLICY course_skill_manage ON training_course_skills FOR ALL USING (rbac_has_permission('training.manage')) WITH CHECK (rbac_has_permission('training.manage'));
CREATE POLICY quiz_read ON training_quizzes FOR SELECT USING (EXISTS(SELECT 1 FROM training_courses c WHERE c.id=course_id AND (c.org_id IS NULL OR c.org_id=current_user_org_id())));
-- Answer keys are server-only for employees. Managers can maintain question banks.
CREATE POLICY question_manage ON training_quiz_questions FOR ALL USING (rbac_has_permission('training.manage')) WITH CHECK (rbac_has_permission('training.manage'));
CREATE POLICY attempt_self ON training_quiz_attempts FOR SELECT USING(employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_has_permission('training.manage')));
CREATE POLICY attempt_insert_self ON training_quiz_attempts FOR INSERT WITH CHECK(employee_id=auth.uid() AND org_id=current_user_org_id());
CREATE POLICY employee_skill_read ON employee_skills FOR SELECT USING(employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_has_permission('career.read')));
CREATE POLICY employee_skill_manage ON employee_skills FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('career.manage')) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('career.manage'));
CREATE POLICY pathway_read ON career_pathways FOR SELECT USING(org_id IS NULL OR (org_id=current_user_org_id() AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id)));
CREATE POLICY pathway_manage ON career_pathways FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('career.manage')) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('career.manage'));
CREATE POLICY pathway_step_read ON career_pathway_steps FOR SELECT USING(EXISTS(SELECT 1 FROM career_pathways p WHERE p.id=pathway_id AND (p.org_id IS NULL OR p.org_id=current_user_org_id())));
CREATE POLICY pathway_step_manage ON career_pathway_steps FOR ALL USING(rbac_has_permission('career.manage')) WITH CHECK(rbac_has_permission('career.manage'));
CREATE POLICY career_plan_read ON employee_career_plans FOR SELECT USING(employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_has_permission('career.read')));
CREATE POLICY career_plan_manage ON employee_career_plans FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('career.manage')) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('career.manage'));

COMMIT;
