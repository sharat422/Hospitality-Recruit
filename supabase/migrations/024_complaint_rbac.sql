-- =============================================================================
-- 024_complaint_rbac.sql
-- Role-based access control for complaint identity disclosure.
--
-- New table:
--   complaint_identity_views — audit log: who viewed which complaint's identity,
--                              when, what role they held, and why.
--
-- Privileged roles (hr_admin, super_admin, admin) may call
--   GET /api/v1/hr-bot/complaints/{id}/identity
-- to reveal the reporter's identity for anonymous complaints.
-- Every such access is immutably logged here for compliance.
--
-- View update:
--   v_hr_complaints_display — add sla_status and days_open so the list
--   endpoint returns richer data without exposing identity to normal managers.
-- =============================================================================

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. complaint_identity_views — immutable audit log
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS complaint_identity_views (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    complaint_id   UUID        NOT NULL REFERENCES hr_complaints(id) ON DELETE CASCADE,
    ticket_number  VARCHAR(25),          -- denormalised for quick audit reports
    is_anonymous   BOOLEAN,              -- was the complaint anonymous at access time?

    -- Who accessed the identity
    viewed_by      UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    viewer_role    VARCHAR(50),          -- role at access time (immutable record)

    -- Why they accessed it (optional but encouraged)
    purpose        TEXT,

    -- Immutable timestamp — no updated_at on purpose (audit log must not change)
    viewed_at      TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS civ_complaint ON complaint_identity_views(complaint_id);
CREATE INDEX IF NOT EXISTS civ_viewer    ON complaint_identity_views(viewed_by);
CREATE INDEX IF NOT EXISTS civ_org_date  ON complaint_identity_views(org_id, viewed_at DESC);

-- RLS: accessible only within the same org
ALTER TABLE complaint_identity_views ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS civ_policy ON complaint_identity_views;
CREATE POLICY civ_policy ON complaint_identity_views
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Rebuild v_hr_complaints_display
--    Identity is masked for anonymous complaints for all callers.
--    Only the privileged identity endpoint exposes the real reporter.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_hr_complaints_display AS
SELECT
    hc.id,
    hc.org_id,
    hc.ticket_number,
    hc.category,
    hc.severity,
    hc.status,
    hc.complaint_text,
    hc.source,
    hc.escalated,
    hc.is_anonymous,

    -- Identity — always masked for anonymous; shown for named
    CASE
        WHEN hc.is_anonymous THEN 'Anonymous Reporter'
        ELSE COALESCE(u.email, hc.phone, 'Unknown')
    END                                         AS reporter_display,

    CASE
        WHEN hc.is_anonymous THEN NULL
        ELSE hc.employee_id
    END                                         AS reporter_employee_id,

    -- SLA
    hc.sla_deadline,
    hc.sla_breached,
    CASE
        WHEN hc.status IN ('RESOLVED', 'CLOSED')       THEN 'met'
        WHEN hc.sla_deadline < NOW()                    THEN 'breached'
        WHEN hc.sla_deadline < NOW() + INTERVAL '1 day' THEN 'at_risk'
        ELSE                                                 'on_track'
    END                                         AS sla_status,

    -- Age
    EXTRACT(DAY FROM NOW() - hc.created_at)::INTEGER AS days_open,

    -- Assignment / resolution
    hc.assigned_to,
    hc.assigned_at,
    hc.resolution_notes,
    hc.resolved_at,
    hc.close_reason,
    hc.closed_at,

    -- Escalation
    hc.escalated_at,
    hc.escalated_to,
    hc.escalation_reason,

    -- Audit timestamps
    hc.created_at,
    hc.updated_at,

    -- How many times this complaint's identity has been revealed
    (SELECT COUNT(*) FROM complaint_identity_views civ
     WHERE civ.complaint_id = hc.id)            AS identity_view_count

FROM hr_complaints hc
LEFT JOIN users u ON u.id = hc.employee_id;


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Document privileged roles (comment only — no constraint change)
--    Roles that may call GET /complaints/{id}/identity:
--      hr_admin    — HR department administrator
--      super_admin — platform-level administrator
--      admin       — org-level administrator (legacy)
-- ─────────────────────────────────────────────────────────────────────────────
-- No schema change needed: the users.role column is VARCHAR(50) with no CHECK.
-- Privileged role enforcement is in the application layer.

COMMIT;
