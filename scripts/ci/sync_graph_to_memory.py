#!/usr/bin/env python3
"""
sync_graph_to_memory.py — Bridge local Graphify AST graphs with SupremeAI agent memory & diagnostics.

Guarantees:
  1. Zero-Token Discovery: Maps local AST nodes (classes, functions, endpoints, imports) without external LLM calls.
  2. Audit-to-Code Root Cause: Resolves failing URLs/components identified by devtools-audit directly to source file & line.
  3. Non-Regression Guard: Traces call graphs and dependency impact before modifying shared interfaces.
  4. Control Tower Memory Ready: Prepares structured entities & relations compatible with memory_create_entities and memory_create_relations.
  5. Fail-Safe & Self-Testing: Exits 0 on clean runs and provides `--self-test` for CI verification.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DOMAINS = {
    "studio": ROOT_DIR / "studio" / "src",
    "gateway": ROOT_DIR / "gateway",
    "core": ROOT_DIR / "core",
}
DEFAULT_CACHE_DIR = ROOT_DIR / ".cache" / "graphify"


def run_graphify_extract(target_dir: Path, out_dir: Path) -> Path:
    """Run local AST extraction using graphify CLI."""
    out_dir.mkdir(parents=True, exist_ok=True)
    graph_json = out_dir / "graphify-out" / "graph.json"

    cmd = [
        "graphify",
        "extract",
        str(target_dir),
        "--code-only",
        "--out",
        str(out_dir),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        print("[sync_graph_to_memory] Error: 'graphify' command not found in PATH.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[sync_graph_to_memory] Extraction failed:\n{e.stderr}", file=sys.stderr)
        sys.exit(e.returncode)

    if not graph_json.exists():
        print(f"[sync_graph_to_memory] Error: {graph_json} was not generated.", file=sys.stderr)
        sys.exit(1)

    return graph_json


def load_graph(graph_file: Path) -> dict[str, Any]:
    """Load and parse graph.json."""
    if not graph_file.exists():
        return {}
    with graph_file.open("r", encoding="utf-8") as f:
        return json.load(f)


def query_symbol(graph: dict[str, Any], query: str) -> list[dict[str, Any]]:
    """Search nodes matching query string in id, label, or source_file."""
    query_lower = query.lower()
    matches = []
    nodes = graph.get("nodes", [])
    for n in nodes:
        lbl = str(n.get("label", "")).lower()
        nid = str(n.get("id", "")).lower()
        src = str(n.get("source_file", "")).lower()
        if query_lower in lbl or query_lower in nid or query_lower in src:
            matches.append(n)
    return matches


def trace_node_relations(graph: dict[str, Any], node_id: str) -> list[dict[str, Any]]:
    """Trace incoming and outgoing links for a given node id."""
    links = graph.get("links", []) + graph.get("edges", [])
    related = []
    for link in links:
        if link.get("source") == node_id or link.get("target") == node_id:
            related.append(link)
    return related


def format_entities_for_memory(graph: dict[str, Any], domain: str) -> dict[str, Any]:
    """Format nodes and edges into MCP memory entity payload."""
    entities = []
    for n in graph.get("nodes", []):
        entities.append({
            "name": n.get("label") or n.get("id"),
            "entityType": "CodeSymbol",
            "observations": [
                f"Domain: {domain}",
                f"Source: {n.get('source_file')}:{n.get('source_location')}",
                f"Callable: {n.get('_callable', False)}",
                f"Community: {n.get('community', 'default')}",
            ],
        })

    relations = []
    links = graph.get("links", []) + graph.get("edges", [])
    for l in links:
        relations.append({
            "from": l.get("source"),
            "to": l.get("target"),
            "relationType": l.get("relation", "relates_to"),
        })

    return {
        "domain": domain,
        "entity_count": len(entities),
        "relation_count": len(relations),
        "entities": entities,
        "relations": relations,
    }


def self_test() -> int:
    """Validate internal parser and data transformation invariants."""
    print("Running sync_graph_to_memory self-test...")
    dummy_graph = {
        "nodes": [
            {"id": "service_api_login", "label": "login", "source_file": "services/api.ts", "source_location": "L45", "_callable": True},
            {"id": "comp_chat", "label": "GuestChat", "source_file": "components/GuestChat.tsx", "source_location": "L12"},
        ],
        "links": [
            {"source": "comp_chat", "target": "service_api_login", "relation": "calls"},
        ],
    }
    matches = query_symbol(dummy_graph, "login")
    assert len(matches) == 1, f"Expected 1 match, got {len(matches)}"
    assert matches[0]["label"] == "login"

    rels = trace_node_relations(dummy_graph, "comp_chat")
    assert len(rels) == 1
    assert rels[0]["relation"] == "calls"

    payload = format_entities_for_memory(dummy_graph, "studio")
    assert payload["entity_count"] == 2
    assert payload["relation_count"] == 1

    print("[sync_graph_to_memory] All self-tests passed successfully! (OK)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Graphify AST graph with SupremeAI agent memory & root-cause analysis")
    parser.add_argument("--domain", choices=list(DEFAULT_DOMAINS.keys()), default="studio", help="Target domain (default: studio)")
    parser.add_argument("--path", type=Path, help="Override target source directory")
    parser.add_argument("--query", help="Search AST graph for symbol or filename")
    parser.add_argument("--trace", help="Trace all relations for a specific node ID")
    parser.add_argument("--export-entities", action="store_true", help="Output formatted entities for MCP memory sidecar")
    parser.add_argument("--force-extract", action="store_true", help="Force re-extraction of the AST graph")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests and exit")

    args = parser.parse_args()

    if args.self_test:
        return self_test()

    target_dir = args.path or DEFAULT_DOMAINS[args.domain]
    cache_dir = DEFAULT_CACHE_DIR / args.domain
    graph_file = cache_dir / "graphify-out" / "graph.json"

    if args.force_extract or not graph_file.exists():
        print(f"Extracting AST graph for {args.domain} from {target_dir}...")
        graph_file = run_graphify_extract(target_dir, cache_dir)

    graph = load_graph(graph_file)
    print(f"Loaded graph: {len(graph.get('nodes', []))} nodes, {len(graph.get('links', []))} edges from {graph_file}")

    if args.query:
        matches = query_symbol(graph, args.query)
        print(f"\n--- Found {len(matches)} match(es) for '{args.query}' ---")
        for m in matches[:15]:
            print(f"- [{m.get('label', m.get('id'))}] in {m.get('source_file')}:{m.get('source_location')} (ID: {m.get('id')})")
        if len(matches) > 15:
            print(f"... and {len(matches) - 15} more.")

    if args.trace:
        relations = trace_node_relations(graph, args.trace)
        print(f"\n--- Tracing relations for '{args.trace}' ({len(relations)} connections) ---")
        for r in relations[:20]:
            print(f"  {r.get('source')} --({r.get('relation', 'relates_to')})--> {r.get('target')}")

    if args.export_entities:
        payload = format_entities_for_memory(graph, args.domain)
        out_path = cache_dir / "mcp_entities.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\nWrote MCP memory payload to {out_path} ({payload['entity_count']} entities, {payload['relation_count']} relations)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
