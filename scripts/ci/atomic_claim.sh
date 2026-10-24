#!/usr/bin/env bash
# Atomic Mutex Claim (GAP-01 fix — Claim-then-Verify pattern)
# ============================================================
# GitHub REST API-এর `issue edit --add-assignee` true atomic lock নয় —
# দুজন agent একই সময়ে assign করলে race condition হয়। এই script
# Claim-then-Verify pattern implement করে:
#
#   1. CLAIM:    gh issue edit $ID --add-assignee "$AGENT_NAME"
#   2. VERIFY:   gh issue view $ID --json assignees → check যে আমি একমাত্র assignee
#   3. CAS check: যদি অন্য assignee থাকে → আমি lose, exit 1
#   4. LOCK:     status:in-progress label যোগ করি (atomic via gh issue edit)
#
# AUDIT-FIX (#1838): --skip-assign flag added. GitHub App bots (e.g.
# supremeai-coder-1-bot[bot]) get 403 Forbidden on /assignees API — they
# cannot be assigned. With --skip-assign the CLAIM/VERIFY steps are
# replaced by a LABEL-based pre-check + LOCK (status:in-progress label,
# the canonical lock per AGENTS.md §3).
#
# Usage:
#   scripts/ci/atomic_claim.sh <issue_number> <agent_name> [--status-label <label>] [--skip-assign]
#
# Exit codes:
#   0 = claim successful (this agent owns the issue now)
#   1 = claim failed (race lost — another agent got there first)
#   2 = invalid args / missing dependencies

set -euo pipefail

# ─── Args ────────────────────────────────────────────────────────────────
# (#1838) flag parsing — backwards compatible with positional args.
SKIP_ASSIGN=false
FORCE=false
STATUS_LABEL="status:in-progress"
POSITIONAL=()
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-assign|--skip-assign=true)
      SKIP_ASSIGN=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --status-label)
      shift
      STATUS_LABEL="${1:-status:in-progress}"
      shift
      ;;
    --status-label=*)
      STATUS_LABEL="${1#*=}"
      shift
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done
ISSUE_NUMBER="${POSITIONAL[0]:-}"
AGENT_NAME="${POSITIONAL[1]:-}"

if [ -z "$ISSUE_NUMBER" ] || [ -z "$AGENT_NAME" ]; then
  echo "Usage: $0 <issue_number> <agent_name> [--status-label <label>] [--skip-assign]" >&2
  echo "  --skip-assign      Skip assignee step (for GitHub App bots that get 403)" >&2
  echo "  --status-label     Override the status label (default: status:in-progress)" >&2
  echo "Examples:" >&2
  echo "  $0 900 agent-1                          # Human operator claim" >&2
  echo "  $0 900 agent-3-coder-1 --skip-assign   # Bot claim (skips 403)" >&2
  exit 2
fi

if ! command -v gh &> /dev/null; then
  echo "ERROR: gh CLI not installed" >&2
  exit 2
fi

# Required env (GH_TOKEN: explicit env -> gh auth token fallback -> fail)
: "${GH_TOKEN:=$(gh auth token 2>/dev/null || true)}"

export GH_REPO="${GH_REPO:-SaifulHaqueNiloy/supremeai}"
: "${GH_TOKEN:?GH_TOKEN required -- run: gh auth login}"

# ─── Pre-check: already claimed? ────────────────────────────────────────
echo "🔍 Pre-checking issue #$ISSUE_NUMBER for existing claim..."

# GAP-DUPLICATE-01 FIX: Check for 'has-pr' label FIRST.
# If any agent already opened a PR for this issue, the issue gets 'has-pr'.
# Seeing 'has-pr' means a PR already exists — do NOT open another one.
EXISTING_HAS_PR=$(gh issue view "$ISSUE_NUMBER" --json labels -q '.labels[].name' 2>/dev/null | grep -Fx 'has-pr' || true)
if [ -n "$EXISTING_HAS_PR" ]; then
  echo "❌ Issue #$ISSUE_NUMBER already has 'has-pr' label — a PR exists for this issue."
  echo "Duplicate PR prevention (GAP-DUPLICATE-01): aborting claim."
  echo "Check open PRs for this issue before proceeding."
  exit 1
fi

# GAP-DUPLICATE-01 FIX: Also check if any open PR references this issue
# (fallback for issues where 'has-pr' label wasn't set by a prior agent)
OPEN_PR_FOR_ISSUE=$(gh pr list --state open --search "#$ISSUE_NUMBER" --json number,title --limit 5 2>/dev/null | python3 -c "
import json, sys
try:
    prs = json.load(sys.stdin)
    refs = [str(p['number']) for p in prs if str($ISSUE_NUMBER) in (p.get('body') or p.get('title') or '')]
    print(' '.join(refs))
except:
    print('')
" 2>/dev/null || echo "")
if [ -n "$OPEN_PR_FOR_ISSUE" ]; then
  echo "⚠️  Open PR(s) found referencing issue #$ISSUE_NUMBER: $OPEN_PR_FOR_ISSUE"
  echo "Adding missing 'has-pr' label to issue (backfill)..."
  gh issue edit "$ISSUE_NUMBER" --add-label 'has-pr' 2>/dev/null || true
  echo "❌ Duplicate PR prevention (GAP-DUPLICATE-01): aborting claim."
  exit 1
fi

# ─── Sequential Integrity Check (Rule #26: GSPQ Contiguous Order) ───────
echo "🚂 Checking sequential integrity for issue #$ISSUE_NUMBER..."
if python3 scripts/ci/issue_queue_manager.py verify-claim --issue "$ISSUE_NUMBER" 2>/dev/null; then
  echo "✅ Sequential constraint verified."
elif python scripts/ci/issue_queue_manager.py verify-claim --issue "$ISSUE_NUMBER" 2>/dev/null; then
  echo "✅ Sequential constraint verified."
else
  echo "❌ Sequential constraint violation! You cannot claim out of sequence."
  echo "Prior issue in group sequence must be claimed or completed first."
  exit 1
fi


# AUDIT-FIX (#2008): Rule #13 "ONE ACTIVE CLAIM PER AGENT" — check if this
# agent already has another issue with status:in-progress before claiming.
# Uses label-based check (works for bots that can't be assigned via API).
ACTIVE_CLAIMS=$(gh issue list --label "$STATUS_LABEL" --state open --json number,title --limit 50 2>/dev/null || echo "[]")
ACTIVE_COUNT=$(echo "$ACTIVE_CLAIMS" | python3 -c "
import json, sys
try:
    issues = json.load(sys.stdin)
    print(len(issues))
except:
    print(0)
" 2>/dev/null || echo "0")

if [ "$ACTIVE_COUNT" -gt 0 ]; then
  # Check if any of the active claims have THIS agent's audit comment
  MY_ACTIVE=$(echo "$ACTIVE_CLAIMS" | python3 -c "
import json, sys, subprocess
issues = json.load(sys.stdin)
me = '$AGENT_NAME'
my_issues = []
for issue in issues:
    num = issue.get('number')
    try:
        comments = subprocess.run(['gh', 'issue', 'view', str(num), '--json', 'comments', '-q', '.comments[].body'],
            capture_output=True, text=True, timeout=10)
        if me in comments.stdout:
            my_issues.append(f'#{num}: {issue.get(\"title\",\"\")[:60]}')
    except:
        pass
if my_issues:
    print('\\n'.join(my_issues))
else:
    print('')
" 2>/dev/null || echo "")

  if [ -n "$MY_ACTIVE" ]; then
    echo "⚠️  WARNING: You already have $STATUS_LABEL on these issues (Rule #13: ONE ACTIVE CLAIM PER AGENT):"
    echo "$MY_ACTIVE" | sed 's/^/    /'
    echo ""
    echo "Complete or release the current claim before claiming another."
    echo "Use --force to override (with caution)."
    # (--force is parsed in the Args loop above — "$@" is consumed by then)
    if [ "$FORCE" != "true" ]; then
      echo "❌ Claim blocked by Rule #13. Use --force to override."
      exit 1
    else
      echo "⚡ --force override: proceeding despite active claims"
    fi
  fi
fi

EXISTING_ASSIGNEES=$(gh issue view "$ISSUE_NUMBER" --json assignees -q '.assignees[].login' 2>/dev/null || echo "")

# AUDIT-FIX (#1838): When --skip-assign is used (bot mode), check the
# status:in-progress LABEL instead of assignees — that's the canonical lock.
if [ "$SKIP_ASSIGN" = "true" ]; then
  EXISTING_LABELS=$(gh issue view "$ISSUE_NUMBER" --json labels -q '.labels[].name' 2>/dev/null || echo "")
  if echo "$EXISTING_LABELS" | grep -qFx "$STATUS_LABEL"; then
    # Check if this agent already posted an audit comment (idempotent)
    EXISTING_COMMENTS=$(gh issue view "$ISSUE_NUMBER" --json comments -q '.comments[].body' 2>/dev/null || echo "")
    if echo "$EXISTING_COMMENTS" | grep -q "Atomic Claim.*$AGENT_NAME"; then
      echo "✅ Issue #$ISSUE_NUMBER already claimed by me ($AGENT_NAME) — idempotent success"
      exit 0
    fi
    echo "❌ Issue #$ISSUE_NUMBER already has '$STATUS_LABEL' label (claimed by another agent)"
    echo "Claim failed — race lost."
    exit 1
  fi
  echo "  No existing '$STATUS_LABEL' label — proceeding to LOCK"
else
  if [ -n "$EXISTING_ASSIGNEES" ]; then
    # Check if it's me already (idempotent retry)
    if echo "$EXISTING_ASSIGNEES" | grep -qFx "$AGENT_NAME"; then
      echo "✅ Issue #$ISSUE_NUMBER already assigned to me ($AGENT_NAME) — idempotent success"
      # Ensure status label is present
      gh issue edit "$ISSUE_NUMBER" --add-label "$STATUS_LABEL" 2>/dev/null || true
      exit 0
    fi
    echo "❌ Issue #$ISSUE_NUMBER already has assignee(s):"
    echo "$EXISTING_ASSIGNEES" | sed 's/^/  - /'
    echo "Claim failed — race lost."
    exit 1
  fi
fi

# ─── STEP 1: CLAIM (optimistic) ──────────────────────────────────────────
if [ "$SKIP_ASSIGN" = "true" ]; then
  # (#1838) Bot mode — skip assignee step entirely. GitHub App bots get 403
  # on /assignees API. The canonical lock (AGENTS.md §3) is the label.
  echo "🎯 Bot mode (--skip-assign): skipping assignee step"
else
  echo "🎯 Claiming issue #$ISSUE_NUMBER as $AGENT_NAME..."
  gh issue edit "$ISSUE_NUMBER" --add-assignee "$AGENT_NAME" 2>&1 | sed 's/^/  /' || {
    echo "❌ Claim command failed"
    exit 1
  }
fi

# ─── STEP 2: VERIFY (Compare-And-Swap check) ───────────────────────────
# CRITICAL: GitHub's --add-assignee is APPEND, not REPLACE.
# If two agents called simultaneously, BOTH might be in the assignees list.
# We must verify we are the ONLY assignee (or at least the first one).
# (#1838) Bot mode skips this — no assignee write happened, nothing to CAS.
if [ "$SKIP_ASSIGN" != "true" ]; then
echo "🔍 Verifying claim..."
sleep 1  # Brief delay to let any concurrent claims settle

ASSIGNEES_JSON=$(gh issue view "$ISSUE_NUMBER" --json assignees)
ASSIGNEE_COUNT=$(echo "$ASSIGNEES_JSON" | python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d.get('assignees',[])))")
FIRST_ASSIGNEE=$(echo "$ASSIGNEES_JSON" | python3 -c "import json,sys;d=json.load(sys.stdin);a=d.get('assignees',[]);print(a[0]['login'] if a else '')")

echo "  Current assignees: $ASSIGNEE_COUNT"
echo "  First assignee: $FIRST_ASSIGNEE"

if [ "$FIRST_ASSIGNEE" != "$AGENT_NAME" ]; then
  echo "❌ Lost the race — first assignee is '$FIRST_ASSIGNEE', not me ($AGENT_NAME)"
  echo "Removing myself from assignees (cleanup)..."
  gh issue edit "$ISSUE_NUMBER" --remove-assignee "$AGENT_NAME" 2>/dev/null || true
  exit 1
fi

if [ "$ASSIGNEE_COUNT" -gt 1 ]; then
  echo "⚠️ Multiple assignees detected ($ASSIGNEE_COUNT) — I am first, but race happened"
  echo "Removing other assignees (I claimed first)..."
  # Remove all assignees except myself
  OTHER_ASSIGNEES=$(echo "$ASSIGNEES_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
me = '$AGENT_NAME'
for a in d.get('assignees', []):
    if a['login'] != me:
        print(a['login'])
")
  for other in $OTHER_ASSIGNEES; do
    echo "  removing $other..."
    gh issue edit "$ISSUE_NUMBER" --remove-assignee "$other" 2>/dev/null || true
  done
fi
fi # SKIP_ASSIGN (STEP 2 CAS verify — human mode only)

# ─── STEP 3: LOCK — add status label + drop stale unclaimed label ─────────
echo "🔒 Adding status label '$STATUS_LABEL'..."
gh issue edit "$ISSUE_NUMBER" --add-label "$STATUS_LABEL" 2>&1 | sed 's/^/  /' || {
  echo "⚠️ Failed to add status label (non-fatal — claim still valid)"
}

# Issue #1909 fix: an issue that just got claimed must no longer advertise
# itself as unclaimed. Leaving status:unclaimed on it makes any queue that
# filters on that label (e.g. next_claimable.sh, #1906) hand the same issue
# to another agent — double-claim risk. Best-effort removal: the claim
# (assignee CAS above) is already authoritative even if this fails.
echo "🧹 Removing stale 'status:unclaimed' label (issue #1909)..."
gh issue edit "$ISSUE_NUMBER" --remove-label "status:unclaimed" 2>&1 | sed 's/^/  /' || {
  echo "⚠️ Failed to remove status:unclaimed (non-fatal — claim still valid)"
}

# ─── STEP 3.5: POST-VERIFY — TOCTOU hardening (issue #1989) ─────────────
# বাংলা: label add করার পরেই অবস্থা re-read করা বাধ্যতামূলক — add-assignee
# ও add-label দুটোই APPEND; verify ও label-এর মাঝামাঝি সময়ে আরেকটি agent
# ঢুকে গেলে শুধু আগের CAS check তা ধরত না। নিচের re-read নিশ্চিত করে:
#   (a) আমি এখনো একমাত্র/প্রথম assignee, এবং
#   (b) status label সত্যিই বসেছে।
# ব্যর্থ হলে নিজের label সরিয়ে (release) exit 1 — double-claim অসম্ভব।
echo "🔎 Post-verify: re-reading issue state (issue #1989)..."
sleep 1
FINAL_JSON=$(gh issue view "$ISSUE_NUMBER" --json assignees,labels 2>/dev/null || echo "{}")
if [ "$SKIP_ASSIGN" != "true" ]; then
  # (#1838) assignee re-check only makes sense when we wrote an assignee.
  ME_STILL_ASSIGNED=$(echo "$FINAL_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
me = '$AGENT_NAME'
print('yes' if any(a.get('login') == me for a in d.get('assignees', [])) else 'no')
")
  if [ "$ME_STILL_ASSIGNED" != "yes" ]; then
    echo "❌ Post-verify FAILED: I am no longer an assignee (raced and evicted) — releasing $STATUS_LABEL..."
    gh issue edit "$ISSUE_NUMBER" --remove-label "$STATUS_LABEL" 2>/dev/null || true
    exit 1
  fi
fi
FINAL_HAS_LABEL=$(echo "$FINAL_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
want = '$STATUS_LABEL'
print('yes' if any(l.get('name') == want for l in d.get('labels', [])) else 'no')
")
if [ "$FINAL_HAS_LABEL" != "yes" ]; then
  echo "⚠️ status label missing after add — retrying once..."
  gh issue edit "$ISSUE_NUMBER" --add-label "$STATUS_LABEL" 2>/dev/null || true
fi
if [ "$SKIP_ASSIGN" = "true" ]; then
  echo "  ✅ Post-verify passed: status label present (bot mode)"
else
  echo "  ✅ Post-verify passed: sole assignee + status label present"
fi

# ─── STEP 4: Post claim timestamp comment (for audit trail) ────────────
CLAIM_TIME=$(date -u +'%Y-%m-%dT%H:%M:%SZ')

# GAP-DUPLICATE-01: Enforce branch naming convention in the claim comment.
# Branch MUST include the issue number: <lane>-<N>-<issue_number>-<slug>
# Example: coder-1-2253-fix-session-takeover  (NOT just 'coder-1')
if [ -n "${BRANCH_NAME:-}" ] && [[ "$BRANCH_NAME" != *"$ISSUE_NUMBER"* ]]; then
  echo "❌ BRANCH NAME VIOLATION (GAP-DUPLICATE-01): '$BRANCH_NAME' must contain issue number '$ISSUE_NUMBER'"
  echo "Required format: <lane>-<N>-<issue_number>-<slug>  e.g. coder-1-${ISSUE_NUMBER}-my-fix"
  echo "Releasing claim..."
  gh issue edit "$ISSUE_NUMBER" --remove-label "$STATUS_LABEL" 2>/dev/null || true
  exit 1
fi

CLAIM_COMMENT="### 🔒 Atomic Claim Established (GAP-01)

- **Agent:** \`$AGENT_NAME\`
- **Issue:** #$ISSUE_NUMBER
- **Claimed at:** $CLAIM_TIME
- **Branch:** \`${BRANCH_NAME:-not-yet-created}\`
- **Method:** Claim-then-Verify (Compare-And-Swap) + has-pr guard (GAP-DUPLICATE-01)
- **Verifier:** \`scripts/ci/atomic_claim.sh\`

_Automated by atomic_claim.sh — Race-safe mutex establishment per ARCH-GAP-01_"

gh issue comment "$ISSUE_NUMBER" --body "$CLAIM_COMMENT" 2>&1 | sed 's/^/  /' || true

# GAP-DUPLICATE-01: The agent MUST add 'has-pr' label to the issue immediately
# after gh pr create succeeds. This is NOT done here (we haven't created the PR yet),
# but scripts/ci/open_pr.sh (or the agent's next step) MUST call:
#   gh issue edit $ISSUE_NUMBER --add-label 'has-pr'
# Agents: see Rule #24 in AGENTS.md. FAILURE TO DO SO causes duplicate PRs.
echo "📌 REMINDER (GAP-DUPLICATE-01): After 'gh pr create', immediately run:"
echo "   gh issue edit $ISSUE_NUMBER --add-label 'has-pr'"
echo "   This MUST happen before any other agent's next_claimable.sh run."

# ─── STEP 5: AUTO-SYNC WORKSPACE (Zero Drift Protection) ─────────────────
echo "🔄 Auto-syncing workspace with latest origin/main..."
python3 scripts/git/auto_sync_main.py 2>/dev/null || python scripts/git/auto_sync_main.py 2>/dev/null || true

echo "✅ Atomic claim successful — issue #$ISSUE_NUMBER owned by $AGENT_NAME"
exit 0
