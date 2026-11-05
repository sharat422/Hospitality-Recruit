-- 020_diversity_reporting.sql
-- Indian Diversity Reporting Engine
-- Laws: RPWD Act 2016, Transgender Persons (Protection of Rights) Act 2019,
--       Equal Remuneration Act 1976 (pay gap), DPDP Act 2023 (consent)
--
-- Design constraints:
--   • Gender and PwD status are ALWAYS optional — never mandatory
--   • Religion is NEVER collected (no column, no API)
--   • SC/ST/OBC/EWS collected ONLY when statutory_reporting_required=true on org
--   • Blind screening: name/photo/hometown stripped at query time (no permanent change)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Organizations — statutory reporting gate
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS statutory_reporting_required BOOLEAN DEFAULT FALSE,
    -- TRUE only for orgs required by law to submit diversity returns
    -- (Factories Act: ≥500 employees; some state acts: ≥50 workers)
    ADD COLUMN IF NOT EXISTS statutory_employee_threshold INT DEFAULT 500,
    -- Employee count threshold that triggered statutory_reporting_required=true
    ADD COLUMN IF NOT EXISTS statutory_reporting_law TEXT;
    -- e.g. "Factories Act 1948 / Equal Remuneration Act 1976"

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Candidates — denormalised diversity fields for fast dashboard queries
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS gender             VARCHAR(30),
    -- MALE | FEMALE | TRANSGENDER | NON_BINARY | PREFER_NOT_TO_SAY
    -- Populated from india_diversity_data on consent; nullable = not disclosed
    ADD COLUMN IF NOT EXISTS is_pwd             BOOLEAN DEFAULT FALSE,
    -- Person with Disability (RPWD Act 2016); default false ≠ "not pwd"
    ADD COLUMN IF NOT EXISTS offered_salary_inr NUMERIC,
    -- Monthly CTC in INR at time of offer (for pay gap computation)
    ADD COLUMN IF NOT EXISTS hired_at           TIMESTAMP;
    -- When candidate moved to 'hired' stage (for hire-rate denominator)

-- Indexes for diversity dashboard aggregations
CREATE INDEX IF NOT EXISTS cand_gender_stage
    ON candidates(org_id, gender, pipeline_stage);

CREATE INDEX IF NOT EXISTS cand_pwd
    ON candidates(org_id, is_pwd)
    WHERE is_pwd = TRUE;

CREATE INDEX IF NOT EXISTS cand_hired_salary
    ON candidates(org_id, gender, offered_salary_inr)
    WHERE offered_salary_inr IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Jobs — blind screening mode flag
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS blind_screening_enabled BOOLEAN DEFAULT FALSE;
    -- When true, candidate name/photo/hometown are hidden in screening views

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Remove religion from india_diversity_data
-- The religion column was defined in 014 but must NOT be collected per policy.
-- We DROP it here and enforce the prohibition at the API layer.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE india_diversity_data
    DROP COLUMN IF EXISTS religion;

-- Also add a NOT NULL check that social_category only collected with proper gate
-- (enforced at service layer, not in SQL to keep migrations simple)

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Diversity snapshot cache — precomputed dashboard numbers (updated nightly)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS diversity_snapshots (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Applications by gender
    total_applications         INT DEFAULT 0,
    applications_male          INT DEFAULT 0,
    applications_female        INT DEFAULT 0,
    applications_transgender   INT DEFAULT 0,
    applications_non_binary    INT DEFAULT 0,
    applications_not_disclosed INT DEFAULT 0,

    -- Hires by gender
    total_hires                INT DEFAULT 0,
    hires_male                 INT DEFAULT 0,
    hires_female               INT DEFAULT 0,
    hires_transgender          INT DEFAULT 0,
    hires_not_disclosed        INT DEFAULT 0,

    -- PwD
    applications_pwd           INT DEFAULT 0,
    hires_pwd                  INT DEFAULT 0,

    -- Pay gap (Equal Remuneration Act 1976)
    median_salary_male_inr     NUMERIC,
    median_salary_female_inr   NUMERIC,
    gender_pay_gap_pct         NUMERIC,
    pay_gap_sample_size        INT DEFAULT 0,

    -- SC/ST/OBC/EWS (only when statutory_reporting_required=true)
    applications_sc            INT,  -- NULL when not statutory
    applications_st            INT,
    applications_obc           INT,
    applications_ews           INT,
    applications_general       INT,

    computed_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE(org_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS diversity_snap_org ON diversity_snapshots(org_id, snapshot_date DESC);

ALTER TABLE diversity_snapshots ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS diversity_snap_policy ON diversity_snapshots;
CREATE POLICY diversity_snap_policy ON diversity_snapshots
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));

COMMIT;
