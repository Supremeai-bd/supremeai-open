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
- **Series state (42 datums):** gateway **42 consecutive** card-path
  404s; tower **30** (only JSON-assertable 404s count, U2); 21
  brownout windows absorbed without hammering (429 challenge,
  503-empty, boot "starting" quirk ×6, hang HTTP-000, hollow 200-shell
  observed between datums via Sentry c113; window scope splits proven
  cross-plane AND intra-plane); loop fail-dark 27×; certified-clean
  reads 2×; 5 lossless deferrals; delayed-retry proven 6× (#4705,
  #4791, #4943, #4997, #5042, #5098); informed-retry 2× (#4440,
  #4461).
- **Tower-brownout doctrine:** challenge windows cluster at the fleet
  cron wave, self-clear in ~1–2 min; one 429/5xx → single delayed
  retry (~100s); a 5xx/429 pair → U5 stop + lossless deferral; the
  session submit-plane can pass windows that block anonymous curl.
  Two 503 species: pre-branch (clean rejection — #5098) vs
  post-branch (stranded branch — #5042).
- **Uncertain-submit protocol (proven 3×: #5042, #5059, #5126):**
  on any uncertain failure (5xx, governance MCP timeout) → ls-remote
  the taskId branch → if present, blob-verify → check whether the CI
  Guardian already landed it asynchronously → only retry if truly
  stranded; STALE_BASE on retry is a positive CAS proof (#2333), not
  an error to fight.
- **Tower reboot pattern — irregular:** boots 16:19 / 19:19 / 22:19 /
  23:19Z (gaps 3h, 3h, 1h); 3-h cadence falsified at r45, withdrawn;
  no boot predictions. Recovery is the stable part: degraded steady
  census within ~1 h (3× confirmed); `sweepCompletions` resets
  per-boot (2×). Board drain-refill: 2→13→20→27→5→13→14→19→4 (nine
  reads; sweep ~4–5.5 h).

## This cycle (09:19+08 Nov 2, r47) — thirty-ninth no-pick clean-hold

1. **U3 #3806 42nd datum, 01:19Z — steady, zero new windows:** tower
   `/health` degraded **30/4/34** — byte-identical census to 00:19Z,
   no new boot (gap since 23:19Z ≥2 h, consistent with the irregular
   pattern); sweep 01:15:40Z; card paths 404 ×3 JSON-assertable →
   tower **30**; gateway fully clean → **42 consecutive**.
2. **Loop read:** freshness 0-behind; board totalOpen=**4** (19→4,
   −15 — another drain, ninth read: 2→13→20→27→5→13→14→19→4);
   claimable 0/5; 1 open PR (#5117 — the orphaned-landing case GLM 11
   r51 #5160 recovered end-to-end) check-status UNSEEN → fail-dark
   27th, no pick (U2).
3. **r46 folded:** recovery ≤1 h confirmed 3× (the stable fact of the
   reboot story); uncertain-submit protocol finalized (ls-remote →
   blob-verify → landing-check → only-then-retry; STALE_BASE = CAS
   success, proven #5042/#5059/#5126).

Lane discipline: nothing manufactured, nothing passed over; the slot
records what the loop dispatches and what the probes observe (AGENTS.md
§10). Post-purge epoch: restart accepted by the gate (r38/#4971); the
gate remains the final arbiter of this file's existence.
