"""
Database Migration: ATS Integration

Creates tables for Merge.dev ATS synchronization:
- ats_configurations: OAuth tokens for ATS connections
- ats_synced_jobs: Cache of jobs pulled from ATS
- ats_sync_logs: Audit trail of sync operations
- candidate_ats_mappings: Links HospRecruit candidates to ATS profiles

Supported ATS Platforms (50+):
- Bullhorn
- iCIMS
- Greenhouse
- Workable
- SmartRecruiters
- JazzHR
- And 44+ more via Merge.dev
"""

-- ============================================================================
-- ATS Configuration: OAuth tokens for ATS connections
-- ============================================================================

CREATE TABLE ats_configurations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    
    -- ATS Provider
    ats_provider VARCHAR(100) NOT NULL,  -- bullhorn, icims, greenhouse, etc
    provider_display_name VARCHAR(255),  -- "Bullhorn" vs "bullhorn"
    
    -- Merge.dev Connection
    merge_account_token VARCHAR(500) NOT NULL,  -- Unique token from Merge.dev
    merge_integration_id VARCHAR(255),  -- Merge's integration ID for tracking
    
    -- OAuth Tokens (encrypted at rest)
    access_token VARCHAR(2000),  -- ATS-specific OAuth token
    refresh_token VARCHAR(2000),
    token_expires_at TIMESTAMP,
    
    -- Connection Status
    is_connected BOOLEAN DEFAULT FALSE,
    last_verified_at TIMESTAMP,
    connection_verified_at TIMESTAMP,
    
    -- Sync Settings
    auto_sync_enabled BOOLEAN DEFAULT TRUE,
    auto_sync_frequency_hours INT DEFAULT 6,  -- Sync every 6 hours
    last_sync_at TIMESTAMP,
    next_sync_at TIMESTAMP,
    
    -- Direction Control
    sync_jobs_from_ats BOOLEAN DEFAULT TRUE,   -- Pull jobs
    sync_candidates_to_ats BOOLEAN DEFAULT TRUE,  -- Push candidates
    
    -- Metadata
    ats_instance_url VARCHAR(500),  -- For some providers (e.g., Bullhorn, iCIMS)
    additional_config JSONB DEFAULT '{}',  -- Provider-specific settings
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    connected_by UUID REFERENCES users(id),
    connected_at TIMESTAMP,
    
    UNIQUE(org_id, ats_provider)
);

ALTER TABLE ats_configurations ENABLE ROW LEVEL SECURITY;
CREATE POLICY ats_configurations_org_isolation ON ats_configurations
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = ats_configurations.org_id));

-- ============================================================================
-- ATS Synced Jobs: Cache of jobs pulled from ATS
-- ============================================================================

CREATE TABLE ats_synced_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    ats_config_id UUID NOT NULL REFERENCES ats_configurations(id) ON DELETE CASCADE,
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    
    -- ATS Job Identity
    ats_job_id VARCHAR(255) NOT NULL,  -- ID in the ATS system
    ats_provider VARCHAR(100),  -- Copied from ats_configurations for easy filtering
    
    -- Job Details
    title VARCHAR(255),
    description TEXT,
    department VARCHAR(255),
    location VARCHAR(255),
    
    -- Salary
    salary_min NUMERIC,
    salary_max NUMERIC,
    salary_currency VARCHAR(10),
    
    -- Status
    ats_status VARCHAR(50),  -- open, closed, paused, filled, on_hold
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Requisition
    req_id VARCHAR(255),  -- Requisition number
    req_status VARCHAR(50),  -- approved, pending, rejected
    hiring_manager_name VARCHAR(255),
    hiring_manager_email VARCHAR(255),
    
    -- Sync Metadata
    synced_at TIMESTAMP DEFAULT NOW(),
    synced_from_ats BOOLEAN DEFAULT TRUE,
    ats_last_modified TIMESTAMP,
    sync_hash VARCHAR(64),  -- Hash to detect changes
    
    -- Publishing
    published_to_hosprecruit BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMP,
    
    -- Raw data
    ats_raw_data JSONB,  -- Full ATS response for debugging
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(org_id, ats_provider, ats_job_id)
);

CREATE INDEX ats_synced_jobs_org ON ats_synced_jobs(org_id);
CREATE INDEX ats_synced_jobs_status ON ats_synced_jobs(org_id, ats_status);
CREATE INDEX ats_synced_jobs_provider ON ats_synced_jobs(ats_provider);
CREATE INDEX ats_synced_jobs_active ON ats_synced_jobs(org_id, is_active);

ALTER TABLE ats_synced_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY ats_synced_jobs_org_isolation ON ats_synced_jobs
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = ats_synced_jobs.org_id));

-- ============================================================================
-- Candidate ATS Mapping: Links HospRecruit candidates to ATS profiles
-- ============================================================================

CREATE TABLE candidate_ats_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    candidate_id UUID NOT NULL REFERENCES candidates(id),
    ats_config_id UUID NOT NULL REFERENCES ats_configurations(id) ON DELETE CASCADE,
    
    -- ATS Candidate Identity
    ats_candidate_id VARCHAR(255) NOT NULL,  -- Candidate ID in ATS
    ats_provider VARCHAR(100),  -- Copied for easy filtering
    
    -- Application
    ats_application_id VARCHAR(255),  -- Application ID in ATS
    ats_job_id VARCHAR(255),  -- Job ID in ATS
    
    -- Candidate Status in ATS
    ats_stage VARCHAR(100),  -- new_lead, phone_screen, interview, offer, hired, rejected
    ats_status_detail TEXT,  -- Custom status from ATS
    
    -- HospRecruit Status
    hosprecruit_status VARCHAR(50),  -- screened, interviewing, offered, hired, rejected
    
    -- Sync Direction
    last_synced_from_ats TIMESTAMP,
    last_synced_to_ats TIMESTAMP,
    sync_direction VARCHAR(20),  -- inbound, outbound, bidirectional
    
    -- Score & Rating
    screening_score NUMERIC,  -- From HospRecruit AI screener
    interview_score NUMERIC,  -- From interview feedback
    ats_rating_stars INT,  -- 1-5 star rating in ATS
    
    -- Notes
    internal_notes TEXT,  -- HospRecruit internal notes
    ats_notes TEXT,  -- Notes from ATS
    
    -- Sync Metadata
    sync_hash VARCHAR(64),
    is_synced BOOLEAN DEFAULT FALSE,
    requires_resync BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(org_id, candidate_id, ats_config_id)
);

CREATE INDEX candidate_ats_mappings_org ON candidate_ats_mappings(org_id);
CREATE INDEX candidate_ats_mappings_candidate ON candidate_ats_mappings(candidate_id);
CREATE INDEX candidate_ats_mappings_not_synced ON candidate_ats_mappings(org_id, is_synced)
    WHERE is_synced = FALSE;

ALTER TABLE candidate_ats_mappings ENABLE ROW LEVEL SECURITY;
CREATE POLICY candidate_ats_mappings_org_isolation ON candidate_ats_mappings
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = candidate_ats_mappings.org_id));

-- ============================================================================
-- ATS Sync Logs: Audit trail of all sync operations
-- ============================================================================

CREATE TABLE ats_sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    ats_config_id UUID NOT NULL REFERENCES ats_configurations(id) ON DELETE CASCADE,
    
    -- Operation Details
    operation_type VARCHAR(50),  -- job_sync, candidate_push, status_update, webhook_received
    sync_direction VARCHAR(20),  -- inbound, outbound
    
    -- Objects
    job_id UUID REFERENCES jobs(id),
    candidate_id UUID REFERENCES candidates(id),
    ats_job_id VARCHAR(255),
    ats_candidate_id VARCHAR(255),
    
    -- Result
    status VARCHAR(50),  -- success, partial_success, failed, retrying
    error_message TEXT,
    error_code VARCHAR(50),
    
    -- Details
    records_processed INT,
    records_succeeded INT,
    records_failed INT,
    
    -- Payload Tracking
    payload_sent JSONB,  -- What we sent to ATS
    response_received JSONB,  -- What ATS returned
    
    -- Retry Info
    retry_count INT DEFAULT 0,
    next_retry_at TIMESTAMP,
    
    -- Performance
    duration_ms INT,  -- How long the sync took
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ats_sync_logs_org ON ats_sync_logs(org_id, created_at DESC);
CREATE INDEX ats_sync_logs_status ON ats_sync_logs(org_id, status) WHERE status != 'success';
CREATE INDEX ats_sync_logs_operations ON ats_sync_logs(org_id, operation_type);
CREATE INDEX ats_sync_logs_candidate_id ON ats_sync_logs(candidate_id) WHERE candidate_id IS NOT NULL;

ALTER TABLE ats_sync_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY ats_sync_logs_org_isolation ON ats_sync_logs
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = ats_sync_logs.org_id));

-- ============================================================================
-- ATS Events: Process webhooks from ATS platforms
-- ============================================================================

CREATE TABLE ats_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    ats_config_id UUID NOT NULL REFERENCES ats_configurations(id) ON DELETE CASCADE,
    
    -- Event Type
    event_type VARCHAR(100),  -- candidate.created, candidate.updated, job.closed, etc
    event_name VARCHAR(255),
    
    -- Source
    ats_provider VARCHAR(100),
    
    -- Objects
    ats_job_id VARCHAR(255),
    ats_candidate_id VARCHAR(255),
    ats_application_id VARCHAR(255),
    
    -- Event Details
    event_payload JSONB,
    
    -- Processing Status
    is_processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,
    processing_error TEXT,
    
    -- Webhook Details
    webhook_id VARCHAR(255),
    webhook_timestamp TIMESTAMP,
    webhook_signature_verified BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ats_events_org_unprocessed ON ats_events(org_id, is_processed)
    WHERE is_processed = FALSE;
CREATE INDEX ats_events_type ON ats_events(event_type);

ALTER TABLE ats_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY ats_events_org_isolation ON ats_events
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = ats_events.org_id));

-- ============================================================================
-- Trigger: Update candidate status mapping when candidate status changes
-- ============================================================================

CREATE OR REPLACE FUNCTION sync_candidate_to_ats_on_status_change()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.pipeline_stage IS DISTINCT FROM OLD.pipeline_stage THEN
        -- Mark all ATS mappings as needing resync
        UPDATE candidate_ats_mappings
        SET requires_resync = TRUE,
            updated_at = NOW()
        WHERE candidate_id = NEW.id;
        
        -- Log the change
        INSERT INTO ats_sync_logs (
            org_id,
            ats_config_id,
            operation_type,
            sync_direction,
            candidate_id,
            status,
            payload_sent,
            created_at
        )
        SELECT
            NEW.org_id,
            c.ats_config_id,
            'status_update',
            'outbound',
            NEW.id,
            'pending',
            jsonb_build_object(
                'candidate_id', NEW.id,
                'old_stage', OLD.pipeline_stage,
                'new_stage', NEW.pipeline_stage
            ),
            NOW()
        FROM candidate_ats_mappings c
        WHERE c.candidate_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER candidate_status_change_trigger
AFTER UPDATE ON candidates
FOR EACH ROW
WHEN (OLD.pipeline_stage IS DISTINCT FROM NEW.pipeline_stage)
EXECUTE FUNCTION sync_candidate_to_ats_on_status_change();

-- ============================================================================
-- Realtime: Enable for real-time ATS event processing
-- ============================================================================

ALTER PUBLICATION supabase_realtime ADD TABLE ats_configurations;
ALTER PUBLICATION supabase_realtime ADD TABLE ats_synced_jobs;
ALTER PUBLICATION supabase_realtime ADD TABLE ats_events;
