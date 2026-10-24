-- Migration: 20_create_browser_credentials.sql
-- Purpose: Encrypted browser credentials schema with strict RLS and audit safety
-- Fields: id, owner_id, provider, label, encrypted_secret, secret_metadata, created_at, updated_at, is_revoked, revoked_at

CREATE TABLE IF NOT EXISTS public.browser_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    label TEXT NOT NULL,
    encrypted_secret TEXT NOT NULL,
    key_ref TEXT,
    secret_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for efficient ownership queries and lookups
CREATE INDEX IF NOT EXISTS idx_browser_credentials_owner_id ON public.browser_credentials (owner_id);
CREATE INDEX IF NOT EXISTS idx_browser_credentials_provider ON public.browser_credentials (provider);
CREATE INDEX IF NOT EXISTS idx_browser_credentials_is_revoked ON public.browser_credentials (is_revoked);
CREATE INDEX IF NOT EXISTS idx_browser_credentials_created_at ON public.browser_credentials (created_at DESC);

-- Enable Row Level Security
ALTER TABLE public.browser_credentials ENABLE ROW LEVEL SECURITY;

-- Supabase RLS Policies: Authenticated users can only read, insert, update, and delete their own credentials
DROP POLICY IF EXISTS browser_credentials_select_own ON public.browser_credentials;
CREATE POLICY browser_credentials_select_own ON public.browser_credentials
    FOR SELECT TO authenticated
    USING (owner_id = auth.uid()::text);

DROP POLICY IF EXISTS browser_credentials_insert_own ON public.browser_credentials;
CREATE POLICY browser_credentials_insert_own ON public.browser_credentials
    FOR INSERT TO authenticated
    WITH CHECK (owner_id = auth.uid()::text);

DROP POLICY IF EXISTS browser_credentials_update_own ON public.browser_credentials;
CREATE POLICY browser_credentials_update_own ON public.browser_credentials
    FOR UPDATE TO authenticated
    USING (owner_id = auth.uid()::text)
    WITH CHECK (owner_id = auth.uid()::text);

DROP POLICY IF EXISTS browser_credentials_delete_own ON public.browser_credentials;
CREATE POLICY browser_credentials_delete_own ON public.browser_credentials
    FOR DELETE TO authenticated
    USING (owner_id = auth.uid()::text);
