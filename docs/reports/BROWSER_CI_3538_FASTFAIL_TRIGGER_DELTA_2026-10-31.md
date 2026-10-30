# Browser CI #3538 (Run 41089438563) — third-agent convergence + two deltas the landed triage #3545 does not carry (2026-10-31)

- **Refs:** #3538 (P0 CI incident) · landed triage #3545 (GLM Agent 23, filed 16:27:16Z, U3 facts) · routing contract: #3538's own Protected-Path note (#2512) · precedent shape: #3474
- **Agent:** GLM Agent 25 · Job 486821 · probes 2026-10-31 00:25–00:55+08 (= 2026-10-30 16:25–16:55Z) · zero-credential tower lane · no claim taken (report-only receipt per the routing note, #3494/#3545 precedent)
- **Verdict:** #3545's U3 facts CONFIRMED (run still failing, no newer run). TWO NEW mechanically-verified deltas: (A) the satellite's live `ci.yml` push trigger is textually malformed — `branches: ain]` instead of `branches: [main]` — a workflow-internal defect (admin-only fix path) that #3545's "the push trigger demonstrably fires" inference missed; (B) the failed job lived ≤ ~18 seconds, which exonerates pytest/ruff by arithmetic and contradicts #3545's "new-commit-breaks-tests" consistency read — the timing fits a fast-fail in the unpinned `pip install` step, and every gate passes on the in-parity local mirror.

**বাংলা সারসংক্ষেপ:** লুপ আমাকে #3538 (browser satellite-এর P0 CI লাল) দিয়েছে। তদন্তের মধ্যেই Agent 23-এর triage (#3545) ল্যান্ড করেছে — U3 তথ্যে আমরা একমত, তাই ডুপ্লিকেট নয়, শুধু দুটি নতুন যান্ত্রিক প্রমাণ জমা দিচ্ছি: (ক) satellite-এর লাইভ ci.yml-এ push trigger **ভাঙা** — `branches: ain]` (হওয়ার কথা `[main]`); GitHub-এ অবৈধ glob fail-open করে বলেই main-এ run ফায়ার করছে — এটি workflow-internal, অর্থাৎ admin-only মেরামত; (খ) পুরো job **≤ ~১৮ সেকেন্ড** বেঁচে ছিল (run তৈরি 16:23:27Z → watchdog-env print 16:23:45Z) — এই সময়ে ৮টি আনপিনড প্যাকেজের pip install + pytest ধরেই না, অর্থাৎ "নতুন কমিটে টেস্ট ভাঙা" পাঠ সময়ের হিসাবেই অসম্ভব; দ্রুত-ব্যর্থতা pip-install ধাপের দিকে ইঙ্গিত করে। লোকাল mirror-এ সব গেট সবুজ (pytest ১৭/১৭, ruff পরিষ্কার, secret-scan পরিষ্কার) এবং mirror-satellite parity প্রমাণিত (requirements.txt blob sha হুবহু এক)।

## 1. Convergence with landed triage #3545 (no re-argument)

Independent probes before I read #3545 reproduced its core: run 41089438563 = push/main/failure @ 16:23:27Z, latest of 19 runs, head sha 4359f15; run 18 green @ 2026-10-27T15:59:16Z; failed job = push-lane `test`; tail-only log snippet, failing line not agent-visible. Read #3545 as primary for those facts.

## 2. Delta A — the push trigger is textually broken (workflow-internal, admin-only)

`github.read_file(Supremeai-bd/supremeai-browser:.github/workflows/ci.yml)` returns the same blob (`324471d…`) at main and at the run commit 4359f15:

```yaml
on:
  push:
    branches: ain]
```

The filter value is the literal string `ain]` — not the intended flow-sequence `[main]`. Pushes to `main` still fire the workflow (all 19 runs are push/main), which requires the invalid glob to fall open at trigger-evaluation time (mechanism labeled inference; the broken filter itself is objective text). Two consequences:

- #3545's "FIRST run in 72.4h, so the push trigger demonstrably fires (NOT the trigger-corruption class)" conflates "the workflow ran" with "the branch filter is intact" — the filter is demonstrably NOT intact.
- The one-line remedy (`branches: [main]`) lives in `.github/workflows/` = protected path: **admin-only per #2512**; no agent patch can land it. Until fixed, the workflow fires on any branch's pushes and the fail-open mask persists.

The same malformed blob is mirrored in the open repo (`browser/.github/workflows/ci.yml`, present since mirror-heal c99d8f5, 2026-10-30T12:37:58Z) — the sync faithfully propagates the defect; fixing the satellite fixes both.

## 3. Delta B — ≤18-second job: pytest/ruff exonerated by arithmetic

Timeline from the run object and the log tail: run created 16:23:27Z; the last timestamped lines are 16:23:45.005–45.641Z (the failure-watchdog step's env group — its presence proves the job failed — then post-job cleanup, then "Cleaning up orphan processes" ends the log). The whole job therefore lived ≲ 18 s. setup-python demonstrably completed (toolcache `Python/3.12.15` paths appear in the watchdog env dump). That leaves ~10 s for install + lint + tests + secret-scan combined: `pip install ruff pytest pytest-asyncio pydantic fastapi httpx beautifulsoup4 loguru` alone cannot complete in that window (typical 25–45 s; no cache configured). So pytest and ruff plausibly never started — #3545's "new-commit-breaks-tests" consistency read fails on arithmetic, not just on my local evidence.

Fast-fail class that fits: an unpinned `pip install` resolving against live PyPI (resolution conflict or transient registry/network error in seconds). Fresh-venv resolution of the exact 8-package line is clean now (00:45+08) — consistent with a bad release published ~16:2xZ and yanked/fixed within hours (labeled hypothesis; unprovable after the fact). Supporting parity evidence: satellite `requirements.txt` at 4359f15 is blob-identical to the open mirror (`f4922342…`), and the full gate suite passes on the mirror — pytest 17 passed / 1 skipped, `ruff --select=E9,F63,F7,F82` clean, all four secret patterns clean. Durable hardening (U6): pin the toolchain install (the repo already proves the pattern — `requirements.txt` is a pinned 23-package closure resolved 2026-10-28) so a bad upstream release cannot re-open this lane.

## 4. Scope discipline and resolution predicate

- No claim taken, no autoclose (`Refs #3538` bare); resolution predicate unchanged from #3545: **next browser main run green**.
- Admin-lane items this receipt adds: (1) restore `branches: [main]` in the satellite ci.yml; (2) pin or retry-guard the unpinned install line. Both are `.github/`/satellite-side — outside the agent envelope.
- Single additive docs file; no code, no protected paths.

## 5. Honest limitations

- Job-level start/end timestamps come from the run object + log tail, not the jobs API (Actions API auth-gated to anonymous probes) — the ≤18 s bound is an upper bound; the failing step is inferred, not read.
- The fail-open glob mechanism is an inference from "runs fired despite the broken filter"; GitHub's exact evaluation behavior for invalid globs is not documented here.
- Transient-release hypothesis cannot be confirmed post-hoc; if the satellite received content beyond my read_file probes, an earlier-step failure remains possible — the arithmetic bound is the robust part.

## 6. Reflection Evidence

- **why:** the loop dispatched a P0 row whose triage landed mid-flight (#3545, filed 4 minutes after the run). Minting a second full triage would be U5 noise; silent walk-away would discard two mechanically-verified deltas — a broken trigger that #3545's own inference actively mis-dismisses, and a timeline that falsifies its primary consistency read. The delta-receipt is the honest completion shape.
- **alternatives_rejected:**
  - full second triage re-arguing U3: duplicate of #3545.
  - claim + satellite code fix: no defect found in satellite content (all gates green on an in-parity mirror), and the identified remedies are admin-only (`branches:` fix, install pinning) — a structurally blocked patch per #2512.
  - new standalone issue for the malformed trigger: the incident row #3538 is the natural carrier (same failure chain); a new row would fragment the record.
