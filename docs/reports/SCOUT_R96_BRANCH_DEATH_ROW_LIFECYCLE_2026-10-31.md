# Scout R96 — Branch-Death Orphaned-Tracking-Row Lifecycle

**Lane:** the fleet's per-branch CI tracking rows outlive their own remediable surface: three automations (watchdog mirror-mint, `cleanup_stale_branches.py` prune, register heal-close) hold disjoint lifecycle assumptions, and their intersection — **a branch died before its failure could heal** — has no mechanical owner. The obligation falls to a timed manual bulk-close wave, and until that wave lands, every loop run pays a live branch-existence probe per ghost candidate and can lose its whole pick window to them.

**Filed by:** GLM Agent 04 (Job ID 486718, slot agent-3), ecosystem-scout role, cycle 09:04+08 2026-10-31. Zero-credential throughout (tower viewer plane + public git transport only). No code edits by the filer (scout mandate).

**Verdict:** `adapt` — the plane is real, live-proven end-to-end within one 90-minute window, and mechanically fixable at the death moment. Owner-lane plans 1–4 below.

**Status:** **open (filed 2026-10-31 ~09:3x+08; stays open until the plans land per the receipt-closure convention — this report does not resolve its own subject).**

---

## 1. The live window (all first-hand, 2026-10-31 01:04–01:36Z, worktree 853be43, 0-behind)

| # | Evidence | Time (Z) | Plane |
|---|----------|----------|-------|
| E1 | Tower board queue: 13 open rows, **10 are watchdog-mirror CI rows** (#4036, #4044, #4047, #4053, #4056, #4060, #4061, #4063, #4064, #4066) — all labeled `P2-medium, status:unclaimed, handoff:coder`, all minted 00:33–01:01Z | ~01:07 | tower `bridge_work` queue |
| E2 | Loop pick pre-verify: **5 consecutive `incident-branch-gone (U3 demotion, #4009 class)` skips** (#4036, #4044, #4047, #4053, #4056), then `top 5 candidates live-claimed — no clean pick this run` — the entire candidate queue was ghost rows | ~01:05 | `continuous_agent_loop.py` run output |
| E3 | Branch census via `git ls-remote origin refs/heads/<branch>`: all 6 distinct head branches of the 10 rows **absent from origin** — `feat/bridge-parent-anchor-subissue`, `fix/workflow-concurrency-and-dispatch-isolation`, `test/verify-end-to-end-satellite-sync`, `test/verify-5-satellites-sync`, `feat/automatic-satellite-sync`, `fix/ci-watchdog-inplace-notice` | ~01:10 | public git transport |
| E4 | Spot-checks via tower single-fetch: #4036, #4044, #4056, #4066 all `closed / completed`, `updatedAt` 01:06:01–01:06:42Z, 1 comment each — **10 rows bulk-closed by hand within ~41 seconds** (the admin/verdict closure tax, paid manually) | ~01:35 | tower `bridge_work` order view |
| E5 | Board post-wave: 2 open rows (a worklog receipt + WO #4072) — the board drained 13 → 2 inside ~30 min, entirely via manual closure + natural reporting | ~01:36 | tower queue |
| E6 | Mint timeline vs fix landing: all 10 rows created **00:33–01:01Z**; #4065 ("watchdog in-place only, no auto-created CI/bridge issues") landed **01:03:45Z** — the wave was entirely **pre-fix residue**; the creation-plane fix is real, and the residue lifecycle is what remained unowned | computed | git + tower |

## 2. The code legs (three automations, zero death-coupling)

1. **The death-dealer — `scripts/ci/cleanup_stale_branches.py`.** Prunes agent/bridge/dev branches (`bridge/`, `fix/`, `feat/`, `test/`, `docs/`, `chore/`, `refactor/`, `perf/`, `revert/`, `agent-`, …) from origin once no open PR carries them. The script contains **zero issue-lifecycle coupling**: its body is `git fetch --prune` + batched `push origin --delete` only — no issue search, no close, no label. Wired **twice** in `.github/workflows/pipeline.yml` (≈L151 and ≈L1123, "Prune Stale Remote Branches"), both call sites already hold a `GH_TOKEN` env (`MERGE_PAT || OPEN_SYNC_PAT || GITHUB_TOKEN`) — the death moment is machine-known and machine-armed, it just notifies nobody.

2. **The immortal-by-construction closer — `scripts/ci/pipeline_failure_register.py`.** `auto_close_on_heal` (policy L106; `close_healed_issue` L837–848) keys on the fingerprint `workflow @ branch` (L159–161): closure fires only when the **same branch produces a green run**. A deleted branch never runs again ⇒ no heal event is even possible ⇒ any row keyed to that branch is open forever until hands intervene. The register's own `watching` route (L497–521) is the honest confession of the same gap: it mints `fix(ci): [watch:branch:X]` P3 rows whose body requires a **human** resurrect-or-cleanup decision, and whose cleanup step is by-hand ("branch delete + এই ইস্যু close (কারণসহ)") — while `cleanup_stale_branches.py` deletes the branch automatically, never telling the watching row.

3. **The minter — `scripts/ci/federation_ci_watchdog.py`.** `mirror_failure()` pre-#4065 minted `fix(ci): [{repo}] {workflow} failed on {branch} (Run #N)` mirrors (`build_issue_title` L197–203) — the E1 rows match this format exactly. Post-#4065, PR-lane is in-place-only and production (main-only, `classify_failure_lane` L70–78) still mints — main never dies, so the watchdog family's future exposure is closed; the register's watching family and any future per-branch minter are not.

4. **The per-run burn — `scripts/agents/continuous_agent_loop.py` L380–393.** The #4009-class demotion probes branch existence **live, per candidate, per run** — correct as a symptom-side skip, structurally wasteful as a substitute for a label the rows never receive; and the pick message itself ("admin/verdict lane owns row closure") encodes a standing human obligation with no mechanical trigger. E2 shows the cost shape: one full pick window consumed by ghosts.

## 3. Root cause (one sentence)

**Branch-death is a first-class lifecycle event for the code plane but a non-event for the tracking plane: the one automation that knows the exact moment and the exact branch names (`cleanup_stale_branches.py`) is not wired to the rows keyed to those branches, so every family re-learns the same accident separately** — the watchdog-mirror family via this 10-row manual wave (E1/E4), the register's watching family by design (human decision required), and the bridge-WO family via a rebase-conflict tripwire that closes rows for the wrong reason (the #3809 case, `docs/reports/CI_4617_U4_DUPLICATE_GUARD_LANDING_DISCONNECT_CONT_2026-10-31.md` §80). This is the Zero-Recurrence Invariant (U6) violated at the family level: the accident class is never learned once, only re-paid per family.

## 4. Fix contract (owner lane; no code edits by the filer)

- **Plan-1 (root-cause, at the death moment):** `cleanup_stale_branches.py` gains an issue-lifecycle step after computing `to_delete`: for each pruned branch, search OPEN incident rows referencing it (watchdog mirror title fragment `failed on {branch} `, body marker `MIRROR_RUN:`, register key `branch:{branch}`) and close them `state_reason: not_planned` with a mechanical comment ("head branch pruned by cleanup_stale_branches; the failure can no longer heal") + label `incident:branch-gone` for the audit trail. The script already holds the exact branch list; both pipeline.yml call sites already hold a token (job needs `issues: write`).
- **Plan-2 (sweep safety net):** the watchdog's scheduled run (or a tiny cron job) closes incident rows whose head branch is absent from origin (`git ls-remote` / API), same label+comment contract — catches branches that die outside the cleanup path (manual deletes, satellite-side GC, renamed heads).
- **Plan-3 (loop economy + admin ergonomics):** once rows carry `incident:branch-gone`, the loop's #4009 demotion short-circuits on the label instead of paying a per-candidate probe, and the admin/verdict bulk-close becomes a one-shot label filter instead of a timed manual wave (E4's 41-second sprint was a human doing what Plan-1 makes free).
- **Plan-4 (U6 pin):** a test asserting the close-on-prune behavior end-to-end (fixture branch list → expected close/label calls), so the coupling cannot silently regress — the same accident must not re-learn itself in a fourth family.

## 5. Adjacency (verified disjoint, honest-degrade faces)

- **#4065** — creation plane (stops future PR-lane mints). This lane is the residue/lifecycle plane; E6's timeline shows the wave pre-dated that fix. Disjoint.
- **#3050 / #4009** — loop-side pick-time demotion (symptom-side skip). This lane is the board-side lifecycle root cause + the death-coupling that removes the need to demote. Disjoint (and complementary: Plan-3 feeds them).
- **#4004** ("close issues on admin pr merge") — closure wired to the admin-merge path only; the abandonment path is unowned. Disjoint trigger plane.
- **R94** — board ground-truth **view** freshness (stale web views vs tower single-fetch). This lane is row **lifecycle** (permanently unactionable rows with fresh views). Disjoint.
- **WO #4072** (GLM Agent 05, 01:11Z) — the drain-to-zero **event record** + subject-dead case study; cited as the event witness. This lane is the **mechanism** (why ghosts form, why closure needs hands, the three-automation intersection). Disjoint subject, same window.
- **R92 / R93 / R95** — heartbeat liveness / anchor routing / relay blind spots. Unrelated.

## 6. Freeness predicate (#2392, three-plane, at fresh main 853be43)

- **Tracked tree:** the guard's own sweep (`radar_index_freshness_guard.sweep`) reports **zero** `R96` citation hits and zero successor-token hits; `--check` green on all invariants (D/E/G) at pointer R96, re-run green at the rebased tip 4bf2b17. (The pass-4/22 fixture tokens inside `tests/test_radar_index_freshness_guard.py` are excluded by the guard's own scan classes — machine-verified, not manually waved.)
- **Last-200 origin/main subjects:** zero `R96` occurrences (`git log --oneline -200 | grep -c` → 0).
- **Open-queue capture:** the 13-row snapshot (~01:07Z) and the 2-row re-capture (~01:36Z) carry zero `R96` titles.

Pointer advance moves next free to **R97** (pin 96→97), and baseline regeneration rides this same change per the #3624 co-obligation. Rule 7 stands: the index is the only counter.

## 7. বাংলা সারসংক্ষেপ (scout summary)

দশটা CI ট্র্যাকিং-ইস্যু এমন ব্রাঞ্চের নাম বহন করছিল যেগুলো `cleanup_stale_branches.py` অরিজিন থেকে মুছে দিয়েছে — অর্থাৎ ব্যর্থতা আর কখনো সারতে পারে না, আর ইস্যু বন্ধও হয় না। লুপ প্রতিটা রানে প্রতিটা প্রার্থীর ব্রাঞ্চ লাইভ প্রোব করে সময় নষ্ট করে (এ রানে পাঁচটা skip, পিক-উইন্ডো শূন্য)। ০১:০৬Z-এ অ্যাডমিন-লেন ৪১ সেকেন্ডে হাতে দশটা বন্ধ করে দিয়েছে — মানুষ যে কাজটা করছে, সেটাই যান্ত্রিক হওয়ার কথা। মূল কারণ: ব্রাঞ্চ-মৃত্যু কোড-প্লেনে ঘটনা, কিন্তু ট্র্যাকিং-প্লেনে অ-ঘটনা। সমাধান-চুক্তি Plan-1: যে স্ক্রিপ্ট ব্রাঞ্চ মোছে, সেই মুহূর্তেই সে সংশ্লিষ্ট খোলা ইস্যু বন্ধ/লেবেল করবে (to_delete তালিকা তার হাতেই আছে, টোকেনও); Plan-2 সুইপ-সেফটি-নেট; Plan-3 লেবেল-শর্ট-সার্কিটে লুপের প্রোব-বার্ন শেষ; Plan-4 U6 পিন-টেস্ট। একই দুর্ঘটনা তিনটি পরিবারে আলাদাভাবে শেখা হচ্ছে — এটাই Zero-Recurrence লঙ্ঘন; একবার শিখলেই হবে।
