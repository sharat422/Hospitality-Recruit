-- Candidate application flow hardening and mobile completion metadata.
-- Additive migration: existing OTP sessions, candidates and applications remain valid.

ALTER TABLE mobile_otp_sessions
    ALTER COLUMN otp DROP NOT NULL;

ALTER TABLE mobile_otp_sessions
    ADD COLUMN IF NOT EXISTS otp_hash TEXT,
    ADD COLUMN IF NOT EXISTS verification_token UUID UNIQUE,
    ADD COLUMN IF NOT EXISTS otp_verified_at TIMESTAMPTZ;

ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(5) DEFAULT 'hi',
    ADD COLUMN IF NOT EXISTS low_bandwidth_mode BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS candidates_tracking_token_unique_idx
    ON candidates(tracking_token) WHERE tracking_token IS NOT NULL;

-- Public uploads use an unguessable candidate tracking token. The RPC prevents
-- anonymous callers from supplying an arbitrary candidate_id or org_id.
CREATE OR REPLACE FUNCTION public.register_candidate_application_document(
    p_tracking_token UUID,
    p_application_id UUID,
    p_document_type TEXT,
    p_file_name TEXT,
    p_file_url TEXT,
    p_mime_type TEXT,
    p_file_size_bytes BIGINT
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_candidate candidates%ROWTYPE;
    v_application applications%ROWTYPE;
    v_document_id UUID;
BEGIN
    SELECT * INTO v_candidate
    FROM candidates
    WHERE tracking_token = p_tracking_token;

    IF v_candidate.id IS NULL THEN
        RAISE EXCEPTION 'Invalid application tracking token';
    END IF;

    SELECT * INTO v_application
    FROM applications
    WHERE id = p_application_id AND candidate_id = v_candidate.id;

    IF v_application.id IS NULL THEN
        RAISE EXCEPTION 'Application does not belong to candidate';
    END IF;

    INSERT INTO candidate_documents (
        org_id, candidate_id, application_id, document_type,
        file_name, storage_key, file_url, mime_type,
        status, uploaded_by
    ) VALUES (
        v_candidate.org_id, v_candidate.id, v_application.id,
        upper(p_document_type), p_file_name, p_file_url, p_file_url, p_mime_type,
        'UPLOADED', NULL
    ) RETURNING id INTO v_document_id;

    IF upper(p_document_type) = 'RESUME' THEN
        UPDATE candidates SET resume_url = p_file_url, updated_at = NOW()
        WHERE id = v_candidate.id;
    END IF;

    RETURN v_document_id;
END;
$$;

REVOKE ALL ON FUNCTION public.register_candidate_application_document(UUID, UUID, TEXT, TEXT, TEXT, TEXT, BIGINT) FROM PUBLIC;

CREATE TABLE IF NOT EXISTS whatsapp_apply_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) NOT NULL,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    state VARCHAR(20) NOT NULL DEFAULT 'NAME'
        CHECK (state IN ('NAME','CITY','EXPERIENCE','COMPLETED','CANCELLED')),
    answers JSONB NOT NULL DEFAULT '{}',
    candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,
    application_id UUID REFERENCES applications(id) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '24 hours',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS whatsapp_apply_sessions_phone_idx
    ON whatsapp_apply_sessions(phone, updated_at DESC);
ALTER TABLE whatsapp_apply_sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS whatsapp_apply_sessions_org_policy ON whatsapp_apply_sessions;
CREATE POLICY whatsapp_apply_sessions_org_policy ON whatsapp_apply_sessions
    FOR ALL USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()))
    WITH CHECK (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));
