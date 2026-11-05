-- Employee engagement channels, privacy-safe analytics and recognition.
BEGIN;

ALTER TABLE employee_pulse_surveys
 ADD COLUMN IF NOT EXISTS channels JSONB NOT NULL DEFAULT '["PWA","WHATSAPP"]',
 ADD COLUMN IF NOT EXISTS language_code VARCHAR(10) NOT NULL DEFAULT 'en',
 ADD COLUMN IF NOT EXISTS min_reporting_group SMALLINT NOT NULL DEFAULT 5 CHECK(min_reporting_group >= 3);
ALTER TABLE employee_pulse_responses
 ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'PWA' CHECK(source IN ('PWA','WHATSAPP','WEB','ADMIN')),
 ADD COLUMN IF NOT EXISTS property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
 ADD COLUMN IF NOT EXISTS department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS employee_pulse_participation (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 survey_id UUID NOT NULL REFERENCES employee_pulse_surveys(id) ON DELETE CASCADE,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 channel VARCHAR(20) NOT NULL CHECK(channel IN ('PWA','WHATSAPP','WEB','ADMIN')),
 participated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(survey_id,employee_id)
);

CREATE TABLE IF NOT EXISTS employee_recognitions (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 property_id UUID REFERENCES properties(id) ON DELETE SET NULL, department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, nominated_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 category VARCHAR(40) NOT NULL CHECK(category IN ('GUEST_DELIGHT','TEAMWORK','SERVICE_EXCELLENCE','INNOVATION','SAFETY','LEADERSHIP','VALUES','OTHER')),
 reason TEXT NOT NULL CHECK(length(trim(reason)) >= 10), recognition_points INT NOT NULL DEFAULT 1 CHECK(recognition_points BETWEEN 0 AND 100),
 status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','APPROVED','REJECTED')),
 is_public BOOLEAN NOT NULL DEFAULT TRUE, reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL, reviewed_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employee_of_month_awards (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE, department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, award_year SMALLINT NOT NULL,
 award_month SMALLINT NOT NULL CHECK(award_month BETWEEN 1 AND 12), citation TEXT NOT NULL,
 recognition_summary JSONB NOT NULL DEFAULT '{}', approved_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 awarded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(property_id,department_id,award_year,award_month)
);

CREATE TABLE IF NOT EXISTS employee_engagement_scores (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
 department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
 engagement_score NUMERIC(5,2) NOT NULL CHECK(engagement_score BETWEEN 0 AND 100),
 engagement_level VARCHAR(20) NOT NULL CHECK(engagement_level IN ('LOW','MODERATE','HIGH','VERY_HIGH')),
 score_components JSONB NOT NULL DEFAULT '{}', data_quality VARCHAR(20) NOT NULL DEFAULT 'LIMITED',
 model_type VARCHAR(20) NOT NULL DEFAULT 'RULES_BASED', model_version VARCHAR(40) NOT NULL DEFAULT 'ENGAGEMENT_RULES_V1',
 calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), calculated_by UUID REFERENCES users(id) ON DELETE SET NULL, superseded_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS engagement_one_current_score ON employee_engagement_scores(employee_id) WHERE superseded_at IS NULL;
CREATE INDEX IF NOT EXISTS engagement_scope_idx ON employee_engagement_scores(org_id,property_id,department_id,calculated_at DESC);

ALTER TABLE employee_pulse_participation ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_recognitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_of_month_awards ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_engagement_scores ENABLE ROW LEVEL SECURITY;

-- Managers never receive direct SELECT access to raw response content. Aggregation is server-only.
DROP POLICY IF EXISTS pulse_response_manager_read ON employee_pulse_responses;
DROP POLICY IF EXISTS pulse_response_self_insert ON employee_pulse_responses;
DROP POLICY IF EXISTS pulse_response_service_insert ON employee_pulse_responses;
DROP POLICY IF EXISTS participation_self_insert ON employee_pulse_participation;
DROP POLICY IF EXISTS participation_self_read ON employee_pulse_participation;
DROP POLICY IF EXISTS recognition_read ON employee_recognitions;
DROP POLICY IF EXISTS recognition_nominate ON employee_recognitions;
DROP POLICY IF EXISTS recognition_manage ON employee_recognitions;
DROP POLICY IF EXISTS eom_read ON employee_of_month_awards;
DROP POLICY IF EXISTS eom_manage ON employee_of_month_awards;
DROP POLICY IF EXISTS engagement_score_read ON employee_engagement_scores;
DROP POLICY IF EXISTS engagement_score_manage ON employee_engagement_scores;
CREATE POLICY pulse_response_service_insert ON employee_pulse_responses FOR INSERT WITH CHECK(org_id=current_user_org_id() AND (employee_id=auth.uid() OR employee_id IS NULL));
CREATE POLICY participation_self_insert ON employee_pulse_participation FOR INSERT WITH CHECK(org_id=current_user_org_id() AND employee_id=auth.uid());
CREATE POLICY participation_self_read ON employee_pulse_participation FOR SELECT USING(employee_id=auth.uid());
CREATE POLICY recognition_read ON employee_recognitions FOR SELECT USING(org_id=current_user_org_id() AND (employee_id=auth.uid() OR nominated_by=auth.uid() OR (is_public AND status='APPROVED') OR rbac_has_permission('employees.read')));
CREATE POLICY recognition_nominate ON employee_recognitions FOR INSERT WITH CHECK(org_id=current_user_org_id() AND nominated_by=auth.uid());
CREATE POLICY recognition_manage ON employee_recognitions FOR UPDATE USING(org_id=current_user_org_id() AND rbac_has_permission('employees.manage')) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('employees.manage'));
CREATE POLICY eom_read ON employee_of_month_awards FOR SELECT USING(org_id=current_user_org_id());
CREATE POLICY eom_manage ON employee_of_month_awards FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('employees.manage')) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('employees.manage'));
CREATE POLICY engagement_score_read ON employee_engagement_scores FOR SELECT USING(org_id=current_user_org_id() AND rbac_has_permission('employees.read') AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id));
CREATE POLICY engagement_score_manage ON employee_engagement_scores FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('employees.manage')) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('employees.manage'));

COMMIT;
