#!/usr/bin/env bash
# STABILIZE — Boot test script
#
# Verifies that the SupremeAI backend app boots cleanly with ALL routers loaded.
# Run this BEFORE every push to main.
#
# Usage: bash scripts/check_app_boots.sh
# Exit code: 0 = success, 1 = failure

set -euo pipefail
cd "$(git rev-parse --show-toplevel)/backend"

echo "════════════════════════════════════════════════════════════════════"
echo "STABILIZE Boot Test — $(date)"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# Check Python version
echo "1. Python version: $(python3 --version)"

# Check critical deps available
echo "2. Critical dependencies:"
for mod in fastapi pydantic sqlalchemy loguru httpx; do
    if python3 -c "import $mod" 2>/dev/null; then
        echo "   ✅ $mod"
    else
        echo "   ❌ $mod MISSING"
        exit 1
    fi
done
echo ""

# Test app boot
echo "3. App boot test:"
BOOT_RESULT=$(python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from core.app import app
    print(f'OK {len(app.routes)}')
except Exception as e:
    print(f'FAIL {type(e).__name__}: {e}')
" 2>&1 | tail -1)

if [[ "$BOOT_RESULT" == OK* ]]; then
    ROUTE_COUNT=$(echo "$BOOT_RESULT" | awk '{print $2}')
    echo "   ✅ App booted with $ROUTE_COUNT routes"
else
    echo "   ❌ App boot failed:"
    echo "     $BOOT_RESULT"
    exit 1
fi
echo ""

# Test all routers load
echo "4. Router load test:"
ROUTER_RESULT=$(python3 -c "
import sys
sys.path.insert(0, '.')
from api.routers import ALL_ROUTERS
loaded = 0
failed = []
for r in ALL_ROUTERS:
    try:
        __import__(r['path'])
        loaded += 1
    except Exception as e:
        failed.append(f'{r[\"path\"]}: {type(e).__name__}')
print(f'{loaded}/{len(ALL_ROUTERS)}')
if failed:
    print('FAILED:')
    for f in failed:
        print(f'  - {f}')
" 2>&1 | tail -5)

SUCCESS_LINE=$(echo "$ROUTER_RESULT" | head -1)
if [[ "$SUCCESS_LINE" == */* ]]; then
    LOADED=$(echo "$SUCCESS_LINE" | cut -d/ -f1)
    TOTAL=$(echo "$SUCCESS_LINE" | cut -d/ -f2)
    if [[ "$LOADED" == "$TOTAL" ]]; then
        echo "   ✅ All $LOADED routers loaded"
    else
        echo "   ⚠️  $LOADED/$TOTAL routers loaded (some failed — see below)"
        echo "$ROUTER_RESULT" | tail -n +2
        exit 1
    fi
fi
echo ""

# Verify R2 lint (no blocking requests lib)
echo "5. R2 lint check:"
cd "$(git rev-parse --show-toplevel)"
if bash scripts/check_no_requests_in_backend.sh 2>&1 | grep -q "✅"; then
    echo "   ✅ No blocking 'requests' usage"
else
    echo "   ❌ Blocking 'requests' lib found"
    bash scripts/check_no_requests_in_backend.sh
    exit 1
fi
echo ""

echo "════════════════════════════════════════════════════════════════════"
echo "✅ ALL STABILIZE CHECKS PASSED"
echo "════════════════════════════════════════════════════════════════════"
exit 0
