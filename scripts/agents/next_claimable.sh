#!/usr/bin/env bash
# next_claimable.sh — the priority-ordered claim queue for your lane.
# ============================================================================
# Implements docs/agents/ISSUE_PRIORITY_POLICY.md (founder directive):
#   claim order = priority DESC (P0-critical > P1-high > P2-medium > P3-low),
#   then oldest first (createdAt ASC). Missing priority label = P3-low
#   (unlabeled issues never jump the queue).
#
# Usage:
#   ./scripts/agents/next_claimable.sh <lane> [limit]
#     lane:  planner | coder | ci | pr-helper | browser | platform
#     limit: max rows to show (default 10)
#
#   GH_TOKEN must be set (or use an authenticated gh CLI).
#
# Output: the lane's unclaimed issues in claim order + a ready-to-paste
#         atomic claim command for the top issue.
# ============================================================================
set -euo pipefail

LANE="${1:-}"
LIMIT="${2:-10}"

if [ -z "$LANE" ]; then
  echo "Usage: ./scripts/agents/next_claimable.sh <lane> [limit]" >&2
  echo "  lane: planner | coder | ci | pr-helper | browser | platform" >&2
  exit 1
fi

export GH_TOKEN="${GH_TOKEN:-$(gh auth token 2>/dev/null || true)}"

# Resolve the gh binary once (CI: /usr/bin/gh; some dev shells: ~/bin/gh).
GH_BIN="$(command -v gh || true)"
if [ -z "$GH_BIN" ] && [ -x "$HOME/bin/gh" ]; then GH_BIN="$HOME/bin/gh"; fi
if [ -z "$GH_BIN" ]; then
  echo "error: gh CLI not found (install github cli or put it on PATH)" >&2
  exit 1
fi
export GH_BIN

python3 - "$LANE" "$LIMIT" <<'PY'
import json, os, subprocess, sys

lane, limit = sys.argv[1], int(sys.argv[2])
repo = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")

RANK = {"P0-critical": 0, "P1-high": 1, "P2-medium": 2, "P3-low": 3}

def gh_list(extra_labels):
    cmd = [os.environ.get("GH_BIN", "gh"), "issue", "list", "--repo", repo, "--state", "open",
           "--limit", "400", "--json", "number,title,labels,createdAt"]
    for lb in extra_labels:
        cmd += ["--label", lb]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"gh error: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return json.loads(r.stdout or "[]")

def labels_of(i):
    return [l["name"] for l in i["labels"]]

# Claimable universe (#1997 alignment): open, NOT in-progress, NOT a ledger.
# `status:planned` and `status:unclaimed` BOTH mean "awaiting a claim"
# (auditor-filed work carries planned; auto-filed blockers carry unclaimed) —
# excluding planned would hide freshly-triaged P0/P1 work from every lane.
_all = gh_list([])
claimable = [i for i in _all
             if "status:in-progress" not in labels_of(i)
             and "type:ledger" not in labels_of(i)
             and "PRIORITY-QUEUE-LEDGER" not in i.get("title", "")]

# Lane-matched issues (explicit handoff) + generic pool (no handoff label at all).
lane_issues = [i for i in claimable if f"handoff:{lane}" in labels_of(i)]
lane_ids = {i["number"] for i in lane_issues}
generic = [i for i in claimable
           if i["number"] not in lane_ids
           and not any(n.startswith("handoff:") for n in labels_of(i))]

def prio(i):
    ps = [l["name"] for l in i["labels"] if l["name"] in RANK]
    return min(ps, key=lambda p: RANK[p]) if ps else "P3-low"

def sort_key(match):
    rank, created = match
    return (rank, created)

rows = []
for i in lane_issues:
    rows.append((RANK[prio(i)], i["createdAt"], prio(i), i, "lane"))
for i in generic:
    rows.append((RANK[prio(i)], i["createdAt"], prio(i), i, "generic"))
rows.sort(key=lambda r: (r[0], r[1]))

if not rows:
    print(f"No unclaimed issues for lane '{lane}'.")
    print("Never idle — check adjacent lanes' backlogs with the auditor before sitting silent.")
    sys.exit(0)

print(f"Next claimable for lane '{lane}' (priority order — ISSUE_PRIORITY_POLICY.md)\n")
print(f"  {'PRIORITY':<12} {'#':<6} {'CREATED':<11} {'POOL':<8} TITLE")
for rank, created, p, i, pool in rows[:limit]:
    marker = "  <-- CLAIM THIS" if (rank, created) == (rows[0][0], rows[0][1]) and i["number"] == rows[0][3]["number"] else ""
    print(f"  {p:<12} {i['number']:<6} {i['createdAt'][:10]:<11} {pool:<8} {i['title'][:64]}{marker}")

top = rows[0][3]
print(f"\nClaim the top issue:")
print(f"  GH_TOKEN=<token> GH_REPO={repo} ./scripts/ci/atomic_claim.sh {top['number']} <identity>")
print("\nSkipping a priority level requires a stated reason on the skipped issue (policy §2).")
PY
