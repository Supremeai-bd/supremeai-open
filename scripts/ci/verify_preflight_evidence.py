#!/usr/bin/env python3
"""Verify deployment preflight evidence integrity and schema."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REQUIRED_KEYS = {"schema_version", "generated_at", "status", "required_roles", "accounts", "route_inventory"}


def verify(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing evidence file: {path}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid JSON: {exc}"]
    if not isinstance(payload, dict):
        return ["evidence root must be an object"]
    errors.extend(f"missing key: {key}" for key in sorted(REQUIRED_KEYS - payload.keys()))
    if payload.get("schema_version") not in {"1.0", "1.1"}:
        errors.append("unsupported schema_version")
    if payload.get("status") not in {"ready", "blocked"}:
        errors.append("status must be ready or blocked")
    if not isinstance(payload.get("required_roles"), list):
        errors.append("required_roles must be a list")
    if not isinstance(payload.get("accounts"), list):
        errors.append("accounts must be a list")
    for index, account in enumerate(payload.get("accounts", [])):
        if not isinstance(account, dict):
            errors.append(f"accounts[{index}] must be an object")
            continue
        if account.get("status") not in {"ready", "blocked", "unknown", "cooldown", "recheck_required", "error"}:
            errors.append(f"accounts[{index}] has invalid status")
        if account.get("source") == "estimated_deploy_history" and account.get("confidence") == "verified":
            errors.append(f"accounts[{index}] cannot mark deploy history as verified")

    inventory = payload.get("route_inventory")
    if not isinstance(inventory, dict):
        errors.append("route_inventory must be an object")
    elif inventory.get("status") == "valid":
        if not isinstance(inventory.get("sha256"), str) or len(inventory["sha256"]) != 64:
            errors.append("valid route inventory must include a SHA-256 digest")
        if not isinstance(inventory.get("route_count"), int) or inventory["route_count"] < 0:
            errors.append("valid route inventory must include a non-negative route_count")
    return errors


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ci-reports/render-deploy-preflight.json")
    errors = verify(path)
    if errors:
        for error in errors:
            print(f"::error::{error}")
        return 1
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"preflight evidence verified: {path} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
