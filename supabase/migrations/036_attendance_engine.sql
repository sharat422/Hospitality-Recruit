-- Attendance engine: actual punches, validation, corrections and biometric adapters.
-- Payroll must consume only attendance_daily_records where validation_status='VALIDATED'.

BEGIN;

CREATE TABLE IF NOT EXISTS attendance_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata',
    latitude NUMERIC(10,7),
    longitude NUMERIC(10,7),
    geofence_radius_m INT NOT NULL DEFAULT 150 CHECK (geofence_radius_m BETWEEN 25 AND 5000),
    require_geofence BOOLEAN NOT NULL DEFAULT FALSE,
    late_grace_minutes INT NOT NULL DEFAULT 10 CHECK (late_grace_minutes BETWEEN 0 AND 120),
    early_departure_grace_minutes INT NOT NULL DEFAULT 5 CHECK (early_departure_grace_minutes BETWEEN 0 AND 120),
    overtime_after_minutes INT NOT NULL DEFAULT 480 CHECK (overtime_after_minutes > 0),
    -- ISO weekday numbers: Monday=1 through Sunday=7.
    weekly_off_days INT[] NOT NULL DEFAULT ARRAY[7],
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(org_id, property_id)
);

CREATE TABLE IF NOT EXISTS attendance_punches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    punch_type VARCHAR(8) NOT NULL CHECK (punch_type IN ('IN','OUT')),
    punched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source VARCHAR(24) NOT NULL DEFAULT 'WEB' CHECK (source IN ('WEB','MOBILE','BIOMETRIC','WHATSAPP','MANUAL')),
    latitude NUMERIC(10,7),
    longitude NUMERIC(10,7),
    gps_accuracy_m NUMERIC(8,2),
    distance_from_property_m NUMERIC(10,2),
    geofence_status VARCHAR(24) NOT NULL DEFAULT 'NOT_REQUIRED'
        CHECK (geofence_status IN ('INSIDE','OUTSIDE','UNAVAILABLE','NOT_REQUIRED')),
    device_id VARCHAR(200),
    provider_code VARCHAR(50),
    provider_event_id VARCHAR(200),
    notes TEXT,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(provider_code, provider_event_id)
);
CREATE INDEX IF NOT EXISTS attendance_punch_employee_time_idx
    ON attendance_punches(org_id, employee_id, punched_at DESC);

CREATE TABLE IF NOT EXISTS attendance_daily_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    attendance_date DATE NOT NULL,
    scheduled_start TIMESTAMPTZ,
    scheduled_end TIMESTAMPTZ,
    first_in_at TIMESTAMPTZ,
    last_out_at TIMESTAMPTZ,
    worked_minutes INT NOT NULL DEFAULT 0 CHECK (worked_minutes >= 0),
    late_minutes INT NOT NULL DEFAULT 0 CHECK (late_minutes >= 0),
    early_departure_minutes INT NOT NULL DEFAULT 0 CHECK (early_departure_minutes >= 0),
    overtime_minutes INT NOT NULL DEFAULT 0 CHECK (overtime_minutes >= 0),
    status VARCHAR(24) NOT NULL DEFAULT 'MISSING_PUNCH'
        CHECK (status IN ('PRESENT','ABSENT','WEEKLY_OFF','LEAVE','MISSING_PUNCH','INVALID')),
    anomaly_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    validation_status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (validation_status IN ('PENDING','VALIDATED','REJECTED')),
    validated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    validated_at TIMESTAMPTZ,
    source_version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(org_id, employee_id, attendance_date)
);
CREATE INDEX IF NOT EXISTS attendance_daily_property_date_idx
    ON attendance_daily_records(org_id, property_id, attendance_date DESC);

CREATE TABLE IF NOT EXISTS attendance_corrections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    daily_record_id UUID NOT NULL REFERENCES attendance_daily_records(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    requested_in_at TIMESTAMPTZ,
    requested_out_at TIMESTAMPTZ,
    reason TEXT NOT NULL CHECK (length(trim(reason)) >= 5),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','APPROVED','REJECTED','CANCELLED')),
    requested_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    review_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS attendance_correction_one_pending_idx
    ON attendance_corrections(daily_record_id, employee_id) WHERE status='PENDING';

CREATE TABLE IF NOT EXISTS attendance_correction_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    correction_id UUID NOT NULL REFERENCES attendance_corrections(id) ON DELETE CASCADE,
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(40) NOT NULL,
    before_data JSONB,
    after_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS biometric_provider_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    provider_code VARCHAR(50) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    config_secret_ref TEXT,
    webhook_secret_hash TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_sync_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(org_id, property_id, provider_code)
);

CREATE TABLE IF NOT EXISTS biometric_sync_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider_config_id UUID REFERENCES biometric_provider_configs(id) ON DELETE SET NULL,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    provider_code VARCHAR(50) NOT NULL,
    external_event_id VARCHAR(200) NOT NULL,
    employee_external_id VARCHAR(200) NOT NULL,
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'RECEIVED'
        CHECK (status IN ('RECEIVED','PROCESSED','DUPLICATE','FAILED')),
    error_message TEXT,
    attendance_punch_id UUID REFERENCES attendance_punches(id) ON DELETE SET NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    UNIQUE(org_id, provider_code, external_event_id)
);

CREATE OR REPLACE FUNCTION audit_attendance_correction_change()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
  INSERT INTO attendance_correction_audit_logs
    (org_id, correction_id, actor_id, action, before_data, after_data)
  VALUES (
    NEW.org_id, NEW.id, auth.uid(),
    CASE WHEN TG_OP='INSERT' THEN 'REQUESTED' ELSE 'STATUS_' || NEW.status END,
    CASE WHEN TG_OP='UPDATE' THEN to_jsonb(OLD) ELSE NULL END,
    to_jsonb(NEW)
  );
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS attendance_correction_audit_trigger ON attendance_corrections;
CREATE TRIGGER attendance_correction_audit_trigger
AFTER INSERT OR UPDATE ON attendance_corrections
FOR EACH ROW EXECUTE FUNCTION audit_attendance_correction_change();

ALTER TABLE attendance_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_punches ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_daily_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_corrections ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_correction_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE biometric_provider_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE biometric_sync_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS attendance_policy_read ON attendance_policies;
DROP POLICY IF EXISTS attendance_policy_manage ON attendance_policies;
DROP POLICY IF EXISTS attendance_punch_read ON attendance_punches;
DROP POLICY IF EXISTS attendance_punch_self_insert ON attendance_punches;
DROP POLICY IF EXISTS attendance_punch_manage_insert ON attendance_punches;
DROP POLICY IF EXISTS attendance_daily_read ON attendance_daily_records;
DROP POLICY IF EXISTS attendance_daily_manage ON attendance_daily_records;
DROP POLICY IF EXISTS attendance_correction_read ON attendance_corrections;
DROP POLICY IF EXISTS attendance_correction_self_insert ON attendance_corrections;
DROP POLICY IF EXISTS attendance_correction_manage ON attendance_corrections;
DROP POLICY IF EXISTS attendance_audit_read ON attendance_correction_audit_logs;
DROP POLICY IF EXISTS biometric_config_manage ON biometric_provider_configs;
DROP POLICY IF EXISTS biometric_event_read ON biometric_sync_events;

CREATE POLICY attendance_policy_read ON attendance_policies FOR SELECT USING (
  org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('attendance.read'));
CREATE POLICY attendance_policy_manage ON attendance_policies FOR ALL USING (
  org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('attendance.manage'))
  WITH CHECK (org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('attendance.manage'));

CREATE POLICY attendance_punch_read ON attendance_punches FOR SELECT USING (
  employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_employee_access(employee_id)
    AND current_user_role() NOT IN ('EMPLOYEE','CANDIDATE') AND rbac_has_permission('attendance.read')));
CREATE POLICY attendance_punch_self_insert ON attendance_punches FOR INSERT WITH CHECK (
  employee_id=auth.uid() AND org_id=current_user_org_id() AND has_property_access(property_id)
  AND source IN ('WEB','MOBILE','WHATSAPP'));
CREATE POLICY attendance_punch_manage_insert ON attendance_punches FOR INSERT WITH CHECK (
  org_id=current_user_org_id() AND rbac_employee_access(employee_id)
  AND has_property_access(property_id) AND rbac_has_permission('attendance.manage'));

CREATE POLICY attendance_daily_read ON attendance_daily_records FOR SELECT USING (
  employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_employee_access(employee_id)
    AND current_user_role() NOT IN ('EMPLOYEE','CANDIDATE') AND rbac_has_permission('attendance.read')));
CREATE POLICY attendance_daily_manage ON attendance_daily_records FOR ALL USING (
  org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission('attendance.manage'))
  WITH CHECK (org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission('attendance.manage'));

CREATE POLICY attendance_correction_read ON attendance_corrections FOR SELECT USING (
  employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_employee_access(employee_id)
    AND current_user_role() NOT IN ('EMPLOYEE','CANDIDATE') AND rbac_has_permission('attendance.read')));
CREATE POLICY attendance_correction_self_insert ON attendance_corrections FOR INSERT WITH CHECK (
  employee_id=auth.uid() AND requested_by=auth.uid() AND org_id=current_user_org_id()
  AND EXISTS (SELECT 1 FROM attendance_daily_records d WHERE d.id=daily_record_id
    AND d.employee_id=auth.uid() AND d.org_id=current_user_org_id()));
CREATE POLICY attendance_correction_manage ON attendance_corrections FOR UPDATE USING (
  org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission('attendance.manage'))
  WITH CHECK (org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission('attendance.manage'));

CREATE POLICY attendance_audit_read ON attendance_correction_audit_logs FOR SELECT USING (
  org_id=current_user_org_id() AND EXISTS (SELECT 1 FROM attendance_corrections c
    WHERE c.id=correction_id AND (c.employee_id=auth.uid() OR
      (rbac_employee_access(c.employee_id) AND rbac_has_permission('attendance.read')))));

CREATE POLICY biometric_config_manage ON biometric_provider_configs FOR ALL USING (
  org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('attendance.manage'))
  WITH CHECK (org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('attendance.manage'));
CREATE POLICY biometric_event_read ON biometric_sync_events FOR SELECT USING (
  org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('attendance.manage'));

CREATE OR REPLACE VIEW validated_attendance_for_payroll
WITH (security_invoker=true) AS
SELECT id, org_id, employee_id, property_id, attendance_date, worked_minutes,
       overtime_minutes, status, validated_by, validated_at
FROM attendance_daily_records
WHERE validation_status='VALIDATED';

COMMIT;
