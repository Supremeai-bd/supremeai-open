-- Migration: 07_tenant_config.sql
-- Description: Per-tenant rate limits and billing tier configuration

CREATE TABLE IF NOT EXISTS tenant_limits (
    tenant_id TEXT PRIMARY KEY,
    requests_per_minute INTEGER DEFAULT 60,
    max_tokens_per_day INTEGER DEFAULT 100000,
    billing_tier TEXT DEFAULT 'free' CHECK (billing_tier IN ('free', 'pro', 'enterprise')),
    custom_limits JSONB DEFAULT '{}',
    stripe_customer_id TEXT,
    admin_override BOOLEAN DEFAULT false,
    override_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tenant_usage (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    requests_count INTEGER DEFAULT 0,
    tokens_count INTEGER DEFAULT 0,
    cost_usd DECIMAL(10,4) DEFAULT 0.0,
    billing_period_start TIMESTAMP DEFAULT NOW(),
    billing_period_end TIMESTAMP,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_limits_tier ON tenant_limits(billing_tier);
CREATE INDEX IF NOT EXISTS idx_tenant_usage_tenant ON tenant_usage(tenant_id);

-- Enable Row Level Security (RLS)
ALTER TABLE tenant_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_usage ENABLE ROW LEVEL SECURITY;
