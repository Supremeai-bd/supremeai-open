-- Migration: 09_offline_sync_logs.sql
-- Description: Offline action queue and sync tracking for mobile/web clients

CREATE TABLE IF NOT EXISTS offline_sync_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_id TEXT,
    action_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    status TEXT DEFAULT 'synced' CHECK (status IN ('pending', 'synced', 'failed', 'conflict')),
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS offline_sync_conflicts (
    id BIGSERIAL PRIMARY KEY,
    sync_log_id BIGINT NOT NULL REFERENCES offline_sync_logs(id) ON DELETE CASCADE,
    conflict_type TEXT NOT NULL,
    server_data JSONB,
    client_data JSONB,
    resolution TEXT CHECK (resolution IN ('server_wins', 'client_wins', 'manual', 'pending')),
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_offline_sync_user ON offline_sync_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_offline_sync_status ON offline_sync_logs(status);

-- Enable Row Level Security (RLS)
ALTER TABLE offline_sync_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE offline_sync_conflicts ENABLE ROW LEVEL SECURITY;
