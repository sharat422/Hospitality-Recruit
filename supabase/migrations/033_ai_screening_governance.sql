-- Govern the existing AI screening implementation without replacing candidates,
-- applications, jobs, or candidate_screening_results.
BEGIN;

CREATE TABLE IF NOT EXISTS screening_weight_configs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
  skill_weight NUMERIC(5,4) NOT NULL DEFAULT 0.30,
  experience_weight NUMERIC(5,4) NOT NULL DEFAULT 0.25,
  language_weight NUMERIC(5,4) NOT NULL DEFAULT 0.10,
  location_weight NUMERIC(5,4) NOT NULL DEFAULT 0.15,
  salary_weight NUMERIC(5,4) NOT NULL DEFAULT 0.10,
  availability_weight NUMERIC(5,4) NOT NULL DEFAULT 0.10,
  shortlist_threshold NUMERIC(5,2) NOT NULL DEFAULT 75,
  reject_threshold NUMERIC(5,2) NOT NULL DEFAULT 45,
  updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (skill_weight >= 0 AND experience_weight >= 0 AND language_weight >= 0 AND
         location_weight >= 0 AND salary_weight >= 0 AND availability_weight >= 0),
  CHECK (abs(skill_weight + experience_weight + language_weight + location_weight + salary_weight + availability_weight - 1.0) < 0.0001),
  CHECK (reject_threshold >= 0 AND reject_threshold < shortlist_threshold AND shortlist_threshold <= 100)
);
CREATE UNIQUE INDEX IF NOT EXISTS screening_weights_job_unique
  ON screening_weight_configs(org_id, job_id) WHERE job_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS screening_weights_org_default_unique
  ON screening_weight_configs(org_id) WHERE job_id IS NULL;

ALTER TABLE candidate_screening_results
  ADD COLUMN IF NOT EXISTS deterministic_score NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS scoring_weights JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS scoring_version TEXT NOT NULL DEFAULT 'deterministic-v1',
  ADD COLUMN IF NOT EXISTS explanation_source TEXT NOT NULL DEFAULT 'DETERMINISTIC',
  ADD COLUMN IF NOT EXISTS recommendation_reasons JSONB NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS recruiter_override TEXT,
  ADD COLUMN IF NOT EXISTS override_reason TEXT,
  ADD COLUMN IF NOT EXISTS overridden_by UUID REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS overridden_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS recruiter_decision TEXT,
  ADD COLUMN IF NOT EXISTS decision_by UUID REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS decision_at TIMESTAMPTZ;

UPDATE candidate_screening_results
SET deterministic_score=total_score
WHERE deterministic_score IS NULL;

DO $$ BEGIN
  ALTER TABLE candidate_screening_results ADD CONSTRAINT csr_override_check
    CHECK (recruiter_override IS NULL OR recruiter_override IN ('shortlist','consider','reject'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE candidate_screening_results ADD CONSTRAINT csr_decision_check
    CHECK (recruiter_decision IS NULL OR recruiter_decision IN ('SHORTLIST_CONFIRMED','OVERRIDE_RECORDED','OVERRIDE_CLEARED'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS screening_decision_audit (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  screening_result_id UUID REFERENCES candidate_screening_results(id) ON DELETE SET NULL,
  candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
  job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  previous_value JSONB NOT NULL DEFAULT '{}',
  new_value JSONB NOT NULL DEFAULT '{}',
  reason TEXT NOT NULL,
  actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (action IN ('SCREENED','WEIGHTS_CHANGED','SHORTLIST_CONFIRMED','RECRUITER_OVERRIDE','OVERRIDE_CLEARED'))
);
CREATE INDEX IF NOT EXISTS screening_audit_candidate_idx ON screening_decision_audit(candidate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS screening_audit_job_idx ON screening_decision_audit(job_id, created_at DESC);

-- Recreate the existing leaderboard as a security-invoker view and append
-- governance fields so RLS remains authoritative for API reads.
CREATE OR REPLACE VIEW v_screening_leaderboard WITH (security_invoker=true) AS
SELECT
  csr.id, csr.org_id, csr.job_id, csr.job_role_id, csr.candidate_id,
  csr.total_score, csr.skill_score, csr.experience_score, csr.language_score,
  csr.location_score, csr.salary_score, csr.availability_score,
  csr.skill_explanation, csr.experience_explanation, csr.language_explanation,
  csr.location_explanation, csr.salary_explanation, csr.availability_explanation,
  csr.cross_industry_match, csr.cross_industry_source, csr.cross_industry_target,
  csr.cross_industry_note, csr.blind_id, csr.blind_mode_used,
  csr.overall_recommendation, csr.auto_shortlisted, csr.shortlisted_at,
  csr.strengths, csr.gaps, csr.screened_at,
  c.first_name, c.last_name, c.email, c.phone, c.source, c.pipeline_status,
  c.years_experience, c.current_location AS candidate_location,
  c.expected_salary_inr, c.notice_period_days,
  COALESCE(j.title, jr.title) AS job_title,
  COALESCE(j.department, jr.department) AS department,
  COALESCE(j.property_name, jr.location) AS property_name,
  RANK() OVER (PARTITION BY COALESCE(csr.job_id, csr.job_role_id) ORDER BY csr.total_score DESC) AS rank,
  csr.deterministic_score, csr.scoring_weights, csr.scoring_version,
  csr.explanation_source, csr.recommendation_reasons, csr.recruiter_override,
  csr.override_reason, csr.overridden_by, csr.overridden_at,
  csr.recruiter_decision, csr.decision_by, csr.decision_at
FROM candidate_screening_results csr
JOIN candidates c ON c.id=csr.candidate_id
LEFT JOIN jobs j ON j.id=csr.job_id
LEFT JOIN job_roles jr ON jr.id=csr.job_role_id;

ALTER TABLE screening_weight_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidate_screening_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE screening_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE screening_decision_audit ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS screening_weights_read ON screening_weight_configs;
CREATE POLICY screening_weights_read ON screening_weight_configs FOR SELECT USING (
  org_id=current_user_org_id() AND rbac_has_permission('candidates.read'));
DROP POLICY IF EXISTS screening_weights_manage ON screening_weight_configs;
CREATE POLICY screening_weights_manage ON screening_weight_configs FOR ALL USING (
  org_id=current_user_org_id() AND rbac_has_permission('candidates.manage'))
  WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('candidates.manage'));
DROP POLICY IF EXISTS screening_results_read ON candidate_screening_results;
CREATE POLICY screening_results_read ON candidate_screening_results FOR SELECT USING (
  org_id=current_user_org_id() AND rbac_has_permission('candidates.read'));
DROP POLICY IF EXISTS screening_results_manage ON candidate_screening_results;
CREATE POLICY screening_results_manage ON candidate_screening_results FOR ALL USING (
  org_id=current_user_org_id() AND rbac_has_permission('candidates.manage'))
  WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('candidates.manage'));
DROP POLICY IF EXISTS screening_runs_org ON screening_runs;
CREATE POLICY screening_runs_org ON screening_runs FOR ALL USING (
  org_id=current_user_org_id() AND rbac_has_permission('candidates.read'))
  WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('candidates.manage'));
DROP POLICY IF EXISTS screening_audit_read ON screening_decision_audit;
CREATE POLICY screening_audit_read ON screening_decision_audit FOR SELECT USING (
  org_id=current_user_org_id() AND rbac_has_permission('candidates.read'));
DROP POLICY IF EXISTS screening_audit_insert ON screening_decision_audit;
CREATE POLICY screening_audit_insert ON screening_decision_audit FOR INSERT WITH CHECK (
  org_id=current_user_org_id() AND rbac_has_permission('candidates.manage'));

COMMIT;
