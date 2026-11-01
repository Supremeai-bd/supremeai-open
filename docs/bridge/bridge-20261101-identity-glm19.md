# GLM Agent 19 — Worklog (Job ID 486803)

> Post-purge restart (2026-11-01). The founder's doc purge (#4965,
> wave 1 of the Nov-1 slimming) removed every lane worklog, including
> this lane's 37-slot chain (r1–r37, PRs #3312–#4943). Nothing is
> restored verbatim; full history stays in git and the archive. This
> file restarts the small live slot per the standing hourly mandate
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
  endpoint. False-resolved once (merge-linked ≠ finding-resolved,
  #3955); owner re-open still pending. One probe pass per cycle, no
  hammering.
- **Purge survival:** the slot survived both purge waves under its
  original name (wave 2, #4984 + #4988 + #4995, spared docs/bridge/
  entirely); the pre-declared two-strike clause stood down at r40.
- **Series state (40 datums):** gateway **40 consecutive** card-path
  404s; tower **28** (only JSON-assertable 404s count, U2); 21
  brownout windows absorbed without hammering (429 challenge,
  503-empty, boot "starting" quirk ×6, hang HTTP-000, hollow 200-shell
  observed between datums via Sentry c113; window scope splits proven
  cross-plane AND intra-plane); loop fail-dark 25×; certified-clean
  reads 2×; 5 lossless deferrals; delayed-retry proven 6× (#4705,
  #4791, #4943, #4997, #5042, #5098); informed-retry 2× (#4440,
  #4461).
- **Tower-brownout doctrine:** challenge windows cluster at the fleet
  cron wave, self-clear in ~1–2 min; one 429/5xx → single delayed
  retry (~100s); a 5xx/429 pair → U5 stop + lossless deferral; the
  session submit-plane can pass windows that block anonymous curl.
  Two 503 species: pre-branch (clean rejection — #5098) vs
  post-branch (stranded branch — #5042); both resolve via ls-remote +
  blob-verify before any retry.
- **Tower reboot pattern — cadence WITHDRAWN:** boots observed at
  16:19 / 19:19 / 22:19 / 23:19Z; the 3-h spacing hypothesis minted at
  r44 was falsified one cycle later by a 1-h gap. Honest reading:
  reboots are irregular (gaps 3h, 3h, 1h), hourly sampling only
  brackets boot times within the hour; `sweepCompletions` resets
  per-boot (confirmed twice). No boot prediction is issued anymore.
  Board drain-refill cadence: 2→13→20→27→5→13→14 (seven reads;
  refill rate varies: +11/+7/+7/−22/+8/+1; sweep ~5.5 h).

## This cycle (07:19+08 Nov 2, r45) — thirty-seventh no-pick clean-hold

1. **U3 #3806 40th datum, 23:19Z — boot ×6, cadence falsified:**
   tower `/health` `starting` 0/0/0 only 1 h after the 22:19Z boot —
   the r44 "3-h cadence" prediction failed at its first test and is
   **withdrawn** (gaps now 3h, 3h, 1h); card paths 404 ×3
   JSON-assertable → tower **28**; gateway fully clean → **40
   consecutive**; window 21. The r44 wording ("trend not law") is
   what allowed a clean retraction — doctrine holds.
2. **Loop read:** freshness 0-behind; board totalOpen=**14** (13→14,
   +1 — refill rate varies hour to hour); claimable 0/5; 1 open PR
   (#5117) check-status UNSEEN → fail-dark 25th, no pick (U2).
3. **r44 folded:** boot ×5 + 3-h cadence hypothesis (now withdrawn);
   per-boot sweep-counter reset confirmed live; delayed-retry 6th
   proof (#5098 clean-rejection species).

Lane discipline: nothing manufactured, nothing passed over; the slot
records what the loop dispatches and what the probes observe (AGENTS.md
§10). Post-purge epoch: restart accepted by the gate (r38/#4971); the
gate remains the final arbiter of this file's existence.
