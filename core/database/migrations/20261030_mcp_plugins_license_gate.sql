-- ============================================================================
-- #1668 — License + provenance gate: catalog metadata columns for mcp_plugins
-- Additive follow-up to 20261030_mcp_plugins_registry.sql (#1523 Phase-1 MVP).
--
-- The control-plane gate (infrastructure/mcp-control-plane
-- src/registry/license-gate.ts) rejects GPL-family licenses, unknown/
-- unverifiable licenses (S10: never accept a plugin whose upstream license
-- cannot be verified), and non-repository upstreams at catalog INGRESS.
-- These columns pin the machine-checkable metadata the gate evaluates so
-- the SQL registry and the control-plane catalog stay in sync.
--
-- NULL is an honest value for the Phase-1 provider-official / BYO rows that
-- pin no OSS upstream (telegram, web-search, google-drive, notion): their
-- gate verdict is REJECT_UNKNOWN_LICENSE by construction, surfaced (not
-- hidden) by marketplace.list_plugins. Seeded github row: MIT +
-- https://github.com/github/github-mcp-server (verified public repository).
-- ============================================================================

ALTER TABLE mcp_plugins
    ADD COLUMN IF NOT EXISTS license VARCHAR(128);

ALTER TABLE mcp_plugins
    ADD COLUMN IF NOT EXISTS upstream_url TEXT;

COMMENT ON COLUMN mcp_plugins.license IS
    '#1668 SPDX license expression of the upstream project; NULL = unverifiable (gate-rejected at ingress for NEW registrations).';
COMMENT ON COLUMN mcp_plugins.upstream_url IS
    '#1668 upstream repository URL (https, code-hosting host, owner/repo); marketing/docs pages are rejected as vendored markers.';

-- Seed parity with the control-plane catalog: the GitHub row pins its
-- verified upstream. The other Phase-1 rows stay NULL (no verified OSS
-- upstream pinned at MVP time — filling them is an admin-lane verification
-- task, never a default).
UPDATE mcp_plugins
   SET license = 'MIT',
       upstream_url = 'https://github.com/github/github-mcp-server'
 WHERE plugin_id = 'github'
   AND license IS NULL;
