-- ═══════════════════════════════════════════════════════════════════════════════
-- SupremeAI — Supabase `ai_memory` Phase C setup (canonical, idempotent)
-- ═══════════════════════════════════════════════════════════════════════════════
-- Task 7-b · audit-first deliverable · see docs/database/AI_MEMORY_SCHEMA_AUDIT.md
--
-- RUN: Supabase Dashboard → SQL Editor (whole file, once per env; re-runs are
--      no-ops)  — or —  psql "$SUPABASE_DATABASE_URL" -f <this file>
--
-- Reconciliation notes (audit evidence in the doc above):
--   * Column superset that accepts EVERY live writer:
--       - CascadeMemoryService / save_memory        (user_id, session_id, agent_type,
--         task_type, summary, embedding, metadata)  services/memory_service.py:322,759
--       - SupabaseVectorBackend (experience DB)     (agent_id, memory_type, content,
--         importance_score)                          adaptive_engine/supabase_vector_backend.py:92
--       - FreeTierOptimizedVectorStore / AutoRAG    (content, user_id, session_id via
--         metadata)                                  core/ai_memory/vector_store.py:58
--   * Embedding dimension: vector(384) — enforced by typmod, matches the live
--     contract (core/embeddings.py:20 `_PG_DIM = 384`) and Alembic
--     2026_09_13_100000. Mixed dimensions are REJECTED by the column type itself.
--   * Identity: user_id TEXT (Supabase auth.uid()::text), nullable; no tenant_id
--     (does not exist in any ai_memory code path); no FK (no users ORM table).
--   * This SQL is a STANDALONE companion to Alembic revision 2026_09_13_100000 —
--     the Alembic versions/ directory is intentionally NOT touched here.
--     Safe on: fresh DBs (creates the table), Alembic-managed DBs (skips table,
--     adds RLS/trigger/retention/RPC layer), and legacy bootstrap DBs whose
--     `embedding` column was TEXT (guarded TEXT→vector conversion).
-- ═══════════════════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────────────────
-- Part 1 — pgvector extension (guarded)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;

-- ───────────────────────────────────────────────────────────────────────────────
-- Part 2 — table (fresh environments; existing tables are reconciled in Part 3)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_memory (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          TEXT,                                     -- auth.uid()::text; NULL = system row
    session_id       TEXT NOT NULL,
    agent_type       TEXT NOT NULL DEFAULT 'main',             -- 'main' | 'subagent' | 'reviewer' | ...
    task_type        TEXT NOT NULL DEFAULT 'general',          -- 'general' | 'bug-fix' | 'feature' | ...
    content          TEXT,                                     -- full text (experience/AutoRAG writers)
    summary          TEXT NOT NULL DEFAULT '',                 -- human-readable summary (cascade writer)
    agent_id         UUID,                                     -- SupabaseVectorBackend placeholder, no FK
    memory_type      TEXT,                                     -- e.g. 'procedural' (experience rows)
    importance_score DOUBLE PRECISION,                         -- SupabaseVectorBackend fitness signal
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,       -- flexible attributes (collection, importance, ...)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- dimension-enforcing vector column: vector(384) rejects any other length
    embedding        vector(384)
);

-- ───────────────────────────────────────────────────────────────────────────────
-- Part 3 — reconcile PRE-EXISTING tables (Alembic-managed or legacy runtime DDL)
--          every statement below is a no-op when the schema is already current
-- ───────────────────────────────────────────────────────────────────────────────
ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS user_id          TEXT;
ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS session_id       TEXT;
ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS agent_type       TEXT NOT NULL DEFAULT 'main';
ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS task_type        TEXT NOT NULL DEFAULT 'general';
ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS content          TEXT;
ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS agent_id         UUID;
ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS memory_type      TEXT;
ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS importance_score DOUBLE PRECISION;
ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS metadata         JSONB DEFAULT '{}'::jsonb;
ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS created_at       TIMESTAMPTZ DEFAULT now();
ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS updated_at       TIMESTAMPTZ DEFAULT now();

-- `summary NOT NULL` (Alembic) blocks the experience writer, which never sends it.
-- A server default unblocks it without loosening NOT NULL for existing data.
ALTER TABLE ai_memory ALTER COLUMN summary SET DEFAULT '';

-- Legacy bootstrap tables created embedding as TEXT (services/memory_service.py:44-56).
-- Convert guarded: pgvector accepts the JSON-array string format directly.
DO $$
DECLARE
    _col_type text;
BEGIN
    SELECT data_type INTO _col_type
      FROM information_schema.columns
     WHERE table_name = 'ai_memory' AND column_name = 'embedding'
     LIMIT 1;

    IF _col_type IS NULL THEN
        ALTER TABLE ai_memory ADD COLUMN embedding vector(384);
        RAISE NOTICE 'ai_memory.embedding added as vector(384)';
    ELSIF _col_type = 'text' THEN
        BEGIN
            ALTER TABLE ai_memory
                ALTER COLUMN embedding TYPE vector(384)
                USING NULLIF(trim(embedding), '')::vector;
            RAISE NOTICE 'ai_memory.embedding converted TEXT -> vector(384)';
        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'ai_memory.embedding TEXT->vector conversion failed (%); '
                          'Python-cosine fallback stays active', SQLERRM;
        END;
    ELSE
        RAISE NOTICE 'ai_memory.embedding already % — skipping conversion', _col_type;
    END IF;
END $$;

-- ───────────────────────────────────────────────────────────────────────────────
-- Part 3b — user_id identity reconciliation (M0.6 checkpoint finding)
--          Legacy bootstrap tables created user_id as UUID; the canonical
--          contract is TEXT = auth.uid()::text (Part 2 line + RLS Part 6).
--          ADD COLUMN IF NOT EXISTS cannot convert an existing column type,
--          so without this block Part 6's `auth.uid()::text = user_id`
--          raises `operator does not exist: text = uuid`. uuid::text is a
--          lossless cast — safe on production rows (verified on live DB).
-- ───────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    _col_type text;
BEGIN
    SELECT data_type INTO _col_type
      FROM information_schema.columns
     WHERE table_name = 'ai_memory' AND column_name = 'user_id'
     LIMIT 1;

    IF _col_type = 'uuid' THEN
        -- RLS policies that reference user_id block ALTER TYPE. Drop every
        -- policy on the table here; Part 6 recreates the canonical owner-
        -- scoped set immediately after (same implicit transaction batch).
        DO $inner$
        DECLARE
            _policy text;
        BEGIN
            FOR _policy IN
                SELECT policyname FROM pg_policies WHERE tablename = 'ai_memory'
            LOOP
                EXECUTE format('DROP POLICY %I ON ai_memory', _policy);
                RAISE NOTICE 'dropped legacy policy % for user_id type reconciliation', _policy;
            END LOOP;
        END
        $inner$;

        ALTER TABLE ai_memory
            ALTER COLUMN user_id TYPE text
            USING user_id::text;
        RAISE NOTICE 'ai_memory.user_id converted UUID -> TEXT (auth.uid()::text contract)';
    ELSE
        RAISE NOTICE 'ai_memory.user_id already % — skipping conversion', _col_type;
    END IF;
END $$;

-- ───────────────────────────────────────────────────────────────────────────────
-- Part 4 — btree indexes (filtering / time queries) — all idempotent
-- ───────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_ai_memory_user_id        ON ai_memory (user_id);
CREATE INDEX IF NOT EXISTS ix_ai_memory_session_id     ON ai_memory (session_id);
CREATE INDEX IF NOT EXISTS ix_ai_memory_user_task      ON ai_memory (user_id, task_type);
CREATE INDEX IF NOT EXISTS ix_ai_memory_created_at_desc ON ai_memory (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_memory_user_created   ON ai_memory (user_id, created_at DESC);

-- ───────────────────────────────────────────────────────────────────────────────
-- Part 5 — vector ANN index: HNSW baseline (m=16, ef_construction=64)
--          created ONLY when no ANN index already exists (Alembic ships an
--          ivfflat twin — two ANN indexes would double write amplification)
-- ───────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    has_ann boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_indexes
         WHERE tablename = 'ai_memory'
           AND indexname IN (
               'ix_ai_memory_embedding_hnsw',
               'ix_ai_memory_embedding_ivfflat',
               'ai_memory_embedding_ivfflat',
               'ai_memory_embedding_idx'
           )
    ) INTO has_ann;

    IF NOT has_ann THEN
        CREATE INDEX ix_ai_memory_embedding_hnsw
            ON ai_memory USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        RAISE NOTICE 'ai_memory: HNSW index created (m=16, ef_construction=64)';
    ELSE
        RAISE NOTICE 'ai_memory: existing ANN index found — HNSW creation skipped';
    END IF;
END $$;

-- IVFFlat alternative (prefer when pgvector < 0.5 has no HNSW, or when build
-- time/memory matters more than recall; requires ANALYZE + periodic reindex):
--
--   CREATE INDEX IF NOT EXISTS ix_ai_memory_embedding_ivfflat
--       ON ai_memory USING ivfflat (embedding vector_cosine_ops)
--       WITH (lists = 100);
--
-- HNSW vs IVFFlat: HNSW = better recall/QPS, no training step, tolerant of
-- steady upserts (this table upserts constantly) at higher memory/build cost.
-- IVFFlat = cheaper build, but degrades unless maintained as the table grows.

-- ───────────────────────────────────────────────────────────────────────────────
-- Part 6 — RLS: enable, deny-by-default for anon, owner-scoped policies
--          user_id stores auth.uid()::text (api/routes/unified_memory_api.py:47)
--          NOTE: Supabase `service_role` carries BYPASSRLS — the FastAPI backend
--          (the only production writer) is unaffected by these policies.
-- ───────────────────────────────────────────────────────────────────────────────
ALTER TABLE ai_memory ENABLE ROW LEVEL SECURITY;

-- Explicit DENY for the anonymous role (stronger than RLS-empty-result semantics).
REVOKE ALL ON ai_memory FROM anon;

GRANT SELECT, INSERT, UPDATE, DELETE ON ai_memory TO authenticated;
GRANT ALL ON ai_memory TO service_role;

DROP POLICY IF EXISTS ai_memory_select_own ON ai_memory;
DROP POLICY IF EXISTS ai_memory_insert_own ON ai_memory;
DROP POLICY IF EXISTS ai_memory_update_own ON ai_memory;
DROP POLICY IF EXISTS ai_memory_delete_own ON ai_memory;

CREATE POLICY ai_memory_select_own ON ai_memory
    FOR SELECT TO authenticated
    USING (auth.uid()::text = user_id);

CREATE POLICY ai_memory_insert_own ON ai_memory
    FOR INSERT TO authenticated
    WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY ai_memory_update_own ON ai_memory
    FOR UPDATE TO authenticated
    USING (auth.uid()::text = user_id)
    WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY ai_memory_delete_own ON ai_memory
    FOR DELETE TO authenticated
    USING (auth.uid()::text = user_id);

-- ───────────────────────────────────────────────────────────────────────────────
-- Part 7 — updated_at trigger
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_ai_memory_touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_ai_memory_updated_at ON ai_memory;
CREATE TRIGGER trg_ai_memory_updated_at
    BEFORE UPDATE ON ai_memory
    FOR EACH ROW
    EXECUTE FUNCTION fn_ai_memory_touch_updated_at();

-- ───────────────────────────────────────────────────────────────────────────────
-- Part 8 — retention: default 180 days (AI_MEMORY_RETENTION_DAYS), documented in
--          docs/database/AI_MEMORY_SCHEMA_AUDIT.md §6; scheduler hooks:
--            * pg_cron example below (Supabase Dashboard → Database → Cron)
--            * app-side: Orchestrator._tasks (core/orchestration/
--              periodic_task_scheduler.py:50) or the MaintenancePipeline pattern
--              (core/maintenance_pipeline.py:162) calling this function
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_ai_memory_retention_cleanup(p_days int DEFAULT NULL)
RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_days    int := COALESCE(p_days, 180);
    v_deleted int;
BEGIN
    IF v_days < 1 THEN
        RAISE EXCEPTION 'fn_ai_memory_retention_cleanup: p_days must be >= 1 (got %)', v_days;
    END IF;

    DELETE FROM ai_memory
     WHERE created_at < now() - make_interval(days => v_days);

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$$;

REVOKE EXECUTE ON FUNCTION fn_ai_memory_retention_cleanup(int) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION fn_ai_memory_retention_cleanup(int) TO service_role;

-- Example pg_cron hook (uncomment + adjust schedule/days to enable):
--
-- CREATE EXTENSION IF NOT EXISTS pg_cron;
-- SELECT cron.schedule(
--     'ai-memory-retention-cleanup',          -- job name (unschedule key)
--     '30 3 * * *',                           -- daily 03:30 UTC
--     $$SELECT fn_ai_memory_retention_cleanup(180)$$
-- );
-- Rollback: SELECT cron.unschedule('ai-memory-retention-cleanup');

-- ───────────────────────────────────────────────────────────────────────────────
-- Part 9 — RPC reconciliation (live callers ↔ database functions)
--          audit §1.3: three drift bugs made recall paths silently fail
-- ───────────────────────────────────────────────────────────────────────────────

-- 9a. `match_memories` — called by AutoRAG (core/ai_memory/vector_store.py,
--     params: query_embedding / match_threshold / match_count / p_user_id) and
--     memory/long_term_memory.py — but DEFINED nowhere until now.
--     `content` falls back through metadata → content column → summary so both
--     the AutoRAG payload layout and cascade rows resolve.
--     ISSUE #1689 (CRITICAL, tenant isolation): p_user_id এখন MANDATORY —
--     আগে `p_user_id text DEFAULT NULL` + `(p_user_id IS NULL OR …)` ছিল,
--     ফলে NULL দিলে সব ইউজারের মেমরি ফেরত যেত (cross-tenant leak)। এখন:
--     · DEFAULT NULL নেই — PostgREST named-arg ছাড়া কল ব্যর্থ হবে
--     · কঠোর equality `m.user_id = p_user_id`
--     · একটি মাত্র স্পষ্ট agent-scope sentinel (`__agent_internal__`) শুধু
--       user_id IS NULL (agent-own learning) rows পায়
--     · GRANT থেকে anon বাদ (tenant-বিহীন caller নীতিগতভাবেই অগ্রাহ্য)
CREATE OR REPLACE FUNCTION match_memories(
    query_embedding vector(384),
    match_threshold float DEFAULT 0.7,
    match_count     int   DEFAULT 5,
    p_user_id       text
)
RETURNS TABLE (
    id         uuid,
    content    text,
    metadata   jsonb,
    similarity float
)
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT m.id,
           COALESCE(m.metadata->>'content', m.content, m.summary) AS content,
           m.metadata,
           1 - (m.embedding <=> query_embedding) AS similarity
      FROM ai_memory m
     WHERE m.embedding IS NOT NULL
       AND (
             m.user_id = p_user_id
             OR (p_user_id = '__agent_internal__' AND m.user_id IS NULL)
           )
       AND 1 - (m.embedding <=> query_embedding) > match_threshold
     ORDER BY m.embedding <=> query_embedding
     LIMIT match_count;
$$;

GRANT EXECUTE ON FUNCTION match_memories(vector, float, int, text) TO authenticated, service_role;

-- 9b. `match_ai_memory` with **p_user_id** — services/memory_service.py:825-833
--     calls the 4-arg RPC with a `p_user_id` named argument, but Alembic
--     2026_09_13_100000 named it `filter_user_id` → PostgREST PGRST202 → silent
--     Python-cosine fallback. Same identity (types) ⇒ replaces the Alembic
--     version; no Python caller uses `filter_user_id` (verified in audit §1.3).
CREATE OR REPLACE FUNCTION match_ai_memory(
    query_embedding vector(384),
    match_threshold float DEFAULT 0.55,
    match_count     int   DEFAULT 5,
    p_user_id       text  DEFAULT NULL
)
RETURNS TABLE (
    id          uuid,
    session_id  text,
    agent_type  text,
    task_type   text,
    summary     text,
    metadata    jsonb,
    created_at  timestamptz,
    similarity  float
)
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT m.id,
           m.session_id,
           m.agent_type,
           m.task_type,
           m.summary,
           m.metadata,
           m.created_at,
           1 - (m.embedding <=> query_embedding) AS similarity
      FROM ai_memory m
     WHERE m.embedding IS NOT NULL
       AND (p_user_id IS NULL OR m.user_id = p_user_id)
       AND 1 - (m.embedding <=> query_embedding) > match_threshold
     ORDER BY m.embedding <=> query_embedding
     LIMIT match_count;
$$;

GRANT EXECUTE ON FUNCTION match_ai_memory(vector, float, int, text) TO anon, authenticated, service_role;

-- 9c. `match_experiences` re-typed VECTOR(1536) → vector(384): callers pass
--     384-dim vectors (embed_for_pgvector) against a 1536-typed argument
--     (database/migrations/16_add_match_experiences_rpc.sql:23) → dimension
--     error at execution. Guarded: only re-typed when the live embedding column
--     is really 384; otherwise a NOTICE is raised and the DB is left untouched.
DO $$
DECLARE
    _dim int;
BEGIN
    SELECT character_maximum_length INTO _dim
      FROM information_schema.columns
     WHERE table_name = 'ai_memory' AND column_name = 'embedding'
     LIMIT 1;

    IF _dim = 384 THEN
        DROP FUNCTION IF EXISTS match_experiences(vector, int, float, text);
        CREATE OR REPLACE FUNCTION match_experiences(
            query_embedding   vector(384),
            match_count       int   DEFAULT 5,
            match_threshold   float DEFAULT 0.3,
            filter_collection text  DEFAULT 'experience'
        )
        RETURNS TABLE (
            id         uuid,
            summary    text,
            metadata   jsonb,
            similarity float
        )
        LANGUAGE sql
        STABLE
        SET search_path = public, pg_temp
        AS $fn$
            SELECT m.id,
                   m.summary,
                   m.metadata,
                   1 - (m.embedding <=> query_embedding) AS similarity
              FROM ai_memory m
             WHERE m.embedding IS NOT NULL
               AND m.metadata->>'collection' = filter_collection
               AND 1 - (m.embedding <=> query_embedding) > match_threshold
             ORDER BY m.embedding <=> query_embedding
             LIMIT match_count;
        $fn$;
        GRANT EXECUTE ON FUNCTION match_experiences(vector, int, float, text)
            TO anon, authenticated, service_role;
        RAISE NOTICE 'match_experiences re-typed to vector(384)';
    ELSE
        RAISE NOTICE 'ai_memory.embedding dim is % (not 384) — match_experiences left untouched', COALESCE(_dim, -1);
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════════════════
-- Part 10 — verification smoke (run after execution; see audit doc §8)
-- ═══════════════════════════════════════════════════════════════════════════════
-- SELECT to_regclass('public.ai_memory') AS table_exists,
--        relrowsecurity  AS rls_enabled
--   FROM pg_class WHERE oid = 'public.ai_memory'::regclass;
-- SELECT column_name, data_type, character_maximum_length AS vector_dim
--   FROM information_schema.columns
--  WHERE table_name = 'ai_memory' ORDER BY ordinal_position;
-- SELECT indexname FROM pg_indexes WHERE tablename = 'ai_memory';
-- SELECT policyname, cmd FROM pg_policies WHERE tablename = 'ai_memory';
-- SELECT proname FROM pg_proc WHERE pronamespace = 'public'::regnamespace
--   AND proname IN ('match_memories', 'match_ai_memory', 'match_ai_memories',
--                   'match_experiences', 'fn_ai_memory_retention_cleanup');
-- SELECT fn_ai_memory_retention_cleanup(100000);  -- retention dry-run: deletes nothing
--
-- Rollback: see docs/database/AI_MEMORY_SCHEMA_AUDIT.md §9 (functions, trigger,
-- policies, cron job are dropped individually; DROP TABLE ai_memory is the
-- last-resort equivalent of the Alembic downgrade).
-- ═══════════════════════════════════════════════════════════════════════════════
