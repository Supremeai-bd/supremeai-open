#!/usr/bin/env bash
# check_internal_topology.sh — public-repo internal-topology grep gate (issue #703)
#
# Fails when internal infrastructure identifiers appear in TRACKED files:
#   1. Render service URLs            -> *.onrender[.]com
#   2. Supabase project references    -> <20-char-ref>.supabase.(co|com|net)
#   3. Cloudflare account/namespace IDs -> 32-hex (word-bounded)
#
# Occurrences that are genuinely unavoidable (live config for running services,
# test fixtures, detection tooling, point-in-time audit artifacts) are pinned in
# scripts/security/internal_topology_baseline.txt as "path:count" lines.
# The baseline only shrinks over time — remove lines as scrubbing completes.
#
# Failure modes:
#   - a tracked file matches that has no baseline line        -> FAIL (new leak)
#   - a baselined file's match count GREW beyond its baseline -> FAIL (regrowth)
#
# Exit codes: 0 = pass, 1 = violations found.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

BASELINE="scripts/security/internal_topology_baseline.txt"
SELF="scripts/security/check_internal_topology.sh"

# Combined POSIX ERE. The 32-hex branch is boundary-guarded so 40-hex commit
# SHAs and 64-hex hashes never match, while bare 32-hex IDs still do.
PATTERN='onrender\.com|[a-z0-9]{20}\.supabase\.(co|com|net)|(^|[^0-9a-f])[a-f0-9]{32}([^0-9a-f]|$)'

# Lockfiles are machine-generated and not meaningfully editable; the gate's own
# two files are trusted by construction.
EXCLUDES=(
  --
  .
  ":(exclude)${SELF}"
  ":(exclude)${BASELINE}"
  ":(exclude)package-lock.json"
  ":(exclude)bun.lock"
)

if [ ! -f "$BASELINE" ]; then
  echo "::error::missing baseline file: ${BASELINE}" >&2
  exit 1
fi

# "path:count" lines for every tracked file with >=1 matching line (exit 1 when
# none — tolerated via || true).
current="$(git grep -cE "$PATTERN" "${EXCLUDES[@]}" || true)"

fail=0
while IFS= read -r entry; do
  [ -z "$entry" ] && continue
  path="${entry%%:*}"
  count="${entry##*:}"
  base="$(awk -F':' -v p="$path" '$1 == p { print $2; exit }' "$BASELINE")"
  if [ -z "$base" ]; then
    echo "::error file=${path}::internal topology identifier found in tracked file (no baseline entry): ${count} matching line(s)" >&2
    fail=1
  elif [ "$count" -gt "$base" ]; then
    echo "::error file=${path}::internal topology occurrences grew: ${count} > baseline ${base}" >&2
    fail=1
  elif [ "$count" -lt "$base" ]; then
    echo "note: ${path} shrank to ${count} (baseline ${base}) — prune the baseline line when it reaches 0" >&2
  fi
done <<< "$current"

# Stale baseline entries (file no longer matches at all) are informational —
# shrinking is the intended direction; remind maintainers to prune.
while IFS= read -r bline; do
  case "$bline" in ''|'#'*) continue ;; esac
  bpath="${bline%%:*}"
  if ! git grep -qE "$PATTERN" -- "$bpath" 2>/dev/null; then
    echo "note: stale baseline entry (0 occurrences now) — remove the line: ${bpath}" >&2
  fi
done < "$BASELINE"

if [ "$fail" -ne 0 ]; then
  echo "" >&2
  echo "Internal topology gate FAILED (#703)." >&2
  echo "Scrub the identifier (placeholder / env-var indirection) or — only for genuinely unavoidable live config —" >&2
  echo "update ${BASELINE} intentionally in the same PR." >&2
  exit 1
fi

echo "Internal topology gate passed: no leaks beyond baseline."
