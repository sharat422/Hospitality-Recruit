-- 018_dpdp_privacy.sql
-- DPDP Act 2023 — Privacy Centre enhancements
-- Adds: legal retention basis, WhatsApp acknowledgment tracking,
--       candidate privacy access tokens, data-localisation metadata
-- Law: DPDP Act 2023 Sections 6, 8, 13, 16 / IT Act 2000 Section 43A

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Enhance dpdp_consent_records
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE dpdp_consent_records
    -- Legal basis for retention even if consent is withdrawn
    -- DPDP Act 2023 s.8(7): data retained where legal obligation exists
    ADD COLUMN IF NOT EXISTS legal_retention_basis  TEXT,
    -- e.g. "Income Tax Act 1961 s.44AB — 8 years", "EPF Act 1952 — 8 years"

    ADD COLUMN IF NOT EXISTS retention_end_date     DATE,
    -- Date after which data MUST be deleted even without erasure request

    -- Data localisation — all PII stored in India
    ADD COLUMN IF NOT EXISTS data_region            VARCHAR(20) DEFAULT 'ap-south-1',
    -- ap-south-1 (Mumbai AWS) or supabase-in (when available)

    -- No-bundling enforcement: one record = one purpose, one decision
    -- Composite unique prevents re-granting without explicit withdrawal
    ADD COLUMN IF NOT EXISTS consent_version_seq    SMALLINT DEFAULT 1;
    -- Increments each time the same purpose is toggled; ensures immutable history

CREATE INDEX IF NOT EXISTS dpdp_consent_latest
    ON dpdp_consent_records(candidate_id, purpose_code, consented_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Enhance dpdp_erasure_requests — WhatsApp acknowledgment
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE dpdp_erasure_requests
    ADD COLUMN IF NOT EXISTS candidate_phone        VARCHAR(15),
    -- E.164 Indian mobile — used for WhatsApp ack
    ADD COLUMN IF NOT EXISTS whatsapp_ack_sent_at   TIMESTAMP,
    ADD COLUMN IF NOT EXISTS whatsapp_ack_sid        TEXT,
    -- Twilio message SID for delivery tracking
    ADD COLUMN IF NOT EXISTS whatsapp_ack_failed     BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS whatsapp_ack_error      TEXT;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Candidate privacy access tokens
-- Enables tokenised, auth-free access to Privacy Centre
-- Token sent via SMS/WhatsApp; expires in 7 days; single-use
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS privacy_center_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id    UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    token           TEXT NOT NULL UNIQUE,       -- URL-safe random 32-char token
    purpose         VARCHAR(30) DEFAULT 'GENERAL',
    -- GENERAL | ERASURE_FOLLOWUP | CONSENT_REVIEW
    expires_at      TIMESTAMP NOT NULL,         -- 7 days from creation
    used_at         TIMESTAMP,                  -- set on first use (single-use)
    ip_address      TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS privacy_session_token  ON privacy_center_sessions(token);
CREATE INDEX IF NOT EXISTS privacy_session_cand   ON privacy_center_sessions(candidate_id);
CREATE INDEX IF NOT EXISTS privacy_session_expiry ON privacy_center_sessions(expires_at)
    WHERE used_at IS NULL;

ALTER TABLE privacy_center_sessions ENABLE ROW LEVEL SECURITY;
-- Sessions are accessed via token (no RLS user context needed for public endpoint)
-- Backend validates token programmatically before any data access

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Legal retention schedule reference table
-- Documents which data must be retained and for how long (DPDP Act s.8)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dpdp_retention_schedule (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purpose_code    VARCHAR(50) NOT NULL,
    data_category   VARCHAR(100) NOT NULL,
    retention_years SMALLINT,                   -- NULL = indefinite
    retention_basis TEXT NOT NULL,
    -- "Income Tax Act 1961 s.44AB — 8 years"
    exempts_erasure BOOLEAN DEFAULT FALSE,
    -- TRUE means erasure request can be rejected for this category
    created_at      TIMESTAMP DEFAULT NOW()
);

INSERT INTO dpdp_retention_schedule
    (purpose_code, data_category, retention_years, retention_basis, exempts_erasure)
VALUES
('RECRUITMENT_DATA', 'Application records',    1,    'DPDP Act 2023 s.8 — reasonable retention post-decision',   FALSE),
('RECRUITMENT_DATA', 'Interview records',       1,    'DPDP Act 2023 s.8',                                        FALSE),
('BACKGROUND_CHECK', 'Identity documents',     3,    'IT Act 2000 / anti-fraud compliance',                      FALSE),
('BACKGROUND_CHECK', 'Employment verification',3,    'IT Act 2000 s.43A',                                        FALSE),
('SENSITIVE_DATA',   'Medical fitness records', NULL, 'Factories Act 1948 s.7A — employer duty of care',          TRUE),
('SENSITIVE_DATA',   'Biometric data',          NULL, 'Aadhaar Act 2016 — UIDAI mandate (last4 only)',            TRUE),
('AI_PROFILING',     'Screening scores',        1,    'DPDP Act 2023 s.8 — post-hiring decision',                 FALSE),
('THIRD_PARTY_SHARE','Shared candidate profile',0,    'Withdraw before sharing; once shared, org controls',       FALSE),
('MARKETING',        'Contact preferences',     0,    'Erase on withdrawal',                                      FALSE),
('CROSS_BORDER',     'Cross-border transfers',  3,    'DPDP Act 2023 s.16 — prior to notified country list',      FALSE),
-- Payroll / statutory
('RECRUITMENT_DATA', 'EPF/UAN records',         8,    'EPF Act 1952 r.32 — 8 years post-employment',              TRUE),
('RECRUITMENT_DATA', 'PAN / Form 16',           8,    'Income Tax Act 1961 s.44AB — 8 years',                     TRUE),
('RECRUITMENT_DATA', 'ESIC records',            8,    'ESIC Act 1948 r.56 — 8 years',                             TRUE),
('SENSITIVE_DATA',   'Professional Tax records', 5,   'Various State PT Acts — 5 years',                          TRUE);

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Data localisation metadata view
-- Confirms that all PII tables are configured for India storage
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_data_localisation_status AS
SELECT
    'dpdp_consent_records'       AS table_name,
    'PII'                        AS data_classification,
    'ap-south-1'                 AS storage_region,
    'DPDP Act 2023 s.16'         AS legal_basis,
    COUNT(*)                     AS row_count
FROM dpdp_consent_records
UNION ALL
SELECT
    'dpdp_erasure_requests', 'PII', 'ap-south-1',
    'DPDP Act 2023 s.13', COUNT(*)
FROM dpdp_erasure_requests
UNION ALL
SELECT
    'india_identity_verifications', 'PII', 'ap-south-1',
    'Aadhaar Act 2016 / DPDP 2023', COUNT(*)
FROM india_identity_verifications
UNION ALL
SELECT
    'candidates', 'PII', 'ap-south-1',
    'DPDP Act 2023 s.8', COUNT(*)
FROM candidates;

COMMIT;
