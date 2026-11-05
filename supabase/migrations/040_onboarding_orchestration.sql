-- Configurable, offer-driven onboarding built on the existing India onboarding tables.
BEGIN;

CREATE TABLE IF NOT EXISTS onboarding_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID REFERENCES properties(id) ON DELETE CASCADE,
    department_id UUID REFERENCES property_departments(id) ON DELETE CASCADE,
    role_template_id UUID REFERENCES role_templates(id) ON DELETE SET NULL,
    name VARCHAR(160) NOT NULL,
    description TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    auto_start BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (org_id IS NOT NULL OR (property_id IS NULL AND department_id IS NULL AND role_template_id IS NULL))
);

CREATE TABLE IF NOT EXISTS onboarding_template_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID NOT NULL REFERENCES onboarding_templates(id) ON DELETE CASCADE,
    stage TEXT NOT NULL CHECK (stage IN ('documents','kyc','certifications','payroll','ready')),
    task_type VARCHAR(80) NOT NULL,
    task_label VARCHAR(255) NOT NULL,
    instructions TEXT,
    is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    due_offset_days INTEGER NOT NULL DEFAULT -1,
    weight NUMERIC(8,2) NOT NULL DEFAULT 1 CHECK (weight > 0),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(template_id, task_type)
);

ALTER TABLE onboarding_flows
    ADD COLUMN IF NOT EXISTS application_id UUID REFERENCES applications(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS template_id UUID REFERENCES onboarding_templates(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS manager_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS offer_accepted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_candidate_activity_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS ghosting_risk_score NUMERIC(5,4) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ghosting_risk_level VARCHAR(20) NOT NULL DEFAULT 'LOW',
    ADD COLUMN IF NOT EXISTS ghosting_risk_signals JSONB NOT NULL DEFAULT '[]';

ALTER TABLE onboarding_tasks
    ADD COLUMN IF NOT EXISTS template_task_id UUID REFERENCES onboarding_template_tasks(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS instructions TEXT,
    ADD COLUMN IF NOT EXISTS weight NUMERIC(8,2) NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS onboarding_flow_application_unique
    ON onboarding_flows(application_id) WHERE application_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS onboarding_templates_scope_idx
    ON onboarding_templates(org_id, property_id, department_id, role_template_id, is_active);
CREATE INDEX IF NOT EXISTS onboarding_flows_scope_idx
    ON onboarding_flows(org_id, property_id, department_id, status);

-- A global fallback is used only when an organization has no scoped template.
INSERT INTO onboarding_templates (id, name, description, is_active, auto_start)
VALUES ('00000000-0000-0000-0000-000000000040', 'India Standard Onboarding',
        'Fallback template for document, KYC, statutory, payroll and joining readiness.', TRUE, TRUE)
ON CONFLICT (id) DO NOTHING;

INSERT INTO onboarding_template_tasks
    (template_id, stage, task_type, task_label, is_mandatory, is_system, due_offset_days, sort_order)
VALUES
 ('00000000-0000-0000-0000-000000000040','documents','aadhaar_upload','Aadhaar verification (last four digits only)',TRUE,FALSE,-7,10),
 ('00000000-0000-0000-0000-000000000040','documents','pan_upload','PAN verification',TRUE,FALSE,-7,20),
 ('00000000-0000-0000-0000-000000000040','documents','bank_details','Bank account and IFSC details',TRUE,FALSE,-7,30),
 ('00000000-0000-0000-0000-000000000040','kyc','identity_kyc','Identity and address KYC review',TRUE,FALSE,-5,10),
 ('00000000-0000-0000-0000-000000000040','certifications','role_certifications','Role and FSSAI certificates reviewed',FALSE,FALSE,-3,10),
 ('00000000-0000-0000-0000-000000000040','payroll','appointment_esign','Appointment letter accepted and eSigned',TRUE,FALSE,-4,10),
 ('00000000-0000-0000-0000-000000000040','payroll','pf_form2','PF Form 2 completed',TRUE,FALSE,-2,20),
 ('00000000-0000-0000-0000-000000000040','payroll','esic_declaration','ESIC declaration completed',TRUE,FALSE,-2,30),
 ('00000000-0000-0000-0000-000000000040','payroll','payroll_setup','Compensation and payroll setup approved',TRUE,FALSE,-1,40),
 ('00000000-0000-0000-0000-000000000040','ready','manager_assigned','Reporting manager assigned',TRUE,FALSE,-1,10),
 ('00000000-0000-0000-0000-000000000040','ready','joining_confirmed','Joining date and reporting instructions confirmed',TRUE,FALSE,0,20)
ON CONFLICT (template_id, task_type) DO NOTHING;

CREATE OR REPLACE FUNCTION select_onboarding_template(
    p_org UUID, p_property UUID, p_department UUID, p_role_template UUID
) RETURNS UUID LANGUAGE sql STABLE SET search_path=public AS $$
 SELECT id FROM onboarding_templates
 WHERE is_active AND auto_start AND (org_id=p_org OR org_id IS NULL)
   AND (property_id IS NULL OR property_id=p_property)
   AND (department_id IS NULL OR department_id=p_department)
   AND (role_template_id IS NULL OR role_template_id=p_role_template)
 ORDER BY (org_id IS NOT NULL)::int DESC, (property_id IS NOT NULL)::int DESC,
          (department_id IS NOT NULL)::int DESC, (role_template_id IS NOT NULL)::int DESC,
          version DESC, created_at DESC
 LIMIT 1
$$;

CREATE OR REPLACE FUNCTION start_onboarding_after_offer_acceptance()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE
    c candidates%ROWTYPE; j jobs%ROWTYPE; v_flow UUID; v_template UUID;
    v_name TEXT; v_joining DATE;
BEGIN
    IF upper(NEW.status) <> 'OFFER_ACCEPTED' OR upper(COALESCE(OLD.status,''))='OFFER_ACCEPTED' THEN
        RETURN NEW;
    END IF;
    SELECT * INTO c FROM candidates WHERE id=NEW.candidate_id;
    SELECT * INTO j FROM jobs WHERE id=NEW.job_id;
    IF c.id IS NULL THEN RETURN NEW; END IF;
    v_joining := CASE
      WHEN COALESCE(NEW.form_data->>'joining_date','') ~ '^\d{4}-\d{2}-\d{2}$'
      THEN (NEW.form_data->>'joining_date')::date ELSE CURRENT_DATE + 14 END;
    v_template := select_onboarding_template(COALESCE(NEW.org_id,c.org_id), NEW.property_id,
                                              NEW.department_id, j.role_template_id);
    v_name := trim(COALESCE(c.first_name,'') || ' ' || COALESCE(c.last_name,''));

    INSERT INTO onboarding_flows
      (org_id,candidate_id,job_id,application_id,template_id,property_id,department_id,
       manager_id,candidate_name,role_title,department,property_name,manager_name,
       joining_date,offer_date,offer_accepted_at,last_candidate_activity_at,status)
    VALUES
      (COALESCE(NEW.org_id,c.org_id),NEW.candidate_id,NEW.job_id,NEW.id,v_template,
       NEW.property_id,NEW.department_id,j.hiring_manager_id,v_name,COALESCE(j.title,'Staff'),
       COALESCE(j.department,''),COALESCE(j.property_name,''),
       COALESCE((SELECT u.full_name FROM users u WHERE u.id=j.hiring_manager_id),''),
       v_joining,CURRENT_DATE,NOW(),NOW(),'active')
    ON CONFLICT (application_id) WHERE application_id IS NOT NULL DO UPDATE
      SET offer_accepted_at=COALESCE(onboarding_flows.offer_accepted_at,NOW()), updated_at=NOW()
    RETURNING id INTO v_flow;

    INSERT INTO onboarding_tasks
      (flow_id,org_id,candidate_id,template_task_id,stage,task_type,task_label,instructions,
       is_mandatory,is_system,status,due_date,weight,sort_order)
    SELECT v_flow,COALESCE(NEW.org_id,c.org_id),NEW.candidate_id,t.id,t.stage,t.task_type,
           t.task_label,t.instructions,t.is_mandatory,t.is_system,'pending',v_joining+t.due_offset_days,
           t.weight,t.sort_order
    FROM onboarding_template_tasks t WHERE t.template_id=v_template
      AND NOT EXISTS (SELECT 1 FROM onboarding_tasks x WHERE x.flow_id=v_flow AND x.task_type=t.task_type);

    INSERT INTO preboarding_messages
      (flow_id,org_id,candidate_id,candidate_phone,template_key,template_label,message_body,scheduled_for,status)
    SELECT v_flow,COALESCE(NEW.org_id,c.org_id),NEW.candidate_id,c.phone,'offer_accepted_welcome',
           'Offer accepted welcome',
           'Welcome '||COALESCE(NULLIF(c.first_name,''),'to the team')||'! Your onboarding checklist is ready. Reply HELP if you need assistance.',
           NOW(),'scheduled'
    WHERE c.phone IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM preboarding_messages m WHERE m.flow_id=v_flow AND m.template_key='offer_accepted_welcome');
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_application_offer_onboarding ON applications;
CREATE TRIGGER trg_application_offer_onboarding
AFTER UPDATE OF status ON applications FOR EACH ROW
EXECUTE FUNCTION start_onboarding_after_offer_acceptance();

ALTER TABLE onboarding_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE onboarding_template_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE onboarding_flows ENABLE ROW LEVEL SECURITY;
ALTER TABLE onboarding_tasks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS onboarding_templates_scope ON onboarding_templates;
CREATE POLICY onboarding_templates_scope ON onboarding_templates FOR SELECT USING (
 org_id IS NULL OR (org_id=current_user_org_id() AND (property_id IS NULL OR has_property_access(property_id)))
);
DROP POLICY IF EXISTS onboarding_templates_manage ON onboarding_templates;
CREATE POLICY onboarding_templates_manage ON onboarding_templates FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('employees.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('employees.manage'));
DROP POLICY IF EXISTS onboarding_template_tasks_scope ON onboarding_template_tasks;
CREATE POLICY onboarding_template_tasks_scope ON onboarding_template_tasks FOR ALL USING (
 EXISTS (SELECT 1 FROM onboarding_templates t WHERE t.id=template_id AND
   (t.org_id IS NULL OR (t.org_id=current_user_org_id() AND rbac_has_permission('employees.read'))))
) WITH CHECK (EXISTS (SELECT 1 FROM onboarding_templates t WHERE t.id=template_id AND
   t.org_id=current_user_org_id() AND rbac_has_permission('employees.manage')));
DROP POLICY IF EXISTS onboarding_flows_scope ON onboarding_flows;
CREATE POLICY onboarding_flows_scope ON onboarding_flows FOR ALL USING (
 org_id=current_user_org_id() AND (property_id IS NULL OR has_property_access(property_id))
 AND rbac_department_access(department_id) AND rbac_has_permission('employees.read')
) WITH CHECK (org_id=current_user_org_id() AND (property_id IS NULL OR has_property_access(property_id))
 AND rbac_department_access(department_id) AND rbac_has_permission('employees.manage'));
DROP POLICY IF EXISTS onboarding_tasks_scope ON onboarding_tasks;
CREATE POLICY onboarding_tasks_scope ON onboarding_tasks FOR ALL USING (
 EXISTS (SELECT 1 FROM onboarding_flows f WHERE f.id=flow_id AND f.org_id=current_user_org_id()
  AND (f.property_id IS NULL OR has_property_access(f.property_id)) AND rbac_department_access(f.department_id))
) WITH CHECK (EXISTS (SELECT 1 FROM onboarding_flows f WHERE f.id=flow_id AND f.org_id=current_user_org_id()
  AND (f.property_id IS NULL OR has_property_access(f.property_id)) AND rbac_department_access(f.department_id)
  AND rbac_has_permission('employees.manage')));

-- Keep dashboard reads compatible while exposing the new persisted risk fields.
CREATE OR REPLACE VIEW v_onboarding_dashboard WITH (security_invoker = true) AS
SELECT f.id,f.org_id,f.candidate_id,f.candidate_name,f.role_title,f.department,f.property_name,
 f.manager_name,f.joining_date,f.offer_date,f.current_stage,f.completion_pct,f.stage_completion,
 f.is_at_risk,f.at_risk_reason,f.status,f.preboarding_started_at,f.created_at,
 (SELECT COUNT(*) FROM onboarding_tasks t WHERE t.flow_id=f.id AND t.is_mandatory) total_tasks,
 (SELECT COUNT(*) FROM onboarding_tasks t WHERE t.flow_id=f.id AND t.status IN ('completed','waived')) done_tasks,
 (SELECT esign_status FROM appointment_letters l WHERE l.flow_id=f.id ORDER BY generated_at DESC LIMIT 1) letter_esign_status,
 CASE WHEN f.joining_date IS NOT NULL THEN f.joining_date-CURRENT_DATE ELSE NULL END days_until_joining,
 (SELECT COUNT(*) FROM preboarding_messages m WHERE m.flow_id=f.id AND m.status='sent') pb_messages_sent,
 (SELECT COUNT(*) FROM preboarding_messages m WHERE m.flow_id=f.id) pb_messages_total,
 f.application_id,f.template_id,f.property_id,f.department_id,f.manager_id,f.offer_accepted_at,
 f.last_candidate_activity_at,f.ghosting_risk_score,f.ghosting_risk_level,f.ghosting_risk_signals
FROM onboarding_flows f;

COMMIT;
