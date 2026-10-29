-- ============================================================================
-- SupremeAI MCP Plugins Marketplace Registry (#1523 — Roadmap Phase 1 MVP)
-- Compatible with PostgreSQL 15+ and Supabase Postgres
--
-- ZERO-RISK BYO-CREDENTIAL INVARIANT:
--   No table in this schema ever stores a plaintext credential. The
--   `credential_vault_ref` column holds ONLY a vault/secret-manager
--   REFERENCE (e.g. "vault:github-token"). The secret itself lives in the
--   user's chosen secret store and is injected at relay time by the
--   control plane. Anything that looks like a live token value must be
--   rejected upstream (see marketplace.connect_plugin guard).
--
-- FLOW CONTRACT (connects the EXISTING federation tools):
--   1. User picks a plugin from `mcp_plugins` (catalog row).
--   2. One-click BYO connect -> control plane `marketplace.connect_plugin`
--      delegates to the SAME registry as `client.register_mcp_server`
--      (remote_mcp_servers, trust-gated, status 'pending').
--   3. `client.discover_mcp_server` pins SHA-256 tool descriptors.
--   4. Only after descriptor approval does `remote.call` relay —
--      fail-closed against descriptor drift (#1712).
-- ============================================================================

-- 1. Marketplace plugin catalog (templates, never tenant data)
CREATE TABLE IF NOT EXISTS mcp_plugins (
    plugin_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    category VARCHAR(64) NOT NULL DEFAULT 'productivity',
    description TEXT NOT NULL,
    provider VARCHAR(64) NOT NULL,
    -- Hosted-endpoint default the user may override in the BYO flow.
    -- NULL means the plugin is self-hosted by design: the user MUST supply
    -- their own endpoint (zero default-endpoint trust).
    endpoint_template TEXT,
    protocol VARCHAR(32) NOT NULL DEFAULT 'streamable-http',
    -- Credential FIELD SPECS only: [{name, label, required, secret}]
    -- Never values. `secret: true` fields must map to vault refs.
    credential_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    trust_level VARCHAR(32) NOT NULL DEFAULT 'untrusted',
    docs_url TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Per-tenant BYO connections (the "installed plugins" ledger)
CREATE TABLE IF NOT EXISTS mcp_plugin_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id VARCHAR(64) NOT NULL REFERENCES mcp_plugins(plugin_id) ON DELETE RESTRICT,
    tenant_id VARCHAR(64) NOT NULL,
    -- id returned by the federation registry (client.register_mcp_server);
    -- joins the connection to descriptor pins and remote.call governance.
    remote_server_id TEXT NOT NULL,
    -- Vault REFERENCE only — NEVER a plaintext token (see header invariant).
    credential_vault_ref TEXT NOT NULL
        CHECK (credential_vault_ref ~ '^vault:[A-Za-z0-9._:-]+$'),
    endpoint_used TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'pending', -- pending|active|quarantined|revoked
    connected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_plugin_conn_tenant UNIQUE (tenant_id, plugin_id)
);

CREATE INDEX IF NOT EXISTS idx_mcp_plugin_conn_tenant
ON mcp_plugin_connections (tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_mcp_plugins_enabled
ON mcp_plugins (enabled, category);

-- 3. Seed catalog: the five Phase-1 BYO providers.
-- endpoint_template is set ONLY for vendors that publish an official hosted
-- MCP endpoint; the rest are intentionally NULL (self-hosted BYO).
INSERT INTO mcp_plugins (plugin_id, name, category, description, provider,
                         endpoint_template, protocol, credential_fields, trust_level, docs_url)
VALUES
    ('github', 'GitHub', 'devtools',
     'Official remote GitHub MCP server: repos, issues, pull requests and workflows under governed tool relay.',
     'github', 'https://api.githubcopilot.com/mcp/', 'streamable-http',
     '[{"name":"github-token","label":"GitHub personal access token (vault ref)","required":true,"secret":true}]'::jsonb,
     'untrusted', 'https://github.com/github/github-mcp-server'),
    ('telegram', 'Telegram', 'messaging',
     'Bring your own Telegram bot gateway MCP server for message send/receive automation inside your tenant.',
     'telegram', NULL, 'streamable-http',
     '[{"name":"bot-token","label":"Telegram bot token (vault ref)","required":true,"secret":true}]'::jsonb,
     'untrusted', NULL),
    ('web-search', 'Web Search', 'research',
     'Bring your own web-search MCP server (SearXNG, Brave-compatible relays, or any compatible endpoint).',
     'web-search', NULL, 'streamable-http',
     '[{"name":"search-api-key","label":"Search API key (vault ref)","required":true,"secret":true}]'::jsonb,
     'untrusted', NULL),
    ('google-drive', 'Google Drive', 'productivity',
     'Bring your own Google Drive MCP server for file listing, reading and sharing workflows.',
     'google', NULL, 'streamable-http',
     '[{"name":"drive-token","label":"Google OAuth token (vault ref)","required":true,"secret":true}]'::jsonb,
     'untrusted', NULL),
    ('notion', 'Notion', 'productivity',
     'Official hosted Notion MCP server: pages, databases and comments under governed tool relay.',
     'notion', 'https://mcp.notion.com/mcp', 'streamable-http',
     '[{"name":"notion-token","label":"Notion integration token (vault ref)","required":true,"secret":true}]'::jsonb,
     'untrusted', 'https://developers.notion.com/docs/mcp')
ON CONFLICT (plugin_id) DO NOTHING;

-- 4. Supabase row-level security: tenants only ever see their own rows.
ALTER TABLE mcp_plugins ENABLE ROW LEVEL SECURITY;
ALTER TABLE mcp_plugin_connections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS mcp_plugins_public_catalog ON mcp_plugins;
CREATE POLICY mcp_plugins_public_catalog ON mcp_plugins
    FOR SELECT USING (enabled = TRUE);

DROP POLICY IF EXISTS mcp_plugin_conn_tenant_isolation ON mcp_plugin_connections;
CREATE POLICY mcp_plugin_conn_tenant_isolation ON mcp_plugin_connections
    FOR ALL USING (
    tenant_id = COALESCE(
        current_setting('request.jwt.claim.tenant_id', TRUE),
        current_setting('app.tenant_id', TRUE)
    )
);

COMMENT ON TABLE mcp_plugins IS
    '#1523 Marketplace MVP catalog: plugin TEMPLATES only — no tenant data, no credentials.';
COMMENT ON COLUMN mcp_plugin_connections.credential_vault_ref IS
    'Vault/secret-manager REFERENCE (vault:<key>). Plaintext is forbidden by schema CHECK and by the connect-plugin guard.';
