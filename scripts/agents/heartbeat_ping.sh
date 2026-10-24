#!/usr/bin/env bash
# Universal shell heartbeat pinger for agent slots (issue #1402).
# Dependencies: curl + python3 (payload builder only). Same Redis contract as
# scripts/agents/heartbeat_ping.py.
#
# Usage:
#   HEARTBEAT_SLOT=agent-1 HEARTBEAT_AGENT_ID=Antigravity \
#   UPSTASH_REDIS_REST_URL=... UPSTASH_REDIS_REST_TOKEN=... \
#   ./heartbeat_ping.sh            # loop, 45s cadence
#
#   ./heartbeat_ping.sh agent-2 "Claude Code" 45   # positional form, loop
#   ./heartbeat_ping.sh agent-8 Aider once         # single ping (hooks/cron)
#
# The slot degrades to 'assigned' on the dashboard within 90s of the last ping.
set -u

SLOT="${1:-${HEARTBEAT_SLOT:-}}"
AGENT_ID="${2:-${HEARTBEAT_AGENT_ID:-}}"
CADENCE="${3:-${HEARTBEAT_INTERVAL:-45}}" # 45 | once
MODE="${HEARTBEAT_MODE:-rest}"            # rest | mcp
TTL=300

if [ -z "$SLOT" ]; then
  echo "usage: heartbeat_ping.sh <agent-N> [agentId] [45|once]  (or env HEARTBEAT_SLOT=…)" >&2
  exit 2
fi
case "$SLOT" in
agent-[0-9]*) ;;
*) echo "invalid slot '$SLOT' — must match agent-N" >&2; exit 2 ;;
esac
AGENT_ID="${AGENT_ID:-$SLOT}"
KEY="supremeai:agent-heartbeat:${SLOT}"

build_args_json() {
  # Emits the exact Upstash REST pipeline body: ["SET", key, payload, "EX", ttl]
  python3 -c '
import json, sys, time
slot, agent_id, ttl = sys.argv[1], sys.argv[2], int(sys.argv[3])
now_ms = int(time.time() * 1000)
payload = json.dumps({
    "slot": slot,
    "agentId": agent_id,
    "source": "cli",
    "updatedAtMs": now_ms,
    "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now_ms / 1000)),
})
print(json.dumps(["SET", f"supremeai:agent-heartbeat:{slot}", payload, "EX", str(ttl)]))
' "$SLOT" "$AGENT_ID" "$TTL"
}

# Failover chain (mirror of heartbeat_ping.py): a quota-dead primary must not
# break the ping while any other account is configured.
send_rest() {
  local args_json
  args_json="$(build_args_json)"

  local label url token
  while read -r label; do
    case "$label" in
      primary)
        url="${UPSTASH_REDIS_REST_URL:-}"; token="${UPSTASH_REDIS_REST_TOKEN:-}" ;;
      secondary)
        url="${UPSTASH_REDIS_SECONDARY_REST_URL:-}"; token="${UPSTASH_REDIS_SECONDARY_REST_TOKEN:-}" ;;
      tertiary)
        url="${UPSTASH_REDIS_TERTIARY_REST_URL:-}"; token="${UPSTASH_REDIS_TERTIARY_REST_TOKEN:-}" ;;
      quaternary)
        url="${UPSTASH_REDIS_QUATERNARY_REST_URL:-}"; token="${UPSTASH_REDIS_QUATERNARY_REST_TOKEN:-}" ;;
      quinary)
        url="${UPSTASH_REDIS_QUINARY_REST_URL:-}"; token="${UPSTASH_REDIS_QUINARY_REST_TOKEN:-}" ;;
      *) continue ;;
    esac
    [ -z "$url" ] || [ -z "$token" ] && continue
    if curl -fsS -m 10 -X POST "$url" \
      -H "Authorization: Bearer $token" \
      -H "Content-Type: application/json" \
      -d "$args_json" >/dev/null 2>&1; then
      return 0
    fi
  done <<EOF
primary
secondary
tertiary
quaternary
quinary
EOF
  return 1
}

send_mcp() {
  # Requires MCP_URL + MCP_API_KEY. One-shot: full handshake + agent_heartbeat.
  python3 "$(dirname "$0")/heartbeat_ping.py" \
    --slot "$SLOT" --agent-id "$AGENT_ID" --mode mcp --once
}

ping() {
  if [ "$MODE" = "mcp" ]; then
    send_mcp && echo "  ✅ $(date +%H:%M:%S) via mcp" && return 0
    return 1
  fi
  send_rest && echo "  ✅ $(date +%H:%M:%S) via rest" && return 0
  return 1
}

if [ "$CADENCE" = "once" ]; then
  ping
  exit $?
fi

echo "💓 pinging $SLOT ($AGENT_ID) every ${CADENCE}s…"
while true; do
  ping || echo "  ⚠️ $(date +%H:%M:%S) ping failed"
  sleep "$CADENCE"
done
