-- ============================================================================
-- HospRecruit AI — Full Schema
-- Run AFTER 000_auth_setup.sql
-- ============================================================================

-- organizations and users already created in 000_auth_setup.sql
-- Skip re-creating them here.

-- ============================================================================
-- Module 1: Candidates & AI Screening
-- ============================================================================

CREATE TABLE IF NOT EXISTS candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    job_id UUID,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    location VARCHAR(255),
    source VARCHAR(50) DEFAULT 'web_form',
    status VARCHAR(50) DEFAULT 'active',
    qualified BOOLEAN DEFAULT FALSE,
    pipeline_stage VARCHAR(50) DEFAULT 'applied',
    raw_data JSONB,
    screening_result JSONB,
    availability JSONB,
    screened_at TIMESTAMP,
    accepted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS candidates_org_job ON candidates(org_id, job_id);
CREATE INDEX IF NOT EXISTS candidates_qualified ON candidates(org_id, qualified);
CREATE INDEX IF NOT EXISTS candidates_pipeline ON candidates(org_id, pipeline_stage);
CREATE INDEX IF NOT EXISTS candidates_status ON candidates(org_id, status);

ALTER TABLE candidates ENABLE ROW LEVEL SECURITY;

CREATE POLICY candidates_org_isolation ON candidates
    USING (
        auth.uid() IN (SELECT id FROM users WHERE org_id = candidates.org_id)
    );

-- ============================================================================
-- Module 2: Jobs & Shifts
-- ============================================================================

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    title VARCHAR(255) NOT NULL,
    role_type VARCHAR(100),
    description TEXT,
    required_qualifications TEXT,
    status VARCHAR(50) DEFAULT 'open',
    positions_available INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shifts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    job_id UUID NOT NULL REFERENCES jobs(id),
    role VARCHAR(100),
    shift_type VARCHAR(50),
    status VARCHAR(50) DEFAULT 'open',
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    hours_per_week FLOAT,
    urgency VARCHAR(50) DEFAULT 'normal',
    season VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shift_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    candidate_id UUID NOT NULL REFERENCES candidates(id),
    shift_id UUID NOT NULL REFERENCES shifts(id),
    match_score FLOAT CHECK (match_score >= 0 AND match_score <= 1),
    status VARCHAR(50) DEFAULT 'matched',
    conflicts JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS shifts_org ON shifts(org_id, status);
CREATE INDEX IF NOT EXISTS shift_matches_org ON shift_matches(org_id, status);

ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE shifts ENABLE ROW LEVEL SECURITY;
ALTER TABLE shift_matches ENABLE ROW LEVEL SECURITY;

CREATE POLICY jobs_org_isolation ON jobs
    USING (auth.uid() IN (SELECT id FROM users WHERE org_id = jobs.org_id));

CREATE POLICY shifts_org_isolation ON shifts
    USING (auth.uid() IN (SELECT id FROM users WHERE org_id = shifts.org_id));

CREATE POLICY shift_matches_org_isolation ON shift_matches
    USING (auth.uid() IN (SELECT id FROM users WHERE org_id = shift_matches.org_id));

-- ============================================================================
-- Module 3: Mobile Candidate Portal
-- ============================================================================

CREATE TABLE IF NOT EXISTS candidate_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES candidates(id),
    current_role VARCHAR(255),
    years_experience INT,
    certifications JSONB DEFAULT '[]',
    willing_relocate BOOLEAN DEFAULT FALSE,
    preferred_locations TEXT[],
    profile_complete BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE candidate_profiles ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Module 4: SMS & Conversations
-- ============================================================================

CREATE TABLE IF NOT EXISTS sms_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    candidate_id UUID REFERENCES candidates(id),
    from_number VARCHAR(20) NOT NULL,
    to_number VARCHAR(20) NOT NULL,
    body TEXT NOT NULL,
    direction VARCHAR(20),
    twilio_sid VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    candidate_id UUID NOT NULL REFERENCES candidates(id),
    user_message TEXT NOT NULL,
    ai_response TEXT NOT NULL,
    intent VARCHAR(50),
    context JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS sms_candidate ON sms_messages(candidate_id);
CREATE INDEX IF NOT EXISTS conversations_candidate ON conversation_turns(candidate_id);

ALTER TABLE sms_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_turns ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Module 5: Onboarding & Compliance
-- ============================================================================

CREATE TABLE IF NOT EXISTS onboarding_flows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    candidate_id UUID NOT NULL REFERENCES candidates(id),
    job_id UUID NOT NULL REFERENCES jobs(id),
    status VARCHAR(50) DEFAULT 'not_started',
    progress_percent FLOAT DEFAULT 0,
    estimated_completion TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compliance_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    candidate_id UUID NOT NULL REFERENCES candidates(id),
    job_id UUID NOT NULL REFERENCES jobs(id),
    task_type VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    due_date TIMESTAMP,
    result JSONB,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS compliance_tasks_pending ON compliance_tasks(org_id, status);
CREATE INDEX IF NOT EXISTS compliance_tasks_due ON compliance_tasks(org_id, due_date);

ALTER TABLE onboarding_flows ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_tasks ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Module 6: Analytics
-- ============================================================================

CREATE TABLE IF NOT EXISTS pipeline_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    job_id UUID REFERENCES jobs(id),
    stage VARCHAR(50),
    count INT,
    avg_days_in_stage FLOAT,
    date TIMESTAMP DEFAULT NOW()
);

ALTER TABLE pipeline_metrics ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Module 7: Talent Pool & Retention
-- ============================================================================

CREATE TABLE IF NOT EXISTS talent_cohorts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    cohort_name VARCHAR(255),
    season VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS engagement_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    cohort_id UUID NOT NULL REFERENCES talent_cohorts(id),
    message TEXT NOT NULL,
    channel VARCHAR(50),
    scheduled_date TIMESTAMP,
    status VARCHAR(50) DEFAULT 'scheduled',
    sent_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE talent_cohorts ENABLE ROW LEVEL SECURITY;
ALTER TABLE engagement_campaigns ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Module 8: Billing & White-Label
-- ============================================================================

CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    tier VARCHAR(50),
    billing_email VARCHAR(255),
    stripe_customer_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'active',
    monthly_cost FLOAT,
    renewal_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(org_id)
);

CREATE TABLE IF NOT EXISTS white_label_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    custom_domain VARCHAR(255),
    logo_url VARCHAR(255),
    brand_color VARCHAR(7) DEFAULT '#000000',
    custom_terms TEXT,
    api_key VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(org_id)
);

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE white_label_configs ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Realtime
-- ============================================================================

ALTER PUBLICATION supabase_realtime ADD TABLE candidates;
ALTER PUBLICATION supabase_realtime ADD TABLE shifts;
ALTER PUBLICATION supabase_realtime ADD TABLE compliance_tasks;
ALTER PUBLICATION supabase_realtime ADD TABLE pipeline_metrics;
