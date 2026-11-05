-- Strict confidential grievance and POSH case management.
BEGIN;

ALTER TABLE hr_complaints
 ADD COLUMN IF NOT EXISTS confidentiality_level VARCHAR(20) NOT NULL DEFAULT 'CONFIDENTIAL' CHECK(confidentiality_level IN ('CONFIDENTIAL','RESTRICTED')),
 ADD COLUMN IF NOT EXISTS investigation_status VARCHAR(24) NOT NULL DEFAULT 'NOT_STARTED' CHECK(investigation_status IN ('NOT_STARTED','PLANNING','IN_PROGRESS','FINDINGS_REVIEW','COMPLETED','CANCELLED')),
 ADD COLUMN IF NOT EXISTS outcome VARCHAR(30) CHECK(outcome IN ('SUBSTANTIATED','PARTIALLY_SUBSTANTIATED','UNSUBSTANTIATED','INCONCLUSIVE','WITHDRAWN'));
UPDATE hr_complaints SET confidentiality_level='RESTRICTED' WHERE complaint_type='POSH';

CREATE TABLE IF NOT EXISTS complaint_case_members (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 complaint_id UUID NOT NULL REFERENCES hr_complaints(id) ON DELETE CASCADE, user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 case_role VARCHAR(30) NOT NULL CHECK(case_role IN ('TRIAGE','INVESTIGATOR','POSH_COMMITTEE','HR_CASEWORKER','LEGAL','AUDITOR')),
 can_view_identity BOOLEAN NOT NULL DEFAULT FALSE, assigned_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), revoked_at TIMESTAMPTZ, UNIQUE(complaint_id,user_id,case_role)
);
CREATE INDEX IF NOT EXISTS complaint_member_user_idx ON complaint_case_members(user_id,complaint_id) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS complaint_investigations (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 complaint_id UUID NOT NULL REFERENCES hr_complaints(id) ON DELETE CASCADE, investigator_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 title VARCHAR(200) NOT NULL, scope TEXT NOT NULL, methodology TEXT, findings TEXT, recommendations TEXT,
 status VARCHAR(24) NOT NULL DEFAULT 'PLANNING' CHECK(status IN ('PLANNING','IN_PROGRESS','FINDINGS_REVIEW','COMPLETED','CANCELLED')),
 started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS complaint_evidence (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 complaint_id UUID NOT NULL REFERENCES hr_complaints(id) ON DELETE CASCADE, investigation_id UUID REFERENCES complaint_investigations(id) ON DELETE SET NULL,
 evidence_type VARCHAR(30) NOT NULL CHECK(evidence_type IN ('DOCUMENT','IMAGE','VIDEO','AUDIO','MESSAGE','STATEMENT','OTHER')),
 file_name VARCHAR(255), content_type VARCHAR(100), storage_key TEXT, text_evidence TEXT, sha256_hash VARCHAR(64),
 collected_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT, collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 description TEXT, chain_of_custody JSONB NOT NULL DEFAULT '[]', is_redacted BOOLEAN NOT NULL DEFAULT FALSE,
 CHECK(storage_key IS NOT NULL OR text_evidence IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS complaint_escalations (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 complaint_id UUID NOT NULL REFERENCES hr_complaints(id) ON DELETE CASCADE, escalated_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 escalated_to UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT, reason TEXT NOT NULL, priority VARCHAR(20) NOT NULL DEFAULT 'HIGH' CHECK(priority IN ('MEDIUM','HIGH','CRITICAL')),
 status VARCHAR(20) NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','ACKNOWLEDGED','CLOSED')), acknowledged_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS complaint_resolutions (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 complaint_id UUID NOT NULL UNIQUE REFERENCES hr_complaints(id) ON DELETE RESTRICT, outcome VARCHAR(30) NOT NULL CHECK(outcome IN ('SUBSTANTIATED','PARTIALLY_SUBSTANTIATED','UNSUBSTANTIATED','INCONCLUSIVE','WITHDRAWN')),
 resolution_summary TEXT NOT NULL, corrective_actions JSONB NOT NULL DEFAULT '[]', disciplinary_action_reference TEXT,
 appeal_deadline DATE, approved_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT, approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 reporter_notified_at TIMESTAMPTZ, closed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS complaint_access_audit (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 complaint_id UUID NOT NULL REFERENCES hr_complaints(id) ON DELETE RESTRICT, actor_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 action VARCHAR(40) NOT NULL, purpose TEXT NOT NULL, resource_type VARCHAR(40), resource_id UUID,
 access_granted BOOLEAN NOT NULL, denial_reason TEXT, actor_role VARCHAR(50), ip_address TEXT,
 occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS complaint_access_audit_idx ON complaint_access_audit(complaint_id,occurred_at DESC);

CREATE OR REPLACE FUNCTION can_access_complaint(target UUID) RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
 SELECT EXISTS(SELECT 1 FROM hr_complaints c WHERE c.id=target AND c.org_id=current_user_org_id() AND (
   (c.employee_id=auth.uid() AND NOT c.is_anonymous)
   OR EXISTS(SELECT 1 FROM complaint_case_members m WHERE m.complaint_id=c.id AND m.user_id=auth.uid() AND m.revoked_at IS NULL)
   OR (c.complaint_type='GRIEVANCE' AND current_user_role() IN ('OWNER','GROUP_ADMIN_HR'))
 ))
$$;
CREATE OR REPLACE FUNCTION can_manage_complaint(target UUID) RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
 SELECT EXISTS(SELECT 1 FROM hr_complaints c WHERE c.id=target AND c.org_id=current_user_org_id() AND (
   EXISTS(SELECT 1 FROM complaint_case_members m WHERE m.complaint_id=c.id AND m.user_id=auth.uid() AND m.revoked_at IS NULL AND m.case_role IN ('INVESTIGATOR','POSH_COMMITTEE','HR_CASEWORKER','LEGAL'))
   OR (c.complaint_type='GRIEVANCE' AND current_user_role() IN ('OWNER','GROUP_ADMIN_HR'))
 ))
$$;

DROP POLICY IF EXISTS hc_policy ON hr_complaints; DROP POLICY IF EXISTS hr_complaints_self ON hr_complaints;
DROP POLICY IF EXISTS hr_complaints_create ON hr_complaints; DROP POLICY IF EXISTS hr_complaints_manage ON hr_complaints;
CREATE POLICY complaint_strict_read ON hr_complaints FOR SELECT USING(can_access_complaint(id));
CREATE POLICY complaint_employee_create ON hr_complaints FOR INSERT WITH CHECK(org_id=current_user_org_id() AND source='APP' AND ((NOT is_anonymous AND employee_id=auth.uid()) OR (is_anonymous AND employee_id IS NULL AND phone IS NULL)));
CREATE POLICY complaint_strict_update ON hr_complaints FOR UPDATE USING(can_manage_complaint(id)) WITH CHECK(org_id=current_user_org_id() AND can_manage_complaint(id));

ALTER TABLE complaint_case_members ENABLE ROW LEVEL SECURITY; ALTER TABLE complaint_investigations ENABLE ROW LEVEL SECURITY;
ALTER TABLE complaint_evidence ENABLE ROW LEVEL SECURITY; ALTER TABLE complaint_escalations ENABLE ROW LEVEL SECURITY;
ALTER TABLE complaint_resolutions ENABLE ROW LEVEL SECURITY; ALTER TABLE complaint_access_audit ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS complaint_members_read ON complaint_case_members; DROP POLICY IF EXISTS complaint_members_manage ON complaint_case_members;
CREATE POLICY complaint_members_read ON complaint_case_members FOR SELECT USING(user_id=auth.uid() OR (org_id=current_user_org_id() AND current_user_role() IN ('OWNER','GROUP_ADMIN_HR')));
CREATE POLICY complaint_members_manage ON complaint_case_members FOR ALL USING(org_id=current_user_org_id() AND current_user_role() IN ('OWNER','GROUP_ADMIN_HR')) WITH CHECK(org_id=current_user_org_id() AND current_user_role() IN ('OWNER','GROUP_ADMIN_HR'));
DO $$ DECLARE t TEXT; BEGIN FOREACH t IN ARRAY ARRAY['complaint_investigations','complaint_evidence','complaint_escalations','complaint_resolutions'] LOOP
 EXECUTE format('DROP POLICY IF EXISTS %I_access ON %I',t,t); EXECUTE format('DROP POLICY IF EXISTS %I_manage ON %I',t,t);
 EXECUTE format('CREATE POLICY %I_access ON %I FOR SELECT USING (org_id=current_user_org_id() AND can_access_complaint(complaint_id))',t,t);
 EXECUTE format('CREATE POLICY %I_manage ON %I FOR ALL USING (org_id=current_user_org_id() AND can_manage_complaint(complaint_id)) WITH CHECK (org_id=current_user_org_id() AND can_manage_complaint(complaint_id))',t,t);
 END LOOP; END $$;
DROP POLICY IF EXISTS complaint_audit_insert ON complaint_access_audit; DROP POLICY IF EXISTS complaint_audit_read ON complaint_access_audit;
CREATE POLICY complaint_audit_insert ON complaint_access_audit FOR INSERT WITH CHECK(actor_id=auth.uid() AND org_id=current_user_org_id());
CREATE POLICY complaint_audit_read ON complaint_access_audit FOR SELECT USING(org_id=current_user_org_id() AND current_user_role() IN ('OWNER','GROUP_ADMIN_HR'));

DROP POLICY IF EXISTS civ_policy ON complaint_identity_views;
CREATE POLICY complaint_identity_audit_insert ON complaint_identity_views FOR INSERT WITH CHECK(viewed_by=auth.uid() AND org_id=current_user_org_id());
CREATE POLICY complaint_identity_audit_read ON complaint_identity_views FOR SELECT USING(org_id=current_user_org_id() AND current_user_role() IN ('OWNER','GROUP_ADMIN_HR'));

-- Force the legacy masked view to obey caller RLS rather than view-owner privileges.
ALTER VIEW v_hr_complaints_display SET (security_invoker=true);
REVOKE ALL ON hr_complaints,complaint_investigations,complaint_evidence,complaint_escalations,complaint_resolutions FROM anon;

-- Message logs must not become a side channel for anonymous complaint identity.
DROP POLICY IF EXISTS wm_policy ON whatsapp_messages;
DROP POLICY IF EXISTS whatsapp_message_audit_read ON whatsapp_messages;
CREATE POLICY whatsapp_message_audit_read ON whatsapp_messages FOR SELECT USING(org_id=current_user_org_id() AND current_user_role() IN ('OWNER','GROUP_ADMIN_HR'));

COMMIT;
