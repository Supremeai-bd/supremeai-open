-- Migration: 17_retype_match_experiences_384.sql
-- Purpose: Re-type the match_experiences RPC to the CANONICAL ai_memory
--          embedding contract — vector(384) — so experience recall works
--          again instead of dying on a pgvector dimension error.
--
-- Problem (verified, #2257 + docs/database/AI_MEMORY_SCHEMA_AUDIT.md §1/§2):
--   Migration 16 created match_experiences with `query_embedding VECTOR(1536)`
--   ("already has VECTOR(1536) column" — a stale assumption). The canonical
--   ai_memory.embedding contract is vector(384), enforced by the column typmod
--   itself (alembic 2026_09_13_100000, core/embeddings._PG_DIM = 384,
--   models.ai_memory.EMBEDDING_DIMENSIONS = 384). Every caller
--   (adaptive_engine/supabase_vector_backend.py::SupabaseVectorBackend.query)
--   passes the output of embed_for_pgvector() = 384 dims, so pgvector rejects
--   every call at execution — ExperienceDatabase similarity search has been
--   returning [] forever (silent degradation at debug level).
--
-- Fix: DROP the 1536 variant, re-create with vector(384). Same body as
--   migration 16 otherwise (matches the guarded re-creation prescribed by
--   AI_MEMORY_SCHEMA_AUDIT.md §Part 6).
--
-- Risk: LOW — CREATE OR REPLACE is idempotent; the 1536 variant could never
--   execute successfully with canonical embeddings (no working callers to
--   break). Rollback: restore migration 16 (DROP + re-CREATE with 1536).
--
-- Verification query (run after migration):
--   SELECT pg_get_function_arguments(oid) FROM pg_proc WHERE proname = 'match_experiences';
--   → expect "query_embedding vector(384), ..."

DROP FUNCTION IF EXISTS match_experiences(vector, int, float, text);

CREATE OR REPLACE FUNCTION match_experiences (
    query_embedding VECTOR(384),
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
    Re-typed to vector(384) — the canonical ai_memory embedding contract
    (#2257; the VECTOR(1536) variant from migration 16 rejected every
    canonical 384-dim call). Filters by collection=''experience'' in
    metadata JSONB.';

-- Idempotency: re-running is safe (DROP IF EXISTS + CREATE OR REPLACE).
