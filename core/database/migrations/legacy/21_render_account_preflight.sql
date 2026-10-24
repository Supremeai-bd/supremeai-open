-- Migration: 21_render_account_preflight.sql
-- Purpose: Intelligent Render Deploy Preflight tables (admin_task.md compliance)
-- Tables:
--   1. public.render_account_status (Tracks quota, cooldown, recheck dates, and states per Render role)
--   2. public.render_preflight_events (Audit event log for state transitions and decisions)
--   3. public.render_preflight_alerts (Deduplicated alert notifications for quota limits and failures)

-- 1. Create render_account_status table
CREATE TABLE IF NOT EXISTS public.render_account_status (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_role VARCHAR(64) NOT NULL, -- 'core', 'worker', 'scraper', 'mcp'
    provider VARCHAR(64) NOT NULL DEFAULT 'render',
    service_id VARCHAR(128) NOT NULL,
    status VARCHAR(64) NOT NULL DEFAULT 'unknown', -- 'ready', 'unknown', 'deploying', 'limit_detected', 'cooldown', 'recheck_required', 'blocked', 'error'
    reason_code VARCHAR(128), -- e.g. 'build_time_limit', 'api_unavailable', 'missing_credentials'
    reason_message TEXT,
    usage_minutes NUMERIC(10, 2),
    safe_build_minutes NUMERIC(10, 2) DEFAULT 450.00,
    detected_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    recheck_at TIMESTAMPTZ,
    reset_at TIMESTAMPTZ,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    last_render_payload JSONB, -- Redacted before persistence
    manual_override BOOLEAN NOT NULL DEFAULT FALSE,
    manual_override_by TEXT,
    manual_override_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_render_account_role UNIQUE (provider, account_role, service_id)
);

-- Indexes for render_account_status
CREATE INDEX IF NOT EXISTS idx_render_account_status_recheck ON public.render_account_status (status, recheck_at);
CREATE INDEX IF NOT EXISTS idx_render_account_status_role_updated ON public.render_account_status (account_role, updated_at DESC);

-- 2. Create render_preflight_events table
CREATE TABLE IF NOT EXISTS public.render_preflight_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_status_id UUID REFERENCES public.render_account_status(id) ON DELETE CASCADE,
    workflow_run_id TEXT,
    commit_sha TEXT,
    event_type TEXT NOT NULL, -- 'check', 'limit_detected', 'cooldown_started', 'recheck', 'ready', 'deploy_skipped', 'manual_override'
    old_status TEXT,
    new_status TEXT NOT NULL,
    reason_code TEXT,
    details JSONB, -- Redacted secrets
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for render_preflight_events
CREATE INDEX IF NOT EXISTS idx_render_preflight_events_status_time ON public.render_preflight_events (account_status_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_render_preflight_events_workflow ON public.render_preflight_events (workflow_run_id);

-- 3. Create render_preflight_alerts table
CREATE TABLE IF NOT EXISTS public.render_preflight_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_role VARCHAR(64) NOT NULL,
    alert_type VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL DEFAULT 'warning', -- 'info', 'warning', 'critical'
    message TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    notification_status VARCHAR(64) NOT NULL DEFAULT 'pending',
    reason_code VARCHAR(128),
    CONSTRAINT uq_render_alert_dedup UNIQUE (account_role, reason_code, notification_status)
);

CREATE INDEX IF NOT EXISTS idx_render_preflight_alerts_active ON public.render_preflight_alerts (account_role, resolved_at);

-- 4. Enable Row Level Security (RLS)
ALTER TABLE public.render_account_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.render_preflight_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.render_preflight_alerts ENABLE ROW LEVEL SECURITY;

-- Read policies for authenticated administrators only
DROP POLICY IF EXISTS render_account_status_read_admin ON public.render_account_status;
CREATE POLICY render_account_status_read_admin ON public.render_account_status
    FOR SELECT TO authenticated
    USING (coalesce((auth.jwt() ->> 'is_admin')::boolean, false) = true);

DROP POLICY IF EXISTS render_preflight_events_read_admin ON public.render_preflight_events;
CREATE POLICY render_preflight_events_read_admin ON public.render_preflight_events
    FOR SELECT TO authenticated
    USING (coalesce((auth.jwt() ->> 'is_admin')::boolean, false) = true);

DROP POLICY IF EXISTS render_preflight_alerts_read_admin ON public.render_preflight_alerts;
CREATE POLICY render_preflight_alerts_read_admin ON public.render_preflight_alerts
    FOR SELECT TO authenticated
    USING (coalesce((auth.jwt() ->> 'is_admin')::boolean, false) = true);
