#!/usr/bin/env bash
# ============================================================================
# Claude Code SessionStart hook — agent-2 heartbeat (issue #1402).
#
# Claude Code invokes this script when a session starts. It sends the
# "connected" transition, then re-execs the keep-alive loop in the
# background (detached, log-file guarded) so the slot stays "idle"/online
# for the lifetime of the session. A stale keep-alive process from a
# previous session is killed first (pidfile) so one session == one pinger.
#
# Install (in the machine that runs Claude Code):
#   mkdir -p ~/.claude/hooks
#   cp heartbeat-hook.sh ~/.claude/hooks/heartbeat.sh && chmod +x ~/.claude/hooks/heartbeat.sh
#   # then register it in ~/.claude/settings.json (see settings-snippet.json):
#   # { "hooks": { "SessionStart": [ { "hooks": [ { "type": "command",
#   #     "command": "$HOME/.claude/hooks/heartbeat.sh" } ] } ] } }
#
# Environment (export in shell profile or hardcode here):
#   HEARTBEAT_URL  e.g. https://<dashboard-host>/api/agents/heartbeat
#   AGENT_SLOT     agent-2 (default matches this slot)
#   AGENT_ID       "Claude Code"
# ============================================================================
set -u

HEARTBEAT_URL="${HEARTBEAT_URL:-}"
AGENT_SLOT="${AGENT_SLOT:-agent-2}"
AGENT_ID="${AGENT_ID:-Claude Code}"
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_HEARTBEAT="$HOOK_DIR/../../tools/agent_heartbeat/heartbeat.sh"
PIDFILE="${TMPDIR:-/tmp}/agent-2-heartbeat.pid"
LOGFILE="${TMPDIR:-/tmp}/agent-2-heartbeat.log"

[ -n "$HEARTBEAT_URL" ] || { echo "[agent-2 heartbeat] HEARTBEAT_URL unset — hook is a no-op" >&2; exit 0; }

# Locate the shared pinger: prefer the repo copy, fall back to hook-local.
PINGER="$REPO_HEARTBEAT"
[ -x "$PINGER" ] || PINGER="$HOOK_DIR/heartbeat.sh"
[ -x "$PINGER" ] || { echo "[agent-2 heartbeat] pinger script not found" >&2; exit 0; }

# Single-pinger guarantee: replace any previous session's keep-alive.
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  kill "$(cat "$PIDFILE")" 2>/dev/null || true
  sleep 1
fi

nohup env HEARTBEAT_URL="$HEARTBEAT_URL" \
          AGENT_SLOT="$AGENT_SLOT" AGENT_ID="$AGENT_ID" \
          "$PINGER" loop >>"$LOGFILE" 2>&1 &
echo $! >"$PIDFILE"

echo "[agent-2 heartbeat] keep-alive started (pid $(cat "$PIDFILE"), interval 45s)" >&2
exit 0
