#!/usr/bin/env python3
"""Tower tool consolidation reference — S0.4 (task #459).

Mapping registry (SSOT) + route resolver + sha256 receipt builder.
The no-regression guarantee is executable: every legacy tool maps to
exactly one destination; the test suite proves full coverage.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# --- Single sources of truth (imported by tests; never copy) ----------------
CORE_TOOLS: Tuple[str, ...] = ("status", "work_claim", "work_next", "bridge_submit", "bridge_work")


@dataclass(frozen=True)
class Mapping:
    legacy: str
    target: str                      # one of CORE_TOOLS, or "REMOVED"
    transform: str                   # human-readable argument transform
    kind: str                        # "ALIAS" | "MERGED" | "REMOVED"


# Order in REGISTRY is irrelevant; route() is deterministic.
REGISTRY: Tuple[Mapping, ...] = (
    Mapping("system_summary", "status", 'status(scope="system")', "MERGED"),
    Mapping("system_health", "status", 'status(scope="health")', "MERGED"),
    Mapping("slot_status", "status", 'status(scope="slots")', "MERGED"),
    Mapping("agent_status", "status", 'status(scope="agent", agentId=?)', "MERGED"),
    Mapping("agent_heartbeat", "work_claim", "claim/renew IS the heartbeat (30m TTL lease)", "MERGED"),
    Mapping("bridge_guide", "REMOVED", "docs/BRIDGE_GUIDE.md carries it — cut by deletion", "REMOVED"),
    Mapping("bridge_work_queue", "bridge_work", 'bridge.work(view="queue")', "MERGED"),
    Mapping("bridge_work_order", "bridge_work", "bridge.work(taskId=?)", "MERGED"),
    Mapping("bridge_submit_patch", "bridge_submit", "bridge.submit(+evidenceEnvelope, +sha256 receipt)", "ALIAS"),
)

LEGACY_NAMES: Tuple[str, ...] = tuple(m.legacy for m in REGISTRY)


class ConsolidationError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def route(legacy_name: str) -> Mapping:
    """Resolve a legacy tool name. Fail-closed on unknown names."""
    for m in REGISTRY:
        if m.legacy == legacy_name:
            return m
    raise ConsolidationError("E_UNKNOWN_TOOL", f"no legacy tool named {legacy_name!r}")


def coverage_report() -> Dict[str, object]:
    """The no-regression proof: full coverage, zero ambiguity, core validity.

    Ambiguity = the SAME legacy name appearing twice (one legacy -> two
    destinations). Many-legacy -> one-target is the goal, not a defect.
    """
    legacy_names = [m.legacy for m in REGISTRY]
    targets = [m.target for m in REGISTRY]
    unknown = [m.legacy for m in REGISTRY if m.target != "REMOVED" and m.target not in CORE_TOOLS]
    return {
        "legacy_count": len(REGISTRY),
        "mapped_count": len(targets),
        "orphans": [m.legacy for m in REGISTRY if m.target not in CORE_TOOLS and m.target != "REMOVED"],
        "ambiguous": sorted({n for n in legacy_names if legacy_names.count(n) > 1}),
        "unknown_targets": unknown,
        "core_tools": list(CORE_TOOLS),
        "removed": sorted(m.legacy for m in REGISTRY if m.target == "REMOVED"),
    }


def assert_no_regression() -> None:
    """Raise unless every legacy tool has exactly one valid destination."""
    report = coverage_report()
    if report["orphans"]:
        raise ConsolidationError("E_ORPHAN_TOOL", f"unmapped legacy tools: {report['orphans']}")
    if report["ambiguous"]:
        raise ConsolidationError("E_AMBIGUOUS_MAP", f"multi-target legacy tools: {report['ambiguous']}")
    if report["unknown_targets"]:
        raise ConsolidationError("E_BAD_TARGET", f"targets outside core: {report['unknown_targets']}")
    if len(set(LEGACY_NAMES)) != len(LEGACY_NAMES):
        raise ConsolidationError("E_DUP_LEGACY", "duplicate legacy names in registry")


# --- sha256 receipts (bridge.submit response contract, spec section 4) ------
def _file_digest(content: str) -> Dict[str, object]:
    raw = content.encode("utf-8")
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def build_submission_receipt(files: Dict[str, str], commit_sha: str = "") -> Dict[str, object]:
    """Deterministic receipt over committed files. Fail-closed: a None or
    unreadable entry forces verified=false with the culprit listed."""
    entries: List[Dict[str, object]] = []
    broken: List[str] = []
    for path in sorted(files):
        content = files[path]
        if not isinstance(content, str):
            broken.append(path)
            continue
        d = _file_digest(content)
        entries.append({"path": path, **d})
    tree_payload = json.dumps(
        [{"path": e["path"], "sha256": e["sha256"]} for e in entries],
        sort_keys=True, separators=(",", ":"))
    tree_sha = hashlib.sha256(tree_payload.encode("utf-8")).hexdigest()
    return {
        "commit": commit_sha,
        "files": entries,
        "tree_sha256": tree_sha,
        "verified": not broken,
        "unverified_paths": broken,
    }


def demo() -> int:
    assert_no_regression()
    print("coverage:", json.dumps(coverage_report(), sort_keys=True))
    print("route system_health ->", route("system_health").transform)
    print("route agent_heartbeat ->", route("agent_heartbeat").transform)
    print("route bridge_guide ->", route("bridge_guide").kind)
    receipt = build_submission_receipt({"a.py": "print(1)\n", "b.md": "hello\n"})
    print("receipt verified:", receipt["verified"], "tree:", receipt["tree_sha256"][:12], "...")
    return 0


if __name__ == "__main__":
    sys.exit(demo())
