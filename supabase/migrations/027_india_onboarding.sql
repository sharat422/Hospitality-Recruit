-- =============================================================================
-- Migration 027: India Digital Onboarding
-- Appointment letters, CTC breakup, Aadhaar eSign, PF/ESIC forms,
-- 5-stage checklist, WhatsApp pre-boarding sequences, at-risk detection.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- onboarding_flows — one row per candidate+job onboarding engagement
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS onboarding_flows (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              UUID,
  candidate_id        UUID REFERENCES candidates(id) ON DELETE CASCADE,
  job_id              UUID,                  -- references jobs(id)
  job_role_id         UUID,                  -- references job_roles(id) — legacy

  -- Identity snapshot (to avoid joins in dashboard queries)
  candidate_name      TEXT,
  role_title          TEXT,
  department          TEXT,
  property_name       TEXT,
  manager_name        TEXT,
  manager_phone       TEXT,
  reporting_location  TEXT,
  reporting_time      TEXT DEFAULT '09:00',

  -- Joining
  joining_date        DATE,
  offer_date          DATE DEFAULT CURRENT_DATE,

  -- 5-stage checklist progress
  -- stages: documents | kyc | certifications | payroll | ready
  current_stage       TEXT NOT NULL DEFAULT 'documents'
                       CHECK (current_stage IN ('documents','kyc','certifications','payroll','ready')),
  completion_pct      NUMERIC(5,2) DEFAULT 0,
  stage_completion    JSONB DEFAULT '{
    "documents":      0,
    "kyc":            0,
    "certifications": 0,
    "payroll":        0,
    "ready":          0
  }'::jsonb,

  -- At-risk flag: joining ≤7 days AND completion <50%
  is_at_risk          BOOLEAN DEFAULT FALSE,
  at_risk_reason      TEXT,
  at_risk_flagged_at  TIMESTAMPTZ,

  -- Completion
  completed_at        TIMESTAMPTZ,
  status              TEXT DEFAULT 'active' CHECK (status IN ('active','completed','dropped','on_hold')),

  -- Pre-boarding
  preboarding_sequence_id UUID,
  preboarding_started_at  TIMESTAMPTZ,

  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 001_init_schema.sql created a smaller table with this name. CREATE TABLE IF
-- NOT EXISTS does not merge columns, so upgrade that legacy shape explicitly.
ALTER TABLE onboarding_flows
  ADD COLUMN IF NOT EXISTS job_role_id UUID,
  ADD COLUMN IF NOT EXISTS candidate_name TEXT,
  ADD COLUMN IF NOT EXISTS role_title TEXT,
  ADD COLUMN IF NOT EXISTS department TEXT,
  ADD COLUMN IF NOT EXISTS property_name TEXT,
  ADD COLUMN IF NOT EXISTS manager_name TEXT,
  ADD COLUMN IF NOT EXISTS manager_phone TEXT,
  ADD COLUMN IF NOT EXISTS reporting_location TEXT,
  ADD COLUMN IF NOT EXISTS reporting_time TEXT DEFAULT '09:00',
  ADD COLUMN IF NOT EXISTS joining_date DATE,
  ADD COLUMN IF NOT EXISTS offer_date DATE DEFAULT CURRENT_DATE,
  ADD COLUMN IF NOT EXISTS current_stage TEXT NOT NULL DEFAULT 'documents',
  ADD COLUMN IF NOT EXISTS completion_pct NUMERIC(5,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS stage_completion JSONB DEFAULT '{"documents":0,"kyc":0,"certifications":0,"payroll":0,"ready":0}'::jsonb,
  ADD COLUMN IF NOT EXISTS is_at_risk BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS at_risk_reason TEXT,
  ADD COLUMN IF NOT EXISTS at_risk_flagged_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS preboarding_sequence_id UUID,
  ADD COLUMN IF NOT EXISTS preboarding_started_at TIMESTAMPTZ;

ALTER TABLE onboarding_flows ALTER COLUMN job_id DROP NOT NULL;
ALTER TABLE onboarding_flows ALTER COLUMN status SET DEFAULT 'active';
UPDATE onboarding_flows SET status='active' WHERE status='not_started';
UPDATE onboarding_flows SET completion_pct=COALESCE(progress_percent,0)
WHERE completion_pct=0 AND progress_percent IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ob_flows_candidate ON onboarding_flows(candidate_id);
CREATE INDEX IF NOT EXISTS idx_ob_flows_org      ON onboarding_flows(org_id);
CREATE INDEX IF NOT EXISTS idx_ob_flows_at_risk  ON onboarding_flows(is_at_risk) WHERE is_at_risk = TRUE;
CREATE INDEX IF NOT EXISTS idx_ob_flows_joining  ON onboarding_flows(joining_date);

-- ─────────────────────────────────────────────────────────────────────────────
-- onboarding_tasks — individual checklist items per flow
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS onboarding_tasks (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  flow_id          UUID REFERENCES onboarding_flows(id) ON DELETE CASCADE,
  org_id           UUID,
  candidate_id     UUID,

  stage            TEXT NOT NULL CHECK (stage IN ('documents','kyc','certifications','payroll','ready')),
  task_type        TEXT NOT NULL,   -- e.g. 'aadhaar_upload', 'appointment_letter_esign'
  task_label       TEXT NOT NULL,   -- HR-readable label
  is_mandatory     BOOLEAN DEFAULT TRUE,
  is_system        BOOLEAN DEFAULT FALSE,  -- system auto-completes (e.g. PF form generated)

  status           TEXT DEFAULT 'pending' CHECK (status IN ('pending','in_progress','completed','waived','failed')),
  completed_at     TIMESTAMPTZ,
  completed_by     TEXT,           -- 'candidate', 'hr', 'system'
  notes            TEXT,
  document_url     TEXT,

  due_date         DATE,
  sort_order       INT DEFAULT 0,

  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ob_tasks_flow ON onboarding_tasks(flow_id);
CREATE INDEX IF NOT EXISTS idx_ob_tasks_stage ON onboarding_tasks(flow_id, stage);

-- ─────────────────────────────────────────────────────────────────────────────
-- appointment_letters — Indian appointment letter with CTC breakup
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS appointment_letters (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  flow_id           UUID REFERENCES onboarding_flows(id) ON DELETE CASCADE,
  org_id            UUID,
  candidate_id      UUID,

  -- CTC inputs
  gross_monthly_inr INT NOT NULL,

  -- CTC breakup (computed and stored)
  ctc_breakup       JSONB NOT NULL DEFAULT '{}',
  -- Expected shape: {basic, hra, special_allowance, epf_employee, epf_employer,
  --   esic_employee, esic_employer, pt, net_monthly, annual_ctc, esic_applicable}

  -- Probation, notice period
  probation_months  INT DEFAULT 6,
  notice_period_days INT DEFAULT 30,

  -- Generated letter
  letter_html       TEXT,           -- full HTML content
  letter_url        TEXT,           -- S3/storage URL for PDF
  letter_version    INT DEFAULT 1,

  -- eSign
  esign_status      TEXT DEFAULT 'not_requested'
                     CHECK (esign_status IN ('not_requested','requested','signed','rejected','expired')),
  esign_provider    TEXT,           -- 'leegality' | 'digio' | 'signdesk' | 'demo'
  esign_request_id  TEXT,           -- provider's request ID
  esign_url         TEXT,           -- candidate sign URL
  esigned_at        TIMESTAMPTZ,
  signed_letter_url TEXT,           -- URL of signed document

  -- Acceptance
  candidate_accepted_at TIMESTAMPTZ,

  generated_at      TIMESTAMPTZ DEFAULT NOW(),
  generated_by      UUID,           -- user_id who triggered generation
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_letters_flow ON appointment_letters(flow_id);
CREATE INDEX IF NOT EXISTS idx_letters_esign ON appointment_letters(esign_status);

-- ─────────────────────────────────────────────────────────────────────────────
-- pf_esic_declarations — PF Form 2 and ESIC declaration records
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pf_esic_declarations (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  flow_id          UUID REFERENCES onboarding_flows(id) ON DELETE CASCADE,
  org_id           UUID,
  candidate_id     UUID,

  form_type        TEXT NOT NULL CHECK (form_type IN ('pf_form2','esic_declaration')),

  -- Form data
  form_data        JSONB NOT NULL DEFAULT '{}',
  -- PF Form 2: member_name, father_spouse_name, dob, date_of_joining,
  --   nominees (name, relationship, dob, share_pct), family_details
  -- ESIC: employee_name, dob, father_spouse_name, nominee, address

  -- Submission
  form_html        TEXT,
  form_url         TEXT,            -- PDF URL
  status           TEXT DEFAULT 'draft' CHECK (status IN ('draft','submitted','filed')),
  submitted_at     TIMESTAMPTZ,
  filed_at         TIMESTAMPTZ,
  uan_number       TEXT,            -- Universal Account Number (PF)
  esic_ip_number   TEXT,            -- ESIC Insurance Person number

  generated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pf_esic_flow ON pf_esic_declarations(flow_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- preboarding_sequences — WhatsApp pre-boarding campaign definitions
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS preboarding_sequences (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID,
  name        TEXT NOT NULL DEFAULT 'Standard India Onboarding',
  is_active   BOOLEAN DEFAULT TRUE,
  -- days_config: list of {offset_days, reference, template_key, label}
  -- reference: 'offer' (days after offer) or 'joining' (days before joining)
  days_config JSONB NOT NULL DEFAULT '[]',
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- preboarding_messages — individual WhatsApp messages per candidate
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS preboarding_messages (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  flow_id          UUID REFERENCES onboarding_flows(id) ON DELETE CASCADE,
  org_id           UUID,
  candidate_id     UUID,
  candidate_phone  TEXT,

  template_key     TEXT NOT NULL,   -- e.g. 'day0_welcome', 'day_before_reporting'
  template_label   TEXT,
  message_body     TEXT,

  scheduled_for    TIMESTAMPTZ NOT NULL,
  sent_at          TIMESTAMPTZ,
  whatsapp_msg_id  TEXT,
  status           TEXT DEFAULT 'scheduled'
                    CHECK (status IN ('scheduled','sent','failed','skipped')),
  error_detail     TEXT,

  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pb_msgs_scheduled ON preboarding_messages(scheduled_for) WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_pb_msgs_flow ON preboarding_messages(flow_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- updated_at triggers
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION set_updated_at_ob()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_ob_flows_updated_at ON onboarding_flows;
CREATE TRIGGER trg_ob_flows_updated_at
  BEFORE UPDATE ON onboarding_flows
  FOR EACH ROW EXECUTE FUNCTION set_updated_at_ob();

DROP TRIGGER IF EXISTS trg_letters_updated_at ON appointment_letters;
CREATE TRIGGER trg_letters_updated_at
  BEFORE UPDATE ON appointment_letters
  FOR EACH ROW EXECUTE FUNCTION set_updated_at_ob();

-- ─────────────────────────────────────────────────────────────────────────────
-- Function: recompute completion % from tasks
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION recompute_onboarding_completion(p_flow_id UUID)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
  v_total     INT;
  v_done      INT;
  v_pct       NUMERIC(5,2);
  v_stage_json JSONB;
  v_stage     TEXT;
  v_stages    TEXT[] := ARRAY['documents','kyc','certifications','payroll','ready'];
  v_s_total   INT;
  v_s_done    INT;
BEGIN
  SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'completed' OR status = 'waived')
  INTO v_total, v_done
  FROM onboarding_tasks
  WHERE flow_id = p_flow_id AND is_mandatory = TRUE;

  v_pct := CASE WHEN v_total = 0 THEN 0 ELSE ROUND(v_done::NUMERIC / v_total * 100, 2) END;

  v_stage_json := '{}'::JSONB;
  FOREACH v_stage IN ARRAY v_stages LOOP
    SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'completed' OR status = 'waived')
    INTO v_s_total, v_s_done
    FROM onboarding_tasks
    WHERE flow_id = p_flow_id AND stage = v_stage AND is_mandatory = TRUE;
    v_stage_json := v_stage_json || jsonb_build_object(
      v_stage,
      CASE WHEN v_s_total = 0 THEN 0 ELSE ROUND(v_s_done::NUMERIC / v_s_total * 100, 0) END
    );
  END LOOP;

  UPDATE onboarding_flows
  SET
    completion_pct   = v_pct,
    stage_completion = v_stage_json,
    is_at_risk = (
      joining_date IS NOT NULL
      AND joining_date - CURRENT_DATE <= 7
      AND v_pct < 50
      AND status = 'active'
    ),
    at_risk_reason = CASE
      WHEN joining_date IS NOT NULL AND joining_date - CURRENT_DATE <= 7 AND v_pct < 50
      THEN 'Joining in ' || (joining_date - CURRENT_DATE) || ' days, only ' || ROUND(v_pct) || '% complete'
      ELSE NULL
    END
  WHERE id = p_flow_id;
END;
$$;

-- Trigger: recompute when task status changes
CREATE OR REPLACE FUNCTION trg_task_completion()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  PERFORM recompute_onboarding_completion(NEW.flow_id);
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_ob_task_status ON onboarding_tasks;
CREATE TRIGGER trg_ob_task_status
  AFTER INSERT OR UPDATE OF status ON onboarding_tasks
  FOR EACH ROW EXECUTE FUNCTION trg_task_completion();

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed default sequence config (6 pre-boarding messages)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO preboarding_sequences (name, is_active, days_config)
VALUES (
  'India Standard Pre-Boarding',
  TRUE,
  '[
    {"offset_days": 0,  "reference": "offer",   "template_key": "day0_welcome",       "label": "Day 0 — Welcome & offer confirmation"},
    {"offset_days": 1,  "reference": "offer",   "template_key": "day1_team_intro",    "label": "Day 1 — Team introduction"},
    {"offset_days": 3,  "reference": "offer",   "template_key": "day3_practical",     "label": "Day 3 — Practical info"},
    {"offset_days": -7, "reference": "joining", "template_key": "pre7_docs_checklist","label": "7 days before — Document checklist"},
    {"offset_days": -1, "reference": "joining", "template_key": "pre1_reporting",     "label": "Day before — Reporting instructions"},
    {"offset_days": 0,  "reference": "joining", "template_key": "day1_morning",       "label": "Joining Day — Morning welcome"}
  ]'::jsonb
)
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- v_onboarding_dashboard — summary view for dashboard queries
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_onboarding_dashboard AS
SELECT
  f.id,
  f.org_id,
  f.candidate_id,
  f.candidate_name,
  f.role_title,
  f.department,
  f.property_name,
  f.manager_name,
  f.joining_date,
  f.offer_date,
  f.current_stage,
  f.completion_pct,
  f.stage_completion,
  f.is_at_risk,
  f.at_risk_reason,
  f.status,
  f.preboarding_started_at,
  f.created_at,
  -- Task counts
  (SELECT COUNT(*) FROM onboarding_tasks t WHERE t.flow_id = f.id AND t.is_mandatory) AS total_tasks,
  (SELECT COUNT(*) FROM onboarding_tasks t WHERE t.flow_id = f.id AND t.status IN ('completed','waived')) AS done_tasks,
  -- Letter status
  (SELECT esign_status FROM appointment_letters l WHERE l.flow_id = f.id ORDER BY generated_at DESC LIMIT 1) AS letter_esign_status,
  -- Days until joining
  CASE WHEN f.joining_date IS NOT NULL THEN f.joining_date - CURRENT_DATE ELSE NULL END AS days_until_joining,
  -- Pre-boarding messages
  (SELECT COUNT(*) FROM preboarding_messages m WHERE m.flow_id = f.id AND m.status = 'sent') AS pb_messages_sent,
  (SELECT COUNT(*) FROM preboarding_messages m WHERE m.flow_id = f.id) AS pb_messages_total
FROM onboarding_flows f;
