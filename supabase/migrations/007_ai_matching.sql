-- Skills taxonomy
CREATE TABLE IF NOT EXISTS skills_taxonomy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category VARCHAR(100) NOT NULL,
    skill VARCHAR(255) NOT NULL,
    aliases TEXT[] DEFAULT '{}',
    cross_industry_source VARCHAR(100),
    weight_multiplier FLOAT DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Extended candidates table (alter if exists, add columns)
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS resume_url TEXT;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS parsed_skills JSONB DEFAULT '{}';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS work_history JSONB DEFAULT '[]';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS soft_skills_score FLOAT DEFAULT 0;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS years_experience INT DEFAULT 0;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'DIRECT';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP DEFAULT NOW();
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS languages TEXT[] DEFAULT '{}';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS certifications TEXT[] DEFAULT '{}';

-- Job roles
CREATE TABLE IF NOT EXISTS job_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id),
    title VARCHAR(255) NOT NULL,
    department VARCHAR(100),
    property_type VARCHAR(50) DEFAULT 'hotel',
    required_skills JSONB DEFAULT '[]',
    preferred_skills JSONB DEFAULT '[]',
    salary_min INT,
    salary_max INT,
    location VARCHAR(255),
    description TEXT,
    seniority_level VARCHAR(50) DEFAULT 'mid',
    work_pattern VARCHAR(50) DEFAULT 'full-time',
    is_active BOOLEAN DEFAULT TRUE,
    auto_reactivate BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Candidate matches
CREATE TABLE IF NOT EXISTS candidate_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    overall_score FLOAT DEFAULT 0,
    skill_match_score FLOAT DEFAULT 0,
    soft_skill_score FLOAT DEFAULT 0,
    experience_score FLOAT DEFAULT 0,
    cross_industry_score FLOAT DEFAULT 0,
    availability_score FLOAT DEFAULT 0,
    match_reasoning TEXT,
    reactivation_sent BOOLEAN DEFAULT FALSE,
    reactivation_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(candidate_id, job_role_id)
);

-- Generated JDs
CREATE TABLE IF NOT EXISTS job_descriptions_generated (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    prompt_inputs JSONB DEFAULT '{}',
    generated_jd TEXT,
    salary_suggestion_min INT,
    salary_suggestion_max INT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Seed skill taxonomy
INSERT INTO skills_taxonomy (category, skill, aliases, cross_industry_source, weight_multiplier) VALUES
('front_of_house','table service','{"waiter","waitress","food service"}',NULL,1.0),
('front_of_house','reservation management','{"bookings","OpenTable","SevenRooms"}',NULL,1.0),
('front_of_house','POS systems','{"point of sale","Lightspeed","Toast"}',NULL,1.0),
('front_of_house','upselling','{"sales","revenue generation"}',NULL,1.0),
('front_of_house','customer complaint handling','{"conflict resolution","service recovery"}',NULL,1.0),
('back_of_house','food prep','{"mise en place","food preparation"}',NULL,1.0),
('back_of_house','HACCP','{"food safety","food hygiene"}',NULL,1.0),
('back_of_house','allergen awareness','{"allergen management"}',NULL,1.0),
('housekeeping','room turnover','{"room cleaning","room change"}',NULL,1.0),
('housekeeping','linen management','{"laundry","linen"}',NULL,1.0),
('front_desk','check-in/check-out','{"guest arrival","reception"}',NULL,1.0),
('front_desk','Opera PMS','{"Opera","property management"}',NULL,1.0),
('front_desk','guest relations','{"guest experience","customer relations"}',NULL,1.0),
('cross_industry_transferable','customer service','{"client service","customer care"}','retail',0.7),
('cross_industry_transferable','cash handling','{"till","register","payments"}','retail',0.7),
('cross_industry_transferable','empathy','{"compassion","patient care"}','healthcare',0.65),
('cross_industry_transferable','shift work','{"rotational shifts","flexible hours"}','healthcare',0.65),
('cross_industry_transferable','event coordination','{"event planning","event management"}','events',0.75),
('cross_industry_transferable','vendor liaison','{"supplier management","procurement"}','events',0.7)
ON CONFLICT DO NOTHING;

ALTER TABLE job_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidate_matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_descriptions_generated ENABLE ROW LEVEL SECURITY;
ALTER TABLE skills_taxonomy ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS job_roles_org ON job_roles;
CREATE POLICY job_roles_org ON job_roles USING (
    org_id IN (SELECT org_id FROM users WHERE id = auth.uid())
);
DROP POLICY IF EXISTS candidate_matches_org ON candidate_matches;
CREATE POLICY candidate_matches_org ON candidate_matches USING (
    candidate_id IN (SELECT id FROM candidates WHERE org_id IN (SELECT org_id FROM users WHERE id = auth.uid()))
);
DROP POLICY IF EXISTS taxonomy_read ON skills_taxonomy;
CREATE POLICY taxonomy_read ON skills_taxonomy FOR SELECT USING (true);
