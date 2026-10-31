# GLM Agent 04 — Worklog (Job ID 486718, slot agent-3)

> In-place-replace / keep-it-small contract (glm22-r2 precedent): durable facts
> only, landed lanes condensed to one table, replaced in place every cycle.
> Full per-lane text lives in the merged receipts, not here.

- **Identity:** GLM Agent 04 · Job 486718 · slot `agent-3` · hourly cron cadence ·
  door = MCP tower handshake (`supremeai-mcp-tower.onrender.com/mcp`) → AGENTS.md
  (5 invariants) → `scripts/agents/continuous_agent_loop.py` dispatch.

## Durable disciplines (earned, mechanical — future cycles must not re-learn)

1. **bridge_submit mechanics:** `summary` ≤ 1000 chars; diff caps 204.8 KB / 30 files;
   tower diff parser accepts **pure unified diffs only** (`diff --git`/`index`/mode/rename
   lines stripped; keep `---`/`+++`/`@@`); `full_file` only for brand-new paths,
   existing paths need `baseSha` CAS pin from `git rev-parse origin/main:<path>`.
2. **Tower surface epochs (live 2026-10-31, post-#4249 admin restore):** roster
   now 158 tools and the `github_*` read family is BACK (underscore forms —
   dotted `github.list_prs` is -32602 again; the wave is BIDIRECTIONAL, so
   every caller must try both spellings — roster gates match both forms,
   wire calls derive the second spelling via `"x.y".replace(".", "_", 1)`).
   A single-spelling roster gate false-darks a live tool (my 16:04+08 find:
   PR-plane stayed "dark" for hours while 10 open PRs were one call away);
   fixed in the loop + pinned by tests. Board/PR truth also via
   `git log origin/main`; list rows camelCase, merged-truth via
   `pull_number` addressability (AGENTS.md Rule 4 — my remedy, #3526).
3. **Liveness planes (R92 subject, still open):** `agent_heartbeat` (redis, 90 s online
   prose / 300 s TTL, rotating account primary→secondary→tertiary) is disjoint from the
   repo-side `agent_identity.py` JSON (600 s/1800 s) and from `slot_status` (registry
   plane — self-assigned slots legitimately "Slot not found", Rule #19 fallback). The
   loop feeds none of them. `agent_status` exposes the live online/stale machine (37 slots).
4. **Radar hygiene:** take the next R-number from `docs/SCOUT_RADAR_INDEX.md` (the SSOT,
   freshness-guarded); re-verify freeness pre-submit (the pass-26 six-recurrence collision
   class is caught by the filer's own re-verification ladder, R95 preamble).
5. **Bare-invocation loop contract (#4097 → #4175):** `continuous_agent_loop.py` takes NO
   CLI flags (--task-envelope/--pick-next/role overrides purged); a cycle is a bare
   `python3 scripts/agents/continuous_agent_loop.py` call. The offline escape hatch is
   env-var-only (`SUPREMEAI_OFFLINE`); the `--offline` flag surface is gone (test_25 governs).

## Landed lanes (all merged on origin/main, first-registration-wins)

| Lane | Subject (one line) | PR |
| - | - | - |
| guard(loop) | sentry TEST-row demotion in dispatch pick (#3371) | #3469 |
| remedy A | AGENTS.md Rule 4 camelCase payload conventions (#3523) | #3526 |
| fix(ci) | #3656 parity-manifest blindspot closed, sentinels v1→v2 | #3658 |
| evidence ×3 | #2974 / #3567 / #3527 live U3 re-verifications | #3359 / #3593 / #3789 |
| census ×4 | R69 codeql-v4, R74 tool census r2, r2360 push-dark, r2567 gate census r4 | #3275 / #3282 / #3290 / #3304 |
| triage ×4 | #3785 + #3851/#3853/#3854 CI trackers, non-repro classifications | #3797 / #3865 / #3867 / #3870 |
| R92 radar | heartbeat liveness contract: 5 windows, 2 disjoint planes, zero mechanical consumers | #3961 / dbf5186a |
| R93 radar | #3993/#3994 anchor-routing result-None hole | #4003 / 4e553bdd |
| R96 radar | branch-death orphaned-tracking-row lifecycle (10/13 open rows) | #4088 / 0bd75aaf |
| worklog mint | keep-it-small identity worklog (this file, r1) | #4101 / e5aaa160 |
| triage P1 | #4124 re-introduced the #3573 time-gate: guard pair red, repro + owner contract | #4125 / 7d6ba3ad |

## Open watch items (owner lanes; no re-file while receipt-covered)

- R92 Plan-1/2 — heartbeat payload self-describing + loop-side ping or lane-alive signal.
- R96 Plan-1..4 — close-on-prune lifecycle + sweep net + label short-circuit + U6 pin.
- R94 board ground-truth protocol paragraph (owner/docs lane).
- PR-plane dark post-RBAC — ROOT-CAUSED & FIXED this cycle (16:04+08): the
  #4249 restore revived the tool under its underscore name; the loop's
  single-spelling roster gate + dotted wire call kept it fake-dark. Gate now
  matches both spellings; both PR probes try in-order; 3 new U6 tests
  (76 passed) + live proof: 10 open PRs visible first call. Revive is
  loop-side, rides my next PR.
- core nightly-RED (P0 #4250) — triaged report-only (7/7 failedJobs =
  scheduled autofix; private-repo `upload-sarif` can never succeed;
  one-line visibility-gate recipe) in
  `docs/reports/TRIAGE_4250_CORE_PRIVATE_SARIF_NIGHTLY_RED_2026-10-31.md`;
  admin lane; the mirror regenerates nightly until Option A lands.
- render-primary `update_failed`: c75's one healthy pass RELAPSED — degraded/update_failed x2, pass 13 (sentry c76, #4206); #3699 boot classes remain owner-lane.
- Blind-ladder class open past #4138's tier-9: 12 red faces invisible to the ladder while --verify-only prints 9/9 PASS (glm19 #4151).
- CVE lanes: js/npm 2-red census re-proven live at 062f8efd (npm: follow-redirects@1.16.1 devtools-audit GHSA-mrwp-f3q8-3g9p; js: 6 pairs) — glm28 OSV-verified owner recipe #4204/#4203 receipt-covers it; pin bumps are maintainer decisions (both guards' own routing), NOT agent-lane work.
- NEW (my 14:04+08 census): py-plane is a pip-audit BLIND LANE — guard runs honest-degradation (#1760 pattern) and skips the audit when pip-audit is absent (CI has no pip-audit), so 2 latent NEW-DRIFT pairs went unseen: core/pyproject.toml:filelock@3.32.7 (20 new ids) + pillow@12.3.0 (17 new ids); osv.dev live-verified the new-id class (10 new GHSAs on filelock, none in baseline). Latent red: test_py_dep_cve_guard::test_live_check_passes_at_landing_head fails wherever pip-audit IS installed. Owner routing: maintainer pin/range bump or admin re-floor (glm28-recipe shape); baseline may never grow; I touched nothing.

## বাংলা সারসংক্ষেপ

স্থায়ী শিক্ষা: bridge_submit-এর তিনটি যান্ত্রিক সীমা, tower-সারফেস নাম-ঢেউয়ের
দ্বিমুখী সত্য (উভয় বানান চেষ্টা বাধ্যতামূলক — এক-বানান গেট জীবিত টুলকেও
মিথ্যা-অন্ধকার দেখায়), তিনটি disjoint liveness plane, আর radar-নম্বর hygiene।
এই চক্রের মূল-কারণ নিরাময়: PR-plane মিথ্যা-অন্ধকার (টুল ফিরেছিল, গেট চিনতে
পারেনি) — লুপ-নিরাময় + ৩টি U6-টেস্ট; এবং সেই উন্মোচনই রাতের-শিফট অন্ধ-লেন
(P0 #4250) প্রকাশ করল: core-এর প্রতি-রাতের লাল = প্রাইভেট-রিপোতে অসম্ভব
SARIF-আপলোড; admin-এক-লাইন-রেসিপিসহ report-only ট্রায়াজ জমা। এই ফাইলই আমার
একমাত্র worklog; পুরনো বিস্তারিত merged receipts-এ আছে, এখানে শুধু সারণি।
প্রতিটি watch item owner-lane-এ receipt-covered — যতক্ষণ না সেটা বদলায়,
re-file করা duplicate হবে।

## Cycle log (append one line, prune on your own cycle per keep-it-small)

- **2026-10-31 11:04→13:04+08 (condensed)** — leasegate arc end-to-end: #4124's
  time-gate regression caught → triage #4125 → glm12 Option A #4138 → pair re-proven
  GREEN (36 passed); worklog r2 landed (#4183).
- **2026-10-31 14:04+08 (condensed)** — py-plane pip-audit blind-lane discovery
  (filelock/pillow NEW-DRIFT, osv-verified, latent red); worklog r3 landed (#4217).
- **2026-10-31 16:04+08** — NEW root cause closed: PR-plane fake-dark — the
  #4249 restore revived `github_list_prs` but the loop's single-spelling gate
  + dotted call kept reporting "roster does not carry"; gate/probes now
  wave-tolerant (76 tests green + live 10-PR proof). Same fix UNTOMBSTONED
  the night-shift blind lane: P0 #4250 root-caused (core private-repo SARIF
  nightly-red, 7/7 job-gated) — report-only triage with admin recipe
  (protected path, U5 dedup vs glm10 #4251/glm09 #4252: they proved the
  access wall, I read past it and named the defect). Loop fix + triage doc
  + worklog r4 (this patch) = three separate PRs.
