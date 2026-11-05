-- Executive dashboard configuration and actual property revenue inputs.
BEGIN;

CREATE TABLE IF NOT EXISTS property_revenue_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    revenue_date DATE NOT NULL,
    amount_inr NUMERIC(16,2) NOT NULL CHECK (amount_inr >= 0),
    source VARCHAR(30) NOT NULL DEFAULT 'MANUAL'
      CHECK (source IN ('MANUAL','PMS','POS','ACCOUNTING_IMPORT')),
    external_reference VARCHAR(200),
    notes TEXT,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(org_id, property_id, revenue_date, source, external_reference)
);
CREATE INDEX IF NOT EXISTS property_revenue_scope_idx
  ON property_revenue_entries(org_id, property_id, revenue_date DESC);

CREATE TABLE IF NOT EXISTS executive_dashboard_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    visible_widgets JSONB NOT NULL DEFAULT '["attendance","leave","absence","vacancies","payroll","compliance","turnover_risk","property_comparison","labour_cost","overtime","revenue_per_employee","source_performance","alerts"]',
    widget_order JSONB NOT NULL DEFAULT '[]',
    default_property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    default_date_range_days INT NOT NULL DEFAULT 30 CHECK(default_date_range_days BETWEEN 1 AND 366),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(org_id,user_id)
);

ALTER TABLE property_revenue_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE executive_dashboard_preferences ENABLE ROW LEVEL SECURITY;

CREATE POLICY property_revenue_read ON property_revenue_entries FOR SELECT USING (
  org_id=current_user_org_id() AND has_property_access(property_id)
  AND rbac_has_permission('reports.financial')
);
CREATE POLICY property_revenue_manage ON property_revenue_entries FOR ALL USING (
  org_id=current_user_org_id() AND has_property_access(property_id)
  AND rbac_has_permission('financial.manage')
) WITH CHECK (
  org_id=current_user_org_id() AND has_property_access(property_id)
  AND rbac_has_permission('financial.manage')
);
CREATE POLICY executive_preferences_self ON executive_dashboard_preferences FOR ALL USING (
  org_id=current_user_org_id() AND user_id=auth.uid()
) WITH CHECK (org_id=current_user_org_id() AND user_id=auth.uid());

COMMIT;
