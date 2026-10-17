#!/usr/bin/env bash
# prune_merged_branches.sh — post-merge head-branch housekeeping for Supremeai-bd/supremeai-open
#
# Bridge-able slice of issue #578 (branch-cleanup): the repository setting
# delete_branch_on_merge and the .github/workflows/landing.yml post-merge fallback
# are operator/admin lane (protected path + admin API). This script is the
# maintainable one-time / periodic cleanup routine they can run with credentials.
#
# Behavior:
#   - DRY RUN by default: prints the branches that WOULD be deleted and exits 0.
#   - --execute: actually deletes each listed ref via the GitHub API (gh CLI),
#     one timeout-wrapped call per branch; a single failure never stops the batch
#     but is counted and reflected in the exit code (fail-closed summary).
#   - Safety rails (fail-closed): only refs under contributor/ or bridge/ prefixes
#     that are fully merged into the base branch are ever considered; main and the
#     base branch itself are never deletable; every branch name is strictly
#     validated before it touches an API path.
#
# Usage:
#   REMOTE=origin BASE=main ./prune_merged_branches.sh            # dry run
#   REMOTE=origin BASE=main ./prune_merged_branches.sh --execute  # real deletion

set -euo pipefail

REMOTE="${REMOTE:-origin}"
BASE="${BASE:-main}"
EXECUTE=0
[ "${1:-}" = "--execute" ] && EXECUTE=1

# Every outbound call is timeout-wrapped (cross-platform guard doctrine: no
# subprocess/IO call without an explicit timeout).
API_TIMEOUT_SECS="${API_TIMEOUT_SECS:-30}"

# Fail-closed input validation for anything that will be interpolated into an
# API path or a shell argument. Refusal is loud, never silent.
safe_ref() {
    case "$1" in
        ''|*[!A-Za-z0-9._/-]*|..) return 1 ;;
    esac
    return 0
}

# The base branch must exist on the remote before any decision is made.
git rev-parse --verify --quiet "refs/remotes/${REMOTE}/${BASE}" >/dev/null || {
    echo "prune: base branch ${REMOTE}/${BASE} not found - nothing to do" >&2
    exit 1
}

# Fully-merged remote branches under the cleanup prefixes only.
MERGED="$(git branch -r --merged "refs/remotes/${REMOTE}/${BASE}" \
    | sed "s#^ *${REMOTE}/##" \
    | grep -E '^(contributor|bridge)/' || true)"

if [ -z "${MERGED}" ]; then
    echo "prune: no merged contributor/* or bridge/* branches found - nothing to clean"
    exit 0
fi

DELETED=0
FAILED=0
SKIPPED=0

while IFS= read -r branch; do
    [ -z "$branch" ] && continue
    if ! safe_ref "$branch"; then
        echo "prune: SKIP (unsafe ref name): $branch" >&2
        SKIPPED=$((SKIPPED + 1))
        continue
    fi
    if [ "$EXECUTE" -eq 1 ]; then
        OWNER_REPO="$(git remote get-url "$REMOTE" | sed -E 's#.*[:/]([^/]+/[^/.]+)(\.git)?$#\1#')"
        if timeout "$API_TIMEOUT_SECS" \
            gh api -X DELETE "repos/${OWNER_REPO}/git/refs/heads/$branch" \
            >/dev/null 2>&1
        then
            echo "prune: deleted $branch"
            DELETED=$((DELETED + 1))
        else
            echo "prune: FAILED to delete $branch (kept; inspect manually)" >&2
            FAILED=$((FAILED + 1))
        fi
    else
        echo "prune: would delete $branch"
        DELETED=$((DELETED + 1))
    fi
done <<EOF
$MERGED
EOF

echo "prune: summary - considered: $((DELETED + FAILED + SKIPPED)), action: ${EXECUTE:+deleted}${EXECUTE:-would-delete} $DELETED, failed: $FAILED, skipped-unsafe: $SKIPPED"
[ "$FAILED" -eq 0 ] || exit 1
exit 0
