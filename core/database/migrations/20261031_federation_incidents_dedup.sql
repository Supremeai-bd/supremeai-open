-- ============================================================================
-- Migration: 20261031_federation_incidents_dedup.sql
-- Description: Authoritative unique incident registry for zero-duplicate incidents
-- Invariant: UNIQUE(fingerprint) ensures atomic get-or-create across all agents
-- ============================================================================

CREATE TABLE IF NOT EXISTS federation_incidents (
    fingerprint VARCHAR(64) PRIMARY KEY,
    environment VARCHAR(32) NOT NULL DEFAULT 'production',
    service VARCHAR(64) NOT NULL,
    normalized_error VARCHAR(128) NOT NULL,
    affected_component VARCHAR(128) NOT NULL,
    root_cause_family VARCHAR(64) NOT NULL DEFAULT 'unspecified',
    canonical_issue_number INTEGER,
    active_pr_number INTEGER,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    evidence_count INTEGER NOT NULL DEFAULT 1,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for querying open incidents by service
CREATE INDEX IF NOT EXISTS idx_federation_incidents_service_status 
ON federation_incidents(service, status);

-- Index for finding active issues
CREATE INDEX IF NOT EXISTS idx_federation_incidents_canonical_issue 
ON federation_incidents(canonical_issue_number) 
WHERE canonical_issue_number IS NOT NULL;

COMMENT ON TABLE federation_incidents IS 'SSOT registry for deduplicating automated incident reports and prevent twin PRs/issues';

