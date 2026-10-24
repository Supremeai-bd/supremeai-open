#!/usr/bin/env bash
# agent-heartbeat.sh — one-line dashboard connector for agent slots (issue #1402).
#
# This is the script referenced by the SupremeAI Agent Self-Registration Prompt
# (Step 8/9). It POSTs to the dashboard heartbeat API — no Upstash credentials
# needed, so it works from ANY machine that can reach the dashboard:
#
#   curl -O "$AGENT_DASHBOARD_HOST/download/agent-heartbeat.sh"  # e.g. export AGENT_DASHBOARD_HOST=https://<your-dashboard-host>
#   chmod +x agent-heartbeat.sh
#
# Usage:
#   ./agent-heartbeat.sh agent-N "<Tool Name>" connected "initializing"  # one-shot
#   ./agent-heartbeat.sh --loop agent-N "<Tool Name>"                    # 45s loop (idle)
#   ./agent-heartbeat.sh agent-N "<Tool Name>" working "fixing CI"       # task ping
#   ./agent-heartbeat.sh agent-N "<Tool Name>" idle ""                   # back to idle
#
# Environment:
#   AGENT_DASHBOARD_URL   dashboard base URL (default: http://localhost:3000)
#   HEARTBEAT_INTERVAL_S  loop cadence (default: 45)
#
# State model: standby → assigned → connected → idle ↔ working → stale → assigned
# Slot degrades to 'assigned' 300s after the last ping (TTL 300s, live < 90s).
set -u

BASE="${AGENT_DASHBOARD_URL:-http://localhost:3000}"
INTERVAL="${HEARTBEAT_INTERVAL_S:-45}"

MODE="once"
if [ "${1:-}" = "--loop" ]; then
  MODE="loop"
  shift
fi

SLOT="${1:-${HEARTBEAT_SLOT:-}}"
AGENT_ID="${2:-${HEARTBEAT_AGENT_ID:-}}"
STATUS="${3:-idle}"
TASK="${4:-}"

if [ -z "$SLOT" ]; then
  echo "usage: agent-heartbeat.sh [--loop] <agent-N> [agentId] [connected|idle|working] [task]" >&2
  exit 2
fi
case "$SLOT" in
  agent-[0-9]*) ;;
  *) echo "invalid slot '$SLOT' — must match agent-N" >&2; exit 2 ;;
esac
case "$STATUS" in
  connected|idle|working) ;;
  *) echo "invalid status '$STATUS' — must be connected | idle | working" >&2; exit 2 ;;
esac
AGENT_ID="${AGENT_ID:-$SLOT}"

ping() {
  BODY=$(printf '{"slot":"%s","agentId":"%s","status":"%s","task":"%s"}' \
    "$SLOT" "$AGENT_ID" "$STATUS" "$(echo "$TASK" | sed 's/"/\\"/g' | cut -c1-200)")
  RESP=$(curl -fsS -m 10 -X POST "$BASE/api/agents/heartbeat" \
    -H "Content-Type: application/json" -d "$BODY" 2>&1) || {
      echo "  ✗ $(date +%H:%M:%S) ping failed — is AGENT_DASHBOARD_URL ($BASE) correct?" >&2
      echo "    $RESP" >&2
      return 1
    }
  STATE=$(echo "$RESP" | grep -o '"state":"[a-z]*"' | head -1 | cut -d'"' -f4)
  echo "  ✓ $(date +%H:%M:%S) $SLOT ($AGENT_ID) → status=$STATUS${STATE:+ state=$STATE}"
}

if [ "$MODE" = "once" ]; then
  ping
  exit $?
fi

echo "💓 pinging $SLOT ($AGENT_ID) every ${INTERVAL}s → $BASE (Ctrl+C to stop)"
while true; do
  ping
  sleep "$INTERVAL"
done
