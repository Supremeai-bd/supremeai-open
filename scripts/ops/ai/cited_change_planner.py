#!/usr/bin/env python3
"""Create an evidence-grounded change plan from deterministic reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def build_plan(impact: dict, drift: dict, metadata: dict) -> dict:
    findings = impact.get("findings", []) + drift.get("findings", [])
    citations = sorted({finding.get("path") for finding in findings if finding.get("path")})
    actions = [
        {"order": 1, "action": "Review changed files and cited findings", "citations": citations},
        {"order": 2, "action": "Resolve deterministic import, configuration, and deployment drift findings", "citations": citations},
        {"order": 3, "action": "Run targeted tests, type checks, and production build", "citations": ["scripts/ai/change_impact_detector.py", "scripts/ai/drift_checks.py"]},
    ]
    status = "blocked" if impact.get("status") == "blocked" else "review" if findings else "proceed"
    return {
        "schema_version": "1.0",
        "decision": status,
        "confidence": "evidence-backed" if metadata else "unknown",
        "assumptions": ["Source files remain authoritative", "No secret values are included in planning input"],
        "citations": citations,
        "actions": actions,
        "findings": findings,
        "limitations": ["This layer does not execute mutations", "AI-generated conclusions must cite this report"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--impact", type=Path, required=True)
    parser.add_argument("--drift", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("ci-reports/cited-change-plan.json"))
    args = parser.parse_args()
    plan = build_plan(load(args.impact), load(args.drift), load(args.metadata))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    return 1 if plan["decision"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
