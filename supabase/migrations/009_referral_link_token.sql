-- ============================================================================
-- Migration 009 — Referral link_token column
-- Adds a cryptographically random, URL-safe token used in the public referral
-- link.  Kept separate from referral_code (the human-readable short code) so
-- the two can evolve independently.
-- ============================================================================

ALTER TABLE referrals ADD COLUMN IF NOT EXISTS link_token VARCHAR(50);

-- Unique index: token must be globally unique so two links can never resolve
-- to different referrals.  Nullable to stay backward-compatible with existing
-- rows that predate this migration.
CREATE UNIQUE INDEX IF NOT EXISTS referrals_link_token_uidx
    ON referrals(link_token)
    WHERE link_token IS NOT NULL;

-- Fast lookup when a candidate follows the link.
CREATE INDEX IF NOT EXISTS referrals_link_token_idx
    ON referrals(link_token);
