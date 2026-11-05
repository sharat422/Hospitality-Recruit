-- Configurable attendance codes (P, WO, CL, SL, EL, CO, LWP, A, HD, H, OD).
--
-- Codes are per hotel, not an enum, because what a code does to pay and to
-- leave balance differs by hotel and by state, and changes over time. The
-- single bridge to payroll is `lop_factor`: loss-of-pay days are the sum of
-- lop_factor across a month, so a half day costs 0.5 and nothing else has to
-- know what "HD" means.
--
-- Migration 036 restricted attendance_daily_records.status to six values.
-- That CHECK is replaced here with a format guard, because the valid set now
-- lives in attendance_codes and an admin may add to it.
BEGIN;

CREATE TABLE IF NOT EXISTS attendance_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    code VARCHAR(8) NOT NULL CHECK (code ~ '^[A-Z][A-Z_]{0,7}$'),
    label_en VARCHAR(60) NOT NULL,
    label_hi VARCHAR(60),
    -- Share of a day's pay lost: 0 = fully paid, 0.5 = half day, 1 = unpaid.
    lop_factor NUMERIC(3,2) NOT NULL DEFAULT 0
        CHECK (lop_factor >= 0 AND lop_factor <= 1),
    -- Whether the day feeds worked-hours and overtime calculations.
    counts_as_worked BOOLEAN NOT NULL DEFAULT FALSE,
    -- Leave balance this code draws down, if any.
    consumes_leave_type VARCHAR(20)
        CHECK (consumes_leave_type IS NULL OR consumes_leave_type IN
               ('CASUAL','SICK','EARNED','COMP_OFF','MATERNITY','PATERNITY')),
    requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
    -- Code-specific rules, e.g. comp-off earning basis and expiry window.
    rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    display_order INTEGER NOT NULL DEFAULT 100,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (property_id, code)
);

CREATE INDEX IF NOT EXISTS attendance_codes_property_idx
    ON attendance_codes(property_id, is_active);

-- Comp-off earned by working a weekly off or holiday. One row per earned day,
-- so expiry is per-day rather than a single decaying balance.
CREATE TABLE IF NOT EXISTS comp_off_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    earned_for_date DATE NOT NULL,
    earned_on DATE NOT NULL DEFAULT CURRENT_DATE,
    expires_on DATE NOT NULL,
    consumed_on DATE,
    consumed_attendance_date DATE,
    status VARCHAR(12) NOT NULL DEFAULT 'AVAILABLE'
        CHECK (status IN ('AVAILABLE','CONSUMED','EXPIRED')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (expires_on >= earned_on),
    -- Working one weekly off earns one comp-off day, never two.
    UNIQUE (employee_id, earned_for_date)
);

CREATE INDEX IF NOT EXISTS comp_off_available_idx
    ON comp_off_ledger(employee_id, status, expires_on);

-- The valid code set is now data, so the DB guards shape only.
ALTER TABLE attendance_daily_records
    DROP CONSTRAINT IF EXISTS attendance_daily_records_status_check;
ALTER TABLE attendance_daily_records
    ADD CONSTRAINT attendance_daily_records_status_format
    CHECK (status ~ '^[A-Z][A-Z_]{0,23}$');

ALTER TABLE attendance_codes  ENABLE ROW LEVEL SECURITY;
ALTER TABLE comp_off_ledger   ENABLE ROW LEVEL SECURITY;

DO $$ DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['attendance_codes','comp_off_ledger'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_property_read ON %I', t, t);
    EXECUTE format('DROP POLICY IF EXISTS %I_property_manage ON %I', t, t);
    EXECUTE format('CREATE POLICY %I_property_read ON %I FOR SELECT USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''attendance.read''))', t, t);
    EXECUTE format('CREATE POLICY %I_property_manage ON %I FOR ALL USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''attendance.manage'')) WITH CHECK(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''attendance.manage''))', t, t);
  END LOOP;
END $$;

-- A staff member can always see their own comp-off balance.
CREATE POLICY comp_off_self_read ON comp_off_ledger
    FOR SELECT USING (employee_id = auth.uid() AND org_id = current_user_org_id());

COMMIT;
