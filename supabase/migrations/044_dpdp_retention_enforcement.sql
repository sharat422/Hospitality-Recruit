-- DPDP retention enforcement: legal holds, scheduled erasure and evidence.
BEGIN;

ALTER TABLE candidate_documents
    ADD COLUMN IF NOT EXISTS data_category VARCHAR(50) DEFAULT 'RECRUITMENT_DOCUMENT',
    ADD COLUMN IF NOT EXISTS retention_until DATE,
    ADD COLUMN IF NOT EXISTS legal_hold BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS legal_hold_basis TEXT,
    ADD COLUMN IF NOT EXISTS erased_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS storage_region VARCHAR(20) NOT NULL DEFAULT 'ap-south-1',
    ADD COLUMN IF NOT EXISTS encryption_mode VARCHAR(20) NOT NULL DEFAULT 'SSE-S3';

ALTER TABLE candidate_documents DROP CONSTRAINT IF EXISTS candidate_documents_status_check;
ALTER TABLE candidate_documents ADD CONSTRAINT candidate_documents_status_check
    CHECK (status IN ('UPLOADED','VERIFIED','REJECTED','EXPIRED','ERASED'));
ALTER TABLE candidate_documents ADD CONSTRAINT candidate_documents_india_region
    CHECK (storage_region = 'ap-south-1');

CREATE INDEX IF NOT EXISTS candidate_documents_retention_due
    ON candidate_documents(retention_until)
    WHERE legal_hold = FALSE AND erased_at IS NULL;

ALTER TABLE dpdp_retention_schedule
    ADD COLUMN IF NOT EXISTS effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
    ADD COLUMN IF NOT EXISTS effective_to DATE,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS dpdp_retention_category_unique
    ON dpdp_retention_schedule(purpose_code, data_category)
    WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS dpdp_retention_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,
    document_id UUID REFERENCES candidate_documents(id) ON DELETE SET NULL,
    data_category VARCHAR(100) NOT NULL,
    action VARCHAR(30) NOT NULL CHECK (action IN ('RETAIN','ANONYMISE','DELETE','LEGAL_HOLD','RELEASE_HOLD')),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','COMPLETED','FAILED','SKIPPED')),
    scheduled_for DATE,
    completed_at TIMESTAMPTZ,
    legal_basis TEXT,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS dpdp_retention_actions_org_date
    ON dpdp_retention_actions(org_id, scheduled_for, status);

ALTER TABLE dpdp_retention_actions ENABLE ROW LEVEL SECURITY;
CREATE POLICY dpdp_retention_actions_read ON dpdp_retention_actions FOR SELECT USING (
    org_id=current_user_org_id() AND rbac_has_permission('compliance.read')
);
CREATE POLICY dpdp_retention_actions_manage ON dpdp_retention_actions FOR ALL USING (
    org_id=current_user_org_id() AND rbac_has_permission('compliance.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('compliance.manage'));

COMMIT;
