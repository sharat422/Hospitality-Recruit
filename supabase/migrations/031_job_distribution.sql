-- Canonical multi-channel job distribution and attribution ledger.
BEGIN;

CREATE TABLE IF NOT EXISTS distribution_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    channel_key VARCHAR(40) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    delivery_mode VARCHAR(30) NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    default_expiry_days INTEGER NOT NULL DEFAULT 30 CHECK (default_expiry_days BETWEEN 1 AND 365),
    configuration JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(org_id, channel_key),
    CHECK (delivery_mode IN ('INTERNAL','SHARE_LINK','REFERRAL','QR','WALK_IN','MANUAL_EXPORT','API'))
);

CREATE TABLE IF NOT EXISTS job_distributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    channel_key VARCHAR(40) NOT NULL,
    delivery_mode VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    attribution_token UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    content_english TEXT,
    content_hindi TEXT,
    posting_url TEXT,
    external_post_id TEXT,
    published_at TIMESTAMPTZ,
    unpublished_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    click_count INTEGER NOT NULL DEFAULT 0,
    application_count INTEGER NOT NULL DEFAULT 0,
    hire_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(job_id, channel_key),
    CHECK (status IN ('DRAFT','PUBLISHED','UNPUBLISHED','EXPIRED','FAILED'))
);

CREATE TABLE IF NOT EXISTS job_distribution_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    distribution_id UUID NOT NULL REFERENCES job_distributions(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,
    application_id UUID REFERENCES applications(id) ON DELETE SET NULL,
    event_type VARCHAR(20) NOT NULL,
    source_ref TEXT,
    ip_hash TEXT,
    user_agent TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (event_type IN ('CLICK','APPLICATION','HIRE'))
);

ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS distribution_id UUID REFERENCES job_distributions(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS attribution_token UUID;
ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS distribution_id UUID REFERENCES job_distributions(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS distribution_application_event_unique
    ON job_distribution_events(distribution_id, application_id, event_type)
    WHERE application_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS distribution_candidate_hire_unique
    ON job_distribution_events(distribution_id, candidate_id, event_type)
    WHERE candidate_id IS NOT NULL AND event_type='HIRE';
CREATE INDEX IF NOT EXISTS job_distributions_analytics_idx
    ON job_distributions(org_id, channel_key, status, published_at);

ALTER TABLE distribution_channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_distributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_distribution_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY distribution_channels_read ON distribution_channels FOR SELECT USING (
    org_id=current_user_org_id() AND rbac_has_permission('jobs.read'));
CREATE POLICY distribution_channels_manage ON distribution_channels FOR ALL USING (
    org_id=current_user_org_id() AND rbac_has_permission('jobs.manage'))
    WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('jobs.manage'));
CREATE POLICY job_distributions_read ON job_distributions FOR SELECT USING (
    org_id=current_user_org_id() AND rbac_has_permission('jobs.read'));
CREATE POLICY job_distributions_manage ON job_distributions FOR ALL USING (
    org_id=current_user_org_id() AND rbac_has_permission('jobs.manage'))
    WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('jobs.manage'));
CREATE POLICY distribution_events_read ON job_distribution_events FOR SELECT USING (
    org_id=current_user_org_id() AND rbac_has_permission('reports.read'));

-- Public tracked links can resolve only live posting metadata. Mutations happen through
-- the narrowly scoped SECURITY DEFINER functions below, never a broad public UPDATE.
CREATE POLICY job_distributions_public_live ON job_distributions FOR SELECT USING (
    status='PUBLISHED' AND (expires_at IS NULL OR expires_at > NOW()));

CREATE OR REPLACE FUNCTION record_distribution_click(p_token UUID, p_ip_hash TEXT, p_user_agent TEXT)
RETURNS TABLE(distribution_id UUID, org_id UUID, job_id UUID, channel_key VARCHAR)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE d job_distributions%ROWTYPE;
BEGIN
  SELECT * INTO d FROM job_distributions
   WHERE attribution_token=p_token AND status='PUBLISHED'
     AND (expires_at IS NULL OR expires_at>NOW()) FOR UPDATE;
  IF d.id IS NULL THEN RETURN; END IF;
  INSERT INTO job_distribution_events(org_id,distribution_id,job_id,event_type,ip_hash,user_agent)
  VALUES(d.org_id,d.id,d.job_id,'CLICK',p_ip_hash,p_user_agent);
  UPDATE job_distributions SET click_count=click_count+1,updated_at=NOW() WHERE id=d.id;
  RETURN QUERY SELECT d.id,d.org_id,d.job_id,d.channel_key;
END $$;
GRANT EXECUTE ON FUNCTION record_distribution_click(UUID,TEXT,TEXT) TO anon, authenticated;

CREATE OR REPLACE FUNCTION record_distribution_conversion(
  p_token UUID, p_event_type VARCHAR, p_candidate_id UUID, p_application_id UUID DEFAULT NULL)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE d job_distributions%ROWTYPE;
BEGIN
  IF p_event_type NOT IN ('APPLICATION','HIRE') THEN RETURN FALSE; END IF;
  SELECT * INTO d FROM job_distributions WHERE attribution_token=p_token FOR UPDATE;
  IF d.id IS NULL THEN RETURN FALSE; END IF;
  INSERT INTO job_distribution_events(org_id,distribution_id,job_id,candidate_id,application_id,event_type,source_ref)
  VALUES(d.org_id,d.id,d.job_id,p_candidate_id,p_application_id,p_event_type,p_token::TEXT)
  ON CONFLICT DO NOTHING;
  IF p_event_type='APPLICATION' THEN
    UPDATE job_distributions SET application_count=(SELECT COUNT(*) FROM job_distribution_events WHERE distribution_id=d.id AND event_type='APPLICATION'),updated_at=NOW() WHERE id=d.id;
  ELSE
    UPDATE job_distributions SET hire_count=(SELECT COUNT(*) FROM job_distribution_events WHERE distribution_id=d.id AND event_type='HIRE'),updated_at=NOW() WHERE id=d.id;
  END IF;
  RETURN TRUE;
END $$;
GRANT EXECUTE ON FUNCTION record_distribution_conversion(UUID,VARCHAR,UUID,UUID) TO anon, authenticated;

COMMIT;
