-- ═══════════════════════════════════════════════════════════════════════
-- SupremeAI Migration 001 (production-readiness plan, item 4a)
-- match_ai_memories — pgvector RPC for database-side similarity ranking
--
-- বাংলা নোট: আগে query_context() সর্বোচ্চ ২০০০ রো Python-এ লোড করে
-- ইন-মেমোরি কসাইন চালাত — ইভেন্ট লুপে ~সেকেন্ড স্তালের ঝুঁকি। এই RPC
-- দিলে similarity ranking সম্পূর্ণ ডাটাবেসেই হয় (ivfflat/HNSW index)।
--
-- চালানোর স্থান: Supabase SQL Editor (বা psql) — একবারই।
-- ফাংশনটি unconstrained `vector` ব্যবহার করে, তাই 384-dim
-- (all-MiniLM-L6-v2) ও 1536-dim — দুই কলাম লেআউটেই কাজ করবে।
-- ═══════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────────────────────────────────────
-- ধাপ ১: ai_memory.embedding TEXT → vector কনভার্সন (শুধু যদি TEXT হয়)।
-- pgvector-এর টেক্সট ইনপুট ফরম্যাট '[0.1,0.2,...]' হলো JSON অ্যারে স্ট্রিং
-- হওয়ায় বিদ্যমান JSON স্ট্রিং সরাসরি cast করা যায়। কোনো কারণে কনভার্শন
-- ব্যর্থ হলে (দূষিত রো ইত্যাদি) WARNING দিয়ে এগিয়ে যায় — কোড-সাইড প্রোব
-- সেক্ষেত্রে পুরনো Python-কসাইন fallback ব্যবহার করবে (graceful degradation)।
-- ─────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    _col_type text;
BEGIN
    SELECT data_type
      INTO _col_type
      FROM information_schema.columns
     WHERE table_name = 'ai_memory'
       AND column_name = 'embedding'
     LIMIT 1;

    IF _col_type IS NULL THEN
        RAISE NOTICE 'ai_memory table not found yet - CascadeMemoryService DDL will create it; re-run this migration afterwards.';
        RETURN;
    END IF;

    IF _col_type = 'text' THEN
        BEGIN
            ALTER TABLE ai_memory
                ALTER COLUMN embedding TYPE vector
                USING NULLIF(trim(embedding), '')::vector;
            RAISE NOTICE 'ai_memory.embedding converted TEXT -> vector';
        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'Could not convert ai_memory.embedding to vector (%). Python-cosine fallback stays active.', SQLERRM;
            RETURN;  -- index creation অর্থহীন, এখানেই শেষ
        END;
    ELSE
        RAISE NOTICE 'ai_memory.embedding already % - skipping conversion', _col_type;
    END IF;

    -- ─────────────────────────────────────────────────────────────────────
    -- ধাপ ২: ANN index (ivfflat, cosine ops) — ছোট টেবিলে lists=100 যথেষ্ট।
    -- ─────────────────────────────────────────────────────────────────────
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
         WHERE tablename = 'ai_memory' AND indexname = 'ai_memory_embedding_ivfflat'
    ) THEN
        CREATE INDEX ai_memory_embedding_ivfflat
            ON ai_memory USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────
-- ধাপ ৩: match_ai_memories RPC — user/session ফিল্টারসহ।
-- বিদ্যমান match_ai_memory (docs/api-database/migrations/ai_memory_migration.sql)
-- ৩-প্যারামিটার ভার্সনের সাথে নাম-সংঘর্ষ এড়াতে বহুল-স্বীকৃত plural নাম।
-- ─────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION match_ai_memories(
    query_embedding    vector,
    match_threshold    float DEFAULT 0.7,
    match_count        int   DEFAULT 5,
    filter_user_id     text  DEFAULT NULL,
    filter_session_id  text  DEFAULT NULL
)
RETURNS TABLE (
    id          uuid,
    user_id     text,
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
AS $$
    SELECT m.id,
           m.user_id,
           m.session_id,
           m.agent_type,
           m.task_type,
           m.summary,
           m.metadata,
           m.created_at,
           1 - (m.embedding <=> query_embedding) AS similarity
      FROM ai_memory m
     WHERE (filter_user_id    IS NULL OR m.user_id    = filter_user_id)
       AND (filter_session_id IS NULL OR m.session_id = filter_session_id)
       AND m.embedding IS NOT NULL
       AND 1 - (m.embedding <=> query_embedding) > match_threshold
     ORDER BY m.embedding <=> query_embedding
     LIMIT match_count;
$$;

GRANT EXECUTE ON FUNCTION match_ai_memories(vector, float, int, text, text) TO anon, authenticated, service_role;
