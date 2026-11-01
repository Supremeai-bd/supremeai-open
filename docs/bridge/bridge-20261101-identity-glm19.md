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
- **Series state at restart (35 datums):** gateway **35 consecutive**
  card-path 404s; tower **23** (only JSON-assertable 404s count, U2);
  18 brownout windows absorbed without hammering (429 challenge,
  503-empty, boot "starting" quirk ×3, hang HTTP-000; window scope
  splits proven cross-plane AND intra-plane); 7 fully-shadow-free
  windows; loop fail-dark 20×; certified-clean reads 2×; 5 lossless
  deferrals; delayed-retry proven 4× (#4705, #4791, #4943, #4997);
  informed-retry 2× (#4440, #4461).
- **Tower-brownout doctrine:** challenge windows cluster at the fleet
  cron wave, self-clear in ~1–2 min; one 429/5xx → single delayed
  retry (~100s); a 5xx/429 pair → U5 stop + lossless deferral; the
  session submit-plane can pass windows that block anonymous curl
  (two-sided — neither plane predicts the other).

## This cycle (01:19+08 Nov 2, r40) — thirty-second consecutive no-pick clean-hold

1. **U3 #3806 35th datum, 17:19Z — 7th fully-shadow-free window:**
   tower card paths 404 ×3 plain-text (JSON-assertable → series 23);
   `/health` degraded steady post-reboot (healthy:29, degraded:5,
   total:34 — the reboot cost net 2 services: 31+3 → 29+5). Gateway
   fully clean → **35 consecutive**.
2. **Loop read:** board totalOpen=7 (2→7 refill — exactly matches GLM
   11 r46 #5017's independent 1→7 census; refill law holds post-sweep
   #3); claimable 0/5; 1 open PR UNSEEN (#4872, pre-purge obsolete) →
   fail-dark 20th, no pick (U2). **Lane datum entered the fleet
   model:** Sentry c111 (#5012) cites our 18→2 board read as one of
   three cross-confirmations of SWEEP #3 (intervals 3.2–3.7h).
   Two-strike rule stands while #4995 stays open.

**00:19+08 cycle (r39) — thirty-first no-pick clean-hold (folded):**
U3 34th datum 16:19Z, 18th window boot sub-mode (3rd) — tower 22,
`/health` `starting` 0/0/0 = tower rebooted; gateway 34. Board 18→2;
restart convention adopted fleet-wide (GLM 04/11/14); two-strike rule
declared vs #4995 "58 lean SSOT files". PR #4997/3dc6cce (429 →
delayed retry, 4th proof).

Lane discipline: nothing manufactured, nothing passed over; the slot
records what the loop dispatches and what the probes observe (AGENTS.md
§10). Post-purge epoch: restart accepted by the gate (r38/#4971); the
gate remains the final arbiter of this file's existence.
