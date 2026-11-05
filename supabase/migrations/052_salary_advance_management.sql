-- Production salary-advance workflow layered onto the existing canonical request table.
BEGIN;

CREATE TABLE IF NOT EXISTS salary_advance_policies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  property_id UUID REFERENCES properties(id) ON DELETE CASCADE, is_active BOOLEAN NOT NULL DEFAULT TRUE,
  minimum_tenure_days INT NOT NULL DEFAULT 90 CHECK (minimum_tenure_days >= 0),
  maximum_advance_pct NUMERIC(5,2) NOT NULL DEFAULT 50 CHECK (maximum_advance_pct > 0 AND maximum_advance_pct <= 100),
  maximum_amount_inr NUMERIC(12,2) NOT NULL DEFAULT 50000 CHECK (maximum_amount_inr > 0),
  maximum_repayment_months SMALLINT NOT NULL DEFAULT 6 CHECK (maximum_repayment_months BETWEEN 1 AND 24),
  require_manager_approval BOOLEAN NOT NULL DEFAULT TRUE, require_payroll_approval BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID REFERENCES users(id), updated_by UUID REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(org_id, property_id)
);

ALTER TABLE employee_salary_advance_requests
 ADD COLUMN IF NOT EXISTS approved_amount_inr NUMERIC(12,2),
 ADD COLUMN IF NOT EXISTS approved_repayment_months SMALLINT,
 ADD COLUMN IF NOT EXISTS disbursed_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS disbursed_by UUID REFERENCES users(id) ON DELETE SET NULL,
 ADD COLUMN IF NOT EXISTS disbursement_reference TEXT,
 ADD COLUMN IF NOT EXISTS outstanding_balance_inr NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (outstanding_balance_inr >= 0),
 ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;

DO $$ DECLARE c RECORD; BEGIN
 FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='employee_salary_advance_requests'::regclass AND contype='c' AND pg_get_constraintdef(oid) ILIKE '%status%' LOOP
  EXECUTE format('ALTER TABLE employee_salary_advance_requests DROP CONSTRAINT %I', c.conname);
 END LOOP;
END $$;
ALTER TABLE employee_salary_advance_requests ADD CONSTRAINT salary_advance_status_check
 CHECK (status IN ('PENDING','APPROVED','REJECTED','DISBURSED','REPAYING','REPAID','CANCELLED'));
DROP INDEX IF EXISTS employee_one_active_salary_advance;
CREATE UNIQUE INDEX employee_one_active_salary_advance ON employee_salary_advance_requests(employee_id)
 WHERE status IN ('PENDING','APPROVED','DISBURSED','REPAYING');

CREATE TABLE IF NOT EXISTS salary_advance_repayments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  advance_id UUID NOT NULL REFERENCES employee_salary_advance_requests(id) ON DELETE RESTRICT,
  employee_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT, installment_number SMALLINT NOT NULL,
  due_year SMALLINT NOT NULL, due_month SMALLINT NOT NULL CHECK (due_month BETWEEN 1 AND 12),
  amount_inr NUMERIC(12,2) NOT NULL CHECK (amount_inr > 0), status VARCHAR(20) NOT NULL DEFAULT 'SCHEDULED'
   CHECK (status IN ('SCHEDULED','IN_PAYROLL','DEDUCTED','WAIVED','FAILED')),
  payroll_run_id UUID REFERENCES payroll_runs(id) ON DELETE SET NULL,
  payroll_adjustment_id UUID REFERENCES payroll_adjustments(id) ON DELETE SET NULL,
  deducted_at TIMESTAMPTZ, waived_by UUID REFERENCES users(id), waiver_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(advance_id, installment_number), UNIQUE(advance_id, due_year, due_month)
);
ALTER TABLE payroll_adjustments ADD COLUMN IF NOT EXISTS salary_advance_repayment_id UUID REFERENCES salary_advance_repayments(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX IF NOT EXISTS one_payroll_adjustment_per_advance_installment ON payroll_adjustments(salary_advance_repayment_id) WHERE salary_advance_repayment_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS salary_advance_audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  advance_id UUID NOT NULL REFERENCES employee_salary_advance_requests(id) ON DELETE RESTRICT,
  actor_id UUID REFERENCES users(id) ON DELETE SET NULL, action VARCHAR(40) NOT NULL,
  before_status VARCHAR(24), after_status VARCHAR(24), amount_inr NUMERIC(12,2), metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE OR REPLACE FUNCTION prevent_salary_advance_audit_mutation() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Salary advance audit records are immutable'; END $$;
DROP TRIGGER IF EXISTS immutable_salary_advance_audit ON salary_advance_audit_logs;
CREATE TRIGGER immutable_salary_advance_audit BEFORE UPDATE OR DELETE ON salary_advance_audit_logs FOR EACH ROW EXECUTE FUNCTION prevent_salary_advance_audit_mutation();

ALTER TABLE salary_advance_policies ENABLE ROW LEVEL SECURITY; ALTER TABLE salary_advance_repayments ENABLE ROW LEVEL SECURITY; ALTER TABLE salary_advance_audit_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS salary_advance_self_cancel ON employee_salary_advance_requests;
DROP POLICY IF EXISTS salary_advance_policy_read ON salary_advance_policies; DROP POLICY IF EXISTS salary_advance_policy_manage ON salary_advance_policies;
CREATE POLICY salary_advance_policy_read ON salary_advance_policies FOR SELECT USING (org_id=current_user_org_id());
CREATE POLICY salary_advance_policy_manage ON salary_advance_policies FOR ALL USING (org_id=current_user_org_id() AND rbac_has_permission('payroll.manage')) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('payroll.manage'));
CREATE POLICY salary_repayment_self_read ON salary_advance_repayments FOR SELECT USING (employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_has_permission('payroll.read')));
CREATE POLICY salary_repayment_manage ON salary_advance_repayments FOR ALL USING (org_id=current_user_org_id() AND rbac_has_permission('payroll.manage')) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('payroll.manage'));
CREATE POLICY salary_advance_audit_read ON salary_advance_audit_logs FOR SELECT USING (org_id=current_user_org_id() AND (rbac_has_permission('payroll.read') OR EXISTS (SELECT 1 FROM employee_salary_advance_requests a WHERE a.id=advance_id AND a.employee_id=auth.uid())));
CREATE POLICY salary_advance_audit_insert ON salary_advance_audit_logs FOR INSERT WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('payroll.manage'));
COMMIT;
