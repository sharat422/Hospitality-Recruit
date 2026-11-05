CREATE TABLE IF NOT EXISTS properties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) DEFAULT 'HOTEL',
    location VARCHAR(255),
    country VARCHAR(100),
    region VARCHAR(100),
    timezone VARCHAR(100) DEFAULT 'UTC',
    brand_color VARCHAR(7) DEFAULT '#7C3AED',
    logo_url TEXT,
    default_recruiter_id UUID REFERENCES users(id) ON DELETE SET NULL,
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hiring_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    property_id UUID REFERENCES properties(id) ON DELETE CASCADE,
    campaign_type VARCHAR(30) DEFAULT 'SEASONAL',
    target_start_date DATE,
    target_hire_count INT DEFAULT 0,
    current_hire_count INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'DRAFT',
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS campaign_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID REFERENCES hiring_campaigns(id) ON DELETE CASCADE,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    target_headcount INT DEFAULT 1,
    filled_count INT DEFAULT 0,
    priority VARCHAR(20) DEFAULT 'NORMAL',
    auto_close_when_filled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS seasonal_forecasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id UUID REFERENCES properties(id) ON DELETE CASCADE,
    forecast_year INT NOT NULL,
    forecast_month INT NOT NULL,
    department VARCHAR(100),
    predicted_headcount_needed INT DEFAULT 0,
    actual_headcount INT,
    confidence_score FLOAT DEFAULT 0.5,
    forecast_inputs JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS seasonal_workers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    property_id UUID REFERENCES properties(id) ON DELETE CASCADE,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    season_year INT NOT NULL,
    season_label VARCHAR(100),
    performance_rating INT CHECK (performance_rating BETWEEN 1 AND 5),
    would_rehire BOOLEAN,
    rehire_priority VARCHAR(20) DEFAULT 'STANDARD',
    recall_sent BOOLEAN DEFAULT FALSE,
    recall_responded BOOLEAN DEFAULT FALSE,
    recall_response VARCHAR(20),
    recall_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bulk_imports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID REFERENCES hiring_campaigns(id) ON DELETE CASCADE,
    imported_by UUID REFERENCES users(id) ON DELETE SET NULL,
    file_url TEXT,
    total_rows INT DEFAULT 0,
    successful_rows INT DEFAULT 0,
    failed_rows INT DEFAULT 0,
    errors JSONB DEFAULT '[]',
    status VARCHAR(20) DEFAULT 'PROCESSING',
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE hiring_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE seasonal_forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE seasonal_workers ENABLE ROW LEVEL SECURITY;
ALTER TABLE bulk_imports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS properties_policy ON properties; CREATE POLICY properties_policy ON properties FOR ALL USING (true);
DROP POLICY IF EXISTS campaigns_policy ON hiring_campaigns; CREATE POLICY campaigns_policy ON hiring_campaigns FOR ALL USING (true);
DROP POLICY IF EXISTS campaign_roles_policy ON campaign_roles; CREATE POLICY campaign_roles_policy ON campaign_roles FOR ALL USING (true);
DROP POLICY IF EXISTS forecasts_policy ON seasonal_forecasts; CREATE POLICY forecasts_policy ON seasonal_forecasts FOR ALL USING (true);
DROP POLICY IF EXISTS seasonal_workers_policy ON seasonal_workers; CREATE POLICY seasonal_workers_policy ON seasonal_workers FOR ALL USING (true);
DROP POLICY IF EXISTS bulk_imports_policy ON bulk_imports; CREATE POLICY bulk_imports_policy ON bulk_imports FOR ALL USING (true);

INSERT INTO properties (name, type, location, country, region, brand_color)
VALUES ('Grand Seaview Resort', 'RESORT', 'Miami Beach, FL', 'USA', 'Southeast', '#7C3AED')
ON CONFLICT DO NOTHING;
