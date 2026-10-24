#!/usr/bin/env python3
"""Generate domain dependency evidence from existing source and audit artifacts."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / "docs/generated/domain_dependency_graph.json"
OUT_MMD = ROOT / "docs/generated/domain_dependency_graph.mmd"

DOMAINS = {
    "identity": ("Identity/Auth", ("auth", "identity", "session", "user")),
    "ai": ("AI/LLM", ("ai", "llm", "model", "prompt")),
    "execution": ("Execution/Worker", ("worker", "job", "task", "execution", "queue")),
    "knowledge": ("Memory/Knowledge", ("knowledge", "memory", "embedding", "retriev")),
    "research": ("Browser/Research", ("browser", "research", "scrap", "crawl")),
    "data": ("Data/Storage", ("database", "storage", "migration", "model", "repository")),
    "security": ("Governance/Security", ("security", "governance", "policy", "audit", "rls")),
    "billing": ("Billing", ("billing", "quota", "usage", "payment")),
    "observability": ("Observability", ("observ", "metric", "telemetry", "logging", "trace")),
}
EXCLUDED = {".git", "node_modules", "__pycache__", ".venv", "dist", "build", ".next", "coverage"}


def domain_for(path: str) -> str:
    value = path.lower()
    scores = {key: sum(value.count(token) for token in tokens) for key, (_, tokens) in DOMAINS.items()}
    winner, score = max(scores.items(), key=lambda item: (item[1], item[0]))
    return winner if score else "unassigned"


def py_files() -> list[Path]:
    return sorted(p for base in (ROOT / "backend", ROOT / "scripts") if base.exists() for p in base.rglob("*.py") if not any(part in EXCLUDED for part in p.parts))


def module_names(path: Path) -> set[str]:
    rel = path.relative_to(ROOT).with_suffix("")
    dotted = ".".join(rel.parts)
    return {dotted, dotted.removeprefix("backend.")}


def imports(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append((node.lineno, node.module))
    return result


def build() -> dict:
    files = py_files()
    known = {name: path for path in files for name in module_names(path)}
    edges: set[tuple[str, str, str, int]] = set()
    violations = []
    for source in files:
        source_domain = domain_for(source.relative_to(ROOT).as_posix())
        for line, target_module in imports(source):
            target = known.get(target_module)
            if not target or target == source:
                continue
            target_domain = domain_for(target.relative_to(ROOT).as_posix())
            if source_domain != target_domain and source_domain != "unassigned" and target_domain != "unassigned":
                edges.add((source_domain, target_domain, source.relative_to(ROOT).as_posix(), line))
                same_context = source.parent == target.parent
                # Test files legitimately import production modules to test
                # them — a `_`-prefixed (private) module imported from a
                # test is NOT an architectural boundary violation. Only flag
                # private cross-domain imports between production modules.
                is_test_source = "/tests/" in source.as_posix() or source.name.startswith("test_")
                if not same_context and not is_test_source and (
                    ".internal." in target_module
                    or ".private." in target_module
                    or target.name.startswith("_")
                ):
                    violations.append({"source": source.relative_to(ROOT).as_posix(), "target": target.relative_to(ROOT).as_posix(), "line": line, "reason": "private cross-domain import"})
    domain_nodes = [{"id": key, "name": name, "owner": key.title(), "lifecycle": "operational" if key not in {"billing"} else "owner-review"} for key, (name, _) in DOMAINS.items()]
    edge_records = [{"source": s, "target": t, "evidence": [{"path": path, "line": line}]} for s, t, path, line in sorted(edges)]
    return {"schema_version": "1.0", "source": "scripts/ci/generate_domain_dependency_graph.py", "domain_count": len(domain_nodes), "domains": domain_nodes, "edges": edge_records, "cycles": [], "boundary_violations": sorted(violations, key=lambda item: (item["source"], item["line"])), "notes": ["Heuristic domain classification is evidence for review, not a replacement for ownership metadata.", "MODULES_LIST.md remains governed by module_wiring_audit.json."]}


def mermaid(data: dict) -> str:
    lines = ["flowchart LR"]
    for node in data["domains"]:
        lines.append(f'    {node["id"]}["{node["name"]}"]')
    for edge in data["edges"]:
        lines.append(f'    {edge["source"]} --> {edge["target"]}')
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    result = build()
    OUT_JSON.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUT_MMD.write_text(mermaid(result), encoding="utf-8")
    print(f"wrote {OUT_JSON} and {OUT_MMD}; edges={len(result['edges'])} violations={len(result['boundary_violations'])}")
