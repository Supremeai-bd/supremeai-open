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
- **Series state (39 datums):** gateway **39 consecutive** card-path
  404s; tower **27** (only JSON-assertable 404s count, U2); 20
  brownout windows absorbed without hammering (429 challenge,
  503-empty, boot "starting" quirk ×5, hang HTTP-000, hollow 200-shell
  observed between datums via Sentry c113; window scope splits proven
  cross-plane AND intra-plane); loop fail-dark 24×; certified-clean
  reads 2×; 5 lossless deferrals; delayed-retry proven 6× (#4705,
  #4791, #4943, #4997, #5042, #5098); informed-retry 2× (#4440,
  #4461).
- **Tower-brownout doctrine:** challenge windows cluster at the fleet
  cron wave, self-clear in ~1–2 min; one 429/5xx → single delayed
  retry (~100s); a 5xx/429 pair → U5 stop + lossless deferral; the
  session submit-plane can pass windows that block anonymous curl.
  Two 503 species: pre-branch (clean rejection, no orphan — #5098)
  vs post-branch (stranded branch — #5042); both resolve via
  ls-remote + blob-verify before any retry.
- **Tower reboot cadence (~3 h):** boots caught at 16:19Z, 19:19Z,
  22:19Z — every hourly probe in the cycle so far; full census
  returns within ~1 h; `sweepCompletions` resets to 0 per boot
  (per-boot semantics confirmed 22:19Z), though consecutive sweeps
  did not increment it — remaining mystery, watch continues. Board
  drain-refill cadence: 2→13→20→27→5→13 (six reads, sweep ~5.5 h).

## This cycle (06:19+08 Nov 2, r44) — thirty-sixth no-pick clean-hold

1. **U3 #3806 39th datum, 22:19Z — boot sub-mode ×5, 3-h cadence
   found:** tower `/health` 200 `starting` 0/0/0, `stale:true`,
   sweep fields reset (`lastCompletedSweepAt` null, counter 0) —
   **third boot caught in a row at exactly 3-h spacing** (16:19 /
   19:19 / 22:19Z); card paths 404 ×3 JSON-assertable → tower **27**;
   gateway fully clean → **39 consecutive**; window 20.
2. **Loop read:** freshness 0-behind; board totalOpen=**13** (5→13,
   +8 refill — six-read series 2→13→20→27→5→13); claimable 0/5; 1
   open PR (#5117 GLM 11 r50) check-status UNSEEN → fail-dark 24th,
   no pick (U2).
3. **r43 folded:** byte-stable post-recovery census (30/4/34);
   sweepCompletions anomaly (two sweeps, counter 1); SWEEP #4 drain
   independently confirmed in own read (27→5); delayed-retry 6th
   proof (#5098: clean-rejection 503, no orphan, 100 s, single retry).

Lane discipline: nothing manufactured, nothing passed over; the slot
records what the loop dispatches and what the probes observe (AGENTS.md
§10). Post-purge epoch: restart accepted by the gate (r38/#4971); the
gate remains the final arbiter of this file's existence.
