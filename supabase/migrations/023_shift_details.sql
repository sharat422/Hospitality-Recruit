-- =============================================================================
-- 023_shift_details.sql
-- Adds property, department, manager, and location columns to shifts.
-- Rebuilds v_employee_shifts to expose all fields the HR-Bot SHIFT command needs:
--   date, start time, end time, property, department, manager name.
--
-- Backward-compatible: all new columns are nullable with no defaults required.
-- Existing shift_matches / shifts data is unaffected.
-- =============================================================================

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Extend shifts table
-- ─────────────────────────────────────────────────────────────────────────────

-- Property / venue where the shift takes place (e.g. "Grand Hyatt Mumbai")
ALTER TABLE shifts
    ADD COLUMN IF NOT EXISTS property_name VARCHAR(200);

-- Department within the property (e.g. "F&B", "Housekeeping", "Front Desk")
ALTER TABLE shifts
    ADD COLUMN IF NOT EXISTS department VARCHAR(100);

-- Direct reporting manager / supervisor for this shift
ALTER TABLE shifts
    ADD COLUMN IF NOT EXISTS manager_id UUID REFERENCES users(id) ON DELETE SET NULL;

-- Physical address or floor/room detail (free text)
ALTER TABLE shifts
    ADD COLUMN IF NOT EXISTS location TEXT;

-- Index on manager for reverse lookup (who is managing which shifts)
CREATE INDEX IF NOT EXISTS shifts_manager ON shifts(manager_id)
    WHERE manager_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Rebuild v_employee_shifts
--    Exposes every field the SHIFT WhatsApp command needs.
--    Uses LEFT JOINs so a shift still appears even when manager is unset.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_employee_shifts AS
SELECT
    -- Employee identity
    u.id                            AS employee_id,
    u.org_id,
    u.phone                         AS employee_phone,

    -- Assignment metadata
    sm.shift_id,
    sm.match_score,
    sm.status                       AS assignment_status,

    -- Shift timing  (start_date / end_date are TIMESTAMP — contain both date + time)
    s.id                            AS shift_id_direct,
    s.start_date,
    s.end_date,
    s.hours_per_week,

    -- Shift classification
    s.role,
    s.shift_type,
    s.status                        AS shift_status,
    s.urgency,
    s.season,

    -- Location details (new columns)
    s.property_name,
    s.department,
    s.location,

    -- Manager details (LEFT JOIN — NULL when manager not assigned)
    s.manager_id,
    mgr.email                       AS manager_email,
    CASE
        WHEN mgr.email IS NOT NULL
        THEN INITCAP(SPLIT_PART(mgr.email, '@', 1))
        ELSE NULL
    END                             AS manager_display_name

FROM users u

-- Link platform user → candidate record (same email + org)
JOIN candidates c
    ON  c.email  = u.email
    AND c.org_id = u.org_id

-- Candidate's confirmed / matched shift assignments
JOIN shift_matches sm
    ON  sm.candidate_id = c.id
    AND sm.status IN ('confirmed', 'matched')

-- The actual shift
JOIN shifts s
    ON  s.id     = sm.shift_id
    AND s.status = 'open'

-- Manager user (optional)
LEFT JOIN users mgr
    ON  mgr.id = s.manager_id

-- Only future shifts (view never shows past shifts)
WHERE s.start_date >= CURRENT_DATE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. v_candidate_shifts — alternate view for employees in candidates table only
--    (employees who are hired candidates but not yet on the users table)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_candidate_shifts AS
SELECT
    c.id                            AS candidate_id,
    c.org_id,
    c.phone                         AS candidate_phone,

    sm.shift_id,
    sm.match_score,
    sm.status                       AS assignment_status,

    s.id                            AS shift_id_direct,
    s.start_date,
    s.end_date,
    s.hours_per_week,

    s.role,
    s.shift_type,
    s.status                        AS shift_status,
    s.urgency,

    s.property_name,
    s.department,
    s.location,

    s.manager_id,
    mgr.email                       AS manager_email,
    CASE
        WHEN mgr.email IS NOT NULL
        THEN INITCAP(SPLIT_PART(mgr.email, '@', 1))
        ELSE NULL
    END                             AS manager_display_name

FROM candidates c

JOIN shift_matches sm
    ON  sm.candidate_id = c.id
    AND sm.status IN ('confirmed', 'matched')

JOIN shifts s
    ON  s.id     = sm.shift_id
    AND s.status = 'open'

LEFT JOIN users mgr
    ON  mgr.id = s.manager_id

WHERE s.start_date >= CURRENT_DATE
  AND c.pipeline_stage IN ('hired', 'offer_accepted', 'joined', 'onboarded');

COMMIT;
