CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    recruiter_id UUID REFERENCES users(id) ON DELETE SET NULL,
    channel VARCHAR(20) DEFAULT 'SMS',
    status VARCHAR(20) DEFAULT 'ACTIVE',
    last_message_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    sender_type VARCHAR(20) NOT NULL,
    sender_id UUID,
    body TEXT NOT NULL,
    channel VARCHAR(20) DEFAULT 'SMS',
    status VARCHAR(20) DEFAULT 'SENT',
    twilio_sid TEXT,
    sent_at TIMESTAMP DEFAULT NOW(),
    read_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS drip_sequences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    trigger_event VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS drip_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sequence_id UUID REFERENCES drip_sequences(id) ON DELETE CASCADE,
    step_order INT NOT NULL,
    delay_hours INT NOT NULL DEFAULT 0,
    channel VARCHAR(20) DEFAULT 'SMS',
    message_template TEXT NOT NULL,
    is_ai_personalized BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS drip_enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    sequence_id UUID REFERENCES drip_sequences(id) ON DELETE CASCADE,
    current_step INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'ACTIVE',
    enrolled_at TIMESTAMP DEFAULT NOW(),
    next_send_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ghosting_risk_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    risk_score FLOAT DEFAULT 0,
    risk_level VARCHAR(20) DEFAULT 'LOW',
    risk_signals JSONB DEFAULT '[]',
    last_calculated_at TIMESTAMP DEFAULT NOW(),
    alert_sent BOOLEAN DEFAULT FALSE,
    alert_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(candidate_id, job_role_id)
);

CREATE TABLE IF NOT EXISTS interview_slots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    recruiter_id UUID REFERENCES users(id) ON DELETE CASCADE,
    candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'AVAILABLE',
    confirmation_token UUID DEFAULT gen_random_uuid(),
    google_event_id TEXT,
    outlook_event_id TEXT,
    reminder_24h_sent BOOLEAN DEFAULT FALSE,
    reminder_1h_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nps_surveys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    stage VARCHAR(30) NOT NULL,
    score INT,
    feedback_text TEXT,
    sent_at TIMESTAMP DEFAULT NOW(),
    responded_at TIMESTAMP,
    response_token UUID DEFAULT gen_random_uuid(),
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE candidates ADD COLUMN IF NOT EXISTS tracking_token UUID DEFAULT gen_random_uuid();
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS pipeline_stage VARCHAR(50) DEFAULT 'APPLIED';

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE drip_sequences ENABLE ROW LEVEL SECURITY;
ALTER TABLE drip_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE drip_enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE ghosting_risk_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE interview_slots ENABLE ROW LEVEL SECURITY;
ALTER TABLE nps_surveys ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS conversations_policy ON conversations;
CREATE POLICY conversations_policy ON conversations FOR ALL USING (true);
DROP POLICY IF EXISTS messages_policy ON messages;
CREATE POLICY messages_policy ON messages FOR ALL USING (true);
DROP POLICY IF EXISTS drip_seq_policy ON drip_sequences;
CREATE POLICY drip_seq_policy ON drip_sequences FOR ALL USING (true);
DROP POLICY IF EXISTS drip_steps_policy ON drip_steps;
CREATE POLICY drip_steps_policy ON drip_steps FOR ALL USING (true);
DROP POLICY IF EXISTS drip_enroll_policy ON drip_enrollments;
CREATE POLICY drip_enroll_policy ON drip_enrollments FOR ALL USING (true);
DROP POLICY IF EXISTS ghosting_policy ON ghosting_risk_scores;
CREATE POLICY ghosting_policy ON ghosting_risk_scores FOR ALL USING (true);
DROP POLICY IF EXISTS interview_slots_policy ON interview_slots;
CREATE POLICY interview_slots_policy ON interview_slots FOR ALL USING (true);
DROP POLICY IF EXISTS nps_policy ON nps_surveys;
CREATE POLICY nps_policy ON nps_surveys FOR ALL USING (true);

INSERT INTO drip_sequences (name, trigger_event, is_active) VALUES
('Post-Offer Pre-Start Nurture', 'OFFER_SENT', true),
('Post-Interview Follow-Up', 'INTERVIEW_SCHEDULED', true),
('Empathetic Rejection', 'REJECTED', true)
ON CONFLICT DO NOTHING;
