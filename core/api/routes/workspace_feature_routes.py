"""Tier-S Routes Registry

Central registration point for all 12 new Tier-S feature routers.
Import this module and call `register_tier_s_routes(app)` to wire
every Tier-S router into a FastAPI application in one step.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from api.routes.artifacts import router as artifacts_router
from api.routes.branch_conversations import router as branch_conversations_router
from api.routes.chat_export import router as chat_export_router
from api.routes.chat_search import router as chat_search_router
from api.routes.chat_upload import router as chat_upload_router
from api.routes.deep_research import router as deep_research_router
from api.routes.global_memory import router as global_memory_router
from api.routes.prompt_templates import router as prompt_templates_router
from api.routes.reasoning import router as reasoning_router
from api.routes.scheduled_tasks import router as scheduled_tasks_router
from api.routes.share import router as share_router
from api.routes.slash_commands import router as slash_commands_router

if TYPE_CHECKING:
    from fastapi import APIRouter

# ---------------------------------------------------------------------------
# Master list of all Tier-S routers with their mount prefixes and tags.
# All routers define their own canonical prefix internally, so outer prefix is empty ("")
# to avoid double prefix concatenation (e.g. /api/share/api/share).
# ---------------------------------------------------------------------------
TIER_S_ROUTERS: list[tuple[APIRouter, str, list[str]]] = [
    (share_router, "", ["share"]),
    (reasoning_router, "", ["reasoning"]),
    (artifacts_router, "", ["artifacts"]),
    (chat_upload_router, "", ["chat-upload"]),
    (slash_commands_router, "", ["slash-commands"]),
    (chat_search_router, "", ["chat-search"]),
    (chat_export_router, "", ["chat-export"]),
    (global_memory_router, "", ["global-memory"]),
    (prompt_templates_router, "", ["prompt-templates"]),
    (branch_conversations_router, "", ["branch-conversations"]),
    (scheduled_tasks_router, "", ["scheduled-tasks"]),
    (deep_research_router, "", ["deep-research"]),
]

# Convenience flat list of just the router objects.
TIER_S_ROUTER_OBJECTS: list[APIRouter] = [r for r, _, _ in TIER_S_ROUTERS]


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------
def register_tier_s_routes(app: FastAPI) -> None:
    """Include all 12 Tier-S routers into *app*.

    Each router is mounted at its designated prefix and tagged for the
    OpenAPI schema so that Tier-S endpoints appear grouped under their
    own tag in ``/docs``.

    Usage::

        from api.routes.tier_s_routes import register_tier_s_routes

        register_tier_s_routes(app)
    """
    for router, prefix, tags in TIER_S_ROUTERS:
        app.include_router(router, prefix=prefix, tags=tags)


# ---------------------------------------------------------------------------
# Fallback raw-SQL for environments that do not run Alembic migrations.
# ---------------------------------------------------------------------------
TIER_S_TABLES_SQL: str = """\
-- ==============================================================
-- Tier-S table creation DDL (PostgreSQL)
-- Run this manually only if Alembic migrations are not available.
-- ==============================================================

-- 1. shared_conversations
CREATE TABLE IF NOT EXISTS shared_conversations (
    share_id        TEXT        PRIMARY KEY,
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id         TEXT        NOT NULL,
    is_public       BOOLEAN     NOT NULL DEFAULT FALSE,
    view_count      INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_shared_conversations_conversation_id
    ON shared_conversations (conversation_id);
CREATE INDEX IF NOT EXISTS ix_shared_conversations_user_id
    ON shared_conversations (user_id);

-- 2. artifacts
CREATE TABLE IF NOT EXISTS artifacts (
    id              UUID        PRIMARY KEY,
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id         TEXT        NOT NULL,
    title           TEXT        NOT NULL,
    artifact_type   TEXT        NOT NULL,
    content         TEXT        NOT NULL,
    version         INTEGER     NOT NULL DEFAULT 1,
    is_pinned       BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_artifacts_conversation_id ON artifacts (conversation_id);
CREATE INDEX IF NOT EXISTS ix_artifacts_user_id ON artifacts (user_id);
CREATE INDEX IF NOT EXISTS ix_artifacts_artifact_type ON artifacts (artifact_type);

-- 3. chat_attachments
CREATE TABLE IF NOT EXISTS chat_attachments (
    id              UUID        PRIMARY KEY,
    user_id         TEXT        NOT NULL,
    conversation_id UUID,
    message_id      UUID,
    file_name       TEXT        NOT NULL,
    file_path       TEXT        NOT NULL,
    file_size       INTEGER     NOT NULL,
    mime_type       TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chat_attachments_user_id ON chat_attachments (user_id);
CREATE INDEX IF NOT EXISTS ix_chat_attachments_conversation_id ON chat_attachments (conversation_id);
CREATE INDEX IF NOT EXISTS ix_chat_attachments_message_id ON chat_attachments (message_id);

-- 4. prompt_templates
CREATE TABLE IF NOT EXISTS prompt_templates (
    id          UUID        PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    name        TEXT        NOT NULL,
    description TEXT,
    category    TEXT,
    prompt      TEXT        NOT NULL,
    variables   JSONB,
    is_builtin  BOOLEAN     NOT NULL DEFAULT FALSE,
    usage_count INTEGER     NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_prompt_templates_user_id ON prompt_templates (user_id);
CREATE INDEX IF NOT EXISTS ix_prompt_templates_category ON prompt_templates (category);

-- 5. scheduled_tasks
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id                UUID        PRIMARY KEY,
    user_id           TEXT        NOT NULL,
    title             TEXT        NOT NULL,
    prompt            TEXT        NOT NULL,
    schedule_type     TEXT        NOT NULL,
    scheduled_time    TIMESTAMPTZ,
    cron_expression   TEXT,
    conversation_id   UUID        REFERENCES conversations(id) ON DELETE SET NULL,
    is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
    last_run_at       TIMESTAMPTZ,
    last_run_status   TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_user_id ON scheduled_tasks (user_id);
CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_is_active ON scheduled_tasks (is_active);

-- 6. scheduled_task_executions
CREATE TABLE IF NOT EXISTS scheduled_task_executions (
    id          UUID        PRIMARY KEY,
    task_id     UUID        NOT NULL REFERENCES scheduled_tasks(id) ON DELETE CASCADE,
    status      TEXT        NOT NULL,
    result      TEXT,
    error       TEXT,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_scheduled_task_executions_task_id
    ON scheduled_task_executions (task_id);
CREATE INDEX IF NOT EXISTS ix_scheduled_task_executions_status
    ON scheduled_task_executions (status);

-- 7. research_sessions
CREATE TABLE IF NOT EXISTS research_sessions (
    id               UUID        PRIMARY KEY,
    user_id          TEXT        NOT NULL,
    query            TEXT        NOT NULL,
    report           JSONB,
    steps_completed  INTEGER     NOT NULL DEFAULT 0,
    total_sources    INTEGER     NOT NULL DEFAULT 0,
    status           TEXT        NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_research_sessions_user_id ON research_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_research_sessions_status ON research_sessions (status);

-- 8. conversations: add parent_conversation_id
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS parent_conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_conversations_parent_conversation_id
    ON conversations (parent_conversation_id);

-- 9. messages: add parent_message_id
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS parent_message_id UUID REFERENCES messages(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_messages_parent_message_id
    ON messages (parent_message_id);
"""

__all__ = [
    "TIER_S_ROUTERS",
    "TIER_S_ROUTER_OBJECTS",
    "TIER_S_TABLES_SQL",
    "register_tier_s_routes",
    "register_workspace_feature_routes",
]

register_workspace_feature_routes = register_tier_s_routes
WORKSPACE_FEATURE_ROUTERS = TIER_S_ROUTERS
WORKSPACE_FEATURE_ROUTER_OBJECTS = TIER_S_ROUTER_OBJECTS
