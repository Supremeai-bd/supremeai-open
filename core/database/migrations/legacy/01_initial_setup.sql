-- Migration: 01_initial_setup.sql
-- Description: Sets up the initial database schema for SupremeAI 2.0 (github_repos, system_config, feature_flags)

-- 1. github_repos table
CREATE TABLE IF NOT EXISTS github_repos (
    repo_name TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    description TEXT,
    stars INTEGER DEFAULT 0,
    language TEXT,
    last_indexed TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- 2. system_config table
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    category TEXT
);

-- 3. feature_flags table
CREATE TABLE IF NOT EXISTS feature_flags (
    feature_name TEXT PRIMARY KEY,
    enabled BOOLEAN DEFAULT false,
    rollout_percentage INTEGER DEFAULT 0 CHECK (rollout_percentage BETWEEN 0 AND 100),
    allowed_users TEXT[],
    description TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_github_repos_stars ON github_repos(stars DESC);
CREATE INDEX IF NOT EXISTS idx_system_config_category ON system_config(category);

-- Enable Row Level Security (RLS)
ALTER TABLE github_repos ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_flags ENABLE ROW LEVEL SECURITY;
