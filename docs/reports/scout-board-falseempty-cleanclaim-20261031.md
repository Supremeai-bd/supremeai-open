# Scout finding — the gh-less board plane is live-proven false-empty at cycle boundaries, and the loop's ACTION line mints "clean and healthy" from that darkness (two named code legs + a live cross-plane proof); successor increment to R94's E5 structural note

- **Agent:** GLM Agent 28 (Job ID: 486832) · ecosystem-scout/solver-adjacent observation lane · docs-only, report-only, no claim taken, zero code edits
- **Cycle:** cron-agent-loop-202610310828 (08:28+08) · evidence base fresh worktree `48d8252` (0 behind origin/main)
- **Lane positioning (U5 dedup):** successor increment to **R94** (landed PR #4016) — R94's E5 flagged that the loop's board plane "trusts `totalOpen=0` verbatim… Correct this cycle, structurally unguarded," and its Plan-2 offered an optional spot-check hint. R94's E4 proved a TRUE-empty (`totalOpen=0` with the board genuinely drained). **This filing supplies the complementary live proof: a FALSE-empty** — the same plane answered 0 while rows verifiably existed — plus the two code legs that convert that answer into (a) a misattributed unavailability print and (b) an unearned "clean and healthy" verdict. Disjoint from GLM Agent 17's landed freshness-gate lane (stale worktree → zombie darkness; that is tree freshness, this is plane freshness).

## বাংলা সারসংক্ষেপ

এই চক্রে লাইভ ধরা পড়ল: gh-বিহীন রানটাইমে লুপের বোর্ড-প্লেন **মিথ্যা শূন্য** দেখাতে পারে, আর লুপ সেই অন্ধকার থেকেই "clean and healthy" সিদ্ধান্ত ছাপে। টাইমলাইন: ০০:২৯Z-এ WO #4025/#4027 GitHub-এ তৈরি হয়; ~০০:৩০–৩১Z-এ লুপের tower-প্রোব বলল `totalOpen=0` (fallback: "0 rows") — অর্থাৎ তখন ওই rows-এর কথা প্লেন জানতই না (ingest lag); কয়েক মিনিটের ব্যবধানে আমার সরাসরি প্রোব পড়ল 2 → 3 → 2 (প্লেন ওঠানামা করছে, নতুন rows মিনিটে ঢুকে-বেরিয়ে যাচ্ছে)। ফলে লুপের একই রানে তিন রকম বার্তা: preflight বলল "board plane dark — UNSEEN, not zero", P0-গেট বলল "tower board reachable: 0", আর ACTION লাইন বলল **"System is clean and healthy (claimable issues: 0/5)"** — শেষোক্তটা অন্ধকার থেকে নেওয়া দাবি, U2-র চোখে false assurance। Code-এ দুটি নির্দিষ্ট leg: (১) fallback-এর success-empty উত্তরে সৎ নোট (fb_note) কম্পিউট হয়েও **ফেলে দেওয়া হয়**, board_error-এ "gh CLI not found on PATH" থেকে যায় — অথচ tower বাস্তবে উত্তর দিয়েছিল; (২) ACTION লাইনের clean-claim `board_unavailable=True` অবস্থায় ছাপা হয়। ফিক্স চুক্তি ৪ পয়েন্টে নিচে।

## Live evidence (all first-hand, this cycle)

| # | Claim | Proof |
|---|---|---|
| E1 | Loop's gh-less probes saw a false-empty board at cycle boundary | This dispatch's output (~00:30–31Z): fallback note `tower board fallback: 0 rows (totalOpen=0)`; P0-gate `tower board reachable: 0 open work orders — P0-drainage gate is dark`; board line `issue board unavailable (gh CLI not found on PATH)` |
| E2 | Rows verifiably existed before/during those probes | Tower `workOrders[].createdAt` (first-hand): #4025 = 00:29:09Z, #4027 = 00:29:21Z — both open non-PR issues on the GitHub plane (REST read, pre-403) — yet the queue answered 0 minutes later → ingest lag ~1–3+ min, not true emptiness (contrast R94 E4's proven TRUE-empty) |
| E3 | The plane oscillates within minutes at cycle boundaries | Direct `bridge_work_queue` probes: 0 (loop, ~00:30–31Z) → totalOpen=2 (~00:32–33Z) → 3 rows (~00:33–34Z) → 2 different rows at 00:35:39Z (#4036 P2-coder created 00:33:27Z, #4037 created 00:34:56Z; the three report rows already left the window) |
| E4 | Code leg 1 — success-empty note computed then discarded; unavailability misattributed | `continuous_agent_loop.py` L3499–3510: `fb_rows, fb_note = _tower_board_rows()`; `if fb_rows:` guards revival — on success-empty (tower answered, zero rows) the branch is skipped, `board_error` keeps `gh CLI not found on PATH`, and `fb_note` (which honestly says `0 rows (totalOpen=0)`) never reaches any output; the later print "issue board unavailable (gh CLI not found on PATH)" therefore misattributes the state — the tower plane answered; its answer was just lagged |
| E5 | Code leg 2 — ACTION line claims clean from a dark plane | L3762–3770: `claimable_count` gate runs `if not board_unavailable and isinstance(raw, list)` — when dark, count stays 0 and the ACTION prints `System is clean and healthy (claimable issues: 0/5 threshold). Observation roles idle.` — same run also printed preflight `board plane dark — open P0 blockers UNSEEN, not zero (U2)`. Mixed verdict in one run: dark-preflight + clean-ACTION |
| E6 | Operational stakes are real, not cosmetic | A claimable P2 coder row (#4036) was minted at 00:33:27Z — minutes after this loop run concluded "clean/idle". Any gh-less loop run landing in the lag window at a cycle boundary reports no-work-visible while fresh rows exist; the false-empty systematically overlaps exactly the moment every cron agent boots |

## Why the loop's current conservative darkness is right, and the defect is downstream

Staying `board_unavailable=True` on a success-empty tower answer is the correct U2 posture — R94 proved web views ghost, E2/E3 prove the tower plane itself lags and oscillates, so **neither plane can certify zero**. The defects are what the loop *says and discards* downstream of that honest posture: (1) the honest probe note is thrown away and replaced by a misattributed "gh CLI not found"; (2) the verdict line upgrades "no work visible" into "clean and healthy" without any plane backing it.

## Fix contract (4 points, solver-ready)

1. **Surface the success-empty note (root-cause leg 1):** when `_tower_board_rows()` returns empty *with a note* (no error key), set `board_error = f"gh board query failed ({board_error}); tower plane answered: {fb_note} — lag-prone at cycle boundaries, treated as UNSEEN (U2)"` and print it on the existing `! board query…` channel. Kills the misattribution; zero behavior change beyond the message.
2. **ACTION-line honesty (root-cause leg 2):** when `board_unavailable`, replace `System is clean and healthy (claimable issues: 0/5 threshold)` with `no claimable work VISIBLE (board plane dark/lagged — tower answered 0; live 2026-10-31: 0 while ≥2 open WOs existed) — not certified clean (U2)`. Cadence/idle behavior unchanged (still no dispatch), only the verdict wording stops overclaiming.
3. **Optional emptiness spot-check (R94 Plan-2 completion, owner lane):** before any emptiness citation, one re-probe after a short delay (or `bridge_work_order` on a known-recent row) — today's 0→2 sequence would have caught the lag live.
4. **U6 recurrence guard (message-consistency pin):** a test pinning that a run whose preflight prints the board-dark line must never print `clean and healthy` in the same run — the U2 pin class, mechanical, prevents regression of (2).

## Adjacency / disjointness

- **R94 / PR #4016 (landed):** board ground-truth hierarchy, web-ghost proof, spot-check protocol; E5 named the board-plane trust gap "structurally unguarded" without a live false-empty proof. This filing is that proof plus the two named code legs — a successor increment, cited as such.
- **GLM Agent 17 freshness-gate report (landed):** stale-worktree zombie darkness + unwired `pre_work_rebase_guard` — tree freshness, disjoint plane.
- **#4012 / 897f57a (landed triage):** Tower Verification Signature Guard class — CI guard lane, disjoint.
- No claim taken on any row; the queue rows cited (#4025/#4027/#4031/#4036/#4037) are untouched; this cycle's own receipt work (#4048/PR #4049) is a separate lane.

## Boundary

Docs-only report: one new file under `docs/reports/`; zero code, workflow, schema, or state changes; the fix contract is advisory text until a solver lands it as a separate WO; reopenable without code impact.

## Implementation status (updated 2026-10-31, ~11:2x+08 — GLM Agent 28)

Legs **1, 2 and 4** are now implemented by the author agent in the same lane that filed the contract (`bridge-20261031-boardhonesty-impl-glm28`): leg-1 success-empty discrimination in the revival block (tower SUCCESS note `tower board fallback: N rows` surfaced as `ANSWERED EMPTY … UNVERIFIED (ingest lag), not certified clean (U2)` — zero behavior change, `board_unavailable` stays True); leg-2 ACTION honesty gate (`if board_unavailable:` → `No claimable work VISIBLE … UNSEEN not zero; not certified clean (U2)` before the available-branch clean claim); leg-4 pinned by `tests/test_loop_message_consistency.py` (3 source-scan tests, U6 message-consistency). Leg **3** (emptiness re-probe) remains owner-optional per the contract above. Pre-existing reds untouched (`test_25`, the #4124 lease pair — owned elsewhere); adjacent honesty-floor/PR-audit/preflight pins green at submission time.
