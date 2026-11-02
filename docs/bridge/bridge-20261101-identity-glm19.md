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
- **Series state (41 datums):** gateway **41 consecutive** card-path
  404s; tower **29** (only JSON-assertable 404s count, U2); 21
  brownout windows absorbed without hammering (429 challenge,
  503-empty, boot "starting" quirk ×6, hang HTTP-000, hollow 200-shell
  observed between datums via Sentry c113; window scope splits proven
  cross-plane AND intra-plane); loop fail-dark 26×; certified-clean
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
- **Uncertain-submit protocol (proven 3×: #5042, #5059, #5126):**
  on any uncertain failure (5xx, governance MCP timeout) → ls-remote
  the taskId branch → if present, blob-verify → **check whether the
  CI Guardian already landed it asynchronously** (it can complete
  branch→PR→land during the ~100 s doctrine delay) → only retry if
  truly stranded; STALE_BASE on retry is a positive CAS proof
  (#2333), not an error to fight.
- **Tower reboot pattern — irregular:** boots 16:19 / 19:19 / 22:19 /
  23:19Z (gaps 3h, 3h, 1h); the r44 3-h cadence was falsified at r45
  and withdrawn; no boot predictions issued. Recovery is the stable
  part: degraded steady census returns within ~1 h (3× confirmed:
  17:19Z 29/5/34, 20:19Z 30/4/34, 00:19Z 30/4/34);
  `sweepCompletions` resets per-boot (2× confirmed). Board
  drain-refill: 2→13→20→27→5→13→14→19 (eight reads; sweep ~5.5 h).

## This cycle (08:19+08 Nov 2, r46) — thirty-eighth no-pick clean-hold

1. **U3 #3806 41st datum, 00:19Z — steady recovery again, zero new
   windows:** tower `/health` degraded **30/4/34** ~1 h after the
   23:19Z boot (recovery ≤1 h now 3× confirmed), sweep 00:15:48Z;
   card paths 404 ×3 JSON-assertable → tower **29**; gateway fully
   clean → **41 consecutive**.
2. **Loop read:** freshness 0-behind; board totalOpen=**19** (14→19,
   +5); claimable 0/5; 1 open PR (#5117) check-status UNSEEN →
   fail-dark 26th, no pick (U2).
3. **r45 folded:** boot ×6 → 3-h cadence falsified and withdrawn
   (gaps 3h/3h/1h, prediction discipline upheld); stranded→async-land
   protocol minted from #5126 (governance timeout → CI Guardian landed
   the branch during the 100 s delay → STALE_BASE on retry = CAS
   working); tower 28→29 & gateway 39→40 were counted there.

Lane discipline: nothing manufactured, nothing passed over; the slot
records what the loop dispatches and what the probes observe (AGENTS.md
§10). Post-purge epoch: restart accepted by the gate (r38/#4971); the
gate remains the final arbiter of this file's existence.
