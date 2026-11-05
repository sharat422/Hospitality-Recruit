-- Complete the India employee-referral lifecycle without replacing existing tables.
ALTER TABLE referrals
    ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS bonus_paid_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS bonus_payout_id TEXT,
    ADD COLUMN IF NOT EXISTS payout_claimed_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS payout_error TEXT,
    ADD COLUMN IF NOT EXISTS payroll_reference TEXT,
    ADD COLUMN IF NOT EXISTS payroll_provider VARCHAR(40),
    ADD COLUMN IF NOT EXISTS payroll_synced_at TIMESTAMP;

ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS tracking_token UUID DEFAULT gen_random_uuid();

UPDATE referrals r
SET org_id = u.org_id
FROM users u
WHERE r.referrer_id = u.id AND r.org_id IS NULL;

CREATE INDEX IF NOT EXISTS referrals_org_status_idx ON referrals(org_id, status);
CREATE INDEX IF NOT EXISTS referrals_bonus_due_idx
    ON referrals(hire_date, retention_bonus_status)
    WHERE status = 'HIRED' AND bonus_paid_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS referrals_bonus_payout_unique_idx
    ON referrals(bonus_payout_id) WHERE bonus_payout_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS applications_tracking_token_unique_idx
    ON applications(tracking_token) WHERE tracking_token IS NOT NULL;

-- Serialize candidate/job claims so two concurrent referrers cannot both receive credit.
CREATE OR REPLACE FUNCTION public.prevent_duplicate_active_referral()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.candidate_email IS NULL OR NEW.status NOT IN ('PENDING','APPLIED','SHORTLISTED','HIRED') THEN
        RETURN NEW;
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(lower(NEW.candidate_email) || ':' || NEW.job_role_id::text, 0));
    IF EXISTS (
        SELECT 1 FROM referrals r
        WHERE r.id <> NEW.id
          AND lower(r.candidate_email) = lower(NEW.candidate_email)
          AND r.job_role_id = NEW.job_role_id
          AND r.status IN ('PENDING','APPLIED','SHORTLISTED','HIRED')
    ) THEN
        RAISE EXCEPTION 'An active referral already exists for this candidate and job'
            USING ERRCODE = '23505';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS referrals_prevent_duplicate_active ON referrals;
CREATE TRIGGER referrals_prevent_duplicate_active
BEFORE INSERT OR UPDATE OF candidate_email, job_role_id, status ON referrals
FOR EACH ROW EXECUTE FUNCTION public.prevent_duplicate_active_referral();

-- Replace the original public policy. Service-role workers bypass RLS.
DROP POLICY IF EXISTS referrals_policy ON referrals;
DROP POLICY IF EXISTS referrals_org_isolation ON referrals;
CREATE POLICY referrals_org_isolation ON referrals
FOR SELECT USING (
    referrer_id = auth.uid()
    OR EXISTS (
        SELECT 1 FROM users u
        WHERE u.id = auth.uid() AND u.org_id = referrals.org_id
          AND lower(u.role) IN ('owner','admin','group_admin','hr_admin','hr_manager','general_manager','recruiter')
    )
);
CREATE POLICY referrals_employee_create ON referrals
FOR INSERT WITH CHECK (
    referrer_id = auth.uid()
    AND org_id = (SELECT u.org_id FROM users u WHERE u.id = auth.uid())
);
CREATE POLICY referrals_staff_update ON referrals
FOR UPDATE USING (
    EXISTS (
        SELECT 1 FROM users u
        WHERE u.id = auth.uid() AND u.org_id = referrals.org_id
          AND lower(u.role) IN ('owner','admin','group_admin','hr_admin','hr_manager','general_manager','recruiter')
    )
) WITH CHECK (
    org_id = (SELECT u.org_id FROM users u WHERE u.id = auth.uid())
);
CREATE POLICY referrals_employee_delete_pending ON referrals
FOR DELETE USING (referrer_id = auth.uid() AND status = 'PENDING');

-- Column-limited self-service operation; employees cannot mutate pipeline/payout state.
CREATE OR REPLACE FUNCTION public.track_referral_whatsapp_share(p_referral_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    UPDATE referrals r
    SET whatsapp_shared = TRUE, whatsapp_shared_at = NOW(), updated_at = NOW()
    WHERE r.id = p_referral_id
      AND (
        r.referrer_id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM users u WHERE u.id = auth.uid() AND u.org_id = r.org_id
              AND lower(u.role) IN ('owner','admin','group_admin','hr_admin','hr_manager','general_manager','recruiter')
        )
      );
    RETURN FOUND;
END;
$$;
REVOKE ALL ON FUNCTION public.track_referral_whatsapp_share(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.track_referral_whatsapp_share(UUID) TO authenticated;
