#!/bin/bash
# acquire_lane_slot.sh — CAS branch-slot acquisition CLI (15-min rule)
# =====================================================================
# Implements issue #1860 (M2) · Plan: docs/plans/ROLE_BASED_AGENT_ECOSYSTEM_PLAN.md §2
# Registry: docs/master_docs/AGENT_SLOT_REGISTRY.yaml v2.1 `acquisition_rules`
#
# Usage:
#   acquire_lane_slot.sh --pool <planner|coder|pr-helper|ci|browser|platform> \
#                        --agent-id <id> [--max 100] [--dry-run]
#
# Exit codes:
#   0 = branch acquired (branch name on stdout as `ACQUIRED_BRANCH=<name>`)
#   1 = pool exhausted (all numeric slots hot), or --dry-run found nothing
#   2 = invalid args / missing dependencies / hostile environment
#
# Algorithm (CAS, race-safe — plan §2.2): walk `<pool>-n` from n=1 upward —
#   1. branch missing       → POST /git/refs (atomic). 201 = WON; 422 = raced → next n
#   2. last commit ≤ 15 min → ACTIVE (heartbeat says occupied) → next n
#   3. last commit > 15 min → STALE → CAS claim commit (plain push whose parent
#      is the observed remote tip; rejected non-fast-forward = raced) → on win,
#      reset branch to origin/main with --force-with-lease (lease = the exact
#      SHA we CAS'd onto, plan §2.4) so zero previous-agent commits leak → WON.
# Exhausted all `--max` numbers → exit 1.
#
# Heartbeat (plan §2.2, issue #1860 requirement): activity IS the latest commit
# timestamp on the branch. Every push — the claim commit and every work commit —
# refreshes it. The normal work cadence is the keepalive; no separate keepalive
# process exists or is needed.
#
# CAS guarantees (why there is no race window):
#   - `POST /git/refs` is atomic on GitHub (422 if the ref already exists)
#   - a plain push of a commit whose parent is the observed remote tip is
#     rejected non-fast-forward if anyone advanced the ref after our read
#   - `--force-with-lease` re-arms the CAS for the reset push: if the ref moved
#     between our claim and the reset, the push aborts and we walk to the next n
#   Losers simply walk to the next number — no state exists where two agents
#   both believe they own the same branch.
#
# Testability note: GitHub interactions go through `gh`, git interactions
# through `git`. Both are overridable via ACQUIRE_GH_CMD / ACQUIRE_GIT_CMD so
# tests (tests/test_acquire_lane_slot.py) can inject fakes without network.
#
# Deliberate deviation from plan §2.4 (documented): the stale-branch reset is
# done worktree-free — `push --force-with-lease` from the current checkout —
# instead of `git checkout P-n && git reset --hard`. The remote outcome is
# identical (branch == origin/main, zero previous-agent commits) but the
# current worktree of the agent is never disrupted (LESSONS_LEARNED: a tool
# that mutates the caller's checkout breaks any concurrently active session).

set -euo pipefail

# ─── Overridable commands (test hooks) ───────────────────────────────────
GH_CMD="${ACQUIRE_GH_CMD:-gh}"
GIT_CMD="${ACQUIRE_GIT_CMD:-git}"

# ─── Tunables (env-overridable for tests; production defaults per registry) ──
STALENESS_MINUTES="${ACQUIRE_STALENESS_MINUTES:-15}"   # registry: staleness_window_minutes
NUMERIC_BOUND="${ACQUIRE_NUMERIC_BOUND:-100}"          # registry: numeric_bound

POOL=""
AGENT_ID=""
MAX_N="${NUMERIC_BOUND}"
DRY_RUN=0

log() { echo "[$(date -u +%H:%M:%S)] $*" >&2; }
die() { log "❌ $*"; exit 2; }

usage() {
  sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

# ─── Args ─────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    --pool)     POOL="${2:-}"; shift 2 ;;
    --agent-id) AGENT_ID="${2:-}"; shift 2 ;;
    --max)      MAX_N="${2:-}"; shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    --help|-h)  usage ;;
    *)          die "unknown argument: $1 (see --help)" ;;
  esac
done

[ -n "$POOL" ]     || die "--pool is required (planner|coder|pr-helper|ci|browser|platform)"
[ -n "$AGENT_ID" ] || die "--agent-id is required (e.g. supremeai-coder-1-bot)"

case "$POOL" in
  planner|coder|pr-helper|ci|browser|platform) ;;  # canonical lanes — AGENTS.md §1
  *) die "invalid pool '$POOL' (must be one of: planner coder pr-helper ci browser platform)" ;;
esac

: "${GH_TOKEN:?GH_TOKEN env var required (gh CLI auth for API calls)}"
: "${GH_REPO:?GH_REPO env var required (e.g. SaifulHaqueNiloy/supremeai)}"
OWNER="${GH_REPO%%/*}"
REPO="${GH_REPO#*/}"
command -v "$GH_CMD"  >/dev/null 2>&1 || die "gh command '$GH_CMD' not found"
command -v "$GIT_CMD" >/dev/null 2>&1 || die "git command '$GIT_CMD' not found"
command -v python3    >/dev/null 2>&1 || die "python3 not found (needed for ISO-date parsing)"

# ─── GitHub API helpers (test-mockable via $GH_CMD) ───────────────────────
BRANCH_SHA=""       # observed remote tip (probe side-channel)
LAST_COMMIT_DATE="" # observed latest commit ISO date (probe side-channel)

# Probe one branch. Return 0 = exists (fills BRANCH_SHA + LAST_COMMIT_DATE),
# return 1 = missing (HTTP 404). Any other API failure aborts: a network blip
# must never be misread as "missing" — the subsequent create would 422 anyway,
# but honest errors beat silent flailing.
branch_exists() {
  local b="$1" out
  if ! out=$("$GH_CMD" api "repos/$OWNER/$REPO/branches/$b" \
        --jq '.commit.sha + " " + (.commit.commit.committer.date // .commit.commit.author.date)' 2>&1); then
    if grep -q "HTTP 404" <<<"$out"; then
      return 1
    fi
    die "API error while probing '$b': $out"
  fi
  BRANCH_SHA="${out%% *}"
  LAST_COMMIT_DATE="${out#* }"
  return 0
}

create_ref() {
  # Atomic create — the CAS primitive for FREE slots. On failure fills
  # CREATE_ERR with gh's stderr so the caller can classify 422-races.
  # (`out=$(...) || rc=$?` captures the exit code while errexit stays ON —
  #  toggling errexit off is itself a Guardian-Lite dangerous-shell finding.)
  local b="$1" sha="$2" rc=0
  CREATE_ERR=""
  CREATE_ERR=$("$GH_CMD" api -X POST "repos/$OWNER/$REPO/git/refs" \
        -f "ref=refs/heads/$b" -f "sha=$sha" 2>&1) || rc=$?
  return "$rc"
}

# ─── Git helpers (test-mockable via $GIT_CMD) ─────────────────────────────
origin_main_head() {
  # Plan §2.2: sha = origin/main HEAD. Prefer the local remote-tracking ref
  # (works offline after `git fetch origin`), fall back to the API.
  local sha
  if sha=$("$GIT_CMD" rev-parse origin/main 2>/dev/null); then
    echo "$sha"
  else
    "$GH_CMD" api "repos/$OWNER/$REPO/commits/main" --jq '.sha'
  fi
}

require_local_object() {
  # commit-tree/push operate on the local object store — fail honestly with a
  # fix instruction instead of a cryptic git error mid-CAS.
  local sha="$1"
  if ! "$GIT_CMD" cat-file -e "${sha}^{commit}" 2>/dev/null; then
    die "commit $sha not in local object store — run 'git fetch origin' and retry"
  fi
}

commit_age_minutes() {
  # ISO-8601 → minutes since commit (python3: TZ/locale-deterministic).
  python3 - "$1" <<'PY'
import sys, datetime
iso = sys.argv[1].strip()
try:
    dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
except ValueError:
    sys.stderr.write(f"unparseable commit date: {iso!r}\n")
    sys.exit(1)
age = datetime.datetime.now(datetime.timezone.utc) - dt
print(int(age.total_seconds() // 60))
PY
}

cas_claim_stale() {
  # STALE takeover (plan §2.2): empty claim commit on top of the observed
  # remote tip, pushed plain — GitHub rejects it non-fast-forward if anyone
  # advanced the ref since our probe. The claim commit is simultaneously the
  # lock, the ownership record, and the first heartbeat. Echoes the CLAIM sha:
  # the ref now sits at our commit, so that is the lease the reset push must
  # pin (--force-with-lease=<ref>:<expect> requires expect == current remote).
  local b="$1" base="$2" claim_msg="$3" new_sha
  require_local_object "$base"
  new_sha=$("$GIT_CMD" commit-tree "$base" -m "$claim_msg") || return 1
  require_local_object "$new_sha"
  "$GIT_CMD" push origin "$new_sha:refs/heads/$b" >/dev/null 2>&1 || return 1
  echo "$new_sha"
}

reset_branch_to_main() {
  # Clean slate (plan §2.4, worktree-free variant): lease pins the reset to
  # the exact SHA we CAS'd onto — if the ref moved after our claim, abort.
  local b="$1" lease="$2" main_sha="$3"
  "$GIT_CMD" push "--force-with-lease=refs/heads/$b:$lease" \
    origin "$main_sha:refs/heads/$b" >/dev/null 2>&1
}

acquire_dry_run() {
  # Walk without any writes: report the first branch we WOULD acquire and why.
  local n b age
  for ((n = 1; n <= MAX_N; n++)); do
    b="${POOL}-${n}"
    if ! branch_exists "$b"; then
      echo "DRY_RUN_WOULD_CREATE=$b"
      return 0
    fi
    age=$(commit_age_minutes "$LAST_COMMIT_DATE")
    if (( age <= STALENESS_MINUTES )); then
      log "  [dry-run] $b ACTIVE (${age}min ≤ ${STALENESS_MINUTES}min heartbeat) — skipping"
      continue
    fi
    echo "DRY_RUN_WOULD_REUSE=$b"
    return 0
  done
  return 1
}

# ─── Main CAS walk ────────────────────────────────────────────────────────
CLAIM_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if (( DRY_RUN )); then
  if acquire_dry_run; then exit 0; fi
  log "❌ dry-run: pool '$POOL' exhausted (all $MAX_N slots hot) — nothing to acquire"
  exit 1
fi

MAIN_SHA="$(origin_main_head)"
require_local_object "$MAIN_SHA"

n=1
while (( n <= MAX_N )); do
  b="${POOL}-${n}"
  log "🔍 probing $b …"

  if ! branch_exists "$b"; then
    # FREE slot → atomic create. 201 wins; 422 = raced a concurrent creator.
    log "  $b missing — atomic create from origin/main ($MAIN_SHA)"
    if create_ref "$b" "$MAIN_SHA"; then
      echo "ACQUIRED_BRANCH=$b"
      log "✅ WON $b (fresh create — atomic ref creation)"
      exit 0
    fi
    if grep -qiE "HTTP 422|already exists" <<<"$CREATE_ERR"; then
      log "  ⚔️ raced on $b (422 — someone created it first) → next slot"
    else
      log "  ⚔️ raced on $b (create rejected: $(head -c 120 <<<"$CREATE_ERR")) → next slot"
    fi
    n=$((n + 1)); continue
  fi

  age=$(commit_age_minutes "$LAST_COMMIT_DATE")
  if (( age <= STALENESS_MINUTES )); then
    log "  $b ACTIVE (last commit ${age}min ago ≤ ${STALENESS_MINUTES}min heartbeat) → next slot"
    n=$((n + 1)); continue
  fi

  # STALE → CAS takeover (base = the exact remote tip observed in the probe).
  log "  $b STALE (${age}min > ${STALENESS_MINUTES}min) — CAS claim-commit push"
  claim_msg="[slot-claim] pool=$POOL agent=$AGENT_ID ts=$CLAIM_TS"
  if LEASE_SHA="$(cas_claim_stale "$b" "$BRANCH_SHA" "$claim_msg")"; then
    log "  ✅ claim commit landed on $b — resetting to origin/main (lease=$LEASE_SHA)"
    if reset_branch_to_main "$b" "$LEASE_SHA" "$MAIN_SHA"; then
      echo "ACQUIRED_BRANCH=$b"
      log "✅ WON $b (stale reuse — clean slate, zero previous-agent commits)"
      exit 0
    fi
    log "  ⚔️ raced on $b (reset lease violated — ref moved after our claim) → next slot"
    n=$((n + 1)); continue
  fi
  log "  ⚔️ raced on $b (claim push rejected non-fast-forward) → next slot"
  n=$((n + 1)); continue
done

log "❌ pool '$POOL' exhausted: all $MAX_N slots hot (heartbeat window ${STALENESS_MINUTES}min)"
exit 1
