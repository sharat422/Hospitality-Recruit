-- Complete the existing candidate/application ATS model without duplicating either table.
BEGIN;

ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS expected_salary_inr INTEGER,
    ADD COLUMN IF NOT EXISTS salary_currency VARCHAR(3) NOT NULL DEFAULT 'INR',
    ADD COLUMN IF NOT EXISTS profile_summary TEXT,
    ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS duplicate_of_candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS shortlisted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS selected_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS offer_accepted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS onboarding_at TIMESTAMPTZ;

ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS stage_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS selected_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS offer_accepted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS onboarding_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS hired_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS candidate_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    application_id UUID REFERENCES applications(id) ON DELETE CASCADE,
    body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 10000),
    is_private BOOLEAN NOT NULL DEFAULT FALSE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS candidate_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    application_id UUID REFERENCES applications(id) ON DELETE SET NULL,
    document_type VARCHAR(50) NOT NULL,
    file_name TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    file_url TEXT,
    mime_type VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'UPLOADED',
    expiry_date DATE,
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (status IN ('UPLOADED','VERIFIED','REJECTED','EXPIRED'))
);

CREATE TABLE IF NOT EXISTS application_stage_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    from_stage VARCHAR(30),
    to_stage VARCHAR(30) NOT NULL,
    notes TEXT,
    changed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS candidates_search_idx ON candidates(org_id, pipeline_stage, source);
CREATE INDEX IF NOT EXISTS candidate_notes_candidate_idx ON candidate_notes(candidate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS candidate_documents_candidate_idx ON candidate_documents(candidate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS application_stage_history_timeline_idx ON application_stage_history(application_id, changed_at);

UPDATE candidates SET pipeline_stage=lower(pipeline_stage) WHERE pipeline_stage IS NOT NULL;
UPDATE applications SET status=upper(status) WHERE status IS NOT NULL;
UPDATE applications SET status='SCREENED' WHERE status='REVIEWING';
UPDATE applications SET status='OFFER' WHERE status='OFFERED';

DO $$ BEGIN
 ALTER TABLE candidates ADD CONSTRAINT candidates_expected_salary_nonnegative CHECK (expected_salary_inr IS NULL OR expected_salary_inr >= 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
 ALTER TABLE candidates ADD CONSTRAINT candidates_pipeline_stage_check CHECK (
   pipeline_stage IN ('applied','screened','shortlisted','interview','selected','offer','offer_accepted','onboarding','hired','rejected','withdrawn'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
 ALTER TABLE applications ADD CONSTRAINT applications_ats_status_check CHECK (
   status IN ('DRAFT','SUBMITTED','APPLIED','SCREENED','SHORTLISTED','INTERVIEW','SELECTED','OFFER','OFFER_ACCEPTED','ONBOARDING','HIRED','REJECTED','WITHDRAWN'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Reuse the existing interview table and add structured feedback only when it exists.
DO $$ BEGIN
 IF to_regclass('public.interviews') IS NOT NULL THEN
   ALTER TABLE interviews ADD COLUMN IF NOT EXISTS feedback JSONB NOT NULL DEFAULT '{}';
   ALTER TABLE interviews ADD COLUMN IF NOT EXISTS recommendation VARCHAR(30);
 END IF;
END $$;

-- The engagement module's interview_slots table is the currently mounted
-- scheduling flow. Extend it in place so scheduling and feedback share one record.
DO $$ BEGIN
 IF to_regclass('public.interview_slots') IS NOT NULL THEN
   ALTER TABLE interview_slots ADD COLUMN IF NOT EXISTS interview_rating NUMERIC(2,1);
   ALTER TABLE interview_slots ADD COLUMN IF NOT EXISTS interview_notes TEXT;
   ALTER TABLE interview_slots ADD COLUMN IF NOT EXISTS feedback JSONB NOT NULL DEFAULT '{}';
   ALTER TABLE interview_slots ADD COLUMN IF NOT EXISTS recommendation VARCHAR(30);
   ALTER TABLE interview_slots ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
 END IF;
END $$;

ALTER TABLE candidate_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidate_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE application_stage_history ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS candidate_notes_rbac ON candidate_notes;
CREATE POLICY candidate_notes_rbac ON candidate_notes FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('candidates.read'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('candidates.manage'));
DROP POLICY IF EXISTS candidate_documents_rbac ON candidate_documents;
CREATE POLICY candidate_documents_rbac ON candidate_documents FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('documents.read'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('documents.manage'));
DROP POLICY IF EXISTS application_stage_history_rbac ON application_stage_history;
CREATE POLICY application_stage_history_rbac ON application_stage_history FOR SELECT USING (
 org_id=current_user_org_id() AND rbac_has_permission('applications.read'));
DROP POLICY IF EXISTS application_stage_history_insert ON application_stage_history;
CREATE POLICY application_stage_history_insert ON application_stage_history FOR INSERT WITH CHECK (
 org_id=current_user_org_id() AND rbac_has_permission('applications.manage'));

COMMIT;
