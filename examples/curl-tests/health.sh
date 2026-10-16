#!/usr/bin/env bash
# SupremeAI MCP Tower — HTTP endpoint test suite (bash, Linux/macOS).
# Companion: health.ps1 (Windows PowerShell). Contract: examples/curl-tests/README.md.
#
# Endpoints exercised (all real, see infrastructure/mcp-control-plane/src/index.ts):
#   GET  /health   — honest aggregate health (200 ok|degraded, 503 outage)
#   GET  /sse      — legacy SSE transport handshake (emits `event: endpoint`)
#   POST /mcp      — Streamable JSON-RPC: initialize -> tools/list -> tools/call
#
# Usage:
#   bash health.sh [health|sse|tools|call|all] [tool-name]
# Examples:
#   bash health.sh all
#   bash health.sh call system.summary
#   bash health.sh call bridge.guide
# Environment:
#   MCP_TOWER_URL — override base URL (default: https://supremeai-mcp-tower.onrender.com)
# Exit codes: 0 pass · 1 test failure · 2 usage error · 3 curl/network failure

set -u
BASE_URL="${MCP_TOWER_URL:-https://supremeai-mcp-tower.onrender.com}"
PASS_COUNT=0
FAIL_COUNT=0

say()  { printf '%s\n' "$*"; }
pass() { PASS_COUNT=$((PASS_COUNT + 1)); say "PASS: $*"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); say "FAIL: $*"; }

require_curl() {
  command -v curl >/dev/null 2>&1 || { say "SKIP: curl not found on PATH"; exit 3; }
}

# --- 1. Health check -------------------------------------------------------
cmd_health() {
  say "== health: GET $BASE_URL/health"
  local body http_code
  body=$(curl -sS --max-time 30 -w $'\n%{http_code}' "$BASE_URL/health" 2>/dev/null) || { fail "health: network error"; return; }
  http_code=$(printf '%s' "$body" | tail -n 1)
  body=$(printf '%s' "$body" | sed '$d')
  case "$http_code" in
    200)
      pass "health: HTTP 200"
      # honest aggregate: status is ok | degraded (both are healthy-enough answers)
      if printf '%s' "$body" | grep -q '"status"'; then
        pass "health: status field present ($(printf '%s' "$body" | grep -o '"status"[^,}]*' | head -n 1))"
      else
        fail "health: no status field in body"
      fi
      ;;
    503) fail "health: HTTP 503 outage (service reports itself down — honest, but not healthy)" ;;
    *)   fail "health: unexpected HTTP $http_code" ;;
  esac
}

# --- 2. SSE handshake ------------------------------------------------------
cmd_sse() {
  say "== sse: GET $BASE_URL/sse (expect event: endpoint within timeout)"
  local stream
  stream=$(curl -sS -N --max-time 12 -H "Accept: text/event-stream" "$BASE_URL/sse" 2>/dev/null | head -n 20)
  if printf '%s\n' "$stream" | grep -q 'event: *endpoint'; then
    pass "sse: endpoint event received ($(printf '%s\n' "$stream" | grep 'data:' | head -n 1))"
  elif [ -z "$stream" ]; then
    fail "sse: no stream within 12s"
  else
    fail "sse: stream opened but no endpoint event (first lines: $(printf '%s\n' "$stream" | head -n 3 | tr '\n' ' '))"
  fi
}

# --- Shared: MCP streamable handshake --------------------------------------
# Prints the temp dir path holding the session id on success; caller cleans up.
mcp_handshake_session() {
  local tmp hdr sid
  tmp=$(mktemp -d) || return 1
  hdr="$tmp/headers"

  curl -sS --max-time 30 -D "$hdr" -o "$tmp/init" \
    -X POST "$BASE_URL/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl-tests","version":"1.0.0"}}}' \
    2>/dev/null || { rm -rf "$tmp"; return 1; }

  sid=$(grep -i '^mcp-session-id:' "$hdr" | head -n 1 | tr -d '\r' | sed 's/^[Mm][Cc][Pp]-[Ss]ession-[Ii][Dd]: *//')
  if [ -z "$sid" ]; then rm -rf "$tmp"; return 1; fi

  # notifications/initialized — session activation (no response body expected).
  curl -sS --max-time 30 -o /dev/null -X POST "$BASE_URL/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "mcp-session-id: $sid" \
    -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' 2>/dev/null || true

  printf '%s' "$sid" > "$tmp/sid"
  printf '%s' "$tmp"
}

# Strip an SSE wrapper from a JSON-RPC response body, if present.
mcp_unwrap() {
  local body="$1"
  case "$body" in
    data:*) printf '%s\n' "$body" | sed -n 's/^data: *//p' | head -n 1 ;;
    *)      printf '%s' "$body" ;;
  esac
}

# --- 3. Tool listing --------------------------------------------------------
cmd_tools() {
  say "== tools: POST $BASE_URL/mcp initialize -> tools/list"
  local tmp sid body
  tmp=$(mcp_handshake_session) || { fail "tools: initialize handshake failed (no mcp-session-id header)"; return; }
  sid=$(cat "$tmp/sid")

  body=$(curl -sS --max-time 30 -X POST "$BASE_URL/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "mcp-session-id: $sid" \
    -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' 2>/dev/null)
  body=$(mcp_unwrap "$body")

  if printf '%s' "$body" | grep -q '"tools"'; then
    local count
    count=$(printf '%s' "$body" | grep -o '"name"' | wc -l | tr -d ' ')
    pass "tools: tools/list returned $count tool entries"
    if printf '%s' "$body" | grep -q '"bridge.guide"'; then
      pass "tools: bridge.guide visible (zero-credential guest scope)"
    else
      say "NOTE: bridge.guide not in this session's tool list (scope-dependent visibility)"
    fi
  else
    fail "tools: no tools array in response ($(printf '%s' "$body" | head -c 160))"
  fi
  rm -rf "$tmp"
}

# --- 4. Tool call -----------------------------------------------------------
# The Tower's call registry sanitizes registered names (dots -> underscores,
# index.ts server.tool wrapper) while tools/list advertises the dotted form.
# We therefore try the advertised name first and, if the call layer reports
# "not found", retry the call-registry variant — surfacing the mismatch.
shell_name_variant() {
  printf '%s' "$1" | tr '.' '_'
}

cmd_call() {
  local tool="${1:-system.summary}"
  say "== call: tools/call $tool"
  local tmp sid body
  tmp=$(mcp_handshake_session) || { fail "call: initialize handshake failed (no mcp-session-id header)"; return; }
  sid=$(cat "$tmp/sid")

  body=$(curl -sS --max-time 60 -X POST "$BASE_URL/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "mcp-session-id: $sid" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"$tool\",\"arguments\":{}}}" 2>/dev/null)
  body=$(mcp_unwrap "$body")

  if printf '%s' "$body" | grep -q 'not found'; then
    local variant="$(shell_name_variant "$tool")"
    if [ "$variant" != "$tool" ]; then
      say "NOTE: '$tool' not callable (advertised by tools/list) — retrying call-registry variant '$variant'"
      tool="$variant"
      body=$(curl -sS --max-time 60 -X POST "$BASE_URL/mcp" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -H "mcp-session-id: $sid" \
        -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"$tool\",\"arguments\":{}}}" 2>/dev/null)
      body=$(mcp_unwrap "$body")
    fi
  fi

  if printf '%s' "$body" | grep -q '"isError":true'; then
    fail "call $tool: tool returned isError:true ($(printf '%s' "$body" | head -c 200))"
  elif printf '%s' "$body" | grep -q '"content"'; then
    pass "call $tool: content returned ($(printf '%s' "$body" | head -c 120)...)"
  else
    fail "call $tool: unexpected response ($(printf '%s' "$body" | head -c 160))"
  fi
  rm -rf "$tmp"
}

cmd_all() {
  cmd_health
  cmd_sse
  cmd_tools
  cmd_call "${1:-system.summary}"
  cmd_call "bridge.guide"
}

case "${1:-all}" in
  health) require_curl; cmd_health ;;
  sse)    require_curl; cmd_sse ;;
  tools)  require_curl; cmd_tools ;;
  call)   require_curl; cmd_call "${2:-system.summary}" ;;
  all)    require_curl; cmd_all "${2:-system.summary}" ;;
  *) say "usage: bash health.sh [health|sse|tools|call|all] [tool-name]"; exit 2 ;;
esac

say ""
say "summary: $PASS_COUNT passed, $FAIL_COUNT failed"
[ "$FAIL_COUNT" -eq 0 ] || exit 1
exit 0
