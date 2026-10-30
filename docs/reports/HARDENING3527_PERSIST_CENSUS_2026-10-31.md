# Hardening #3527 — implicit persist-credentials census tripwire landed (2026-10-31, cycle 5)

- **Agent:** GLM Agent 13 (Job 486783) — claim `GRANT_NEW` on #3527 at 16:16:12Z
- **Task:** task-3527 (AUDIT, P4, task-auditor) — deliver the agent-serviceable half of
  the filer's ranked fix list: the machine-tracked zero-recurrence tripwire
- **Refs:** #3527 #3517 #3518 #1776 — **not closes** (see §4)

## 1. What landed

1. `scripts/ci/workflow_hardening_census_guard.py` extended:
   - new first-class countable class **`implicit_persist_true`**: checkout sites whose
     step block carries no explicit `persist-credentials: false` — the checkout default
     persists the job `GITHUB_TOKEN` into runner git config (#3527 exposure class);
   - **block-aware attribution** (mapping-key indent, bullet-shift aware): an explicit
     `persist-credentials: false` on an unrelated step can no longer mask a bare
     checkout (self-test `3527-masking`), and the core repo's `- name:` → `uses:` →
     `with:` layout is correctly attributed (self-test `core-layout`);
   - `--files` mode: census an explicit file list, enabling cross-repo surfaces
     (e.g. a monorepo workflow fetched out-of-band) without touching `.github/`;
   - `--baseline-out` mode: emit a freezable flat profile baseline;
   - classify() upgraded to `persist_ok = implicit_persist_true == 0` (strictly
     clearer than the old global subtraction);
   - self-test extended to 9 cases, all PASS.
2. `scripts/ci/baselines/workflow_hardening_census_open.json` — **frozen baseline** of
   the open repo's own `.github` surface (profile frozen 2026-10-31, `#3527`): any
   change to the surface (growth OR hardening) now trips `SURFACE_DRIFT` exit 3 until
   consciously re-baselined with dated evidence. Zero-recurrence for the open repo.

## 2. First-hand verification of the finding (U3, live main, tower read)

`Supremeai-bd/supremeai` `.github/workflows/ops-maintenance.yml` (102,028 B live read
this cycle via tower `github.read_file`), censused with the extended guard:

| class | count | filer's claim |
| --- | --- | --- |
| uses_total | 66 | — |
| checkout_sites | **23** | 23 ✓ |
| persist_false (global) | 5 | 5 ✓ |
| **implicit_persist_true** | **18** | 18 ✓ (now structurally attributed) |
| tag_pinned | 47 | — |
| template_injection | 0 | — |

The 5 explicit `persist-credentials: false` are each verified on a checkout step
(L517/L1593/L1701/L1738/L1782); the remaining **18 bare checkouts** persist the job
token. The filer's body correctly flagged its own #3517 count as "per-file marker
hits, value unverified" — this receipt upgrades that to the first structural,
block-attributed verification.

## 3. Why the guard needed the new class (not just subtraction)

The filer's 18 = 23 − 5 (global arithmetic). That happens to be right here, but it is
not block-safe in general: a `persist-credentials: false` on any unrelated step would
mask a bare checkout under global subtraction. The new `3527-masking` self-test pins
that failure mode; `implicit_persist_true` counts structurally, per step block.

## 4. Governance: why Refs, not Closes

The finding's exposure — 18 persisted job tokens on the core monorepo's maintenance
surface — is **not remediated** by this tripwire; the remediation (explicit
`persist-credentials: false` on 18 sites, baseline for the core surface, PAT-fallback
inversion) is owner-lane `.github/` work agents cannot perform. Closing #3527 on
merge would falsify the board while the finding is live (the #2916 closure-integrity
class). The issue stays open until the owner lands the .github/ fix; the guard then
gives the owner a one-command verification (`--files` census + re-baseline).

## 5. বাংলা ব্যাখ্যা (Bangla explanation)

#3527-এর মূল অভিযোগ: core monorepo-র `ops-maintenance.yml`-এ ২৩টি checkout-এর
মধ্যে ১৮টিতে `persist-credentials: false` নেই — ফলে job-এর `GITHUB_TOKEN` runner-এর
git config-এ persist হয়ে থাকে। আমি (১) guard-এ নতুন `implicit_persist_true` ক্লাস
যোগ করেছি যা স্টেপ-ব্লক ধরে গাঠনিকভাবে গোনে (আগের সরল বিয়োগ পদ্ধতিতে ভুল masking
হতে পারত — সেটির জন্য self-test আছে), (২) `--files` ও `--baseline-out` মোড যোগ করেছি,
(৩) open repo-র নিজস্ব surface-এর baseline freeze করেছি — এখন এই ধরনের দেনা বাড়লে
বা কমলে দুটোই যান্ত্রিকভাবে ধরা পড়বে (exit 3)। tower দিয়ে core-এর লাইভ ফাইল পড়ে
ফাইলারের সংখ্যা (২৩/৫/১৮) নিজে যাচাই করেছি। উন্নয়নের মাঝে আমার নিজের স্ক্যানারেই
একটি indent-বাগ ধরা পড়ে ঠিক করেছি — সেই regression-টিই এখন self-test-এ আটকে আছে।
`.github/` সংশোধন owner-লেনের কাজ, তাই issue খোলা থাকবে — এই PR শুধু tripwire
নামায়, তাই `Closes` নয়, `Refs`।

## 6. Rollback

git revert-safe: one modified script + one new baseline JSON + one receipt; zero
`.github/`, zero code-path outside scripts/ci; revert the commit to fully undo.
