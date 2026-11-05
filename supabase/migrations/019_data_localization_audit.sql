-- 019_data_localization_audit.sql
-- India Data Localisation Enforcement Audit Tables
-- DPDP Act 2023 s.16 — Personal data of Indian citizens must be stored in India
-- IT Act 2000 s.43A — Reasonable security practices for sensitive personal data

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. File upload audit log
--    Every file upload (resume, FSSAI cert, KYC doc, video) generates one row.
--    is_india_compliant is computed from s3_region automatically.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS file_upload_audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID REFERENCES organizations(id) ON DELETE SET NULL,
    candidate_id    UUID REFERENCES candidates(id)   ON DELETE SET NULL,

    -- What was uploaded
    file_type       VARCHAR(50) NOT NULL,
    -- RESUME | FSSAI_CERT | KYC_AADHAAR | KYC_PAN | KYC_DIGILOCKER |
    -- IDENTITY_DOC | VIDEO_INTERVIEW | OTHER

    s3_key          TEXT,
    s3_bucket       TEXT,
    s3_region       VARCHAR(30) NOT NULL DEFAULT 'ap-south-1',
    content_type    VARCHAR(100),
    file_size_bytes BIGINT,

    -- Computed: is this upload India-compliant?
    is_india_compliant BOOLEAN GENERATED ALWAYS AS (s3_region = 'ap-south-1') STORED,

    -- Who uploaded
    uploader_type   VARCHAR(20) DEFAULT 'RECRUITER',
    -- RECRUITER | CANDIDATE | SYSTEM | WORKER
    uploader_id     UUID,

    -- Compliance metadata
    law_reference   TEXT DEFAULT 'DPDP Act 2023 s.16 / IT Act 2000 s.43A',
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS upload_audit_org         ON file_upload_audit_log(org_id);
CREATE INDEX IF NOT EXISTS upload_audit_candidate   ON file_upload_audit_log(candidate_id);
CREATE INDEX IF NOT EXISTS upload_audit_compliant   ON file_upload_audit_log(is_india_compliant)
    WHERE NOT is_india_compliant;   -- only non-compliant rows indexed (should be empty)
CREATE INDEX IF NOT EXISTS upload_audit_type        ON file_upload_audit_log(file_type, created_at DESC);

ALTER TABLE file_upload_audit_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS upload_audit_org_policy ON file_upload_audit_log;
CREATE POLICY upload_audit_org_policy ON file_upload_audit_log
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. PII external transmission log
--    Every call that sends candidate PII to a third-party service is recorded.
--    This includes Anthropic, OpenAI, Twilio, Surepass, DigiLocker.
--    AADHAAR and PAN must only appear in Indian-service rows (was_blocked=TRUE otherwise).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pii_external_transmission_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID REFERENCES organizations(id) ON DELETE SET NULL,
    candidate_id    UUID REFERENCES candidates(id)   ON DELETE SET NULL,

    -- Which external service received PII
    service_name    VARCHAR(50) NOT NULL,
    -- ANTHROPIC | OPENAI | SUREPASS | DIGILOCKER | TWILIO | RAZORPAY | OTHER
    service_country VARCHAR(30) NOT NULL,   -- India | USA | EU | Other
    service_region  VARCHAR(50),            -- e.g. ap-south-1, us-east-1

    is_india_service BOOLEAN NOT NULL,

    -- What PII was sent
    pii_types       TEXT[] NOT NULL,
    -- RESUME_TEXT | CANDIDATE_NAME | PHONE_NUMBER | EMAIL |
    -- AADHAAR | PAN | FACE_PHOTO | EMPLOYMENT_HISTORY | SALARY_INFO

    fields_sent     TEXT[],                 -- specific field names

    -- Outcome
    was_allowed     BOOLEAN NOT NULL,
    was_blocked     BOOLEAN GENERATED ALWAYS AS (NOT was_allowed) STORED,
    block_reason    TEXT,                   -- why blocked (if was_allowed=false)
    allow_reason    TEXT,                   -- why allowed (if non-India service)
    -- INDIA_SERVICE | CROSS_BORDER_CONFIGURED | AADHAAR_PAN_BLOCKED

    law_reference   TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS pii_trans_org         ON pii_external_transmission_log(org_id);
CREATE INDEX IF NOT EXISTS pii_trans_candidate   ON pii_external_transmission_log(candidate_id);
CREATE INDEX IF NOT EXISTS pii_trans_blocked     ON pii_external_transmission_log(was_blocked)
    WHERE was_blocked;
CREATE INDEX IF NOT EXISTS pii_trans_service     ON pii_external_transmission_log(service_name, created_at DESC);
CREATE INDEX IF NOT EXISTS pii_trans_sensitive   ON pii_external_transmission_log(pii_types)
    WHERE pii_types && ARRAY['AADHAAR','PAN','FACE_PHOTO'];  -- flag sensitive PII rows

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Data localization compliance view
--    Shows overall compliance picture across all upload and transmission logs
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_data_localization_compliance AS
SELECT
    'UPLOADS'                       AS category,
    COUNT(*)                        AS total,
    SUM(CASE WHEN is_india_compliant THEN 1 ELSE 0 END) AS compliant,
    SUM(CASE WHEN NOT is_india_compliant THEN 1 ELSE 0 END) AS violations
FROM file_upload_audit_log
UNION ALL
SELECT
    'PII_TRANSMISSIONS',
    COUNT(*),
    SUM(CASE WHEN was_allowed AND is_india_service THEN 1 ELSE 0 END),
    SUM(CASE WHEN NOT was_allowed THEN 1 ELSE 0 END)
FROM pii_external_transmission_log;

COMMIT;
