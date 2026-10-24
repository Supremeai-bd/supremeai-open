#!/usr/bin/env python3
"""Deterministic policy loading, failure classification, and decision logging."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY_FILE = ROOT / "config" / "merge_policy_registry.json"
DECISION_LOG = ROOT / "ci-reports" / "merge_decisions.jsonl"
SEVERITIES = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def load_policy(path: Path = POLICY_FILE) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("mode") not in {"advisory", "enforced"}:
        raise ValueError("policy mode must be advisory or enforced")
    for severity in data.get("severity_order", []):
        if severity not in SEVERITIES:
            raise ValueError(f"unknown severity: {severity}")
    return data


def classify_result(name: str, group: str, status: str, count: int, policy: dict[str, Any]) -> dict[str, Any]:
    rule = policy.get("checks", {}).get(name) or policy.get("checks", {}).get(group) or {}
    severity = rule.get("severity", "MEDIUM")
    if severity not in SEVERITIES:
        severity = "MEDIUM"
    failed = status in {"FAIL", "ERROR"}
    advisory = policy.get("mode", "advisory") == "advisory"
    return {
        "check": name,
        "group": group,
        "status": status,
        "count": count,
        "severity": severity,
        "owner": rule.get("owner", "unassigned"),
        "blocking": bool(failed and rule.get("blocking", False) and not advisory),
        "classification": "failure" if failed else ("warning" if status == "WARN" else "pass"),
    }


def record_decision(verdict: str, classifications: list[dict[str, Any]], *, path: Path = DECISION_LOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": os.getenv("SUPREMEAI_MERGE_MODE", "advisory"),
        "verdict": verdict,
        "blocking_count": sum(1 for item in classifications if item["blocking"]),
        "classifications": classifications,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
