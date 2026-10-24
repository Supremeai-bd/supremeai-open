#!/usr/bin/env bash
# R2 FIX — CI guard: block `import requests` / `requests.X(` in backend code.
# Excludes: tests/, scripts/, examples/, pyerrorfix/detectors/ (intentional).
#
# IMPROVED: Handles `httpx as requests` aliases — those are OK because httpx
# has async-safe semantics. Only flags REAL `requests` library usage.
#
# Install in CI:
#   - script: scripts/check_no_requests_in_backend.sh
#
# Add as pre-commit hook:
#   ln -s ../../scripts/check_no_requests_in_backend.sh .git/hooks/pre-commit
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# Step 1: Block direct `import requests` (NOT `import httpx as requests`)
OFFENDING_IMPORTS=$(grep -rE "^import requests(\s|$)" \
    --include='*.py' backend/ \
    --exclude-dir=tests --exclude-dir=__pycache__ \
    --exclude-dir=examples --exclude-dir=pyerrorfix \
    | grep -vE "/(test_|scripts/|pyerrorfix)" \
    | cut -d: -f1 | sort -u || true)

if [ -n "$OFFENDING_IMPORTS" ]; then
    echo "❌ BLOCKING: blocking 'requests' library found in backend code (use httpx instead):"
    echo "$OFFENDING_IMPORTS" | sed 's/^/  - /'
    echo ""
    echo "Fix: replace 'import requests' with 'import httpx' and"
    echo "     'requests.get(url, timeout=t)' with 'httpx.Client(timeout=t).get(url)'"
    echo "     or 'httpx.AsyncClient(timeout=t).get(url)' for async."
    exit 1
fi

# Step 2: Block `requests.X(` calls BUT allow `httpx as requests` aliases
# For each file with `requests.X(` calls, check if `requests` is aliased to httpx
BLOCKING_CALLS=""
while IFS= read -r match; do
    [ -z "$match" ] && continue
    file=$(echo "$match" | cut -d: -f1)
    # Check if this file imports httpx with alias `requests`
    if grep -E "^import httpx\s+as\s+requests" "$file" > /dev/null 2>&1; then
        # httpx aliased as requests — OK, skip
        continue
    fi
    # Also skip if `from httpx import ... as requests` pattern (rare)
    if grep -E "^from httpx import .*as requests" "$file" > /dev/null 2>&1; then
        continue
    fi
    BLOCKING_CALLS="$BLOCKING_CALLS\n$match"
done <<< "$(grep -rE "requests\.(get|post|put|delete|patch)\(" \
    --include='*.py' backend/ \
    --exclude-dir=tests --exclude-dir=__pycache__ \
    --exclude-dir=examples --exclude-dir=pyerrorfix \
    | grep -vE "/(test_|scripts/|pyerrorfix)" || true)"

if [ -n "$(echo -e "$BLOCKING_CALLS" | sed '/^$/d')" ]; then
    echo "❌ BLOCKING: blocking 'requests.X(' calls found in backend async routes:"
    echo -e "$BLOCKING_CALLS" | sed '/^$/d' | sed 's/^/  - /'
    echo ""
    echo "Fix: replace 'import requests' with 'import httpx' and"
    echo "     'requests.get(url, timeout=t)' with 'httpx.Client(timeout=t).get(url)'"
    echo "     or 'httpx.AsyncClient(timeout=t).get(url)' for async."
    exit 1
fi

echo "✅ No blocking 'requests' usage in backend code."
exit 0
