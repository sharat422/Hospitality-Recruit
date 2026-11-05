-- ============================================================================
-- Feature 05 India: Employee Referral Program Engine
-- Adds: referral_programs, employee_upi_details, referral_campaigns,
--       referral_badges, employee_badges
-- Alters: referrals (India-specific columns)
-- Does NOT modify: users, jobs, candidates, applications, properties
-- ============================================================================

-- ----------------------------------------------------------------------------
-- referral_programs — structured programs (per org, INR currency)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS referral_programs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name                VARCHAR(255) NOT NULL,
    description         TEXT,
    is_active           BOOLEAN DEFAULT TRUE,
    valid_from          TIMESTAMP,
    valid_to            TIMESTAMP,
    reward_on_apply     FLOAT DEFAULT 0,
    reward_on_hire      FLOAT DEFAULT 5000,
    retention_bonus     FLOAT DEFAULT 2000,
    retention_days      INT DEFAULT 90,
    currency            VARCHAR(5) DEFAULT 'INR',
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS referral_programs_active_idx
    ON referral_programs(is_active, valid_from, valid_to);

-- ----------------------------------------------------------------------------
-- employee_upi_details — UPI / bank account for INR payouts
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employee_upi_details (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    upi_id              VARCHAR(100),
    bank_account_number VARCHAR(20),
    bank_ifsc           VARCHAR(15),
    bank_name           VARCHAR(100),
    account_holder_name VARCHAR(200),
    is_verified         BOOLEAN DEFAULT FALSE,
    verification_method VARCHAR(20) DEFAULT 'MANUAL',
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id)
);

-- ----------------------------------------------------------------------------
-- referral_campaigns — festive bonus campaigns
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS referral_campaigns (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name             VARCHAR(200) NOT NULL,
    festival_name    VARCHAR(100),
    start_date       TIMESTAMP NOT NULL,
    end_date         TIMESTAMP NOT NULL,
    bonus_multiplier FLOAT DEFAULT 1.0,
    bonus_flat       FLOAT DEFAULT 0,
    whatsapp_template VARCHAR(500),
    banner_text      VARCHAR(500),
    banner_color     VARCHAR(7) DEFAULT '#FF6B00',
    is_active        BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS referral_campaigns_active_idx
    ON referral_campaigns(is_active, start_date, end_date);

-- ----------------------------------------------------------------------------
-- referral_badges — badge catalog
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS referral_badges (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           VARCHAR(100) NOT NULL UNIQUE,
    description    TEXT,
    icon           VARCHAR(50) DEFAULT '🏅',
    tier           VARCHAR(20) DEFAULT 'BRONZE',
    required_hires INT DEFAULT 1,
    reward_bonus   FLOAT DEFAULT 0,
    created_at     TIMESTAMP DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- employee_badges — awards per user
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employee_badges (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    badge_id                UUID NOT NULL REFERENCES referral_badges(id) ON DELETE CASCADE,
    earned_at               TIMESTAMP DEFAULT NOW(),
    referral_count_at_award INT DEFAULT 0,
    notified_via_whatsapp   BOOLEAN DEFAULT FALSE,
    UNIQUE(user_id, badge_id)
);

CREATE INDEX IF NOT EXISTS employee_badges_user_idx ON employee_badges(user_id);

-- ----------------------------------------------------------------------------
-- Extend existing referrals table with India-specific columns
-- ----------------------------------------------------------------------------
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS program_id             UUID REFERENCES referral_programs(id);
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS campaign_id            UUID REFERENCES referral_campaigns(id);
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS whatsapp_shared        BOOLEAN DEFAULT FALSE;
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS whatsapp_shared_at     TIMESTAMP;
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS hire_date              TIMESTAMP;
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS retention_bonus_amount FLOAT DEFAULT 0;
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS retention_bonus_status VARCHAR(20) DEFAULT 'NOT_ELIGIBLE';
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS retention_check_date   TIMESTAMP;
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS upi_payment_ref        VARCHAR(255);
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS currency               VARCHAR(5) DEFAULT 'INR';

-- ----------------------------------------------------------------------------
-- RLS
-- ----------------------------------------------------------------------------
ALTER TABLE referral_programs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_upi_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE referral_campaigns   ENABLE ROW LEVEL SECURITY;
ALTER TABLE referral_badges      ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_badges      ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS referral_programs_policy    ON referral_programs;
CREATE POLICY referral_programs_policy    ON referral_programs    FOR ALL USING (true);

DROP POLICY IF EXISTS employee_upi_policy         ON employee_upi_details;
CREATE POLICY employee_upi_policy         ON employee_upi_details FOR ALL USING (true);

DROP POLICY IF EXISTS referral_campaigns_policy   ON referral_campaigns;
CREATE POLICY referral_campaigns_policy   ON referral_campaigns   FOR ALL USING (true);

DROP POLICY IF EXISTS referral_badges_policy      ON referral_badges;
CREATE POLICY referral_badges_policy      ON referral_badges      FOR SELECT USING (true);

DROP POLICY IF EXISTS employee_badges_policy      ON employee_badges;
CREATE POLICY employee_badges_policy      ON employee_badges      FOR ALL USING (true);

-- ----------------------------------------------------------------------------
-- Seed badge catalog
-- ----------------------------------------------------------------------------
INSERT INTO referral_badges (name, description, icon, tier, required_hires, reward_bonus) VALUES
('First Hire',      'Got your first candidate hired!',                  '🌟', 'BRONZE',    1,   500),
('Star Referrer',   'Referred 3 successful hires',                     '⭐', 'SILVER',    3,  1500),
('Hiring Champion', 'Referred 5 successful hires',                     '🏆', 'GOLD',      5,  3000),
('Talent Magnet',   'Referred 10 successful hires',                    '🧲', 'GOLD',     10,  5000),
('Loyalty Ace',     'Referred 20 hires who stayed 90+ days',           '💎', 'PLATINUM', 20, 10000),
('Festive Star',    'Referred a hire during a festive campaign',        '🎉', 'SILVER',    1,  1000),
('WhatsApp Hero',   'Shared 5 or more referrals via WhatsApp',         '📱', 'BRONZE',    5,   500),
('Early Bird',      'Referred within 7 days of joining the program',   '🐦', 'BRONZE',    1,   250)
ON CONFLICT (name) DO NOTHING;

-- ----------------------------------------------------------------------------
-- Seed festive campaigns 2025-2027
-- ----------------------------------------------------------------------------
INSERT INTO referral_campaigns
    (name, festival_name, start_date, end_date, bonus_multiplier, bonus_flat, banner_text, banner_color)
VALUES
('Diwali Dhamaka 2025',     'DIWALI',          '2025-10-15', '2025-11-05', 2.0,  1000, '🪔 Diwali Special! Earn 2x rewards + ₹1,000 bonus on every hire!', '#FF6B00'),
('New Year Bonanza 2026',   'NEW_YEAR',         '2025-12-26', '2026-01-05', 1.5,   500, '🎆 New Year, New Hires! 1.5x rewards + ₹500 bonus!',               '#4F46E5'),
('Holi Hiring Fest 2026',   'HOLI',             '2026-03-01', '2026-03-30', 1.75,  750, '🎨 Holi Hiring Fest! 1.75x rewards on all hires!',                 '#EC4899'),
('Eid ul-Fitr Boost 2026',  'EID',              '2026-03-20', '2026-04-05', 1.5,   500, '🌙 Eid Mubarak! 1.5x referral bonuses this Eid!',                  '#10B981'),
('Independence Day 2026',   'INDEPENDENCE_DAY', '2026-08-01', '2026-08-20', 1.5,     0, '🇮🇳 Independence Day Sprint! 1.5x referral rewards!',             '#138808'),
('Diwali Dhamaka 2026',     'DIWALI',           '2026-10-15', '2026-11-05', 2.0,  1000, '🪔 Diwali 2026! Earn 2x rewards + ₹1,000 bonus on every hire!',    '#FF6B00'),
('Christmas Bonanza 2026',  'CHRISTMAS',        '2026-12-20', '2027-01-05', 1.5,   500, '🎄 Year-End Referral Bonanza! 1.5x rewards!',                      '#DC2626')
ON CONFLICT DO NOTHING;
