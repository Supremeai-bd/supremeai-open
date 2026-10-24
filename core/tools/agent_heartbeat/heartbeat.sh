#!/usr/bin/env bash
# ============================================================================
# agent_heartbeat.sh — generic keep-alive pinger for the SupremeAI agent
# status dashboard (issue #1402).
#
# POSTs the documented heartbeat contract every PING_INTERVAL seconds while
# this process is alive, with the 6-state lifecycle transitions:
#
#   startup  -> status:"connected" (one-time)
#   +3s      -> status:"idle"
#   loop     -> status:"idle" every PING_INTERVAL seconds (keep-alive)
#
# Configuration (environment variables):
#   HEARTBEAT_URL    endpoint URL (REQUIRED; script exits 0 with a warning if
#                    unset — heartbeat is observability, never a hard dep)
#   AGENT_SLOT       slot name, must match /^agent-\d+$/   (default agent-2)
#   AGENT_ID         human-readable tool label              (default "Unknown Tool")
#   PING_INTERVAL    seconds between keep-alive pings       (default 45)
#   CONNECTED_HOLD   seconds before flipping connected->idle (default 3)
#
# Usage:
#   HEARTBEAT_URL=https://<dashboard-host>/api/agents/heartbeat \
#     ./heartbeat.sh &                 # background keep-alive
#
#   ./heartbeat.sh once                # single idle ping (cron/hook friendly)
#   ./heartbeat.sh working "task text" # single working ping
#   ./heartbeat.sh stop                # final idle ping, then exit
#
# Exit codes are always 0 for observability failures; non-zero only for
# usage errors, so callers can safely `set -e` around it.
# ============================================================================
set -u

HEARTBEAT_URL="${HEARTBEAT_URL:-}"
AGENT_SLOT="${AGENT_SLOT:-agent-2}"
AGENT_ID="${AGENT_ID:-Unknown Tool}"
PING_INTERVAL="${PING_INTERVAL:-45}"
CONNECTED_HOLD="${CONNECTED_HOLD:-3}"

log() { printf '[agent_heartbeat] %s\n' "$*" >&2; }

die_usage() { log "usage: $0 [once|working <task>|stop]  (env: HEARTBEAT_URL, AGENT_SLOT, AGENT_ID, PING_INTERVAL)"; exit 2; }

# --- POST helper: curl -> wget -> python fallback chain -----------------------
post() { # $1 = status, $2 = task (optional)
  [ -n "$HEARTBEAT_URL" ] || { log "HEARTBEAT_URL unset — ping skipped"; return 1; }
  local body task_json=""
  if [ $# -ge 2 ] && [ -n "${2:-}" ]; then
    task_json=$(printf '"%s"' "$(printf '%s' "$2" | sed 's/\\/\\\\/g; s/"/\\"/g')")
  fi
  body="{\"slot\":\"${AGENT_SLOT}\",\"agentId\":\"${AGENT_ID}\",\"status\":\"${1}\""
  [ -n "$task_json" ] && body="${body},\"task\":${task_json}"
  body="${body}}"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS -m 10 -X POST "$HEARTBEAT_URL" -H 'Content-Type: application/json' -d "$body" >/dev/null 2>&1
  elif command -v wget >/dev/null 2>&1; then
    wget -q -T 10 -O /dev/null --header='Content-Type: application/json' --post-data="$body" "$HEARTBEAT_URL" 2>/dev/null
  else
    python3 - "$HEARTBEAT_URL" "$body" <<'PY' >/dev/null 2>&1
import sys, urllib.request
url, body = sys.argv[1], sys.argv[2].encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=10)
PY
  fi
}

ping() { # $1 = status, $2 = task (optional)
  if post "$@"; then log "POST ok  status=$1 slot=${AGENT_SLOT}"; else log "POST failed (non-fatal) status=$1"; fi
}

# --- Modes -------------------------------------------------------------------
MODE="${1:-loop}"
case "$MODE" in
  once)
    ping idle
    ;;
  working)
    [ $# -ge 2 ] || die_usage
    ping working "$2"
    ;;
  stop)
    ping idle
    log "stop ping sent — slot reverts to 'assigned' after TTL expiry"
    ;;
  loop)
    [ -n "$HEARTBEAT_URL" ] || { log "HEARTBEAT_URL unset — nothing to ping; exiting 0"; exit 0; }
    trap 'log "caught signal — sending final idle ping"; ping idle; exit 0' INT TERM
    ping connected
    sleep "$CONNECTED_HOLD"
    ping idle
    while :; do
      sleep "$PING_INTERVAL"
      ping idle
    done
    ;;
  *)
    die_usage
    ;;
esac
