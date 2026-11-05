-- Real recruitment analytics: only actual cost input is new; ATS entities remain canonical.
BEGIN;
CREATE TABLE IF NOT EXISTS recruitment_cost_entries (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 property_id UUID REFERENCES properties(id) ON DELETE CASCADE,department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
 job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,recruiter_id UUID REFERENCES users(id) ON DELETE SET NULL,
 source VARCHAR(40),category VARCHAR(30) NOT NULL CHECK(category IN('JOB_BOARD','ADVERTISING','AGENCY','REFERRAL','RECRUITER','INTERVIEW','TRAVEL','BACKGROUND_CHECK','ONBOARDING','OTHER')),
 amount_inr NUMERIC(14,2) NOT NULL CHECK(amount_inr>=0),incurred_on DATE NOT NULL,description TEXT,external_reference TEXT,
 created_by UUID NOT NULL REFERENCES users(id),created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS recruitment_cost_filter_idx ON recruitment_cost_entries(org_id,property_id,department_id,job_id,recruiter_id,incurred_on);
ALTER TABLE recruitment_cost_entries ENABLE ROW LEVEL SECURITY;
CREATE POLICY recruitment_cost_read ON recruitment_cost_entries FOR SELECT USING(org_id=current_user_org_id() AND rbac_has_permission('reports.read') AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id));
CREATE POLICY recruitment_cost_manage ON recruitment_cost_entries FOR ALL USING(org_id=current_user_org_id() AND rbac_has_permission('reports.financial') AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id)) WITH CHECK(org_id=current_user_org_id() AND rbac_has_permission('reports.financial') AND (property_id IS NULL OR has_property_access(property_id)) AND rbac_department_access(department_id));

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS filled_at TIMESTAMPTZ;
CREATE OR REPLACE FUNCTION update_job_filled_timestamp() RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE target_job UUID; required_count INT; hired_count INT; BEGIN
 target_job:=CASE WHEN TG_OP='DELETE' THEN OLD.job_id ELSE NEW.job_id END;
 IF target_job IS NULL THEN RETURN COALESCE(NEW,OLD); END IF;
 SELECT GREATEST(COALESCE(openings_count,1),1) INTO required_count FROM jobs WHERE id=target_job;
 SELECT count(*) INTO hired_count FROM applications WHERE job_id=target_job AND upper(status)='HIRED';
 UPDATE jobs SET filled_at=CASE WHEN hired_count>=required_count THEN COALESCE(filled_at,NOW()) ELSE NULL END WHERE id=target_job;
 RETURN COALESCE(NEW,OLD);
END $$;
DROP TRIGGER IF EXISTS application_updates_job_fill ON applications;
CREATE TRIGGER application_updates_job_fill AFTER INSERT OR UPDATE OF status OR DELETE ON applications FOR EACH ROW EXECUTE FUNCTION update_job_filled_timestamp();
COMMIT;
