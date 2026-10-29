-- ============================================================================
-- SupremeAI Orchestrator Brain & Model Registry Schema
-- Compatible with PostgreSQL 15+ and Supabase Postgres
-- ============================================================================

-- 1. Connected AI Models Registry
CREATE TABLE IF NOT EXISTS orchestrator_models (
    model_id VARCHAR(64) PRIMARY KEY,
    model_name VARCHAR(128) NOT NULL,
    provider VARCHAR(64) NOT NULL, -- e.g. openai, anthropic, google, local_gguf
    api_endpoint TEXT NOT NULL,
    vault_secret_ref VARCHAR(128) NOT NULL, -- Secure vault key reference (never plaintext)
    connection_status VARCHAR(32) DEFAULT 'active', -- active, inactive, rate_limited, error
    supports_text BOOLEAN DEFAULT TRUE,
    supports_image BOOLEAN DEFAULT FALSE,
    supports_code BOOLEAN DEFAULT TRUE,
    max_context_length INTEGER DEFAULT 8192,
    avg_cost_per_1k_tokens NUMERIC(10, 6) DEFAULT 0.000000,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Category Performance Profiles (One-to-Many with Models)
CREATE TABLE IF NOT EXISTS orchestrator_category_performance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id VARCHAR(64) REFERENCES orchestrator_models(model_id) ON DELETE CASCADE,
    category VARCHAR(64) NOT NULL, -- code_generation, creative_writing, data_analysis, translation, etc.
    avg_quality NUMERIC(5, 2) DEFAULT 75.00, -- 0 to 100
    avg_latency_ms INTEGER DEFAULT 800,
    success_rate NUMERIC(5, 2) DEFAULT 100.00,
    total_tasks INTEGER DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_model_category UNIQUE (model_id, category)
);

CREATE INDEX IF NOT EXISTS idx_cat_perf_lookup 
ON orchestrator_category_performance (category, avg_quality DESC);

-- 3. Routing Engine Configuration (Weights and Exploration Policies)
CREATE TABLE IF NOT EXISTS orchestrator_routing_config (
    config_key VARCHAR(64) PRIMARY KEY,
    weight_quality NUMERIC(4, 3) DEFAULT 0.500,
    weight_latency NUMERIC(4, 3) DEFAULT 0.200,
    weight_cost NUMERIC(4, 3) DEFAULT 0.200,
    exploration_rate NUMERIC(4, 3) DEFAULT 0.100, -- 10% epsilon exploration
    min_tasks_before_trust INTEGER DEFAULT 10,
    decay_factor NUMERIC(4, 3) DEFAULT 0.950, -- recency decay
    fallback_chain JSONB DEFAULT '["local_tiny_brain", "qwen2.5_coder", "gemini_flash"]'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Task Request & Execution Logs (Tracking & Continuous Learning Loop)
CREATE TABLE IF NOT EXISTS orchestrator_task_logs (
    request_id VARCHAR(64) PRIMARY KEY,
    user_input_raw TEXT NOT NULL,
    normalized_intent TEXT,
    detected_category VARCHAR(64) NOT NULL,
    confidence_score NUMERIC(5, 2) DEFAULT 90.00,
    selected_model VARCHAR(64) REFERENCES orchestrator_models(model_id),
    routing_reason TEXT,
    response_time_ms INTEGER,
    validation_passed BOOLEAN DEFAULT TRUE,
    issues_detected JSONB DEFAULT '[]'::jsonb,
    explicit_user_feedback VARCHAR(32) DEFAULT 'none', -- positive, negative, neutral, none
    follow_up_correction BOOLEAN DEFAULT FALSE,
    satisfaction_inferred NUMERIC(5, 2) DEFAULT 80.00,
    cost_incurred NUMERIC(10, 6) DEFAULT 0.000000,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_logs_cat_time 
ON orchestrator_task_logs (detected_category, created_at DESC);
