-- ============================================================================
-- Migration 014 — Feature 06 India: India-Specific Compliance
--
-- Replaces Western compliance (GDPR, CCPA, EEO, I-9, Fair Workweek, UK RTW)
-- with India-specific compliance law:
--
--  Dropped (Western):
--    right_to_work_checks       → india_identity_verifications
--    visa_types                 → (removed — domestic hiring)
--    fair_workweek_rules        → labour_code_compliance
--    scheduling_compliance_log  → working_hours_compliance
--    data_consent_records       → dpdp_consent_records
--    erasure_requests           → dpdp_erasure_requests
--    eeo_data                   → india_diversity_data
--    candidates.blind_screening → (removed — no India law requires this)
--
--  Created (India):
--    india_identity_verifications   Aadhaar / PAN / DigiLocker / Passport
--    epf_esic_registrations         EPF UAN, ESIC IP number, contribution %
--    india_minimum_wages            State/sector minimum wages (INR)
--    labour_code_compliance         India's 4 Labour Codes
--    working_hours_compliance       Factories Act / Shops & Establishment
--    professional_tax_records       State-wise Professional Tax
--    dpdp_consent_records           DPDP Act 2023 consent
--    dpdp_erasure_requests          DPDP right to erasure / correction
--    fssai_certificates             Food Safety (FSSAI) — hospitality critical
--    india_diversity_data           SC/ST/OBC/PWD/Ex-servicemen (voluntary)
--    india_compliance_audit_logs    India-specific audit trail
--
-- Currency: INR throughout. No foreign currency assumptions.
-- RLS: Org isolation on all tables (service-role bypasses for worker jobs).
-- ============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 1 — Remove Western compliance tables
-- ─────────────────────────────────────────────────────────────────────────────

DROP TABLE IF EXISTS right_to_work_checks;
DROP TABLE IF EXISTS visa_types;
DROP TABLE IF EXISTS fair_workweek_rules;
DROP TABLE IF EXISTS scheduling_compliance_log;
DROP TABLE IF EXISTS data_consent_records;
DROP TABLE IF EXISTS erasure_requests;
DROP TABLE IF EXISTS eeo_data;

-- Remove Western-specific candidate columns
ALTER TABLE candidates DROP COLUMN IF EXISTS blind_screening;

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 2 — India Identity Verifications
--             (Replaces right_to_work_checks / US I-9 / UK RTW)
--
-- Covers: Aadhaar, PAN, DigiLocker, Voter ID, Passport, Driving Licence
-- Security: Raw Aadhaar number MUST NOT be stored (UIDAI mandate).
--           Store only the last 4 digits (for display) + verification status.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS india_identity_verifications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_id        UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,

    -- Document type
    doc_type            VARCHAR(30) NOT NULL,
    -- AADHAAR | PAN | DIGILOCKER | VOTER_ID | PASSPORT | DRIVING_LICENCE | BIRTH_CERT

    -- Aadhaar: store only last 4 digits (UIDAI mandate — full number forbidden)
    aadhaar_last4       CHAR(4),
    aadhaar_masked      VARCHAR(20),          -- "XXXX XXXX 1234"
    aadhaar_verified_at TIMESTAMP,

    -- PAN (10-char alphanumeric — public info, safe to store)
    pan_number          VARCHAR(10),
    pan_name_match      BOOLEAN DEFAULT FALSE,
    pan_verified_at     TIMESTAMP,

    -- DigiLocker (document ID / URI issued by NIC)
    digilocker_uri      TEXT,
    digilocker_doc_type VARCHAR(50),          -- e.g. "driving-licence", "marksheet"

    -- Generic document fields
    doc_number_last4    CHAR(4),             -- last 4 of any ID (display only)
    doc_expiry_date     DATE,
    doc_issuing_state   VARCHAR(50),

    -- Verification lifecycle
    status              VARCHAR(20) DEFAULT 'PENDING',
    -- PENDING | UPLOADED | UNDER_REVIEW | VERIFIED | REJECTED | EXPIRED

    verified_by         UUID REFERENCES users(id),
    verified_at         TIMESTAMP,
    rejection_reason    TEXT,

    -- Document image stored in S3 (URL reference, not binary)
    doc_image_url       TEXT,
    upload_token        UUID DEFAULT gen_random_uuid() UNIQUE,

    -- Expiry alerts (for Passport, Driving Licence)
    alert_30_day_sent   BOOLEAN DEFAULT FALSE,
    alert_7_day_sent    BOOLEAN DEFAULT FALSE,
    alert_expired_sent  BOOLEAN DEFAULT FALSE,

    notes               TEXT,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS identity_verif_candidate ON india_identity_verifications(candidate_id);
CREATE INDEX IF NOT EXISTS identity_verif_status    ON india_identity_verifications(org_id, status);
CREATE INDEX IF NOT EXISTS identity_verif_token     ON india_identity_verifications(upload_token);

-- Candidate convenience columns (India-specific)
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS aadhaar_verified  BOOLEAN DEFAULT FALSE;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS pan_verified      BOOLEAN DEFAULT FALSE;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS fssai_trained     BOOLEAN DEFAULT FALSE;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS epf_uan           VARCHAR(15);

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 3 — EPF / ESIC Registrations
--             (Employee Provident Fund + Employee State Insurance)
--
-- EPF:  Mandatory for establishments with ≥ 20 employees
--       Employee contributes 12% of Basic+DA, Employer 12% (8.33% EPS + 3.67% EPF)
-- ESIC: Mandatory for establishments with ≥ 10 employees, wage ≤ ₹21,000/month
--       Employee 0.75% of gross wages, Employer 3.25% of gross wages
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS epf_esic_registrations (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                 UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_id           UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,

    -- EPF details
    epf_uan                VARCHAR(15) UNIQUE,        -- 12-digit Universal Account Number
    epf_account_number     VARCHAR(22),               -- Format: MH/BAN/12345/000/0000001
    epf_member_id          VARCHAR(22),
    epf_joining_date       DATE,
    epf_exit_date          DATE,
    epf_employee_contrib_pct NUMERIC(5,2) DEFAULT 12.00,   -- %
    epf_employer_contrib_pct NUMERIC(5,2) DEFAULT 12.00,   -- %
    eps_contrib_pct          NUMERIC(5,2) DEFAULT 8.33,    -- Employer EPS contribution %
    epf_wage_ceiling_inr     NUMERIC(12,2) DEFAULT 15000,  -- EPF wage ceiling (₹15,000)

    -- ESIC details
    esic_ip_number         VARCHAR(20) UNIQUE,        -- Insured Person (IP) number
    esic_dispensary_code   VARCHAR(10),
    esic_employee_contrib_pct NUMERIC(5,2) DEFAULT 0.75,
    esic_employer_contrib_pct NUMERIC(5,2) DEFAULT 3.25,
    esic_eligible          BOOLEAN DEFAULT FALSE,     -- wage ≤ ₹21,000/month
    esic_monthly_wage_inr  NUMERIC(12,2),

    -- Nomination
    nominee_name           VARCHAR(255),
    nominee_relation       VARCHAR(50),
    nominee_aadhaar_last4  CHAR(4),

    status                 VARCHAR(20) DEFAULT 'PENDING',
    -- PENDING | ACTIVE | INACTIVE | TRANSFERRED | SETTLED

    created_at             TIMESTAMP DEFAULT NOW(),
    updated_at             TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS epf_esic_candidate ON epf_esic_registrations(candidate_id);
CREATE INDEX IF NOT EXISTS epf_esic_org       ON epf_esic_registrations(org_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS epf_uan_idx  ON epf_esic_registrations(epf_uan) WHERE epf_uan IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 4 — India Minimum Wages
--             (Minimum Wages Act 1948 + Code on Wages 2019)
--
-- Floor wage (Central): ₹176/day (2024). States may set higher.
-- Skill categories: UNSKILLED | SEMI_SKILLED | SKILLED | HIGHLY_SKILLED
-- Hospitality is a Scheduled Employment under the Act.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS india_minimum_wages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_code      VARCHAR(5)   NOT NULL,            -- MH, KA, DL, TN, GJ, RJ, WB, GA, UP, TS, AP, KL
    state_name      VARCHAR(100) NOT NULL,
    zone            VARCHAR(5)   DEFAULT 'A',         -- A, B, C (some states have wage zones)
    skill_category  VARCHAR(20)  NOT NULL,            -- UNSKILLED | SEMI_SKILLED | SKILLED | HIGHLY_SKILLED
    sector          VARCHAR(100) DEFAULT 'Hotels and Restaurants',
    daily_wage_inr  NUMERIC(10,2) NOT NULL,
    monthly_wage_inr NUMERIC(12,2) NOT NULL,
    effective_from  DATE NOT NULL,
    effective_to    DATE,                             -- NULL = currently applicable
    is_current      BOOLEAN DEFAULT TRUE,
    source          VARCHAR(200),                     -- Gazette reference
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS min_wages_state ON india_minimum_wages(state_code, skill_category, is_current);

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 5 — Labour Code Compliance
--             India's 4 Labour Codes (replacing Fair Workweek rules)
--
-- Code 1: Code on Wages, 2019
-- Code 2: Industrial Relations Code, 2020
-- Code 3: Code on Social Security, 2020
-- Code 4: Occupational Safety, Health and Working Conditions Code, 2020
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS labour_code_compliance (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    labour_code     VARCHAR(30) NOT NULL,
    -- WAGES | INDUSTRIAL_RELATIONS | SOCIAL_SECURITY | OSH

    rule_type       VARCHAR(100) NOT NULL,
    -- e.g. MIN_WAGE | OVERTIME_RATE | EQUAL_PAY | EPF_THRESHOLD | GRATUITY |
    --       MATERNITY | SAFETY_COMMITTEE | FIRE_SAFETY | WORKING_HOURS

    state_code      VARCHAR(5),           -- NULL = Central/National rule
    state_name      VARCHAR(100),
    rule_detail     JSONB DEFAULT '{}',   -- Structured rule data
    description     TEXT,
    threshold_value NUMERIC(15,2),        -- e.g. 20 (employees), 15000 (wage ceiling INR)
    threshold_unit  VARCHAR(30),          -- EMPLOYEES | INR | HOURS | DAYS | PERCENT

    is_compliant    BOOLEAN,
    compliance_note TEXT,
    assessed_at     TIMESTAMP,
    assessed_by     UUID REFERENCES users(id),

    effective_date  DATE,
    notified_date   DATE,                 -- When the code was notified in this state
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS labour_code_org    ON labour_code_compliance(org_id, labour_code);
CREATE INDEX IF NOT EXISTS labour_code_state  ON labour_code_compliance(state_code, labour_code);

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 6 — Working Hours Compliance
--             (Replaces Fair Workweek scheduling_compliance_log)
--
-- Factories Act 1948:   Max 9 hrs/day, 48 hrs/week, 10.5 hr spread-over
-- Shops Act (state):    Typically 9–10 hrs/day, 1 day weekly rest
-- Code on Wages:        Overtime = 2× normal rate, max 2 hrs OT/day
-- Night work for women: Permitted only with consent + transport + safety
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS working_hours_compliance (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id             UUID REFERENCES users(id),
    candidate_id            UUID REFERENCES candidates(id),

    -- Shift details
    shift_date              DATE NOT NULL,
    shift_start             TIMESTAMP NOT NULL,
    shift_end               TIMESTAMP NOT NULL,
    actual_hours            NUMERIC(5,2),             -- Actual hours worked
    break_hours             NUMERIC(5,2) DEFAULT 0.5, -- Break deducted
    spread_over_hours       NUMERIC(5,2),             -- Start-to-end including breaks

    -- Overtime
    overtime_hours          NUMERIC(5,2) DEFAULT 0,
    overtime_rate_multiplier NUMERIC(4,2) DEFAULT 2.0,  -- India: 2× normal
    overtime_inr            NUMERIC(12,2),

    -- Weekly totals
    week_number             INT,
    weekly_total_hours      NUMERIC(6,2),
    weekly_rest_day         DATE,

    -- Night shift
    is_night_shift          BOOLEAN DEFAULT FALSE,
    night_shift_start       TIME,                      -- 22:00 to 06:00 typically
    night_shift_consent     BOOLEAN DEFAULT FALSE,     -- Women workers consent required
    transport_arranged      BOOLEAN DEFAULT FALSE,

    -- State-specific rules
    state_code              VARCHAR(5),
    applicable_act          VARCHAR(50),               -- FACTORIES_ACT | SHOPS_ACT | BOTH

    -- Violations
    violation_type          VARCHAR(50),
    -- EXCESS_DAILY_HOURS | EXCESS_WEEKLY_HOURS | EXCESS_SPREAD_OVER |
    -- OVERTIME_LIMIT_BREACH | NO_WEEKLY_REST | NIGHT_SHIFT_NO_CONSENT
    violation_severity      VARCHAR(20),               -- INFO | WARNING | CRITICAL
    resolved                BOOLEAN DEFAULT FALSE,
    resolved_at             TIMESTAMP,
    resolved_by             UUID REFERENCES users(id),
    notes                   TEXT,

    created_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS working_hours_org      ON working_hours_compliance(org_id, shift_date);
CREATE INDEX IF NOT EXISTS working_hours_employee ON working_hours_compliance(employee_id, shift_date);
CREATE INDEX IF NOT EXISTS working_hours_violations ON working_hours_compliance(org_id, violation_type)
    WHERE violation_type IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 7 — Professional Tax Records
--             (State-level tax; not applicable in all states)
--
-- States with PT:  Maharashtra, Karnataka, West Bengal, Tamil Nadu,
--                  Andhra Pradesh, Telangana, Kerala, Madhya Pradesh,
--                  Assam, Odisha, Bihar, Jharkhand, Meghalaya, Sikkim
-- Gujarat abolished PT in 2023.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS professional_tax_slabs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_code          VARCHAR(5)   NOT NULL,
    state_name          VARCHAR(100) NOT NULL,
    slab_min_salary_inr NUMERIC(12,2) NOT NULL,   -- Monthly salary lower bound
    slab_max_salary_inr NUMERIC(12,2),             -- NULL = above slab_min
    pt_monthly_inr      NUMERIC(10,2) NOT NULL,   -- PT per month for this slab
    pt_february_inr     NUMERIC(10,2),             -- Maharashtra has extra ₹100 in Feb
    is_employer_liable  BOOLEAN DEFAULT FALSE,     -- PTRC (employer registration)
    effective_from      DATE NOT NULL,
    effective_to        DATE,
    is_current          BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS pt_slabs_state ON professional_tax_slabs(state_code, is_current);

CREATE TABLE IF NOT EXISTS professional_tax_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_id        UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,

    state_code          VARCHAR(5)   NOT NULL,
    state_name          VARCHAR(100) NOT NULL,
    ptrc_number         VARCHAR(30),               -- PT Registration Certificate (employer)
    ptec_number         VARCHAR(30),               -- PT Enrolment Certificate (employee)

    monthly_salary_inr  NUMERIC(12,2) NOT NULL,
    pt_deducted_inr     NUMERIC(10,2) NOT NULL,    -- Amount deducted this period
    pt_period           VARCHAR(7)   NOT NULL,     -- 'YYYY-MM'
    payment_status      VARCHAR(20) DEFAULT 'PENDING',
    -- PENDING | PAID | FILED | CHALLAN_GENERATED

    challan_number      VARCHAR(50),
    payment_date        DATE,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS pt_records_org    ON professional_tax_records(org_id, pt_period);
CREATE INDEX IF NOT EXISTS pt_records_candidate ON professional_tax_records(candidate_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 8 — DPDP Consent Records
--             (Digital Personal Data Protection Act 2023 — replaces GDPR)
--
-- Key DPDP principles:
--   • Consent must be: free, specific, informed, unconditional, unambiguous
--   • Data Fiduciary (employer) must state clear purpose
--   • Consent can be withdrawn at any time (like GDPR but India-specific)
--   • Cross-border transfer only to DPDP-permitted countries
--   • No dark patterns in consent UI
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dpdp_consent_records (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_id         UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,

    -- Purpose (must be specific and granular per DPDP)
    purpose_code         VARCHAR(50) NOT NULL,
    -- RECRUITMENT_DATA     | Processing personal data for recruitment/hiring
    -- BACKGROUND_CHECK     | Verification of identity, credentials, past employment
    -- SENSITIVE_DATA       | Medical records, biometric data, financial info
    -- MARKETING            | Job alerts, newsletters, promotional content
    -- THIRD_PARTY_SHARE    | Sharing with hotels, employers, staffing agencies
    -- AI_PROFILING         | AI-based candidate assessment, screening, ranking
    -- CROSS_BORDER         | Transfer outside India to DPDP-listed countries

    purpose_description  TEXT NOT NULL,           -- Plain-language Hindi + English
    consent_text_version VARCHAR(10) DEFAULT 'v1.0',

    -- Consent state
    consented            BOOLEAN NOT NULL,
    consented_at         TIMESTAMP DEFAULT NOW(),
    withdrawal_requested_at TIMESTAMP,
    withdrawal_effective_at TIMESTAMP,
    withdrawal_reason    TEXT,

    -- Proof of consent (DPDP requires verifiable consent)
    ip_address           INET,
    user_agent           TEXT,
    consent_mechanism    VARCHAR(30) DEFAULT 'DIGITAL_FORM',
    -- DIGITAL_FORM | SMS_OTP | EMAIL_LINK | VERBAL_RECORDED | WRITTEN

    -- Data Fiduciary (employer) details
    data_fiduciary_name  VARCHAR(255),
    grievance_officer    VARCHAR(255),

    created_at           TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS dpdp_consent_candidate ON dpdp_consent_records(candidate_id, purpose_code);
CREATE INDEX IF NOT EXISTS dpdp_consent_org       ON dpdp_consent_records(org_id, purpose_code);
CREATE INDEX IF NOT EXISTS dpdp_consent_pending_withdrawal ON dpdp_consent_records(withdrawal_requested_at)
    WHERE withdrawal_requested_at IS NOT NULL AND withdrawal_effective_at IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 9 — DPDP Erasure / Correction Requests
--             (Replaces GDPR erasure_requests)
--
-- DPDP rights:
--   • Right to access personal data
--   • Right to correction / completion / updation
--   • Right to erasure (when purpose fulfilled / consent withdrawn)
--   • Right to grievance redressal (Data Protection Board of India)
-- Response time: 30 days
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dpdp_erasure_requests (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_id         UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,

    request_type         VARCHAR(20) NOT NULL DEFAULT 'ERASURE',
    -- ERASURE | CORRECTION | ACCESS | NOMINATION (minor's guardian right)

    -- Request details
    reason               TEXT,
    specific_data_fields TEXT[],                   -- Which fields to erase/correct
    correction_data      JSONB,                    -- For CORRECTION requests

    -- Processing
    status               VARCHAR(20) DEFAULT 'PENDING',
    -- PENDING | UNDER_REVIEW | PROCESSING | COMPLETED | REJECTED | APPEALED

    denial_reason        TEXT,
    retention_legal_basis TEXT,                    -- Why data must be kept despite request
    -- e.g. "Statutory audit requirement under Income Tax Act for 7 years"

    -- Timeline (DPDP requires 30-day response)
    requested_at         TIMESTAMP DEFAULT NOW(),
    acknowledged_at      TIMESTAMP,
    response_due_at      TIMESTAMP GENERATED ALWAYS AS
                            (requested_at + INTERVAL '30 days') STORED,
    completed_at         TIMESTAMP,
    processed_by         UUID REFERENCES users(id),

    -- DPBI Grievance (Data Protection Board of India)
    dpbi_complaint_id    VARCHAR(50),
    dpbi_filed_at        TIMESTAMP,

    -- Audit trail of what was actually erased
    erasure_summary      JSONB DEFAULT '{}',

    created_at           TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS dpdp_erasure_candidate  ON dpdp_erasure_requests(candidate_id);
CREATE INDEX IF NOT EXISTS dpdp_erasure_org_status ON dpdp_erasure_requests(org_id, status);
CREATE INDEX IF NOT EXISTS dpdp_erasure_due_date   ON dpdp_erasure_requests(response_due_at)
    WHERE status NOT IN ('COMPLETED', 'REJECTED');

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 10 — FSSAI Certificates
--              Food Safety and Standards Authority of India
--              Critical for hospitality: every food handler needs FSSAI training.
--
-- License types:
--   BASIC       < ₹12 lakh annual turnover (petty food business)
--   STATE       ₹12 lakh–₹20 crore OR state-level operations
--   CENTRAL     > ₹20 crore OR multi-state operations OR import/export
--
-- FoSTaC (Food Safety Training and Certification) for food handlers:
--   Mandatory training for food safety supervisors per FSSAI regulations
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fssai_certificates (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_id        UUID REFERENCES candidates(id) ON DELETE SET NULL,
    -- NULL for establishment-level licenses (not individual)

    -- Certificate type
    cert_type           VARCHAR(20) NOT NULL,
    -- ESTABLISHMENT_LICENSE | FOSTAC_TRAINING | MEDICAL_FITNESS | FOOD_HANDLER

    -- FSSAI License (for establishment)
    license_number      VARCHAR(14),               -- 14-digit FSSAI license number
    license_type        VARCHAR(10),               -- BASIC | STATE | CENTRAL
    licensed_entity     VARCHAR(255),
    licensed_address    TEXT,
    activity_category   VARCHAR(100),              -- e.g. "Restaurant", "Catering", "Bakery"
    state_code          VARCHAR(5),

    -- FoSTaC Training Certificate (for individual food handlers)
    fostac_cert_number  VARCHAR(50),
    training_provider   VARCHAR(255),
    fostac_course       VARCHAR(100),
    -- BASIC_HYGIENE | FOOD_SAFETY_SUPERVISOR | ADVANCED_HYGIENE

    -- Dates
    issue_date          DATE,
    expiry_date         DATE NOT NULL,
    renewal_date        DATE,

    -- Status
    status              VARCHAR(20) DEFAULT 'ACTIVE',
    -- ACTIVE | EXPIRED | SUSPENDED | CANCELLED | RENEWAL_PENDING

    -- Alerts
    alert_30_day_sent   BOOLEAN DEFAULT FALSE,
    alert_7_day_sent    BOOLEAN DEFAULT FALSE,
    alert_expired_sent  BOOLEAN DEFAULT FALSE,

    -- Audit
    verified_by         UUID REFERENCES users(id),
    verified_at         TIMESTAMP,
    doc_url             TEXT,                       -- S3 certificate scan

    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS fssai_license_num ON fssai_certificates(license_number)
    WHERE license_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS fssai_org_expiry    ON fssai_certificates(org_id, expiry_date, status);
CREATE INDEX IF NOT EXISTS fssai_candidate_idx ON fssai_certificates(candidate_id)
    WHERE candidate_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 11 — India Diversity Data
--              (Replaces EEO — not legally mandated like US EEO, but
--               increasingly used for DPIIT certification, CSR reporting,
--               and government contract requirements)
--
-- Categories per India's reservation system:
--   SC: Scheduled Castes (listed under Constitution)
--   ST: Scheduled Tribes
--   OBC: Other Backward Classes (Central/State lists)
--   EWS: Economically Weaker Sections
--   PWD: Persons with Disabilities (RPWD Act 2016)
--   Ex-servicemen: Defence personnel category
--   Women: Gender diversity tracking
--
-- IMPORTANT: Collection is VOLUNTARY. Must have DPDP consent.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS india_diversity_data (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_id        UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,

    -- Social category (all voluntary, requires DPDP consent)
    social_category     VARCHAR(10),              -- SC | ST | OBC | EWS | GENERAL | PREFER_NOT_TO_SAY
    caste_certificate   BOOLEAN DEFAULT FALSE,    -- Whether certificate provided
    caste_cert_state    VARCHAR(50),

    -- Gender (inclusive)
    gender              VARCHAR(30),              -- MALE | FEMALE | TRANSGENDER | NON_BINARY | PREFER_NOT_TO_SAY
    -- Note: Transgender Persons (Protection of Rights) Act 2019 recognition

    -- Disability (RPWD Act 2016)
    is_pwd              BOOLEAN DEFAULT FALSE,    -- Person with Disability
    pwd_category        VARCHAR(50),              -- Locomotor | Visual | Hearing | Intellectual | Multiple
    pwd_cert_number     VARCHAR(50),
    pwd_disability_pct  SMALLINT,                 -- Disability percentage per UDID

    -- Ex-servicemen (Defence)
    is_ex_serviceman    BOOLEAN DEFAULT FALSE,
    service_branch      VARCHAR(30),              -- ARMY | NAVY | AIR_FORCE | PARAMILITARY

    -- Religion (optional, rarely collected — hospital/school contexts)
    religion            VARCHAR(30),              -- COLLECTED_ONLY_WITH_EXPLICIT_CONSENT

    -- DPDP consent reference (mandatory before collection)
    dpdp_consent_id     UUID REFERENCES dpdp_consent_records(id),

    -- Data quality
    self_declared       BOOLEAN DEFAULT TRUE,     -- Self-declared vs. document verified
    collected_at        TIMESTAMP DEFAULT NOW(),

    UNIQUE(candidate_id, org_id)
);

CREATE INDEX IF NOT EXISTS diversity_org        ON india_diversity_data(org_id, social_category);
CREATE INDEX IF NOT EXISTS diversity_candidate  ON india_diversity_data(candidate_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 12 — India Compliance Audit Logs
--              (Enhanced version of compliance_audit_logs for India actions)
--
-- Covers: DPDP Article 11 (grievance), FSSAI inspections, EPF inspections,
--         Labour Code inspections, identity verification actions
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS india_compliance_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID REFERENCES organizations(id) ON DELETE SET NULL,

    -- Who performed the action
    actor_type      VARCHAR(20) NOT NULL,          -- RECRUITER | ADMIN | SYSTEM | CANDIDATE | INSPECTOR
    actor_id        UUID,
    actor_email     VARCHAR(255),

    -- What happened
    action          VARCHAR(100) NOT NULL,
    -- IDENTITY_VERIFIED | IDENTITY_REJECTED | EPF_REGISTERED | ESIC_REGISTERED |
    -- DPDP_CONSENT_GIVEN | DPDP_CONSENT_WITHDRAWN | DPDP_ERASURE_REQUESTED |
    -- DPDP_ERASURE_COMPLETED | FSSAI_CERT_ADDED | FSSAI_CERT_EXPIRED |
    -- DIVERSITY_DATA_COLLECTED | WAGE_COMPLIANCE_CHECK | WORKING_HOURS_FLAGGED |
    -- PT_DEDUCTED | LABOUR_INSPECTION_FLAGGED | DATA_EXPORTED | DATA_ANONYMISED

    -- What was affected
    entity_type     VARCHAR(50),
    entity_id       TEXT,

    -- Compliance law reference
    law_reference   VARCHAR(100),
    -- e.g. "DPDP Act 2023 Section 11", "EPF Act 1952 Section 6",
    --       "Factories Act 1948 Section 51", "FSSAI Regulation 2.1.3"

    -- Context
    metadata        JSONB DEFAULT '{}',
    ip_address      INET,
    user_agent      TEXT,

    -- India-specific: whether this was triggered by regulatory inspection
    is_inspection   BOOLEAN DEFAULT FALSE,
    inspector_id    VARCHAR(50),                   -- Govt. inspector ID if applicable

    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS india_audit_org    ON india_compliance_audit_logs(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS india_audit_action ON india_compliance_audit_logs(action, created_at DESC);
CREATE INDEX IF NOT EXISTS india_audit_entity ON india_compliance_audit_logs(entity_type, entity_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 13 — Row Level Security Policies
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE india_identity_verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE epf_esic_registrations       ENABLE ROW LEVEL SECURITY;
ALTER TABLE india_minimum_wages          ENABLE ROW LEVEL SECURITY;
ALTER TABLE labour_code_compliance       ENABLE ROW LEVEL SECURITY;
ALTER TABLE working_hours_compliance     ENABLE ROW LEVEL SECURITY;
ALTER TABLE professional_tax_slabs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE professional_tax_records     ENABLE ROW LEVEL SECURITY;
ALTER TABLE dpdp_consent_records         ENABLE ROW LEVEL SECURITY;
ALTER TABLE dpdp_erasure_requests        ENABLE ROW LEVEL SECURITY;
ALTER TABLE fssai_certificates           ENABLE ROW LEVEL SECURITY;
ALTER TABLE india_diversity_data         ENABLE ROW LEVEL SECURITY;
ALTER TABLE india_compliance_audit_logs  ENABLE ROW LEVEL SECURITY;

-- Identity verifications: org-isolated
DROP POLICY IF EXISTS india_identity_verif_policy ON india_identity_verifications;
CREATE POLICY india_identity_verif_policy ON india_identity_verifications
    USING (auth.uid() IN (SELECT id FROM users WHERE org_id = india_identity_verifications.org_id));

-- EPF/ESIC: org-isolated
DROP POLICY IF EXISTS epf_esic_policy ON epf_esic_registrations;
CREATE POLICY epf_esic_policy ON epf_esic_registrations
    USING (auth.uid() IN (SELECT id FROM users WHERE org_id = epf_esic_registrations.org_id));

-- Minimum wages: readable by all authenticated users (public data)
DROP POLICY IF EXISTS min_wages_policy ON india_minimum_wages;
CREATE POLICY min_wages_policy ON india_minimum_wages FOR SELECT USING (true);

-- Labour codes: org-isolated for custom entries
DROP POLICY IF EXISTS labour_code_policy ON labour_code_compliance;
CREATE POLICY labour_code_policy ON labour_code_compliance
    USING (auth.uid() IN (SELECT id FROM users WHERE org_id = labour_code_compliance.org_id));

-- Working hours: org-isolated
DROP POLICY IF EXISTS working_hours_policy ON working_hours_compliance;
CREATE POLICY working_hours_policy ON working_hours_compliance
    USING (auth.uid() IN (SELECT id FROM users WHERE org_id = working_hours_compliance.org_id));

-- PT slabs: readable by all (public data)
DROP POLICY IF EXISTS pt_slabs_policy ON professional_tax_slabs;
CREATE POLICY pt_slabs_policy ON professional_tax_slabs FOR SELECT USING (true);

-- PT records: org-isolated
DROP POLICY IF EXISTS pt_records_policy ON professional_tax_records;
CREATE POLICY pt_records_policy ON professional_tax_records
    USING (auth.uid() IN (SELECT id FROM users WHERE org_id = professional_tax_records.org_id));

-- DPDP consent: org-isolated
DROP POLICY IF EXISTS dpdp_consent_policy ON dpdp_consent_records;
CREATE POLICY dpdp_consent_policy ON dpdp_consent_records
    USING (auth.uid() IN (SELECT id FROM users WHERE org_id = dpdp_consent_records.org_id));

-- DPDP erasure: org-isolated
DROP POLICY IF EXISTS dpdp_erasure_policy ON dpdp_erasure_requests;
CREATE POLICY dpdp_erasure_policy ON dpdp_erasure_requests
    USING (auth.uid() IN (SELECT id FROM users WHERE org_id = dpdp_erasure_requests.org_id));

-- FSSAI: org-isolated
DROP POLICY IF EXISTS fssai_policy ON fssai_certificates;
CREATE POLICY fssai_policy ON fssai_certificates
    USING (auth.uid() IN (SELECT id FROM users WHERE org_id = fssai_certificates.org_id));

-- Diversity: org-isolated (extra-sensitive)
DROP POLICY IF EXISTS diversity_policy ON india_diversity_data;
CREATE POLICY diversity_policy ON india_diversity_data
    USING (auth.uid() IN (SELECT id FROM users WHERE org_id = india_diversity_data.org_id));

-- Audit logs: org-isolated, append-only (no DELETE/UPDATE allowed via RLS)
DROP POLICY IF EXISTS india_audit_select_policy ON india_compliance_audit_logs;
CREATE POLICY india_audit_select_policy ON india_compliance_audit_logs
    FOR SELECT USING (auth.uid() IN (SELECT id FROM users WHERE org_id = india_compliance_audit_logs.org_id));

DROP POLICY IF EXISTS india_audit_insert_policy ON india_compliance_audit_logs;
CREATE POLICY india_audit_insert_policy ON india_compliance_audit_logs
    FOR INSERT WITH CHECK (true);

-- ─────────────────────────────────────────────────────────────────────────────
-- Section 14 — Seed Data
-- ─────────────────────────────────────────────────────────────────────────────

-- ── 14a. Minimum Wages (Hospitality Sector, 2024, key states) ─────────────────
-- Source: State Government Gazettes. Figures are approximate — update quarterly.

INSERT INTO india_minimum_wages
    (state_code, state_name, zone, skill_category, sector,
     daily_wage_inr, monthly_wage_inr, effective_from, is_current, source)
VALUES
-- Maharashtra (Zone A: Mumbai, Pune, Nagpur, Nashik, Aurangabad)
('MH','Maharashtra','A','UNSKILLED','Hotels and Restaurants',
 467.08, 12144.00, '2024-01-01', TRUE, 'Maharashtra Gazette Jan 2024'),
('MH','Maharashtra','A','SEMI_SKILLED','Hotels and Restaurants',
 513.84, 13359.84, '2024-01-01', TRUE, 'Maharashtra Gazette Jan 2024'),
('MH','Maharashtra','A','SKILLED','Hotels and Restaurants',
 565.23, 14695.98, '2024-01-01', TRUE, 'Maharashtra Gazette Jan 2024'),
('MH','Maharashtra','A','HIGHLY_SKILLED','Hotels and Restaurants',
 621.75, 16165.50, '2024-01-01', TRUE, 'Maharashtra Gazette Jan 2024'),

-- Delhi (no zones, single rate)
('DL','Delhi','A','UNSKILLED','Hotels and Restaurants',
 674.00, 17524.00, '2024-04-01', TRUE, 'Delhi Gazette Apr 2024'),
('DL','Delhi','A','SEMI_SKILLED','Hotels and Restaurants',
 741.46, 19277.96, '2024-04-01', TRUE, 'Delhi Gazette Apr 2024'),
('DL','Delhi','A','SKILLED','Hotels and Restaurants',
 815.81, 21211.06, '2024-04-01', TRUE, 'Delhi Gazette Apr 2024'),
('DL','Delhi','A','HIGHLY_SKILLED','Hotels and Restaurants',
 897.39, 23332.14, '2024-04-01', TRUE, 'Delhi Gazette Apr 2024'),

-- Karnataka (Zone A: Bengaluru, Mysuru, Mangaluru, Hubballi, Dharwad)
('KA','Karnataka','A','UNSKILLED','Hotels and Restaurants',
 459.12, 11937.12, '2024-04-01', TRUE, 'Karnataka Gazette Apr 2024'),
('KA','Karnataka','A','SEMI_SKILLED','Hotels and Restaurants',
 505.03, 13130.78, '2024-04-01', TRUE, 'Karnataka Gazette Apr 2024'),
('KA','Karnataka','A','SKILLED','Hotels and Restaurants',
 555.54, 14444.04, '2024-04-01', TRUE, 'Karnataka Gazette Apr 2024'),
('KA','Karnataka','A','HIGHLY_SKILLED','Hotels and Restaurants',
 610.96, 15884.96, '2024-04-01', TRUE, 'Karnataka Gazette Apr 2024'),

-- Tamil Nadu (Zone A: Chennai, Coimbatore)
('TN','Tamil Nadu','A','UNSKILLED','Hotels and Restaurants',
 366.00, 9516.00, '2024-04-01', TRUE, 'Tamil Nadu Gazette Apr 2024'),
('TN','Tamil Nadu','A','SEMI_SKILLED','Hotels and Restaurants',
 402.60, 10467.60, '2024-04-01', TRUE, 'Tamil Nadu Gazette Apr 2024'),
('TN','Tamil Nadu','A','SKILLED','Hotels and Restaurants',
 443.00, 11518.00, '2024-04-01', TRUE, 'Tamil Nadu Gazette Apr 2024'),
('TN','Tamil Nadu','A','HIGHLY_SKILLED','Hotels and Restaurants',
 487.20, 12667.20, '2024-04-01', TRUE, 'Tamil Nadu Gazette Apr 2024'),

-- Goa (major tourism state — hospitality minimum wages)
('GA','Goa','A','UNSKILLED','Hotels and Restaurants',
 424.73, 11043.00, '2024-04-01', TRUE, 'Goa Gazette Apr 2024'),
('GA','Goa','A','SKILLED','Hotels and Restaurants',
 559.23, 14540.00, '2024-04-01', TRUE, 'Goa Gazette Apr 2024'),

-- Rajasthan (major hotel destination)
('RJ','Rajasthan','A','UNSKILLED','Hotels and Restaurants',
 289.47, 7526.00, '2024-01-01', TRUE, 'Rajasthan Gazette Jan 2024'),
('RJ','Rajasthan','A','SKILLED','Hotels and Restaurants',
 347.36, 9031.00, '2024-01-01', TRUE, 'Rajasthan Gazette Jan 2024'),

-- Kerala (high literacy, high wages)
('KL','Kerala','A','UNSKILLED','Hotels and Restaurants',
 577.40, 15012.00, '2024-01-01', TRUE, 'Kerala Gazette Jan 2024'),
('KL','Kerala','A','SKILLED','Hotels and Restaurants',
 693.00, 18018.00, '2024-01-01', TRUE, 'Kerala Gazette Jan 2024'),

-- West Bengal
('WB','West Bengal','A','UNSKILLED','Hotels and Restaurants',
 304.00, 7904.00, '2024-01-01', TRUE, 'WB Gazette Jan 2024'),
('WB','West Bengal','A','SKILLED','Hotels and Restaurants',
 364.80, 9484.80, '2024-01-01', TRUE, 'WB Gazette Jan 2024'),

-- Telangana (Hyderabad)
('TS','Telangana','A','UNSKILLED','Hotels and Restaurants',
 409.00, 10634.00, '2024-01-01', TRUE, 'Telangana Gazette Jan 2024'),
('TS','Telangana','A','SKILLED','Hotels and Restaurants',
 491.00, 12766.00, '2024-01-01', TRUE, 'Telangana Gazette Jan 2024'),

-- Uttar Pradesh
('UP','Uttar Pradesh','A','UNSKILLED','Hotels and Restaurants',
 288.00, 7488.00, '2024-01-01', TRUE, 'UP Gazette Jan 2024'),
('UP','Uttar Pradesh','A','SKILLED','Hotels and Restaurants',
 345.60, 8985.60, '2024-01-01', TRUE, 'UP Gazette Jan 2024')

ON CONFLICT DO NOTHING;


-- ── 14b. Professional Tax Slabs (key states, 2024) ────────────────────────────

INSERT INTO professional_tax_slabs
    (state_code, state_name, slab_min_salary_inr, slab_max_salary_inr,
     pt_monthly_inr, pt_february_inr, is_employer_liable, effective_from, is_current)
VALUES
-- Maharashtra
('MH','Maharashtra',     0,  7500, 0.00,   0.00, TRUE, '2023-04-01', TRUE),
('MH','Maharashtra',  7501, 10000, 175.00, 175.00, TRUE, '2023-04-01', TRUE),
('MH','Maharashtra', 10001, NULL,  200.00, 300.00, TRUE, '2023-04-01', TRUE),

-- Karnataka
('KA','Karnataka',       0, 14999, 0.00,   0.00, TRUE, '2023-04-01', TRUE),
('KA','Karnataka',   15000, NULL,  200.00, 200.00, TRUE, '2023-04-01', TRUE),

-- West Bengal
('WB','West Bengal',     0,  8500,   0.00,   0.00, TRUE, '2023-04-01', TRUE),
('WB','West Bengal',  8501, 10000,  90.00,  90.00, TRUE, '2023-04-01', TRUE),
('WB','West Bengal', 10001, 15000, 110.00, 110.00, TRUE, '2023-04-01', TRUE),
('WB','West Bengal', 15001, 25000, 130.00, 130.00, TRUE, '2023-04-01', TRUE),
('WB','West Bengal', 25001, 40000, 150.00, 150.00, TRUE, '2023-04-01', TRUE),
('WB','West Bengal', 40001, NULL,  200.00, 200.00, TRUE, '2023-04-01', TRUE),

-- Tamil Nadu
('TN','Tamil Nadu',      0, 21000,   0.00,   0.00, TRUE, '2023-04-01', TRUE),
('TN','Tamil Nadu',  21001, NULL,  208.33, 208.33, TRUE, '2023-04-01', TRUE),

-- Andhra Pradesh
('AP','Andhra Pradesh',      0,  15000,  0.00,   0.00, TRUE, '2023-04-01', TRUE),
('AP','Andhra Pradesh',  15001,  20000, 150.00, 150.00, TRUE, '2023-04-01', TRUE),
('AP','Andhra Pradesh',  20001,  NULL,  200.00, 200.00, TRUE, '2023-04-01', TRUE),

-- Telangana
('TS','Telangana',       0, 15000,   0.00,   0.00, TRUE, '2023-04-01', TRUE),
('TS','Telangana',   15001, 20000, 150.00, 150.00, TRUE, '2023-04-01', TRUE),
('TS','Telangana',   20001, NULL,  200.00, 200.00, TRUE, '2023-04-01', TRUE),

-- Kerala
('KL','Kerala',          0, 11999,   0.00,   0.00, TRUE, '2023-04-01', TRUE),
('KL','Kerala',      12000, 17999, 120.00, 120.00, TRUE, '2023-04-01', TRUE),
('KL','Kerala',      18000, NULL,  180.00, 180.00, TRUE, '2023-04-01', TRUE),

-- Madhya Pradesh
('MP','Madhya Pradesh',  0, 18750,   0.00,   0.00, TRUE, '2023-04-01', TRUE),
('MP','Madhya Pradesh',18751, NULL, 208.33, 208.33, TRUE, '2023-04-01', TRUE)

ON CONFLICT DO NOTHING;


-- ── 14c. Labour Code Rules (India's 4 Labour Codes — Hospitality sector) ─────

INSERT INTO labour_code_compliance
    (org_id, labour_code, rule_type, state_code, state_name,
     description, threshold_value, threshold_unit, rule_detail,
     effective_date, is_compliant)
-- Note: org_id is NULL for Central/National rules (use a fixed seed org or NULL)
SELECT NULL::UUID, labour_code, rule_type, state_code, state_name,
       description, threshold_value, threshold_unit, rule_detail::JSONB,
       effective_date::DATE, NULL::BOOLEAN
FROM (VALUES
    -- Code on Wages (National)
    ('WAGES','FLOOR_WAGE','','India',
     'Central Floor Wage: ₹176/day (₹4,576/month) — no state may pay below this',
     176,'INR/DAY','{"daily_inr":176,"monthly_inr":4576,"revision":"annual"}','2024-01-01'),
    ('WAGES','OVERTIME_RATE','','India',
     'Overtime = 2× the ordinary rate (Code on Wages 2019 Section 14)',
     2,'MULTIPLIER','{"rate":2,"max_overtime_hours_per_day":2}','2024-01-01'),
    ('WAGES','EQUAL_PAY','','India',
     'Equal remuneration for same/similar work regardless of gender',
     NULL,NULL,'{"applies_to":"gender","penalty_inr":50000}','2024-01-01'),
    ('WAGES','WAGE_PERIOD','','India',
     'Wage must be paid: daily / weekly / fortnightly / monthly',
     30,'DAYS','{"max_period_days":30,"delay_penalty":true}','2024-01-01'),

    -- Social Security Code (National)
    ('SOCIAL_SECURITY','EPF_THRESHOLD','','India',
     'EPF mandatory for establishments with ≥ 20 employees (Social Security Code 2020)',
     20,'EMPLOYEES','{"employee_contrib_pct":12,"employer_contrib_pct":12,"eps_pct":8.33}','2024-01-01'),
    ('SOCIAL_SECURITY','ESIC_THRESHOLD','','India',
     'ESIC mandatory for establishments with ≥ 10 employees, wage ≤ ₹21,000/month',
     10,'EMPLOYEES','{"wage_ceiling_inr":21000,"employee_pct":0.75,"employer_pct":3.25}','2024-01-01'),
    ('SOCIAL_SECURITY','GRATUITY','','India',
     'Gratuity payable after 5 years continuous service: 15 days salary per completed year',
     5,'YEARS','{"formula":"15_days_per_year","cap_inr":2000000}','2024-01-01'),
    ('SOCIAL_SECURITY','MATERNITY','','India',
     'Maternity benefit: 26 weeks paid leave (first 2 children), 12 weeks thereafter',
     26,'WEEKS','{"first_two_children_weeks":26,"subsequent_weeks":12}','2024-01-01'),

    -- OSH Code (National — Factories / Shops)
    ('OSH','MAX_DAILY_HOURS','','India',
     'Maximum 9 hours per day (Factories); spread-over max 10.5 hours including breaks',
     9,'HOURS/DAY','{"max_daily_hours":9,"max_spread_over_hours":10.5,"applies_to":"FACTORIES"}','2024-01-01'),
    ('OSH','MAX_WEEKLY_HOURS','','India',
     'Maximum 48 hours per week (Factories Act 1948 Section 51)',
     48,'HOURS/WEEK','{"weekly_rest":1,"rest_day_pay":true}','2024-01-01'),
    ('OSH','OVERTIME_CAP','','India',
     'Overtime capped at 2 hours/day; max 50 hours per quarter',
     2,'HOURS/DAY','{"quarterly_cap_hours":50,"ot_rate_multiplier":2}','2024-01-01'),
    ('OSH','NIGHT_SHIFT_WOMEN','','India',
     'Women may work night shifts only with written consent and employer transport obligation',
     NULL,NULL,'{"consent_required":true,"transport_mandatory":true,"hours":"22:00-06:00"}','2024-01-01'),
    ('OSH','SAFETY_COMMITTEE','','India',
     'Safety committee mandatory for establishments with ≥ 250 workers',
     250,'EMPLOYEES','{"meets_frequency":"quarterly"}','2024-01-01'),

    -- Industrial Relations (National)
    ('INDUSTRIAL_RELATIONS','NOTICE_PERIOD_LAYOFF','','India',
     'Layoff / retrenchment: 30 days notice or pay (100+ workers); 3 months notice with Govt approval (300+ workers)',
     100,'EMPLOYEES','{"notice_days":30,"large_establishment_threshold":300}','2024-01-01'),
    ('INDUSTRIAL_RELATIONS','STANDING_ORDERS','','India',
     'Standing Orders mandatory for establishments with ≥ 50 employees',
     50,'EMPLOYEES','{}','2024-01-01')
) AS t(labour_code, rule_type, state_code, state_name, description, threshold_value, threshold_unit, rule_detail, effective_date)
ON CONFLICT DO NOTHING;
