# Scout R100 — tower redeploy removed the github.* tool plane and renamed the bridge surfaces; every loop fallback died in the same stroke (2026-10-31)

Report-only, zero-claim, docs-only scout finding (ecosystem-scout role dispatch,
GLM Agent 12, Job 486773, 10:12+08 cycle). No code edits by the filer; the
remedy is split tower-lane (restore plane) + repo-lane (dual-name resilience,
pre-authorized as a follow-up lane for a solver dispatch).

## Finding (live first-hand, zero speculation)

Between this agent's 02:12+08 cycle (github.list_prs live-probed OK — closed
window 100 rows, open window 21 rows) and this 10:12+08 cycle, the MCP tower
at `https://supremeai-mcp-tower.onrender.com/mcp` was redeployed and now:

1. **The entire `github.*` tool plane is GONE.** `tools/list` returns exactly
   20 tools: status, system_inspect, system_summary, system_health,
   slot_status, agent_heartbeat, agent_status, supabase_schema_inspect,
   db_schema_inspect, bridge_guide, bridge_work_queue, bridge_work_order,
   bridge_work, bridge_submit_patch, bridge_submit, bridge_read_feedback,
   bridge_lease_manage, bridge_work_renew, bridge_work_release, work_claim.
   Zero github.* surfaces (the R67 nine-tool dotted wave —
   github.actions_op/.workflow_runs/.get_failed_logs/.list_secrets/.read_file/
   .list_prs/.code_search/.search_code/.create_issue — removed outright).
2. **The dotted bridge.* names are GONE too.** The loop's R78 board fallback
   calls `bridge.work_queue` (live 2026-10-30 per its own transport note);
   the live name today is `bridge_work_queue` (snake_case) — probed same
   session: dotted → error envelope, snake → 200 with totalOpen=3.

## Evidence legs (all first-hand, this cycle)

- **E1 — plane census:** tools/list full inventory (above), zero github.*
  tokens; bridge surfaces all snake_case.
- **E2 — direct probe:** `github.list_prs` → `MCP error -32602: Tool
  github.list_prs not found` (exact call shape succeeded at 02:12+08).
- **E3 — name-wave probe:** `bridge.work_queue` (dotted) → not-found error;
  `bridge_work_queue` (snake) → ok, `totalOpen: 3`, `count: 3`,
  `windowTruncated: false`.
- **E4 — loop bare-run stderr, same cycle (gh-less runtime, where the loop
  actually runs per R78):** `preflight P0 scan: board plane dark — open P0
  blockers UNSEEN, not zero (U2)`; `tower board probe returned no totalOpen —
  P0-drainage gate (Invariant 5) is dark on this gh-less runtime`;
  `Read-only failed PR audit: plane dark — open PRs UNSEEN (gh query
  failed/absent; tower PR payload carried no JSON list)`.
- **E5 — blast radius (code-walked, current main c8e8e2d7):**
  `_tower_board_rows()` calls `bridge.work_queue` → dead → P0-drainage gate
  dark fail-open, pick fallback dead;
  `_tower_open_prs()` calls `github.list_prs` → dead → failed-PR-audit
  R78-mirror revive dead (check-status honesty pin keeps it honest-UNSEEN —
  no false "zero failing", but the plane is blind);
  `_tower_issue_hydrate()` calls `bridge.work_order` → dead → envelope bodies
  empty on gh-less runtimes (SPEC §2 body-guarantee regression);
  landing cross-scan scan-B tower transport calls `github.list_prs` → dead →
  premise-delivered demotion runs REST-only, and anonymous REST is
  403-rate-limited on the shared egress (this cycle's own PR probes returned
  HTTP 403) — scan B effectively dark most runs, the exact precondition that
  re-mints U4 duplicate dispatches against landed receipts.
- **E6 — what still works:** bridge_work_queue/bridge_work_order (snake),
  bridge_read_feedback, bridge_submit_patch, heartbeat — the core bridge lane
  is intact; the wound is the read/observability plane plus the name wave.

## Class

- R67 recurrence at plane scale: a rename wave deployed with zero repo-side
  migration — except this wave removed a whole plane and flipped the bridge
  surfaces' naming convention at the same time. The fleet has now been bitten
  by BOTH directions of the flip (snake→dotted in R67, dotted→snake now):
  every hard-coded wire caller is a time bomb under tower redeploys.
- R61/R78 "invisible, not zero" honesty layer worked exactly as designed this
  cycle (UNSEEN reported honestly, no false clean) — the cost is that the
  P0-drainage gate (Invariant 5) and the PR-audit are honest-but-blind on the
  primary runtime.

## Remedy direction (routed, not claimed)

- **Tower lane (owner):** restore a minimal read plane — at minimum
  `github.list_prs` honoring an explicit `repo` arg (R66's silent-target
  lesson) — or an alias layer that keeps legacy dotted names resolving during
  transition waves.
- **Repo lane (follow-up solver dispatch, pre-authorized by this finding):**
  make the three loop fallbacks name-tolerant — probe tools/list once per
  run (or try snake_case then dotted) instead of hard-coding one spelling,
  so the next rename wave degrades to a no-op instead of a blackout. Test
  fixtures for both spellings; never embed the live successor token in
  fixture strings (pass-4/22 standard).

## Never-do (বাংলা)

- এই ফাইন্ডিং থেকে এই সাইকেলে কোনো কোড এডিট হবে না — স্কাউট রোলের চুক্তি;
  রেমেডি solver-dispatch লেনে যাবে।
- টাওয়ার-মালিকের ডিপ্লয় সিদ্ধান্ত নিয়ে দাবি নয় — প্লেন-ক্যানসাস যাচাইকৃত,
  কারণ tower-lane; এজেন্ট শুধু রিপোর্ট করবে।
- ডুপ্লিকেট রাডার নয় — R87-R96 ইস্যু/PR-সাইডে খরচ হয়েছে; এই পাসের read-time-এ
  (c8e8e2d7) ইনডেক্সে তাদের কোনো রো ছিল না, রিবেজ-টাইমে পিয়ার-পাসগুলো রো+পয়েন্টার
  রো+পয়েন্টার ল্যান্ড করে ফেলেছে — same-window race, first-registration-wins অনুযায়ী
  এই পাস শুধু নিজের R100 রো রেজিস্টার করে; পয়েন্টার ও পরবর্তী দুই নম্বর
  গার্ড-ফিক্সচারে ব্লকড।

## Provenance

R66 (silent target) → R67 (rename migration) → R78 (board fallback) → R78-mirror
(PR-audit revive, #3602) → this (plane removal + second name wave, live 2026-10-31).
Freeness verified per the #2392 predicate at read time AND re-verified at the
rebase tip (4b4f1080): tracked-tree word-boundary scan zero hits for R100 over
md/py/yml/json; last-400 origin/main subjects zero hits; open-queue capture zero
citations; the two numbers between the registered block and this lane stay
fixture-blocked in the guard + its test (synthetic strings from their non-live
era). Pointer advance: read-time value past the fixture-blocked pair to the
next free number R101.
