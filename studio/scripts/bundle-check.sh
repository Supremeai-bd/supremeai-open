#!/usr/bin/env bash
# AETHEL Command Center — Bundle size check
# বাংলা মন্তব্য: Vite build output এর gzip size চেক — রulเกิน하면 fail

set -euo pipefail

DIST_DIR="${1:-dist}"
MAX_INITIAL_KB=250
MAX_TOTAL_KB=900

if [ ! -d "$DIST_DIR" ]; then
  echo "ERROR: $DIST_DIR not found. Run build first."
  exit 1
fi

# Find all .js/.css files and compute gzip size
declare -a sizes=()
initial_chunk=""

# Identify initial chunk (usually index.html references)
if [ -f "$DIST_DIR/index.html" ]; then
  initial_chunk=$(grep -oP 'src="[^"]+\.js"' "$DIST_DIR/index.html" | head -1 | sed 's/src="//;s/"//')
fi

total_bytes=0
initial_bytes=0
violations=0

while IFS= read -r -d '' file; do
  rel="${file#"$DIST_DIR"/}"
  gz_size=$(gzip -c "$file" | wc -c)
  kb=$((gz_size / 1024))
  sizes+=("$kb|$rel")
  total_bytes=$((total_bytes + gz_size))

  # Check if this is the initial chunk
  if [ -n "$initial_chunk" ] && [[ "$rel" == "$initial_chunk" ]]; then
    initial_bytes=$gz_size
  fi
done < <(find "$DIST_DIR" -type f \( -name "*.js" -o -name "*.css" \) -print0)

total_kb=$((total_bytes / 1024))

echo "═══ Bundle Size Report ═══"
echo "Total gzipped: ${total_kb}KB"

if [ $initial_bytes -gt 0 ]; then
  initial_kb=$((initial_bytes / 1024))
  echo "Initial chunk (${initial_chunk:-unknown}): ${initial_kb}KB"
  if [ $initial_kb -gt $MAX_INITIAL_KB ]; then
    echo "FAIL: Initial chunk exceeds ${MAX_INITIAL_KB}KB limit"
    violations=$((violations + 1))
  fi
else
  echo "WARN: Could not identify initial chunk for size check"
fi

if [ $total_kb -gt $MAX_TOTAL_KB ]; then
  echo "FAIL: Total bundle exceeds ${MAX_TOTAL_KB}KB limit (${total_kb}KB)"
  violations=$((violations + 1))
fi

echo "Top 10 largest files:"
printf '%s\n' "${sizes[@]}" | sort -t'|' -k1 -rn | head -10 | while IFS='|' read -r kb path; do
  echo "  ${kb}KB — $path"
done

if [ $violations -gt 0 ]; then
  echo "FAIL: $violations bundle size violation(s) found"
  exit 1
fi

echo "PASS: Bundle within size limits"
exit 0