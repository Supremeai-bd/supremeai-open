# TRIAGE — #4124's "purge version tags" leg broke every skills manifest: 7 red faces in `skills/tests`, absent from every census (glm19 #4151 included), still red at 05dcbe9

- **Lane**: `bridge-20261031-skillsmanifest-versionpurge-glm14` — self-initiated triage, P1-high (7 deterministic reds on main, unowned AND unrecorded; same-commit blast radius as #4125, second half)
- **Agent**: GLM Agent 14 (Job ID 486785) · worktree verified 0-behind at 0f5867e, then 05dcbe9 after mid-cycle pull · zero-credential throughout
- **Trigger**: post-#4151 first-hand full-suite re-verification (U3: never trust a census you didn't run). glm19's landed census says 11F; bare `pytest -q` at the adjacent head returns **18F** — the delta decomposed into exactly 7 skills-suite reds nobody attributes.

## বাংলা সারসংক্ষেপ

`#4124` (a9323f4) শুধু ২টি AST guard ভাঙেনি — একই commit-এর "purge version tags" ধাপ **১৪টি `skills/**/SKILL.md` থেকে `version:` ফ্রন্টম্যাটার লাইন মুছে দিয়েছে**। কিন্তু `skills/registry/manifest_schema.py` L144 `("name", "version", "description")` বাধ্যতামূলক দাবি করে — ফলে `parse_skill_md` প্রতিটি skill-এর জন্য `ManifestError: SKILL.md frontmatter missing 'version'` ছুড়ে দেয় এবং **`skills/tests/`-এর ৭টি টেস্ট লাল** (test_agent_cadence_skill ×২ + test_skills_foundation ProgressiveLoader ×৫)। এগুলো standalone-এও লাল (deterministic, isolation নয়)। glm19-এর সদ্য-landed attribution টেবিলে (#4151) skills row **শূন্য** — তাঁর সেনসাস স্কোপ `tests/`-এ সীমাবদ্ধ ছিল (bare pytest-এ +১৭১ পাসের ডেল্টাই প্রমাণ)। অর্থাৎ #4124-এর blast radius-এর অর্ধেক (guard-pair) #4142 সারিয়েছে, কিন্তু skills-অর্ধ **আজও লাল, মালিকহীন, রেকর্ডহীন**। Fix contract: Option A — a9323f4^ ইতিহাস থেকে `version:` লাইন ফেরত (১৩টি এক-লাইনের যান্ত্রিক সংশোধন); Option B — schema শিথিল (ডিফল্টে প্রত্যাখ্যাত: registry চুক্তি দুর্বল হবে)। সাথে census-স্কোপ ফিক্স: face-runner অবশ্যই `skills/tests` আমলে নেবে।

## Ground truth (reproduced this cycle, first-hand)

`python3 -m pytest skills/tests/test_agent_cadence_skill.py skills/tests/test_skills_foundation.py -q`:

| # | Test | Result |
|---|------|--------|
| S1 | `skills/tests/test_agent_cadence_skill.py::TestAgentCadenceDispatcherSkill::test_progressive_loader_discovers` | FAILED — `ManifestError: … missing 'version'` |
| S2 | `…::test_skill_manifest_parses` | FAILED — same |
| S3-S7 | `skills/tests/test_skills_foundation.py::TestProgressiveLoader::{discover_indexes_reference_skill, load_returns_full_instructions, load_unknown_raises, summaries_are_lightweight, trigger_matching}` | FAILED — same |

- **7 failed, 17 passed in 1.27s — standalone deterministic red** (not an isolation artifact; the class glm19 fixed in #4151 was order-dependent, these are not).
- Reproduced at BOTH heads this cycle: `0f5867e` (cycle-start) and `05dcbe9` (post-pull) — identical 7F/17P.
- Full suite bare `pytest -q` at 05dcbe9: **17F / 2393P / 14S in 87.2s** (at 0f5867e: 18F/2367P; the −1 is glm09's parity red healed by #4159 between the two runs).

## Root-cause chain (three-way evidence)

1. **The purge:** `git show a9323f4 --stat` — #4124's message: "Purges unnecessary version tags across coverage_policy.yaml, service_topology.yaml, agent_cadence.json, **and all 14 skills/**/SKILL.md files**"; diff-stat lists exactly 14 SKILL.md files, each `-1` line.
2. **The contract:** `skills/registry/manifest_schema.py` `parse_skill_md` L144: `for required in ("name", "version", "description")` → `raise ManifestError(f"SKILL.md frontmatter missing {required!r}")`. The registry schema REQUIRES version; the purge removed it from every skill simultaneously.
3. **The survivor count:** today `ls skills/*/SKILL.md | wc -l` = **13**; `rg -c "^version:"` = **0 hits** (the 14th purged path, `skills/examples/echo-greeter/SKILL.md`, is no longer at that path — no matter: every on-disk manifest is non-compliant). `git log -S "version" -- skills/agent-cadence-dispatcher/SKILL.md` → exactly two commits: `c63a788` (#3992, added it) and `a9323f4` (#4124, removed it).

**Causal verdict:** #4124's purge leg is the sole root cause. #3992 shipped the skills package WITH version fields and its tests green; #4124 removed the fields without touching the schema; the tests have been red since. This is the same-commit, second-plane injury: plane 1 (2 AST guards) healed by #4142, verified in #4148 (36 passed); plane 2 (7 manifest reds) untouched and unrecorded until this report.

## Why every census missed it

glm19's #4151 census: 12F/2195P at 35a72f6, post-fix 11F/2196P — **zero skills rows in the attribution table** (`rg "SKILL.md|skills_foundation|ProgressiveLoader|manifest"` over the report: no hits). Bare-pytest pass delta at the adjacent head (2367 vs 2196 = +171) is the skills suite the census never entered. Root cause of the miss = **census scope**: `pytest tests/…` vs bare `pytest` (repo-root discovery includes `skills/tests/`). This is the same blind-ladder class glm28/glm04/glm19 document, one layer deeper: even the fix-it-yourself census inherited the tests/-only scope.

## Fix contract (owner decision; the filer ships zero code edits)

- **Option A (smaller diff, Superior-Replacement-compliant):** restore the `version:` frontmatter line to all 13 SKILL.md files from `a9323f4^` history (mechanical; values already existed — no invention needed). 7 reds go green; registry contract intact; #3992's original state restored.
- **Option B (schema-relax):** make `version` optional in `manifest_schema.py`. Rejected by default: it weakens the registry contract to appease a purge error — the exact anti-pattern the Superior Replacement invariant forbids. Only valid if the founder declares version tags genuinely obsolete in the SKILL plane too (then the schema change must land with the tests rewritten to pin the NEW contract, per glm04's Option-B governance pattern).
- **Paired with either (the actual root cause of the MISS):** the census/face-runner scope must include `skills/tests/` (or run bare `pytest` from repo root). Extends glm19's ladder recommendation with the concrete scope datum: today's ladder-blind surfaces are `tests/test_constitution_freshness.py`, `tests/test_claim_lease_ssot.py`, `tests/test_agent_cadence.py`, `tests/test_script_index_freshness.py` **plus the whole `skills/tests/` tree**.

## Adjacency / disjointness (per the #2392 predicate)

- **glm04 #4125:** same landing (#4124), different plane (2 AST guards in tests/; healed by #4142). This lane does not touch that pair.
- **glm19 #4151:** isolation red fix + 11-red attribution — none of the 11 are skills rows; its census scope is the miss this report corrects. Complementary, not superseding.
- **glm09 #4159:** parity red 12 (test_parity_guard) — different red, healed this window; excluded from my live count.
- **#3992 (skills package):** cited as lineage (the state the purge broke), not re-litigated.
- CI_4617's six older picker reds, R96 branch-death rows, PR-plane dark, sentry cadence planes: untouched.

## Verification (3-tier)

- Tier 1 (reflection): commit-vs-schema-vs-tree three-way read at a9323f4 / 0f5867e / 05dcbe9; `git log -S` lineage for the version field; on-disk frontmatter census (13 files, 0 version lines).
- Tier 2 (boot smoke): `continuous_agent_loop.py` ×3 this cycle — all clean, claimable 0/5, board 7 rows (queued receipts only), no dispatch; P0 gate green.
- Tier 3 (repro): skills pair 7F/17P deterministic at two heads (standalone); full suite 17F/2393P/14S at 05dcbe9, 18F/2367P/14S at 0f5867e; the −1 delta attributed to #4159.

**লাইভ প্রমাণ (নেটওয়ার্ক ছাড়া, zero-credential):** আমি নিজে চালালাম — standalone skills-pair pytest (7F/17P, 1.27s), পূর্ণ suite (17F/2393P), `git show a9323f4 --stat` (১৪ SKILL.md −১ লাইন), `git log -S version` (ঠিক ২ commit: #3992 যোগ, #4124 বাদ), disk census (১৩টি SKILL.md, `version:` শূন্য)।
