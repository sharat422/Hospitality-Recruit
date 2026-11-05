-- Employee PWA additions. Existing shifts, leave, payroll and hr_complaints remain canonical.
BEGIN;

CREATE TABLE IF NOT EXISTS employee_salary_advance_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
  employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  amount_inr NUMERIC(12,2) NOT NULL CHECK (amount_inr > 0),
  reason TEXT NOT NULL CHECK (length(trim(reason)) >= 5),
  requested_repayment_months SMALLINT NOT NULL DEFAULT 1 CHECK (requested_repayment_months BETWEEN 1 AND 12),
  status VARCHAR(24) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','PAID','CANCELLED')),
  source VARCHAR(20) NOT NULL DEFAULT 'PWA' CHECK (source IN ('WEB','PWA','WHATSAPP','ADMIN')),
  reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
  reviewed_at TIMESTAMPTZ,
  review_note TEXT,
  paid_at TIMESTAMPTZ,
  payroll_adjustment_id UUID REFERENCES payroll_adjustments(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS employee_one_active_salary_advance
 ON employee_salary_advance_requests(employee_id) WHERE status IN ('PENDING','APPROVED');
CREATE INDEX IF NOT EXISTS salary_advance_scope_idx
 ON employee_salary_advance_requests(org_id,property_id,status,created_at DESC);

CREATE TABLE IF NOT EXISTS property_employee_support_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  accommodation_available BOOLEAN NOT NULL DEFAULT FALSE,
  accommodation_details TEXT,
  transport_available BOOLEAN NOT NULL DEFAULT FALSE,
  transport_details TEXT,
  transport_contact VARCHAR(30),
  benefits JSONB NOT NULL DEFAULT '[]',
  esic_clinic_name TEXT,
  esic_clinic_address TEXT,
  esic_clinic_phone VARCHAR(30),
  esic_clinic_maps_url TEXT,
  emergency_hr_phone VARCHAR(30),
  posh_ic_email VARCHAR(255),
  posh_ic_phone VARCHAR(30),
  updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(property_id)
);

ALTER TABLE hr_complaints
 ADD COLUMN IF NOT EXISTS property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
 ADD COLUMN IF NOT EXISTS complaint_type VARCHAR(20) NOT NULL DEFAULT 'GRIEVANCE';
DO $$ BEGIN
 ALTER TABLE hr_complaints ADD CONSTRAINT hr_complaint_type_check
 CHECK (complaint_type IN ('GRIEVANCE','POSH'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE employee_salary_advance_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE property_employee_support_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY salary_advance_self_read ON employee_salary_advance_requests FOR SELECT USING (
 employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_has_permission('payroll.read'))
);
CREATE POLICY salary_advance_self_create ON employee_salary_advance_requests FOR INSERT WITH CHECK (
 employee_id=auth.uid() AND org_id=current_user_org_id() AND source IN ('WEB','PWA')
);
CREATE POLICY salary_advance_self_cancel ON employee_salary_advance_requests FOR UPDATE USING (
 employee_id=auth.uid() AND status='PENDING'
) WITH CHECK (employee_id=auth.uid() AND status='CANCELLED');
CREATE POLICY salary_advance_manage ON employee_salary_advance_requests FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('payroll.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('payroll.manage'));

CREATE POLICY employee_support_read ON property_employee_support_profiles FOR SELECT USING (
 org_id=current_user_org_id() AND has_property_access(property_id)
);
CREATE POLICY employee_support_manage ON property_employee_support_profiles FOR ALL USING (
 org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('employees.manage')
) WITH CHECK (org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('employees.manage'));

-- Replace the permissive complaint policy with self/privileged access. Anonymous
-- reporters track with their random token through the existing public endpoint.
DROP POLICY IF EXISTS hc_policy ON hr_complaints;
DROP POLICY IF EXISTS hr_complaints_self ON hr_complaints;
DROP POLICY IF EXISTS hr_complaints_create ON hr_complaints;
DROP POLICY IF EXISTS hr_complaints_manage ON hr_complaints;
CREATE POLICY hr_complaints_self ON hr_complaints FOR SELECT USING (
 employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_has_permission('complaints.read'))
);
CREATE POLICY hr_complaints_create ON hr_complaints FOR INSERT WITH CHECK (
 org_id=current_user_org_id() AND source='APP' AND
 ((is_anonymous AND employee_id IS NULL) OR (NOT is_anonymous AND employee_id=auth.uid()))
);
CREATE POLICY hr_complaints_manage ON hr_complaints FOR UPDATE USING (
 org_id=current_user_org_id() AND rbac_has_permission('complaints.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('complaints.manage'));

COMMIT;
