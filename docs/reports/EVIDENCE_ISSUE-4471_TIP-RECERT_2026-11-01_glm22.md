# #4471 tip re-certification at 97d813a — class DORMANT on main, defeat live, chain kept tip-current

> **Agent:** GLM Agent 22 (Job ID 486813) · **Cycle:** 2026-11-01 05:22+08 ·
> **Dispatch:** `continuous_agent_loop.py` picked #4471 as highest-priority unclaimed (claimable 1/5) — this is the solver turn for that dispatch.
> **Lane:** report-only evidence, same pattern as GLM 08 (#4483), GLM 05 (#4534), GLM 25 (#4527-family), GLM 14 r28 (#4576). Refs #4471 #1630 #1644 — bare, **no `Closes`/`Fixes` line** (closure stays with the admin apply; false-closure #2211/#2225 family respected).

## What is new here (unique delta, not a re-statement)

Four prior receipts proved the mechanism (ordering defeat, blob replay, apply-ready patch). **None reported the live staleness state of main's own committed index.** This filing adds exactly that, plus re-certifies both proofs at the current tip so the admin acts on fresh evidence.

## Datum A — the class is DORMANT on main right now (first positive/negative state report)

`python3 scripts/ops/generate_script_index.py --check` on clean tip `97d813a`:

```
OK: .../scripts/ops/_INDEX.md is up to date (559 scripts, 6 hand sections).
exit 0
```

The committed `_INDEX.md` is fresh — GLM 20's instance heal (#4463, at tip 5a665fb, 21:26+0600) still holds through ~40 later landings. **Reading: the hole (pipeline.yml:571 `|| true`) is present but no fire is active; urgency is preventive, not incident response** — the next stale-index PR would sail through the placebo gate exactly as the #4450 wave did.

## Datum B — real-incident blob replay re-certified at the new tip

The actual #4450-regressed `_INDEX.md` (66,533 bytes, `git show 7c731bf:scripts/ops/_INDEX.md`) dropped into a throwaway worktree at `97d813a` as the only mutation:

```
STALE: .../_INDEX.md differs from the regenerated index (559 live scripts found).
exit 1
```

The #1644 fail-closed gate (`scripts/ci/deploy_preflight_guard.py:62`) fires correctly when actually reached with the artifact class that really burned the fleet census — now proven at three tips (2f1268c → glm05; 889da7c → glm25; 97d813a → here).

## Datum C — ordering defeat re-certified end-to-end at the new tip

Same worktree, same stale start: step C regen (`python3 scripts/ops/generate_script_index.py`, what line 571 runs every CI pass) → `Wrote ... 559 scripts ... 6 hand section(s) preserved`, exit 0; step D gate re-run (`deploy_preflight_guard.py --step1-syntax`, what line 572 runs) → `[Step 1] PASS: All files compiled cleanly with 0 syntax errors`, **exit 0 — false positive**. Same stale start fails the gate when reached directly (Datum B, exit 1) and passes it when CI's own line 571 heals the runner copy first. Worktree removed afterwards; main tree verified clean (0 residue).

## Solver-turn lifecycle (second on this row)

Per the dispatch contract the remedy lives in `.github/workflows/pipeline.yml` = **protected path** → evidence via bridge, no auto-close. Following the freshest landed precedent (GLM 14 r28, #4576: "NO claim and NO Closes; evidence-only"), **no claim was taken**; GLM 05's claim lifecycle (#4534, GRANT_NEW, released after landing) remains the documented claim precedent. Premise verified first-hand on `origin/main`: line 571 is still `python3 scripts/ops/generate_script_index.py || true` — the swap has NOT been applied (freshness datum for the admin lane).

## Remedy (unchanged, minimal, apply-ready — third tip-fresh confirmation)

One line in the fast-lint step at `pipeline.yml:571`: replace the regen `|| true` with `python3 scripts/ops/generate_script_index.py --check`; `set -euo pipefail` in the same step propagates the exit. `--check` is memory-only (no write — GLM 25's independent verification), so no regen can pre-empt the gate; Datums B+C prove the wired gate blocks the real incident class while Datum A proves the happy path stays green.

## Never-do

- No `Closes`/`Fixes` anywhere; no fork-PR; no `full_file` against `.github/`.
- No repeat of the instance regen wave (#4463/#4468 raced; the class ends only at CI).
- No claim (two dispatch precedents: claim lifecycle done once by GLM 05; evidence-only by GLM 14) — anti-stampede U5.
- No working-tree residue: throwaway worktree removed, main tree clean.

---

**বাংলা (GLM Agent 22):** লুপ এই cycle-এ 4471 আমাকে solver-রোলে দিয়েছে (২৫টি observation-cycle-এর পর প্রথম dispatch)। চারটি আগের রিসিট মেকানিজম প্রমাণ করেছিল, কিন্তু কেউ main-এর নিজের committed index-এর তাৎক্ষণিক অবস্থা জানায়নি — সেই-ই নতুন datum: **class এই মুহূর্তে main-এ DORMANT** (index fresh, #4463 heal টিকে আছে), অর্থাৎ ঝুঁকি preventive, incident-response নয়। পাশাপাশি দুটো প্রমাণ নতুন tip-এ (97d813a) re-certify করলাম: প্রকৃত #4450 blob-এ gate exit 1, আর regen-first ordering সেই-ই stale শুরুতে false-positive PASS — পরাজয়টা এখন তিনটি tip-এ যান্ত্রিকভাবে প্রমাণিত। কন্ট্রাক্ট অনুযায়ী remedy protected path-এ, তাই evidence-only, claim নেই (GLM 14-এর সদ্য-landed প্রেসিডেন্ট অনুসরণ), কোনো Closes নেই — বন্ধ করার সিদ্ধান্ত admin-এর।
