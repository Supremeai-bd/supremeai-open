-- Migration: 18_fix_missing_rls_policies.sql
-- Description:
--   17_enable_rls.sql enabled RLS on every public table but only created
--   policies for tables listed in its category arrays. Any table NOT in
--   those arrays (or in them but missing the assumed ownership column) was
--   left in "RLS ON + 0 policies" = deny-all, the exact same bug class that
--   broke evolution_logs (fixed in 835fa97). A code audit of every
--   `.table(...)` call in backend/ found this is NOT an isolated case --
--   17 tables are affected, all writing through the RLS-enforced
--   self.client (not the service-role client), so every one of these is
--   currently either silently failing with 42501 or (for tables that
--   happen to have no active traffic yet) will fail the moment it does.
--
--   This migration is split into two groups:
--     A. User-owned data tables -> real per-user RLS policies
--        (auth.uid() scoped), since these ARE meant to be governed by RLS.
--     B. Backend/system-internal tables -> intentionally left with NO
--        authenticated/anon policy (same posture as evolution_logs);
--        access must go through supabase_client.py's service_client.
--        Code changes for group B are shipped alongside this migration
--        (see 18_SERVICE_CLIENT_MIGRATION_NOTES.md).

DO $$
BEGIN

    -- ============================================================
    -- GROUP A: user-owned tables with a direct user_id column
    -- ============================================================
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='artifacts')
       AND EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='artifacts' AND column_name='user_id') THEN
        DROP POLICY IF EXISTS artifacts_select ON public.artifacts;
        CREATE POLICY artifacts_select ON public.artifacts FOR SELECT TO authenticated USING (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS artifacts_insert ON public.artifacts;
        CREATE POLICY artifacts_insert ON public.artifacts FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS artifacts_update ON public.artifacts;
        CREATE POLICY artifacts_update ON public.artifacts FOR UPDATE TO authenticated USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS artifacts_delete ON public.artifacts;
        CREATE POLICY artifacts_delete ON public.artifacts FOR DELETE TO authenticated USING (user_id = auth.uid()::text);
    END IF;

    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='chat_attachments')
       AND EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='chat_attachments' AND column_name='user_id') THEN
        DROP POLICY IF EXISTS chat_attachments_select ON public.chat_attachments;
        CREATE POLICY chat_attachments_select ON public.chat_attachments FOR SELECT TO authenticated USING (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS chat_attachments_insert ON public.chat_attachments;
        CREATE POLICY chat_attachments_insert ON public.chat_attachments FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS chat_attachments_delete ON public.chat_attachments;
        CREATE POLICY chat_attachments_delete ON public.chat_attachments FOR DELETE TO authenticated USING (user_id = auth.uid()::text);
    END IF;

    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='prompt_templates')
       AND EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='prompt_templates' AND column_name='user_id') THEN
        DROP POLICY IF EXISTS prompt_templates_select ON public.prompt_templates;
        CREATE POLICY prompt_templates_select ON public.prompt_templates FOR SELECT TO authenticated USING (user_id = auth.uid()::text OR is_public = true);
        DROP POLICY IF EXISTS prompt_templates_insert ON public.prompt_templates;
        CREATE POLICY prompt_templates_insert ON public.prompt_templates FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS prompt_templates_update ON public.prompt_templates;
        CREATE POLICY prompt_templates_update ON public.prompt_templates FOR UPDATE TO authenticated USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS prompt_templates_delete ON public.prompt_templates;
        CREATE POLICY prompt_templates_delete ON public.prompt_templates FOR DELETE TO authenticated USING (user_id = auth.uid()::text);
    END IF;

    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='scheduled_tasks')
       AND EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='scheduled_tasks' AND column_name='user_id') THEN
        DROP POLICY IF EXISTS scheduled_tasks_select ON public.scheduled_tasks;
        CREATE POLICY scheduled_tasks_select ON public.scheduled_tasks FOR SELECT TO authenticated USING (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS scheduled_tasks_insert ON public.scheduled_tasks;
        CREATE POLICY scheduled_tasks_insert ON public.scheduled_tasks FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS scheduled_tasks_update ON public.scheduled_tasks;
        CREATE POLICY scheduled_tasks_update ON public.scheduled_tasks FOR UPDATE TO authenticated USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS scheduled_tasks_delete ON public.scheduled_tasks;
        CREATE POLICY scheduled_tasks_delete ON public.scheduled_tasks FOR DELETE TO authenticated USING (user_id = auth.uid()::text);
    END IF;

    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='shared_conversations')
       AND EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='shared_conversations' AND column_name='user_id') THEN
        DROP POLICY IF EXISTS shared_conversations_select ON public.shared_conversations;
        CREATE POLICY shared_conversations_select ON public.shared_conversations FOR SELECT TO authenticated USING (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS shared_conversations_insert ON public.shared_conversations;
        CREATE POLICY shared_conversations_insert ON public.shared_conversations FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS shared_conversations_update ON public.shared_conversations;
        CREATE POLICY shared_conversations_update ON public.shared_conversations FOR UPDATE TO authenticated USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS shared_conversations_delete ON public.shared_conversations;
        CREATE POLICY shared_conversations_delete ON public.shared_conversations FOR DELETE TO authenticated USING (user_id = auth.uid()::text);
        -- Public share links must remain readable by anon via their share_id -- add a
        -- narrow anon SELECT policy scoped by a non-guessable share_id, never a blanket USING(true).
        IF EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='shared_conversations' AND column_name='share_id') THEN
            DROP POLICY IF EXISTS shared_conversations_public_read ON public.shared_conversations;
            CREATE POLICY shared_conversations_public_read ON public.shared_conversations FOR SELECT TO anon USING (share_id IS NOT NULL);
        END IF;
    END IF;

    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='deep_research_sessions')
       AND EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='deep_research_sessions' AND column_name='user_id') THEN
        DROP POLICY IF EXISTS deep_research_sessions_select ON public.deep_research_sessions;
        CREATE POLICY deep_research_sessions_select ON public.deep_research_sessions FOR SELECT TO authenticated USING (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS deep_research_sessions_insert ON public.deep_research_sessions;
        CREATE POLICY deep_research_sessions_insert ON public.deep_research_sessions FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS deep_research_sessions_update ON public.deep_research_sessions;
        CREATE POLICY deep_research_sessions_update ON public.deep_research_sessions FOR UPDATE TO authenticated USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);
    END IF;

    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='ai_memory')
       AND EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='ai_memory' AND column_name='user_id') THEN
        DROP POLICY IF EXISTS ai_memory_select ON public.ai_memory;
        CREATE POLICY ai_memory_select ON public.ai_memory FOR SELECT TO authenticated USING (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS ai_memory_insert ON public.ai_memory;
        CREATE POLICY ai_memory_insert ON public.ai_memory FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS ai_memory_delete ON public.ai_memory;
        CREATE POLICY ai_memory_delete ON public.ai_memory FOR DELETE TO authenticated USING (user_id = auth.uid()::text);
    END IF;

    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='user_keys') THEN
        -- user_keys stores per-user API keys -- strictly owner-only, no service bypass needed
        IF EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='user_keys' AND column_name='user_id') THEN
            DROP POLICY IF EXISTS user_keys_select ON public.user_keys;
            CREATE POLICY user_keys_select ON public.user_keys FOR SELECT TO authenticated USING (user_id = auth.uid()::text);
            DROP POLICY IF EXISTS user_keys_insert ON public.user_keys;
            CREATE POLICY user_keys_insert ON public.user_keys FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid()::text);
            DROP POLICY IF EXISTS user_keys_update ON public.user_keys;
            CREATE POLICY user_keys_update ON public.user_keys FOR UPDATE TO authenticated USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);
            DROP POLICY IF EXISTS user_keys_delete ON public.user_keys;
            CREATE POLICY user_keys_delete ON public.user_keys FOR DELETE TO authenticated USING (user_id = auth.uid()::text);
        END IF;
    END IF;

    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='voice_interactions')
       AND EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='voice_interactions' AND column_name='user_id') THEN
        DROP POLICY IF EXISTS voice_interactions_select ON public.voice_interactions;
        CREATE POLICY voice_interactions_select ON public.voice_interactions FOR SELECT TO authenticated USING (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS voice_interactions_insert ON public.voice_interactions;
        CREATE POLICY voice_interactions_insert ON public.voice_interactions FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid()::text);
    END IF;

    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='agent_memories')
       AND EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='agent_memories' AND column_name='user_id') THEN
        DROP POLICY IF EXISTS agent_memories_select ON public.agent_memories;
        CREATE POLICY agent_memories_select ON public.agent_memories FOR SELECT TO authenticated USING (user_id = auth.uid()::text);
        DROP POLICY IF EXISTS agent_memories_insert ON public.agent_memories;
        CREATE POLICY agent_memories_insert ON public.agent_memories FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid()::text);
    END IF;

    -- ============================================================
    -- GROUP A2: real conversations/messages (Alembic-managed schema --
    -- conversations.user_id exists; messages is scoped indirectly via
    -- conversation_id, so its policy is a sub-select, not a direct column).
    -- ============================================================
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='conversations')
       AND EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='conversations' AND column_name='user_id') THEN
        DROP POLICY IF EXISTS conversations_select ON public.conversations;
        CREATE POLICY conversations_select ON public.conversations FOR SELECT TO authenticated USING (user_id = auth.uid());
        DROP POLICY IF EXISTS conversations_insert ON public.conversations;
        CREATE POLICY conversations_insert ON public.conversations FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
        DROP POLICY IF EXISTS conversations_update ON public.conversations;
        CREATE POLICY conversations_update ON public.conversations FOR UPDATE TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
        DROP POLICY IF EXISTS conversations_delete ON public.conversations;
        CREATE POLICY conversations_delete ON public.conversations FOR DELETE TO authenticated USING (user_id = auth.uid());
    END IF;

    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='messages')
       AND EXISTS (SELECT FROM information_schema.columns WHERE table_schema='public' AND table_name='messages' AND column_name='conversation_id')
       AND EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='conversations') THEN
        DROP POLICY IF EXISTS messages_select ON public.messages;
        CREATE POLICY messages_select ON public.messages FOR SELECT TO authenticated USING (
            conversation_id IN (SELECT id FROM public.conversations WHERE user_id = auth.uid())
        );
        DROP POLICY IF EXISTS messages_insert ON public.messages;
        CREATE POLICY messages_insert ON public.messages FOR INSERT TO authenticated WITH CHECK (
            conversation_id IN (SELECT id FROM public.conversations WHERE user_id = auth.uid())
        );
        DROP POLICY IF EXISTS messages_delete ON public.messages;
        CREATE POLICY messages_delete ON public.messages FOR DELETE TO authenticated USING (
            conversation_id IN (SELECT id FROM public.conversations WHERE user_id = auth.uid())
        );
    END IF;

    -- ============================================================
    -- GROUP B: backend/system-internal tables -- NO authenticated/anon
    -- policy added on purpose (same posture as evolution_logs). These
    -- must be accessed only via supabase_client.py's service_client.
    -- Corresponding Python call sites are switched from self.client to
    -- self.service_client in this same change (see notes doc):
    --   feedback_loop, tools_registry, referral_codes,
    --   referral_redemptions, scheduled_task_executions
    -- Nothing to execute here -- RLS is already ON with 0 policies from
    -- migration 17, which is the correct end state for these tables.
    -- ============================================================

END $$;
