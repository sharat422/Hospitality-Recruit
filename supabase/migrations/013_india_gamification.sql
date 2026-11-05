-- ============================================================================
-- Migration 013 — India Referral Gamification
--
-- Adds:
--   referral_badges.milestone_type  — 'hired_count' | 'whatsapp_count'
--   referral_badges.name_en         — English name (for bilingual badge cards)
--   referral_badges.name_hi         — Hindi name
--   referral_badges.description_hi  — Hindi description on badge card
--   Six Hindi-named badge entries   — पहला कदम, टीम बिल्डर, टैलेंट हंटर,
--                                     स्टार रेफरर, Legend, दोस्त बनाओ
--   ONAM 2026 & 2027 campaigns
--   PONGAL 2026 & 2027 campaigns
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Extend referral_badges with bilingual + milestone-type columns
-- ----------------------------------------------------------------------------

ALTER TABLE referral_badges
    ADD COLUMN IF NOT EXISTS milestone_type  VARCHAR(20) DEFAULT 'hired_count',
    ADD COLUMN IF NOT EXISTS name_en         VARCHAR(100),
    ADD COLUMN IF NOT EXISTS name_hi         VARCHAR(100),
    ADD COLUMN IF NOT EXISTS description_hi  TEXT;

-- Backfill existing English badges so name_en matches name
UPDATE referral_badges SET name_en = name WHERE name_en IS NULL;

-- ----------------------------------------------------------------------------
-- Hindi badge catalog  (unique names in Devanagari — no conflict with English)
-- ----------------------------------------------------------------------------

INSERT INTO referral_badges
    (name, name_en, name_hi, description, description_hi,
     icon, tier, required_hires, reward_bonus, milestone_type)
VALUES
(
    'पहला कदम', 'First Step', 'पहला कदम',
    'Got your very first referral hired!',
    'पहला referral hire कराया! आपका पहला कदम। 🌱',
    '🌱', 'BRONZE', 1, 500, 'hired_count'
),
(
    'टीम बिल्डर', 'Team Builder', 'टीम बिल्डर',
    'Referred 3 candidates who got hired.',
    '3 candidates hire कराए — आप एक अच्छे टीम प्लेयर हैं! 🤝',
    '🤝', 'SILVER', 3, 1500, 'hired_count'
),
(
    'टैलेंट हंटर', 'Talent Hunter', 'टैलेंट हंटर',
    'Referred 5 candidates who got hired.',
    '5 candidates hire कराए — talent ढूंढने में माहिर! 🎯',
    '🎯', 'GOLD', 5, 3000, 'hired_count'
),
(
    'स्टार रेफरर', 'Star Referrer', 'स्टार रेफरर',
    'Referred 10 candidates who got hired.',
    '10 candidates hire कराए — आप हमारे Star हैं! ⭐',
    '⭐', 'GOLD', 10, 5000, 'hired_count'
),
(
    'Legend', 'Legend', 'Legend',
    'Referred 20 candidates who got hired. You are a legend!',
    '20 candidates hire कराए — आप एक Legend हैं! 💎',
    '💎', 'PLATINUM', 20, 10000, 'hired_count'
),
(
    'दोस्त बनाओ', 'Make Friends', 'दोस्त बनाओ',
    'Shared 5 referrals via WhatsApp.',
    'WhatsApp से 5 referral share किए — दोस्त बनाओ, साथ बढ़ो! 📱',
    '📱', 'BRONZE', 5, 500, 'whatsapp_count'
)
ON CONFLICT (name) DO NOTHING;

-- ----------------------------------------------------------------------------
-- Onam campaigns (Kerala harvest festival — late August/early September)
-- ----------------------------------------------------------------------------

INSERT INTO referral_campaigns
    (name, festival_name, start_date, end_date,
     bonus_multiplier, bonus_flat, banner_text, banner_color)
VALUES
(
    'Onam Bonanza 2026', 'ONAM',
    '2026-08-22', '2026-09-06',
    1.75, 750,
    '🌸 Onam Special! 1.75x referral rewards + ₹750 bonus on every hire!',
    '#F59E0B'
),
(
    'Onam Bonanza 2027', 'ONAM',
    '2027-08-12', '2027-08-27',
    1.75, 750,
    '🌸 Onam 2027! 1.75x rewards + ₹750 bonus — refer and celebrate!',
    '#F59E0B'
)
ON CONFLICT DO NOTHING;

-- ----------------------------------------------------------------------------
-- Pongal campaigns (Tamil Nadu harvest festival — January 14-17)
-- ----------------------------------------------------------------------------

INSERT INTO referral_campaigns
    (name, festival_name, start_date, end_date,
     bonus_multiplier, bonus_flat, banner_text, banner_color)
VALUES
(
    'Pongal Harvest 2026', 'PONGAL',
    '2026-01-13', '2026-01-17',
    1.5, 500,
    '🌾 Pongal Special! 1.5x referral rewards + ₹500 bonus — Pongalo Pongal!',
    '#16A34A'
),
(
    'Pongal Harvest 2027', 'PONGAL',
    '2027-01-13', '2027-01-17',
    1.5, 500,
    '🌾 Pongal 2027! 1.5x rewards + ₹500 bonus — नई फसल, नई कमाई!',
    '#16A34A'
)
ON CONFLICT DO NOTHING;
