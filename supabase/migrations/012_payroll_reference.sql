-- ============================================================================
-- Migration 012 — Payroll adapter sync columns on referrals
--
-- Added by the payroll adapter pattern so that after a successful sync
-- to greytHR / Keka / Darwinbox / Zoho Payroll the provider's transaction
-- reference is stored alongside the referral row for auditing.
-- ============================================================================

ALTER TABLE referrals
    ADD COLUMN IF NOT EXISTS payroll_reference  VARCHAR(100),
    ADD COLUMN IF NOT EXISTS payroll_provider   VARCHAR(30),
    ADD COLUMN IF NOT EXISTS payroll_synced_at  TIMESTAMP;

-- Auditing index: find all referrals synced to a given provider
CREATE INDEX IF NOT EXISTS referrals_payroll_provider_idx
    ON referrals(payroll_provider)
    WHERE payroll_provider IS NOT NULL;
