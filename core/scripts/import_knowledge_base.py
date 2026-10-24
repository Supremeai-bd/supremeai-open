"""Validate and import the approved SupremeAI knowledge manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED = {
    "knowledge_key",
    "title",
    "domain",
    "namespace",
    "content",
    "source_document",
    "source_section",
    "confidence",
    "risk_level",
    "status",
    "tags",
}
ALLOWED_STATUS = {"draft", "approved", "deprecated"}
ALLOWED_RISK = {"low", "medium", "high", "critical"}

# বাংলা: (?<![a-z])sk- = 'sk-' কিন্তু আগে ছোটহাতের অক্ষর নেই — 'task-'/'risk-'
# ভুয়া-ধনাত্মক বাদ; বাকি তিন প্যাটার্ন (= বা স্পেস-সহ) আগের মতোই।
_SECRET_PATTERN = re.compile(r"api_key=|(?<![a-z])sk-|bearer |password=")


def validate(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    keys: set[str] = set()
    for i, record in enumerate(records):
        missing = REQUIRED - record.keys()
        if missing:
            errors.append(f"record[{i}] missing: {sorted(missing)}")
        key = str(record.get("knowledge_key", ""))
        if not re.fullmatch(r"[a-z0-9_.-]{3,120}", key):
            errors.append(f"record[{i}] invalid knowledge_key")
        if key in keys:
            errors.append(f"duplicate knowledge_key: {key}")
        keys.add(key)
        confidence = record.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append(f"record[{i}] invalid confidence")
        if record.get("status") not in ALLOWED_STATUS:
            errors.append(f"record[{i}] invalid status")
        if record.get("risk_level") not in ALLOWED_RISK:
            errors.append(f"record[{i}] invalid risk_level")
        if not isinstance(record.get("tags"), list):
            errors.append(f"record[{i}] tags must be a list")
        # বাংলা (M23 P-C): 'sk-' হিউরিস্টিকে word-boundary যোগ — আগে 'task-specific',
        # 'risk-' জাতীয় সাধারণ শব্দেও ম্যাচ করে ভুয়া 'possible secret' দিত (false
        # positive), ফলে বৈধ বই-কনটেন্ট আটকে যেত। word-boundary-র পরেও প্রকৃত
        # OpenAI-ধাঁচের কি ('sk-abc…') ধরা পড়ে — precision বাড়ল, সনাক্তকরণ দুর্বল হয়নি।
        if _SECRET_PATTERN.search(json.dumps(record).lower()):
            errors.append(f"record[{i}] possible secret")
    return errors


def content_hash(record: dict[str, Any]) -> str:
    canonical = json.dumps(
        {k: record[k] for k in sorted(record) if k not in {"status"}},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


ROLLBACK_COLUMNS = (
    "title",
    "domain",
    "namespace",
    "content",
    "source",
    "metadata",
    "content_hash",
    "status",
    "confidence",
    "risk_level",
    "source_version",
    "review_after",
)


def _jsonify(value: Any) -> Any:
    """Normalizes values for JSONB parameters (dicts/lists must serialize)."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def capture_rollback_snapshot(cur: Any, keys: list[str]) -> dict[str, dict[str, Any] | None]:
    """Snapshots pre-import row state for every manifest knowledge_key.

    None means the row did not exist before this import (delete on rollback).
    The snapshot is stored inside the audit entry's `evidence` JSON so a later
    `--rollback <rollback_id>` can restore the previous state exactly.
    """
    if not keys:
        return {}
    cur.execute(
        "SELECT knowledge_key, title, domain, namespace, content, source, "
        "metadata, content_hash, status, confidence, risk_level, source_version, "
        "review_after FROM knowledge_base WHERE knowledge_key = ANY(%s)",
        (keys,),
    )
    existing: dict[str, dict[str, Any] | None] = {}
    for row in cur.fetchall():
        existing[row[0]] = {
            "title": row[1],
            "domain": row[2],
            "namespace": row[3],
            "content": row[4],
            "source": row[5],
            "metadata": row[6],
            "content_hash": row[7],
            "status": row[8],
            "confidence": row[9],
            "risk_level": row[10],
            "source_version": row[11],
            "review_after": row[12].isoformat() if row[12] is not None else None,
        }
    return {k: existing.get(k) for k in keys}


def rollback_knowledge(cur: Any, snapshot: dict[str, dict[str, Any] | None]) -> tuple[int, int]:
    """Restores rows captured in `capture_rollback_snapshot`.

    Rows that did not exist before the import (snapshot None) are deleted;
    rows that existed are restored to their pre-import values.
    Returns (deleted, restored) row counts.
    """
    deleted = 0
    restored = 0
    for key, prev in snapshot.items():
        if prev is None:
            cur.execute("DELETE FROM knowledge_base WHERE knowledge_key = %s", (key,))
            deleted += cur.rowcount
            continue
        cur.execute(
            "UPDATE knowledge_base SET title=%s, domain=%s, namespace=%s, "
            "content=%s, source=%s, metadata=%s::jsonb, content_hash=%s, "
            "status=%s, confidence=%s, risk_level=%s, source_version=%s, "
            "review_after=%s, updated_at=NOW() WHERE knowledge_key=%s",
            (
                prev.get("title"),
                prev.get("domain"),
                prev.get("namespace"),
                prev.get("content"),
                prev.get("source"),
                _jsonify(prev.get("metadata")),
                prev.get("content_hash"),
                prev.get("status"),
                prev.get("confidence"),
                prev.get("risk_level"),
                prev.get("source_version"),
                prev.get("review_after"),
                key,
            ),
        )
        restored += cur.rowcount
    return deleted, restored


def run_rollback(rollback_id: str) -> int:
    """Restores the database to its pre-import state for a given rollback_id.

    Uses the rollback snapshot embedded in knowledge_import_audits.evidence at
    import time. Best-effort restores only the rows the import touched and
    records `rolled_back_at` on the audit row for external verification.
    """
    import psycopg2

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT manifest_hash, source_version, imported_count, evidence "
                "FROM knowledge_import_audits WHERE rollback_id = %s",
                (rollback_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise SystemExit(f"Unknown rollback_id: {rollback_id}")
            evidence = row[3]
            if isinstance(evidence, str):
                evidence = json.loads(evidence)
            snapshot = evidence.get("rollback") if isinstance(evidence, dict) else None
            if not snapshot:
                raise SystemExit(f"No rollback snapshot found for {rollback_id} — cannot rollback")
            deleted, restored = rollback_knowledge(cur, snapshot)
            cur.execute(
                "UPDATE knowledge_import_audits SET "
                "evidence = evidence::jsonb || %s::jsonb WHERE rollback_id = %s",
                (
                    json.dumps({"rolled_back_at": datetime.now(UTC).isoformat()}),
                    rollback_id,
                ),
            )
    print(
        json.dumps(
            {
                "rollback_id": rollback_id,
                "deleted_rows": deleted,
                "restored_rows": restored,
                "rolled_back": True,
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "manifest", nargs="?", default="backend/data/supremeai_long_term_knowledge_v1.json"
    )
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--rollback",
        help="Roll back a previous import using its rollback_id (see audit evidence)",
    )
    args = parser.parse_args()
    if args.rollback:
        if args.validate_only:
            raise SystemExit("--rollback cannot be combined with --validate-only")
        return run_rollback(args.rollback)
    payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    records = payload.get("records", [])
    errors = validate(records)
    result = {
        "manifest_version": payload.get("manifest_version"),
        "record_count": len(records),
        "errors": errors,
        "manifest_hash": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
    }
    if errors:
        print(json.dumps(result, indent=2))
        return 2
    if args.validate_only:
        print(json.dumps(result, indent=2))
        return 0
    try:
        import psycopg2
    except ImportError:
        raise SystemExit(
            "psycopg2 is required for database import; use --validate-only for offline validation"
        )
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    rollback_id = f"knowledge-import-{uuid.uuid4()}"
    with conn:
        with conn.cursor() as cur:
            keys = [record["knowledge_key"] for record in records]
            # Pre-import snapshot so `--rollback <rollback_id>` can restore state.
            snapshot = capture_rollback_snapshot(cur, keys)
            for record in records:
                digest = content_hash(record)
                metadata = {
                    k: record[k]
                    for k in ("when_to_use", "decision_rules", "anti_patterns", "tags")
                    if k in record
                }
                cur.execute(
                    """INSERT INTO knowledge_base (id, knowledge_key, title, domain, namespace, content, source, metadata, content_hash, status, confidence, risk_level, source_version, review_after, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,NOW()+INTERVAL '180 days',NOW()) ON CONFLICT (knowledge_key) DO UPDATE SET title=EXCLUDED.title, domain=EXCLUDED.domain, content=EXCLUDED.content, source=EXCLUDED.source, metadata=EXCLUDED.metadata, content_hash=EXCLUDED.content_hash, source_version=EXCLUDED.source_version, updated_at=NOW() WHERE knowledge_base.status <> 'approved' OR knowledge_base.content_hash = EXCLUDED.content_hash""",
                    (
                        record["knowledge_key"],
                        record["knowledge_key"],
                        record["title"],
                        record["domain"],
                        record["namespace"],
                        record["content"],
                        f"{record['source_document']}#{record['source_section']}",
                        json.dumps(metadata),
                        digest,
                        record["status"],
                        record["confidence"],
                        record["risk_level"],
                        payload["source_version"],
                    ),
                )
            cur.execute(
                "INSERT INTO knowledge_import_audits (manifest_hash, source_version, imported_count, rollback_id, evidence) VALUES (%s,%s,%s,%s,%s::jsonb)",
                (
                    result["manifest_hash"],
                    payload["source_version"],
                    len(records),
                    rollback_id,
                    json.dumps(
                        {
                            "tool": "import_knowledge_base.py",
                            "timestamp": datetime.now(UTC).isoformat(),
                            **({"rollback": snapshot} if snapshot else {}),
                        },
                        default=str,
                    ),
                ),
            )
    print(json.dumps({**result, "rollback_id": rollback_id}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
