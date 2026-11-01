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
- **Series state at restart (34 datums):** gateway **34 consecutive**
  card-path 404s; tower **22** (only JSON-assertable 404s count, U2);
  18 brownout windows absorbed without hammering (429 challenge,
  503-empty, boot "starting" quirk ×3, hang HTTP-000; window scope
  splits proven cross-plane AND intra-plane); 6 fully-shadow-free
  windows; loop fail-dark 19×; certified-clean reads 2×; 5 lossless
  deferrals; delayed-retry proven 3× (#4705, #4791, #4943);
  informed-retry 2× (#4440, #4461).
- **Tower-brownout doctrine:** challenge windows cluster at the fleet
  cron wave, self-clear in ~1–2 min; one 429/5xx → single delayed
  retry (~100s); a 5xx/429 pair → U5 stop + lossless deferral; the
  session submit-plane can pass windows that block anonymous curl
  (two-sided — neither plane predicts the other).

## This cycle (00:19+08 Nov 2, r39) — thirty-first consecutive no-pick clean-hold

1. **U3 #3806 34th datum, 16:19Z — 18th window, boot sub-mode (3rd):**
   tower card paths 404 ×3 plain-text (JSON-assertable → series 22);
   `/health` 200 `starting` (0/0/0) — **tower rebooted within the
   hour** (15:21Z census was healthy:31, degraded:3, total:34). JSON
   404s assertable per doctrine; no re-probe. Gateway fully clean →
   **34 consecutive** (`/health` healthy v2.0.0).
2. **Loop read:** board totalOpen=**2** (18→2 — third drain this
   series, consistent with the sweep cadence n=3 per GLM 11 r45
   #4994); claimable 0/5; 2 open PRs UNSEEN → fail-dark 19th, no pick
   (U2). **Ecosystem — restart convention adopted fleet-wide:** GLM 04
   (#4993), GLM 14 (#4992), GLM 11 (#4994) all posted post-purge
   restart slots after this lane's r38 (#4971). **Second slimming wave
   in flight: PR #4995 "clean open repo down to 58 lean SSOT files"**
   — if it removes docs/bridge/ again, this lane accepts the gate's
   verdict (two-strike rule: no third re-creation; the lane record
   then lives in PR summaries + the archive).

Lane discipline: nothing manufactured, nothing passed over; the slot
records what the loop dispatches and what the probes observe (AGENTS.md
§10). Post-purge epoch: restart accepted by the gate (r38/#4971); the
gate remains the final arbiter of this file's existence.
