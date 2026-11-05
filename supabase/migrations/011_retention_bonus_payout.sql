-- ============================================================================
-- Migration 011 — Retention-bonus payout tracking
--
-- Adds columns required by the daily Bull/Redis referral-payout worker:
--
--   referrals.bonus_paid_at       — timestamp when 90-day bonus was disbursed
--   referrals.bonus_payout_id     — Razorpay payout ID for the retention bonus
--                                   (kept separate from razorpay_payout_id which
--                                    tracks the initial hire-reward payout)
--   users.phone                   — employee mobile number for WhatsApp notification
--
-- BONUS_PAID is added as a valid referral status; the worker transitions
-- status from HIRED → BONUS_PAID once the retention bonus is confirmed paid.
-- ============================================================================

-- Retention-bonus disbursement columns on referrals
ALTER TABLE referrals
    ADD COLUMN IF NOT EXISTS bonus_paid_at    TIMESTAMP,
    ADD COLUMN IF NOT EXISTS bonus_payout_id  VARCHAR(50);

-- Index used by the worker's daily eligibility query:
--   status = 'HIRED', hire_date ≤ 90 days ago, bonus_paid_at IS NULL
CREATE INDEX IF NOT EXISTS referrals_bonus_worker_idx
    ON referrals(status, hire_date)
    WHERE status = 'HIRED' AND bonus_paid_at IS NULL;

-- Unique index: one bonus payout per referral
CREATE UNIQUE INDEX IF NOT EXISTS referrals_bonus_payout_uidx
    ON referrals(bonus_payout_id)
    WHERE bonus_payout_id IS NOT NULL;

-- Employee phone number — used by the worker to send the WhatsApp notification
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
