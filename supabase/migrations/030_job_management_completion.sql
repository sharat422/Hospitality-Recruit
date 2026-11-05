-- Complete the existing jobs model; do not create a parallel job table.
BEGIN;

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS role_template_id UUID REFERENCES role_templates(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS hiring_manager_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS recruiter_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS education_level VARCHAR(50),
    ADD COLUMN IF NOT EXISTS required_skills JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS preferred_skills JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS required_languages JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS shift_requirements JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS accommodation_provided BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS food_provided BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS transportation_provided BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS ctc_min_inr INTEGER,
    ADD COLUMN IF NOT EXISTS ctc_max_inr INTEGER,
    ADD COLUMN IF NOT EXISTS salary_period VARCHAR(20) NOT NULL DEFAULT 'MONTHLY',
    ADD COLUMN IF NOT EXISTS urgency_level VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
    ADD COLUMN IF NOT EXISTS approval_status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    ADD COLUMN IF NOT EXISTS approval_requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS approval_requested_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS approval_notes TEXT,
    ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS closed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS duplicated_from_job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS job_board_versions JSONB NOT NULL DEFAULT '{}';

ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS recruiter_id UUID REFERENCES users(id) ON DELETE SET NULL;

UPDATE jobs SET approval_status='APPROVED', approved_at=COALESCE(updated_at, created_at)
WHERE lower(status)='open' AND approval_status='DRAFT';
UPDATE jobs SET urgency_level=CASE WHEN is_urgent THEN 'URGENT' ELSE 'NORMAL' END
WHERE urgency_level='NORMAL';
UPDATE jobs j SET role_template_id=rt.id FROM role_templates rt
WHERE j.role_template_id IS NULL AND j.role_template=rt.role_key;
UPDATE applications a SET job_id=c.applied_job_id
FROM candidates c WHERE a.candidate_id=c.id AND a.job_id IS NULL AND c.applied_job_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS jobs_manager_idx ON jobs(org_id, hiring_manager_id);
CREATE INDEX IF NOT EXISTS jobs_recruiter_idx ON jobs(org_id, recruiter_id);
CREATE INDEX IF NOT EXISTS jobs_approval_idx ON jobs(org_id, approval_status, status);
CREATE INDEX IF NOT EXISTS applications_job_idx ON applications(job_id, status);

DO $$ BEGIN
 ALTER TABLE jobs ADD CONSTRAINT jobs_salary_range_check CHECK (
   salary_min_inr IS NULL OR salary_max_inr IS NULL OR salary_min_inr <= salary_max_inr);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
 ALTER TABLE jobs ADD CONSTRAINT jobs_ctc_range_check CHECK (
   ctc_min_inr IS NULL OR ctc_max_inr IS NULL OR ctc_min_inr <= ctc_max_inr);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
 ALTER TABLE jobs ADD CONSTRAINT jobs_experience_range_check CHECK (
   experience_min_years >= 0 AND (experience_max_years IS NULL OR experience_max_years >= experience_min_years));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
 ALTER TABLE jobs ADD CONSTRAINT jobs_openings_positive CHECK (openings_count > 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
 ALTER TABLE jobs ADD CONSTRAINT jobs_approval_status_check CHECK (
   approval_status IN ('DRAFT','PENDING_APPROVAL','APPROVED','REJECTED'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
 ALTER TABLE jobs ADD CONSTRAINT jobs_urgency_level_check CHECK (
   urgency_level IN ('NORMAL','HIGH','URGENT','CRITICAL'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS job_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    from_status VARCHAR(30),
    to_status VARCHAR(30) NOT NULL,
    action VARCHAR(40) NOT NULL,
    notes TEXT,
    changed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS job_status_history_job_idx ON job_status_history(job_id, changed_at DESC);
ALTER TABLE job_status_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY job_status_history_read ON job_status_history FOR SELECT USING (
 org_id=current_user_org_id() AND rbac_has_permission('jobs.read'));
CREATE POLICY job_status_history_write ON job_status_history FOR INSERT WITH CHECK (
 org_id=current_user_org_id() AND rbac_has_permission('jobs.manage'));

COMMIT;
