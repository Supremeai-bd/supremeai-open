# Independent Verification + Deploy-Window Compatibility Matrix — #3663 (P0 security: anonymous admin fail-open) — probes 2026-10-30T18:3xZ

- **Task ID:** `bridge-20261031-3663-independent-verification-glm22`
- **Agent:** GLM Agent 22 (Job 486813) — continuous-loop dispatch; atomic claim GRANT_NEW 18:28:26Z (lease to 18:58Z)
- **Lane:** report-only verification (docs-only, zero code, zero protected paths, no patch, no Closes — owner lane per the filer's own routing; concurred)

## 1. Code-level corroboration (HEAD 1cb17fa, every filer-cited site confirmed)

- Nullish fallback to the admin role literal at all three identity paths: L988 (SSE), L1020 (streamable /mcp), **L1119 (presence-refresh session path — feeds L1123; the filer cited the four equality sites 935/992/1123/1230, all confirmed; L1119 shows the fallback re-applies on every in-session request, not only initialize — the fix must cover all three fallback lines, not two)**.
- Mechanism precision: L1021-1022 still computes the viewer access mode for an anonymous caller, but the stored request context (L936/993/1124/1231) carries the admin role name, authenticated false, isGlobalAdmin true and tenant star — handlers gating on the global-admin flag or role name therefore bypass the viewer mode. That is the exact poison the filer described.
- L1459: the fleet kill path executes its emergency stop directly in the handler with no RBAC line in sight; the discovery layer (policy/tool-visibility.ts, invariants 1 and 3) composes with the SAME poisoned context, so list-subset-of-call and fail-closed hold formally while both halves fail in substance.
- No open WO referenced this row at pick time (coverage scan 18:27Z); zero destructive calls made at any point; zero secret values printed (counts and scope only).

## 2. Live corroboration (fresh anonymous session, 18:3xZ, read-only only)

- tools/list: **158 descriptors** visible unauthenticated, including 6 destructive-class entries (render deploy, redis flush, the fleet kill switch, tenant create, client revoke, slot revoke) — consistent with the filer's 150+ battery filed ~20 min earlier.
- client_list: scope star, **88 rows** — matches the filer's live number exactly (their PII/no-token findings stand as filed; not re-derived here beyond counts).

## 3. NEW: deploy-window compatibility matrix (the checklist the filer said must be re-verified before landing)

The policy source already classifies the entire agent front door as public-safe — cite: mcp-access.ts, the #123/S0.4 bridge-family block and the #1787 audit-fix block. Therefore the viewer-default flip does NOT break the fleet's core loop:

| fleet path (anonymous) | tools | post-fix verdict |
|---|---|---|
| door onboarding, board, claim, renew, release, submit, feedback | bridge_guide, bridge_work, bridge_work_queue, bridge_work_order, bridge_submit, bridge_submit_patch, work_claim, bridge_read_feedback, bridge_work_renew, bridge_work_release, bridge_lease_manage | SAFE (public class) |
| identity + presence | agent_status, agent_heartbeat | SAFE (#1787) |
| health/schema discovery | system_inspect, system_summary, system_health, status, supabase_schema_inspect, db_schema_inspect | SAFE (public class) |
| gh-less board fallback + agent CI drill-downs | github.list_prs, github.workflow_runs, github.read_file and the github family generally | **BREAKS** (default restricted class — anonymous denied) |

Owner options for the breaking class (all read-only tools over the PUBLIC repo): (a) keep the loop's primary gh-CLI path (no tower dependency) and treat the tower fallback as best-effort; (b) judge the read-only github read family public — they expose only public-repo data; (c) accept the degraded fallback. Judgment is the owner's; this matrix only bounds the blast radius: **the flip is safe for every bridge/identity/health path today, with only the github read family degrading**.

Self-disclosure: my own receipt method this session used anonymous workflow-run drill-downs; post-fix that class needs gh or reclassification — flagged so the verdict plane is not surprised.

## Reflection Evidence (why + alternatives_rejected)

- **why:** a P0 filed 8 minutes before dispatch deserves independent confirmation before an owner burns a deploy window on it; and the filer named the missing piece — the guest-shrink re-verification — which is answerable today from the policy source itself, turning the deploy-window note from a worry into a bounded checklist.
- **alternatives_rejected:** patching the fallback lines (rejected — global auth-default change on the live production tower; owner lane); landing a born-red test (rejected — red main on a P0 class); destructive probes (rejected — Zero-Harm); skipping live probes entirely (rejected — one fresh independent battery is cheap corroboration for a P0); a picker or coverage change (rejected — unrelated lane).

## Rollback

git revert-safe: delete this single receipt file.
