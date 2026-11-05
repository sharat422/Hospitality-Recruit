-- 016_fssai_upload.sql
-- FSSAI certificate upload support + new certificate types
-- Adds: BASIC_FOOD_HYGIENE, FOSTAC, FSSAI_LICENSE, ALCOHOL_LICENSE_FORM_FL
-- Adds: s3_key, upload_token, candidate_phone, recruiter_email columns
-- Law: Food Safety and Standards Act 2006, State Excise Acts

BEGIN;

-- ─── New cert-type values (comment documents the enum; Postgres uses VARCHAR) ───
-- Previous types: ESTABLISHMENT_LICENSE | FOSTAC_TRAINING | FOOD_HANDLER
-- New types added by this migration:
--   BASIC_FOOD_HYGIENE    – Basic Food Hygiene training (individual)
--   FOSTAC                – FoSTaC (Food Safety Training and Certification)
--   FSSAI_LICENSE         – FSSAI establishment license (14-digit)
--   ALCOHOL_LICENSE_FORM_FL – State Excise alcohol licence (Form FL-3/FL-11)

-- ─── S3 upload support ────────────────────────────────────────────────────────
ALTER TABLE fssai_certificates
    ADD COLUMN IF NOT EXISTS s3_key        TEXT,          -- S3 object key (ap-south-1)
    ADD COLUMN IF NOT EXISTS upload_token  UUID DEFAULT gen_random_uuid() UNIQUE,
    -- upload_token is returned with presigned URL; confirmed to prevent orphan uploads
    ADD COLUMN IF NOT EXISTS upload_confirmed_at TIMESTAMP,
    -- populated once the frontend PUTs the file and calls confirm-upload
    ADD COLUMN IF NOT EXISTS candidate_phone     VARCHAR(15),  -- for SMS alert
    ADD COLUMN IF NOT EXISTS recruiter_email     TEXT;         -- for email alert

-- Ensure upload_token is unique and indexed for fast look-up during confirm step
CREATE UNIQUE INDEX IF NOT EXISTS fssai_upload_token ON fssai_certificates(upload_token);

-- ─── 7-day alert column (was already in 014 but add IF NOT EXISTS for safety) ──
ALTER TABLE fssai_certificates
    ADD COLUMN IF NOT EXISTS alert_7_day_sent   BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS alert_expired_sent BOOLEAN DEFAULT FALSE;

-- ─── Alcohol license specific fields ─────────────────────────────────────────
ALTER TABLE fssai_certificates
    ADD COLUMN IF NOT EXISTS alcohol_license_number VARCHAR(50),
    ADD COLUMN IF NOT EXISTS alcohol_license_form   VARCHAR(20),  -- FL-3 | FL-11 | FL-12
    ADD COLUMN IF NOT EXISTS issuing_authority      TEXT;         -- State Excise Dept name

-- ─── Index for expiry worker (queries ACTIVE certs not yet alerted) ───────────
CREATE INDEX IF NOT EXISTS fssai_expiry_worker
    ON fssai_certificates(expiry_date, status, alert_30_day_sent, alert_7_day_sent)
    WHERE status = 'ACTIVE';

COMMIT;
