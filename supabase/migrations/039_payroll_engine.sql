-- Configurable India payroll engine. Existing payslips remain canonical outputs.
BEGIN;
CREATE TABLE IF NOT EXISTS payroll_rules (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 property_id UUID REFERENCES properties(id) ON DELETE CASCADE,name VARCHAR(120) NOT NULL,effective_from DATE NOT NULL,effective_to DATE,
 basic_pct NUMERIC(6,4) NOT NULL DEFAULT .50,hra_pct_of_basic NUMERIC(6,4) NOT NULL DEFAULT .50,
 epf_employee_pct NUMERIC(6,4) NOT NULL DEFAULT .12,epf_employer_pct NUMERIC(6,4) NOT NULL DEFAULT .12,
 epf_wage_cap_inr NUMERIC(12,2) NOT NULL DEFAULT 15000,epf_cap_enabled BOOLEAN NOT NULL DEFAULT TRUE,
 esic_employee_pct NUMERIC(6,4) NOT NULL DEFAULT .0075,esic_employer_pct NUMERIC(6,4) NOT NULL DEFAULT .0325,
 esic_wage_limit_inr NUMERIC(12,2) NOT NULL DEFAULT 21000,overtime_multiplier NUMERIC(5,2) NOT NULL DEFAULT 2,
 rounding_mode VARCHAR(20) NOT NULL DEFAULT 'HALF_UP',settings JSONB NOT NULL DEFAULT '{}',created_by UUID REFERENCES users(id),created_at TIMESTAMPTZ DEFAULT NOW(),
 CHECK(effective_to IS NULL OR effective_to>=effective_from),UNIQUE(org_id,property_id,name,effective_from)
);
CREATE TABLE IF NOT EXISTS employee_compensation_structures (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
 effective_from DATE NOT NULL,effective_to DATE,annual_ctc_inr NUMERIC(14,2),monthly_gross_inr NUMERIC(12,2) NOT NULL,
 basic_inr NUMERIC(12,2),hra_inr NUMERIC(12,2),allowances JSONB NOT NULL DEFAULT '{}',state_code VARCHAR(3) NOT NULL,
 joining_date DATE,epf_applicable BOOLEAN DEFAULT TRUE,esic_applicable BOOLEAN DEFAULT TRUE,tds_monthly_inr NUMERIC(12,2) DEFAULT 0,
 created_by UUID REFERENCES users(id),created_at TIMESTAMPTZ DEFAULT NOW(),CHECK(effective_to IS NULL OR effective_to>=effective_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS compensation_active_unique ON employee_compensation_structures(employee_id,effective_from);
CREATE TABLE IF NOT EXISTS payroll_runs (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,period_year SMALLINT NOT NULL,period_month SMALLINT NOT NULL CHECK(period_month BETWEEN 1 AND 12),
 status VARCHAR(24) NOT NULL DEFAULT 'DRAFT' CHECK(status IN('DRAFT','CALCULATED','PENDING_APPROVAL','APPROVED','FINALIZED','REJECTED','CANCELLED')),
 rule_id UUID REFERENCES payroll_rules(id),created_by UUID NOT NULL REFERENCES users(id),submitted_by UUID REFERENCES users(id),submitted_at TIMESTAMPTZ,
 approved_by UUID REFERENCES users(id),approved_at TIMESTAMPTZ,finalized_by UUID REFERENCES users(id),finalized_at TIMESTAMPTZ,
 totals JSONB NOT NULL DEFAULT '{}',version INT NOT NULL DEFAULT 1,created_at TIMESTAMPTZ DEFAULT NOW(),updated_at TIMESTAMPTZ DEFAULT NOW(),
 UNIQUE(org_id,property_id,period_year,period_month,version)
);
CREATE TABLE IF NOT EXISTS payroll_adjustments (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 payroll_run_id UUID NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,employee_id UUID NOT NULL REFERENCES users(id),
 adjustment_type VARCHAR(20) NOT NULL CHECK(adjustment_type IN('BONUS','INCENTIVE','ARREAR','DEDUCTION','REIMBURSEMENT')),
 amount_inr NUMERIC(12,2) NOT NULL,narration TEXT NOT NULL,created_by UUID REFERENCES users(id),created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS payroll_run_items (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 payroll_run_id UUID NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,employee_id UUID NOT NULL REFERENCES users(id),
 compensation_structure_id UUID REFERENCES employee_compensation_structures(id),attendance_snapshot JSONB NOT NULL,rule_snapshot JSONB NOT NULL,
 calculation_snapshot JSONB NOT NULL,snapshot_hash VARCHAR(64) NOT NULL,gross_inr NUMERIC(12,2) NOT NULL,net_inr NUMERIC(12,2) NOT NULL,
 employer_cost_inr NUMERIC(12,2) NOT NULL,lop_inr NUMERIC(12,2) DEFAULT 0,overtime_inr NUMERIC(12,2) DEFAULT 0,
 bonus_inr NUMERIC(12,2) DEFAULT 0,incentive_inr NUMERIC(12,2) DEFAULT 0,arrears_inr NUMERIC(12,2) DEFAULT 0,
 status VARCHAR(20) NOT NULL DEFAULT 'CALCULATED',created_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(payroll_run_id,employee_id)
);
CREATE TABLE IF NOT EXISTS payroll_approval_logs (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,payroll_run_id UUID NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
 actor_id UUID NOT NULL REFERENCES users(id),action VARCHAR(30) NOT NULL,note TEXT,before_status VARCHAR(24),after_status VARCHAR(24),created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS payroll_statutory_exports (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,payroll_run_id UUID NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
 export_type VARCHAR(24) NOT NULL CHECK(export_type IN('EPF_ECR','ESIC','FORM16_DATA')),file_url TEXT,checksum VARCHAR(64),status VARCHAR(20) DEFAULT 'GENERATED',
 generated_by UUID REFERENCES users(id),generated_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(payroll_run_id,export_type)
);
ALTER TABLE payslips ADD COLUMN IF NOT EXISTS payroll_run_item_id UUID REFERENCES payroll_run_items(id) ON DELETE RESTRICT,
 ADD COLUMN IF NOT EXISTS annual_ctc_inr NUMERIC(14,2),ADD COLUMN IF NOT EXISTS lop_inr NUMERIC(12,2) DEFAULT 0,
 ADD COLUMN IF NOT EXISTS incentives_inr NUMERIC(12,2) DEFAULT 0,ADD COLUMN IF NOT EXISTS arrears_inr NUMERIC(12,2) DEFAULT 0,
 ADD COLUMN IF NOT EXISTS snapshot_hash VARCHAR(64),ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'FINALIZED';

CREATE OR REPLACE FUNCTION prevent_finalized_payroll_mutation() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Finalized payroll snapshots are immutable'; END $$;
DROP TRIGGER IF EXISTS immutable_payroll_item ON payroll_run_items;
CREATE TRIGGER immutable_payroll_item BEFORE UPDATE OR DELETE ON payroll_run_items FOR EACH ROW
 WHEN (OLD.status='FINALIZED') EXECUTE FUNCTION prevent_finalized_payroll_mutation();
DROP TRIGGER IF EXISTS immutable_payslip ON payslips;
CREATE TRIGGER immutable_payslip BEFORE UPDATE OR DELETE ON payslips FOR EACH ROW
 WHEN (OLD.status='FINALIZED') EXECUTE FUNCTION prevent_finalized_payroll_mutation();

ALTER TABLE payroll_rules ENABLE ROW LEVEL SECURITY;ALTER TABLE employee_compensation_structures ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_runs ENABLE ROW LEVEL SECURITY;ALTER TABLE payroll_adjustments ENABLE ROW LEVEL SECURITY;ALTER TABLE payroll_run_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_approval_logs ENABLE ROW LEVEL SECURITY;ALTER TABLE payroll_statutory_exports ENABLE ROW LEVEL SECURITY;
DO $$ DECLARE t TEXT; BEGIN FOREACH t IN ARRAY ARRAY['payroll_rules','employee_compensation_structures','payroll_runs','payroll_adjustments','payroll_run_items','payroll_approval_logs','payroll_statutory_exports'] LOOP
 EXECUTE format('DROP POLICY IF EXISTS %I_read ON %I',t,t);EXECUTE format('DROP POLICY IF EXISTS %I_manage ON %I',t,t);
 EXECUTE format('CREATE POLICY %I_read ON %I FOR SELECT USING (org_id=current_user_org_id() AND current_user_role() NOT IN (''EMPLOYEE'',''CANDIDATE'') AND rbac_has_permission(''payroll.read''))',t,t);
 EXECUTE format('CREATE POLICY %I_manage ON %I FOR ALL USING (org_id=current_user_org_id() AND rbac_has_permission(''payroll.manage'')) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission(''payroll.manage''))',t,t);
 END LOOP;END $$;
DROP POLICY IF EXISTS compensation_self_read ON employee_compensation_structures;
CREATE POLICY compensation_self_read ON employee_compensation_structures FOR SELECT USING(employee_id=auth.uid() AND org_id=current_user_org_id());
DROP POLICY IF EXISTS payroll_item_self_read ON payroll_run_items;
CREATE POLICY payroll_item_self_read ON payroll_run_items FOR SELECT USING(employee_id=auth.uid() AND org_id=current_user_org_id() AND status='FINALIZED');
COMMIT;
