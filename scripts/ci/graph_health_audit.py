#!/usr/bin/env python3
"""Graph Health Auditor — SupremeAI Ecosystem Graph-এর স্বয়ংক্রিয় ডাক্তর (issue #2399).

Deliverable #4: "মিসিং এজ, ডুপ্লিকেট নোড বা ড্যাংলার সেন্টার চিহ্নিত করার স্বয়ংক্রিয়
অডিট টুল।"

এই টুল `docs/architecture/ECOSYSTEM_GRAPH_REGISTRY.yaml` (একমাত্র source of
truth) পড়ে ১২টি health invariant (REG-01..REG-12) যাচাই করে — registry-র
নিজের ঘোষিত health_invariants সেকশনের সাথে মিলিয়ে:

  REG-01  unique-node-ids            প্রতিটি node.id অনন্য                (HIGH)
  REG-02  no-duplicate-node-paths    এক path দুই node-এ নয়               (HIGH)
  REG-03  node-domain-valid          node.domain বৈধ domain-এ              (HIGH)
  REG-04  node-path-exists           node.path/owning_path ডিস্কে আছে      (MEDIUM)
  REG-05  edge-endpoints-valid       edge from/to বৈধ                      (HIGH)
  REG-06  no-dangling-centers        প্রতিটি domain-এর নোড+পথ আছে          (HIGH)
  REG-07  db-map-full-coverage       সব backend/models/*.py ম্যাপড          (HIGH)
  REG-08  db-map-no-stale-entries    মৃত (ডিস্কে নেই) মডেল ম্যাপে নয়       (HIGH)
  REG-09  db-map-domain-valid        ম্যাপের domain বৈধ                     (HIGH)
  REG-10  eight-questions-complete   ৮ গোল্ডেন প্রশ্নের উত্তর অ-খালি        (HIGH)
  REG-11  group-boundary-paths-exist গ্রুপের allowed_paths ডিস্কে আছে      (MEDIUM)
  REG-12  no-group-boundary-overlap  দুই গ্রুপের পথ overlap নয়            (HIGH)

Usage:
    python scripts/ci/graph_health_audit.py
    python scripts/ci/graph_health_audit.py --fail-on MEDIUM --report audit.json
    python scripts/ci/graph_health_audit.py --format json

Exit codes:
    0 = clean (বা fail-on threshold-এর নিচের findings)
    1 = threshold-এর সমান/উপরের severity-র finding আছে
    2 = registry পড়াই গেল না (CRITICAL)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = REPO_ROOT / "docs/architecture/ECOSYSTEM_GRAPH_REGISTRY.yaml"
MODELS_DIR = REPO_ROOT / "backend/models"

# ৮টি গোল্ডেন প্রশ্নের key — registry-র eight_questions_spec এর সাথে lockstep
EIGHT_QUESTIONS_KEYS = (
    "identity",
    "responsibility",
    "upstream",
    "downstream",
    "side_effects",
    "verification",
    "blast_radius",
    "ultimate_value",
)

# severity ranking — বড় মানে বড় বিপদ
SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

# base plumbing ফাইল — বিজনেস ডোমেইন নয়, তাই db-map coverage থেকে বাদ
MODEL_COVERAGE_EXEMPT = {"__init__.py", "base.py"}


class AuditFinding:
    """একটি graph health finding — invariant, severity, মানবপাঠ্য বার্তা।"""

    def __init__(self, invariant: str, severity: str, message: str) -> None:
        self.invariant = invariant
        self.severity = severity
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {
            "invariant": self.invariant,
            "severity": self.severity,
            "message": self.message,
        }

    def __str__(self) -> str:
        return f"[{self.severity}] {self.invariant}: {self.message}"


def load_registry(path: Path) -> dict[str, Any]:
    """Registry YAML লোড — ভাঙলে CRITICAL (audit চলবেই না, exit 2)।"""
    try:
        import yaml
    except ImportError:
        print("CRITICAL: PyYAML ইনস্টল নেই — registry পড়া যাচ্ছে না", file=sys.stderr)
        raise SystemExit(2)
    if not path.exists():
        print(f"CRITICAL: registry file নেই: {path}", file=sys.stderr)
        raise SystemExit(2)
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as err:
        print(f"CRITICAL: YAML parse error: {err}", file=sys.stderr)
        raise SystemExit(2)
    if not isinstance(data, dict):
        print("CRITICAL: registry root টা mapping নয়", file=sys.stderr)
        raise SystemExit(2)
    return data


def _as_list(value: Any) -> list[Any]:
    """None-safe list রূপান্তর (YAML খালি হলে None দেয়)।"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _answer_nonempty(answer: Any) -> bool:
    """৮-প্রশ্নের একটি উত্তর অ-খালি কিনা — string হলে strip, list হলে দৈর্ঘ্য।"""
    if answer is None:
        return False
    if isinstance(answer, (list, tuple)):
        return len(answer) > 0
    if isinstance(answer, str):
        return bool(answer.strip())
    return True


def check_eight_questions(
    findings: list[AuditFinding],
    kind: str,
    item_id: str,
    eight: Any,
) -> None:
    """REG-10: ৮টি গোল্ডেন প্রশ্নের প্রতিটির উত্তর আছে ও অ-খালি।"""
    if not isinstance(eight, dict):
        findings.append(
            AuditFinding(
                "REG-10", "HIGH",
                f"{kind} '{item_id}' — eight_questions ব্লকই নেই",
            )
        )
        return
    for key in EIGHT_QUESTIONS_KEYS:
        if not _answer_nonempty(eight.get(key)):
            findings.append(
                AuditFinding(
                    "REG-10", "HIGH",
                    f"{kind} '{item_id}' — প্রশ্ন '{key}' এর উত্তর খালি/অনুপস্থিত",
                )
            )


def audit_registry(registry: dict[str, Any], repo_root: Path) -> list[AuditFinding]:
    """পুরো ১২-invariant অডিট — সব finding একত্র করে ফেরত দেয়।"""
    findings: list[AuditFinding] = []

    domains = registry.get("domains") or []
    nodes = registry.get("nodes") or []
    core_truths = registry.get("core_truths") or []
    edges = registry.get("edges") or []
    db_map = registry.get("db_model_domain_map") or {}
    groups = registry.get("group_boundaries") or []

    domain_ids = {d.get("id") for d in domains if isinstance(d, dict) and d.get("id")}
    node_ids = {n.get("id") for n in nodes if isinstance(n, dict) and n.get("id")}
    core_ids = {c.get("id") for c in core_truths if isinstance(c, dict) and c.get("id")}
    valid_endpoints = domain_ids | node_ids | core_ids

    # ── REG-01: unique node ids ──
    seen_ids: dict[str, int] = {}
    for node in nodes:
        if isinstance(node, dict) and node.get("id"):
            seen_ids[node["id"]] = seen_ids.get(node["id"], 0) + 1
    for node_id, count in seen_ids.items():
        if count > 1:
            findings.append(
                AuditFinding(
                    "REG-01", "HIGH",
                    f"node id '{node_id}' {count} বার declare হয়েছে — duplicate নোড নিষিদ্ধ",
                )
            )

    # ── REG-02: no duplicate node paths ──
    seen_paths: dict[str, list[str]] = {}
    for node in nodes:
        if isinstance(node, dict) and node.get("path"):
            seen_paths.setdefault(node["path"], []).append(str(node.get("id")))
    for path, owners in seen_paths.items():
        if len(owners) > 1:
            findings.append(
                AuditFinding(
                    "REG-02", "HIGH",
                    f"path '{path}' একাধিক node-এ ({', '.join(owners)}) — 1 পথ = 1 মালিক",
                )
            )

    # ── REG-03 + REG-04 + REG-10 (nodes): per-node checks ──
    for node in nodes:
        if not isinstance(node, dict) or not node.get("id"):
            findings.append(
                AuditFinding("REG-01", "HIGH", f"id-বিহীন node declare হয়েছে: {node!r:.120}")
            )
            continue
        node_id = node["id"]
        node_domain = node.get("domain")
        if node_domain not in domain_ids:
            findings.append(
                AuditFinding(
                    "REG-03", "HIGH",
                    f"node '{node_id}' — domain '{node_domain}' রেজিস্ট্রিতে নেই (dangling node)",
                )
            )
        node_path = node.get("path")
        if node_path and not (repo_root / node_path).exists():
            findings.append(
                AuditFinding(
                    "REG-04", "MEDIUM",
                    f"node '{node_id}' — path '{node_path}' ডিস্কে নেই (planned node কি?)",
                )
            )
        check_eight_questions(findings, "node", node_id, node.get("eight_questions"))

    # ── REG-10 (core truths + domains) + REG-04 (owning paths) ──
    for core in core_truths:
        if isinstance(core, dict) and core.get("id"):
            check_eight_questions(findings, "core", core["id"], core.get("eight_questions"))
    for domain in domains:
        if not isinstance(domain, dict) or not domain.get("id"):
            continue
        domain_id = domain["id"]
        check_eight_questions(findings, "domain", domain_id, domain.get("eight_questions"))
        for owning in _as_list(domain.get("owning_paths")):
            if not (repo_root / str(owning)).exists():
                findings.append(
                    AuditFinding(
                        "REG-04", "MEDIUM",
                        f"domain '{domain_id}' — owning_path '{owning}' ডিস্কে নেই",
                    )
                )

    # ── REG-05: edge endpoints valid ──
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        for side in ("from", "to"):
            endpoint = edge.get(side)
            if endpoint and endpoint not in valid_endpoints:
                findings.append(
                    AuditFinding(
                        "REG-05", "HIGH",
                        f"edge {edge.get('from', '?')} → {edge.get('to', '?')} — "
                        f"'{endpoint}' বৈধ domain/node id নয় (missing edge endpoint)",
                    )
                )

    # ── REG-06: no dangling centers (নোড ও বাস্তবে-থাকা পথ ছাড়া কেন্দ্র নিষিদ্ধ) ──
    for domain in domains:
        if not isinstance(domain, dict) or not domain.get("id"):
            continue
        domain_id = domain["id"]
        node_count = sum(
            1 for n in nodes if isinstance(n, dict) and n.get("domain") == domain_id
        )
        if node_count == 0:
            findings.append(
                AuditFinding(
                    "REG-06", "HIGH",
                    f"domain '{domain_id}' — একটিও node নেই (dangling center)",
                )
            )
        live_paths = [
            p for p in _as_list(domain.get("owning_paths"))
            if (repo_root / str(p)).exists()
        ]
        if not live_paths:
            findings.append(
                AuditFinding(
                    "REG-06", "HIGH",
                    f"domain '{domain_id}' — একটিও বাস্তব owning_path নেই (dangling center)",
                )
            )

    # ── REG-07/08/09: DB model → domain map ──
    if MODELS_DIR.exists():
        on_disk = {
            p.name for p in MODELS_DIR.glob("*.py") if p.name not in MODEL_COVERAGE_EXEMPT
        }
        mapped = {str(k) for k in db_map.keys()}
        for missing in sorted(on_disk - mapped):
            findings.append(
                AuditFinding(
                    "REG-07", "HIGH",
                    f"DB model '{missing}' db_model_domain_map-এ নেই — গ্রাফে অনাথ schema নোড",
                )
            )
        for stale in sorted(mapped - on_disk):
            findings.append(
                AuditFinding(
                    "REG-08", "HIGH",
                    f"db_model_domain_map-এ '{stale}' আছে কিন্তু backend/models-এ ফাইলটি নেই (stale)",
                )
            )
    for model_file, domain_id in db_map.items():
        if domain_id not in domain_ids:
            findings.append(
                AuditFinding(
                    "REG-09", "HIGH",
                    f"DB model '{model_file}' — অজানা domain '{domain_id}'",
                )
            )

    # ── REG-11: group boundary paths exist ──
    for group in groups:
        if not isinstance(group, dict) or not group.get("group"):
            continue
        group_id = group["group"]
        for allowed in _as_list(group.get("allowed_paths")):
            if not (repo_root / str(allowed)).exists():
                findings.append(
                    AuditFinding(
                        "REG-11", "MEDIUM",
                        f"group '{group_id}' — allowed_path '{allowed}' ডিস্কে নেই",
                    )
                )

    # ── REG-12: no group boundary overlap ──
    # বাংলা মন্তব্য: এক file/path subtree দুই সক্রিয় গ্রুপের হাতে গেলে সংঘর্ষ —
    # "1 পথ = 1 মালিক" নীতি। identical বা ancestor/descendant দুই-ই overlap।
    group_paths: list[tuple[str, str]] = []
    for group in groups:
        if not isinstance(group, dict) or not group.get("group"):
            continue
        for allowed in _as_list(group.get("allowed_paths")):
            group_paths.append((str(group["group"]), str(allowed)))
    for i, (owner_a, path_a) in enumerate(group_paths):
        for owner_b, path_b in group_paths[i + 1:]:
            if owner_a == owner_b:
                continue
            if path_a == path_b or path_a.startswith(path_b + "/") or path_b.startswith(path_a + "/"):
                findings.append(
                    AuditFinding(
                        "REG-12", "HIGH",
                        f"গ্রুপ '{owner_a}' ও '{owner_b}' — পথ overlap: '{path_a}' বনাম '{path_b}'",
                    )
                )

    return findings


def build_report(registry: dict[str, Any], findings: list[AuditFinding]) -> dict[str, Any]:
    """Machine-readable রিপোর্ট — CI artifact ও dashboard এর জন্য।"""
    by_severity: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for finding in findings:
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
    domains = registry.get("domains") or []
    nodes = registry.get("nodes") or []
    return {
        "schema_version": registry.get("schema_version", "unknown"),
        "issue": 2399,
        "stats": {
            "core_truths": len(registry.get("core_truths") or []),
            "domains": len(domains),
            "nodes": len(nodes),
            "edges": len(registry.get("edges") or []),
            "db_models_mapped": len(registry.get("db_model_domain_map") or {}),
            "groups": len(registry.get("group_boundaries") or []),
        },
        "findings": [f.to_dict() for f in findings],
        "totals": by_severity,
        "healthy": not any(
            SEVERITY_ORDER.get(f.severity, 0) >= SEVERITY_ORDER["HIGH"] for f in findings
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Graph Health Auditor — ECOSYSTEM_GRAPH_REGISTRY অডিট (#2399)"
    )
    parser.add_argument(
        "--registry", default=str(DEFAULT_REGISTRY),
        help="registry YAML path (default: docs/architecture/ECOSYSTEM_GRAPH_REGISTRY.yaml)",
    )
    parser.add_argument(
        "--fail-on", default="HIGH", choices=("CRITICAL", "HIGH", "MEDIUM", "LOW"),
        help="এই severity বা তার উপরের কোনো finding থাকলে exit 1 (default: HIGH)",
    )
    parser.add_argument(
        "--report", default=None,
        help="JSON রিপোর্ট এই ফাইলে লিখবে (CI artifact)",
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="আউটপুট ফরম্যাট (default: text)",
    )
    args = parser.parse_args()

    registry = load_registry(Path(args.registry))
    findings = audit_registry(registry, REPO_ROOT)
    report = build_report(registry, findings)

    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        stats = report["stats"]
        print(f"SupremeAI Ecosystem Graph Health Audit (schema {report['schema_version']})")
        print(f"  domains={stats['domains']} nodes={stats['nodes']} edges={stats['edges']} db_models={stats['db_models_mapped']}")
        if not findings:
            print("  ✅ সব ১২টি invariant পাস — গ্রাফ সুস্থ")
        else:
            for finding in findings:
                print(f"  ❌ {finding}")
            print(f"  মোট finding: {len(findings)} ({report['totals']['HIGH']} HIGH, {report['totals']['MEDIUM']} MEDIUM)")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    threshold = SEVERITY_ORDER[args.fail_on]
    worst = max((SEVERITY_ORDER.get(f.severity, 0) for f in findings), default=0)
    return 1 if worst >= threshold else 0


if __name__ == "__main__":
    sys.exit(main())
