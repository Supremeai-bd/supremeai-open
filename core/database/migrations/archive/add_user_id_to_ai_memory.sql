-- File: backend/database/migrations/legacy/add_user_id_to_ai_memory.sql
-- Relocated from root migrations/ to central backend/database/migrations/legacy/
-- Run against PostgreSQL to add user scoping to ai_memory

ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_ai_memory_user_id ON ai_memory (user_id);
CREATE INDEX IF NOT EXISTS idx_ai_memory_user_task ON ai_memory (user_id, task_type);
