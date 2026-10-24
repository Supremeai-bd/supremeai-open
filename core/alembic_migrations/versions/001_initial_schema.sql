-- ============================================================
-- ⚠️ HISTORICAL / SUPERSEDED — DO NOT USE AS CURRENT SCHEMA REFERENCE
-- ============================================================
-- This file is kept for migration lineage/history integrity only. It does
-- NOT reflect the current production database. Production has evolved to
-- a different architecture (ai_memory, dynamic_agents, execution_logs,
-- etc. replacing users/agents/memory_vectors/tool_executions/
-- hitl_approvals from this file).
--
-- The single source of truth for what must exist in production is:
--   backend/database/contracts/schema_contract.yaml
-- enforced by:
--   scripts/ci/check_database_schema.py (CI job: db-schema-check)
--
-- See audit findings 2026-08-30 (commit 627bec68db) for full context.
-- ============================================================
--
-- SupremeAI - Initial Database Schema Migration
-- Version: 001_initial
-- Description: Creates core tables for users, agents, conversations, memory, HITL
-- ============================================================

BEGIN;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";  -- pgvector for AI embeddings

-- ============================================================
-- 1. USERS TABLE
-- Authentication and authorization
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    -- Primary key using UUID for distributed system compatibility
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Authentication fields
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,  -- bcrypt hash
    
    -- Profile information
    full_name VARCHAR(255) NOT NULL,
    avatar_url VARCHAR(500),
    
    -- Role-based access control
    role VARCHAR(50) DEFAULT 'user' 
        CHECK (role IN ('user', 'admin', 'agent_operator')),
    
    -- Account status
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    
    -- Multi-factor authentication
    mfa_secret VARCHAR(255),  -- TOTP secret (encrypted)
    mfa_enabled BOOLEAN DEFAULT FALSE,
    backup_codes TEXT[],     -- Encrypted backup codes
    
    -- Security tracking
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMPTZ,
    password_changed_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Session management
    last_login_at TIMESTAMPTZ,
    last_login_ip INET,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for users table
CREATE INDEX idx_users_email ON users(email) WHERE is_active = TRUE;
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_created_at ON users(created_at DESC);

-- ============================================================
-- 2. REFRESH TOKENS TABLE
-- JWT refresh token storage
-- ============================================================
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Token relationship
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,  -- SHA256 hash of token
    
    -- Token metadata
    device_info JSONB DEFAULT '{}',
    ip_address INET,
    
    -- Expiration and revocation
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    revoke_reason VARCHAR(100),
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for token lookup and cleanup
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_expires_at ON refresh_tokens(expires_at) 
    WHERE revoked_at IS NULL;

-- ============================================================
-- 3. AGENTS TABLE
-- AI agent definitions and configurations
-- ============================================================
CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Ownership
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Agent identity
    name VARCHAR(255) NOT NULL,
    description TEXT,
    avatar_url VARCHAR(500),
    
    -- Agent type and configuration
    type VARCHAR(50) NOT NULL 
        CHECK (type IN ('conversational', 'task_agent', 'analyst', 'orchestrator')),
    
    status VARCHAR(50) DEFAULT 'created' 
        CHECK (status IN ('created', 'configured', 'active', 'paused', 'terminated', 'error')),
    
    -- Agent behavior configuration (JSONB for flexibility)
    config JSONB NOT NULL DEFAULT '{}',
    system_prompt TEXT,
    
    -- Model configuration
    model_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    /*
    Example model_config:
    {
        "provider": "openai",
        "model": "gpt-4-turbo",
        "temperature": 0.7,
        "max_tokens": 4096,
        "top_p": 1.0,
        "frequency_penalty": 0,
        "presence_penalty": 0
    }
    */
    
    -- Tool permissions (which tools this agent can use)
    tool_permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
    /*
    Example: ["web_search", "calculator", "code_executor", "file_read"]
    */
    
    -- Human-in-the-Loop policy
    hitl_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    /*
    Example:
    {
        "enabled": true,
        "auto_approve_patterns": ["read:*", "calculate:*"],
        "require_approval_patterns": ["write:*", "delete:*", "send_email:*"],
        "escalation_timeout_minutes": 60,
        "notify_on_escalation": true
    }
    */
    
    -- Memory configuration
    memory_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    /*
    Example:
    {
        "working_memory_max_messages": 100,
        "enable_episodic_memory": true,
        "enable_procedural_memory": false,
        "episodic_retention_days": 90,
        "importance_threshold": 0.6
    }
    */
    
    -- Rate limiting per agent
    rate_limits JSONB NOT NULL DEFAULT '{}'::jsonb,
    /*
    Example:
    {
        "requests_per_minute": 30,
        "tokens_per_minute": 60000,
        "daily_token_limit": 1000000
    }
    */
    
    -- Usage statistics (updated by background job)
    stats JSONB NOT NULL DEFAULT '{}'::jsonb,
    /*
    Example:
    {
        "total_executions": 150,
        "total_tokens_used": 45000,
        "avg_execution_time_seconds": 12.5,
        "success_rate": 0.95
    }
    */
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ
);

-- Indexes for agents table
CREATE INDEX idx_agents_user_id ON agents(user_id);
CREATE INDEX idx_agents_type ON agents(type);
CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_agents_created_at ON agents(created_at DESC);
-- GIN index for JSONB queries on config
CREATE INDEX idx_agents_config ON agents USING GIN(config);

-- ============================================================
-- 4. CONVERSATIONS TABLE
-- Chat sessions with agents
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Relationships
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Conversation metadata
    title VARCHAR(500),
    summary TEXT,  -- Auto-generated summary of conversation
    
    -- Configuration for this specific conversation
    config JSONB DEFAULT '{}',
    
    -- Status tracking
    status VARCHAR(50) DEFAULT 'active' 
        CHECK (status IN ('active', 'archived', 'deleted')),
    
    -- Statistics
    message_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_message_at TIMESTAMPTZ
);

-- Indexes for conversations
CREATE INDEX idx_conversations_agent_id ON conversations(agent_id);
CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_status ON conversations(status);
CREATE INDEX idx_conversations_updated_at ON conversations(updated_at DESC);
CREATE INDEX idx_conversations_last_message_at ON conversations(last_message_at DESC);

-- ============================================================
-- 5. MESSAGES TABLE
-- Individual messages in conversations
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Relationship
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    
    -- Message content
    role VARCHAR(20) NOT NULL 
        CHECK (role IN ('user', 'assistant', 'system', 'tool', 'function')),
    content TEXT NOT NULL,
    
    -- Token usage for cost tracking
    token_count INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    
    -- Message metadata
    metadata JSONB DEFAULT '{}',
    /*
    Examples:
    - For tool calls: {"tool_name": "web_search", "tool_args": {...}}
    - For function results: {"function_name": "...", "execution_time_ms": 123}
    - For errors: {"error_type": "rate_limit", "retryable": true}
    */
    
    -- Parent message for threading/replies
    parent_message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    
    -- Ordering within conversation
    sequence_number INTEGER NOT NULL,
    
    -- Timestamp
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for messages
CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_role ON messages(role);
CREATE INDEX idx_messages_sequence ON messages(conversation_id, sequence_number);
CREATE INDEX idx_messages_created_at ON messages(created_at DESC);
-- Partial index for efficient filtering
CREATE INDEX idx_messages_content_search ON messages USING GIN(to_tsvector('english', content));

-- ============================================================
-- 6. MEMORY VECTORS TABLE
-- Vector embeddings for agent memory (pgvector)
-- ============================================================
CREATE TABLE IF NOT EXISTS memory_vectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Owner
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    
    -- Memory classification
    memory_type VARCHAR(50) NOT NULL 
        CHECK (memory_type IN ('working', 'episodic', 'procedural', 'semantic')),
    
    -- Content and embedding
    content TEXT NOT NULL,
    embedding VECTOR(1536),  -- OpenAI text-embedding-3-small dimensions
    
    -- Metadata for filtering
    metadata JSONB DEFAULT '{}',
    /*
    Examples:
    - {"source_conversation_id": "...", "topic": "technical"}
    - {"pattern_type": "success", "context": "api_integration"}
    - {"importance_score": 0.85, "access_count": 15}
    */
    
    -- Importance scoring for retrieval ranking
    importance_score FLOAT DEFAULT 0.5 CHECK (importance_score >= 0 AND importance_score <= 1),
    
    -- Access tracking
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    
    -- Expiration for time-limited memories
    expires_at TIMESTAMPTZ,
    
    -- Timestamp
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create IVFFlat index for approximate nearest neighbor search
-- Lists=100 is good for ~100K vectors; increase for larger datasets
CREATE INDEX idx_memory_vectors_embedding ON memory_vectors 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Other indexes for memory vectors
CREATE INDEX idx_memory_vectors_agent_id ON memory_vectors(agent_id);
CREATE INDEX idx_memory_vectors_type ON memory_vectors(memory_type);
CREATE INDEX idx_memory_vectors_importance ON memory_vectors(importance_score DESC);
CREATE INDEX idx_memory_vectors_expires_at ON memory_vectors(expires_at) 
    WHERE expires_at IS NOT NULL;
-- GIN index for metadata queries
CREATE INDEX idx_memory_vectors_metadata ON memory_vectors USING GIN(metadata);

-- ============================================================
-- 7. TOOL EXECUTIONS TABLE
-- Audit log for all tool executions
-- ============================================================
CREATE TABLE IF NOT EXISTS tool_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Context
    agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    executed_by UUID REFERENCES users(id),
    
    -- Tool identification
    tool_name VARCHAR(100) NOT NULL,
    tool_version VARCHAR(20) DEFAULT '1.0.0',
    
    -- Execution details
    input_params JSONB NOT NULL DEFAULT '{}',
    output_result JSONB,  -- Can be large
    
    -- Execution status and timing
    status VARCHAR(30) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'timeout', 'cancelled')),
    error_message TEXT,
    error_code VARCHAR(50),
    
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    
    -- Resource usage
    memory_used_mb FLOAT,
    cpu_time_ms INTEGER,
    
    -- Timestamp
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for tool executions
CREATE INDEX idx_tool_executions_agent_id ON tool_executions(agent_id);
CREATE INDEX idx_tool_executions_tool_name ON tool_executions(tool_name);
CREATE INDEX idx_tool_executions_status ON tool_executions(status);
CREATE INDEX idx_tool_executions_created_at ON tool_executions(created_at DESC);
CREATE INDEX idx_tool_executions_duration ON tool_executions(duration_ms) 
    WHERE status = 'completed';

-- ============================================================
-- 8. HITL APPROVALS TABLE
-- Human-in-the-loop approval workflow
-- ============================================================
CREATE TABLE IF NOT EXISTS hitl_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Context
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    execution_id UUID REFERENCES tool_executions(id) ON DELETE CASCADE,
    
    -- Request details
    request_type VARCHAR(50) NOT NULL,
        -- e.g., "tool_execution", "api_call", "data_access", "email_send"
    request_payload JSONB NOT NULL,
    
    -- Risk assessment
    risk_level VARCHAR(20) NOT NULL 
        CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    risk_score FLOAT CHECK (risk_score >= 0 AND risk_score <= 1),
    risk_factors JSONB DEFAULT '[]',
    /*
    Example risk factors:
    [
        {"factor": "external_api_call", "weight": 0.3},
        {"factor": "pii_in_request", "weight": 0.5},
        {"factor": "high_value_transaction", "weight": 0.2}
    ]
    */
    
    -- Approval workflow state
    status VARCHAR(30) DEFAULT 'pending' 
        CHECK (status IN ('pending', 'approved', 'rejected', 'escalated', 'expired', 'cancelled')),
    
    -- People involved
    requested_by UUID NOT NULL REFERENCES users(id),
    assigned_to UUID REFERENCES users(id),  -- Who should review
    reviewed_by UUID REFERENCES users(id),
    
    -- Review outcome
    decision_notes TEXT,
    decision_metadata JSONB DEFAULT '{}',
    
    -- Timing
    requested_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    
    -- Escalation tracking
    escalation_count INTEGER DEFAULT 0,
    escalated_at TIMESTAMPTZ,
    escalated_to UUID REFERENCES users(id),
    
    -- Timestamp
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for HITL approvals
CREATE INDEX idx_hitl_approvals_agent_id ON hitl_approvals(agent_id);
CREATE INDEX idx_hitl_approvals_status ON hitl_approvals(status);
CREATE INDEX idx_hitl_approvals_risk_level ON hitl_approvals(risk_level);
CREATE INDEX idx_hitl_approvals_assigned_to ON hitl_approvals(assigned_to) 
    WHERE status = 'pending';
CREATE INDEX idx_hitl_approvals_expires_at ON hitl_approvals(expires_at) 
    WHERE status = 'pending';
CREATE INDEX idx_hitl_approvals_requested_at ON hitl_approvals(requested_at DESC);

-- ============================================================
-- 9. AUDIT LOGS TABLE
 Comprehensive audit trail for compliance
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    
    -- Actor
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    actor_type VARCHAR(20) DEFAULT 'user' 
        CHECK (actor_type IN ('user', 'agent', 'system', 'api_key')),
    actor_ip INET,
    
    -- Action details
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
        -- e.g., "user", "agent", "conversation", "tool_execution"
    resource_id UUID,
    
    -- Change details (before/after snapshots)
    old_values JSONB,
    new_values JSONB,
    
    -- Additional context
    context JSONB DEFAULT '{}',
    /*
    Examples:
    - {"user_agent": "Mozilla/5.0...", "request_id": "..."}
    - {"reason": "password_change", "mfa_verified": true}
    - {"automation": true, "trigger": "scheduled_task"}
    */
    
    -- Result
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    
    -- Timestamp
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Partitioning strategy for audit logs (time-based)
-- Create partition for current month and future months will be auto-created
CREATE INDEX idx_audit_logs_actor_id ON audit_logs(actor_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);
CREATE INDEX idx_audit_logs_success ON audit_logs(success) 
    WHERE success = FALSE;

-- ============================================================
-- 10. API KEYS TABLE
-- Programmatic access credentials
-- ============================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Owner
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Key information
    name VARCHAR(255) NOT NULL,
    key_prefix VARCHAR(10) NOT NULL,  -- First 10 chars for identification
    key_hash VARCHAR(255) UNIQUE NOT NULL,  -- SHA256 hash of full key
    
    -- Permissions (scoped to specific actions)
    scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
    /*
    Example: ["agents:read", "agents:write", "conversations:read"]
    */
    
    -- Usage limits
    daily_limit INTEGER,  -- Null means unlimited
    used_today INTEGER DEFAULT 0,
    limit_reset_at DATE,
    
    -- Status and expiration
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    last_used_ip INET,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    revocation_reason VARCHAR(255)
);

-- Indexes for API keys
CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);
CREATE INDEX idx_api_keys_active ON api_keys(is_active) 
    WHERE is_active = TRUE;
CREATE INDEX idx_api_keys_expires_at ON api_keys(expires_at) 
    WHERE expires_at IS NOT NULL AND is_active = TRUE;

-- ============================================================
-- 11. RATE LIMITING TABLE
-- Distributed rate limiting support
-- ============================================================
CREATE TABLE IF NOT EXISTS rate_limits (
    id BIGSERIAL PRIMARY KEY,
    
    -- Identifier (user IP, API key, etc.)
    identifier VARCHAR(255) NOT NULL,
    identifier_type VARCHAR(50) NOT NULL 
        CHECK (identifier_type IN ('ip', 'user_id', 'api_key', 'agent_id')),
    
    -- Limit window
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    
    -- Counters
    request_count INTEGER DEFAULT 1,
    
    -- What's being limited
    limit_type VARCHAR(50) NOT NULL,
        -- e.g., "api_requests", "agent_executions", "token_usage"
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for efficient rate limit lookups
CREATE UNIQUE INDEX idx_rate_limits_unique ON rate_limits(
    identifier, identifier_type, limit_type, window_start
);
CREATE INDEX idx_rate_limits_window_end ON rate_limits(window_end) 
    WHERE request_count > 0;

-- ============================================================
-- 12. WEBHOOKS TABLE
-- Event-driven webhook configurations
-- ============================================================
CREATE TABLE IF NOT EXISTS webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Owner
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Webhook configuration
    name VARCHAR(255) NOT NULL,
    url VARCHAR(1000) NOT NULL,
    secret VARCHAR(255) NOT NULL,  -- HMAC signing secret
    
    -- Event subscriptions
    events JSONB NOT NULL DEFAULT '[]'::jsonb,
    /*
    Example: ["agent.completed", "hitl.approval_required", "error.rate_limit"]
    */
    
    -- Delivery settings
    retry_count INTEGER DEFAULT 3,
    timeout_seconds INTEGER DEFAULT 30,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Statistics
    total_deliveries INTEGER DEFAULT 0,
    successful_deliveries INTEGER DEFAULT 0,
    failed_deliveries INTEGER DEFAULT 0,
    last_delivery_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    last_failure_error TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for webhooks
CREATE INDEX idx_webhooks_user_id ON webhooks(user_id);
CREATE INDEX idx_webhooks_events ON webhooks USING GIN(events);
CREATE INDEX idx_webhooks_active ON webhooks(is_active) 
    WHERE is_active = TRUE;

-- Webhook delivery log
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id UUID NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    
    -- Delivery attempt info
    attempt_number INTEGER DEFAULT 1,
    status VARCHAR(30) NOT NULL 
        CHECK (status IN ('pending', 'success', 'failed', 'retrying')),
    
    response_status_code INTEGER,
    response_body TEXT,
    error_message TEXT,
    
    delivery_duration_ms INTEGER,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_webhook_deliveries_webhook_id ON webhook_deliveries(webhook_id);
CREATE INDEX idx_webhook_deliveries_status ON webhook_deliveries(status);
CREATE INDEX idx_webhook_deliveries_created_at ON webhook_deliveries(created_at DESC);

-- ============================================================
-- TRIGGERS AND FUNCTIONS
-- ============================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at trigger to relevant tables
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_agents_updated_at BEFORE UPDATE ON agents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversations_updated_at BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_hitl_approvals_updated_at BEFORE UPDATE ON hitl_approvals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_webhooks_updated_at BEFORE UPDATE ON webhooks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to increment conversation message count
CREATE OR REPLACE FUNCTION increment_message_count()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE conversations 
    SET message_count = message_count + 1,
        updated_at = NOW(),
        last_message_at = NOW()
    WHERE id = NEW.conversation_id;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER trigger_increment_message_count AFTER INSERT ON messages
    FOR EACH ROW EXECUTE FUNCTION increment_message_count();

-- Function to update agent last_active_at
CREATE OR REPLACE FUNCTION update_agent_activity()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE agents 
    SET last_active_at = NOW(),
        updated_at = NOW()
    WHERE id = NEW.agent_id;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_agent_last_active AFTER INSERT ON messages
    FOR EACH ROW EXECUTE FUNCTION update_agent_activity();

-- Function to clean up expired data (run via scheduled job)
CREATE OR REPLACE FUNCTION cleanup_expired_data()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER := 0;
BEGIN
    -- Delete expired refresh tokens
    DELETE FROM refresh_tokens 
    WHERE (expires_at < NOW() OR revoked_at IS NOT NULL)
      AND (revoked_at < NOW() - INTERVAL '30 days' OR revoked_at IS NULL AND expires_at < NOW());
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    -- Delete expired memory vectors
    DELETE FROM memory_vectors WHERE expires_at < NOW();
    
    -- Expire pending HITL approvals past their deadline
    UPDATE hitl_approvals 
    SET status = 'expired', updated_at = NOW()
    WHERE status = 'pending' AND expires_at < NOW();
    
    -- Reset daily rate limit counters
    DELETE FROM rate_limits WHERE window_end < NOW();
    
    RETURN deleted_count;
END;
$$ language 'plpgsql';

COMMIT;

-- ============================================================
-- MIGRATION COMPLETE
-- Tables created: 12 core tables + 1 delivery log table
-- Indexes created: 35+ indexes for optimal query performance
-- Triggers created: 5 triggers for automatic field updates
-- Functions created: 4 utility functions
-- ============================================================
