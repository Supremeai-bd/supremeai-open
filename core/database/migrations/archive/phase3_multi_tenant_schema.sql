-- File: backend/database/migrations/legacy/phase3_multi_tenant_schema.sql
-- Relocated from root migrations/ to central backend/database/migrations/legacy/

-- G8: User API Keys
CREATE TABLE IF NOT EXISTS user_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    encrypted_key TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(user_id, provider)
);

-- Enable RLS
ALTER TABLE user_keys ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage their own keys"
ON user_keys
FOR ALL
USING (auth.uid()::text = user_id);

-- G10: Conversations
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage their own conversations"
ON conversations
FOR ALL
USING (auth.uid()::text = user_id);

CREATE POLICY "Users can manage messages in their conversations"
ON messages
FOR ALL
USING (
    EXISTS (
        SELECT 1 FROM conversations c
        WHERE c.id = messages.conversation_id
        AND c.user_id = auth.uid()::text
    )
);
