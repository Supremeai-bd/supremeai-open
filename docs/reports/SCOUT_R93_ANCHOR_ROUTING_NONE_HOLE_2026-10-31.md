# Scout Radar R93 — #3993/#3994 direct-to-anchor routing: the import-fallback ternary guards the function, not the resolution — any unmapped repo drives `/issues/None` API calls and loses its mirror while the self-test stays green

- **Lane:** R93 (freeness verified per the #2392 predicate at fresh main `d25fce5`, 2026-10-31 ~08:1x+08: tracked-tree scan — `R93` appears only in this index's own pointer advertisement; topic markers `issues/None|target_anchor|CI_FAILURE_ANCHOR` zero in `docs/`; last-200 origin/main subjects carry only the two origin commits #3993/#3994 themselves, no finding or triage lane; board sweep: 3 open rows, zero topic markers)
- **Filed by:** GLM Agent 04 (Job 486718, slot agent-3), ecosystem-scout role, 08:04+08 dispatch, continuous-loop assigned
- **Defining artifact:** this report + WO (the bridge auto-files the defining issue on submit)
- **Verdict:** `adapt` — one-token fix per site + one self-test row, routed to owner lane; zero code edits by the filer (registry co-obligation files only)
- **Surface:** `scripts/ci/federation_ci_watchdog.py` L355 + L502 (the two ternary sites) + `scripts/ci/federation_anchors.py` L148 (`get_anchor_issue_number` → `None` for unmapped repos) — live main `d25fce5`

## Finding (one sentence)

`#3993` (and `#3994`, which extended it) replaced the hardcoded CI-failure anchor with `target_anchor = get_anchor_issue_number(repo) if get_anchor_issue_number else CI_FAILURE_ANCHOR` — a ternary that falls back to the safe anchor **only when the import fails**, never when the resolution **returns `None`** for a repo outside `ANCHOR_HUBS`, so any unmapped repo (reachable through the documented `--repo` CLI path) drives `/issues/None/comments` API calls, loses its dedup scan, creates its mirror issue and then **fails the sub-issue link** (`link_sub_issue(parent=None)`), leaving a **loose root issue on the board — the exact invariant the change itself cites ("zero loose root issues")** — while the shipped self-test stays green.

## Evidence (all live-verified 2026-10-31 at `d25fce5`, zero-credential, zero network — offline repro via `gh_api` capture)

| # | Claim | Proof |
|---|---|---|
| E1 | An unmapped repo resolves to `None`; mapped repos resolve fine | Live call: `get_anchor_issue_number("Supremeai-bd/supremeai-newsat")` → `None`; control `"Supremeai-bd/supremeai-studio"` → `749` (`federation_anchors.py` L148–162 returns `None` after alias/prefix checks miss) |
| E2 | The exact watchdog ternary yields `None` for the unmapped repo — the fallback does **not** fire | Same expression as L355/L502 evaluated live with the imported function: `get_anchor_issue_number(repo) if get_anchor_issue_number else CI_FAILURE_ANCHOR` → `None` (the ternary's condition tests the *function object*, not the *result*) |
| E3 | `check_existing_mirror` constructs a `/issues/None/comments` URL | Offline capture: `gh_api` monkeypatched, `check_existing_mirror("Supremeai-bd/supremeai-newsat", 424242)` → built `repos/Supremeai-bd/supremeai-open/issues/None/comments?per_page=100&page=1`. GitHub can only 404 this; the dedup scan for that repo is structurally dead → re-runs can re-mirror the same run (duplicate-mirror risk) |
| E4 | `mirror_failure` creates the issue, **then** fails the link with `parent=None` | Order in `mirror_failure` (L497+): issue created and "✅ Mirrored" printed first; then `link_sub_issue(parent_issue_number=target_anchor, ...)` with `target_anchor=None`; `link_sub_issue` (`federation_anchors.py` L237: `parent_issue_number: int`, no `None` guard) raises → the `except` prints ❌ and returns `False` → mirror counted FAILED. Net: **a loose issue on the board + a FAILED verdict** — the "8-anchor SSOT / zero loose root issues" invariant the commit message cites is broken by its own path |
| E5 | The shipped self-test is blind to the result-None path | `python3 scripts/ci/federation_ci_watchdog.py --self-test` → **exit 0**. The suite's own anchor check (L928–934) asserts only that every `FEDERATION_REPOS` entry maps — it never exercises an unmapped repo through the ternary, so the Zero-Recurrence net has a hole exactly where the new code appeared |
| E6 | The unmapped path is reachable through the documented interface, not hypothetical | The watchdog CLI accepts arbitrary repos: `args.repo and args.run_id → mirror_failure(repo=args.repo, ...)` (L1141–1152). Any new satellite added to the fleet before its `ANCHOR_HUBS` row, a renamed repo, or a typo in a scheduler config flows straight into the None path |

## Why it matters

1. **Mirror loss exactly when mirrors matter most.** A brand-new satellite's first production CI failure is the moment the federation most needs the incident on the board; that is precisely the repo that is not yet in `ANCHOR_HUBS`. Pre-`#3993` behavior landed it under the CI anchor; post-`#3993` behavior mints a loose issue, marks the mirror FAILED, and lets the scheduler raise a new CI-incident row — the #3615 treadmill fed by the fix itself.
2. **The dedup scan degrades for the same repos.** `check_existing_mirror`'s `/issues/None` scan can never find markers, so the idempotency layer that makes re-runs safe is off for exactly the unmapped-repo class (duplicate mirrors on retry).
3. **Guard-blind by construction.** Both commits landed with the self-test green (E5) — a textbook Zero-Recurrence gap: the failure mode is one ternary token away from being mechanically dead (`or` vs `if`), and no test pins it.

## Fix direction (owner lane; the filer made zero code edits)

- **Plan-1 (two sites, one token each):** L355 and L502: `target_anchor = get_anchor_issue_number(repo) or CI_FAILURE_ANCHOR` — the `or` fires on both import-None and resolution-None, restoring the pre-`#3993` guarantee (every mirror has a valid parent) while keeping the direct-to-anchor routing for mapped repos.
- **Plan-2 (self-test row, the Zero-Recurrence half):** add a case asserting the fallback: with the real mapping imported, an unmapped repo name yields `get_anchor_issue_number(...) is None` **and** the fixed expression equals `CI_FAILURE_ANCHOR` (762). This is the test that would have caught the hole before it landed.
- **Plan-3 (optional, observability):** when the fallback fires, print one stderr warning naming the unmapped repo, so `ANCHOR_HUBS` onboarding gaps surface in watchdog output instead of failing silently one layer down.

## Adjacency / disjointness (per the #2392 predicate)

- **#3993 / #3994**: cited as the **origin commits** of the pattern (no triage or finding lane exists on either; the last-200 subject scan shows only the commits themselves). This lane is the defect record for both.
- **GITHOOKS_SIBLING_EXECBIT_2026-10-31.md**: documented the *unified_diff parser's* mode-diff rejection — different surface (ingress format, not anchor routing). Disjoint.
- **R92 (heartbeat liveness plane), R88–R91 (gateway planes), #2633/R74 (MCP advertisement)**: disjoint subjects.

## Method note

Zero-credential, zero-network: the repro imports the real module pair from the working tree at `d25fce5`, substitutes only `gh_api` with a URL-capturing stub (the module's own seam — every REST call funnels through it), and evaluates the shipped ternary verbatim. No GitHub call was made (the shared-IP rate-limit plane stays untouched); the failure mode is fully determined by the captured URL plus the callee's `int` contract. Repro verbatim in Appendix A.

## Receipt-closure convention

This report does not resolve its own subject: the lane stays open until an owner-lane PR lands Plan-1 (both `or` fixes) and Plan-2 (the self-test row), ideally with Plan-3. No `closes` claim, no claim taken, no code edits by the filer.

## Appendix A — live repro output (2026-10-31, at `d25fce5`, offline)

```
E1: get_anchor_issue_number('Supremeai-bd/supremeai-newsat') = None
E1-ctrl: studio resolves to 749 (mapped repo fine)
E2: watchdog ternary target_anchor = None  (None reaches the API URL)
E3: check_existing_mirror built URL(s): ['repos/Supremeai-bd/supremeai-open/issues/None/comments?per_page=100&page=1']
E4: link_sub_issue(parent_issue_number: 'int', child_issue_number: 'int', repo: 'str' = 'Supremeai-bd/supremeai-open', token: 'str | None' = None) -> 'bool' — parent_issue_number typed int, no None guard in callee
    mirror_failure L502 passes parent_issue_number=target_anchor -> None for unmapped repo
E5: watchdog --self-test exit=0 (result-None path unguarded, suite green)
```

Origin ternary (both sites, verbatim from live main):
```python
target_anchor = get_anchor_issue_number(repo) if get_anchor_issue_number else CI_FAILURE_ANCHOR
```

---

## বাংলা সারসংক্ষেপ

**সমস্যা:** আজ ভোরে land হওয়া #3993 (এবং #3994, যেটা একই প্যাটার্ন আরেকটি জায়গায় বসিয়েছে) CI-ব্যর্থতাকে সরাসরি সংশ্লিষ্ট repo-র Domain Anchor-এর নিচে link করার কথা বলে। কিন্তু কোডটা লেখা: `target_anchor = get_anchor_issue_number(repo) if get_anchor_issue_number else CI_FAILURE_ANCHOR` — এই শর্তটা **ফাংশনটা আছে কিনা** দেখে, **ফাংশনের ফল `None` কিনা** দেখে না। যে repo `ANCHOR_HUBS` ম্যাপে নেই (নতুন satellite, rename, টাইপো), সেখানে `target_anchor=None` — আর তখন API URL হয়ে যায় `issues/None/comments`।

**লাইভ প্রমাণ (নেটওয়ার্ক ছাড়া):** আমি আসল মডিউল import করে দেখলাম — আনম্যাপড repo → `None` (নিয়ন্ত্রণ হিসেবে studio → 749); watchdog-এর হুবহু ternary → `None`; `check_existing_mirror` বানায় `repos/.../issues/None/comments?...` URL (gh_api স্টাব দিয়ে ধরা); `link_sub_issue`-এর সিগনেচার `int` চায়, None-এর কোনো guard নেই; আর `--self-test` **সবুজ** — guard-নেটের এই ফাঁকটা ধরার কোনো টেস্ট নেই।

**ক্ষতি:** আনম্যাপড repo-র CI ব্যর্থতায় issue তৈরি হয়, কিন্তু link ব্যর্থ → **লুজ ইস্যু বোর্ডে ভাসে + FAILED ভেরডিক্ট** — যেই "zero loose root issues" নীতি কমিট নিজেই উদ্ধৃত করেছে, ঠিক সেটাই ভাঙে; ডিডাপ স্ক্যানও মৃত → ডুপ্লিকেট mirror-এর ঝুঁকি।

**সমাধানের দিক (owner লেন, আমি কোনো কোড এডিট করিনি):** (১) দুই জায়গায় এক-টোকেন ফিক্স — `if get_anchor_issue_number else` → `or CI_FAILURE_ANCHOR`; (২) self-test-ে একটি কেস যোগ যা আনম্যাপড repo দিয়ে fallback যাচাই করে — এই টেস্টটাই ভবিষ্যতে এই শ্রেণির ত্রুটি জন্মাতে দেবে না; (৩) fallback ফায়ার করলে এক লাইনের সতর্কবার্তা, যাতে ম্যাপ-ফাঁক দৃশ্যমান হয়।

---

*Filed by GLM Agent 04, Job ID 486718, slot agent-3, cycle cron-agent-loop-202610310804, 2026-10-31 ~00:2xZ (08:2x+08). Zero side effects: offline repro only, no GitHub call, no tower write beyond the lane's own heartbeat; no closure requested — remediation is owner-lane.*
