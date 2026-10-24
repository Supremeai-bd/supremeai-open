-- MANUAL ONLY: review and apply through the project's migration workflow.
-- This draft is intentionally not executed by automation because database access is unavailable.

create table if not exists public.control_plane_executions (
  id uuid primary key default gen_random_uuid(), tenant_id uuid not null, actor_id uuid not null,
  workspace_id uuid not null, correlation_id text not null, idempotency_key text not null,
  capability text not null, risk_level text not null, status text not null,
  result jsonb, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique (tenant_id, idempotency_key)
);

create table if not exists public.control_plane_events (
  id uuid primary key default gen_random_uuid(), execution_id uuid not null references public.control_plane_executions(id) on delete cascade,
  tenant_id uuid not null, event_type text not null, sequence bigint not null,
  fingerprint text not null, payload jsonb not null, occurred_at timestamptz not null default now(),
  unique (execution_id, fingerprint), unique (execution_id, sequence)
);

create table if not exists public.control_plane_approvals (
  id uuid primary key default gen_random_uuid(), execution_id uuid not null references public.control_plane_executions(id) on delete cascade,
  tenant_id uuid not null, action text not null, status text not null default 'pending',
  reason text, expires_at timestamptz, consumed_at timestamptz, created_at timestamptz not null default now()
);

create index if not exists control_plane_events_tenant_time on public.control_plane_events(tenant_id, occurred_at desc);
create index if not exists control_plane_executions_tenant_time on public.control_plane_executions(tenant_id, created_at desc);

alter table public.control_plane_executions enable row level security;
alter table public.control_plane_events enable row level security;
alter table public.control_plane_approvals enable row level security;

-- Replace these example policies with the project's canonical tenant-membership function.
-- Never authorize from editable user metadata.
-- create policy control_plane_execution_read on public.control_plane_executions for select to authenticated using (tenant_id = public.current_tenant_id());
-- create policy control_plane_event_read on public.control_plane_events for select to authenticated using (tenant_id = public.current_tenant_id());
-- Do not grant client INSERT/UPDATE to status, result, approval, or audit tables; use restricted server-side RPCs.
