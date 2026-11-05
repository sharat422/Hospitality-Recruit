/*
  Screening Chatbot Module Migration
  
  Creates tables and infrastructure for the AI Chatbot Screener module:
  - 24/7 conversational screening via SMS (Twilio)
  - Hospitality-specific questions (ServSafe, shift availability, guest scenarios)
  - Real-time scoring and candidate qualification
  - Bi-directional ATS sync (Merge.dev → Bullhorn/iCIMS)
  
  Pain Point Resolution:
  - Pain #1: Reduces screening admin time by 70% (automated multi-turn conversations)
  - Pain #2: Qualifies candidates 24/7 without recruiter intervention
  - ROI: $X per role (estimated 15-30 minutes saved per applicant)
*/

-- ============================================================================
-- Screening Sessions: 24/7 Conversational AI
-- ============================================================================

CREATE TABLE screening_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    candidate_id UUID NOT NULL REFERENCES candidates(id),
    job_id UUID NOT NULL REFERENCES jobs(id),
    session_status VARCHAR(50) DEFAULT 'in_progress', -- in_progress, completed, abandoned
    phone_number VARCHAR(20) NOT NULL,
    twilio_conversation_sid VARCHAR(255) UNIQUE, -- Twilio conversation tracking
    
    -- Screening metadata
    total_questions_asked INT DEFAULT 0,
    questions_answered INT DEFAULT 0,
    conversation_started_at TIMESTAMP DEFAULT NOW(),
    conversation_ended_at TIMESTAMP,
    total_duration_seconds INT,
    
    -- Scoring & qualification
    screening_score FLOAT CHECK (screening_score >= 0 AND screening_score <= 100),
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 100),
    qualified BOOLEAN DEFAULT FALSE,
    
    -- Extracted structured data
    candidate_answers JSONB DEFAULT '{}', -- {question_key: "user_response", ...}
    extracted_data JSONB DEFAULT '{}', -- {availability: [...], certifications: [...], experience: "X years", ...}
    red_flags JSONB DEFAULT '[]', -- array of concern flags
    
    -- Moderator review
    ai_recommendation VARCHAR(50) DEFAULT 'pending', -- recommended, review_needed, rejected
    recruiter_notes TEXT,
    recruiter_reviewed_at TIMESTAMP,
    recruiter_id UUID REFERENCES users(id),
    
    -- Integration tracking
    ats_synced BOOLEAN DEFAULT FALSE,
    ats_candidate_id VARCHAR(255), -- External ATS ID from Merge.dev
    last_ats_sync_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX screening_sessions_org ON screening_sessions(org_id);
CREATE INDEX screening_sessions_candidate ON screening_sessions(candidate_id);
CREATE INDEX screening_sessions_job ON screening_sessions(job_id);
CREATE INDEX screening_sessions_status ON screening_sessions(org_id, session_status);
CREATE INDEX screening_sessions_qualified ON screening_sessions(org_id, qualified);
CREATE INDEX screening_sessions_recommendation ON screening_sessions(org_id, ai_recommendation) WHERE ai_recommendation = 'review_needed';

ALTER TABLE screening_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY screening_sessions_org_isolation ON screening_sessions
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = screening_sessions.org_id));

-- Enable realtime for live dashboard updates
ALTER PUBLICATION supabase_realtime ADD TABLE screening_sessions;

-- ============================================================================
-- Screening Questions Library: Hospitality-Specific Q&A
-- ============================================================================

CREATE TABLE screening_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    question_key VARCHAR(100) NOT NULL, -- unique identifier (e.g., 'servsafe_cert', 'shift_availability', 'guest_scenario_1')
    question_text TEXT NOT NULL,
    question_category VARCHAR(50), -- certification, availability, scenario, experience, legal
    job_type VARCHAR(100), -- server, host, kitchen, manager, or NULL for all
    
    -- Scoring rules
    expected_response_pattern TEXT, -- regex or keyword list for auto-scoring
    scoring_weight FLOAT DEFAULT 1.0, -- importance multiplier (0.5-2.0)
    is_required_for_advancement BOOLEAN DEFAULT FALSE,
    
    -- Branching logic
    follow_up_logic JSONB DEFAULT '{}', -- {response_type: "question_key_to_ask_next", ...}
    
    -- Metadata
    question_order INT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(org_id, question_key)
);

CREATE INDEX screening_questions_org ON screening_questions(org_id, active);
CREATE INDEX screening_questions_category ON screening_questions(org_id, question_category);

ALTER TABLE screening_questions ENABLE ROW LEVEL SECURITY;
CREATE POLICY screening_questions_org_isolation ON screening_questions
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = screening_questions.org_id));

-- ============================================================================
-- Conversation Turn History: Multi-Turn Chat Log
-- ============================================================================

CREATE TABLE screening_conversation_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    screening_session_id UUID NOT NULL REFERENCES screening_sessions(id) ON DELETE CASCADE,
    candidate_id UUID NOT NULL REFERENCES candidates(id),
    
    -- Message flow
    turn_number INT NOT NULL, -- 1, 2, 3, ... sequential
    question_asked TEXT NOT NULL,
    question_key VARCHAR(100), -- reference to screening_questions.question_key
    candidate_response TEXT NOT NULL,
    ai_response TEXT, -- Claude's follow-up or confirmation
    
    -- Analysis
    response_sentiment VARCHAR(50), -- positive, neutral, negative
    response_confidence FLOAT CHECK (response_confidence >= 0 AND response_confidence <= 100), -- AI confidence in parsing response
    extracted_value JSONB DEFAULT '{}', -- parsed structured data from response
    
    -- Scoring contribution
    turn_score FLOAT DEFAULT 0, -- contribution to overall screening_score (0-100)
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX screening_turns_session ON screening_conversation_turns(screening_session_id);
CREATE INDEX screening_turns_candidate ON screening_conversation_turns(candidate_id);
CREATE INDEX screening_turns_org ON screening_conversation_turns(org_id);

ALTER TABLE screening_conversation_turns ENABLE ROW LEVEL SECURITY;
CREATE POLICY screening_turns_org_isolation ON screening_conversation_turns
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = screening_conversation_turns.org_id));

-- ============================================================================
-- ATS Sync Logs: Merge.dev Bi-Directional Integration
-- ============================================================================

CREATE TABLE ats_sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    candidate_id UUID REFERENCES candidates(id),
    screening_session_id UUID REFERENCES screening_sessions(id),
    
    -- Integration direction
    sync_direction VARCHAR(20), -- outbound (HospRecruit → ATS), inbound (ATS → HospRecruit)
    sync_action VARCHAR(50), -- create, update, archive
    
    -- Merge.dev specifics
    ats_provider VARCHAR(100), -- bullhorn, icims, greenhouse, etc
    external_candidate_id VARCHAR(255), -- ID in external ATS
    external_job_id VARCHAR(255),
    merge_dev_request_id VARCHAR(255), -- Merge.dev transaction ID for idempotency
    
    -- Sync payload
    payload_sent JSONB,
    response_received JSONB,
    
    -- Status
    status VARCHAR(50) DEFAULT 'pending', -- pending, success, failed, retry
    error_message TEXT,
    retry_count INT DEFAULT 0,
    last_retry_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ats_sync_logs_org ON ats_sync_logs(org_id, created_at DESC);
CREATE INDEX ats_sync_logs_candidate ON ats_sync_logs(candidate_id);
CREATE INDEX ats_sync_logs_status ON ats_sync_logs(org_id, status) WHERE status != 'success';

ALTER TABLE ats_sync_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY ats_sync_logs_org_isolation ON ats_sync_logs
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = ats_sync_logs.org_id));

-- ============================================================================
-- Candidate Extended Fields for Screening Chatbot
-- ============================================================================

-- Note: The candidates table already has screening_result JSONB and availability JSONB
-- This section documents the expected structure:
--
-- candidates.screening_result = {
--   "ai_score": 85.5,
--   "confidence_score": 92.3,
--   "qualified": true,
--   "key_qualifications": ["ServSafe certified", "3+ years server experience"],
--   "red_flags": ["No weekend availability", "New to North Carolina"],
--   "recommended_next_step": "send_offer",
--   "screening_session_id": "uuid",
--   "screened_at": "2025-04-09T14:30:00Z",
--   "ai_model": "claude-3-5-sonnet-20241022",
--   "screening_method": "sms_chatbot"
-- }
--
-- candidates.availability = [
--   {"day": "Monday", "start": "09:00", "end": "17:00"},
--   {"day": "Friday", "start": "17:00", "end": "22:00"}
-- ]

-- ============================================================================
-- Triggers: Automatic Updates & Sync Triggers
-- ============================================================================

-- Trigger: When screening_session.qualified changes, update candidates.qualified
CREATE OR REPLACE FUNCTION update_candidate_qualified_from_session()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE candidates 
    SET 
        qualified = NEW.qualified,
        screening_result = jsonb_set(
            screening_result,
            '{ai_score}',
            to_jsonb(NEW.screening_score)
        ) || jsonb_set(
            '{}',
            '{screening_session_id}',
            to_jsonb(NEW.id::text)
        ) || jsonb_set(
            '{}',
            '{screened_at}',
            to_jsonb(NEW.updated_at::text)
        ),
        updated_at = NOW()
    WHERE id = NEW.candidate_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER screening_session_update_candidate
AFTER UPDATE ON screening_sessions
FOR EACH ROW
WHEN (OLD.qualified IS DISTINCT FROM NEW.qualified OR OLD.screening_score IS DISTINCT FROM NEW.screening_score)
EXECUTE FUNCTION update_candidate_qualified_from_session();

-- Trigger: When screening_session is completed, trigger ATS sync
CREATE OR REPLACE FUNCTION trigger_ats_sync_on_session_complete()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.session_status = 'completed' AND OLD.session_status != 'completed' AND NEW.qualified = TRUE THEN
        -- Insert pending ATS sync log (will be processed by background job)
        INSERT INTO ats_sync_logs (
            org_id,
            candidate_id,
            screening_session_id,
            sync_direction,
            sync_action,
            status,
            created_at
        ) VALUES (
            NEW.org_id,
            NEW.candidate_id,
            NEW.id,
            'outbound',
            'create',
            'pending',
            NOW()
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER screening_session_complete_trigger_ats_sync
AFTER UPDATE ON screening_sessions
FOR EACH ROW
EXECUTE FUNCTION trigger_ats_sync_on_session_complete();

-- ============================================================================
-- Realtime Configuration
-- ============================================================================

-- Already added screening_sessions to realtime above
-- Add more tables for recruiter dashboard real-time updates
ALTER PUBLICATION supabase_realtime ADD TABLE screening_conversation_turns;
ALTER PUBLICATION supabase_realtime ADD TABLE ats_sync_logs;

-- ============================================================================
-- Initial Data: Default Hospitality Screening Questions
-- ============================================================================

-- This data will be inserted via a separate script or frontend admin panel
-- Example questions are documented in the application code

-- Note: Questions are organization-specific and should be seeded 
-- during onboarding. The screener service will load these dynamically
-- based on org_id and job_type for flexible hospitality screening.
