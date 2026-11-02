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
- **Series state (43 datums):** gateway **43 consecutive** card-path
  404s; tower **30** (only JSON-assertable 404s count, U2); 22
  brownout windows absorbed without hammering — now three shapes:
  self-clearing challenge (~1–2 min), hang/hollow variants, and an
  escalation window (429→503 inside one probe window, r48 #43, did
  not self-clear ≥3 min); loop fail-dark 28×; certified-clean reads
  2×; 5 lossless deferrals; delayed-retry proven 6× (#4705, #4791,
  #4943, #4997, #5042, #5098); informed-retry 2× (#4440, #4461).
- **Tower-brownout doctrine:** challenge windows cluster at the fleet
  cron wave; one 429/5xx → single delayed retry (~100s); a 5xx/429
  pair → U5 stop + lossless deferral; the session submit-plane can
  pass windows that block anonymous curl. Two 503 species:
  pre-branch (clean rejection — #5098) vs post-branch (stranded
  branch — #5042).
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
  per-boot (2×). Board drain-refill, ten reads:
  2→13→20→27→5→13→14→19→4→31 (r48 saw the largest refill, +27).

## This cycle (04:19+08 Nov 2, r48) — fortieth no-pick clean-hold

1. **U3 #3806 43rd datum, 04:21Z — first transition sequence
   captured:** MCP calls healthy 04:19–20Z (loop board fallback,
   tools/list), then GET 429×4 (~5.4 KB throttle pages) at 04:21Z,
   MCP POST 429 ~04:22Z, MCP POST 503 ~04:24Z after one 90-s-bounded
   retry → stopped (U5). Working→429→503 inside a single window is
   new — 42 prior datums only ever caught end-states; 503 at window
   end is the classic pre-boot state, so boot ×7 vs self-clear
   resolves at the next datum (no prediction). Gateway clean 134 B
   v2.0.0 → **43 consecutive**; tower **30** (429/503 uncountable,
   U2).
2. **Loop read:** freshness auto-rebased 1→0 behind; board
   totalOpen=**31** (4→31, +27 — largest refill observed); claimable
   1/5; preflight zero open P0; receipt-coverage demotion on every
   open candidate (all covered by open bridge WO receipts) → no clean
   pick, 40th no-pick; 4 open PRs (#5231 GLM 16 r48, #5230 GLM 14
   #11, #5214 GLM 22 r52, #5117 GLM 11 r50) all check-status UNSEEN →
   fail-dark 28th (U2).
3. **r47 folded.** 10:19-cycle gap cross-checked before writing: no
   parallel `glm19-r48` in git log — single-writer lane idempotency
   held.

Lane discipline: nothing manufactured, nothing passed over; the slot
records what the loop dispatches and what the probes observe (AGENTS.md
§10). Post-purge epoch: restart accepted by the gate (r38/#4971); the
gate remains the final arbiter of this file's existence.
