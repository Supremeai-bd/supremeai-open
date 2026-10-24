"""Offline gate for the approved long-term knowledge curriculum."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

REQUIRED = {"knowledge_key", "title", "domain", "namespace", "content", "source_document", "source_section", "confidence", "risk_level", "status", "tags"}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args()
    path = Path(args.manifest)
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    errors, keys = [], set()
    for index, record in enumerate(records or []):
        missing = REQUIRED - record.keys()
        if missing: errors.append(f"record[{index}] missing {sorted(missing)}")
        key = record.get("knowledge_key", "")
        if not re.fullmatch(r"[a-z0-9_.-]{3,120}", key): errors.append(f"record[{index}] invalid knowledge_key")
        if key in keys: errors.append(f"duplicate key {key}")
        keys.add(key)
        if record.get("status") not in {"draft", "approved", "deprecated"}: errors.append(f"record[{index}] invalid status")
        if record.get("risk_level") not in {"low", "medium", "high", "critical"}: errors.append(f"record[{index}] invalid risk")
        if not isinstance(record.get("confidence"), (int, float)) or not 0 <= record["confidence"] <= 1: errors.append(f"record[{index}] invalid confidence")
        if any(token in json.dumps(record).lower() for token in ("api_key=", "sk-", "bearer ", "password=")): errors.append(f"record[{index}] possible secret")
    result = {"manifest": str(path), "manifest_hash": hashlib.sha256(path.read_bytes()).hexdigest(), "records": len(records or []), "errors": errors}
    print(json.dumps(result, indent=2))
    return 2 if errors else 0

if __name__ == "__main__": raise SystemExit(main())
