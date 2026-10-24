#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# claim_issue.sh — Claim-then-Verify issue mutex (issue #876 / ARCH-GAP-01 GAP-01)
#
# GitHub issue assignment is NOT Compare-and-Swap (CAS): two agents claiming
# the same issue concurrently can BOTH succeed. This helper implements the
# OPS-06 Safeguard-3 claim-then-verify pattern:
#
#   1. pre-check — refuse if the issue already has an assignee
#   2. claim     — gh issue edit --add-assignee --add-label in-progress
#   3. verify    — re-read assignees; if more than one owner, auto-release
#                  the claim and leave a step-back comment
#
# Usage:  bash .github/scripts/claim_issue.sh <ISSUE_ID> <AGENT_ID>
# Exit:   0 = sole owner (safe to start work)
#         1 = claim lost / already owned (pick another issue)
#         2 = usage or API error
# ---------------------------------------------------------------------------
set -euo pipefail

ISSUE_ID="${1:?usage: claim_issue.sh <ISSUE_ID> <AGENT_ID>}"
AGENT="${2:?usage: claim_issue.sh <ISSUE_ID> <AGENT_ID>}"

# ---- 1. Pre-check: already owned? ------------------------------------------
ASSIGNEES=$(gh issue view "$ISSUE_ID" --json assignees -q '.assignees | length' 2>/dev/null) || {
  echo "::error::cannot read issue #$ISSUE_ID"
  exit 2
}
if [ "$ASSIGNEES" -ne 0 ]; then
  echo "::error::issue #$ISSUE_ID already has $ASSIGNEES assignee(s) — pick another issue"
  exit 1
fi

# ---- 2. Claim ---------------------------------------------------------------
gh issue edit "$ISSUE_ID" --add-assignee "$AGENT" --add-label "in-progress" > /dev/null

# ---- 3. Verify (read-back after an eventual-consistency window) -------------
sleep 3
ASSIGNEES=$(gh issue view "$ISSUE_ID" --json assignees -q '.assignees | length' 2>/dev/null || echo "?")
if [ "$ASSIGNEES" != "1" ]; then
  echo "::error::CONCURRENT CLAIM on #$ISSUE_ID ($ASSIGNEES assignees) — releasing claim and stepping back"
  gh issue edit "$ISSUE_ID" --remove-assignee "$AGENT" > /dev/null 2>&1 || true
  gh issue comment "$ISSUE_ID" \
    --body "⤴️ **$AGENT** released its claim on #$ISSUE_ID — concurrent claim detected by claim-then-verify (OPS-06 Safeguard 3)." \
    > /dev/null 2>&1 || true
  exit 1
fi

echo "✅ issue #$ISSUE_ID claimed by $AGENT (verified sole owner)"
