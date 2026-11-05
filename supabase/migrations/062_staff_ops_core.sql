-- Staff Ops core employee model.
--
-- Step 1 of 4 (see docs/staff-ops/DB_DESIGN.md). Deliberately does NOT create
-- an `employees` table: 37 tables already declare `employee_id REFERENCES
-- users(id)`, so `users` IS the employee record. What lives here is only the
-- Staff Ops data that does not belong on `users`, which keeps recruiting's
-- view of `users` completely unchanged.
--
-- `staff_ops_agencies` is created here rather than in step 2 because
-- `staff_ops_employee_profiles.agency_id` depends on it.
--
-- Decisions carried in from review (29 Oct 2026):
--   Q1  Bank account numbers are NOT stored. Only the last 4 digits for
--       recognition, plus a Razorpay payout token. The safest account number
--       is one we never hold.
--   Q2  `supervisor_id` is separate from `users.manager_id` — in a hotel the
--       floor supervisor and the reporting manager are different people.
--   Q4  UAN and ESI live here, not on `epf_esic_registrations`. That table is
--       keyed to `candidate_id NOT NULL` and serves the onboarding workflow;
--       reusing it would mean making candidate_id nullable on a
--       recruiting-owned table. Hire conversion copies the numbers across.
BEGIN;

-- ---------------------------------------------------------------------------
-- Agencies (outsourced labour suppliers)
-- ---------------------------------------------------------------------------
-- Per PLAN decision 11 the agency invoices the hotel directly, so Staff Ops
-- never computes agency wages. Only the contract and its compliance are held.
CREATE TABLE IF NOT EXISTS staff_ops_agencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    name VARCHAR(200) NOT NULL,
    gstin VARCHAR(15),
    pan VARCHAR(10),
    contact_name VARCHAR(120),
    contact_phone VARCHAR(20),
    contact_email VARCHAR(255),
    contract_start DATE,
    contract_end DATE,
    -- Contract Labour (Regulation & Abolition) Act 1970 registration.
    clra_licence_number VARCHAR(50),
    clra_licence_expiry DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT agency_contract_dates CHECK (contract_end IS NULL OR contract_start IS NULL
                                            OR contract_end >= contract_start),
    UNIQUE (property_id, name)
);

CREATE INDEX IF NOT EXISTS staff_ops_agencies_property_idx
    ON staff_ops_agencies(property_id, is_active);
CREATE INDEX IF NOT EXISTS staff_ops_agencies_licence_expiry_idx
    ON staff_ops_agencies(clra_licence_expiry) WHERE is_active;

-- ---------------------------------------------------------------------------
-- Designations
-- ---------------------------------------------------------------------------
-- `users.job_title` is free text, so "Steward", "steward" and "F&B Steward"
-- are three different jobs and no report can group them. This gives each
-- hotel a controlled list.
CREATE TABLE IF NOT EXISTS staff_ops_designations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
    code VARCHAR(40) NOT NULL CHECK (code ~ '^[A-Z][A-Z0-9_]{1,39}$'),
    name VARCHAR(120) NOT NULL,
    grade VARCHAR(20),
    default_shift_template_id UUID REFERENCES shift_templates(id) ON DELETE SET NULL,
    display_order INTEGER NOT NULL DEFAULT 100,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (property_id, code)
);

CREATE INDEX IF NOT EXISTS staff_ops_designations_property_idx
    ON staff_ops_designations(property_id, department_id, is_active);

-- ---------------------------------------------------------------------------
-- Employee profiles — the Staff Ops extension of `users`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staff_ops_employee_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,

    -- The employee IS a users row. One profile per person per deployment.
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Set when the person arrived through recruiting; NULL for direct hires.
    candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,
    designation_id UUID REFERENCES staff_ops_designations(id) ON DELETE SET NULL,

    staff_type VARCHAR(20) NOT NULL DEFAULT 'PERMANENT'
        CHECK (staff_type IN ('PERMANENT','TRAINEE','INDUSTRIAL_TRAINEE','AGENCY','CASUAL')),
    agency_id UUID REFERENCES staff_ops_agencies(id) ON DELETE RESTRICT,

    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE','ON_NOTICE','LEFT','ABSCONDING')),
    joining_date DATE,
    notice_start_date DATE,
    leaving_date DATE,
    leaving_reason TEXT,

    -- Rostering defaults. 0 = Sunday, matching PostgreSQL's EXTRACT(DOW).
    default_weekly_off SMALLINT CHECK (default_weekly_off BETWEEN 0 AND 6),
    default_shift_template_id UUID REFERENCES shift_templates(id) ON DELETE SET NULL,

    -- Which departments and roles this person can cover, for replacements.
    -- JSONB because it is a short list always read whole, never queried
    -- field-by-field: [{"department_id":…,"designation_id":…,"proficiency":"PRIMARY"}]
    skills JSONB NOT NULL DEFAULT '[]'::jsonb,

    biometric_id VARCHAR(50),

    -- A hotel supervisor is not the same person as the reporting manager
    -- (users.manager_id), so both are kept.
    supervisor_id UUID REFERENCES users(id) ON DELETE SET NULL,

    wage_type VARCHAR(12) NOT NULL DEFAULT 'MONTHLY'
        CHECK (wage_type IN ('MONTHLY','DAILY','HOURLY','PER_SHIFT')),
    wage_amount_inr NUMERIC(12,2) CHECK (wage_amount_inr IS NULL OR wage_amount_inr >= 0),

    -- Statutory identifiers. Aadhaar is deliberately absent: it lives only on
    -- india_identity_verifications, last 4 digits only, per UIDAI rules.
    uan VARCHAR(15) CHECK (uan IS NULL OR uan ~ '^[0-9]{12}$'),
    esic_ip_number VARCHAR(20),

    -- Banking: the full account number is NEVER stored (review Q1). The last
    -- four digits let a clerk recognise the account; the payout token is the
    -- Razorpay fund-account reference used to actually pay.
    bank_name VARCHAR(120),
    bank_account_last4 CHAR(4) CHECK (bank_account_last4 IS NULL OR bank_account_last4 ~ '^[0-9]{4}$'),
    bank_ifsc VARCHAR(11) CHECK (bank_ifsc IS NULL OR bank_ifsc ~ '^[A-Z]{4}0[A-Z0-9]{6}$'),
    payout_token VARCHAR(120),

    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT employee_profile_leaving_after_joining
        CHECK (leaving_date IS NULL OR joining_date IS NULL OR leaving_date >= joining_date),
    CONSTRAINT employee_profile_notice_after_joining
        CHECK (notice_start_date IS NULL OR joining_date IS NULL OR notice_start_date >= joining_date),
    -- Agency staff must name their agency; nobody else may.
    CONSTRAINT employee_profile_agency_required
        CHECK ((staff_type = 'AGENCY') = (agency_id IS NOT NULL)),
    -- Someone who has left needs a leaving date on record.
    CONSTRAINT employee_profile_left_has_date
        CHECK (status <> 'LEFT' OR leaving_date IS NOT NULL),
    -- Nobody supervises themselves.
    CONSTRAINT employee_profile_supervisor_not_self
        CHECK (supervisor_id IS NULL OR supervisor_id <> employee_id),

    UNIQUE (employee_id, property_id)
);

CREATE INDEX IF NOT EXISTS staff_ops_profiles_property_status_idx
    ON staff_ops_employee_profiles(property_id, status);
CREATE INDEX IF NOT EXISTS staff_ops_profiles_employee_idx
    ON staff_ops_employee_profiles(employee_id);
CREATE INDEX IF NOT EXISTS staff_ops_profiles_supervisor_idx
    ON staff_ops_employee_profiles(supervisor_id) WHERE supervisor_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS staff_ops_profiles_agency_idx
    ON staff_ops_employee_profiles(agency_id) WHERE agency_id IS NOT NULL;
-- One candidate converts to one employee; a second conversion is a bug.
CREATE UNIQUE INDEX IF NOT EXISTS staff_ops_profiles_candidate_unique
    ON staff_ops_employee_profiles(candidate_id) WHERE candidate_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS staff_ops_profiles_biometric_unique
    ON staff_ops_employee_profiles(property_id, biometric_id) WHERE biometric_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Employee documents
-- ---------------------------------------------------------------------------
-- Mirrors candidate_documents and reuses the same S3 path (ap-south-1,
-- presigned uploads). `source_document_id` records lineage when a document is
-- copied across on hire (PLAN decision 4: copy, do not move).
CREATE TABLE IF NOT EXISTS staff_ops_employee_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_document_id UUID REFERENCES candidate_documents(id) ON DELETE SET NULL,

    doc_type VARCHAR(40) NOT NULL
        CHECK (doc_type IN ('ID_PROOF','ADDRESS_PROOF','PHOTO','CERTIFICATE',
                            'CONTRACT','APPOINTMENT_LETTER','BANK_PROOF',
                            'POLICE_VERIFICATION','MEDICAL','OTHER')),
    -- S3 object key, never a public URL. Access is via presigned GET.
    document_url TEXT NOT NULL,
    file_name VARCHAR(255),
    mime_type VARCHAR(100),
    size_bytes BIGINT CHECK (size_bytes IS NULL OR size_bytes >= 0),
    expires_on DATE,

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','VERIFIED','REJECTED','EXPIRED','SUPERSEDED')),
    verified_by UUID REFERENCES users(id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ,
    rejection_reason TEXT,

    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT employee_document_verified_has_actor
        CHECK (status <> 'VERIFIED' OR verified_by IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS staff_ops_emp_docs_employee_idx
    ON staff_ops_employee_documents(employee_id, doc_type);
CREATE INDEX IF NOT EXISTS staff_ops_emp_docs_expiry_idx
    ON staff_ops_employee_documents(property_id, expires_on)
    WHERE expires_on IS NOT NULL AND status = 'VERIFIED';

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
-- Same shape as every other property-scoped table in this schema: the policy
-- itself checks the permission, so a user can only ever see hotels they have
-- access to even if application code forgets to filter.
ALTER TABLE staff_ops_agencies             ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_ops_designations         ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_ops_employee_profiles    ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_ops_employee_documents   ENABLE ROW LEVEL SECURITY;

DO $$ DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['staff_ops_agencies','staff_ops_designations',
                           'staff_ops_employee_profiles','staff_ops_employee_documents'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_property_read ON %I', t, t);
    EXECUTE format('DROP POLICY IF EXISTS %I_property_manage ON %I', t, t);
    EXECUTE format('CREATE POLICY %I_property_read ON %I FOR SELECT USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''employees.read''))', t, t);
    EXECUTE format('CREATE POLICY %I_property_manage ON %I FOR ALL USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''employees.manage'')) WITH CHECK(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''employees.manage''))', t, t);
  END LOOP;
END $$;

-- A staff member can always read their own profile and their own documents,
-- which is what the employee PWA needs without granting employees.read.
CREATE POLICY staff_ops_profile_self_read ON staff_ops_employee_profiles
    FOR SELECT USING (employee_id = auth.uid() AND org_id = current_user_org_id());
CREATE POLICY staff_ops_emp_docs_self_read ON staff_ops_employee_documents
    FOR SELECT USING (employee_id = auth.uid() AND org_id = current_user_org_id());

-- ---------------------------------------------------------------------------
-- No hard deletes
-- ---------------------------------------------------------------------------
-- An employee record is history: it is referenced by attendance, leave,
-- payroll and audit rows. Status moves to LEFT or ABSCONDING instead. The rule
-- makes this true even for direct SQL, not merely for application code.
CREATE OR REPLACE RULE staff_ops_employee_profiles_no_delete AS
    ON DELETE TO staff_ops_employee_profiles DO INSTEAD NOTHING;
CREATE OR REPLACE RULE staff_ops_employee_documents_no_delete AS
    ON DELETE TO staff_ops_employee_documents DO INSTEAD NOTHING;

COMMENT ON TABLE staff_ops_employee_profiles IS
    'Staff Ops extension of users. users IS the employee record; this holds only Staff Ops fields.';
COMMENT ON COLUMN staff_ops_employee_profiles.bank_account_last4 IS
    'Last 4 digits only. Full account numbers are never stored; payout_token references Razorpay.';
COMMENT ON COLUMN staff_ops_employee_profiles.supervisor_id IS
    'Floor supervisor. Distinct from users.manager_id, the reporting manager.';

COMMIT;
