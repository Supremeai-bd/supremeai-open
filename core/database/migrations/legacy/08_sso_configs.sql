-- Migration: 08_sso_configs.sql
-- Description: SSO provider configuration per tenant (SAML / OIDC)

CREATE TABLE IF NOT EXISTS sso_configs (
    tenant_id TEXT PRIMARY KEY,
    provider TEXT CHECK (provider IN ('saml', 'oidc', 'google', 'azure', 'okta')),
    enabled BOOLEAN DEFAULT false,
    config JSONB NOT NULL DEFAULT '{}',
    sp_entity_id TEXT,
    acs_url TEXT,
    idp_entity_id TEXT,
    idp_sso_url TEXT,
    idp_slo_url TEXT,
    idp_x509_cert TEXT,
    sp_x509_cert TEXT,
    sp_private_key TEXT,
    oidc_client_id TEXT,
    oidc_client_secret TEXT,
    oidc_redirect_uri TEXT,
    oidc_domain TEXT,
    oidc_tenant TEXT,
    group_role_mapping JSONB DEFAULT '{}',
    metadata XML,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sso_sessions (
    session_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    email TEXT,
    roles TEXT[] DEFAULT '{}',
    groups TEXT[] DEFAULT '{}',
    method TEXT,
    idp_session_index TEXT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sso_sessions_tenant ON sso_sessions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sso_sessions_user ON sso_sessions(user_id);

-- Enable Row Level Security (RLS)
ALTER TABLE sso_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE sso_sessions ENABLE ROW LEVEL SECURITY;
