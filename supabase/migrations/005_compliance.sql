CREATE TABLE IF NOT EXISTS right_to_work_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    application_id UUID,
    check_type VARCHAR(30) DEFAULT 'UK_RTW',
    status VARCHAR(20) DEFAULT 'PENDING',
    documents JSONB DEFAULT '[]',
    verified_by UUID REFERENCES users(id) ON DELETE SET NULL,
    verified_at TIMESTAMP,
    expiry_date DATE,
    upload_token UUID DEFAULT gen_random_uuid(),
    alert_30_day_sent BOOLEAN DEFAULT FALSE,
    alert_7_day_sent BOOLEAN DEFAULT FALSE,
    alert_expired_sent BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS visa_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    country VARCHAR(100),
    max_duration_days INT,
    annual_cap INT,
    renewal_notice_days INT DEFAULT 30,
    documentation_required JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fair_workweek_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jurisdiction VARCHAR(30) NOT NULL,
    rule_type VARCHAR(50) NOT NULL,
    rule_value JSONB DEFAULT '{}',
    effective_date DATE,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scheduling_compliance_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID,
    shift_date DATE,
    shift_start TIMESTAMP,
    shift_end TIMESTAMP,
    hours_since_last_shift FLOAT,
    violation_type VARCHAR(30),
    violation_severity VARCHAR(20),
    jurisdiction VARCHAR(30),
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS data_consent_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    consent_type VARCHAR(30) NOT NULL,
    consented BOOLEAN NOT NULL,
    consent_text_version VARCHAR(10) DEFAULT 'v1.0',
    consented_at TIMESTAMP DEFAULT NOW(),
    withdrawn_at TIMESTAMP,
    ip_address TEXT,
    user_agent TEXT
);

CREATE TABLE IF NOT EXISTS erasure_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    requested_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'PENDING',
    denial_reason TEXT,
    completed_at TIMESTAMP,
    processed_by UUID REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS eeo_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    application_id UUID,
    gender VARCHAR(20),
    ethnicity VARCHAR(30),
    disability_status VARCHAR(20),
    veteran_status VARCHAR(20),
    collected_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compliance_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_type VARCHAR(20) NOT NULL,
    actor_id UUID,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id TEXT,
    metadata JSONB DEFAULT '{}',
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Seed visa types
INSERT INTO visa_types (code, name, country, max_duration_days, annual_cap, renewal_notice_days, documentation_required) VALUES
('H2B', 'H-2B Temporary Non-Agricultural Worker', 'US', 365, 66000, 60, '["H2B approval notice", "Passport", "I-94"]'),
('J1', 'J-1 Exchange Visitor', 'US', 730, NULL, 30, '["J-1 visa stamp", "DS-2019", "Passport"]'),
('TIER2', 'Tier 2 / Skilled Worker Visa', 'UK', 1825, NULL, 90, '["BRP card", "Visa vignette", "Certificate of Sponsorship"]'),
('EU_SETTLED', 'EU Settled Status', 'UK', NULL, NULL, 90, '["Share code", "Passport or national ID"]'),
('BRP', 'Biometric Residence Permit', 'UK', 1825, NULL, 60, '["BRP card"]')
ON CONFLICT DO NOTHING;

-- Seed Fair Workweek rules
INSERT INTO fair_workweek_rules (jurisdiction, rule_type, rule_value, effective_date, description) VALUES
('NYC', 'ADVANCE_SCHEDULE_NOTICE', '{"notice_days": 14, "penalty_per_violation": 100}', '2017-11-26', 'Fast food employers must post schedules 14 days in advance'),
('NYC', 'CLOPENING_RESTRICTION', '{"min_rest_hours": 11, "premium_pay_if_violated": 100}', '2017-11-26', 'Employees must have 11 hours rest between closing and opening shifts'),
('SF', 'ADVANCE_SCHEDULE_NOTICE', '{"notice_days": 14, "penalty_per_violation": 75}', '2015-07-03', 'Retail employers must post schedules 14 days in advance'),
('SF', 'SPLIT_SHIFT_PREMIUM', '{"max_gap_hours": 4, "premium_multiplier": 1.5}', '2015-07-03', 'Split shifts with gap over 4 hours require premium pay'),
('CHICAGO', 'ADVANCE_SCHEDULE_NOTICE', '{"notice_days": 10, "penalty_per_violation": 50}', '2020-07-01', 'Chicago Fair Workweek Ordinance: 10 days advance notice'),
('SEATTLE', 'ADVANCE_SCHEDULE_NOTICE', '{"notice_days": 14, "penalty_per_violation": 100}', '2017-07-01', 'Seattle secure scheduling: 14 days advance notice'),
('UK_NATIONAL', 'REST_BETWEEN_SHIFTS', '{"min_rest_hours": 11}', '1998-10-01', 'Working Time Regulations 1998: 11 hours daily rest'),
('UK_NATIONAL', 'ADVANCE_SCHEDULE_NOTICE', '{"weekly_hours_cap": 48}', '1998-10-01', '48-hour working week cap (Working Time Regulations)')
ON CONFLICT DO NOTHING;

-- Enable RLS
ALTER TABLE right_to_work_checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE visa_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE fair_workweek_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduling_compliance_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_consent_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE erasure_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE eeo_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_audit_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rtw_policy ON right_to_work_checks; CREATE POLICY rtw_policy ON right_to_work_checks FOR ALL USING (true);
DROP POLICY IF EXISTS visa_types_policy ON visa_types; CREATE POLICY visa_types_policy ON visa_types FOR SELECT USING (true);
DROP POLICY IF EXISTS fw_rules_policy ON fair_workweek_rules; CREATE POLICY fw_rules_policy ON fair_workweek_rules FOR SELECT USING (true);
DROP POLICY IF EXISTS sched_log_policy ON scheduling_compliance_log; CREATE POLICY sched_log_policy ON scheduling_compliance_log FOR ALL USING (true);
DROP POLICY IF EXISTS consent_policy ON data_consent_records; CREATE POLICY consent_policy ON data_consent_records FOR ALL USING (true);
DROP POLICY IF EXISTS erasure_policy ON erasure_requests; CREATE POLICY erasure_policy ON erasure_requests FOR ALL USING (true);
DROP POLICY IF EXISTS eeo_policy ON eeo_data; CREATE POLICY eeo_policy ON eeo_data FOR ALL USING (true);
DROP POLICY IF EXISTS audit_policy ON compliance_audit_logs; CREATE POLICY audit_policy ON compliance_audit_logs FOR ALL USING (true);

ALTER TABLE candidates ADD COLUMN IF NOT EXISTS blind_screening BOOLEAN DEFAULT FALSE;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS data_status VARCHAR(20) DEFAULT 'ACTIVE';
