-- ============================================================================
-- Migration 010 — Razorpay payout tracking columns
--
-- Adds:
--   referrals.razorpay_payout_id   — Razorpay payout entity ID (pout_xxx)
--   referrals.payout_status        — PROCESSING | PAID | FAILED | NOT_INITIATED
--   employee_upi_details.razorpay_contact_id      — reuse across payouts
--   employee_upi_details.razorpay_fund_account_id — reuse across payouts
-- ============================================================================

-- Payout tracking on the referral row
ALTER TABLE referrals
    ADD COLUMN IF NOT EXISTS razorpay_payout_id VARCHAR(50),
    ADD COLUMN IF NOT EXISTS payout_status VARCHAR(20) DEFAULT 'NOT_INITIATED';

-- Fast lookup when a webhook arrives with a payout ID
CREATE INDEX IF NOT EXISTS referrals_razorpay_payout_idx
    ON referrals(razorpay_payout_id)
    WHERE razorpay_payout_id IS NOT NULL;

-- Cache the Razorpay Contact + FundAccount so we don't recreate them
-- every time the same employee receives a bonus
ALTER TABLE employee_upi_details
    ADD COLUMN IF NOT EXISTS razorpay_contact_id      VARCHAR(50),
    ADD COLUMN IF NOT EXISTS razorpay_fund_account_id VARCHAR(50);

-- Constraint: payout_status must be one of the known values
-- (ALTER DOMAIN not available in Supabase PostgreSQL without extensions;
--  use a CHECK constraint instead)
ALTER TABLE referrals
    ADD CONSTRAINT referrals_payout_status_check
    CHECK (payout_status IN (
        'NOT_INITIATED', 'PROCESSING', 'PAID', 'FAILED'
    ));
