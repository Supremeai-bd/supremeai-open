-- Migration: 02_phase2_setup.sql
-- Description: Sets up the database schema for Phase 2 (audit_logs, tools_registry, dynamic_skills)

-- 1. tools_registry table
CREATE TABLE IF NOT EXISTS tools_registry (
    tool_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    version TEXT DEFAULT '1.0.0',
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. dynamic_skills table
CREATE TABLE IF NOT EXISTS dynamic_skills (
    skill_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    code TEXT NOT NULL,
    language TEXT DEFAULT 'python',
    status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
    network_access BOOLEAN DEFAULT false,
    resource_limit_memory TEXT DEFAULT '128m',
    resource_limit_cpu DECIMAL(3,2) DEFAULT 0.5,
    timeout_seconds INTEGER DEFAULT 30,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. audit_logs table (Partitioned by month for performance)
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL,
    timestamp TIMESTAMP DEFAULT NOW(),
    user_id TEXT,
    action TEXT NOT NULL,
    tool_id TEXT,
    model TEXT,
    tokens_input INTEGER,
    tokens_output INTEGER,
    cost DECIMAL(10,6),
    latency_ms INTEGER,
    status TEXT,
    error_message TEXT,
    metadata JSONB,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Initial partition for June 2026
CREATE TABLE IF NOT EXISTS audit_logs_2026_06 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

-- Indexes
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_dynamic_skills_status ON dynamic_skills(status);

-- Enable Row Level Security (RLS)
ALTER TABLE tools_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE dynamic_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs_2026_06 ENABLE ROW LEVEL SECURITY;
