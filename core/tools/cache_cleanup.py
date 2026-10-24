#!/usr/bin/env python3
import os
import sys

try:
    import redis
except ImportError:  # pragma: no cover
    print(
        "ERROR: redis package is required. Install with `python -m pip install redis`."
    )
    sys.exit(1)


def scan_keys(client, pattern: str) -> list[str]:
    try:
        return list(client.scan_iter(match=pattern, count=1000))
    except Exception as scan_err:
        print(
            f"WARNING: scan_iter failed: {scan_err}. Falling back to KEYS pattern scan."
        )
        try:
            return client.keys(pattern)
        except Exception as keys_err:
            print(f"ERROR: Fallback keys scan failed: {keys_err}")
            return []


def clear_stale_cache() -> int:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        print("REDIS_URL is not configured. Skipping cache cleanup.")
        return 0

    client = redis.from_url(redis_url, decode_responses=True)
    patterns = ["temp_cache:*"]
    deleted_keys = []

    for pattern in patterns:
        print(f"Scanning Redis for keys matching: {pattern}")
        keys = scan_keys(client, pattern)
        if not keys:
            print(f"  No keys found for pattern: {pattern}")
            continue
        deleted_keys.extend(keys)

    if not deleted_keys:
        print("No stale cache keys found.")
        return 0

    print(f"Deleting {len(deleted_keys)} stale cache key(s)...")
    client.delete(*deleted_keys)
    return len(deleted_keys)


if __name__ == "__main__":
    count = clear_stale_cache()
    if count > 0:
        print(f"Deleted {count} stale cache key(s).")
    sys.exit(0)
