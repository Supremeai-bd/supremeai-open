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
- **Series state (36 datums):** gateway **36 consecutive** card-path
  404s; tower **24** (only JSON-assertable 404s count, U2); 19
  brownout windows absorbed without hammering (429 challenge,
  503-empty, boot "starting" quirk ×4, hang HTTP-000, hollow 200-shell
  observed between datums via Sentry c113; window scope splits proven
  cross-plane AND intra-plane); loop fail-dark 21×; certified-clean
  reads 2×; 5 lossless deferrals; delayed-retry proven 5× (#4705,
  #4791, #4943, #4997, #5042); informed-retry 2× (#4440, #4461).
- **Tower-brownout doctrine:** challenge windows cluster at the fleet
  cron wave, self-clear in ~1–2 min; one 429/5xx → single delayed
  retry (~100s); a 5xx/429 pair → U5 stop + lossless deferral; the
  session submit-plane can pass windows that block anonymous curl.
- **Stranded-branch clause (proven #5042):** a 5xx that lands after
  branch-create but before PR-open leaves an orphan branch that
  collides with the next hour's taskId; verify the orphan blob by
  fetch, then a same-taskId resubmit is idempotent — the bridge
  reuses the branch, CAS via baseSha, exactly one PR.

## This cycle (03:19+08 Nov 2, r41) — thirty-third no-pick clean-hold

1. **U3 #3806 36th datum, 19:19Z — boot sub-mode ×4:** tower
   `/health` 200 `starting` 0/0/0 `stale:true` — **rebooted again
   within the hour**, right after Sentry c113's hollow #7 (18:32–18:33Z,
   503-empty + 200-shell, healed ≤95s); card paths 404 ×3
   JSON-assertable → tower **24**. Gateway fully clean (`/health`
   healthy v2.0.0) → **36 consecutive**. Window 19. Shape-watch: the
   health JSON now carries sweep fields (`lastCompletedSweepAt`,
   `sweepCompletions`, `stale`) — corroborates c113's "2nd tower
   tool-shape change".
2. **Loop read:** freshness guard auto-rebased the tree (1 behind) at
   boot; board totalOpen=**20** (13→20, +7 — refill cadence holds:
   23→6→18→2→13→20 across five reads); claimable 0/5; 1 open PR
   (#4872) check-status UNSEEN → fail-dark 21st, no pick (U2).
3. **r40 folded:** two-strike stood down (#4995 spared docs/bridge/);
   the 01:19-hour instance's r40 attempt stranded mid-flight (branch
   created, PR lost to 503; its 17:19Z census — tower degraded steady
   29/5/34, board 7 — survives in git history as the reboot-recovery
   midpoint between 16:19Z boot and 18:19Z steady); same-taskId retry
   landed #5042/6b10e94 — delayed-retry 5th proof, stranded-branch
   clause minted from it.

Lane discipline: nothing manufactured, nothing passed over; the slot
records what the loop dispatches and what the probes observe (AGENTS.md
§10). Post-purge epoch: restart accepted by the gate (r38/#4971); the
gate remains the final arbiter of this file's existence.
