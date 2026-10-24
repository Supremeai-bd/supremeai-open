#!/usr/bin/env bash
set -euo pipefail
# Resolve miner scripts relative to this script's directory so the runner works
# from any CWD (fixes #1618: previously pointed at tools/*.py, which does not
# exist — the miners live in tools/gap_miner/tools/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-.}"
OUT="${2:-reports/gap-miner}"
mkdir -p "$OUT"
python3 "$SCRIPT_DIR/tools/gap_miner.py" "$ROOT" --format both --out "$OUT"
python3 "$SCRIPT_DIR/tools/provider_capacity_miner.py" "$ROOT" --out "$OUT/provider_capacity.json"
python3 "$SCRIPT_DIR/tools/security_config_miner.py" "$ROOT" --out "$OUT/security_config.json"
python3 "$SCRIPT_DIR/tools/architecture_miner.py" "$ROOT" --out "$OUT/architecture.json"
echo "Gap mining completed: $OUT"
