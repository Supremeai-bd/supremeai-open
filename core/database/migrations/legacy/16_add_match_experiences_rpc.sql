-- Migration: 16_add_match_experiences_rpc.sql
-- Purpose: Add match_experiences RPC function for Supabase pgvector
--          so ExperienceDatabase can do similarity search without
--          ChromaDB/Qdrant (Render free-tier has no persistent disk).
--
-- Why: Render free-tier does NOT support persistent disks/volumes.
-- ChromaDB and Qdrant store vectors in local files — lost on every
-- container restart (free-tier sleeps after 15 min idle).
-- This RPC uses Supabase pgvector (already provisioned) which is
-- remote + persistent across restarts.
--
-- Risk: LOW — CREATE OR REPLACE FUNCTION is idempotent.
-- Rollback: DROP FUNCTION IF EXISTS match_experiences;
--
-- Source: FREE_TIER_STORAGE_PLAN.md

-- Use the existing ai_memory table (already has VECTOR(1536) column +
-- ivfflat index from migration 001_initial_schema.sql:301)

-- Filter by collection name (stored in metadata JSONB) so we don't
-- pollute other ai_memory rows (e.g. long-term facts, working memory).
CREATE OR REPLACE FUNCTION match_experiences (
    query_embedding VECTOR(1536),
    match_count INT DEFAULT 5,
    match_threshold FLOAT DEFAULT 0.3,
    filter_collection TEXT DEFAULT 'experience'
)
RETURNS TABLE (
    id UUID,
    summary TEXT,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        ai_memory.id,
        ai_memory.summary,
        ai_memory.metadata,
        1 - (ai_memory.embedding <=> query_embedding) AS similarity
    FROM ai_memory
    WHERE
        ai_memory.metadata->>'collection' = filter_collection
        AND 1 - (ai_memory.embedding <=> query_embedding) > match_threshold
    ORDER BY ai_memory.embedding <=> query_embedding
    LIMIT match_count;
$$;

COMMENT ON FUNCTION match_experiences IS
    'Cosine similarity search for ExperienceDatabase (SupabaseVectorBackend).
    Filters by collection=''experience'' in metadata JSONB.
    Replaces ChromaDB/Qdrant which require local disk (not available on Render free-tier).';

-- Idempotency: re-running this migration is safe (CREATE OR REPLACE).
-- Verification query (run after migration):
--   SELECT proname, prosrc FROM pg_proc WHERE proname = 'match_experiences';
