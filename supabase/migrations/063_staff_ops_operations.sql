-- Staff Ops operations: overtime, shift replacement, casual workers and
-- agency compliance. Step 2 of 4 (see docs/staff-ops/DB_DESIGN.md).
--
-- Depends on 062 for staff_ops_agencies and staff_ops_employee_profiles.
BEGIN;

-- Preflight. Raw to_regclass rather than migration_requires(), because that
-- helper lives in 069 and this file must work whether or not 069 has run.
DO $$ BEGIN
    IF to_regclass('public.staff_ops_agencies') IS NULL
       OR to_regclass('public.staff_ops_designations') IS NULL THEN
        RAISE EXCEPTION
          E'Migration 062_staff_ops_core.sql has not been applied.\n'
          '063 references staff_ops_agencies and staff_ops_designations, which 062 creates.\n'
          'Apply 062 first. Run supabase/migrations/CHECK_APPLIED.sql to see what is in place.';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Overtime
-- ---------------------------------------------------------------------------
-- attendance_daily_records.overtime_minutes records that OT happened. It
-- cannot record who authorised it, at what multiplier, or whether it was
-- paid — all three of which a labour inspector asks for.
--
-- ot_multiplier is stored on the row, not looked up at read time, so a rate
-- change next year does not silently restate last year's approved overtime.
CREATE TABLE IF NOT EXISTS staff_ops_ot_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    attendance_date DATE NOT NULL,
    attendance_record_id UUID REFERENCES attendance_daily_records(id) ON DELETE SET NULL,

    ot_minutes INTEGER NOT NULL CHECK (ot_minutes > 0),
    -- Read from staff_ops_settings at approval time, never hard-coded.
    ot_multiplier NUMERIC(4,2) NOT NULL CHECK (ot_multiplier >= 1),
    hourly_rate_inr NUMERIC(10,2) CHECK (hourly_rate_inr IS NULL OR hourly_rate_inr >= 0),
    ot_amount_inr NUMERIC(12,2) CHECK (ot_amount_inr IS NULL OR ot_amount_inr >= 0),
    reason TEXT,

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','APPROVED','REJECTED','PAID','CANCELLED')),
    requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
    approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    rejection_reason TEXT,
    payroll_run_id UUID REFERENCES payroll_runs(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ot_approved_has_actor
        CHECK (status NOT IN ('APPROVED','PAID') OR approved_by IS NOT NULL),
    CONSTRAINT ot_paid_has_run
        CHECK (status <> 'PAID' OR payroll_run_id IS NOT NULL),
    -- One OT record per person per day; extra hours amend the existing row.
    UNIQUE (employee_id, attendance_date)
);

CREATE INDEX IF NOT EXISTS staff_ops_ot_property_date_idx
    ON staff_ops_ot_records(property_id, attendance_date DESC);
CREATE INDEX IF NOT EXISTS staff_ops_ot_pending_idx
    ON staff_ops_ot_records(property_id, status) WHERE status = 'PENDING';

-- ---------------------------------------------------------------------------
-- Casual (daily-wage) workers
-- ---------------------------------------------------------------------------
-- employee_id is nullable on purpose: casuals are often engaged at the staff
-- gate before any account exists, so a name and phone number must be enough
-- to record the engagement. (Design review Q5.)
CREATE TABLE IF NOT EXISTS staff_ops_casual_workers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    employee_id UUID REFERENCES users(id) ON DELETE SET NULL,
    candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,

    full_name VARCHAR(200) NOT NULL,
    phone VARCHAR(20) CHECK (phone IS NULL OR phone ~ '^\+91[6-9][0-9]{9}$'),
    preferred_language VARCHAR(5)
        CHECK (preferred_language IS NULL OR preferred_language IN ('en','hi','te','ta','kn')),

    day_rate_inr NUMERIC(10,2) CHECK (day_rate_inr IS NULL OR day_rate_inr >= 0),
    skills JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferred_departments JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- {"mon":true,"tue":false,…} — read whole, never queried per day.
    availability JSONB NOT NULL DEFAULT '{}'::jsonb,

    last_worked_on DATE,
    total_shifts INTEGER NOT NULL DEFAULT 0 CHECK (total_shifts >= 0),
    rating NUMERIC(2,1) CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),

    is_blacklisted BOOLEAN NOT NULL DEFAULT FALSE,
    blacklist_reason TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Reachable one way or another, or the pool is useless.
    CONSTRAINT casual_contactable CHECK (employee_id IS NOT NULL OR phone IS NOT NULL),
    CONSTRAINT casual_blacklist_has_reason
        CHECK (NOT is_blacklisted OR blacklist_reason IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS staff_ops_casual_available_idx
    ON staff_ops_casual_workers(property_id, is_active)
    WHERE is_active AND NOT is_blacklisted;
CREATE UNIQUE INDEX IF NOT EXISTS staff_ops_casual_phone_unique
    ON staff_ops_casual_workers(property_id, phone) WHERE phone IS NOT NULL;

CREATE TABLE IF NOT EXISTS staff_ops_casual_engagements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    casual_worker_id UUID NOT NULL REFERENCES staff_ops_casual_workers(id) ON DELETE RESTRICT,
    department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
    shift_template_id UUID REFERENCES shift_templates(id) ON DELETE SET NULL,

    work_date DATE NOT NULL,
    hours_worked NUMERIC(4,2) CHECK (hours_worked IS NULL OR hours_worked BETWEEN 0 AND 24),
    -- Which of the per-hotel pay settings applied on the day.
    rate_basis VARCHAR(12) NOT NULL DEFAULT 'PER_SHIFT'
        CHECK (rate_basis IN ('PER_DAY','PER_SHIFT','PER_HOUR')),
    rate_inr NUMERIC(10,2) NOT NULL CHECK (rate_inr >= 0),
    amount_inr NUMERIC(12,2) NOT NULL CHECK (amount_inr >= 0),

    payment_mode VARCHAR(20) NOT NULL DEFAULT 'CASH'
        CHECK (payment_mode IN ('CASH','BANK_TRANSFER','RAZORPAY_PAYOUT')),
    payment_status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (payment_status IN ('PENDING','APPROVED','PAID','CANCELLED')),
    payout_reference VARCHAR(120),

    approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    payroll_run_id UUID REFERENCES payroll_runs(id) ON DELETE SET NULL,

    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT casual_paid_has_timestamp
        CHECK (payment_status <> 'PAID' OR paid_at IS NOT NULL),
    CONSTRAINT casual_hourly_needs_hours
        CHECK (rate_basis <> 'PER_HOUR' OR hours_worked IS NOT NULL),
    -- One engagement per worker per shift per day.
    UNIQUE (casual_worker_id, work_date, shift_template_id)
);

CREATE INDEX IF NOT EXISTS staff_ops_casual_eng_date_idx
    ON staff_ops_casual_engagements(property_id, work_date DESC);
CREATE INDEX IF NOT EXISTS staff_ops_casual_eng_unpaid_idx
    ON staff_ops_casual_engagements(property_id, payment_status)
    WHERE payment_status IN ('PENDING','APPROVED');

-- ---------------------------------------------------------------------------
-- Shift offers (absence replacement)
-- ---------------------------------------------------------------------------
-- shift_swap_requests is A-asks-B. This is "someone called in sick, broadcast
-- the gap, first acceptance wins" — and recipients may be permanent staff or
-- the casual pool, which is the whole point of the replacement flow.
CREATE TABLE IF NOT EXISTS staff_ops_shift_offers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    shift_id UUID REFERENCES shifts(id) ON DELETE CASCADE,
    department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
    designation_id UUID REFERENCES staff_ops_designations(id) ON DELETE SET NULL,

    work_date DATE NOT NULL,
    reason VARCHAR(30) NOT NULL
        CHECK (reason IN ('ABSENCE','LEAVE','RESIGNATION','EXTRA_DEMAND','NO_SHOW','OTHER')),
    absent_employee_id UUID REFERENCES users(id) ON DELETE SET NULL,
    notes TEXT,
    -- Optional incentive offered to whoever picks the shift up.
    offered_rate_inr NUMERIC(10,2) CHECK (offered_rate_inr IS NULL OR offered_rate_inr >= 0),

    status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN','FILLED','EXPIRED','CANCELLED')),
    filled_by_employee_id UUID REFERENCES users(id) ON DELETE SET NULL,
    filled_by_casual_id UUID REFERENCES staff_ops_casual_workers(id) ON DELETE SET NULL,
    filled_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,

    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- A filled offer names exactly one person, of exactly one kind.
    CONSTRAINT offer_filled_has_exactly_one_taker CHECK (
        (status <> 'FILLED')
        OR (filled_at IS NOT NULL
            AND (filled_by_employee_id IS NOT NULL) <> (filled_by_casual_id IS NOT NULL))
    ),
    CONSTRAINT offer_open_has_no_taker CHECK (
        status = 'FILLED'
        OR (filled_by_employee_id IS NULL AND filled_by_casual_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS staff_ops_offers_open_idx
    ON staff_ops_shift_offers(property_id, work_date) WHERE status = 'OPEN';

CREATE TABLE IF NOT EXISTS staff_ops_shift_offer_recipients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    offer_id UUID NOT NULL REFERENCES staff_ops_shift_offers(id) ON DELETE CASCADE,

    employee_id UUID REFERENCES users(id) ON DELETE CASCADE,
    casual_worker_id UUID REFERENCES staff_ops_casual_workers(id) ON DELETE CASCADE,

    channel VARCHAR(20) NOT NULL DEFAULT 'WHATSAPP'
        CHECK (channel IN ('WHATSAPP','SMS','PUSH','IN_APP')),
    language VARCHAR(5)
        CHECK (language IS NULL OR language IN ('en','hi','te','ta','kn')),
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    responded_at TIMESTAMPTZ,
    response VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (response IN ('PENDING','ACCEPTED','DECLINED','NO_RESPONSE')),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT recipient_is_one_kind
        CHECK ((employee_id IS NOT NULL) <> (casual_worker_id IS NOT NULL)),
    CONSTRAINT recipient_responded_has_time
        CHECK (response IN ('PENDING','NO_RESPONSE') OR responded_at IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS staff_ops_offer_recipient_emp_unique
    ON staff_ops_shift_offer_recipients(offer_id, employee_id) WHERE employee_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS staff_ops_offer_recipient_casual_unique
    ON staff_ops_shift_offer_recipients(offer_id, casual_worker_id) WHERE casual_worker_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS staff_ops_offer_recipient_offer_idx
    ON staff_ops_shift_offer_recipients(offer_id, response);

-- ---------------------------------------------------------------------------
-- Agency monthly compliance
-- ---------------------------------------------------------------------------
-- PLAN decision 11: the agency invoices the hotel, so no wages are computed
-- here. What the hotel is liable for is proof the agency paid PF and ESI.
CREATE TABLE IF NOT EXISTS staff_ops_agency_monthly_compliance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    agency_id UUID NOT NULL REFERENCES staff_ops_agencies(id) ON DELETE RESTRICT,

    period_year SMALLINT NOT NULL CHECK (period_year BETWEEN 2000 AND 2100),
    period_month SMALLINT NOT NULL CHECK (period_month BETWEEN 1 AND 12),
    doc_type VARCHAR(30) NOT NULL
        CHECK (doc_type IN ('PF_CHALLAN','ESI_CHALLAN','WAGE_REGISTER',
                            'POLICE_VERIFICATION','LICENCE_RENEWAL','INVOICE')),

    document_url TEXT,
    workers_covered INTEGER CHECK (workers_covered IS NULL OR workers_covered >= 0),
    amount_inr NUMERIC(14,2) CHECK (amount_inr IS NULL OR amount_inr >= 0),
    due_date DATE,

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','SUBMITTED','VERIFIED','REJECTED','OVERDUE')),
    verified_by UUID REFERENCES users(id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ,
    rejection_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT agency_doc_submitted_has_file
        CHECK (status IN ('PENDING','OVERDUE') OR document_url IS NOT NULL),
    CONSTRAINT agency_doc_verified_has_actor
        CHECK (status <> 'VERIFIED' OR verified_by IS NOT NULL),
    UNIQUE (agency_id, period_year, period_month, doc_type)
);

CREATE INDEX IF NOT EXISTS staff_ops_agency_compliance_due_idx
    ON staff_ops_agency_monthly_compliance(property_id, due_date)
    WHERE status IN ('PENDING','OVERDUE');

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE staff_ops_ot_records                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_ops_casual_workers               ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_ops_casual_engagements           ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_ops_shift_offers                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_ops_shift_offer_recipients       ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_ops_agency_monthly_compliance    ENABLE ROW LEVEL SECURITY;

-- Rostering tables read with attendance.read; money tables with payroll.read.
DO $$ DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['staff_ops_ot_records','staff_ops_casual_engagements'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_property_read ON %I', t, t);
    EXECUTE format('DROP POLICY IF EXISTS %I_property_manage ON %I', t, t);
    EXECUTE format('CREATE POLICY %I_property_read ON %I FOR SELECT USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''payroll.read''))', t, t);
    EXECUTE format('CREATE POLICY %I_property_manage ON %I FOR ALL USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''payroll.manage'')) WITH CHECK(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''payroll.manage''))', t, t);
  END LOOP;

  FOREACH t IN ARRAY ARRAY['staff_ops_casual_workers','staff_ops_shift_offers',
                           'staff_ops_shift_offer_recipients'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_property_read ON %I', t, t);
    EXECUTE format('DROP POLICY IF EXISTS %I_property_manage ON %I', t, t);
    EXECUTE format('CREATE POLICY %I_property_read ON %I FOR SELECT USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''attendance.read''))', t, t);
    EXECUTE format('CREATE POLICY %I_property_manage ON %I FOR ALL USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''attendance.manage'')) WITH CHECK(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''attendance.manage''))', t, t);
  END LOOP;

  FOREACH t IN ARRAY ARRAY['staff_ops_agency_monthly_compliance'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_property_read ON %I', t, t);
    EXECUTE format('DROP POLICY IF EXISTS %I_property_manage ON %I', t, t);
    EXECUTE format('CREATE POLICY %I_property_read ON %I FOR SELECT USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''compliance.read''))', t, t);
    EXECUTE format('CREATE POLICY %I_property_manage ON %I FOR ALL USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''compliance.manage'')) WITH CHECK(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''compliance.manage''))', t, t);
  END LOOP;
END $$;

-- An employee sees their own OT, and a recipient sees offers sent to them.
CREATE POLICY staff_ops_ot_self_read ON staff_ops_ot_records
    FOR SELECT USING (employee_id = auth.uid() AND org_id = current_user_org_id());
CREATE POLICY staff_ops_offer_recipient_self_read ON staff_ops_shift_offer_recipients
    FOR SELECT USING (employee_id = auth.uid() AND org_id = current_user_org_id());

-- ---------------------------------------------------------------------------
-- No hard deletes on OT or payment rows
-- ---------------------------------------------------------------------------
CREATE OR REPLACE RULE staff_ops_ot_records_no_delete AS
    ON DELETE TO staff_ops_ot_records DO INSTEAD NOTHING;
CREATE OR REPLACE RULE staff_ops_casual_engagements_no_delete AS
    ON DELETE TO staff_ops_casual_engagements DO INSTEAD NOTHING;

COMMENT ON COLUMN staff_ops_ot_records.ot_multiplier IS
    'Multiplier applied on the day, from staff_ops_settings. Stored so a later rate change cannot restate approved overtime.';
COMMENT ON COLUMN staff_ops_casual_workers.employee_id IS
    'Nullable: casuals are often engaged at the gate before any account exists.';

COMMIT;
