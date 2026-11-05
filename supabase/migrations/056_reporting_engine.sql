-- Reusable report definitions, schedules, immutable runs and delivery audit.
BEGIN;
CREATE TABLE IF NOT EXISTS report_schedules (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 name VARCHAR(160) NOT NULL,report_type VARCHAR(40) NOT NULL CHECK(report_type IN('DAILY_HR','WEEKLY_RECRUITMENT','MONTHLY_WORKFORCE','PAYROLL','COMPLIANCE','ATTRITION','SOURCE','PROPERTY_COMPARISON')),
 property_id UUID REFERENCES properties(id) ON DELETE CASCADE,frequency VARCHAR(12) NOT NULL CHECK(frequency IN('DAILY','WEEKLY','MONTHLY')),
 timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata',delivery_hour SMALLINT NOT NULL DEFAULT 9 CHECK(delivery_hour BETWEEN 0 AND 23),
 day_of_week SMALLINT CHECK(day_of_week BETWEEN 0 AND 6),day_of_month SMALLINT CHECK(day_of_month BETWEEN 1 AND 28),
 channels JSONB NOT NULL DEFAULT '["EMAIL"]',recipients JSONB NOT NULL DEFAULT '[]',is_active BOOLEAN NOT NULL DEFAULT TRUE,
 next_run_at TIMESTAMPTZ NOT NULL,created_by UUID NOT NULL REFERENCES users(id),created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS report_schedule_due_idx ON report_schedules(next_run_at) WHERE is_active;
CREATE TABLE IF NOT EXISTS report_runs (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 schedule_id UUID REFERENCES report_schedules(id) ON DELETE SET NULL,report_type VARCHAR(40) NOT NULL,property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
 period_start DATE NOT NULL,period_end DATE NOT NULL,status VARCHAR(16) NOT NULL DEFAULT 'PROCESSING' CHECK(status IN('PROCESSING','COMPLETED','PARTIAL','FAILED')),
 report_data JSONB NOT NULL DEFAULT '{}',download_token UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),download_expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW()+INTERVAL '7 days',
 generated_by UUID REFERENCES users(id) ON DELETE SET NULL,error_message TEXT,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),completed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS report_deliveries (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,report_run_id UUID NOT NULL REFERENCES report_runs(id) ON DELETE CASCADE,
 channel VARCHAR(12) NOT NULL CHECK(channel IN('EMAIL','WHATSAPP')),recipient VARCHAR(255) NOT NULL,status VARCHAR(16) NOT NULL CHECK(status IN('PENDING','SENT','FAILED')),
 provider_reference TEXT,error_message TEXT,attempt_count INT NOT NULL DEFAULT 0,delivered_at TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(report_run_id,channel,recipient)
);
CREATE UNIQUE INDEX IF NOT EXISTS report_schedule_period_once
  ON report_runs(schedule_id,period_start,period_end) WHERE schedule_id IS NOT NULL;
ALTER TABLE report_schedules ENABLE ROW LEVEL SECURITY;ALTER TABLE report_runs ENABLE ROW LEVEL SECURITY;ALTER TABLE report_deliveries ENABLE ROW LEVEL SECURITY;
CREATE POLICY report_schedule_read ON report_schedules FOR SELECT USING(org_id=current_user_org_id() AND rbac_has_permission('reports.read') AND (property_id IS NULL OR has_property_access(property_id)));
CREATE POLICY report_schedule_manage ON report_schedules FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('reports.financial') AND (property_id IS NULL OR has_property_access(property_id))) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('reports.financial') AND (property_id IS NULL OR has_property_access(property_id)));
CREATE POLICY report_run_read ON report_runs FOR SELECT USING(org_id=current_user_org_id() AND rbac_has_permission('reports.read') AND (property_id IS NULL OR has_property_access(property_id)));
CREATE POLICY report_run_insert ON report_runs FOR INSERT WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('reports.read') AND (property_id IS NULL OR has_property_access(property_id)));
CREATE POLICY report_run_update ON report_runs FOR UPDATE USING(org_id=current_user_org_id() AND rbac_has_permission('reports.read') AND (property_id IS NULL OR has_property_access(property_id))) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('reports.read') AND (property_id IS NULL OR has_property_access(property_id)));
CREATE POLICY report_delivery_read ON report_deliveries FOR SELECT USING(org_id=current_user_org_id() AND rbac_has_permission('reports.read'));
CREATE POLICY report_delivery_manage ON report_deliveries FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('reports.financial')) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('reports.financial'));
COMMIT;
