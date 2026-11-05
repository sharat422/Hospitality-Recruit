-- Permission-aware global search support. Search reads canonical domain tables;
-- this migration stores only each user's recent query history.
BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS user_recent_searches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    query TEXT NOT NULL CHECK (char_length(query) BETWEEN 2 AND 100),
    normalized_query TEXT NOT NULL CHECK (char_length(normalized_query) BETWEEN 2 AND 100),
    categories TEXT[] NOT NULL DEFAULT '{}',
    result_count INTEGER NOT NULL DEFAULT 0 CHECK (result_count >= 0),
    searched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, normalized_query, categories)
);

CREATE INDEX IF NOT EXISTS recent_searches_user_time_idx
    ON user_recent_searches(user_id, searched_at DESC);

-- Trigram indexes support exact/contains/fuzzy search without a duplicate index table.
CREATE INDEX IF NOT EXISTS candidates_search_name_trgm_idx
    ON candidates USING gin ((lower(first_name || ' ' || last_name)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS candidates_search_email_trgm_idx
    ON candidates USING gin ((lower(email)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS users_search_name_trgm_idx
    ON users USING gin ((lower(coalesce(full_name, ''))) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS jobs_search_title_trgm_idx
    ON jobs USING gin ((lower(title)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS properties_search_name_trgm_idx
    ON properties USING gin ((lower(name)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS departments_search_name_trgm_idx
    ON property_departments USING gin ((lower(name)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS referrals_search_code_trgm_idx
    ON referrals USING gin ((lower(referral_code)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS documents_search_file_trgm_idx
    ON candidate_documents USING gin ((lower(file_name)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS complaints_search_ticket_trgm_idx
    ON hr_complaints USING gin ((lower(ticket_number)) gin_trgm_ops);

ALTER TABLE user_recent_searches ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS recent_searches_self_select ON user_recent_searches;
DROP POLICY IF EXISTS recent_searches_self_insert ON user_recent_searches;
DROP POLICY IF EXISTS recent_searches_self_update ON user_recent_searches;
DROP POLICY IF EXISTS recent_searches_self_delete ON user_recent_searches;
CREATE POLICY recent_searches_self_select ON user_recent_searches FOR SELECT
    USING (user_id=auth.uid() AND org_id=current_user_org_id());
CREATE POLICY recent_searches_self_insert ON user_recent_searches FOR INSERT
    WITH CHECK (user_id=auth.uid() AND org_id=current_user_org_id());
CREATE POLICY recent_searches_self_update ON user_recent_searches FOR UPDATE
    USING (user_id=auth.uid() AND org_id=current_user_org_id())
    WITH CHECK (user_id=auth.uid() AND org_id=current_user_org_id());
CREATE POLICY recent_searches_self_delete ON user_recent_searches FOR DELETE
    USING (user_id=auth.uid() AND org_id=current_user_org_id());

REVOKE ALL ON user_recent_searches FROM anon;
COMMIT;
