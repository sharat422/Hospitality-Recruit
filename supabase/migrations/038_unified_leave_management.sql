-- Unified leave management for WEB, PWA and WHATSAPP channels.
BEGIN;

CREATE TABLE IF NOT EXISTS leave_types (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  code VARCHAR(30) NOT NULL,
  name VARCHAR(100) NOT NULL,
  annual_allowance_days NUMERIC(6,2) NOT NULL DEFAULT 0,
  is_paid BOOLEAN NOT NULL DEFAULT TRUE,
  requires_document BOOLEAN NOT NULL DEFAULT FALSE,
  requires_hr_approval BOOLEAN NOT NULL DEFAULT FALSE,
  allow_negative_balance BOOLEAN NOT NULL DEFAULT FALSE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(org_id, code)
);

INSERT INTO leave_types(org_id, code, name, annual_allowance_days, is_paid, requires_hr_approval)
SELECT o.id, v.code, v.name, v.days, v.paid, v.hr
FROM organizations o CROSS JOIN (VALUES
 ('CASUAL','Casual Leave',12,true,false), ('SICK','Sick Leave',12,true,false),
 ('EARNED','Earned Leave',15,true,true), ('EMERGENCY','Emergency Leave',12,true,false),
 ('LWP','Leave Without Pay',0,false,true)
) AS v(code,name,days,paid,hr)
ON CONFLICT(org_id,code) DO NOTHING;

CREATE OR REPLACE FUNCTION seed_default_leave_types_for_org()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
  INSERT INTO leave_types(org_id,code,name,annual_allowance_days,is_paid,requires_hr_approval) VALUES
   (NEW.id,'CASUAL','Casual Leave',12,true,false),(NEW.id,'SICK','Sick Leave',12,true,false),
   (NEW.id,'EARNED','Earned Leave',15,true,true),(NEW.id,'EMERGENCY','Emergency Leave',12,true,false),
   (NEW.id,'LWP','Leave Without Pay',0,false,true)
  ON CONFLICT(org_id,code) DO NOTHING;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS seed_default_leave_types_on_org ON organizations;
CREATE TRIGGER seed_default_leave_types_on_org AFTER INSERT ON organizations
FOR EACH ROW EXECUTE FUNCTION seed_default_leave_types_for_org();

CREATE TABLE IF NOT EXISTS property_holidays (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  holiday_date DATE NOT NULL,
  name VARCHAR(160) NOT NULL,
  holiday_type VARCHAR(24) NOT NULL DEFAULT 'PUBLIC' CHECK(holiday_type IN ('PUBLIC','RESTRICTED','PROPERTY')),
  is_paid BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(property_id,holiday_date,name)
);

ALTER TABLE leave_requests
  ADD COLUMN IF NOT EXISTS property_id UUID REFERENCES properties(id) ON DELETE RESTRICT,
  ADD COLUMN IF NOT EXISTS department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS start_date DATE,
  ADD COLUMN IF NOT EXISTS end_date DATE,
  ADD COLUMN IF NOT EXISTS total_days NUMERIC(6,2) NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'WHATSAPP',
  ADD COLUMN IF NOT EXISTS manager_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  ADD COLUMN IF NOT EXISTS manager_reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS manager_reviewed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS hr_status VARCHAR(20) NOT NULL DEFAULT 'NOT_REQUIRED',
  ADD COLUMN IF NOT EXISTS hr_reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS hr_reviewed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS attachment_url TEXT;

UPDATE leave_requests SET start_date=leave_date, end_date=leave_date,
 source=COALESCE(channel,'WHATSAPP'), manager_status=CASE WHEN status='PENDING' THEN 'PENDING' ELSE status END
WHERE start_date IS NULL OR end_date IS NULL;
ALTER TABLE leave_requests ALTER COLUMN start_date SET NOT NULL;
ALTER TABLE leave_requests ALTER COLUMN end_date SET NOT NULL;
DO $$ BEGIN ALTER TABLE leave_requests ADD CONSTRAINT leave_request_date_order CHECK(end_date>=start_date); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE leave_requests ADD CONSTRAINT leave_request_source_check CHECK(source IN ('WEB','PWA','WHATSAPP','ADMIN')); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE leave_requests ADD CONSTRAINT leave_request_manager_status_check CHECK(manager_status IN ('PENDING','APPROVED','REJECTED')); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE leave_requests ADD CONSTRAINT leave_request_hr_status_check CHECK(hr_status IN ('NOT_REQUIRED','PENDING','APPROVED','REJECTED')); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE UNIQUE INDEX IF NOT EXISTS leave_request_active_day_unique
  ON leave_requests(employee_id,start_date,end_date) WHERE status IN ('PENDING','APPROVED');
CREATE INDEX IF NOT EXISTS leave_request_calendar_idx ON leave_requests(org_id,property_id,start_date,end_date,status);

CREATE TABLE IF NOT EXISTS leave_audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  leave_request_id UUID NOT NULL REFERENCES leave_requests(id) ON DELETE CASCADE,
  actor_id UUID REFERENCES users(id) ON DELETE SET NULL, action VARCHAR(40) NOT NULL,
  source VARCHAR(20) NOT NULL, before_data JSONB, after_data JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE leave_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE property_holidays ENABLE ROW LEVEL SECURITY;
ALTER TABLE leave_audit_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS leave_type_read ON leave_types; DROP POLICY IF EXISTS leave_type_manage ON leave_types;
CREATE POLICY leave_type_read ON leave_types FOR SELECT USING(org_id=current_user_org_id() AND rbac_has_permission('leave.read'));
CREATE POLICY leave_type_manage ON leave_types FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('leave.manage')) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('leave.manage'));
DROP POLICY IF EXISTS holiday_read ON property_holidays; DROP POLICY IF EXISTS holiday_manage ON property_holidays;
CREATE POLICY holiday_read ON property_holidays FOR SELECT USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('leave.read'));
CREATE POLICY holiday_manage ON property_holidays FOR ALL USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('leave.manage')) WITH CHECK(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('leave.manage'));
DROP POLICY IF EXISTS leave_audit_read ON leave_audit_logs; DROP POLICY IF EXISTS leave_audit_insert ON leave_audit_logs;
CREATE POLICY leave_audit_read ON leave_audit_logs FOR SELECT USING(org_id=current_user_org_id() AND rbac_has_permission('leave.read'));
CREATE POLICY leave_audit_insert ON leave_audit_logs FOR INSERT WITH CHECK(org_id=current_user_org_id() AND actor_id=auth.uid());

COMMIT;
