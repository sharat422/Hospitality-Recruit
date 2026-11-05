-- India employee exit, settlement and alumni management. Additive to Employee 360.
BEGIN;

CREATE TABLE IF NOT EXISTS employee_exit_cases (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT, property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
 department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL, manager_id UUID REFERENCES users(id) ON DELETE SET NULL,
 exit_type VARCHAR(24) NOT NULL DEFAULT 'RESIGNATION' CHECK(exit_type IN ('RESIGNATION','TERMINATION','RETIREMENT','ABSCONDING','CONTRACT_END')),
 status VARCHAR(30) NOT NULL DEFAULT 'SUBMITTED' CHECK(status IN ('DRAFT','SUBMITTED','ACKNOWLEDGED','NOTICE_PERIOD','CLEARANCE','SETTLEMENT_PENDING','COMPLETED','CANCELLED','REJECTED')),
 resignation_date DATE NOT NULL DEFAULT CURRENT_DATE, requested_last_working_date DATE NOT NULL,
 approved_last_working_date DATE, notice_period_days INT NOT NULL DEFAULT 30 CHECK(notice_period_days BETWEEN 0 AND 365),
 notice_days_served INT CHECK(notice_days_served BETWEEN 0 AND 365), notice_waiver_days INT NOT NULL DEFAULT 0 CHECK(notice_waiver_days BETWEEN 0 AND 365),
 primary_reason VARCHAR(50) NOT NULL, reason_details TEXT, destination_company VARCHAR(180), destination_role VARCHAR(180),
 voluntary BOOLEAN NOT NULL DEFAULT TRUE, rehire_eligible BOOLEAN, rehire_notes TEXT,
 submitted_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT, acknowledged_by UUID REFERENCES users(id) ON DELETE SET NULL,
 acknowledged_at TIMESTAMPTZ, completed_by UUID REFERENCES users(id) ON DELETE SET NULL, completed_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 CHECK(requested_last_working_date >= resignation_date), CHECK(approved_last_working_date IS NULL OR approved_last_working_date >= resignation_date)
);
CREATE UNIQUE INDEX IF NOT EXISTS exit_one_open_case ON employee_exit_cases(employee_id) WHERE status NOT IN ('COMPLETED','CANCELLED','REJECTED');
CREATE INDEX IF NOT EXISTS exit_scope_idx ON employee_exit_cases(org_id,property_id,department_id,status);

CREATE TABLE IF NOT EXISTS employee_exit_interviews (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 exit_case_id UUID NOT NULL UNIQUE REFERENCES employee_exit_cases(id) ON DELETE CASCADE, employee_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 interview_date DATE, interviewer_id UUID REFERENCES users(id) ON DELETE SET NULL, overall_experience SMALLINT CHECK(overall_experience BETWEEN 1 AND 5),
 manager_relationship SMALLINT CHECK(manager_relationship BETWEEN 1 AND 5), work_environment SMALLINT CHECK(work_environment BETWEEN 1 AND 5),
 compensation_satisfaction SMALLINT CHECK(compensation_satisfaction BETWEEN 1 AND 5), growth_opportunities SMALLINT CHECK(growth_opportunities BETWEEN 1 AND 5),
 reason_for_leaving TEXT, what_went_well TEXT, improvements TEXT, would_recommend BOOLEAN, consent_to_contact BOOLEAN NOT NULL DEFAULT FALSE,
 status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','SUBMITTED','COMPLETED','DECLINED')),
 submitted_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employee_exit_clearance_items (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 exit_case_id UUID NOT NULL REFERENCES employee_exit_cases(id) ON DELETE CASCADE, employee_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 clearance_type VARCHAR(30) NOT NULL CHECK(clearance_type IN ('DEPARTMENT','IT','FINANCE','PAYROLL','ACCOMMODATION','TRANSPORT','SECURITY','DOCUMENTS','UNIFORM','OTHER')),
 label VARCHAR(180) NOT NULL, owner_id UUID REFERENCES users(id) ON DELETE SET NULL,
 status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','CLEARED','NOT_APPLICABLE','BLOCKED')),
 amount_due_inr NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK(amount_due_inr >= 0), notes TEXT, cleared_by UUID REFERENCES users(id) ON DELETE SET NULL,
 cleared_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(exit_case_id,clearance_type,label)
);

CREATE TABLE IF NOT EXISTS employee_final_settlements (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 exit_case_id UUID NOT NULL UNIQUE REFERENCES employee_exit_cases(id) ON DELETE RESTRICT, employee_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 property_id UUID REFERENCES properties(id) ON DELETE SET NULL, status VARCHAR(24) NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','CALCULATED','PENDING_APPROVAL','APPROVED','PAID','CANCELLED')),
 settlement_snapshot JSONB NOT NULL DEFAULT '{}', gross_payable_inr NUMERIC(14,2) NOT NULL DEFAULT 0,
 total_deductions_inr NUMERIC(14,2) NOT NULL DEFAULT 0, net_payable_inr NUMERIC(14,2) NOT NULL DEFAULT 0,
 payment_reference VARCHAR(120), calculated_by UUID REFERENCES users(id) ON DELETE SET NULL, calculated_at TIMESTAMPTZ,
 approved_by UUID REFERENCES users(id) ON DELETE SET NULL, approved_at TIMESTAMPTZ, paid_by UUID REFERENCES users(id) ON DELETE SET NULL, paid_at TIMESTAMPTZ,
 snapshot_hash VARCHAR(64), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employee_exit_documents (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 exit_case_id UUID NOT NULL REFERENCES employee_exit_cases(id) ON DELETE CASCADE, employee_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 document_type VARCHAR(30) NOT NULL CHECK(document_type IN ('EXPERIENCE_LETTER','RELIEVING_LETTER','SETTLEMENT_STATEMENT','SERVICE_CERTIFICATE')),
 document_html TEXT, storage_key TEXT, document_hash VARCHAR(64) NOT NULL, generated_by UUID REFERENCES users(id) ON DELETE SET NULL,
 generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(exit_case_id,document_type)
);

CREATE TABLE IF NOT EXISTS employee_alumni_profiles (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 employee_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE RESTRICT, last_property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
 last_department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL, last_job_title VARCHAR(180), joining_date DATE, exit_date DATE NOT NULL,
 exit_reason VARCHAR(50), rehire_eligible BOOLEAN, rehire_notes TEXT, alumni_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK(alumni_status IN ('ACTIVE','DO_NOT_CONTACT','REHIRED')),
 consent_to_contact BOOLEAN NOT NULL DEFAULT FALSE, skills_snapshot JSONB NOT NULL DEFAULT '[]', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION prevent_paid_settlement_mutation() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Paid final settlement snapshots are immutable'; END $$;
DROP TRIGGER IF EXISTS immutable_paid_final_settlement ON employee_final_settlements;
CREATE TRIGGER immutable_paid_final_settlement BEFORE UPDATE OR DELETE ON employee_final_settlements FOR EACH ROW WHEN (OLD.status='PAID') EXECUTE FUNCTION prevent_paid_settlement_mutation();

DO $$ DECLARE t TEXT; BEGIN FOREACH t IN ARRAY ARRAY['employee_exit_cases','employee_exit_interviews','employee_exit_clearance_items','employee_final_settlements','employee_exit_documents','employee_alumni_profiles'] LOOP
 EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('DROP POLICY IF EXISTS %I_self_read ON %I',t,t); EXECUTE format('DROP POLICY IF EXISTS %I_manage ON %I',t,t);
 EXECUTE format('CREATE POLICY %I_self_read ON %I FOR SELECT USING (employee_id=auth.uid())',t,t);
 EXECUTE format('CREATE POLICY %I_manage ON %I FOR ALL USING (org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission(''employees.manage'')) WITH CHECK (org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission(''employees.manage''))',t,t);
 END LOOP; END $$;
DROP POLICY IF EXISTS exit_case_self_create ON employee_exit_cases;
DROP POLICY IF EXISTS exit_interview_self_manage ON employee_exit_interviews;
DROP POLICY IF EXISTS exit_interview_self_update ON employee_exit_interviews;
CREATE POLICY exit_case_self_create ON employee_exit_cases FOR INSERT WITH CHECK(
 employee_id=auth.uid() AND submitted_by=auth.uid() AND org_id=current_user_org_id()
 AND exit_type='RESIGNATION' AND voluntary=TRUE
 AND EXISTS(SELECT 1 FROM users u WHERE u.id=auth.uid() AND u.org_id=employee_exit_cases.org_id
   AND u.active_property_id IS NOT DISTINCT FROM employee_exit_cases.property_id AND u.department_id IS NOT DISTINCT FROM employee_exit_cases.department_id)
);
CREATE POLICY exit_interview_self_manage ON employee_exit_interviews FOR INSERT WITH CHECK(employee_id=auth.uid() AND org_id=current_user_org_id() AND EXISTS(SELECT 1 FROM employee_exit_cases c WHERE c.id=exit_case_id AND c.employee_id=auth.uid()));
CREATE POLICY exit_interview_self_update ON employee_exit_interviews FOR UPDATE USING(employee_id=auth.uid() AND EXISTS(SELECT 1 FROM employee_exit_cases c WHERE c.id=exit_case_id AND c.employee_id=auth.uid())) WITH CHECK(employee_id=auth.uid() AND org_id=current_user_org_id());

COMMIT;
