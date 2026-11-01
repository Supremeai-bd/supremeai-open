# GLM Agent 19 — Worklog (Job ID 486803)

> Post-purge restart (2026-11-01). The founder's doc purge (#4965,
> Batch 1/5: 308 files / 16,356 lines from docs/reports/ +
> docs/bridge/) removed every lane worklog, including this lane's
> 37-slot chain (r1–r37, PRs #3312–#4943). Nothing is restored
> verbatim; full history stays in git and the archive. This file
> restarts the small live slot per the standing hourly mandate
> ("keep worklog small, remove old worklog and keep only important
> part") — only the durable facts a fresh reader needs.

## Durable facts carried forward

- Identity: GLM Agent 19, Job ID 486803; zero-credential lane via the
  MCP tower; `mcp_call.py` session helper (session TTL self-heal).
  Probe targets always quoted from live artifacts, never memory
  (#3966): tower URL from AGENTS.md, canonical gateway from the README
  "Live Federation Services" table.
- **Standing U3 duty (#3806):** the tower's A2A card paths
  (`/.well-known/agent-card.json`, `/a2a`, legacy `/agent.json`) 404
  while the tower card's own `url` field declares the tower as the A2A
  endpoint. Issue was false-resolved once (merge-linked ≠
  finding-resolved, #3955); owner re-open still pending. Probed every
  cycle; one pass per cycle, no hammering.
- **Series state (35 datums):** gateway **35 consecutive** card-path
  404s; tower **23** (only JSON-assertable 404s count, U2); 18
  brownout windows absorbed without hammering (429 challenge,
  503-empty, boot "starting" quirk ×3, hang HTTP-000; window scope
  splits proven cross-plane AND intra-plane); 6 shadow-free windows;
  loop fail-dark 20×; certified-clean reads 2×; 5 lossless deferrals;
  delayed-retry proven 4× (#4705, #4791, #4943, #4997);
  informed-retry 2× (#4440, #4461).
- **Tower-brownout doctrine:** challenge windows cluster at the fleet
  cron wave, self-clear in ~1–2 min; one 429/5xx → single delayed
  retry (~100s); a 5xx/429 pair → U5 stop + lossless deferral; the
  session submit-plane can pass windows that block anonymous curl
  (two-sided — neither plane predicts the other).

## This cycle (02:19+08 Nov 2, r40) — thirty-second no-pick clean-hold

1. **Two-strike rule stands down — survived both purges.** Owner's
   second slimming wave landed (#4984 717-file purge, #4988 361
   legacy-test prune, #4995 58-lean-SSOT); docs/bridge/ **survived**
   with 15 files, this lane's slot untouched under its original name
   (others renamed to -post-purge variants). No third-rebuild clause
   needed; the gate-accepts-either-way posture pre-declared in r39
   held without conflict.
2. **U3 #3806 35th datum, 18:19Z — full steady state, zero new
   windows:** tower card paths 404 ×3 JSON-assertable (9B) → tower
   **23**; `/health` 200 (293B) — the 16:19Z boot reboot has fully
   recovered. Gateway fully clean → **35 consecutive** (`/health`
   healthy).
3. **Loop read:** freshness guard auto-rebased the tree (was 1
   behind) at boot; board totalOpen=**13** (2→13, +11 refill —
   drain-refill cadence now four-way confirmed: this series
   23→6→18→2→13, GLM 11 r43–r47, Sentry c111–c112); claimable 0/5;
   1 open PR (#4872) check-status UNSEEN → fail-dark 20th, no pick
   (U2).

Previous cycle (r39, 00:19+08): 34th datum was the 18th window, boot
sub-mode ×3 (tower `/health` `starting`, 0/0/0 — reboot observed);
restart convention adopted fleet-wide (GLM 04/11/14 after this lane's
r38/#4971); first submit 429 → 100s delayed retry landed #4997.

Lane discipline: nothing manufactured, nothing passed over; the slot
records what the loop dispatches and what the probes observe (AGENTS.md
§10). Post-purge epoch: restart accepted by the gate (r38/#4971); the
gate remains the final arbiter of this file's existence.
