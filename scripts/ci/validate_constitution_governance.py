#!/usr/bin/env python3
"""Validate constitutional governance metadata without contacting production."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exceptions", default=".github/constitution/exceptions.yml")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    path = root / args.exceptions
    if not path.exists():
        print(f"governance file missing: {path}")
        return 1
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
        data = yaml.safe_load(text) or {}
        exemptions = data.get("exemptions") or []
    except ModuleNotFoundError:
        # CI installs PyYAML; keep local verification dependency-free.
        exemptions = []
        for block in text.split("\n  - ")[1:]:
            item = {}
            for line in block.splitlines():
                if ":" in line and not line.lstrip().startswith("#"):
                    key, value = line.strip().split(":", 1)
                    item[key.strip()] = value.strip().strip("\\\"'")
            if item:
                exemptions.append(item)
    except Exception as exc:
        print(f"unable to parse governance file: {exc}")
        return 1
    errors = []
    now = datetime.now(timezone.utc)
    for index, item in enumerate(exemptions, 1):
        for required in ("rule_id", "file_path", "owner", "reason", "expires"):
            if not item.get(required):
                errors.append(f"exemption #{index}: missing {required}")
        if item.get("expires"):
            try:
                expires = datetime.fromisoformat(str(item["expires"]).replace("Z", "+00:00"))
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires <= now:
                    errors.append(f"exemption #{index}: expired at {expires.isoformat()}")
            except ValueError:
                errors.append(f"exemption #{index}: expires must be ISO-8601")
    if errors:
        for error in errors:
            print(f"::error::{error}")
        return 1
    print("constitution governance metadata is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
