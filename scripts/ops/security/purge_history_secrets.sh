#!/usr/bin/env bash
# HS-01 (issue #504): purge leaked secrets from ALL git history.
#
# Dry-run by default. Pass FORCE_PURGE=1 to actually rewrite history.
# Requires: git-filter-repo (pip install git-filter-repo)
#
# ⚠️  READ docs/security/HS-01-REMEDIATION.md FIRST.
# 1. ROTATE the credentials BEFORE purging — history copies still leak until
#    the keys themselves are dead.
# 2. Rewriting history invalidates every clone and open PR; coordinate a
#    force-push window with the team.
#
# Usage:
#   bash scripts/security/purge_history_secrets.sh --dry-run   # default
#   FORCE_PURGE=1 bash scripts/security/purge_history_secrets.sh
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "ERROR: git-filter-repo not installed.  pip install git-filter-repo" >&2
  exit 1
fi

REPLACEMENTS="$(mktemp)"
trap 'rm -f "$REPLACEMENTS"' EXIT

# --- Secret shapes to neutralize (patterns, never hardcoded values) -------
# Render API keys: rnd_ followed by 20+ alphanumerics
echo 'regex:rnd_[A-Za-z0-9]{20,}===>***REMOVED***' >> "$REPLACEMENTS"
# Infisical universal-auth client secrets: 64-hex strings
echo 'regex:[0-9a-f]{64}===>***REMOVED***' >> "$REPLACEMENTS"
# Firebase service-account JSON snippets that embed private keys
echo 'regex:"private_key":\s*"-----BEGIN PRIVATE KEY-----[^"]+===>***REMOVED***' >> "$REPLACEMENTS"

# --- Optionally add known literal leaked values at runtime ----------------
# Never commit this file. One value per line, format:  <value>===>***REMOVED***
if [ -n "${LEAKED_VALUES_FILE:-}" ] && [ -f "$LEAKED_VALUES_FILE" ]; then
  cat "$LEAKED_VALUES_FILE" >> "$REPLACEMENTS"
  echo "Added $(wc -l < "$LEAKED_VALUES_FILE") literal values from $LEAKED_VALUES_FILE"
fi

# --- Known files that carried real credentials ----------------------------
PATHS=(
  'docs/Enviorment vs secret key/env_security_auth.md'
  'scripts/sync_secrets_to_frontend.py'
  'scripts/sync_secrets_to_render.py'
  'scripts/check_deploys.py'
  'scripts/check_health_path.py'
  'scripts/check_key.py'
  'scripts/fetch_logs.py'
  'scripts/status.py'
  'scripts/sync_both.py'
  'scripts/test_render_api.py'
  'scripts/trigger.py'
  'scripts/trigger_deploys.py'
)
INVERT_PATHS=()
for p in "${PATHS[@]}"; do INVERT_PATHS+=(--invert-paths "$p"); done

echo "== Dry-run plan =============================================="
echo "Patterns: $(grep -c . "$REPLACEMENTS") replacement rules"
echo "Files to remove from history:"
printf '  - %s\n' "${PATHS[@]}"

if [ "${FORCE_PURGE:-0}" != "1" ]; then
  echo
  echo "DRY-RUN ONLY. To execute:  FORCE_PURGE=1 bash $0"
  echo "(run with --analyze for git-filter-repo's own report first)"
  [ "${1:-}" = "--analyze" ] && git filter-repo --analyze
  exit 0
fi

echo "== Rewriting history (this invalidates all clones) ==========="
git filter-repo --force --replace-text "$REPLACEMENTS" "${INVERT_PATHS[@]}"

echo
echo "Done. Now coordinate the push (rewrites every SHA):"
echo "  git push --force --all && git push --force --tags"
echo "Then make every teammate re-clone. See docs/security/HS-01-REMEDIATION.md"
