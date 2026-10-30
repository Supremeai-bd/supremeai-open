#!/bin/sh
# ============================================================================
# SupremeAI Gateway — E2E smoke: 10 real-world calls (5 non-stream + 5 SSE)
# Issue #403 · POSIX sh + curl + jq. Windows mirror: run_e2e_smoke.ps1
# (same subcommands, same output contract, same exit codes).
#
# Usage:
#   sh run_e2e_smoke.sh                # full matrix: 5 non-stream + 5 stream
#   sh run_e2e_smoke.sh all            # explicit full matrix
#   sh run_e2e_smoke.sh nonstream      # only the 5 non-streaming calls
#   sh run_e2e_smoke.sh stream         # only the 5 SSE streaming calls
#   sh run_e2e_smoke.sh help           # this help
#
# Environment overrides:
#   GATEWAY_URL           default: https://supremeai-api-ulw0.onrender.com
#                         (README SSOT service table; repo client contract,
#                         examples/gateway_client.py — ghost host retired by
#                         #2355/#2365/#2377, ghost_host_guard.py enforces)
#   SUPREMEAI_API_KEY     required — monolith key-plane-issued key (vault/env;
#                         never hardcode, SECRETS_MODEL.md)
#   MODELS                space-separated model rotation, default: "auto"
#                         (live list: GET /v1/models)
#   MAX_TOKENS            default: 32 (budget cap — runaway-cost guard)
#   CURL_TIMEOUT          default: 30 (seconds per request)
#
# Contract checks per the issue #403 acceptance:
#   - non-stream: HTTP 200, choices[0].message.content non-empty, usage object
#   - stream: valid `data:` frames, terminal frame EXACT `data: [DONE]`,
#     TTFT recorded per call (curl time_starttransfer)
#   - mid-stream provider failure = honest FAIL line + non-zero exit
#     (never a silent corrupted drop)
#
# Exit codes: 0 = 10/10 (or N/N for the requested subset) passed; 1 = at
# least one call failed (fail-closed — a skipped check does not exist).
# ============================================================================
set -u

GATEWAY_URL="${GATEWAY_URL:-https://supremeai-api-ulw0.onrender.com}"
GATEWAY_URL="${GATEWAY_URL%/}"
MODELS="${MODELS:-auto}"
MAX_TOKENS="${MAX_TOKENS:-32}"
CURL_TIMEOUT="${CURL_TIMEOUT:-30}"
PROMPT="Reply with exactly: SUPREME-E2E-OK"

failures=0
passed=0
STATE_DIR=$(mktemp -d)
trap 'rm -rf "$STATE_DIR"' EXIT INT TERM

fail() { # $1 = label, $2 = reason, $3 = optional model context (honest ledger)
  failures=$((failures + 1))
  if [ $# -ge 3 ]; then
    printf 'FAIL %s (model=%s): %s\n' "$1" "$3" "$2"
  else
    printf 'FAIL %s: %s\n' "$1" "$2"
  fi
}

ok() { # $1 = label, $2 = detail
  passed=$((passed + 1))
  printf 'PASS %s: %s\n' "$1" "$2"
}

require_env() {
  if [ -z "${SUPREMEAI_API_KEY:-}" ]; then
    printf 'FAIL setup: SUPREMEAI_API_KEY is not set — key-plane key required (docs/CONSUMERS.md). No live calls attempted.\n'
    exit 1
  fi
  if ! command -v jq >/dev/null 2>&1; then
    printf 'FAIL setup: jq is required for SSE/JSON frame validation (fail-closed; install jq).\n'
    exit 1
  fi
}

model_at() { # $1 = 0-based index → rotated model from $MODELS (POSIX; no set--, no arrays)
  count=$(printf '%s' "$MODELS" | wc -w)
  pos=$(( $1 % count + 1 ))
  printf '%s' "$MODELS" | tr -s ' \t' '  ' | cut -d' ' -f"$pos"
}

nonstream_call() { # $1 = label, $2 = model
  body_file="$STATE_DIR/body_$1.json"
  meta=$(curl -sS -m "$CURL_TIMEOUT" -o "$body_file" \
    -H "X-SupremeAI-Key: $SUPREMEAI_API_KEY" -H 'Content-Type: application/json' \
    -w '%{http_code} %{time_total}' \
    -d "{\"model\":\"$2\",\"messages\":[{\"role\":\"user\",\"content\":\"$PROMPT\"}],\"stream\":false,\"max_tokens\":$MAX_TOKENS}" \
    "$GATEWAY_URL/v1/chat/completions" 2>"$STATE_DIR/curl_err_$1") || {
      fail "$1" "curl transport error: $(cat "$STATE_DIR/curl_err_$1")" "$2"; return 1; }
  status=$(printf '%s' "$meta" | cut -d' ' -f1)
  latency=$(printf '%s' "$meta" | cut -d' ' -f2)
  if [ "$status" != "200" ]; then
    fail "$1" "honest error — HTTP $status (gateway must return sanitized ledger): $(head -c 200 "$body_file")" "$2"
    return 1
  fi
  content=$(jq -r '.choices[0].message.content // empty' "$body_file" 2>/dev/null)
  usage=$(jq -r 'has("usage")' "$body_file" 2>/dev/null)
  if [ -z "$content" ]; then
    fail "$1" "empty choices[0].message.content — contract violation" "$2"
    return 1
  fi
  if [ "$usage" != "true" ]; then
    fail "$1" "usage object missing — Honest Ledger contract violation" "$2"
    return 1
  fi
  ok "$1" "model=$2 non-stream 200, content+usage present, ${latency}s"
}

stream_call() { # $1 = label, $2 = model
  body_file="$STATE_DIR/sse_$1.txt"
  meta=$(curl -sS -N -m "$CURL_TIMEOUT" -o "$body_file" \
    -H "X-SupremeAI-Key: $SUPREMEAI_API_KEY" -H 'Content-Type: application/json' \
    -w '%{http_code} %{time_starttransfer}' \
    -d "{\"model\":\"$2\",\"messages\":[{\"role\":\"user\",\"content\":\"$PROMPT\"}],\"stream\":true,\"max_tokens\":$MAX_TOKENS}" \
    "$GATEWAY_URL/v1/chat/completions" 2>"$STATE_DIR/curl_err_$1") || {
      fail "$1" "curl transport error: $(cat "$STATE_DIR/curl_err_$1")" "$2"; return 1; }
  status=$(printf '%s' "$meta" | cut -d' ' -f1)
  ttft=$(printf '%s' "$meta" | cut -d' ' -f2)
  if [ "$status" != "200" ]; then
    fail "$1" "honest error — HTTP $status: $(head -c 200 "$body_file")" "$2"
    return 1
  fi
  # SSE frame validation: every frame must be `data: ...`; terminal EXACT [DONE]
  if ! grep -q '^data:' "$body_file"; then
    fail "$1" "no SSE data: frames — streaming contract violation" "$2"
    return 1
  fi
  terminal=$(grep '^data:' "$body_file" | tail -n 1 | sed 's/^data:[[:space:]]*//' | tr -d '\r')
  if [ "$terminal" != "[DONE]" ]; then
    fail "$1" "stream ended without exact 'data: [DONE]' terminal frame (mid-stream drop is an honest failure): last='$terminal'" "$2"
    return 1
  fi
  # every non-terminal frame must parse as JSON with a delta chunk
  frames_file="$STATE_DIR/frames_$1.txt"
  grep '^data:' "$body_file" | sed 's/^data:[[:space:]]*//' | tr -d '\r' > "$frames_file"
  bad_frames=0
  while IFS= read -r frame; do
    [ "$frame" = "[DONE]" ] && continue
    printf '%s' "$frame" | jq -e '.choices[0].delta != null' >/dev/null 2>&1 || bad_frames=$((bad_frames + 1))
  done < "$frames_file"
  if [ "$bad_frames" != "0" ]; then
    fail "$1" "$bad_frames SSE frame(s) missing choices[0].delta or unparseable — frame contract violation" "$2"
    return 1
  fi
  ok "$1" "model=$2 SSE 200, frames valid, terminal [DONE] exact, TTFT=${ttft}s"
}

run_matrix() { # $1 = "nonstream" | "stream" | "all"
  i=0
  while [ $i -lt 5 ]; do
    i=$((i + 1))
    m=$(model_at $((i - 1)))
    if [ "$1" != "stream" ]; then nonstream_call "ns$i" "$m" || true; fi
    if [ "$1" != "nonstream" ]; then stream_call "st$i" "$m" || true; fi
  done
}

main() {
  sub="${1:-all}"
  case "$sub" in
    help|-h)
      sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    all|nonstream|stream) ;;
    *)
      printf 'unknown subcommand: %s (use: all | nonstream | stream | help)\n' "$sub"
      exit 1
      ;;
  esac
  require_env
  printf 'SupremeAI E2E smoke — gateway=%s models=[%s] subset=%s\n' "$GATEWAY_URL" "$MODELS" "$sub"
  run_matrix "$sub"
  total=$((passed + failures))
  printf 'RESULT: %s/%s calls passed (fail-closed — failures listed above are honest)\n' "$passed" "$total"
  [ "$failures" -eq 0 ]
}

main "$@"
