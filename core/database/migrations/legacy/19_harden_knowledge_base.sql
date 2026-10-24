-- SupremeAI long-term knowledge contract v1
CREATE EXTENSION IF NOT EXISTS pgcrypto;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS knowledge_key TEXT;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS domain TEXT;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'draft';
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS confidence NUMERIC(4,3) NOT NULL DEFAULT 0.700;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS risk_level TEXT NOT NULL DEFAULT 'low';
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS source_version TEXT;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS review_after TIMESTAMPTZ;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS supersedes TEXT;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
UPDATE knowledge_base SET knowledge_key = id WHERE knowledge_key IS NULL;
UPDATE knowledge_base SET title = LEFT(content, 160) WHERE title IS NULL;
UPDATE knowledge_base SET domain = COALESCE(NULLIF(namespace, ''), 'general') WHERE domain IS NULL;
UPDATE knowledge_base SET content_hash = encode(digest(COALESCE(content, ''), 'sha256'), 'hex') WHERE content_hash IS NULL;
ALTER TABLE knowledge_base ALTER COLUMN knowledge_key SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_base_knowledge_key ON knowledge_base(knowledge_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_base_content_hash ON knowledge_base(content_hash);
CREATE INDEX IF NOT EXISTS idx_knowledge_base_status_review ON knowledge_base(status, review_after);
CREATE INDEX IF NOT EXISTS idx_knowledge_base_domain ON knowledge_base(domain);

CREATE TABLE IF NOT EXISTS knowledge_import_audits (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), manifest_hash TEXT NOT NULL,
  source_version TEXT NOT NULL, imported_count INTEGER NOT NULL DEFAULT 0,
  rejected_count INTEGER NOT NULL DEFAULT 0, rollback_id TEXT NOT NULL,
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE knowledge_base ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_import_audits ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS knowledge_base_service_read ON knowledge_base;
CREATE POLICY knowledge_base_service_read ON knowledge_base FOR SELECT USING (status = 'approved');
