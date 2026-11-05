-- =============================================================================
-- 022_whatsapp_hr_bot.sql
-- WhatsApp HR Bot — extended tables
--
-- New tables (do NOT conflict with 021_hr_bot_tables.sql):
--   whatsapp_users    — canonical identity registry: phone ↔ employee
--   whatsapp_messages — full message audit log (inbound + outbound)
--   payslip_requests  — employee payslip-view requests (not actual payslip data)
--   hr_complaints     — richer complaint table with anonymous reporting support
--
-- Extended tables (ALTER only, 021 tables remain intact):
--   leave_requests    — adds whatsapp_message_id, duration_days, SLA, cancel fields
--
-- Design notes:
--   • whatsapp_users is the authoritative identity record; hr_bot_sessions (021)
--     remains for lightweight real-time session tracking.
--   • hr_complaints is separate from employee_complaints (021) because anonymous
--     reports need employee_id = NULL, which the old table disallows.
--   • All tables carry org_id + RLS for multi-tenant isolation.
--   • Anonymous complaints: is_anonymous=TRUE → employee_id NULL; phone stored
--     encrypted at app layer but kept here for bot reply; identity visible only
--     to superadmin via audit; UI masks identity for regular HR staff.
-- =============================================================================

BEGIN;

-- =============================================================================
-- Shared helper: auto-update updated_at on every UPDATE
-- =============================================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


-- =============================================================================
-- 1. whatsapp_users — identity registry
--    One row per WhatsApp phone number, linked to an employee when recognised.
-- =============================================================================

CREATE TABLE IF NOT EXISTS whatsapp_users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    phone            VARCHAR(20) NOT NULL UNIQUE,
    -- E.164 without the "whatsapp:" prefix, e.g. "+919876543210"

    employee_id      UUID REFERENCES users(id)          ON DELETE SET NULL,
    -- NULL = phone not yet matched to any employee
    org_id           UUID REFERENCES organizations(id)  ON DELETE SET NULL,
    display_name     VARCHAR(200),
    -- Populated from users.email or candidates first+last name

    -- Verification
    is_verified      BOOLEAN  NOT NULL DEFAULT FALSE,
    verified_at      TIMESTAMP,
    verification_method VARCHAR(30) DEFAULT 'phone_match',
    -- phone_match | otp_verified | admin_linked | candidate_match

    -- Opt-out (DPDP s.7 — right to withdraw consent for processing via bot)
    opt_out          BOOLEAN  NOT NULL DEFAULT FALSE,
    opt_out_at       TIMESTAMP,
    opt_out_reason   TEXT,

    -- Status
    is_active        BOOLEAN  NOT NULL DEFAULT TRUE,
    deactivated_at   TIMESTAMP,
    deactivation_reason TEXT,

    -- Engagement metrics (denormalised for fast stats)
    first_message_at TIMESTAMP,
    last_message_at  TIMESTAMP,
    message_count    INTEGER  NOT NULL DEFAULT 0,
    last_command     VARCHAR(50),
    -- LEAVE | PAYSLIP | SHIFT | BALANCE | COMPLAINT | CAREER | HELP | UNKNOWN

    -- Audit
    registered_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    -- NULL = self-registered (first message); UUID = admin manually linked
    notes            TEXT,

    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS wu_phone       ON whatsapp_users(phone);
CREATE INDEX IF NOT EXISTS wu_employee    ON whatsapp_users(employee_id);
CREATE INDEX IF NOT EXISTS wu_org_active  ON whatsapp_users(org_id, is_active);
CREATE INDEX IF NOT EXISTS wu_last_msg    ON whatsapp_users(last_message_at DESC);

DROP TRIGGER IF EXISTS trg_wu_updated_at ON whatsapp_users;
CREATE TRIGGER trg_wu_updated_at
    BEFORE UPDATE ON whatsapp_users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE whatsapp_users ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS wu_policy ON whatsapp_users;
CREATE POLICY wu_policy ON whatsapp_users
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));


-- =============================================================================
-- 2. whatsapp_messages — complete message audit trail
--    Every inbound command and every outbound bot reply gets one row.
--    Inbound rows carry: command, command_args, command_status, response_body.
--    Outbound rows carry: twilio_sid, twilio_status.
-- =============================================================================

CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID REFERENCES organizations(id) ON DELETE SET NULL,
    whatsapp_user_id  UUID REFERENCES whatsapp_users(id) ON DELETE SET NULL,
    phone             VARCHAR(20) NOT NULL,
    -- denormalised: fast lookup even when whatsapp_user_id is NULL (unregistered)

    -- ── Message content ─────────────────────────────────────────────────────
    direction         VARCHAR(10) NOT NULL,
    -- INBOUND (employee → bot) | OUTBOUND (bot → employee)
    CONSTRAINT wm_direction_check CHECK (direction IN ('INBOUND', 'OUTBOUND')),

    body              TEXT,
    -- Raw message text from employee or bot reply text
    media_url         TEXT,       -- Twilio MediaUrl0 for image/doc messages
    media_type        VARCHAR(50),-- image/jpeg, application/pdf, etc.
    num_media         SMALLINT DEFAULT 0,

    -- ── Twilio metadata ─────────────────────────────────────────────────────
    twilio_sid        VARCHAR(50) UNIQUE,
    -- MessageSid from Twilio (null for internally-generated outbound)
    twilio_status     VARCHAR(30),
    -- queued | sending | sent | delivered | undelivered | failed | read

    -- ── Parsed command (INBOUND only) ───────────────────────────────────────
    command           VARCHAR(50),
    -- LEAVE | PAYSLIP | SHIFT | BALANCE | COMPLAINT | CAREER | HELP | UNKNOWN
    command_args      TEXT,
    -- Everything after the first word, e.g. "2026-06-20 not feeling well"
    command_status    VARCHAR(30) DEFAULT 'PROCESSED',
    -- PROCESSED | FAILED | IGNORED | UNREGISTERED | OPTED_OUT

    -- ── Bot response (INBOUND only, populated once reply is sent) ────────────
    response_body     TEXT,
    -- The text the bot sent back (mirrors the OUTBOUND row body for traceability)
    response_sid      VARCHAR(50),
    -- Twilio SID of the outbound reply message
    error_message     TEXT,
    -- Set if command_status = FAILED

    -- ── Source & timing ─────────────────────────────────────────────────────
    source            VARCHAR(20) NOT NULL DEFAULT 'WHATSAPP',
    processed_at      TIMESTAMP,
    -- Set when command handling completes

    created_at        TIMESTAMP NOT NULL DEFAULT NOW()
    -- No updated_at — messages are immutable audit records
);

CREATE INDEX IF NOT EXISTS wm_phone          ON whatsapp_messages(phone, created_at DESC);
CREATE INDEX IF NOT EXISTS wm_user_created   ON whatsapp_messages(whatsapp_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS wm_org_command    ON whatsapp_messages(org_id, command);
CREATE INDEX IF NOT EXISTS wm_twilio_sid     ON whatsapp_messages(twilio_sid) WHERE twilio_sid IS NOT NULL;
CREATE INDEX IF NOT EXISTS wm_direction      ON whatsapp_messages(org_id, direction, created_at DESC);
CREATE INDEX IF NOT EXISTS wm_inbound_date   ON whatsapp_messages(org_id, created_at DESC)
    WHERE direction = 'INBOUND';

ALTER TABLE whatsapp_messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS wm_policy ON whatsapp_messages;
CREATE POLICY wm_policy ON whatsapp_messages
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));

-- Trigger: when an INBOUND message is inserted, update the user's engagement stats
CREATE OR REPLACE FUNCTION sync_whatsapp_user_stats()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.direction = 'INBOUND' AND NEW.whatsapp_user_id IS NOT NULL THEN
        UPDATE whatsapp_users SET
            last_message_at = NEW.created_at,
            last_command    = COALESCE(NEW.command, last_command),
            message_count   = message_count + 1,
            first_message_at = COALESCE(first_message_at, NEW.created_at),
            updated_at      = NOW()
        WHERE id = NEW.whatsapp_user_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_wm_user_stats ON whatsapp_messages;
CREATE TRIGGER trg_wm_user_stats
    AFTER INSERT ON whatsapp_messages
    FOR EACH ROW EXECUTE FUNCTION sync_whatsapp_user_stats();


-- =============================================================================
-- 3. payslip_requests — employee payslip-view requests
--    Tracks every time an employee asks the bot for a payslip.
--    Separate from the payslips table (021), which stores HR-uploaded payslip data.
-- =============================================================================

CREATE TABLE IF NOT EXISTS payslip_requests (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id          UUID NOT NULL REFERENCES users(id)         ON DELETE CASCADE,
    whatsapp_message_id  UUID REFERENCES whatsapp_messages(id)      ON DELETE SET NULL,

    -- What the employee asked for
    requested_month      SMALLINT NOT NULL,
    CONSTRAINT pr_month_range CHECK (requested_month BETWEEN 1 AND 12),
    requested_year       SMALLINT NOT NULL,

    -- Resolution
    status               VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    -- PENDING | FULFILLED | NOT_FOUND | ERROR
    CONSTRAINT pr_status_check CHECK (status IN ('PENDING','FULFILLED','NOT_FOUND','ERROR')),

    payslip_id           UUID REFERENCES payslips(id) ON DELETE SET NULL,
    -- Populated when a matching payslip is found
    fulfilled_at         TIMESTAMP,

    -- Error detail (status = ERROR)
    error_detail         TEXT,

    -- Audit
    source               VARCHAR(20) NOT NULL DEFAULT 'WHATSAPP',
    -- WHATSAPP | APP | EMAIL

    created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS pr_employee_month ON payslip_requests(employee_id, requested_year, requested_month);
CREATE INDEX IF NOT EXISTS pr_org_status     ON payslip_requests(org_id, status);
CREATE INDEX IF NOT EXISTS pr_created        ON payslip_requests(created_at DESC);

DROP TRIGGER IF EXISTS trg_pr_updated_at ON payslip_requests;
CREATE TRIGGER trg_pr_updated_at
    BEFORE UPDATE ON payslip_requests
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE payslip_requests ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pr_policy ON payslip_requests;
CREATE POLICY pr_policy ON payslip_requests
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));


-- =============================================================================
-- 4. hr_complaints — richer complaint table with anonymous reporting
--
--    Why separate from employee_complaints (021)?
--    • employee_complaints has employee_id NOT NULL — anonymous impossible.
--    • This table makes employee_id nullable; phone stored separately so the
--      bot can still send status updates without revealing identity.
--    • is_anonymous = TRUE → employee_id NULL, display as "Anonymous Reporter".
--    • anonymous_token is given to the reporter so they can query status later
--      without identifying themselves.
--    • Severity + SLA deadline + escalation columns support a full ITSM workflow.
-- =============================================================================

CREATE TABLE IF NOT EXISTS hr_complaints (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- ── Reporter identity ────────────────────────────────────────────────────
    employee_id          UUID REFERENCES users(id) ON DELETE SET NULL,
    -- NULL when is_anonymous = TRUE
    phone                VARCHAR(20),
    -- Always stored (needed to send WhatsApp replies even for anonymous cases).
    -- UI layer masks this when is_anonymous = TRUE and viewer is not superadmin.
    is_anonymous         BOOLEAN NOT NULL DEFAULT FALSE,
    anonymous_token      VARCHAR(100) UNIQUE,
    -- 40-char hex token given to the reporter at submission time.
    -- They can query status at /api/v1/hr-bot/complaints/track/{token} without login.

    -- ── Complaint content ────────────────────────────────────────────────────
    complaint_text       TEXT NOT NULL,
    category             VARCHAR(30) NOT NULL DEFAULT 'GENERAL',
    -- GENERAL | HARASSMENT | SAFETY | PAYROLL | DISCRIMINATION | WORKPLACE | FACILITIES
    CONSTRAINT hc_category_check CHECK (
        category IN ('GENERAL','HARASSMENT','SAFETY','PAYROLL',
                     'DISCRIMINATION','WORKPLACE','FACILITIES')
    ),
    severity             VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
    -- LOW | MEDIUM | HIGH | CRITICAL
    CONSTRAINT hc_severity_check CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),

    -- ── Tracking ─────────────────────────────────────────────────────────────
    ticket_number        VARCHAR(25) NOT NULL UNIQUE,
    -- Format: HR-YYYYMMDD-XXXXXX (auto-generated by application layer)
    status               VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    -- OPEN | UNDER_REVIEW | RESOLVED | CLOSED | ESCALATED
    CONSTRAINT hc_status_check CHECK (
        status IN ('OPEN','UNDER_REVIEW','RESOLVED','CLOSED','ESCALATED')
    ),

    -- ── Assignment ───────────────────────────────────────────────────────────
    assigned_to          UUID REFERENCES users(id) ON DELETE SET NULL,
    assigned_at          TIMESTAMP,

    -- ── Resolution ───────────────────────────────────────────────────────────
    resolution_notes     TEXT,
    resolved_at          TIMESTAMP,
    closed_at            TIMESTAMP,
    close_reason         TEXT,
    -- e.g. "Duplicate of HR-20260515-ABC123" | "Reporter withdrew"

    -- ── Escalation ───────────────────────────────────────────────────────────
    escalated            BOOLEAN NOT NULL DEFAULT FALSE,
    escalated_at         TIMESTAMP,
    escalated_to         UUID REFERENCES users(id) ON DELETE SET NULL,
    escalation_reason    TEXT,
    -- Required when escalated = TRUE

    -- ── SLA management ───────────────────────────────────────────────────────
    sla_deadline         TIMESTAMP,
    -- Set at insert: NOW() + interval based on severity:
    --   CRITICAL → 1 working day, HIGH → 2, MEDIUM → 3, LOW → 5
    sla_breached         BOOLEAN NOT NULL DEFAULT FALSE,
    -- Flipped by a scheduled job when NOW() > sla_deadline and status != RESOLVED/CLOSED

    -- ── Source & audit ───────────────────────────────────────────────────────
    source               VARCHAR(20) NOT NULL DEFAULT 'WHATSAPP',
    -- WHATSAPP | APP | EMAIL | PHONE | IN_PERSON
    CONSTRAINT hc_source_check CHECK (
        source IN ('WHATSAPP','APP','EMAIL','PHONE','IN_PERSON')
    ),
    whatsapp_message_id  UUID REFERENCES whatsapp_messages(id) ON DELETE SET NULL,

    created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS hc_employee      ON hr_complaints(employee_id) WHERE employee_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS hc_org_status    ON hr_complaints(org_id, status);
CREATE INDEX IF NOT EXISTS hc_org_open      ON hr_complaints(org_id, created_at DESC)
    WHERE status = 'OPEN';
CREATE INDEX IF NOT EXISTS hc_category      ON hr_complaints(org_id, category);
CREATE INDEX IF NOT EXISTS hc_severity      ON hr_complaints(org_id, severity)
    WHERE severity IN ('HIGH','CRITICAL');
CREATE INDEX IF NOT EXISTS hc_anon_token    ON hr_complaints(anonymous_token)
    WHERE anonymous_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS hc_sla_overdue   ON hr_complaints(sla_deadline)
    WHERE status NOT IN ('RESOLVED','CLOSED') AND sla_deadline IS NOT NULL;
CREATE INDEX IF NOT EXISTS hc_ticket        ON hr_complaints(ticket_number);

DROP TRIGGER IF EXISTS trg_hc_updated_at ON hr_complaints;
CREATE TRIGGER trg_hc_updated_at
    BEFORE UPDATE ON hr_complaints
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Auto-set sla_deadline on INSERT based on severity
CREATE OR REPLACE FUNCTION set_hc_sla_deadline()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.sla_deadline IS NULL THEN
        NEW.sla_deadline := NOW() + CASE NEW.severity
            WHEN 'CRITICAL' THEN INTERVAL '1 day'
            WHEN 'HIGH'     THEN INTERVAL '2 days'
            WHEN 'MEDIUM'   THEN INTERVAL '3 days'
            ELSE                 INTERVAL '5 days'   -- LOW
        END;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_hc_sla ON hr_complaints;
CREATE TRIGGER trg_hc_sla
    BEFORE INSERT ON hr_complaints
    FOR EACH ROW EXECUTE FUNCTION set_hc_sla_deadline();

-- RLS: employees see only their own; anonymous complaints visible by org
ALTER TABLE hr_complaints ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS hc_policy ON hr_complaints;
CREATE POLICY hc_policy ON hr_complaints
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));


-- =============================================================================
-- 5. ALTER leave_requests (021) — add missing audit + linkage columns
-- =============================================================================

-- Link back to the WhatsApp message that created this request
ALTER TABLE leave_requests
    ADD COLUMN IF NOT EXISTS whatsapp_message_id UUID
        REFERENCES whatsapp_messages(id) ON DELETE SET NULL;

-- How many calendar days the leave covers (default 1 for day-off requests)
ALTER TABLE leave_requests
    ADD COLUMN IF NOT EXISTS duration_days SMALLINT NOT NULL DEFAULT 1;

-- SLA for HR to respond (3 working days by default)
ALTER TABLE leave_requests
    ADD COLUMN IF NOT EXISTS sla_deadline TIMESTAMP;

ALTER TABLE leave_requests
    ADD COLUMN IF NOT EXISTS sla_breached BOOLEAN NOT NULL DEFAULT FALSE;

-- Cancellation support (employee can cancel PENDING requests)
ALTER TABLE leave_requests
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP;

ALTER TABLE leave_requests
    ADD COLUMN IF NOT EXISTS cancel_reason TEXT;

-- Cover arrangement (optional: who covers while employee is on leave)
ALTER TABLE leave_requests
    ADD COLUMN IF NOT EXISTS substitute_employee_id UUID
        REFERENCES users(id) ON DELETE SET NULL;

-- Additional audit fields
ALTER TABLE leave_requests
    ADD COLUMN IF NOT EXISTS reviewed_notes TEXT;
-- HR note visible to employee alongside approval/rejection

-- Index the new foreign key
CREATE INDEX IF NOT EXISTS lr_wm ON leave_requests(whatsapp_message_id)
    WHERE whatsapp_message_id IS NOT NULL;

-- Back-fill sla_deadline for all existing PENDING requests (3 days from creation)
UPDATE leave_requests
SET sla_deadline = created_at + INTERVAL '3 days'
WHERE status = 'PENDING'
  AND sla_deadline IS NULL;


-- =============================================================================
-- 6. Views
-- =============================================================================

-- Summary view: WhatsApp user + employee profile + engagement stats
CREATE OR REPLACE VIEW v_whatsapp_user_summary AS
SELECT
    wu.id                   AS whatsapp_user_id,
    wu.phone,
    wu.display_name,
    wu.is_verified,
    wu.verified_at,
    wu.opt_out,
    wu.is_active,
    wu.last_message_at,
    wu.message_count,
    wu.last_command,
    wu.created_at           AS registered_at,

    -- Employee details (NULL if not yet linked)
    u.id                    AS employee_id,
    u.email                 AS employee_email,
    u.org_id,

    -- Candidate fallback name (when user is a candidate, not a platform user)
    COALESCE(wu.display_name, u.email)  AS resolved_name,

    -- Activity summary
    (SELECT COUNT(*) FROM leave_requests lr
     WHERE lr.employee_id = wu.employee_id)   AS total_leave_requests,
    (SELECT COUNT(*) FROM hr_complaints hc
     WHERE hc.employee_id = wu.employee_id)   AS total_complaints

FROM whatsapp_users wu
LEFT JOIN users u ON u.id = wu.employee_id;


-- HR view: complaints with masked identity for anonymous reports
-- HR staff see category/text/status but not the phone/name of anonymous reporters.
CREATE OR REPLACE VIEW v_hr_complaints_display AS
SELECT
    hc.id,
    hc.org_id,
    hc.ticket_number,
    hc.category,
    hc.severity,
    hc.status,
    hc.complaint_text,
    hc.sla_deadline,
    hc.sla_breached,
    hc.source,
    hc.escalated,
    hc.created_at,
    hc.updated_at,
    hc.resolved_at,
    hc.resolution_notes,
    hc.assigned_to,

    -- Mask identity for anonymous reporters
    CASE
        WHEN hc.is_anonymous THEN 'Anonymous Reporter'
        ELSE COALESCE(u.email, hc.phone, 'Unknown')
    END AS reporter_display,

    CASE
        WHEN hc.is_anonymous THEN NULL
        ELSE hc.employee_id
    END AS reporter_employee_id,

    hc.is_anonymous,
    hc.anonymous_token,

    -- Days since filed
    EXTRACT(DAY FROM NOW() - hc.created_at)::INTEGER AS days_open,

    -- SLA status
    CASE
        WHEN hc.status IN ('RESOLVED','CLOSED') THEN 'met'
        WHEN hc.sla_deadline < NOW()            THEN 'breached'
        WHEN hc.sla_deadline < NOW() + INTERVAL '1 day' THEN 'at_risk'
        ELSE 'on_track'
    END AS sla_status

FROM hr_complaints hc
LEFT JOIN users u ON u.id = hc.employee_id;


-- Message stats view per org (used by /stats endpoint)
CREATE OR REPLACE VIEW v_whatsapp_message_stats AS
SELECT
    org_id,
    DATE_TRUNC('day', created_at)   AS day,
    COUNT(*)                         AS total_messages,
    COUNT(*) FILTER (WHERE direction = 'INBOUND')  AS inbound,
    COUNT(*) FILTER (WHERE direction = 'OUTBOUND') AS outbound,
    COUNT(*) FILTER (WHERE command = 'LEAVE')      AS leave_commands,
    COUNT(*) FILTER (WHERE command = 'PAYSLIP')    AS payslip_commands,
    COUNT(*) FILTER (WHERE command = 'COMPLAINT')  AS complaint_commands,
    COUNT(*) FILTER (WHERE command = 'BALANCE')    AS balance_commands,
    COUNT(*) FILTER (WHERE command = 'SHIFT')      AS shift_commands,
    COUNT(*) FILTER (WHERE command = 'CAREER')     AS career_commands,
    COUNT(*) FILTER (WHERE command = 'HELP')       AS help_commands,
    COUNT(*) FILTER (WHERE command_status = 'FAILED') AS failed_commands,
    COUNT(*) FILTER (WHERE command = 'UNKNOWN')    AS unknown_commands
FROM whatsapp_messages
WHERE direction = 'INBOUND'
GROUP BY org_id, DATE_TRUNC('day', created_at);


-- =============================================================================
-- 7. Seed: back-fill whatsapp_users from existing hr_bot_sessions (021)
--    Creates a whatsapp_users row for every active session that has an employee.
-- =============================================================================

INSERT INTO whatsapp_users (
    phone, employee_id, org_id, display_name,
    is_verified, verified_at, verification_method,
    is_active, first_message_at, last_message_at,
    message_count, last_command, registered_by
)
SELECT
    hbs.phone,
    hbs.employee_id,
    hbs.org_id,
    COALESCE(u.email, hbs.phone)    AS display_name,
    TRUE                             AS is_verified,
    hbs.created_at                  AS verified_at,
    'phone_match'                    AS verification_method,
    hbs.is_active,
    hbs.created_at                  AS first_message_at,
    hbs.last_message_at,
    hbs.message_count,
    hbs.last_command,
    NULL                             AS registered_by
FROM hr_bot_sessions hbs
LEFT JOIN users u ON u.id = hbs.employee_id
WHERE hbs.employee_id IS NOT NULL
ON CONFLICT (phone) DO NOTHING;


COMMIT;
