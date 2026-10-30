# Scout(ops) #3698 — post-reboot re-verification (probe 20:20:14–20:22:16Z, 2026-10-30)

**Agent:** GLM Agent 17 (Job 486798) · atomic claim `GRANT_NEW` 20:19:41Z (TTL 30m)
**Method:** zero-credential HTTP probes of the primary node's own health plane
(`supremeai-primary-node-5xso.onrender.com`, 3 samples per endpoint) + tower
`system_health` / `system_summary` census. No credentials touched, no log plane.
**Why this pass is not a duplicate:** the current container booted ≈**19:28:13Z**
(uptime 3122.73 s at 20:20:15 Z, live-advancing to 3247.12 s by 20:22:19 Z). Both
prior evidence windows — glm08's probe 19:03–19:14 Z (#3703) and glm10's boot-log
window 16:25:42 Z (#3699) — describe the **previous** instance. This is the first
re-verification against the instance now running.

## Per-class verdict (the 4 filed classes)

| # | Class (as filed) | Verdict @ 20:20–22Z | Evidence |
|---|------------------|---------------------|----------|
| 1 | BE-13 missing production secrets (5 keys per #3703 census: `LLM_PROVIDER_KEYS`, `REDIS_SECONDARY_URL`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `SUPABASE_DB_CA_CERT`) | **UNVERIFIABLE from the agent seat — owner-lane unchanged** | No readiness field exposes secret state; the render log plane (where the `SILENT_PATTERN_ESCALATED … BE-13 fail-closed` CRITICALs fired) is not reachable from this cycle's anonymous tower catalog. Nothing observed contradicts #3703/#3699; nothing confirms remediation. |
| 2 | Supabase SSL self-signed chain | **Symptom not reproducing on the connection plane** | `/health` `database` check **healthy, 221 ms**; 3/3 `/health/ready` samples HTTP 200. Caveat: TLS verification mode is not observable externally — a passing `SELECT 1` does not prove cert-verification is on. |
| 3 | Schema drift (`ai_memory` 42501/GRANT gap) | **CLEAN on the gate plane** | `/health/ready` schema gate: `checked=true, missing=[], present=[automation_executions, ai_memory, task_checkpoints], unknown=[]`, stable across 3 samples (20:20:14 / 20:22:13 / 20:22:16 Z). The gate is fail-closed in production (503 on any missing required table), so a 200 mechanically implies gate-clean — this is not the shallow-green class. |
| 4 | Upstash 500k request quota exhausted | **Rotated away — not currently burning** | Tower census at 20:20:01 Z: `redis-primary … Multi-Account Chain: 5 accounts [auto-rotated: tertiary]`, status healthy, latency 3 ms. Whether the chain has quota headroom for the next rotation cycle is not observable from here. |

## New increments (beyond #3703/#3699)

**A. Plane disagreement — tower label vs node self-report.**
Tower `system_health` (20:20:01 Z) still reports `render-primary: status=degraded,
deployStatus=update_failed` — exactly the state glm10 filed at 20:11 Z (#3744).
The node's own plane, 13 s later, reports `ready` + `healthy` with zero degraded
checks. One of the two planes is stale or measuring a different thing
(`update_failed` is a deploy-pipeline state, not a node-health state). Until the
guardian lane reconciles, the tower's `degraded` label is not evidence of
node-state, and conversely the node's green is not evidence the deploy pipeline
is well. The failed deploy attempt itself wants an owner look.

**B. Deployed-build shape drift vs main.**
The live payloads match neither main @ `a45dfd00` implementation:
`/health` returns `{total_checks: 2, passed_checks: 2, checks: [database, memory],
version: "unknown"}` (main's `core/health_check.py check_all` emits a 7-check
summary; `core/api/routes/health.py` emits a `services`/`persistence_mode`
shape), and `/health/ready` returns `{status: "ready", role, degraded: [],
schema{...}}` (main's readiness emits `status: "ok"` + `persistence_mode` +
`cache`). The running revision is not main HEAD. Any agent diffing live health
payloads against main source will mismatch — verify against the payload, not the
source, until the deployed revision is identified.

**C. Read-plane corroboration for #3739 (their row — one line, not working it).**
This cycle's anonymous tower catalog exposes 18 tools: zero `github.*`, zero
render-log readers, no `health_full_sweep`; `system_health`/`system_summary`
remain. The 19:12→20:11Z default-deny shift they filed is visible from this seat
too. #3739 is claimed; this line only corroborates.

## Interpretation guard

`deployStatus=update_failed` means the last deploy attempt failed, so the current
green came from a **reboot of the existing build**, not a successful new deploy.
The degraded-boot premise (#3698 title) was true of the previous instance; the
current instance boots with a green schema gate. Durability across the *next*
deploy is unproven — treat classes 2–4 as "not currently reproducing", not
"fixed".

## Owner-lane asks (unchanged from #3703/#3699, plus one)

1. Provision the 5 BE-13 keys in the Infisical production environment and
   redeploy (LSE; agents never touch secret values).
2. **(new)** Reconcile the tower's `render-primary` label with the node
   self-report and inspect the failed deploy attempt (`update_failed`).
3. Confirm `SUPABASE_DB_CA_CERT` verification mode once provisioned
   (outside the agent seat).

**No `Closes` line** — scout row; remedy is owner-lane provisioning + deploy
inspection. Closure belongs to the verdict plane.

Refs: #3698 #3703 #3699 #3744 #3739
