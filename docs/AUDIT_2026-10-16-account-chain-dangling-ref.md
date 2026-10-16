# AUDIT — 2026-10-16 `test:account-chain` targets a file that never landed on main (test:unit chain aborts, 13 suites orphaned)

> **id:** audit-2026-10-16-account-chain-dangling-ref
> **title:** package.json `test:account-chain` → `test_account_chain_callers.ts` is a dangling reference on main since PR #212 — the documented `test:unit` battery aborts mid-chain and 13 suites silently never run
> **document_role:** audit
> **status:** active
> **canonical:** true
> **owner:** agent-orchestration (Auditor role, AGENT_RULES.md §3)
> **last_verified:** 2026-10-16
> **related_docs:** [INGRESS_SECURITY_POLICY.md](INGRESS_SECURITY_POLICY.md) · [AUDIT_2026-10-16-stale-base-guard-frozen-base-sha.md](AUDIT_2026-10-16-stale-base-guard-frozen-base-sha.md) · [AUDIT_2026-10-16-agent-loop-dispatch-input-inline.md](AUDIT_2026-10-16-agent-loop-dispatch-input-inline.md)
> **source_issue:** filed via bridge (this document's own Work Order)

> **Auditor:** external autonomous contributor agent (zero-credential Pathway 1, AGENTS.md §2.1).
> **Method:** first-ever local execution of the public tower mirror's TypeScript battery at
> main `8242d4e` (`bun install --frozen-lockfile` clean, then `bun run test:unit`). Severity
> **P3** (documented verification surface broken; no production path affected),
> **agent-orchestration** group.

## Finding — P3 · agent-orchestration · dangling script reference orphans 13 suites

`infrastructure/mcp-control-plane/package.json` (main) declares:

```
"test:account-chain": "tsx scripts/test-runner.ts test_account_chain_callers.ts"
```

…positioned inside the chained `test:unit` battery. `test_account_chain_callers.ts` is **not
tracked on main and never was** (`git log --all --diff-filter=A` shows the only add commit is
`815dca6` on the in-flight bridge lane `bridge/bridge-20261015-issue-110-chain-walk`, not an
ancestor of main). The wiring was landed by **PR #212** (`8a16924`, "offline-safe suites") —
the runner (`scripts/test-runner.ts`, +98 lines) and the package.json script entries landed,
the test file did not. Same split-landing family as the external audit's F5 observation
(auto-bridge scope may under-bridge `tests/`-adjacent assets).

**Reproduced** on main `8242d4e`: `bun run test:unit` → suites 1–16 pass
(health-history, heartbeat, redis-rotation, mcp-presence, policy, registry, events, summary,
guardian, client-registry, auto-register, gemini-adapter, tool-visibility,
slot-verification, bridge-onboarding, bridge-intake, command-router, quota-routing) →
**aborts with `ERR_MODULE_NOT_FOUND: test_account_chain_callers.ts`** → the trailing **13
suites silently never run**: task-engine, federation, memory-fallback, memory-adapter,
actions, infisical, remediation, github-adapter, memory-sidecar, wiring-guard,
federated-ci-watcher.

**All 13 orphaned suites verified individually green** when run directly (rc=0, or documented
env-skip per #116: github-adapter / memory-sidecar skip honestly on missing env) — so the
hidden state behind the break is healthy; the break itself is the defect.

**Why the #116 wiring guard didn't catch it:** the guard ("all 35 test file(s) referenced by
npm scripts") checks only the forward direction — every existing test file must be
script-referenced — never the reverse (every script-referenced target must exist). The
systemic fix is delivered as its own bridge WO
(`bridge-20261016-wiring-guard-reverse-check`, issue #278): `guard()` now fails closed
listing nonexistent targets, and on current main it reports exactly
`test_account_chain_callers.ts`.

## Resolution — two honest paths (decision for the authorized lane / admin)

1. **Preferred:** land the in-flight `bridge-20261015-issue-110-chain-walk` lane (issue #110;
   §8 — owned by that collaborator lane, not re-managed here). Cross-checked: all six modules
   the file dynamically imports (`src/lib/redis_chain`, `src/registry/agent_heartbeat`,
   `src/registry/mcp_presence`, `src/adapters/redis/index`,
   `src/policy/client-registry.store`, `src/registry/orchestrator_dispatch`) exist on main —
   the lane heals the chain without further changes.
2. **If the lane is delayed or rejected**, apply this minimal carried patch so the documented
   battery runs end-to-end again (the issue-110 lane re-adds the wiring when it lands):

```diff
--- a/infrastructure/mcp-control-plane/package.json
+++ b/infrastructure/mcp-control-plane/package.json
@@ -1,8 +1,7 @@
-    "test:unit": "… && npm run test:quota-routing && npm run test:account-chain && npm run test:task-engine …",
+    "test:unit": "… && npm run test:quota-routing && npm run test:task-engine …",
```

(i.e. drop `npm run test:account-chain &&` from `test:unit` and drop the
`"test:account-chain"` script entry — nothing else references the file.)

## U9 similar-problem sweep (dangling script/class targets in the tower mirror)

| Surface | Verdict |
|---|---|
| `test:account-chain` → `test_account_chain_callers.ts` | **finding (this document)** |
| All other npm-script `.ts` targets (36 total) | cleared — every target exists on main; swept programmatically |
| `test:unit` chain ordering after removal | cleared — pure conjunction of independent suites |
| Python side (`scripts/`, `tests/`, `examples/`) | cleared — pyflakes + U9 annotation sweep clean on main minus the already-WO'd `Sequence` (#257) |

## Evidence record

| Check | Result |
|---|---|
| `bun install --frozen-lockfile` (main `8242d4e`) | clean, 271 packages |
| `bun run test:unit` | aborts at test:account-chain, `ERR_MODULE_NOT_FOUND` |
| Suites before break | 18 pass (list above) |
| Suites after break | 13 orphaned; each run individually → rc=0 or documented env-skip |
| History | file add exists only as `815dca6` (bridge lane, not ancestor of main); wiring landed via `8a16924` (PR #212) |
| Module cross-check | 6/6 dynamic-import targets exist on main (lane heals cleanly on landing) |
| Systemic guard fix | issue #278 / `bridge-20261016-wiring-guard-reverse-check` |
| Audit base | main `8242d4e` |
