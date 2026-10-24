-- Migration: 17_enable_rls.sql
-- Description: Enables RLS on all tables and applies strict table-by-table policies.

DO $$
DECLARE
    t_name text;
    -- Define our categories
    system_tables text[] := ARRAY[
        'system_config', 'system_dependencies', 'system_incidents', 'system_alerts',
        'provider_configs', 'api_endpoints', 'feature_flags', 'rules', 'guardrails',
        'outbox_events', 'ci_reports', 'agent_configs', 'agent_sessions',
        'provider_benchmarks', 'verification_queue', 'sso_configs', 'sso_sessions'
    ];
    user_owned_tables text[] := ARRAY[
        'user_preferences', 'user_wallets', 'dynamic_skills', 'skill_proposals',
        'markdown_exports', 'code_proposals', 'credit_wallets', 'domain_profiles',
        'dynamic_capabilities', 'skills', 'skill_fitness'
    ];
    tenant_tables text[] := ARRAY[
        'tenant_limits', 'tenant_usage', 'github_repos', 'knowledge_base',
        'learned_facts', 'transaction_ledger', 'task_history', 'task_checkpoints',
        'file_memories', 'credit_ledger', 'usage_metrics'
    ];
    audit_tables text[] := ARRAY[
        'audit_logs', 'evolution_logs', 'execution_chains', 'ai_mistakes', 'ai_model_behavior'
    ];
BEGIN
    -- 1. Enable RLS on ALL tables in the public schema
    FOR t_name IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE IF EXISTS public.%I ENABLE ROW LEVEL SECURITY;', t_name);
    END LOOP;

    -- 2. User-Owned Tables (Strict Ownership via user_id)
    FOREACH t_name IN ARRAY user_owned_tables LOOP
        IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = t_name) THEN
            -- We assume the column is 'user_id' except for dynamic_skills where it's 'author_id'
            DECLARE
                uid_col text := 'user_id';
            BEGIN
                IF t_name = 'dynamic_skills' THEN uid_col := 'author_id'; END IF;
                
                -- Verify the column actually exists before creating policies
                IF EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = t_name AND column_name = uid_col) THEN
                    EXECUTE format('DROP POLICY IF EXISTS %I_select ON public.%I;', t_name, t_name);
                    EXECUTE format('CREATE POLICY %I_select ON public.%I FOR SELECT TO authenticated USING (%I = auth.uid()::text);', t_name, t_name, uid_col);

                    EXECUTE format('DROP POLICY IF EXISTS %I_insert ON public.%I;', t_name, t_name);
                    EXECUTE format('CREATE POLICY %I_insert ON public.%I FOR INSERT TO authenticated WITH CHECK (%I = auth.uid()::text);', t_name, t_name, uid_col);

                    EXECUTE format('DROP POLICY IF EXISTS %I_update ON public.%I;', t_name, t_name);
                    EXECUTE format('CREATE POLICY %I_update ON public.%I FOR UPDATE TO authenticated USING (%I = auth.uid()::text) WITH CHECK (%I = auth.uid()::text);', t_name, t_name, uid_col, uid_col);

                    EXECUTE format('DROP POLICY IF EXISTS %I_delete ON public.%I;', t_name, t_name);
                    EXECUTE format('CREATE POLICY %I_delete ON public.%I FOR DELETE TO authenticated USING (%I = auth.uid()::text);', t_name, t_name, uid_col);
                END IF;
            END;
        END IF;
    END LOOP;

    -- 3. Tenant-Isolated Data
    FOREACH t_name IN ARRAY tenant_tables LOOP
        IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = t_name) THEN
            IF EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = t_name AND column_name = 'tenant_id') THEN
                EXECUTE format('DROP POLICY IF EXISTS %I_tenant_select ON public.%I;', t_name, t_name);
                EXECUTE format('CREATE POLICY %I_tenant_select ON public.%I FOR SELECT TO authenticated USING (tenant_id = current_setting(''app.current_tenant_id'', true));', t_name, t_name);

                EXECUTE format('DROP POLICY IF EXISTS %I_tenant_insert ON public.%I;', t_name, t_name);
                EXECUTE format('CREATE POLICY %I_tenant_insert ON public.%I FOR INSERT TO authenticated WITH CHECK (tenant_id = current_setting(''app.current_tenant_id'', true));', t_name, t_name);

                EXECUTE format('DROP POLICY IF EXISTS %I_tenant_update ON public.%I;', t_name, t_name);
                EXECUTE format('CREATE POLICY %I_tenant_update ON public.%I FOR UPDATE TO authenticated USING (tenant_id = current_setting(''app.current_tenant_id'', true)) WITH CHECK (tenant_id = current_setting(''app.current_tenant_id'', true));', t_name, t_name);

                EXECUTE format('DROP POLICY IF EXISTS %I_tenant_delete ON public.%I;', t_name, t_name);
                EXECUTE format('CREATE POLICY %I_tenant_delete ON public.%I FOR DELETE TO authenticated USING (tenant_id = current_setting(''app.current_tenant_id'', true));', t_name, t_name);
            END IF;
        END IF;
    END LOOP;

    -- 4. Append-Only / Audit Data (Read-only for owners, backend handles writes)
    FOREACH t_name IN ARRAY audit_tables LOOP
        IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = t_name) THEN
            IF EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = t_name AND column_name = 'user_id') THEN
                EXECUTE format('DROP POLICY IF EXISTS %I_select ON public.%I;', t_name, t_name);
                EXECUTE format('CREATE POLICY %I_select ON public.%I FOR SELECT TO authenticated USING (user_id = auth.uid()::text);', t_name, t_name);
            END IF;
        END IF;
    END LOOP;

    -- 5. System Tables automatically get "Deny by Default" for anon/authenticated 
    -- because RLS is enabled and no explicit policies are created for them.
END $$;
