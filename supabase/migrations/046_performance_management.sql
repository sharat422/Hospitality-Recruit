-- Configurable hospitality performance management, extending Employee 360 reviews.
BEGIN;

-- Extend the canonical RBAC function with narrow performance permissions.
CREATE OR REPLACE FUNCTION rbac_has_permission(permission TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public AS $$
DECLARE r TEXT := current_user_role();
BEGIN
 IF r = 'OWNER' THEN RETURN TRUE; END IF;
 IF r = 'GROUP_ADMIN_HR' THEN RETURN permission <> 'financial.manage'; END IF;
 IF r = 'GENERAL_MANAGER' THEN RETURN permission = ANY(ARRAY['candidates.read','employees.read','employees.manage','jobs.read','jobs.manage','applications.read','applications.manage','payroll.read','attendance.read','attendance.manage','leave.read','leave.manage','compliance.read','documents.read','documents.manage','reports.read','reports.financial','complaints.create','complaints.read','complaints.manage','properties.read','financial.read','performance.read','performance.manage']); END IF;
 IF r = 'HR_MANAGER' THEN RETURN permission = ANY(ARRAY['candidates.read','candidates.manage','employees.read','employees.manage','jobs.read','jobs.manage','applications.read','applications.manage','payroll.read','attendance.read','leave.read','leave.manage','compliance.read','compliance.manage','documents.read','documents.manage','reports.read','complaints.create','complaints.read','complaints.manage','properties.read','performance.read','performance.manage']); END IF;
 IF r = 'DEPARTMENT_HEAD' THEN RETURN permission = ANY(ARRAY['candidates.read','employees.read','jobs.read','applications.read','applications.manage','attendance.read','attendance.manage','leave.read','leave.manage','documents.read','reports.read','complaints.create','properties.read','performance.read','performance.manage']); END IF;
 IF r = 'RECRUITER' THEN RETURN permission = ANY(ARRAY['candidates.read','candidates.manage','jobs.read','jobs.manage','applications.read','applications.manage','documents.read','documents.manage','reports.read','complaints.create','properties.read']); END IF;
 IF r = 'EMPLOYEE' THEN RETURN permission = ANY(ARRAY['payroll.read','attendance.read','leave.read','complaints.create','documents.read','properties.read','performance.read']); END IF;
 RETURN permission = ANY(ARRAY['applications.read','documents.read']);
END $$;

CREATE TABLE IF NOT EXISTS performance_appraisal_cycles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID REFERENCES properties(id) ON DELETE CASCADE,
    name VARCHAR(180) NOT NULL,
    review_period_start DATE NOT NULL,
    review_period_end DATE NOT NULL,
    self_review_due_at TIMESTAMPTZ,
    peer_review_due_at TIMESTAMPTZ,
    manager_review_due_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
      CHECK (status IN ('DRAFT','ACTIVE','CALIBRATION','CLOSED','CANCELLED')),
    promotion_threshold NUMERIC(5,2) NOT NULL DEFAULT 80 CHECK (promotion_threshold BETWEEN 0 AND 100),
    increment_threshold NUMERIC(5,2) NOT NULL DEFAULT 70 CHECK (increment_threshold BETWEEN 0 AND 100),
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (review_period_end >= review_period_start)
);

CREATE TABLE IF NOT EXISTS performance_kpi_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    department_name VARCHAR(120) NOT NULL,
    role_title VARCHAR(180),
    metric_key VARCHAR(100) NOT NULL,
    name VARCHAR(180) NOT NULL,
    description TEXT,
    unit VARCHAR(30) NOT NULL DEFAULT 'SCORE',
    direction VARCHAR(15) NOT NULL DEFAULT 'HIGHER_BETTER'
      CHECK (direction IN ('HIGHER_BETTER','LOWER_BETTER','TARGET')),
    target_value NUMERIC(12,2),
    min_value NUMERIC(12,2),
    max_value NUMERIC(12,2),
    default_weight NUMERIC(5,2) NOT NULL DEFAULT 25 CHECK (default_weight > 0 AND default_weight <= 100),
    source VARCHAR(30) NOT NULL DEFAULT 'MANAGER'
      CHECK (source IN ('MANAGER','SYSTEM','GUEST_FEEDBACK','OPERATIONS')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (org_id,department_name,role_title,metric_key)
);

CREATE TABLE IF NOT EXISTS performance_cycle_kpis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cycle_id UUID NOT NULL REFERENCES performance_appraisal_cycles(id) ON DELETE CASCADE,
    template_id UUID REFERENCES performance_kpi_templates(id) ON DELETE SET NULL,
    department_id UUID REFERENCES property_departments(id) ON DELETE CASCADE,
    role_title VARCHAR(180),
    name VARCHAR(180) NOT NULL,
    description TEXT,
    unit VARCHAR(30) NOT NULL DEFAULT 'SCORE',
    direction VARCHAR(15) NOT NULL,
    target_value NUMERIC(12,2),
    min_value NUMERIC(12,2),
    max_value NUMERIC(12,2),
    weight NUMERIC(5,2) NOT NULL CHECK (weight > 0 AND weight <= 100),
    source VARCHAR(30) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE employee_performance_reviews
    ADD COLUMN IF NOT EXISTS cycle_id UUID REFERENCES performance_appraisal_cycles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS role_title_snapshot VARCHAR(180),
    ADD COLUMN IF NOT EXISTS self_review JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS self_submitted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS manager_submitted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS overall_score NUMERIC(5,2) CHECK (overall_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS promotion_eligible BOOLEAN,
    ADD COLUMN IF NOT EXISTS increment_eligible BOOLEAN,
    ADD COLUMN IF NOT EXISTS outcome_status VARCHAR(20) NOT NULL DEFAULT 'NOT_REVIEWED'
      CHECK (outcome_status IN ('NOT_REVIEWED','RECOMMENDED','APPROVED','REJECTED'));

CREATE UNIQUE INDEX IF NOT EXISTS performance_cycle_employee_unique
 ON employee_performance_reviews(cycle_id,employee_id) WHERE cycle_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS performance_review_contributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    review_id UUID NOT NULL REFERENCES employee_performance_reviews(id) ON DELETE CASCADE,
    reviewer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reviewer_type VARCHAR(15) NOT NULL CHECK (reviewer_type IN ('SELF','MANAGER','PEER')),
    comments TEXT,
    strengths TEXT,
    development_areas TEXT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(review_id,reviewer_id,reviewer_type)
);

CREATE TABLE IF NOT EXISTS performance_peer_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    review_id UUID NOT NULL REFERENCES employee_performance_reviews(id) ON DELETE CASCADE,
    reviewer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status VARCHAR(15) NOT NULL DEFAULT 'ASSIGNED' CHECK (status IN ('ASSIGNED','COMPLETED','DECLINED')),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    UNIQUE(review_id,reviewer_id)
);

CREATE TABLE IF NOT EXISTS performance_kpi_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    review_id UUID NOT NULL REFERENCES employee_performance_reviews(id) ON DELETE CASCADE,
    cycle_kpi_id UUID NOT NULL REFERENCES performance_cycle_kpis(id) ON DELETE CASCADE,
    reviewer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reviewer_type VARCHAR(15) NOT NULL CHECK (reviewer_type IN ('SELF','MANAGER','PEER','SYSTEM')),
    actual_value NUMERIC(12,2),
    normalized_score NUMERIC(5,2) NOT NULL CHECK (normalized_score BETWEEN 0 AND 100),
    evidence TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(review_id,cycle_kpi_id,reviewer_id,reviewer_type)
);

CREATE TABLE IF NOT EXISTS performance_guest_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    review_id UUID REFERENCES employee_performance_reviews(id) ON DELETE SET NULL,
    source VARCHAR(40) NOT NULL DEFAULT 'MANUAL',
    rating NUMERIC(3,2) NOT NULL CHECK (rating BETWEEN 1 AND 5),
    complaint_count INT NOT NULL DEFAULT 0 CHECK (complaint_count >= 0),
    compliment_count INT NOT NULL DEFAULT 0 CHECK (compliment_count >= 0),
    feedback_date DATE NOT NULL DEFAULT CURRENT_DATE,
    reference_id TEXT,
    notes TEXT,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS performance_outcome_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    review_id UUID NOT NULL UNIQUE REFERENCES employee_performance_reviews(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    increment_percent NUMERIC(5,2) CHECK (increment_percent BETWEEN 0 AND 100),
    promotion_role_title VARCHAR(180),
    recommendation_reason TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'RECOMMENDED'
      CHECK (status IN ('RECOMMENDED','APPROVED','REJECTED')),
    recommended_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO performance_kpi_templates
 (department_name,role_title,metric_key,name,description,unit,direction,target_value,min_value,max_value,default_weight,source)
VALUES
 ('Front Office',NULL,'checkin_efficiency','Check-in performance','Accuracy, speed and guest readiness at check-in','SCORE','HIGHER_BETTER',90,0,100,35,'OPERATIONS'),
 ('Front Office',NULL,'guest_complaints','Guest complaint rate','Validated guest complaints attributable to service','COUNT','LOWER_BETTER',0,0,10,30,'GUEST_FEEDBACK'),
 ('Front Office',NULL,'guest_rating','Guest service rating','Average attributable guest rating','RATING_5','HIGHER_BETTER',4.5,1,5,35,'GUEST_FEEDBACK'),
 ('Housekeeping',NULL,'room_quality','Room quality audit','Room inspection and cleanliness audit score','SCORE','HIGHER_BETTER',95,0,100,50,'OPERATIONS'),
 ('Housekeeping',NULL,'room_turnaround','Room turnaround performance','Rooms completed on time and to standard','SCORE','HIGHER_BETTER',90,0,100,30,'OPERATIONS'),
 ('Housekeeping',NULL,'guest_complaints','Room complaint rate','Validated cleanliness or room-readiness complaints','COUNT','LOWER_BETTER',0,0,10,20,'GUEST_FEEDBACK'),
 ('Kitchen',NULL,'food_cost','Food cost control','Food cost performance against approved target','PERCENT','TARGET',30,0,100,35,'OPERATIONS'),
 ('Kitchen',NULL,'food_waste','Food waste control','Waste percentage against production','PERCENT','LOWER_BETTER',3,0,25,35,'OPERATIONS'),
 ('Kitchen',NULL,'food_quality','Food quality audit','Recipe, presentation and safety audit score','SCORE','HIGHER_BETTER',90,0,100,30,'OPERATIONS'),
 ('F&B',NULL,'upsell_performance','Upsell performance','Upsell revenue or conversion against target','SCORE','HIGHER_BETTER',85,0,100,40,'OPERATIONS'),
 ('F&B',NULL,'guest_rating','Guest service rating','Average attributable dining guest rating','RATING_5','HIGHER_BETTER',4.5,1,5,35,'GUEST_FEEDBACK'),
 ('F&B',NULL,'order_accuracy','Order accuracy','Orders delivered accurately','PERCENT','HIGHER_BETTER',98,0,100,25,'OPERATIONS')
ON CONFLICT (org_id,department_name,role_title,metric_key) DO NOTHING;

CREATE INDEX IF NOT EXISTS appraisal_cycles_org_idx ON performance_appraisal_cycles(org_id,status,review_period_end);
CREATE INDEX IF NOT EXISTS review_contributions_review_idx ON performance_review_contributions(review_id,reviewer_type);
CREATE INDEX IF NOT EXISTS kpi_scores_review_idx ON performance_kpi_scores(review_id,reviewer_type);
CREATE INDEX IF NOT EXISTS guest_feedback_employee_idx ON performance_guest_feedback(employee_id,feedback_date DESC);

ALTER TABLE performance_appraisal_cycles ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_kpi_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_cycle_kpis ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_review_contributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_peer_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_kpi_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_guest_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_outcome_recommendations ENABLE ROW LEVEL SECURITY;

CREATE POLICY appraisal_cycles_read ON performance_appraisal_cycles FOR SELECT USING
 (org_id=current_user_org_id() AND rbac_has_permission('performance.read') AND (property_id IS NULL OR has_property_access(property_id)));
CREATE POLICY appraisal_cycles_manage ON performance_appraisal_cycles FOR ALL USING
 (org_id=current_user_org_id() AND rbac_has_permission('performance.manage') AND (property_id IS NULL OR has_property_access(property_id)))
 WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('performance.manage') AND (property_id IS NULL OR has_property_access(property_id)));
CREATE POLICY kpi_templates_read ON performance_kpi_templates FOR SELECT USING
 (org_id IS NULL OR (org_id=current_user_org_id() AND rbac_has_permission('performance.read')));
CREATE POLICY kpi_templates_manage ON performance_kpi_templates FOR ALL USING
 (org_id=current_user_org_id() AND rbac_has_permission('performance.manage'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('performance.manage'));
CREATE POLICY cycle_kpis_read ON performance_cycle_kpis FOR SELECT USING
 (EXISTS (SELECT 1 FROM performance_appraisal_cycles c WHERE c.id=cycle_id AND c.org_id=current_user_org_id()
  AND rbac_has_permission('performance.read')));
CREATE POLICY cycle_kpis_manage ON performance_cycle_kpis FOR ALL USING
 (EXISTS (SELECT 1 FROM performance_appraisal_cycles c WHERE c.id=cycle_id AND c.org_id=current_user_org_id()
  AND rbac_has_permission('performance.manage')))
 WITH CHECK (EXISTS (SELECT 1 FROM performance_appraisal_cycles c WHERE c.id=cycle_id AND c.org_id=current_user_org_id()
  AND rbac_has_permission('performance.manage')));
CREATE POLICY contributions_read ON performance_review_contributions FOR SELECT USING
 (reviewer_id=auth.uid() OR EXISTS (SELECT 1 FROM employee_performance_reviews r WHERE r.id=review_id
  AND (r.employee_id=auth.uid() OR (r.org_id=current_user_org_id() AND rbac_has_permission('performance.manage')))));
CREATE POLICY peer_assignments_read ON performance_peer_assignments FOR SELECT USING
 (reviewer_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_has_permission('performance.manage')));
CREATE POLICY peer_assignments_manage ON performance_peer_assignments FOR ALL USING
 (org_id=current_user_org_id() AND rbac_has_permission('performance.manage'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('performance.manage'));
CREATE POLICY peer_assignments_self_update ON performance_peer_assignments FOR UPDATE USING
 (org_id=current_user_org_id() AND reviewer_id=auth.uid() AND status='ASSIGNED')
 WITH CHECK (org_id=current_user_org_id() AND reviewer_id=auth.uid() AND status IN ('COMPLETED','DECLINED'));
CREATE POLICY contributions_write ON performance_review_contributions FOR ALL USING
 (org_id=current_user_org_id() AND reviewer_id=auth.uid() AND EXISTS
  (SELECT 1 FROM employee_performance_reviews r WHERE r.id=review_id AND r.org_id=current_user_org_id()
   AND (r.employee_id=auth.uid() OR rbac_has_permission('performance.manage') OR EXISTS
    (SELECT 1 FROM performance_peer_assignments p WHERE p.review_id=r.id AND p.reviewer_id=auth.uid() AND p.status='ASSIGNED'))))
 WITH CHECK (org_id=current_user_org_id() AND reviewer_id=auth.uid() AND EXISTS
  (SELECT 1 FROM employee_performance_reviews r WHERE r.id=review_id AND r.org_id=current_user_org_id()
   AND (r.employee_id=auth.uid() OR rbac_has_permission('performance.manage') OR EXISTS
    (SELECT 1 FROM performance_peer_assignments p WHERE p.review_id=r.id AND p.reviewer_id=auth.uid() AND p.status='ASSIGNED'))));
CREATE POLICY kpi_scores_read ON performance_kpi_scores FOR SELECT USING
 (reviewer_id=auth.uid() OR EXISTS (SELECT 1 FROM employee_performance_reviews r WHERE r.id=review_id
  AND (r.employee_id=auth.uid() OR (r.org_id=current_user_org_id() AND rbac_has_permission('performance.manage')))));
CREATE POLICY kpi_scores_write ON performance_kpi_scores FOR ALL USING
 (org_id=current_user_org_id() AND (reviewer_id=auth.uid() OR rbac_has_permission('performance.manage'))
  AND EXISTS (SELECT 1 FROM employee_performance_reviews r WHERE r.id=review_id AND r.org_id=current_user_org_id()))
 WITH CHECK (org_id=current_user_org_id() AND (reviewer_id=auth.uid() OR rbac_has_permission('performance.manage'))
  AND EXISTS (SELECT 1 FROM employee_performance_reviews r WHERE r.id=review_id AND r.org_id=current_user_org_id()));
CREATE POLICY guest_feedback_read ON performance_guest_feedback FOR SELECT USING
 (org_id=current_user_org_id() AND (employee_id=auth.uid() OR rbac_has_permission('performance.manage')));
CREATE POLICY guest_feedback_manage ON performance_guest_feedback FOR ALL USING
 (org_id=current_user_org_id() AND rbac_has_permission('performance.manage'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('performance.manage'));
CREATE POLICY performance_outcomes_access ON performance_outcome_recommendations FOR ALL USING
 (org_id=current_user_org_id() AND rbac_has_permission('performance.manage'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('performance.manage'));

DROP POLICY IF EXISTS performance_self_read ON employee_performance_reviews;
DROP POLICY IF EXISTS performance_manage ON employee_performance_reviews;
CREATE POLICY performance_self_read ON employee_performance_reviews FOR SELECT USING (
 employee_id=auth.uid() OR EXISTS (SELECT 1 FROM performance_peer_assignments p
  WHERE p.review_id=employee_performance_reviews.id AND p.reviewer_id=auth.uid() AND p.status='ASSIGNED')
 OR (org_id=current_user_org_id() AND rbac_has_permission('performance.manage')
 AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id))
);
CREATE POLICY performance_manage ON employee_performance_reviews FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('performance.manage')
 AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id)
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('performance.manage')
 AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id));

COMMIT;
