-- India compliance hardening: identifier minimisation, expiry automation and DPDP erasure evidence.
BEGIN;

-- Convert any legacy full PAN stored by the old manual endpoint to ABCDE****F.
UPDATE india_identity_verifications
SET pan_masked = CASE
        WHEN pan_number ~ '^[A-Z]{5}[0-9]{4}[A-Z]$' THEN substr(pan_number, 1, 5) || '****' || right(pan_number, 1)
        WHEN pan_number ~ '^[A-Z]{5}\*{4}[A-Z]$' THEN pan_number
        ELSE pan_masked
    END,
    pan_number = CASE
        WHEN pan_number ~ '^[A-Z]{5}[0-9]{4}[A-Z]$' THEN substr(pan_number, 1, 5) || '****' || right(pan_number, 1)
        WHEN pan_number ~ '^[A-Z]{5}\*{4}[A-Z]$' THEN pan_number
        ELSE NULL
    END
WHERE pan_number IS NOT NULL;

ALTER TABLE india_identity_verifications
    DROP CONSTRAINT IF EXISTS identity_pan_masked_only,
    DROP CONSTRAINT IF EXISTS identity_aadhaar_last4_only,
    DROP CONSTRAINT IF EXISTS identity_aadhaar_mask_format;
ALTER TABLE india_identity_verifications
    ADD CONSTRAINT identity_pan_masked_only CHECK (
        pan_number IS NULL OR pan_number ~ '^[A-Z]{5}\*{4}[A-Z]$'
    ),
    ADD CONSTRAINT identity_aadhaar_last4_only CHECK (
        aadhaar_last4 IS NULL OR aadhaar_last4 ~ '^[0-9]{4}$'
    ),
    ADD CONSTRAINT identity_aadhaar_mask_format CHECK (
        aadhaar_masked IS NULL OR aadhaar_masked ~ '^XXXX XXXX [0-9]{4}$'
    );

ALTER TABLE aadhaar_kyc_sessions
    DROP CONSTRAINT IF EXISTS aadhaar_session_last4_only,
    DROP CONSTRAINT IF EXISTS aadhaar_session_mask_format;
ALTER TABLE aadhaar_kyc_sessions
    ADD CONSTRAINT aadhaar_session_last4_only CHECK (
        aadhaar_last4 IS NULL OR aadhaar_last4 ~ '^[0-9]{4}$'
    ),
    ADD CONSTRAINT aadhaar_session_mask_format CHECK (
        aadhaar_masked IS NULL OR aadhaar_masked ~ '^XXXX XXXX [0-9]{4}$'
    );

ALTER TABLE dpdp_erasure_requests
    ADD COLUMN IF NOT EXISTS erasure_manifest JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS storage_deletion_status VARCHAR(20) DEFAULT 'NOT_STARTED',
    ADD COLUMN IF NOT EXISTS storage_deleted_at TIMESTAMP;

-- One employee can have at most one statutory PT deduction record per month.
CREATE UNIQUE INDEX IF NOT EXISTS professional_tax_candidate_period_unique
    ON professional_tax_records(org_id, candidate_id, pt_period);

-- DPDP records contain sensitive purpose/identity data. Replace broad org-member policies.
DROP POLICY IF EXISTS dpdp_consent_policy ON dpdp_consent_records;
DROP POLICY IF EXISTS dpdp_consent_rbac_select ON dpdp_consent_records;
DROP POLICY IF EXISTS dpdp_consent_rbac_insert ON dpdp_consent_records;
CREATE POLICY dpdp_consent_rbac_select ON dpdp_consent_records FOR SELECT USING (
    EXISTS (SELECT 1 FROM candidates c WHERE c.id=dpdp_consent_records.candidate_id AND c.user_id=auth.uid())
    OR (org_id=current_user_org_id() AND rbac_has_permission('compliance.read'))
);
CREATE POLICY dpdp_consent_rbac_insert ON dpdp_consent_records FOR INSERT WITH CHECK (
    EXISTS (SELECT 1 FROM candidates c WHERE c.id=dpdp_consent_records.candidate_id AND c.user_id=auth.uid())
    OR (org_id=current_user_org_id() AND rbac_has_permission('compliance.manage'))
);

DROP POLICY IF EXISTS dpdp_erasure_policy ON dpdp_erasure_requests;
DROP POLICY IF EXISTS dpdp_erasure_rbac_select ON dpdp_erasure_requests;
DROP POLICY IF EXISTS dpdp_erasure_rbac_insert ON dpdp_erasure_requests;
DROP POLICY IF EXISTS dpdp_erasure_rbac_update ON dpdp_erasure_requests;
CREATE POLICY dpdp_erasure_rbac_select ON dpdp_erasure_requests FOR SELECT USING (
    EXISTS (SELECT 1 FROM candidates c WHERE c.id=dpdp_erasure_requests.candidate_id AND c.user_id=auth.uid())
    OR (org_id=current_user_org_id() AND rbac_has_permission('compliance.read'))
);
CREATE POLICY dpdp_erasure_rbac_insert ON dpdp_erasure_requests FOR INSERT WITH CHECK (
    EXISTS (SELECT 1 FROM candidates c WHERE c.id=dpdp_erasure_requests.candidate_id AND c.user_id=auth.uid())
    OR (org_id=current_user_org_id() AND rbac_has_permission('compliance.manage'))
);
CREATE POLICY dpdp_erasure_rbac_update ON dpdp_erasure_requests FOR UPDATE USING (
    org_id=current_user_org_id() AND rbac_has_permission('compliance.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('compliance.manage'));

COMMIT;
