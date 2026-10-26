# Verdict Executor — install note (#1331)

`.github/` is a protected path on the bridge lane, so this workflow ships as a template.

## Install (admin, one command)
```bash
git mv docs/ci-templates/verdict-executor.yml .github/workflows/verdict-executor.yml
```
No edits needed. Requires two repo secrets: TELEGRAM_ALERTS_BOT_TOKEN, TELEGRAM_ALERTS_CHAT_ID
(notification degrades gracefully when absent).

## What it does
Every 2 hours (and on manual dispatch):
1. Single-flight lease guard (skips if another run is in progress)
2. Scans open PRs for Guardian verdict comments and enacts them:
   - CLOSE_PR → comment + auto-close (Tier-2 auto-lane only)
   - FIX_REGRESSION_THEN_MERGE → spawns a deduplicated `handoff:coder` remediation work order
   - ESCALATE_TO_ADMIN / MERGE_PR → intentionally untouched (human gates)
3. Telegram notification per run (non-fatal on failure)

## Provenance
Parent issue: #1331 (bridge-20261027-guardian-verdict-executor).
Live evidence at filing time: PRs #328/#326 sat open for days despite CLOSE_PR verdicts;
#324's regression verdict spawned no remediation order.
