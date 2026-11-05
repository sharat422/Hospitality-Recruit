CREATE TABLE IF NOT EXISTS referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id UUID REFERENCES users(id) ON DELETE CASCADE,
    referrer_email VARCHAR(255),
    candidate_email VARCHAR(255),
    candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    referral_code VARCHAR(20) UNIQUE NOT NULL,
    status VARCHAR(20) DEFAULT 'PENDING',
    -- PENDING → APPLIED → SHORTLISTED → HIRED → REWARDED
    reward_amount FLOAT DEFAULT 0,
    reward_status VARCHAR(20) DEFAULT 'NOT_EARNED',
    -- NOT_EARNED → EARNED → PAID
    reward_paid_at TIMESTAMP,
    application_id UUID,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(referrer_id, candidate_email, job_role_id)
);

CREATE TABLE IF NOT EXISTS referral_rewards_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    reward_on_apply FLOAT DEFAULT 0,
    reward_on_hire FLOAT DEFAULT 50,
    reward_currency VARCHAR(5) DEFAULT 'USD',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS referrals_code_idx ON referrals(referral_code);
CREATE INDEX IF NOT EXISTS referrals_referrer_idx ON referrals(referrer_id);

ALTER TABLE referrals ENABLE ROW LEVEL SECURITY;
ALTER TABLE referral_rewards_config ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS referrals_policy ON referrals;
CREATE POLICY referrals_policy ON referrals FOR ALL USING (true);
DROP POLICY IF EXISTS rewards_config_policy ON referral_rewards_config;
CREATE POLICY rewards_config_policy ON referral_rewards_config FOR ALL USING (true);
