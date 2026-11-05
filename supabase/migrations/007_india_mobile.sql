CREATE TABLE IF NOT EXISTS candidate_otp_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(15) NOT NULL,
    otp_hash TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS india_states_cities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_name VARCHAR(100) NOT NULL,
    state_code VARCHAR(5) NOT NULL,
    city_name VARCHAR(100) NOT NULL,
    is_major_city BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS whatsapp_bot_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(15) NOT NULL,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    session_data JSONB DEFAULT '{}',
    step VARCHAR(30) DEFAULT 'NAME',
    status VARCHAR(20) DEFAULT 'IN_PROGRESS',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE candidates ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(10) DEFAULT 'hi';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS current_ctc FLOAT;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS expected_ctc FLOAT;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS notice_period VARCHAR(20);
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS state VARCHAR(100);
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS city VARCHAR(100);
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS has_gov_id BOOLEAN DEFAULT FALSE;

-- Update job_role_translations to support Indian languages
ALTER TABLE job_role_translations ADD COLUMN IF NOT EXISTS script VARCHAR(30);

ALTER TABLE candidate_otp_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE india_states_cities ENABLE ROW LEVEL SECURITY;
ALTER TABLE whatsapp_bot_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS otp_policy ON candidate_otp_sessions;
CREATE POLICY otp_policy ON candidate_otp_sessions FOR ALL USING (true);
DROP POLICY IF EXISTS states_policy ON india_states_cities;
CREATE POLICY states_policy ON india_states_cities FOR SELECT USING (true);
DROP POLICY IF EXISTS wa_bot_policy ON whatsapp_bot_sessions;
CREATE POLICY wa_bot_policy ON whatsapp_bot_sessions FOR ALL USING (true);

-- Seed major Indian states and cities
INSERT INTO india_states_cities (state_name, state_code, city_name, is_major_city) VALUES
('Maharashtra', 'MH', 'Mumbai', true), ('Maharashtra', 'MH', 'Pune', true), ('Maharashtra', 'MH', 'Nashik', false),
('Delhi', 'DL', 'New Delhi', true), ('Delhi', 'DL', 'Noida', true), ('Delhi', 'DL', 'Gurugram', true),
('Karnataka', 'KA', 'Bengaluru', true), ('Karnataka', 'KA', 'Mysuru', false), ('Karnataka', 'KA', 'Mangaluru', false),
('Tamil Nadu', 'TN', 'Chennai', true), ('Tamil Nadu', 'TN', 'Coimbatore', false), ('Tamil Nadu', 'TN', 'Madurai', false),
('Rajasthan', 'RJ', 'Jaipur', true), ('Rajasthan', 'RJ', 'Udaipur', true), ('Rajasthan', 'RJ', 'Jodhpur', false),
('Goa', 'GA', 'Panaji', true), ('Goa', 'GA', 'Margao', false), ('Goa', 'GA', 'Vasco da Gama', false),
('Uttar Pradesh', 'UP', 'Lucknow', true), ('Uttar Pradesh', 'UP', 'Agra', true), ('Uttar Pradesh', 'UP', 'Varanasi', false),
('West Bengal', 'WB', 'Kolkata', true), ('West Bengal', 'WB', 'Siliguri', false),
('Telangana', 'TS', 'Hyderabad', true), ('Telangana', 'TS', 'Warangal', false),
('Kerala', 'KL', 'Kochi', true), ('Kerala', 'KL', 'Thiruvananthapuram', true), ('Kerala', 'KL', 'Kozhikode', false),
('Gujarat', 'GJ', 'Ahmedabad', true), ('Gujarat', 'GJ', 'Surat', false), ('Gujarat', 'GJ', 'Vadodara', false),
('Punjab', 'PB', 'Chandigarh', true), ('Punjab', 'PB', 'Amritsar', false), ('Punjab', 'PB', 'Ludhiana', false),
('Himachal Pradesh', 'HP', 'Shimla', true), ('Himachal Pradesh', 'HP', 'Manali', true), ('Himachal Pradesh', 'HP', 'Dharamshala', true),
('Uttarakhand', 'UK', 'Dehradun', true), ('Uttarakhand', 'UK', 'Mussoorie', true), ('Uttarakhand', 'UK', 'Rishikesh', true)
ON CONFLICT DO NOTHING;
