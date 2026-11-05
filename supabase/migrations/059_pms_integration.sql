-- Hotel PMS integration: occupancy feed and occupancy-driven staffing demand.
--
-- Indian hotel groups run IDS Next / eZee / Hotelogix as the system of record
-- for rooms. This pulls their occupancy forecast in and turns it into required
-- headcount per department, which is what actually drives hiring.
--
-- Credentials are NOT stored here. `credential_env_var` names the environment
-- variable holding the vendor API key, so no vendor secret ever sits in a
-- database column that `properties.read` can see.
BEGIN;

CREATE TABLE IF NOT EXISTS pms_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    provider_code VARCHAR(40) NOT NULL
        CHECK (provider_code IN ('MOCK','IDS_NEXT','EZEE','HOTELOGIX')),
    base_url TEXT,
    property_ref VARCHAR(120),
    rooms_available INTEGER CHECK (rooms_available IS NULL OR rooms_available > 0),
    credential_env_var VARCHAR(80),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_sync_at TIMESTAMPTZ,
    last_sync_status VARCHAR(20)
        CHECK (last_sync_status IS NULL OR last_sync_status IN ('OK','FAILED')),
    last_sync_error TEXT,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- One live connection per property; a hotel has exactly one PMS.
    UNIQUE (property_id),
    -- A REST provider is unusable without an endpoint; sandbox needs none.
    CONSTRAINT pms_rest_requires_base_url
        CHECK (provider_code = 'MOCK' OR base_url IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS pms_occupancy_forecasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    business_date DATE NOT NULL,
    rooms_available INTEGER NOT NULL CHECK (rooms_available >= 0),
    rooms_sold INTEGER NOT NULL CHECK (rooms_sold >= 0),
    occupancy_pct NUMERIC(5,2) NOT NULL CHECK (occupancy_pct BETWEEN 0 AND 100),
    arrivals INTEGER NOT NULL DEFAULT 0 CHECK (arrivals >= 0),
    departures INTEGER NOT NULL DEFAULT 0 CHECK (departures >= 0),
    source VARCHAR(40) NOT NULL DEFAULT 'PMS',
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (rooms_sold <= rooms_available),
    -- Re-syncing a date overwrites it rather than duplicating the forecast.
    UNIQUE (property_id, business_date)
);

CREATE INDEX IF NOT EXISTS pms_forecast_property_date_idx
    ON pms_occupancy_forecasts(property_id, business_date);

CREATE TABLE IF NOT EXISTS department_staffing_ratios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    department_code VARCHAR(40) NOT NULL,
    department_name VARCHAR(120) NOT NULL,
    -- Which occupancy number this department's headcount scales with.
    driver VARCHAR(20) NOT NULL DEFAULT 'OCCUPIED_ROOMS'
        CHECK (driver IN ('OCCUPIED_ROOMS','ARRIVALS','DEPARTURES','COVERS','FIXED')),
    -- Driver units one person covers per day (e.g. 16 rooms per attendant).
    units_per_staff NUMERIC(8,2) NOT NULL DEFAULT 1 CHECK (units_per_staff > 0),
    -- Floor that must be rostered even at zero occupancy.
    min_staff INTEGER NOT NULL DEFAULT 0 CHECK (min_staff >= 0),
    -- Guests served per occupied room; only meaningful for the COVERS driver.
    covers_per_room NUMERIC(4,2) NOT NULL DEFAULT 1.6 CHECK (covers_per_room > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (property_id, department_code)
);

ALTER TABLE pms_connections            ENABLE ROW LEVEL SECURITY;
ALTER TABLE pms_occupancy_forecasts    ENABLE ROW LEVEL SECURITY;
ALTER TABLE department_staffing_ratios ENABLE ROW LEVEL SECURITY;

DO $$ DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['pms_connections','pms_occupancy_forecasts','department_staffing_ratios'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_property_read ON %I', t, t);
    EXECUTE format('DROP POLICY IF EXISTS %I_property_manage ON %I', t, t);
    EXECUTE format('CREATE POLICY %I_property_read ON %I FOR SELECT USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''properties.read''))', t, t);
    EXECUTE format('CREATE POLICY %I_property_manage ON %I FOR ALL USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''properties.manage'')) WITH CHECK(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''properties.manage''))', t, t);
  END LOOP;
END $$;

COMMIT;
