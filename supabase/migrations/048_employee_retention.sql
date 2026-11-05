-- Employee retention and transparent rules-based attrition risk.
BEGIN;

CREATE TABLE IF NOT EXISTS employee_turnover_history (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT, property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
 department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
 event_type VARCHAR(24) NOT NULL CHECK(event_type IN ('RESIGNED','TERMINATED','ABSCONDED','RETIREMENT','TRANSFERRED_OUT','REHIRED')),
 effective_date DATE NOT NULL, reason_category VARCHAR(60), reason_notes TEXT, voluntary BOOLEAN,
 eligible_for_rehire BOOLEAN, recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(employee_id,event_type,effective_date)
);

CREATE TABLE IF NOT EXISTS employee_pulse_surveys (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 property_id UUID REFERENCES properties(id) ON DELETE CASCADE, department_id UUID REFERENCES property_departments(id) ON DELETE CASCADE,
 title VARCHAR(180) NOT NULL, question_text TEXT NOT NULL, scale_min SMALLINT NOT NULL DEFAULT 1,
 scale_max SMALLINT NOT NULL DEFAULT 5, opens_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), closes_at TIMESTAMPTZ,
 is_anonymous BOOLEAN NOT NULL DEFAULT TRUE, status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('DRAFT','ACTIVE','CLOSED','CANCELLED')),
 created_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 CHECK(scale_min < scale_max), CHECK(closes_at IS NULL OR closes_at > opens_at)
);

CREATE TABLE IF NOT EXISTS employee_pulse_responses (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 survey_id UUID NOT NULL REFERENCES employee_pulse_surveys(id) ON DELETE CASCADE,
 employee_id UUID REFERENCES users(id) ON DELETE SET NULL, response_fingerprint VARCHAR(64) NOT NULL,
 score SMALLINT NOT NULL, comment TEXT, submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(survey_id,response_fingerprint)
);

CREATE TABLE IF NOT EXISTS employee_retention_risk_scores (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
 department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
 risk_score NUMERIC(5,2) NOT NULL CHECK(risk_score BETWEEN 0 AND 100),
 risk_level VARCHAR(12) NOT NULL CHECK(risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
 risk_factors JSONB NOT NULL DEFAULT '[]', recommended_actions JSONB NOT NULL DEFAULT '[]', input_snapshot JSONB NOT NULL DEFAULT '{}',
 model_type VARCHAR(24) NOT NULL DEFAULT 'RULES_BASED' CHECK(model_type IN ('RULES_BASED','VALIDATED_STATISTICAL')),
 model_version VARCHAR(40) NOT NULL DEFAULT 'RETENTION_RULES_V1', data_quality VARCHAR(20) NOT NULL DEFAULT 'LIMITED',
 calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), calculated_by UUID REFERENCES users(id) ON DELETE SET NULL,
 superseded_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS retention_one_current_score ON employee_retention_risk_scores(employee_id) WHERE superseded_at IS NULL;
CREATE INDEX IF NOT EXISTS retention_risk_scope_idx ON employee_retention_risk_scores(org_id,property_id,department_id,risk_level) WHERE superseded_at IS NULL;

CREATE TABLE IF NOT EXISTS employee_retention_interventions (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 risk_score_id UUID NOT NULL REFERENCES employee_retention_risk_scores(id) ON DELETE CASCADE,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 action_type VARCHAR(40) NOT NULL, notes TEXT, status VARCHAR(20) NOT NULL DEFAULT 'PLANNED' CHECK(status IN ('PLANNED','IN_PROGRESS','COMPLETED','DISMISSED')),
 owner_id UUID REFERENCES users(id) ON DELETE SET NULL, due_at TIMESTAMPTZ, completed_at TIMESTAMPTZ,
 created_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE employee_turnover_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_pulse_surveys ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_pulse_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_retention_risk_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_retention_interventions ENABLE ROW LEVEL SECURITY;

CREATE POLICY turnover_read ON employee_turnover_history FOR SELECT USING(org_id=current_user_org_id() AND rbac_has_permission('employees.read') AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id));
CREATE POLICY turnover_manage ON employee_turnover_history FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('employees.manage')) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('employees.manage'));
CREATE POLICY pulse_survey_read ON employee_pulse_surveys FOR SELECT USING(org_id=current_user_org_id() AND (status='ACTIVE' OR rbac_has_permission('employees.read')) AND (property_id IS NULL OR has_property_access(property_id)));
CREATE POLICY pulse_survey_manage ON employee_pulse_surveys FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('employees.manage')) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('employees.manage'));
CREATE POLICY pulse_response_self_insert ON employee_pulse_responses FOR INSERT WITH CHECK(org_id=current_user_org_id() AND (employee_id=auth.uid() OR employee_id IS NULL));
CREATE POLICY pulse_response_manager_read ON employee_pulse_responses FOR SELECT USING(org_id=current_user_org_id() AND rbac_has_permission('employees.read'));
CREATE POLICY retention_risk_read ON employee_retention_risk_scores FOR SELECT USING(org_id=current_user_org_id() AND rbac_has_permission('employees.read') AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id));
CREATE POLICY retention_risk_manage ON employee_retention_risk_scores FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('employees.manage')) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('employees.manage'));
CREATE POLICY retention_intervention_access ON employee_retention_interventions FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('employees.read')) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('employees.manage'));

COMMIT;
