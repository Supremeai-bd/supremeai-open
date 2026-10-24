-- Migration: 04_schema_upgrade.sql
-- Description: Upgrades tables to match the full Admin Plan specifications.

-- 1. Upgrade github_repos
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'github_repos' AND column_name = 'repo_name'
    ) THEN
        ALTER TABLE github_repos RENAME COLUMN repo_name TO id;
    END IF;
END $$;
ALTER TABLE github_repos ALTER COLUMN owner DROP NOT NULL;
ALTER TABLE github_repos
ADD COLUMN IF NOT EXISTS name TEXT,
ADD COLUMN IF NOT EXISTS url TEXT,
ADD COLUMN IF NOT EXISTS category TEXT,
ADD COLUMN IF NOT EXISTS priority TEXT CHECK (priority IN ('critical', 'high', 'medium', 'low')),
ADD COLUMN IF NOT EXISTS purpose TEXT,
ADD COLUMN IF NOT EXISTS install_command TEXT,
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active' CHECK (status IN ('active', 'archived', 'deprecated')),
ADD COLUMN IF NOT EXISTS added_date TIMESTAMP DEFAULT NOW();

-- 2. Upgrade tools_registry
ALTER TABLE tools_registry
ADD COLUMN IF NOT EXISTS file_path TEXT,
ADD COLUMN IF NOT EXISTS category TEXT,
ADD COLUMN IF NOT EXISTS cost_per_call DECIMAL(10,6),
ADD COLUMN IF NOT EXISTS success_rate DECIMAL(3,2),
ADD COLUMN IF NOT EXISTS avg_latency_ms INTEGER,
ADD COLUMN IF NOT EXISTS total_calls INTEGER DEFAULT 0;

-- 3. Upgrade dynamic_skills
ALTER TABLE dynamic_skills
ADD COLUMN IF NOT EXISTS sandbox_required BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS approved_by TEXT,
ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS usage_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS failure_count INTEGER DEFAULT 0;
