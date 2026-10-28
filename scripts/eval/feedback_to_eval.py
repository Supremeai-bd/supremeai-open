#!/usr/bin/env python3
"""Convert negative user feedback into sanitized candidate evaluation cases.

WO #1363 contract item 2 (AIQ-107): safely turn user feedback (thumbs_down,
correction, and optionally weak signals like retry/regenerate) recorded in the
durable learning plane (``learning_events`` table, fed by
``core.learning.store.LearningStore``) into candidate evaluation cases.

Privacy contract (mirrors core.learning.store.sanitize_metadata):
- Raw prompt/response/content keys are NEVER emitted, at any depth.
- Only the fixed allowlist of event fields is serialized.
- Output is deterministic: rows sorted by event_id, stable key order.

Usage:
    python scripts/eval/feedback_to_eval.py --dsn "$DATABASE_URL" [--out PATH]
        [--limit N] [--include-weak] [--dry-run]

Exit codes: 0 success (including zero rows), 1 usage/DB error, 2 partial
write failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

DEFAULT_OUT = "data/eval/feedback_candidates.jsonl"

# Negative categories converted to eval candidates by default. "retry" and
# "regenerate" are weak negative signals — opt-in via --include-weak.
NEGATIVE_FEEDBACK_TYPES = frozenset({"thumbs_down", "correction"})
WEAK_NEGATIVE_FEEDBACK_TYPES = frozenset({"retry", "regenerate"})

# Serialization allowlist — must stay a subset of LEARNING_EVENT_FIELDS and
# must NEVER include free-text content fields.
EMITTED_FIELDS: tuple[str, ...] = (
    "event_id",
    "ts",
    "task_type",
    "skill_id",
    "provider",
    "model",
    "feedback",
    "error_class",
)

_FORBIDDEN_MARKERS = ("prompt", "response", "content")


def sanitize_mapping(value: Any, _depth: int = 0) -> dict[str, Any]:
    """Privacy-safe copy of a mapping: drop forbidden keys at any depth."""
    if not isinstance(value, dict) or _depth > 4:
        return {}
    clean: dict[str, Any] = {}
    for key, val in value.items():
        key_lower = str(key).lower()
        if any(marker in key_lower for marker in _FORBIDDEN_MARKERS):
            continue  # privacy: never serialize prompt/response/content
        if isinstance(val, dict):
            nested = sanitize_mapping(val, _depth + 1)
            if nested:
                clean[str(key)] = nested
            continue
        if isinstance(val, (int, float, bool)) or isinstance(val, str):
            clean[str(key)] = val if isinstance(val, (int, float, bool)) else str(val)[:120]
    return clean


def row_to_candidate(row: dict[str, Any]) -> dict[str, Any]:
    """Map one learning_events row to a candidate eval case (allowlist emit)."""
    candidate: dict[str, Any] = {"id": f"eval-fb-{int(row['event_id'])}", "source": "feedback"}
    for field in EMITTED_FIELDS:
        val = row.get(field)
        if val is None:
            continue
        if field == "ts" and hasattr(val, "isoformat"):
            val = val.isoformat()
        candidate[field] = val
    # Metadata is scrubbed separately and never carries raw content.
    scrubbed = sanitize_mapping(row.get("metadata") or {})
    if scrubbed:
        candidate["metadata"] = scrubbed
    return candidate


def select_negative_rows(rows: Iterable[dict[str, Any]], include_weak: bool = False) -> list[dict[str, Any]]:
    allowed = set(NEGATIVE_FEEDBACK_TYPES) | (set(WEAK_NEGATIVE_FEEDBACK_TYPES) if include_weak else set())
    picked = [r for r in rows if str(r.get("feedback") or "") in allowed]
    picked.sort(key=lambda r: int(r.get("event_id") or 0))
    return picked


def fetch_rows(dsn: str, limit: int) -> list[dict[str, Any]]:
    """Read feedback rows from the durable learning plane (Postgres)."""
    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise SystemExit(
            "psycopg is required to read the learning plane; install it or run "
            "with a rows file via --rows-file for offline processing"
        ) from exc

    cols = ", ".join(EMITTED_FIELDS + ("metadata",))
    query = f"SELECT {cols} FROM learning_events WHERE feedback = ANY(%s) ORDER BY event_id LIMIT %s"
    types = sorted(NEGATIVE_FEEDBACK_TYPES | WEAK_NEGATIVE_FEEDBACK_TYPES)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(query, (types, limit))
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def load_rows_file(path: str) -> list[dict[str, Any]]:
    """Load rows from a JSONL/JSON file (offline mode, testable without a DB)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("rows") or []
    return list(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("LEARNING_DB_DSN", ""), help="Postgres DSN for learning_events")
    parser.add_argument("--rows-file", default="", help="offline mode: read rows from this JSONL/JSON file")
    parser.add_argument("--out", default=DEFAULT_OUT, help=f"output JSONL path (default {DEFAULT_OUT})")
    parser.add_argument("--limit", type=int, default=500, help="max rows to fetch (default 500)")
    parser.add_argument("--include-weak", action="store_true", help="also convert retry/regenerate signals")
    parser.add_argument("--dry-run", action="store_true", help="print candidates to stdout instead of writing")
    args = parser.parse_args(argv)

    if args.rows_file:
        rows = load_rows_file(args.rows_file)
    elif args.dsn:
        rows = fetch_rows(args.dsn, args.limit)
    else:
        parser.error("provide --dsn (or LEARNING_DB_DSN) or --rows-file")
        return 1

    picked = select_negative_rows(rows, include_weak=args.include_weak)
    candidates = [row_to_candidate(r) for r in picked]

    if args.dry_run:
        for candidate in candidates:
            print(json.dumps(candidate, sort_keys=True))
        print(f"# {len(candidates)} candidate(s) from {len(rows)} row(s)", file=sys.stderr)
        return 0

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate, sort_keys=True) + "\n")
            written += 1
    print(f"wrote {written} candidate(s) to {out_path} (from {len(rows)} row(s))")
    return 0 if written == len(candidates) else 2


if __name__ == "__main__":
    raise SystemExit(main())
