#!/bin/bash
set -e

echo "🧹 Initiating Smart Cache Purge Engine..."

# Calculate the date 7 days ago in ISO 8601 format
SEVEN_DAYS_AGO=$(date -d '7 days ago' -Iseconds)
THRESHOLD_EPOCH=$(date -d "$SEVEN_DAYS_AGO" +%s)

echo "🔍 Fetching cache list..."
gh cache list --limit 100 --json key,createdAt -q '.[] | "\(.key)|\(.createdAt)"' | while IFS="|" read -r key created_at; do
    if [[ -z "$key" ]]; then
        continue
    fi

    # Convert createdAt to epoch for comparison
    CREATED_EPOCH=$(date -d "$created_at" +%s)

    if [[ "$CREATED_EPOCH" -lt "$THRESHOLD_EPOCH" ]]; then
        echo "🗑️ Deleting cache older than 7 days: $key (Created: $created_at)"
        gh cache delete "$key" || true
    else
        echo "✅ Keeping recent cache: $key"
    fi
done

echo "✅ Smart cache pruning complete."
