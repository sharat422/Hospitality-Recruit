-- Read-only, permission-aware Hospitality AI Assistant audit trail.
BEGIN;

CREATE TABLE IF NOT EXISTS ai_assistant_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(160),
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_assistant_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES ai_assistant_conversations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(12) NOT NULL CHECK (role IN ('USER','ASSISTANT')),
    content TEXT NOT NULL CHECK (char_length(content) BETWEEN 1 AND 12000),
    tool_name VARCHAR(80),
    sources JSONB NOT NULL DEFAULT '[]',
    metrics JSONB NOT NULL DEFAULT '{}',
    filters JSONB NOT NULL DEFAULT '{}',
    generated_by VARCHAR(30) NOT NULL DEFAULT 'DETERMINISTIC'
        CHECK (generated_by IN ('DETERMINISTIC','CLAUDE_NARRATIVE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_assistant_tool_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES ai_assistant_conversations(id) ON DELETE CASCADE,
    message_id UUID REFERENCES ai_assistant_messages(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tool_name VARCHAR(80) NOT NULL,
    permission_required VARCHAR(80) NOT NULL,
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
    row_count INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    status VARCHAR(20) NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','DENIED','FAILED')),
    error_code VARCHAR(80),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ai_assistant_conversation_user_idx
    ON ai_assistant_conversations(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS ai_assistant_message_conversation_idx
    ON ai_assistant_messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS ai_assistant_tool_audit_idx
    ON ai_assistant_tool_runs(org_id, user_id, started_at DESC);

ALTER TABLE ai_assistant_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_assistant_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_assistant_tool_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY ai_conversations_self ON ai_assistant_conversations FOR ALL
    USING (org_id=current_user_org_id() AND user_id=auth.uid())
    WITH CHECK (org_id=current_user_org_id() AND user_id=auth.uid());
CREATE POLICY ai_messages_self ON ai_assistant_messages FOR ALL
    USING (org_id=current_user_org_id() AND user_id=auth.uid()
      AND EXISTS (SELECT 1 FROM ai_assistant_conversations c
                  WHERE c.id=conversation_id AND c.user_id=auth.uid()))
    WITH CHECK (org_id=current_user_org_id() AND user_id=auth.uid()
      AND EXISTS (SELECT 1 FROM ai_assistant_conversations c
                  WHERE c.id=conversation_id AND c.user_id=auth.uid()));
CREATE POLICY ai_tool_runs_self_read ON ai_assistant_tool_runs FOR SELECT
    USING (org_id=current_user_org_id() AND user_id=auth.uid());
CREATE POLICY ai_tool_runs_self_insert ON ai_assistant_tool_runs FOR INSERT
    WITH CHECK (org_id=current_user_org_id() AND user_id=auth.uid());
CREATE POLICY ai_tool_runs_self_update ON ai_assistant_tool_runs FOR UPDATE
    USING (org_id=current_user_org_id() AND user_id=auth.uid())
    WITH CHECK (org_id=current_user_org_id() AND user_id=auth.uid());

REVOKE ALL ON ai_assistant_conversations, ai_assistant_messages, ai_assistant_tool_runs FROM anon;
COMMIT;
