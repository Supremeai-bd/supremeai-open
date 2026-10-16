#!/bin/sh
# ============================================================================
# SupremeAI MCP Tower — HTTP endpoint smoke tests (POSIX sh, curl only)
# Issue #49 · works on Linux, macOS, any POSIX shell with curl.
# Windows mirror: health.ps1 (same subcommands, same output contract).
#
# Usage:
#   sh health.sh                 # health check (default)
#   sh health.sh health          # explicit health check
#   sh health.sh sse             # SSE handshake smoke (bounded read)
#   sh health.sh tools-list      # MCP tools/list over /mcp
#   sh health.sh tool-call system_summary
#   sh health.sh tool-call bridge_guide
#   sh health.sh all             # everything, non-interactive
#   sh health.sh gateway         # supremeai-api gateway smoke (issue #336, GW_BASE_URL)
#
# Environment overrides:
#   BASE_URL              default: https://supremeai-mcp-tower.onrender.com
#   MCP_PROTOCOL_VERSION  default: 2025-03-26
#   CURL_TIMEOUT          default: 20 (seconds per request)
#   GW_BASE_URL           default: http://127.0.0.1:8080  (gateway subcommand)
#   GW_KEY                default: supremeai-key-local-dev           (#336)
#
# Exit codes: 0 = all requested checks passed; 1 = at least one failed
# (fail-closed, matching repo doctrine — a skipped check does not exist).
# ============================================================================
set -u

BASE_URL="${BASE_URL:-https://supremeai-mcp-tower.onrender.com}"
MCP_PROTOCOL_VERSION="${MCP_PROTOCOL_VERSION:-2025-03-26}"
CURL_TIMEOUT="${CURL_TIMEOUT:-20}"
BASE_URL="${BASE_URL%/}"
GW_BASE_URL="${GW_BASE_URL:-http://127.0.0.1:8080}"
GW_BASE_URL="${GW_BASE_URL%/}"
GW_KEY="${GW_KEY:-supremeai-key-local-dev}"

failures=0
STATE_DIR=$(mktemp -d)
trap 'rm -rf "$STATE_DIR"' EXIT INT TERM
unwrap() { # $1 = raw response; strips SSE framing (event:/data:) if present
  if printf '%s' "$1" | grep -q '^data:'; then
    printf '%s' "$1" | grep '^data:' | sed 's/^data:[[:space:]]*//' | tr -d '\r'
  else
    printf '%s' "$1"
  fi
}
mcp_code() { cat "$STATE_DIR/code" 2>/dev/null || printf '?'; }
mcp_sid() { cat "$STATE_DIR/sid" 2>/dev/null || true; }
note() { printf '%s\n' "$*"; }
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }

# --- health ----------------------------------------------------------------
cmd_health() {
  note "== GET $BASE_URL/health =="
  body=$(curl -sS --max-time "$CURL_TIMEOUT" -w '\n%{http_code}' "$BASE_URL/health" 2>&1) || { fail "health: curl transport error"; return 0; }
  code=$(printf '%s' "$body" | tail -n 1)
  payload=$(printf '%s' "$body" | sed '$d')
  if [ "$code" = "200" ]; then
    pass "health: HTTP $code — $payload"
  else
    fail "health: HTTP $code — $payload"
  fi
}

# --- SSE handshake (bounded, read-only) --------------------------------------
cmd_sse() {
  note "== GET $BASE_URL/sse (bounded ${CURL_TIMEOUT}s read) =="
  frames=$(curl -sS -N --max-time "$CURL_TIMEOUT" -H 'Accept: text/event-stream' "$BASE_URL/sse" 2>&1)
  # The transport's first frames name the endpoint event and the session.
  if printf '%s' "$frames" | grep -q 'event:' && printf '%s' "$frames" | grep -q 'data:'; then
    endpoint=$(printf '%s' "$frames" | grep '^data:' | head -n 1 | sed 's/^data:[[:space:]]*//')
    pass "sse: stream opened, endpoint frame: $endpoint"
  else
    fail "sse: no event/data frames within ${CURL_TIMEOUT}s"
  fi
}

# --- MCP JSON-RPC over /mcp ---------------------------------------------------
# Streamable MCP: initialize (capture mcp-session-id), then authenticated calls.
mcp_post() { # $1 = JSON body ; prints response body ; code/sid persisted to $STATE_DIR (subshell-safe)
  cur_sid=$(mcp_sid)   # re-read state file FIRST: each $(...) subshell starts fresh
  hdrs="$STATE_DIR/hdrs"
  resp=$(curl -sS --max-time "$CURL_TIMEOUT" -D "$hdrs" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    ${cur_sid:+-H "mcp-session-id: $cur_sid"} \
    -X POST -d "$1" "$BASE_URL/mcp" 2>&1) || { printf '%s' "$resp"; return 1; }
  awk '$1 ~ /^HTTP\/[0-9.]+$/ {code=$2} END{print code}' "$hdrs" > "$STATE_DIR/code"
  # Keep the previous session id when a response carries none (e.g. the
  # notifications/initialized 202 would otherwise clobber it).
  awk 'tolower($1)=="mcp-session-id:" {sub(/\r$/,"",$2); print $2; found=1} END{exit !found}' "$hdrs" > "$STATE_DIR/sid.new" 2>/dev/null \
    && mv "$STATE_DIR/sid.new" "$STATE_DIR/sid" || rm -f "$STATE_DIR/sid.new"
  cur_sid=$(cat "$STATE_DIR/sid" 2>/dev/null || true)
  printf '%s' "$resp"
}

mcp_init() {
  jsonrpc_id=$((jsonrpc_id + 1))
  : > "$STATE_DIR/sid"   # fresh session lifecycle — never re-initialize an existing session
  cur_sid=$(mcp_sid)
  mcp_post "{\"jsonrpc\":\"2.0\",\"id\":$jsonrpc_id,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"$MCP_PROTOCOL_VERSION\",\"capabilities\":{},\"clientInfo\":{\"name\":\"supremeai-curl-tests\",\"version\":\"1.0\"}}}"
}

cmd_tools_list() {
  note "== POST $BASE_URL/mcp (initialize + tools/list) =="
  init_resp=$(unwrap "$(mcp_init)") || { fail "tools-list: initialize transport error"; return 0; }
  if [ "$(mcp_code)" != "200" ]; then fail "tools-list: initialize HTTP $(mcp_code) — $init_resp"; return 0; fi
  # notifications/initialized (no response expected)
  jsonrpc_id=$((jsonrpc_id + 1))
  mcp_post '{"jsonrpc":"2.0","method":"notifications/initialized"}' >/dev/null 2>&1 || true
  jsonrpc_id=$((jsonrpc_id + 1))
  list_resp=$(unwrap "$(mcp_post "{\"jsonrpc\":\"2.0\",\"id\":$jsonrpc_id,\"method\":\"tools/list\"}")") || { fail "tools-list: transport error"; return 0; }
  if printf '%s' "$list_resp" | grep -q '"tools"'; then
    count=$(printf '%s' "$list_resp" | grep -o '"name"' | wc -l | tr -d ' ')
    pass "tools-list: HTTP 200, tools frame present (~$count name fields)"
  else
    fail "tools-list: no tools frame — $list_resp"
  fi
}

cmd_tool_call() { # $1 = tool name (e.g. system_summary, bridge_guide)
  tool="${1:-system_summary}"
  note "== POST $BASE_URL/mcp (initialize + tools/call $tool) =="
  init_resp=$(unwrap "$(mcp_init)") || { fail "tool-call: initialize transport error"; return 0; }
  if [ "$(mcp_code)" != "200" ]; then fail "tool-call: initialize HTTP $(mcp_code) — $init_resp"; return 0; fi
  jsonrpc_id=$((jsonrpc_id + 1))
  mcp_post '{"jsonrpc":"2.0","method":"notifications/initialized"}' >/dev/null 2>&1 || true
  jsonrpc_id=$((jsonrpc_id + 1))
  call_resp=$(unwrap "$(mcp_post "{\"jsonrpc\":\"2.0\",\"id\":$jsonrpc_id,\"method\":\"tools/call\",\"params\":{\"name\":\"$tool\",\"arguments\":{}}}")") || { fail "tool-call $tool: transport error"; return 0; }
  if printf '%s' "$call_resp" | grep -q '"result"'; then
    pass "tool-call $tool: HTTP 200, result frame present"
    printf '%s' "$call_resp" | head -c 400; printf '\n'
  elif printf '%s' "$call_resp" | grep -q '"error"'; then
    fail "tool-call $tool: JSON-RPC error — $call_resp"
  else
    fail "tool-call $tool: unexpected response — $call_resp"
  fi
}

cmd_all() {
  cmd_health
  cmd_sse
  cmd_tools_list
  cmd_tool_call system_summary
  cmd_tool_call bridge_guide
}

# --- gateway (issue #336 AC3): unified provider gateway smoke ---------------
# Runs against GW_BASE_URL (a supremeai-api gateway, not the MCP tower).
gw_health() {
  note "== GET $GW_BASE_URL/healthz =="
  body=$(curl -sS --max-time "$CURL_TIMEOUT" -w '\n%{http_code}' "$GW_BASE_URL/healthz" 2>&1) || { fail "gw-health: curl transport error"; return 0; }
  code=$(printf '%s' "$body" | tail -n 1)
  payload=$(printf '%s' "$body" | sed '$d')
  [ "$code" = "200" ] && pass "gw-health: HTTP $code — $payload" || fail "gw-health: HTTP $code — $payload"
}
gw_models_auth_gate() {
  note "== GET $GW_BASE_URL/v1/models (no key -> 401 default-deny) =="
  code=$(curl -sS --max-time "$CURL_TIMEOUT" -o /dev/null -w '%{http_code}' "$GW_BASE_URL/v1/models" 2>&1) || { fail "gw-models-auth: curl transport error"; return 0; }
  [ "$code" = "401" ] && pass "gw-models-auth: HTTP 401 (default-deny)" || fail "gw-models-auth: expected 401, got $code"
}
gw_models() {
  note "== GET $GW_BASE_URL/v1/models (keyed) =="
  body=$(curl -sS --max-time "$CURL_TIMEOUT" -w '\n%{http_code}' -H "X-SupremeAI-Key: $GW_KEY" "$GW_BASE_URL/v1/models" 2>&1) || { fail "gw-models: curl transport error"; return 0; }
  code=$(printf '%s' "$body" | tail -n 1)
  payload=$(printf '%s' "$body" | sed '$d')
  if [ "$code" = "200" ] && printf '%s' "$payload" | grep -q '"data"'; then
    pass "gw-models: HTTP 200 — model list present"
  else
    fail "gw-models: HTTP $code — $payload"
  fi
}
gw_chat_json() {
  note "== POST $GW_BASE_URL/v1/chat/completions (stream:false) =="
  body=$(curl -sS --max-time "$CURL_TIMEOUT" -w '\n%{http_code}' -H "X-SupremeAI-Key: $GW_KEY" -H 'Content-Type: application/json' -X POST -d '{"model":"auto","messages":[{"role":"user","content":"smoke"}]}' "$GW_BASE_URL/v1/chat/completions" 2>&1) || { fail "gw-chat: curl transport error"; return 0; }
  code=$(printf '%s' "$body" | tail -n 1)
  payload=$(printf '%s' "$body" | sed '$d')
  if [ "$code" = "200" ] && printf '%s' "$payload" | grep -q '"chat.completion"'; then
    pass "gw-chat: HTTP 200 — OpenAI-compatible completion"
  else
    fail "gw-chat: HTTP $code — $payload"
  fi
}
gw_chat_sse() {
  note "== POST $GW_BASE_URL/v1/chat/completions (stream:true, bounded read) =="
  frames=$(curl -sS -N --max-time "$CURL_TIMEOUT" -H "X-SupremeAI-Key: $GW_KEY" -H 'Content-Type: application/json' -X POST -d '{"stream":true,"messages":[{"role":"user","content":"smoke"}]}' "$GW_BASE_URL/v1/chat/completions" 2>&1)
  if printf '%s' "$frames" | grep -q '^event:' && printf '%s' "$frames" | grep -q '^data:'; then
    pass "gw-chat-sse: event:/data: framing present"
  else
    fail "gw-chat-sse: no SSE frames within ${CURL_TIMEOUT}s"
  fi
}
cmd_gateway() {
  gw_health
  gw_models_auth_gate
  gw_models
  gw_chat_json
  gw_chat_sse
}

case "${1:-health}" in
  health)      cmd_health ;;
  sse)         cmd_sse ;;
  tools-list)  cmd_tools_list ;;
  tool-call)   shift; cmd_tool_call "${1:-system_summary}" ;;
  gateway)     cmd_gateway ;;
  all)         cmd_all ;;
  *) printf 'unknown subcommand: %s\n' "$1" >&2; printf 'usage: sh health.sh [health|sse|tools-list|tool-call <name>|all]\n' >&2; exit 2 ;;
esac

if [ "$failures" -gt 0 ]; then
  printf '\n%d check(s) FAILED (fail-closed: no silent skips).\n' "$failures" >&2
  exit 1
fi
printf '\nAll requested checks passed.\n'
exit 0
