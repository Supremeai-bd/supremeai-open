# Tower exposure probe — standing machine check + first archived receipt (issue #2076)

Report-only + one new standing check script. Delivers #2076's unmet archive requirement
("Probe results must be archived — script committed to scout workspace") and the agent-safe
foundation of deliverable B. Zero credentials, zero advertised-tool executions.

## Files

1. `scripts/tower_discovery_probe.py` — the standing machine check (stdlib-only). Contract:
   - `exit 0 "pass"` — advertised ∩ {secret, destructive name-classes} = ∅ AND count ≤ baseline
   - `exit 1 "violation"` — any secret/destructive candidate advertised, or count grew vs
     baseline (fail-close; shrink-only ratchet via `--baseline`)
   - `exit 0 "skip"` — tower unreachable (honest-skip, #1760 offline doctrine; no fake red CI)
   - Advertisement-only evidence by design: the probe NEVER executes an advertised tool
     (`executed_advertised_tools: 0` in every receipt). A name being advertised is itself the
     policy breach; execution would turn a read-only probe into the incident.
   - NOT wired into `scripts/ops/ai/drift_checks.py`: that surface is deterministic/offline
     (regex over local files) by its own contract; a network probe there would break the
     offline doctrine and force CI to depend on a live third-party endpoint. The probe script
     is the machine check; the drift_checks wiring (and the `advertised ⊆ tree-registry`
     assertion, which needs tower-repo internals) routes to the tower/maintainer lane.

## First archived receipt — 2026-10-28T10:00:23Z (zero-credential)

```json
{"check": "tower_exposure_probe", "url": "https://supremeai-mcp-tower.onrender.com/mcp",
 "at": "2026-10-28T10:00:23Z", "zero_credential": true, "executed_advertised_tools": 0,
 "status": "violation", "advertised_count": 142,
 "secret_class_candidates": ["client_rotate_token", "github_list_secrets",
   "infisical_audit_secrets", "redis_read_key", "render_get_env_var_keys",
   "render_get_env_vars", "slot_rotate_credential", "tenant_rotate_admin_token"],
 "destructive_class_candidates": ["action_cloudflare_purge", "action_render_deploy",
   "autonomy_kill_switch", "client_approve", "client_revoke", "client_rotate_token",
   "memory_delete_entities", "memory_delete_observations", "memory_delete_relations",
   "policy_approve", "slot_approve", "slot_provision", "slot_revoke",
   "slot_rotate_credential", "tenant_rotate_admin_token"]}
```

## Findings

1. **Exposure persists 13 minutes after filing** (issue 09:47:09Z, receipt 10:00:23Z):
   anonymous zero-credential `tools/list` still returns **142 tools** — the exact count the
   issue reports. No redeploy has landed between filing and this receipt.
2. **Classification delta is honest, not a contradiction**: the issue counts
   5 destructive + 4 secret via the tower's capability classes (`mcp-access.ts`); this probe
   is name-pattern based and reports 15 + 8 *candidates*. Candidate-level overcounting is the
   safe direction (fail-close); the tower's own classification remains authoritative for the
   ∅ assertion once deliverable A's redeploy lands.
3. **Secret-class advertisement is the sharpest edge**: `render_get_env_vars`,
   `github_list_secrets`, `infisical_audit_secrets` being *listed* to anonymous clients is
   reconnaissance-as-a-service even if every execution is role-gated — tool names advertise
   the stack (Render, Infisical, Redis, tenant model) before any RBAC check runs.
4. `client_revoke` / `slot_revoke` appear in this receipt but not in the filing-time scan —
   advertisement set is live-mutable; another reason the check must be standing, not one-shot.

## Routing (per #2076's own deliverable split)

- **A (maintainer)**: Render redeploy + probe re-run — the re-run is now one command:
  `python scripts/tower_discovery_probe.py --json`. Re-run AFTER the redeploy, before any
  "fixed" claim (the issue's own acceptance rule).
- **B (standing check)**: the probe script here is the check; drift-wiring + tree-registry
  assertion remain maintainer decisions (tower-repo data required for the ⊆ half).
- **C (docs parity)**: `docs/TOOL-EXPOSURE.md` and `mcp_config.remote.json` live in the
  tower repo — outside this lane (bridge lands to supremeai-open only; protected-path
  contract #1643/#1769).

## Boundary

One new script + one new report, zero code paths touched, no `.github/**`, no credentials,
no tool executions. The probe is intentionally URL-parameterized so it can point at any
tower instance (staging vs prod) without code edits. Honest absence: deploy history
(Render-side) is unreadable from this lane — persistence claim above rests on the receipt
timestamp vs issue timestamp, both UTC.
