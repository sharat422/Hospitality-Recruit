-- Feature 04: Mobile-First Candidate Experience
-- Migration: Creates tables for mobile applications, video interviews, QR codes, and translations

CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES hiring_campaigns(id) ON DELETE SET NULL,
    source VARCHAR(30) DEFAULT 'DIRECT',
    source_ref TEXT,
    status VARCHAR(20) DEFAULT 'SUBMITTED',
    applied_via VARCHAR(20) DEFAULT 'MOBILE_WEB',
    completion_time_seconds INT,
    form_data JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS video_interviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id UUID REFERENCES applications(id) ON DELETE CASCADE,
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    interview_type VARCHAR(10) DEFAULT 'VIDEO',
    questions JSONB DEFAULT '[]',
    recording_url TEXT,
    thumbnail_url TEXT,
    duration_seconds INT DEFAULT 0,
    access_token UUID DEFAULT gen_random_uuid(),
    status VARCHAR(20) DEFAULT 'PENDING',
    recruiter_rating INT,
    recruiter_notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    reviewed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS video_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    time_limit_seconds INT DEFAULT 120,
    order_index INT DEFAULT 0,
    is_required BOOLEAN DEFAULT TRUE,
    category VARCHAR(50) DEFAULT 'general',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS qr_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(20) NOT NULL,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE SET NULL,
    campaign_id UUID REFERENCES hiring_campaigns(id) ON DELETE SET NULL,
    employee_id UUID REFERENCES users(id) ON DELETE SET NULL,
    short_code VARCHAR(10) UNIQUE NOT NULL,
    redirect_url TEXT NOT NULL,
    qr_image_url TEXT,
    scan_count INT DEFAULT 0,
    application_count INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS qr_scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    qr_code_id UUID REFERENCES qr_codes(id) ON DELETE CASCADE,
    scanned_at TIMESTAMP DEFAULT NOW(),
    user_agent TEXT,
    converted BOOLEAN DEFAULT FALSE,
    candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS language_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    language_code VARCHAR(10) NOT NULL,
    detected_from VARCHAR(20) DEFAULT 'BROWSER',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(candidate_id)
);

CREATE TABLE IF NOT EXISTS job_role_translations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    language_code VARCHAR(10) NOT NULL,
    translated_title TEXT,
    translated_description TEXT,
    translated_requirements TEXT,
    translated_benefits TEXT,
    translated_by VARCHAR(10) DEFAULT 'AI',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(job_role_id, language_code)
);

-- Seed video questions
INSERT INTO video_questions (job_role_id, question_text, time_limit_seconds, order_index, category) VALUES
(NULL, 'Tell us about yourself and why you want to work in hospitality.', 90, 1, 'general'),
(NULL, 'Describe a time you handled a difficult guest or customer situation.', 120, 2, 'general'),
(NULL, 'What does great customer service mean to you?', 60, 3, 'general'),
(NULL, 'What are your availability and when can you start?', 45, 4, 'general'),
(NULL, 'What cuisines and cooking techniques are you most experienced in?', 90, 5, 'kitchen'),
(NULL, 'Describe how you handle a busy service and maintain quality.', 120, 6, 'kitchen'),
(NULL, 'Tell us about a team you managed and how you developed them.', 120, 7, 'management'),
(NULL, 'How do you handle underperforming team members?', 90, 8, 'management')
ON CONFLICT DO NOTHING;

ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_interviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE qr_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE qr_scans ENABLE ROW LEVEL SECURITY;
ALTER TABLE language_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_role_translations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS applications_policy ON applications; CREATE POLICY applications_policy ON applications FOR ALL USING (true);
DROP POLICY IF EXISTS video_interviews_policy ON video_interviews; CREATE POLICY video_interviews_policy ON video_interviews FOR ALL USING (true);
DROP POLICY IF EXISTS video_questions_policy ON video_questions; CREATE POLICY video_questions_policy ON video_questions FOR ALL USING (true);
DROP POLICY IF EXISTS qr_codes_policy ON qr_codes; CREATE POLICY qr_codes_policy ON qr_codes FOR ALL USING (true);
DROP POLICY IF EXISTS qr_scans_policy ON qr_scans; CREATE POLICY qr_scans_policy ON qr_scans FOR ALL USING (true);
DROP POLICY IF EXISTS lang_pref_policy ON language_preferences; CREATE POLICY lang_pref_policy ON language_preferences FOR ALL USING (true);
DROP POLICY IF EXISTS translations_policy ON job_role_translations; CREATE POLICY translations_policy ON job_role_translations FOR ALL USING (true);
