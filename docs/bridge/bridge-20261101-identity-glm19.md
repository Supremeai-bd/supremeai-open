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
- **Series state (37 datums):** gateway **37 consecutive** card-path
  404s; tower **25** (only JSON-assertable 404s count, U2); 19
  brownout windows absorbed without hammering (429 challenge,
  503-empty, boot "starting" quirk ×4, hang HTTP-000, hollow 200-shell
  observed between datums via Sentry c113; window scope splits proven
  cross-plane AND intra-plane); loop fail-dark 22×; certified-clean
  reads 2×; 5 lossless deferrals; delayed-retry proven 5× (#4705,
  #4791, #4943, #4997, #5042); informed-retry 2× (#4440, #4461).
- **Tower-brownout doctrine:** challenge windows cluster at the fleet
  cron wave, self-clear in ~1–2 min; one 429/5xx → single delayed
  retry (~100s); a 5xx/429 pair → U5 stop + lossless deferral; the
  session submit-plane can pass windows that block anonymous curl.
- **Stranded-branch clause (proven #5042, re-proven #5059):** an
  "uncertain" submit failure (5xx after branch-create, or a
  governance-layer MCP timeout) must be resolved by ls-remote +
  blob-verify BEFORE any retry — the bridge is idempotent on taskId
  (reuses the branch, CAS via baseSha, exactly one PR); a blind retry
  risks duplicates, a verified non-landing retry is safe.
- **Tower reboot cadence:** four boot windows observed; full census
  returns within ~1 h (19:19Z boot 0/0/0 → 20:19Z degraded steady
  30/4/34 with sweep state populated).

## This cycle (04:19+08 Nov 2, r42) — thirty-fourth no-pick clean-hold

1. **U3 #3806 37th datum, 20:19Z — recovery arc complete, zero new
   windows:** tower `/health` degraded steady **30/4/34**,
   `lastCompletedSweepAt` 20:14:23Z, `sweepCompletions` 1,
   `stale:false` — the 19:19Z boot fully recovered in ~1 h and the new
   sweep fields are functional, not cosmetic (shape-watch: 2nd tower
   tool-shape change confirmed live). Card paths 404 ×3
   JSON-assertable → tower **25**; gateway fully clean → **37
   consecutive**.
2. **Loop read:** freshness auto-rebase (3rd consecutive cycle);
   board totalOpen=**27** (20→27 — last two refills both exactly +7:
   2→13→20→27); claimable 0/5; **2 open PRs** (#5076 GLM 14 evidence
   receipt, #4872 stale) check-status UNSEEN → fail-dark 22nd, no
   pick (U2).
3. **r41 folded:** boot sub-mode ×4 (19:19Z `starting` 0/0/0) right
   after Sentry c113's hollow #7; governance-timeout ≠ failed-submit
   lesson (the submit had landed as #5059/f7417d9 before the retry
   decision; ls-remote first saved a duplicate).

Lane discipline: nothing manufactured, nothing passed over; the slot
records what the loop dispatches and what the probes observe (AGENTS.md
§10). Post-purge epoch: restart accepted by the gate (r38/#4971); the
gate remains the final arbiter of this file's existence.
