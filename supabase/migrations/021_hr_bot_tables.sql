-- 021_hr_bot_tables.sql
-- WhatsApp HR Bot — employee self-service tables
-- Covers: leave requests, payslips, complaints, leave balances, bot sessions
-- These tables support all seven bot commands:
--   LEAVE · PAYSLIP · SHIFT · BALANCE · COMPLAINT · CAREER · HELP

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Leave balances (annual allocation per employee)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leave_balances (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id      UUID NOT NULL REFERENCES users(id)         ON DELETE CASCADE,
    year             SMALLINT NOT NULL,

    casual_total     SMALLINT DEFAULT 12,
    casual_used      SMALLINT DEFAULT 0,

    sick_total       SMALLINT DEFAULT 12,
    sick_used        SMALLINT DEFAULT 0,

    earned_total     SMALLINT DEFAULT 15,
    earned_used      SMALLINT DEFAULT 0,

    -- Computed columns for fast queries
    casual_remaining SMALLINT GENERATED ALWAYS AS (casual_total - casual_used)  STORED,
    sick_remaining   SMALLINT GENERATED ALWAYS AS (sick_total   - sick_used)    STORED,
    earned_remaining SMALLINT GENERATED ALWAYS AS (earned_total - earned_used)  STORED,

    created_at       TIMESTAMP DEFAULT NOW(),
    updated_at       TIMESTAMP DEFAULT NOW(),
    UNIQUE(employee_id, year)
);

CREATE INDEX IF NOT EXISTS lb_org_year ON leave_balances(org_id, year);

ALTER TABLE leave_balances ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lb_policy ON leave_balances;
CREATE POLICY lb_policy ON leave_balances
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));

-- Seed current year balance for any existing users (no-op if already seeded)
INSERT INTO leave_balances (org_id, employee_id, year)
SELECT u.org_id, u.id, EXTRACT(YEAR FROM NOW())::smallint
FROM users u
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Leave requests
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leave_requests (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id      UUID NOT NULL REFERENCES users(id)         ON DELETE CASCADE,

    leave_date       DATE    NOT NULL,
    leave_type       VARCHAR(20) DEFAULT 'CASUAL',
    -- CASUAL | SICK | EMERGENCY | EARNED

    reason           TEXT    NOT NULL,

    status           VARCHAR(20) DEFAULT 'PENDING',
    -- PENDING | APPROVED | REJECTED | CANCELLED

    ticket_number    VARCHAR(25) UNIQUE NOT NULL,   -- LV-YYYYMMDD-XXXXXX
    approved_by      UUID REFERENCES users(id),
    approved_at      TIMESTAMP,
    rejection_reason TEXT,

    -- Source channel
    channel          VARCHAR(20) DEFAULT 'WHATSAPP', -- WHATSAPP | APP | EMAIL

    created_at       TIMESTAMP DEFAULT NOW(),
    updated_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS lr_employee   ON leave_requests(employee_id, leave_date);
CREATE INDEX IF NOT EXISTS lr_org_status ON leave_requests(org_id, status);

ALTER TABLE leave_requests ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lr_policy ON leave_requests;
CREATE POLICY lr_policy ON leave_requests
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Payslips
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payslips (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id           UUID NOT NULL REFERENCES users(id)         ON DELETE CASCADE,

    month                 SMALLINT NOT NULL,      -- 1-12
    year                  SMALLINT NOT NULL,

    -- Earnings
    gross_salary_inr      NUMERIC NOT NULL,
    basic_salary_inr      NUMERIC,
    hra_inr               NUMERIC DEFAULT 0,
    da_inr                NUMERIC DEFAULT 0,
    allowances_inr        NUMERIC DEFAULT 0,
    overtime_inr          NUMERIC DEFAULT 0,
    bonus_inr             NUMERIC DEFAULT 0,

    -- Deductions
    epf_deduction_inr     NUMERIC DEFAULT 0,
    esic_deduction_inr    NUMERIC DEFAULT 0,
    professional_tax_inr  NUMERIC DEFAULT 0,
    tds_inr               NUMERIC DEFAULT 0,
    other_deductions_inr  NUMERIC DEFAULT 0,

    -- Net
    net_salary_inr        NUMERIC NOT NULL,

    -- Payment
    paid_at               TIMESTAMP,
    payment_method        VARCHAR(20) DEFAULT 'BANK_TRANSFER',
    -- BANK_TRANSFER | UPI | CASH
    payslip_pdf_url       TEXT,    -- S3 ap-south-1 link

    -- Attendance
    working_days          SMALLINT,
    present_days          SMALLINT,
    absent_days           SMALLINT,
    leave_days            SMALLINT,

    created_at            TIMESTAMP DEFAULT NOW(),
    UNIQUE(employee_id, month, year)
);

CREATE INDEX IF NOT EXISTS ps_employee_month ON payslips(employee_id, year, month);
CREATE INDEX IF NOT EXISTS ps_org_month      ON payslips(org_id, year, month);

ALTER TABLE payslips ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ps_policy ON payslips;
CREATE POLICY ps_policy ON payslips
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Employee complaints
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS employee_complaints (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id      UUID NOT NULL REFERENCES users(id)         ON DELETE CASCADE,

    complaint_text   TEXT NOT NULL,
    category         VARCHAR(30) DEFAULT 'GENERAL',
    -- GENERAL | HARASSMENT | SAFETY | PAYROLL | DISCRIMINATION | WORKPLACE

    ticket_number    VARCHAR(25) UNIQUE NOT NULL,   -- HR-YYYYMMDD-XXXXXX
    status           VARCHAR(20) DEFAULT 'OPEN',
    -- OPEN | UNDER_REVIEW | RESOLVED | CLOSED

    assigned_to      UUID REFERENCES users(id),     -- HR manager handling
    resolution_notes TEXT,
    resolved_at      TIMESTAMP,

    channel          VARCHAR(20) DEFAULT 'WHATSAPP',

    created_at       TIMESTAMP DEFAULT NOW(),
    updated_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ec_employee ON employee_complaints(employee_id);
CREATE INDEX IF NOT EXISTS ec_org_open ON employee_complaints(org_id, status) WHERE status = 'OPEN';

ALTER TABLE employee_complaints ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ec_policy ON employee_complaints;
CREATE POLICY ec_policy ON employee_complaints
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. HR Bot sessions (conversation state per phone number)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hr_bot_sessions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone            VARCHAR(20) NOT NULL UNIQUE,       -- E.164 without whatsapp: prefix
    employee_id      UUID REFERENCES users(id)      ON DELETE SET NULL,
    org_id           UUID REFERENCES organizations(id) ON DELETE SET NULL,
    last_command     VARCHAR(50),
    last_message_at  TIMESTAMP DEFAULT NOW(),
    message_count    INTEGER   DEFAULT 0,
    is_active        BOOLEAN   DEFAULT TRUE,
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS hbs_phone      ON hr_bot_sessions(phone);
CREATE INDEX IF NOT EXISTS hbs_employee   ON hr_bot_sessions(employee_id);
CREATE INDEX IF NOT EXISTS hbs_active     ON hr_bot_sessions(is_active, last_message_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Employee shift assignments view
--    Joins candidates → shift_matches → shifts for SHIFT command
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_employee_shifts AS
SELECT
    u.id                    AS employee_id,
    u.org_id,
    u.phone,
    sm.shift_id,
    sm.match_score,
    sm.status               AS assignment_status,
    s.role,
    s.shift_type,
    s.start_date,
    s.end_date,
    s.hours_per_week,
    s.status                AS shift_status
FROM users u
JOIN candidates c ON c.email = u.email AND c.org_id = u.org_id
JOIN shift_matches sm ON sm.candidate_id = c.id AND sm.status IN ('confirmed', 'matched')
JOIN shifts s ON s.id = sm.shift_id
WHERE s.status = 'open'
  AND s.start_date >= CURRENT_DATE;

COMMIT;
