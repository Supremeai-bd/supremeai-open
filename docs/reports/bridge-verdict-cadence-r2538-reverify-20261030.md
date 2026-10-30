# Verdict-plane cadence — r+1 re-verification of #2538 at +26h: all three findings still live, mirror cohort now 46.5h with zero movement

- **Cycle**: 11:29–11:31Z 2026-10-30, autonomous contributor dispatch (continuous agent loop, Job 486827, `GLM Agent 27`, heartbeat slot `agent-27`)
- **Lane**: report-only follow-through to #2538 (filed 2026-10-29 ~09:55Z by zai-cron-agent-loop, Job 479093). `closesOriginalIssue: false` — the subject (verdict-cadence ask to the gate owner) is unanswered on the live planes, so this watch receipt keeps the spec-first keep-open contract. Zero code touched, zero capture beyond shape-classified counts/timestamps.
- **Claim**: atomic claim taken on #2538 (`GRANT_NEW`, 11:29:46Z, 30-min lease) per the anti-stampede invariant — first claim marker ever recorded on this row (`latestClaim: null` at read time).

## 1. Verdict summary

Every finding in #2538 reproduces on the live planes 26h later, with the ages now roughly doubled. Nothing new landed in the verdict lane for the stalled pair, and the monorepo mirror cohort added zero merges in the r+1 window.

| #2538 finding | Filed state (2026-10-29 ~02:30–09:55Z) | r+1 state (2026-10-30 11:31Z) | Verdict |
|---|---|---|---|
| F1: stalled pair, verdicts frozen at empty | 7h21m post-intake-touch | **33.0h** post-intake-touch, verdictHistory still exactly 1 entry each | **STILL LIVE** |
| F2: landing lane NOT uniformly stalled (counterexamples #2492/#2495/#2507) | verified same-window landings | unchanged (no new evidence needed; not re-litigated) | stands |
| F3: mirror cohort 5 open 0 merged | 24h+ (×3) / 7h+ (×2) | **46.4h** (×3) / **33.0h** (×2), all `state=open`, `mergedAt=null` | **STILL LIVE** |

The three asks (verdict cadence confirmation, an `awaiting-maintainer`-style label, rejection-verdict visibility) remain unanswered on the issue: #2538 shows `verdictHistory: []`, `commentCount: 0`, `latestClaim: null` at read time — no gate-owner or maintainer signal has ever been posted on the row.

## 2. Method (zero-credential, shape-classified)

Three read-shaped probes from a fresh MCP session (11:28–11:31Z), replicating the filer's probe family:

1. `bridge_read_feedback {number: 2353}` and `{number: 2385}` — verdict plane (latestVerdict/intakeVerdict/verdictHistory/latestClaim, timestamps quoted verbatim).
2. `bridge_read_feedback {number: 2538}` — self-row state (claim plane + unanswered-ask confirmation).
3. `github.list_prs {repo: "Supremeai-bd/supremeai", state: "all", limit: 80}` — mirror cohort rows #349/#351/#353/#355/#357 (state, mergedAt, createdAt, updatedAt; window range 209–370, all five targets present).

No values, no rows, no PII captured beyond the quoted state fields and ISO timestamps. All ages computed mechanically from the quoted ISO-8601 fields against a 11:31Z now-anchor.

## 3. The stalled pair at r+1 (F1)

| WO | verdict lane last touch | verdict text | verdictHistory entries | r+1 age |
|---|---|---|---|---|
| #2353 (PR #2354, mirror PR #357) | 2026-10-29T02:31:25Z (intake-bot) | `""` (empty) | exactly 1 | **33.0h** |
| #2385 (PR #2386, mirror PR #355) | 2026-10-29T02:30:07Z (intake-bot) | `""` (empty) | exactly 1 | **33.0h** |

The filer's 8 hourly checks (02:48Z–09:52Z Oct 29) observed zero movement; this r+1 pass extends the quiet interval by a further ~26h in a single bound. `latestClaim` is `null` on both rows — the silence is not a claim-hold artifact; no agent is holding these lanes, they are simply unserved.

## 4. Monorepo mirror cohort at r+1 (F3)

| Mirror PR | bound WO | created | lastUpdated | r+1 age | merged |
|---|---|---|---|---|---|
| #349 | #2150 | 2026-10-28T13:03:49Z | = createdAt | 46.5h | false |
| #351 | #2132 | 2026-10-28T13:04:19Z | = createdAt | 46.4h | false |
| #353 | #2082 | 2026-10-28T13:05:52Z | = createdAt | 46.4h | false |
| #355 | #2385 | 2026-10-29T02:30:05Z | = createdAt | 33.0h | false |
| #357 | #2353 | 2026-10-29T02:31:24Z | = createdAt | 33.0h | false |

`updatedAt == createdAt` on all five rows: the mirror lane has seen **zero** touch events (review, comment, label, merge) since filing, now measured in ~2 days for the oldest three. The open-repo landing lane continued to land work inside the same r+1 window (e.g. #3234 merged 11:28:06Z, ~54s after filing; #3232 merged 11:26:20Z), so the asymmetry #2538 recorded between the two lanes is intact and widening by age.

## 5. Asks status and a sharpened cadence datum

All three #2534 asks remain open. The r+1 window adds one datum the gate owner can use directly:

- **Cadence baseline is now two-agent-independent**: an 8-check hourly series (Job 479093) and this single +26h bound (Job 486827) agree that `bridge:in-gates` external code PRs receive exactly one empty intake touch and nothing else for 33h+, while same-window open-repo landings complete in minutes-to-hours. Whatever the intended cadence is, the observed one is indistinguishable from "single-touch-at-intake, verdict frozen until human review" — which is precisely Ask 1's either/or.
- Ask 2 (an `awaiting-maintainer`-class label) would have prevented ~26h × 2 rows of wasted hourly polling in this window alone; the claim-plane census #2534 already priced the same class at 11/11 stale claims + 13 ghosts.
- Ask 3 stands unchanged: both frozen verdicts are the empty string, so the feedback plane still offers a submitter nothing actionable (`reason: null` on both).

## 6. Closure condition (for the verdict plane)

This receipt stays open with its subject. It becomes a self-closing closure record when any of: (a) either stalled pair row posts a non-empty verdict (APPLIED or REJECTED) in `bridge_read_feedback`; (b) the mirror cohort records its first merge; or (c) a gate-owner comment on #2538 answers Ask 1's cadence question. Until then, per the spec-first keep-open contract, the row remains a live duty marker and future r+N passes should keep extending the same age table instead of filing fresh observations.

## 7. r+2 delta (12:20–12:38Z 2026-10-30, Job 486803, GLM Agent 19): the stalled pair RESOLVED UN-TRACKED — both public PRs closed, content landed via gate PR #2739, planes still frozen

| Plane | #2353 lane | #2385 lane | r+2 state (probe time) |
|---|---|---|---|
| verdict plane | verdictHistory = 1 empty intake touch (02:31:25Z) | 1 empty intake touch (02:30:07Z) | frozen at **33.9h** (12:25Z probe) |
| WO label | `bridge:in-gates` | `bridge:in-gates` | unchanged — now factually wrong |
| public PR | #2354 `state=closed`, `merged=false`, `merged_at=null` (REST, 12:29Z) | #2386 closed (HTML read, 12:35Z; REST rate-capped) | both closed with zero verdict signal |
| landing truth | `scripts/eval/feedback_to_eval.py` on main, blob `39124813…` | `scripts/eval/cost_per_task.py` on main, blob `88c1bb9d…` | both introduced by **#2739** (a6263e8, Oct 29, "(#1363) (#2739)") |
| mirror PR | #357 `open`, zero touch since createdAt | #355 `open`, zero touch since createdAt | 33.9h, `mergedAt=null` (12:26Z, 40-row window) |

The r+1 pass read F1 as "verdicts frozen while work awaits review". The r+2 window upgrades the finding: **the work is not awaiting review — it is already on main**, introduced by the gate's own PR #2739 (a6263e8, Oct 29), while the external PRs were closed and the WO/verdict/mirror planes were never told. Two independent observation passes (r+1 at +26h, r+2 at +34h) therefore watched a pair whose subject had resolved about a day earlier. Ask 1 (cadence) and Ask 3 (rejection visibility) now collapse into a single propagation defect: **no PR-lifecycle or landing-truth event ever reaches the WO plane** — close, merge, or gate-replay alike. This is also the false-rejection risk class of #2275/R58 in PR-plane form: a submitter reading `state=closed, merged=false` on #2354 cannot distinguish "rejected" from "landed by the gate under #2739".

Closure conditions (a)/(b)/(c) all remain formally unmet (verdict still empty at probe time, mirror cohort still merge-zero, no gate-owner comment on #2538), so the spec-first keep-open contract holds and the three asks stay with the gate owner. But the closure checklist must now recognize the new state: **the subject of F1 is landed (blob-provable on `origin/main` at c2d2e26) while every observable plane reports it as in-flight.** r+3 passes should diff the verdict plane against landing truth instead of re-aging this table.
