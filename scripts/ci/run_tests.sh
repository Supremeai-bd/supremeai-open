#!/usr/bin/env bash
set -euo pipefail

echo "Running repository tests, lints, and type checks"
if command -v poetry >/dev/null 2>&1; then
  poetry run ruff check . || true
  poetry run mypy . || true
  poetry run pytest -q
else
  echo "poetry not found, running pytest only"
  pytest -q
fi

echo "Tests finished"
