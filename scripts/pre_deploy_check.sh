#!/usr/bin/env bash
# ============================================================================
# SupremeAI Pre-Deploy Gate
# ----------------------------------------------------------------------------
# Orchestrates the existing verification scripts into one deploy/no-deploy
# decision (see docs/DEPLOYMENT_CHECKLIST.md — sections 1–3 are automated).
#
# Usage:
#   bash scripts/pre_deploy_check.sh            # full gate
#   bash scripts/pre_deploy_check.sh --quick    # skip pytest (slow)
#
# Exit code: 0 = safe to deploy, 1 = DO NOT DEPLOY
# ============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

QUICK=false
[[ "${1:-}" == "--quick" ]] && QUICK=true

PASS=0
FAIL=0
FAILED_STEPS=()

step() {
  local name="$1"; shift
  echo "──────────────────────────────────────────────────────────"
  echo "▶ $name"
  if "$@"; then
    echo "  ✅ PASS"
    PASS=$((PASS + 1))
  else
    echo "  ❌ FAIL"
    FAIL=$((FAIL + 1))
    FAILED_STEPS+=("$name")
  fi
}

echo "══════════════════════════════════════════════════════════"
echo " SupremeAI Pre-Deploy Gate — $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "══════════════════════════════════════════════════════════"

# 1. Syntax: every backend python file must compile
step "Python compile check (backend)" python3 -m compileall -q backend

# 2. Router imports: every api/routes module must import cleanly
step "Router import validation" python3 scripts/ci/validate_router_imports.py --strict

# 3. App boots with all routers mounted (needs runtime deps installed)
step "Boot test (app + routers)" bash scripts/check_app_boots.sh

# 4. No blocking `requests` library in backend
step "No requests-in-backend" bash scripts/check_no_requests_in_backend.sh

# 5. Frontend secrets never committed
step "Frontend secret scan" python3 scripts/ci/check_frontend_secrets.py

# 6. Migration safety (alembic heads + destructive-op diff)
step "Migration safety" python3 scripts/ci/check_migration_safety.py

# 7. Required secrets present (env/Infisical)
step "Required secrets check" python3 scripts/ci/check_required_secrets.py

# 8. Free-tier guardrails (quota/limits config sanity)
step "Free-tier limits check" python3 scripts/ci/check_free_tier_limits.py

# 9. Tests (skippable — CI runs the full matrix anyway)
if [[ "$QUICK" == "true" ]]; then
  echo "──────────────────────────────────────────────────────────"
  echo "▶ Test suite — SKIPPED (--quick)"
else
  step "Backend test suite" bash scripts/ci/run_tests.sh
fi

echo "══════════════════════════════════════════════════════════"
echo " RESULT: $PASS passed, $FAIL failed"
if [[ "$FAIL" -gt 0 ]]; then
  echo ""
  echo " DO NOT DEPLOY. Failed steps:"
  for s in "${FAILED_STEPS[@]}"; do echo "   - $s"; done
  echo "══════════════════════════════════════════════════════════"
  exit 1
fi
echo " ✅ SAFE TO DEPLOY"
echo "══════════════════════════════════════════════════════════"
exit 0
