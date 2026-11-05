-- Staff Ops governance: settings, audit log, month close, and the fixes to
-- leave_requests and properties. Step 3 of 4 (docs/staff-ops/DB_DESIGN.md).
BEGIN;

-- ---------------------------------------------------------------------------
-- Settings — every labour-law value lives here
-- ---------------------------------------------------------------------------
-- properties.*_settings JSONB already exists but has no history, so it cannot
-- answer "what was the OT multiplier last March?". `valid_from` makes a rate
-- change a new row, leaving last month's payroll reproducible.
--
-- This replaces the module constants OT_RATE_MULTIPLIER, MAX_OT_PER_DAY_H,
-- DAILY_STANDARD_HOURS and EPF_EMPLOYER_CONTRIB_PCT.
CREATE TABLE IF NOT EXISTS staff_ops_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    -- NULL = an organisation-wide default for every hotel.
    property_id UUID REFERENCES properties(id) ON DELETE CASCADE,

    key VARCHAR(80) NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{1,79}$'),
    value JSONB NOT NULL,
    value_type VARCHAR(12) NOT NULL DEFAULT 'NUMBER'
        CHECK (value_type IN ('NUMBER','STRING','BOOLEAN','JSON')),
    description TEXT,
    -- Statutory values differ by state; recorded so an audit can show why.
    state_code VARCHAR(3),

    valid_from DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to DATE,

    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT setting_valid_range CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

-- One value per key per scope per start date. Two partial indexes because
-- NULL property_id (org-wide) would otherwise never collide with itself.
CREATE UNIQUE INDEX IF NOT EXISTS staff_ops_settings_property_key_unique
    ON staff_ops_settings(property_id, key, valid_from) WHERE property_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS staff_ops_settings_org_key_unique
    ON staff_ops_settings(org_id, key, valid_from) WHERE property_id IS NULL;
CREATE INDEX IF NOT EXISTS staff_ops_settings_lookup_idx
    ON staff_ops_settings(key, valid_from DESC);

-- Resolution order: hotel-specific newest first, then org-wide, then the code
-- default. Returns NULL when nothing is configured, so callers keep their own
-- fallback rather than this inventing a statutory rate.
CREATE OR REPLACE FUNCTION staff_ops_setting(
    p_property_id UUID,
    p_key VARCHAR,
    p_on_date DATE DEFAULT CURRENT_DATE
) RETURNS JSONB LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT value FROM staff_ops_settings
     WHERE key = p_key
       AND valid_from <= p_on_date
       AND (valid_to IS NULL OR valid_to >= p_on_date)
       AND (property_id = p_property_id OR property_id IS NULL)
     ORDER BY (property_id IS NOT NULL) DESC, valid_from DESC
     LIMIT 1;
$$;

-- ---------------------------------------------------------------------------
-- Audit log
-- ---------------------------------------------------------------------------
-- PLAN decision 6: the nine existing audit tables stay as they are; this one
-- serves new Staff Ops features only.
CREATE TABLE IF NOT EXISTS staff_ops_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,

    -- NULL for cron and webhook actions; `source` says which.
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(40) NOT NULL
        CHECK (action IN ('CREATE','UPDATE','DELETE','APPROVE','REJECT','ESCALATE',
                          'CANCEL','LOCK','UNLOCK','CLOSE','REOPEN','PAY','IMPORT','EXPORT')),
    entity_type VARCHAR(60) NOT NULL,
    entity_id UUID,
    -- Whose record this touched, which is the question auditors actually ask.
    employee_id UUID REFERENCES users(id) ON DELETE SET NULL,

    old_value JSONB,
    new_value JSONB,
    changed_fields TEXT[],
    reason TEXT,

    source VARCHAR(20) NOT NULL DEFAULT 'WEB'
        CHECK (source IN ('WEB','MOBILE','WHATSAPP','BIOMETRIC','SYSTEM','API','IMPORT')),
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS staff_ops_audit_entity_idx
    ON staff_ops_audit_log(property_id, entity_type, entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS staff_ops_audit_employee_idx
    ON staff_ops_audit_log(employee_id, created_at DESC) WHERE employee_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS staff_ops_audit_actor_idx
    ON staff_ops_audit_log(actor_id, created_at DESC);

-- An audit log that can be edited is not an audit log.
CREATE OR REPLACE RULE staff_ops_audit_log_no_update AS
    ON UPDATE TO staff_ops_audit_log DO INSTEAD NOTHING;
CREATE OR REPLACE RULE staff_ops_audit_log_no_delete AS
    ON DELETE TO staff_ops_audit_log DO INSTEAD NOTHING;

-- ---------------------------------------------------------------------------
-- Month close
-- ---------------------------------------------------------------------------
-- Review Q3: no grace window. Once ATTENDANCE_LOCKED, corrections are refused
-- outright; reopening is a separate, logged act.
CREATE TABLE IF NOT EXISTS staff_ops_month_close (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,

    period_year SMALLINT NOT NULL CHECK (period_year BETWEEN 2000 AND 2100),
    period_month SMALLINT NOT NULL CHECK (period_month BETWEEN 1 AND 12),

    status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN','ATTENDANCE_LOCKED','CLOSED','REOPENED')),

    attendance_locked_at TIMESTAMPTZ,
    attendance_locked_by UUID REFERENCES users(id) ON DELETE SET NULL,
    closed_at TIMESTAMPTZ,
    closed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reopened_at TIMESTAMPTZ,
    reopened_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reopen_reason TEXT,

    totals JSONB NOT NULL DEFAULT '{}'::jsonb,
    payroll_run_id UUID REFERENCES payroll_runs(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT month_locked_has_actor
        CHECK (status = 'OPEN' OR attendance_locked_by IS NOT NULL),
    CONSTRAINT month_closed_has_actor
        CHECK (status <> 'CLOSED' OR closed_by IS NOT NULL),
    -- Reopening a month is deliberate and must be explained.
    CONSTRAINT month_reopen_has_reason
        CHECK (status <> 'REOPENED' OR (reopened_by IS NOT NULL AND reopen_reason IS NOT NULL)),
    UNIQUE (property_id, period_year, period_month)
);

CREATE INDEX IF NOT EXISTS staff_ops_month_close_lookup_idx
    ON staff_ops_month_close(property_id, period_year, period_month);

-- True when the period is locked against attendance edits. The API checks
-- this before accepting any attendance, leave, OT or casual-engagement write.
CREATE OR REPLACE FUNCTION staff_ops_period_locked(
    p_property_id UUID,
    p_date DATE
) RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT COALESCE(
        (SELECT status IN ('ATTENDANCE_LOCKED','CLOSED')
           FROM staff_ops_month_close
          WHERE property_id = p_property_id
            AND period_year = EXTRACT(YEAR FROM p_date)::SMALLINT
            AND period_month = EXTRACT(MONTH FROM p_date)::SMALLINT
          LIMIT 1),
        FALSE);
$$;

-- ---------------------------------------------------------------------------
-- leave_requests: date range, hotel scope, escalation
-- ---------------------------------------------------------------------------
-- Three defects, all user-visible:
--   1. `leave_date` is a SINGLE day, so three-day leave cannot be recorded.
--   2. No property_id, breaking the hotel-isolation rule.
--   3. No escalation path, which PLAN decision 2 requires (a supervisor may
--      approve, or pass the request to the Department Head).
--
-- `leave_date` is read by six call sites (attendance.py, hr_bot.py,
-- workforce_schedules.py, employee_360_service.py, hr_bot_service.py), so it
-- is kept and synchronised by trigger rather than dropped.
ALTER TABLE leave_requests
    ADD COLUMN IF NOT EXISTS property_id UUID REFERENCES properties(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS from_date DATE,
    ADD COLUMN IF NOT EXISTS to_date DATE,
    ADD COLUMN IF NOT EXISTS days_requested NUMERIC(4,1),
    ADD COLUMN IF NOT EXISTS escalated_to UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS escalated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS decided_by UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS half_day BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill: every existing row is a one-day request.
UPDATE leave_requests
   SET from_date = leave_date,
       to_date = COALESCE(to_date, leave_date),
       days_requested = COALESCE(days_requested, 1)
 WHERE from_date IS NULL AND leave_date IS NOT NULL;

-- Backfill the hotel from the employee's active property where known. Rows
-- whose employee has no active property stay NULL; the API requires
-- property_id on new rows, so this converges without a failing NOT NULL.
UPDATE leave_requests lr
   SET property_id = u.active_property_id
  FROM users u
 WHERE lr.employee_id = u.id
   AND lr.property_id IS NULL
   AND u.active_property_id IS NOT NULL;

DO $$ BEGIN
    ALTER TABLE leave_requests ADD CONSTRAINT leave_request_date_range
        CHECK (to_date IS NULL OR from_date IS NULL OR to_date >= from_date);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE leave_requests ADD CONSTRAINT leave_request_escalation_complete
        CHECK (escalated_to IS NULL OR escalated_at IS NOT NULL);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Keeps the old single-date column and the new range in step, in both
-- directions, so existing readers and writers continue to work unchanged.
CREATE OR REPLACE FUNCTION leave_request_sync_dates()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    -- Legacy writer: only leave_date supplied.
    IF NEW.from_date IS NULL AND NEW.leave_date IS NOT NULL THEN
        NEW.from_date := NEW.leave_date;
    END IF;
    -- New writer: range supplied, mirror the first day back to leave_date.
    IF NEW.from_date IS NOT NULL THEN
        NEW.leave_date := NEW.from_date;
        IF NEW.to_date IS NULL THEN
            NEW.to_date := NEW.from_date;
        END IF;
    END IF;
    IF NEW.days_requested IS NULL AND NEW.from_date IS NOT NULL AND NEW.to_date IS NOT NULL THEN
        NEW.days_requested := CASE WHEN NEW.half_day THEN 0.5
                                   ELSE (NEW.to_date - NEW.from_date) + 1 END;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS leave_request_sync_dates_trg ON leave_requests;
CREATE TRIGGER leave_request_sync_dates_trg
    BEFORE INSERT OR UPDATE ON leave_requests
    FOR EACH ROW EXECUTE FUNCTION leave_request_sync_dates();

CREATE INDEX IF NOT EXISTS leave_requests_property_range_idx
    ON leave_requests(property_id, from_date, to_date);
CREATE INDEX IF NOT EXISTS leave_requests_escalated_idx
    ON leave_requests(escalated_to) WHERE escalated_to IS NOT NULL;

COMMENT ON COLUMN leave_requests.leave_date IS
    'DEPRECATED — first day of the range. Kept in sync with from_date by trigger for existing readers.';

-- ---------------------------------------------------------------------------
-- properties: Staff Ops flag and the India timezone
-- ---------------------------------------------------------------------------
ALTER TABLE properties
    ADD COLUMN IF NOT EXISTS staff_ops_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- Review decision 12. The default was 'UTC' on an India-only product, which
-- puts a 22:00-06:00 night shift on the wrong calendar day.
ALTER TABLE properties ALTER COLUMN timezone SET DEFAULT 'Asia/Kolkata';
UPDATE properties
   SET timezone = 'Asia/Kolkata'
 WHERE timezone IS NULL OR timezone = '' OR timezone = 'UTC';

-- ---------------------------------------------------------------------------
-- No hard deletes on attendance and leave
-- ---------------------------------------------------------------------------
-- Verified first that no application code deletes from these tables, and that
-- DPDP erasure removes S3 objects rather than rows. Statutory retention under
-- the Shops & Establishments Acts requires these records be kept regardless.
CREATE OR REPLACE RULE attendance_daily_records_no_delete AS
    ON DELETE TO attendance_daily_records DO INSTEAD NOTHING;
CREATE OR REPLACE RULE attendance_punches_no_delete AS
    ON DELETE TO attendance_punches DO INSTEAD NOTHING;
CREATE OR REPLACE RULE leave_requests_no_delete AS
    ON DELETE TO leave_requests DO INSTEAD NOTHING;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE staff_ops_settings     ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_ops_audit_log    ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_ops_month_close  ENABLE ROW LEVEL SECURITY;

-- Settings are org-wide when property_id IS NULL, so the property check is
-- skipped for those rows rather than hiding the organisation's defaults.
DROP POLICY IF EXISTS staff_ops_settings_read ON staff_ops_settings;
CREATE POLICY staff_ops_settings_read ON staff_ops_settings
    FOR SELECT USING (
        org_id = current_user_org_id()
        AND (property_id IS NULL OR has_property_access(property_id))
        AND rbac_has_permission('properties.read'));

DROP POLICY IF EXISTS staff_ops_settings_manage ON staff_ops_settings;
CREATE POLICY staff_ops_settings_manage ON staff_ops_settings
    FOR ALL USING (
        org_id = current_user_org_id()
        AND (property_id IS NULL OR has_property_access(property_id))
        AND rbac_has_permission('properties.manage'))
    WITH CHECK (
        org_id = current_user_org_id()
        AND (property_id IS NULL OR has_property_access(property_id))
        AND rbac_has_permission('properties.manage'));

DO $$ DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['staff_ops_audit_log','staff_ops_month_close'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_property_read ON %I', t, t);
    EXECUTE format('DROP POLICY IF EXISTS %I_property_manage ON %I', t, t);
    EXECUTE format('CREATE POLICY %I_property_read ON %I FOR SELECT USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''reports.read''))', t, t);
    EXECUTE format('CREATE POLICY %I_property_manage ON %I FOR ALL USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''payroll.manage'')) WITH CHECK(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''payroll.manage''))', t, t);
  END LOOP;
END $$;

COMMENT ON FUNCTION staff_ops_setting IS
    'Resolve a setting: hotel-specific newest first, then org-wide, else NULL.';
COMMENT ON FUNCTION staff_ops_period_locked IS
    'True when attendance for that month is locked or closed. No grace window.';

COMMIT;
