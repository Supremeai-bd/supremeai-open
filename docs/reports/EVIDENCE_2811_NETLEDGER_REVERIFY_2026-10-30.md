# EVIDENCE #2811 — net-ledger re-verification: corrections still dominate, escalation NOT triggered; raw snapshot-pair deltas produce false escalation (zero-credential)

- **Date**: 2026-10-30 (live snapshot 12:56Z / 18:56 +08)
- **Agent**: GLM Agent 28, Job ID 486832 (cron-agent-loop-202610302028), dispatched via `continuous_agent_loop.py --loop`
- **Targets**: #2811 (audit:finding, P3-minor, report-only) · family context #3086, #2225/#2597
- **Tools**: `render_service_health` (tower, zero-credential), repo timeline cross-read of `docs/reports/EVIDENCE_3086_BUILDMINUTE_ADJUDICATION_2026-10-30.md`
- **Claim**: none held (report-only evidence submission; no closure requested)

## 1. Headline

Independent re-verification of #2811's "refund-adjusted read" ~16h after its c47 snapshot confirms the finding's core interpretation and adds a methodological receipt the family was missing:

- **Live tower vantage at 12:56Z**: render-primary `monthlyBuildMinutes` **113.5** / `freeLimitRemaining` 386.5; render-worker **124.1** / 375.9; both `freeLimitExhausted: false` (limit 500).
- **Net movement 07:15Z → 12:56Z (5.7h): combined −6.0 min (−1.06 min/h)** — the latest observed movement is again **downward** (primary −4.6, worker −1.4), i.e. a further small correction or near-zero net burn, not resumed depletion.
- **#2811's escalation predicate (corrections stop AND gross burn resumes >3 min/h sustained) is NOT triggered.** #2811's "no urgency" posture stands.
- **Methodological receipt**: a naive snapshot-pair read (c47 21:08Z → live 12:56Z) yields a raw combined delta of **+192.7 min**, which mechanically "triggers" the >3 min/h predicate and would have produced a **false escalation** — the +200.8 combined jump documented in EVIDENCE #3086 (07:08–07:20Z, adjudicated as metering correction with zero build-log rows) is inside that window. This is exactly the failure mode #2811's Impact #2 warns about ("any triage/alert logic treating buildMin as monotonically increasing will misread these adjustments"): non-monotonic corrections invalidate raw pairwise deltas; **net movement must be computed between adjacent observations, with the correction events subtracted out**.

## 2. Timeline (all tower-vantage, combined)

| Point (UTC) | primary buildMin | worker buildMin | Interval | Combined Δ | Note |
|---|---|---|---|---|---|
| c47, 10-29 21:08Z | 20.3 | 24.6 | — | — | #2811's exact dual-account mirror |
| #3086 sweep, 10-30 07:08–07:20Z | 118.1 | 125.5 | 10.1h | **+198.7** | +200.8 jump adjudicated as metering correction (zero build-log rows, positive control clean) |
| This receipt, 10-30 12:56Z | 113.5 | 124.1 | 5.7h | **−6.0** | further small correction / near-zero net burn |

- Naive c47→live pairwise delta: **+192.7** — matches the burn+correction superposition, not burn alone.
- Correction-family observation count since #2811's filing: **4th event class** (c47 dual-account mirror → #3086's +200.8 → this −6.0) — the corrections are neither one-off nor monotone; they occur in both directions and at very different magnitudes, consistent with reconciliation/metering-basis adjustments rather than refunds of specific builds.

## 3. What this changes

1. **#2597's quota trajectory**: the refund-adjusted read #2811 requested is now empirically anchored across three observation points — net depletion is materially lower than gross-delta reads suggest; no urgency derivable from gross burn alone stands.
2. **#3086's residual ask remains live**: the mechanism of the corrections (which Render subsystem credits the minutes; whether failed-build refunds are intended) is still invisible from the tower vantage — admin/HITL lane item, unchanged.
3. **Guard surface**: the #2811 window-class hardening is already landed on `main` (`scripts/ci/render_build_quota_guard.py`, `scripts/ci/render_build_budget_guard.py`, `tests/test_render_build_minute_window.py` — "Witness #2811" battery: month-window sums, cursor pagination, non-truncated windows). Impact #2's automation risk is therefore already remediated for the guard surface; this receipt closes the remaining observation-loop gap by supplying the missing "2nd observation" style data point with an explicit net-rate computation.
4. **Standing watch**: if the next hourly sweep shows sustained positive net movement ≥3 min/h across 2 adjacent observations (after accounting for any correction event), #2811's escalation predicate triggers for real; projected exhaustion at the historical retry-fail rate (~5.5 min/h combined net, per #2811 §6h-net) would then be ≈ 30–35h from 500-limit — still ample for the P1 deploy-plane fix path.

## 4. Method note (for replication)

- `render_service_health {accountId: render-primary|render-worker, serviceId: srv-dau7c9ek1f9s73almn0g | srv-dabm7evqj5pc738jkf30}` at 12:56Z.
- Rate math: interval Δ ÷ wall-clock hours between adjacent snapshots; escalation evaluated on **net** rate with corrections itemized, never on raw pairwise deltas spanning a known correction event.
- Cross-reads: EVIDENCE #3086 (07:08–07:20Z ledger table), #2811 body (c43/c44/c47 event table, 6h net −46.9).
