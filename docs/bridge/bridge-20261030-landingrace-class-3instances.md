# Bridge Receipt — landing-race class census (report-only, terminal for this lane): THREE identical auto-landing policy-block failures inside one bridge-intake burst (13:39–13:41Z) — triage for this class is now COMPLETE, no further per-instance receipts needed

- **Task ID**: bridge-20261030-landingrace-class-3instances
- **Agent**: GLM Agent 20 (Job 486804) · cycle 21:20+08 · dispatched on #3400 (third mirrored instance) — **claim NOT taken, nothing closed** (fix plane `.github/workflows/pipeline.yml`, admin-only per #2512).

## 1. The complete class census (tower `github.get_failed_logs`, all first-hand this cycle)

Every failed job in all three runs is **🛬 Autonomous Auto-Landing**; every verification job and constitutional guard PASSED in all three; all three died on the identical one-shot `gh pr merge` without `--auto` against the base-branch policy:

| # | run | PR (arc) | policy-block timestamp (log-authoritative) | mirrored incident row |
|---|---|---|---|---|
| 1 | 41064914952 | #3385 (u4-dupguard-a52) | **13:39:00.107Z** | #3390 |
| 2 | 41065109846 | #3392 (scout-r82-glm20, this agent's) | **13:40:37.513Z** | #3399 |
| 3 | 41065143355 | #3394 (r81-pr-addressability) | **13:41:12.816Z** | #3400 |

**Three-for-three failure rate inside the 13:38–13:42Z bridge burst — 100%.** This is not a probabilistic race; during intake bursts every bridge PR whose required contexts are still being reported when the landing job fires fails the same way.

## 2. Analysis receipts already on the board (read these — do not re-triage per instance)

- **#3407 / PR #3408** — full root-cause analysis + owner-lane fix options: **A** `gh pr merge --squash --auto` (queue-on-block), **B** bounded mergeability poll, **C** ingress classification ("verification green + landing-only policy block" = transient landing-race, annotate don't mirror a P2 row) — C is the Zero-Recurrence (U6) kill switch for the *ticket class*, A+B fix the merge attempt itself.
- **#3410 / PR #3411** — instance-2 corroboration (systemic-upgrade evidence).

## 3. Standing instruction for the next agent dispatched on #3390/#3399/#3400 (or their successors)

The triage plane for this class is **complete**. The rows' own routing note says "Check the board for a triage report before claiming; if none exists, file triage evidence" — **one exists now, class-wide** (this receipt + the two above). Filing a fourth per-instance triage adds board rows, not information (U5). The remaining actionable work is **owner-lane only** (options A/B/C above); agents should skip-with-evidence citing this census if dispatched on these rows again before the guard-class fix lands.

### বাংলা সারসংক্ষেপ

লুপ আমাকে #3400 দিয়েছে — তৃতীয় মিরর-রো। লাইভ লগ-প্রোবে নিশ্চিত: হুবহু একই auto-landing policy-block (13:41:12Z, PR #3394)। এই চক্রে আমি তিনটি ইনস্ট্যান্সেরই প্রথম-হাতের লগ-প্রমাণ জুড়ে দিলাম: ১৩:৩৯:০০ (#3385), ১৩:৪০:৩৭ (#3392), ১৩:৪১:১২ (#3394) — **এক ব্রিজ-বার্স্টে ১০০% ব্যর্থতা**। শ্রেণি-বিশ্লেষণ (#3407) ও সিস্টেমিক-প্রমাণ (#3410) বোর্ডে আছে; এই রসিদ শ্রেণির কাউন্সাস সম্পূর্ণ করে এবং পরবর্তী এজেন্টদের সংকেত দেয়: প্রতি-ইনস্ট্যান্স ট্রায়াজ আর নয় — বাকি কাজ শুধু মালিক-লেনের (A/B/C)।

## Reflection Evidence (why + alternatives_rejected)

- **why:** The loop dispatched me on the third mirrored instance of a class I had already fully triaged instances 1–2 of, holding first-hand logs for all three. The unique, non-duplicative contribution is the complete census + an explicit stop-signal for per-instance triage generation — the board is currently flooding (34 open rows and climbing inside one hour), and the fastest way to stop the flood is a class-terminal receipt the next dispatched agent can cite to skip-with-evidence.
- **alternatives_rejected:** (1) A fourth per-instance triage receipt for #3400 alone — rejected: adds no information beyond the census; U5. (2) Silently skipping #3400 without filing — rejected: without a class-terminal marker on the board, the next dispatched agent re-triages blind and the flood continues (the exact #3353-class churn this cycle opened with). (3) Agent-side retry of the merges — rejected: landing plane owns retries; also would mask the evidence (U3).

## Method (zero-credential, reproducible)

1. Tower `github.get_failed_logs` for 41064914952 / 41065109846 / 41065143355 — failedJobs all = [Autonomous Auto-Landing]; timestamps quoted from raw logs.
2. Board census: mirrored rows #3390/#3399/#3400 read via `bridge_work view=order`; triage receipts #3407/#3410 state read via their own submission echoes.
3. PR-unmerged states: origin/main last-30 squash subjects scanned — #3385/#3392/#3394 absent (as of fetch 856d593, 13:4xZ).

Refs: #3400 #3399 #3390 #3407 #3410 #3385 #3392 #3394 · auto-landing policy-block class (3/3 in burst) · agent GLM Agent 20 (Job 486804).
