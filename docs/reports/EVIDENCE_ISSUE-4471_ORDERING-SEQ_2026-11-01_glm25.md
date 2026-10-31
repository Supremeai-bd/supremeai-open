# #4471 ordering defeat — first end-to-end sequence reproduction (regen-before-gate vacuously satisfies the #1644 freshness gate)

> **Agent:** GLM Agent 25 (Job ID 486821) · **Cycle:** 2026-11-01 02:25+08 · **Dispatch:** `continuous_agent_loop.py` (board 18 rows, loop demoted #4471 per U5 receipt-coverage — this filing is deliberate non-conflicting evidence, not a solver claim).
> **Lane:** report-only evidence for the admin/HITL lane, same pattern as GLM 08's `EVIDENCE_ISSUE-4471_FAILCLOSED_INDEX_2026-11-01_glm08.md` and GLM 13's #4486 audit. Refs #4471 #1630 (bare, no `Closes` line — closure stays with the admin apply).

## What is new here (unique delta, not a re-statement)

GLM 13 (#4486) upgraded the #4471 root cause from "fail-open `|| true`" to an **ordering regression**: the regen at `pipeline.yml:571` runs *before* the #1644 fail-closed freshness gate inside `deploy_preflight_guard.py --step1-syntax` (line 572), so the gate reads a vacuously-fresh index. That upgrade was asserted from code reading plus memory-only `--check` verification. **This file turns the assertion into a five-step mechanical sequence run against live main `889da7c`** — the reproduction nobody had executed end-to-end.

## The five-step sequence (all run locally on tip `889da7c`, tree restored clean afterwards)

| Step | Action (CI mapping) | Result | Exit |
|---|---|---|---|
| A | Append probe line to `scripts/ops/_INDEX.md` (simulates a PR carrying a stale index) | index now stale | — |
| B | Run the guard **directly**, i.e. what a correctly-wired gate would do | `[Step 1: Syntax & Lint] FAIL ... index: STALE ... differs from the regenerated index (559 live scripts found)` | **1** |
| C | Run `python3 scripts/ops/generate_script_index.py` (exactly what `pipeline.yml:571` does every CI run, `|| true` equivalent) | `Wrote .../​_INDEX.md — 559 scripts ... 6 hand section(s) preserved` | 0 |
| D | Run the guard **again from the same stale start** (exactly what `pipeline.yml:572` does) | `[Step 1: Syntax & Lint] PASS: All files compiled cleanly with 0 syntax errors` — **false positive** | **0** |
| E | `git checkout -- scripts/ops/_INDEX.md`; baseline guard re-run | tree clean, `PASS`, exit 0 (main healthy, zero residue) | 0 |

**Reading:** the same stale starting point fails the gate when the gate is reached directly (B, exit 1) and passes it when CI's own line 571 regenerates the runner copy first (D, exit 0). The stale committed `_INDEX.md` lands. That is the defeat, mechanically, not by inference.

## Gate-location facts (first-hand, backing GLM 13's claim)

- The #1644/#1630 fail-closed gate exists and is healthy: `scripts/ci/deploy_preflight_guard.py:62` `def _script_index_freshness()` — step B proves it fires correctly when actually reached with a stale tree.
- Its own docstring states the wiring hole in first person (line 65): *"The index advertises a `--check` CI gate that was never wired anywhere"* — the gate was built, the regen ahead of it makes it read a self-healed copy. Ordering is the whole bug.
- Therefore GLM 08's one-line swap (`|| true` → `--check`) cures the class, not just the instance: `--check` is memory-only (no write), verified independently in my previous cycle (fresh main exit 0 / artificial stale exit 1 / restore exit 0), so no regeneration can pre-empt the gate and B-style failure becomes the CI outcome for stale PRs.

## Scope & boundary

- Zero code touched; single docs file under `docs/reports/` (non-protected lane). No claim taken; `latestClaim` untouched; #4272 and the admin-lane patch are other parties' work and are not re-solved here (U3/U5 respected).
- This is the fourth independent confirmation on #4471 (GLM 09 discovery → GLM 08 apply-ready patch → GLM 13 ordering upgrade → GLM 25 sequence proof) and the only end-to-end one; admin apply remains the sole remaining step.

## Never-do

- No `Closes`/`Fixes` line: the hole stays open until an admin applies the line-571 swap (false-closure #2211/#2225 family).
- No repeat of the instance-level regen PR wave: instances #4463/#4468 already raced; this class ends only at CI (root-cause mandate).
- No local working-tree residue: sequence E restored the tree; the only durable artifact is this file.

---

**বাংলা (GLM Agent 25):** #4471-এর ordering-defeat দাবিটি (GLM 13, #4486) আমি প্রথমবার পাঁচ-ধাপে যান্ত্রিকভাবে প্রমাণ করলাম: stale index নিয়ে guard সরাসরি চালালে **FAIL (exit 1)**, কিন্তু CI-র ৫৭১-নং লাইনের regen আগে চালালে একই stale শুরুতে guard **পাস করে ফেলে (exit 0, মিথ্যা ইতিবাচক)** — অর্থাৎ gate ঠিকই আছে, ভাঙা হলো ক্রম (regen গেটের আগে রানার-কপি সুস্থ করে ফেলে)। Gate-এর অবস্থান প্রথম-হাতে নিশ্চিত: `deploy_preflight_guard.py:62`, যার নিজের docstring-ই স্বীকার করে গেটটি "কোথাও wire করা হয়নি"। তাই GLM 08-এর এক-লাইন সোয়াপ (`|| true` → `--check`, memory-only) শ্রেণিটাই বন্ধ করে — regen আর গেটকে আগে-পৌঁছে-শুধিয়ে দিতে পারবে না। প্রমাণ-শৃঙ্খল এখন চার-সদস্যের (আবিষ্কার → apply-ready প্যাচ → ordering আপগ্রেড → সিকোয়েন্স-প্রমাণ); এখন শুধু admin-এর প্রয়োগ বাকি। গাছ শূন্য-অবশিষ্ট, কোনো claim নেই, closure admin-এর।
