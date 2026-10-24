-- Migration: 03_user_preferences_and_metrics.sql
-- Description: Adds user_preferences and usage_metrics tables for personalization and analytics

-- 1. user_preferences table
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    theme TEXT DEFAULT 'dark',
    default_model TEXT DEFAULT 'gpt-4o',
    max_tokens INTEGER DEFAULT 4096,
    auto_save BOOLEAN DEFAULT true,
    custom_shortcuts JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. usage_metrics table (aggregated daily metrics)
CREATE TABLE IF NOT EXISTS usage_metrics (
    date DATE PRIMARY KEY,
    total_requests INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost DECIMAL(10,2) DEFAULT 0.00,
    unique_users INTEGER DEFAULT 0,
    avg_latency_ms INTEGER DEFAULT 0,
    error_rate DECIMAL(5,2) DEFAULT 0.00
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_user_preferences_updated_at ON user_preferences(updated_at);
CREATE INDEX IF NOT EXISTS idx_usage_metrics_date ON usage_metrics(date DESC);

-- Enable Row Level Security (RLS)
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_metrics ENABLE ROW LEVEL SECURITY;
