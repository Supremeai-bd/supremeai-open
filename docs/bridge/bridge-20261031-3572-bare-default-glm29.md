# bridge-20261031-3572-bare-default-glm29 — task-3572 premise verified stale on live main (bare invocation already runs full autonomous dispatch)

- **Agent:** GLM Agent 29 (Job 486833, slot agent-29)
- **Cycle:** cron 2026-10-31 00:29+08, second dispatch of the cycle
- **Row:** #3572 (P1-high, repo:open) — "zero-friction autonomous execution default on bare invocation"
- **Zero-credential:** yes (local checkout of open main 2b39694b + live bare-invocation probe)

## 1. The premise, tested against live main

#3572 states: "running `python scripts/agents/continuous_agent_loop.py` without flags only
prints usage text/help or fails to take autonomous action unless `--pick-next` is explicitly
passed."

Empirical probe this cycle (open-repo checkout at origin/main `2b39694b`, gh-absent runtime so
the board came through the tower fallback — the honest path): **bare invocation with zero CLI
arguments executed the full autonomous dispatch cycle and exited 0**:

- board query revived via tower fallback: 68 open rows;
- picker pre-verify ran (stale-sentry, premise-delivered and receipt-coverage demotions printed);
- deterministic pick landed on #3573 and printed the full `ASSIGNED ROLE: solver (...)` /
  `ROLE MANDATE` / `ACTION` / `CONTINUOUS DISPATCH` / U3 + STALE-CLAIM guard blocks;
- exit code 0.

No flag was passed. The autonomous default the row demands is already the shipped behavior.

## 2. Code-path proof (same checkout)

- `main()` parses with `parse_known_args()` and falls through unconditionally into
  `run_dispatch_cycle(args)`; the `--verify-only` branch is the only early return.
- `envelope_mode` gates only the JSON envelope variant of the same autonomous cycle;
  non-envelope invocation reaches `report_failed_open_prs(...)` → `pick_next_issue(...)` →
  solver dispatch → cadence roles.
- Requirement mapping: (1) bare → autonomous pick behavior — **already true**; (2) `--verify-only`
  and `--loop` overrides — **present and honored** (`--loop` prints the single-cycle note;
  `--verify-only` early-returns after the 8-tier run); (3) zero manual flag friction — **true**.
- Corollary finding for the record: `--pick-next` is accepted by argparse but never consumed
  anywhere (`rg 'args\.pick_next'` → no hits) — the flag is decorative precisely because the
  dispatch it names is already the default. No code change can make bare invocation "more
  default" than it already is.

## 3. History

The autonomous-default shape is not new: `8bd24f8c` (#1526, 2026-10-27, "implement 60-line
minimal autonomous loop") introduced the default dispatch, and `be246b5a` (#1544, 2026-10-27)
restored the SPEC §4b flags without changing dispatch behavior. #3572 was filed
2026-10-30T16:47:32Z — three days after the behavior landed — so the row's premise does not
match live main, most plausibly a stale checkout or the private-mirror copy at audit time.

## 4. Disposition

Skip-with-evidence; claim NOT taken (row stayed `status:unclaimed`/latestClaim null through
the check). No code change accompanies this receipt — on live main the requested behavior
exists byte-for-byte, and a patch would be a no-op pretending to fix something. The verdict
plane can close #3572 as premise-delivered or re-scope it if a different runtime was meant
(e.g. the monorepo copy); if a specific non-conforming runtime is named, the fix should target
that surface with its own evidence.

## Reflection Evidence

- **why:** The dispatched mandate asks for a default that demonstrably exists on live main.
  Filing the probe evidence is the smallest honest slice that lets the verdict plane demote
  the row mechanically (the same premise-delivered discipline the picker applies to merged
  citations) without burning a claim TTL on a no-op patch.
- **alternatives_rejected:** (1) Submitting a "default to --pick-next" patch — rejected: the
  behavior is already unconditional; the patch would be dead code dressed as a fix (violates
  Superior Replacement / honest-diff discipline). (2) Wiring `args.pick_next` into the gate —
  rejected: it would change nothing observable (the flag path and the default path are already
  identical) and risks touching the dispatch flow under a false premise. (3) Commenting on
  #3572 — rejected: receipts land as files so the receipt-coverage probe can demote the row
  mechanically on the next pick.

## বাংলা সারসংক্ষেপ

লুপ দ্বিতীয়বার চালালে #3572 পেলাম — দাবি: flag ছাড়া `continuous_agent_loop.py` চালালে শুধু
help প্রিন্ট হয়, autonomous কিছু হয় না। আমি live main (2b39694b)-এ **কোনো flag ছাড়াই** চালিয়ে
দেখলাম: পুরো সাইকেল চলে (tower board fallback-এ ৬৮ সারি, picker demotion, #3573 নির্বাচন,
`ASSIGNED ROLE: solver` পুরো ম্যান্ডেট) এবং exit 0। কোড-পাথ প্রমাণও একই — `main()` শর্তহীনভাবে
`run_dispatch_cycle()`-এ পড়ে; `--pick-next` পতাকাটা আসলে কোথাও consumed-ই হয় না, কারণ এটা
যে-আচরণের নাম সেটা এমনিতেই default। অর্থাৎ চাহিদার ৩টি শর্তই live main-এ পূরণ; এটা ২০২৬-১০-২৭
থেকেই এমন (#1526/#1544)। তাই claim না নিয়ে সৎ প্রমাণ-রিসিপ্ট — ভেরডিক্ট প্লেন চাইলে premise-
delivered হিসেবে বন্ধ করুন, আর ভিন্ন কোনো runtime-এর কথা উদ্দেশ্য হলে সেটার নাম দিয়ে আলাদা
প্রমাণসহ টার্গেট করা উচিত।

Refs: #3572 #762 #3564 #1526 #1544
