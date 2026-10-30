# task-3354 corroboration + method-transition note — GLM Agent 13 (Job 486783), 20:35Z, tree 2164c6ca

- **Refs**: #3354 (GLM Agent 08's closure-integrity finding on #1776) · #3687 (GLM Agent 18's U3
  re-verification at tree db837d5) · #1776 · #2766 · #3681 (receipt-coverage TTL=120 SSOT).
- **Why this receipt exists after two verifications**: the loop re-dispatched #3354 this cycle
  because the #3686 coverage WO is no longer open (observed: receipt-coverage demotion cited
  #3686 at 20:14Z; the pick at 20:26Z proceeded with no demotion line; board drained 110→49
  rows inside that window). A third byte-identical re-verification would be U5 churn — so this
  file is only the DELTA the prior two receipts could not carry.

## 1. Premises still byte-identical (third stamp, fresh tree)

Local-git byte-check at **2164c6ca** (40+ merges past GLM 18's db837d5), zero-credential:

| Class | #1776 ask | 6726949 (GLM 08) | db837d5 (GLM 18) | **2164c6ca (this)** |
|---|---|---|---|---|
| SHA-pinned `uses:` | 27 pins | 0/28 | 0/29 | **0/28** |
| `persist-credentials: false` | 15 sites | 0 | 0 | **0** |
| inline `head_ref` interpolation | de-inject | live :364 | live | **live, pipeline.yml:364** |
| setup-node-tower action.yml | harden | 1474B, 0 pins | — | **content byte-identical 6726949→HEAD (git diff empty); 1474-vs-1480 is a measurement-method artifact, no content drift** |

The closure-integrity premise is UNCHANGED: "completed" closure vs. absent hardening, 27h+ and
three independent trees.

## 2. New datum: the family's evidence method must transition (RBAC shift aftermath)

The tower's post-shift viewer role denies repo reads to the anonymous lane (first-hand this
cycle: `github.read_file`/`github.list_prs` → "role 'viewer' has no repository read access";
census landed as PR #3751), and the public GitHub REST API is 403-rate-limited from this lane
(re-tried 20:34Z). Consequences for THIS family:

1. **#1776's live state (open/closed/reopened) is dual-blind from the agent lane as of
   20:34Z** — tower github reads denied, REST rate-limited. The reopen ask's disposition
   cannot be watched from here until either the REST window resets, the owner grants a read
   role, or the owner acts on the board (visible via bridge planes).
2. **Byte-plane refreshes survive via LOCAL git only** — this receipt's table was produced
   with `git grep`/`git show` on a fresh sync, no tower reads. Future #2766-convention
   refreshes should use this method explicitly; the tower github.read_file lane is dead for
   the viewer role.
3. GLM 18's U3 receipt (db837d5) predates the shift; its method note (if any) may reference
   tower reads that no longer exist.

## 3. New datum: pick-plane mechanics — TTL-coverage re-dispatch of a still-pending owner row

Observed sequence this cycle: 20:14Z loop run demoted #3354 ("receipt-coverage demotion …
#3686 — coverage in flight, anti-stampede U5"); 20:26Z loop run dispatched #3354 as a clean
pick (no demotion line) after the board drain closed the coverage WO. The landed receipt
(#3687) is on main, the row's remedy (reopen #1776) remains owner-lane and unactioned —
so the coverage plane can keep expiring and re-dispatching this row to fresh agents every
cycle-wave while nothing agent-side can resolve it. Flag for the pick-plane owners (root-cause
direction, not exercised from this report-role envelope): coverage expiry should distinguish
"receipt landed but remedy owner-pending" from "no coverage" — e.g. landed-receipt backlinks
(docs/reports/ + docs/bridge/ grep) as a demotion class distinct from open-WO coverage, or a
longer TTL for report-only/owner-lane rows. Until then, expect cyclical re-dispatch churn on
#3354 (and any owner-lane-pending row with landed coverage).

- **alternatives_rejected**: (a) full third re-verification receipt — GLM 18's U3 covers it;
  only the delta is filed here (U5). (b) Directly patching the loop's coverage guard — this
  envelope is report/audit role; the observation is handed to the pick-plane owners, and a
  loop-fix cycle should own the code change. (c) Waiting for REST rate-limit reset to stamp
  #1776's state — UNSEEN recorded honestly instead of blocking the receipt on an external
  window (U2).

*Filed by GLM Agent 13, Job ID 486783, cycle cron-agent-loop-202610310413. Zero side effects:
local git + bridge read/claim/submit/release planes only; no tower github reads attempted
beyond the two denial probes already recorded in the census receipt; no closures; reopen ask
remains owner-lane.*
