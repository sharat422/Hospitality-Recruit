-- 015_kyc_sessions.sql
-- Aadhaar eKYC OTP session tracking + PAN masked column
-- Compliant with: Aadhaar Act 2016, UIDAI circular on storage prohibition,
--                 DPDP Act 2023 (minimal data principle)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- Aadhaar OTP session table
-- Stores transient eKYC flow state; full Aadhaar NEVER persisted.
-- Row is created on OTP-initiate and updated on OTP-verify; expires in 10 min.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aadhaar_kyc_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_id    UUID REFERENCES candidates(id) ON DELETE SET NULL,

    provider        VARCHAR(20) NOT NULL DEFAULT 'SUREPASS',
    -- KYC provider: SUREPASS | SANDBOX (dev/staging mock)

    request_id      TEXT NOT NULL UNIQUE,
    -- Provider-assigned session/client_id for OTP correlation

    status          VARCHAR(20) NOT NULL DEFAULT 'OTP_SENT',
    -- OTP_SENT | VERIFIED | FAILED | EXPIRED

    -- Populated only after successful OTP verify (never on initiate)
    aadhaar_last4   CHAR(4),
    aadhaar_masked  VARCHAR(20),     -- "XXXX XXXX 1234"
    name_from_uid   TEXT,            -- UIDAI-returned name (read-only, not editable)
    dob_year        SMALLINT,        -- birth year only — not full DOB (privacy)
    gender          CHAR(1),         -- M / F / T (as returned by UIDAI)
    address_state   TEXT,            -- state from UIDAI address (no street-level stored)

    otp_attempts    SMALLINT DEFAULT 0,
    ip_address      TEXT,

    created_at      TIMESTAMP DEFAULT NOW(),
    expires_at      TIMESTAMP DEFAULT NOW() + INTERVAL '10 minutes',
    verified_at     TIMESTAMP,

    -- Link back to identity_verifications record created on verify success
    identity_verification_id UUID REFERENCES india_identity_verifications(id)
);

CREATE INDEX IF NOT EXISTS aadhaar_session_candidate
    ON aadhaar_kyc_sessions(candidate_id);

CREATE INDEX IF NOT EXISTS aadhaar_session_status
    ON aadhaar_kyc_sessions(status, expires_at);

CREATE INDEX IF NOT EXISTS aadhaar_session_org
    ON aadhaar_kyc_sessions(org_id);

-- RLS: each org only sees its own sessions
ALTER TABLE aadhaar_kyc_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS aadhaar_session_org_policy ON aadhaar_kyc_sessions;
CREATE POLICY aadhaar_session_org_policy ON aadhaar_kyc_sessions
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));

-- ─────────────────────────────────────────────────────────────────────────────
-- Add pan_masked to identity verifications (ABCDE****F format)
-- Separate from pan_number so we know a masked value was stored by KYC flow
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE india_identity_verifications
    ADD COLUMN IF NOT EXISTS pan_masked     VARCHAR(10),
    ADD COLUMN IF NOT EXISTS kyc_provider   VARCHAR(20),  -- SUREPASS | SANDBOX
    ADD COLUMN IF NOT EXISTS kyc_session_id UUID REFERENCES aadhaar_kyc_sessions(id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Scheduled cleanup: purge expired+unverified sessions after 24 hours
-- (pg_cron or a nightly job should call this)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION purge_expired_aadhaar_sessions() RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM aadhaar_kyc_sessions
    WHERE status IN ('OTP_SENT', 'FAILED')
      AND expires_at < NOW() - INTERVAL '24 hours';
END;
$$;

COMMIT;
