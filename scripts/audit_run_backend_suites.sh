#!/usr/bin/env bash
# Audit driver: run every backend test suite in isolation, one log per suite.
# Reproduces the per-suite matrix in docs/audits/FULL_SYSTEM_AUDIT_2026-09-14.md.
#
# Usage (repo root or anywhere):
#   bash scripts/audit_run_backend_suites.sh
# Logs land in /tmp/suites/<suite>.log with exit codes in /tmp/suites/_exitcodes.txt.
set -u
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../backend" && pwd)"
cd "$BACKEND_DIR"
mkdir -p /tmp/suites
export TESTING=true ENV=test
export TEST_DATABASE_URL="sqlite+aiosqlite:///./test.db"
export DATABASE_URL="postgresql://u:p@db.example.com:5432/supremeai"
export REDIS_URL="redis://localhost:6379/9"

DIRS="adaptive_engine agents ai api brain byoc core database engine hitl learning llm memory middleware missions models monitoring orchestration p2p_tests rag runtime scout_tests scripts security services test_evolution test_strategic_patches tools unit unit_light utils verification workers"

for d in $DIRS; do
  if [ -d "tests/$d" ]; then
    timeout 900 .venv/bin/python -m pytest "tests/$d" -p no:cacheprovider -q --no-cov --tb=no \
      > "/tmp/suites/$d.log" 2>&1
    echo "$? $d" >> /tmp/suites/_exitcodes.txt
    echo "done $d"
  fi
done
# root-level loose backend test files (tests/*.py at backend/tests root)
timeout 1500 .venv/bin/python -m pytest tests/*.py -p no:cacheprovider -q --no-cov --tb=no \
  > /tmp/suites/_root_tests.log 2>&1
echo "$? root_tests" >> /tmp/suites/_exitcodes.txt
echo "ALL-SUITES-DONE"
