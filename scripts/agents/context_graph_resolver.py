#!/usr/bin/env python3
"""S13 — Multimodal Knowledge Graph & Token-Diet Engine (issue #500).

Persistent, cross-session agent memory with extreme token efficiency for
the 11-satellite federation:

  * compact node-edge graph (``KnowledgeNode`` / ``KnowledgeEdge`` —
    field-for-field mirror of the issue's TypeScript schema);
  * 1-hop context resolution in a strict < 500-token budget, replacing
    50,000-100,000-token raw-file dumps;
  * SHA-256 incremental cache: touching 1 file updates exactly 1 node and
    its immediate edges — never a full re-index;
  * honest classification: ``explicit`` (found by extraction) vs
    ``inferred`` edges, never silently upgraded;
  * token-diet benchmark: > 50x savings vs raw document injection
    (issue headline: 71.5x);
  * 100% standard library — zero external heavy dependencies.

Deployment layout (issue #500): the engine core lives here as the SSOT;
``scripts/archive/build_knowledge_graph.py`` and
``scripts/archive/incremental_graph_update.py`` (outside this repo's
bridge lane) are thin standalone shells documented verbatim in
``docs/S13_KNOWLEDGE_GRAPH_SPEC.md`` Appendix A — copies must stay in
sync with this module (parity doctrine, cf. #67 marker discipline).

Pure stdlib. Run: python3 scripts/agents/context_graph_resolver.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

NODE_TYPES: Final = ("satellite", "file", "contract", "policy", "god_node")
EDGE_RELATIONS: Final = ("depends_on", "enforces", "dispatches_to", "validates")
EDGE_CONFIDENCE: Final = ("explicit", "inferred")

#: 1-hop resolution token budget (issue: "< 500 tokens per query").
TOKEN_BUDGET_PER_QUERY: Final = 500
#: Benchmark floor (issue acceptance: > 50x; headline: 71.5x).
MIN_TOKEN_SAVINGS_RATIO: Final = 50.0

HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
RULE_REF_RE = re.compile(r"(?:^|\s)([A-Z][A-Z0-9_]+\.md)(?:#(\S+))?")


class GraphError(ValueError):
    """Raised when a graph payload violates the schema (fail-closed)."""


@dataclass(frozen=True)
class KnowledgeNode:
    id: str
    type: str
    summary: str
    sha256: str


@dataclass(frozen=True)
class KnowledgeEdge:
    source: str
    target: str
    relation: str
    confidence: str


@dataclass(frozen=True)
class ContextResolution:
    root: KnowledgeNode
    edges: tuple[KnowledgeEdge, ...]
    neighbors: tuple[KnowledgeNode, ...]
    tokens_estimate: int
    budget_ok: bool


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate: ceil(words * 4 / 3) (≈4 chars/word,
    conservative for code-heavy summaries)."""
    words = len(text.split())
    return max(1, -(-words * 4 // 3))


def _check_node(node: KnowledgeNode) -> None:
    if node.type not in NODE_TYPES:
        raise GraphError(f"node type must be one of {NODE_TYPES}, got {node.type!r}")
    if not node.id or not node.summary:
        raise GraphError(f"node {node.id!r} needs id and summary")
    if not re.fullmatch(r"[0-9a-f]{64}", node.sha256):
        raise GraphError(f"node {node.id!r} sha256 malformed: {node.sha256!r}")


def _check_edge(edge: KnowledgeEdge) -> None:
    if edge.relation not in EDGE_RELATIONS:
        raise GraphError(
            f"edge relation must be one of {EDGE_RELATIONS}, got {edge.relation!r}"
        )
    if edge.confidence not in EDGE_CONFIDENCE:
        raise GraphError(
            f"edge confidence must be one of {EDGE_CONFIDENCE}, got {edge.confidence!r}"
        )
    if not edge.source or not edge.target or edge.source == edge.target:
        raise GraphError(f"edge needs distinct endpoints, got {edge!r}")


# ---------------------------------------------------------------------------
# Extraction (Phase: build — the engine the archive shells wrap)
# ---------------------------------------------------------------------------


def file_sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def extract_python_nodes(
    path: str, content: str
) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
    """AST extraction: module-level defs/classes as nodes, imports as
    explicit ``depends_on`` edges (same-package targets only)."""
    nodes: list[KnowledgeNode] = []
    edges: list[KnowledgeEdge] = []
    sha = file_sha256(content)
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        raise GraphError(f"{path}: source does not parse: {exc}") from exc
    node_id = f"file:{path}"
    doc = ast.get_docstring(tree) or path
    nodes.append(KnowledgeNode(node_id, "file", doc.splitlines()[0][:200], sha))
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            child_id = f"file:{path}#{stmt.name}"
            summary = (ast.get_docstring(stmt) or stmt.name).splitlines()[0][:200]
            nodes.append(
                KnowledgeNode(
                    child_id, "god_node", summary, file_sha256(f"{path}::{stmt.name}")
                )
            )
            edges.append(KnowledgeEdge(node_id, child_id, "depends_on", "explicit"))
        if isinstance(stmt, ast.ImportFrom) and stmt.module:
            target = f"ref:{stmt.module.replace('.', '/')}.py"
            edges.append(KnowledgeEdge(node_id, target, "depends_on", "inferred"))
    return nodes, edges


def extract_markdown_nodes(
    path: str, content: str
) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
    """Markdown extraction: H1-H3 headings as policy/contract nodes; rule
    references (FILE.md#anchor) as ``enforces`` edges with RAW targets
    (``ref:`` scheme — resolved against the full node set by
    ``build_graph``, honestly dropped when unresolvable)."""
    nodes: list[KnowledgeNode] = []
    edges: list[KnowledgeEdge] = []
    sha = file_sha256(content)
    node_id = f"file:{path}"
    ntype = (
        "policy"
        if "rule" in path.lower() or "governance" in path.lower()
        else "contract"
    )
    first_para = next((ln for ln in content.splitlines() if ln.strip()), path)
    nodes.append(KnowledgeNode(node_id, ntype, first_para[:200], sha))
    seen_refs: set[str] = set()
    own_base = path.split("/")[-1]
    for match in RULE_REF_RE.finditer(content):
        ref_file, anchor = match.group(1), match.group(2) or ""
        if ref_file == own_base:
            continue  # a file referencing itself is not an edge
        target = f"ref:{ref_file}" + (f"#{anchor}" if anchor else "")
        if target not in seen_refs:
            seen_refs.add(target)
            edges.append(KnowledgeEdge(node_id, target, "enforces", "explicit"))
    return nodes, edges


def _resolve_ref(target: str, node_ids: set[str]) -> str | None:
    """Resolve a raw ``ref:`` target against known node ids.

    Deterministic order: exact id -> unique suffix match on the file name
    (any directory). Anchors are advisory: resolution targets the file-
    level node unless a child node with that exact anchored id exists.
    Unresolvable refs are dropped honestly (never fabricated, never
    dangling).
    """
    raw = target[len("ref:") :]
    base = raw.split("#")[0]
    anchored = f"file:{raw}"
    if target in node_ids:
        return target
    if anchored in node_ids or f"file:{raw}" in node_ids:
        return anchored if anchored in node_ids else f"file:{raw}"
    matches = sorted(
        nid
        for nid in node_ids
        if nid.split("#")[0].endswith("/" + base) or nid.split("#")[0] == f"file:{base}"
    )
    if len(matches) == 1:
        return matches[0].split("#")[0]  # file-level node; anchor advisory
    return None


def build_graph(sources: Mapping[str, str]) -> KnowledgeGraph:
    """Build the initial graph from {path: content}. Fail-closed."""
    nodes: list[KnowledgeNode] = []
    edges: list[KnowledgeEdge] = []
    for path, content in sorted(sources.items()):
        if path.endswith(".py"):
            n, e = extract_python_nodes(path, content)
        elif path.endswith(".md"):
            n, e = extract_markdown_nodes(path, content)
        else:
            raise GraphError(
                f"unsupported source type: {path!r} "
                "(stdlib extractor covers .py and .md)"
            )
        nodes.extend(n)
        edges.extend(e)
    node_ids = {n.id for n in nodes}
    resolved_edges: list[KnowledgeEdge] = []
    for edge in edges:
        if edge.target.startswith("ref:"):
            resolved = _resolve_ref(edge.target, node_ids)
            if resolved is None:
                continue  # honest drop: unresolved references are not edges
            edge = KnowledgeEdge(edge.source, resolved, edge.relation, edge.confidence)
        resolved_edges.append(edge)
    return KnowledgeGraph(nodes=tuple(nodes), edges=tuple(resolved_edges))


# ---------------------------------------------------------------------------
# Graph container + 1-hop resolution (token diet)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnowledgeGraph:
    nodes: tuple[KnowledgeNode, ...]
    edges: tuple[KnowledgeEdge, ...]

    def __post_init__(self) -> None:
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise GraphError(f"duplicate node ids: {dupes}")
        for node in self.nodes:
            _check_node(node)
        for edge in self.edges:
            _check_edge(edge)
            if edge.source not in ids or edge.target not in ids:
                raise GraphError(
                    f"edge {edge.source!r}->{edge.target!r} references an "
                    "unknown node — dangling edges are rejected (fail-closed)"
                )

    @property
    def node_map(self) -> Mapping[str, KnowledgeNode]:
        return MappingProxyType({n.id: n for n in self.nodes})

    def resolve_context(self, node_id: str) -> ContextResolution:
        """1-hop context map within the strict token budget."""
        nodes = self.node_map
        root = nodes.get(node_id)
        if root is None:
            raise GraphError(f"unknown node {node_id!r}")
        out_edges = tuple(e for e in self.edges if e.source == node_id)
        in_edges = tuple(e for e in self.edges if e.target == node_id)
        edges = out_edges + in_edges
        neighbor_ids = {e.target for e in out_edges} | {e.source for e in in_edges}
        neighbors = tuple(nodes[nid] for nid in sorted(neighbor_ids))
        text = "\n".join(
            [f"{root.id}: {root.summary}"]
            + [f"- {e.relation} -> {e.target} ({e.confidence})" for e in out_edges]
            + [f"- {e.relation} <- {e.source} ({e.confidence})" for e in in_edges]
            + [f"{nb.id}: {nb.summary}" for nb in neighbors]
        )
        tokens = estimate_tokens(text)
        return ContextResolution(
            root=root,
            edges=edges,
            neighbors=neighbors,
            tokens_estimate=tokens,
            budget_ok=tokens <= TOKEN_BUDGET_PER_QUERY,
        )


def benchmark_savings(
    raw_documents: Mapping[str, str], resolution: ContextResolution
) -> float:
    """Token savings vs raw document injection (fail-closed, > 50x gate).

    ``raw_documents`` are the files the agent WOULD have read without the
    graph; the baseline includes the root file plus every 1-hop neighbor
    file the resolution covers.
    """
    if not raw_documents:
        raise GraphError("benchmark needs raw documents")
    root_file = resolution.root.id.split("#")[0][len("file:") :]
    baseline_files = {root_file}
    for nb in resolution.neighbors:
        baseline_files.add(nb.id.split("#")[0][len("file:") :])
    baseline_tokens = sum(
        estimate_tokens(content)
        for path, content in sorted(raw_documents.items())
        if path in baseline_files
    )
    if baseline_tokens <= 0:
        raise GraphError("baseline documents empty for resolved context")
    return baseline_tokens / resolution.tokens_estimate


# ---------------------------------------------------------------------------
# SHA-256 incremental cache (touch 1 file -> exactly 1 node update)
# ---------------------------------------------------------------------------


@dataclass
class IncrementalCache:
    """file path -> sha256; the acceptance-critical structure."""

    hashes: dict[str, str] = field(default_factory=dict)

    def changed_files(self, current: Mapping[str, str]) -> tuple[str, ...]:
        """Paths whose content differs from the cached snapshot (values are
        raw content; hashing is internal)."""
        return tuple(
            sorted(
                path
                for path, content in current.items()
                if self.hashes.get(path) != file_sha256(content)
            )
        )

    def commit(self, current: Mapping[str, str]) -> None:
        """Record the current content snapshot (hashes computed here)."""
        self.hashes.update(
            {path: file_sha256(content) for path, content in current.items()}
        )


def incremental_update(
    graph: KnowledgeGraph, cache: IncrementalCache, path: str, new_content: str
) -> tuple[KnowledgeGraph, int]:
    """Touch 1 file -> update EXACTLY 1 node + its immediate edges.

    Returns the new graph and the number of rebuilt nodes (must be 1 for
    a single-file change). Unchanged files are preserved verbatim — no
    full re-index.
    """
    nodes = list(graph.nodes)
    index = {n.id: i for i, n in enumerate(nodes)}
    target_id = f"file:{path}"
    if target_id not in index:
        raise GraphError(
            f"node {target_id!r} not in graph — run the full "
            "builder first (incremental updates amend, never "
            "bootstrap)"
        )
    if path.endswith(".py"):
        fresh_nodes, fresh_edges = extract_python_nodes(path, new_content)
    elif path.endswith(".md"):
        fresh_nodes, fresh_edges = extract_markdown_nodes(path, new_content)
    else:
        raise GraphError(f"unsupported source type: {path!r}")

    new_root = next(n for n in fresh_nodes if n.id == target_id)
    replaced = 0
    for i, node in enumerate(nodes):
        if node.id == target_id:
            nodes[i] = new_root
            replaced += 1
        elif node.id.startswith(target_id + "#") and node.sha256 != file_sha256(
            f"{path}::{node.id.split('#')[1]}"
        ):
            fresh_child = next((n for n in fresh_nodes if n.id == node.id), None)
            if fresh_child is not None and fresh_child.sha256 != node.sha256:
                nodes[i] = fresh_child
                replaced += 1
    # Re-wire edges: keep edges whose endpoints still exist, replace the
    # root's edges with the fresh ones (raw refs resolved, unresolved
    # dropped honestly — same contract as build_graph).
    node_ids = {n.id for n in nodes}
    kept = [
        e for e in graph.edges if not (e.source == target_id or e.target == target_id)
    ]
    for e in fresh_edges:
        if e.target.startswith("ref:"):
            resolved = _resolve_ref(e.target, node_ids)
            if resolved is None:
                continue
            e = KnowledgeEdge(e.source, resolved, e.relation, e.confidence)
        kept.append(e)
    new_graph = KnowledgeGraph(nodes=tuple(nodes), edges=tuple(kept))
    return new_graph, replaced


def self_test() -> bool:
    sources = {
        "docs/AGENT_RULES.md": "# Rules\n\nU4 hold doctrine. See AGENT_RULES.md#U4 "
        "and GATEWAY.md#auth\n",
        "docs/GATEWAY.md": "# Gateway SSOT\nBearer + key auth\n",
        "scripts/agents/loop.py": (
            '"""Agent loop."""\nimport json\n\n'
            'def run():\n    """Run the loop."""\n    return json.loads(\'{}\')\n'
        ),
    }
    graph = build_graph(sources)
    assert any(n.id == "file:scripts/agents/loop.py" for n in graph.nodes)
    assert any(n.type == "god_node" and n.id.endswith("#run") for n in graph.nodes)
    assert any(
        e.relation == "enforces" and e.confidence == "explicit" for e in graph.edges
    )

    # Schema fail-closed (construction itself must raise).
    bad_graphs = (
        lambda: KnowledgeGraph((KnowledgeNode("x", "alien", "s", "a" * 64),), ()),
        lambda: KnowledgeGraph((KnowledgeNode("x", "file", "", "a" * 64),), ()),
        lambda: KnowledgeGraph((KnowledgeNode("x", "file", "s", "nothex"),), ()),
        lambda: KnowledgeGraph(
            (KnowledgeNode("x", "file", "s", "a" * 64),),
            (KnowledgeEdge("x", "x", "depends_on", "explicit"),),
        ),
        lambda: KnowledgeGraph(
            (KnowledgeNode("x", "file", "s", "a" * 64),),
            (KnowledgeEdge("x", "y", "depends_on", "explicit"),),
        ),
        lambda: KnowledgeGraph(
            (
                KnowledgeNode("x", "file", "s", "a" * 64),
                KnowledgeNode("x", "file", "s2", "b" * 64),
            ),
            (),
        ),
        lambda: KnowledgeGraph(
            (KnowledgeNode("x", "file", "s", "a" * 64),),
            (KnowledgeEdge("x", "x", "marries", "explicit"),),
        ),
    )
    for build_bad in bad_graphs:
        try:
            build_bad()
            raise SystemExit("graph schema failed open")
        except GraphError:
            pass

    # 1-hop resolution within budget.
    resolution = graph.resolve_context("file:docs/AGENT_RULES.md")
    assert resolution.budget_ok, resolution.tokens_estimate
    # Anchor advisory: ref GATEWAY.md#auth resolves to the file-level node.
    assert any(
        e.target == "file:docs/GATEWAY.md" and e.relation == "enforces"
        for e in resolution.edges
    ) or any(nb.id == "file:docs/GATEWAY.md" for nb in resolution.neighbors)
    try:
        graph.resolve_context("file:ghost.md")
        raise SystemExit("resolve gate failed open")
    except GraphError:
        pass

    # Benchmark: graph 1-hop vs raw dump — synthetic >50x.
    big_rule = "docs/AGENT_RULES.md"
    raw = {
        big_rule: ("line of doctrine text " * 4000),
        "docs/GATEWAY.md": "line of gateway text " * 4000,
    }
    slim_graph = KnowledgeGraph(
        nodes=(
            KnowledgeNode(f"file:{big_rule}", "policy", "one-line summary", "a" * 64),
            KnowledgeNode(
                "file:docs/GATEWAY.md", "contract", "one-line gateway", "b" * 64
            ),
        ),
        edges=(
            KnowledgeEdge(
                f"file:{big_rule}", "file:docs/GATEWAY.md", "enforces", "explicit"
            ),
        ),
    )
    slim_resolution = slim_graph.resolve_context(f"file:{big_rule}")
    ratio = benchmark_savings(raw, slim_resolution)
    assert ratio > MIN_TOKEN_SAVINGS_RATIO, ratio

    # Incremental: touch 1 file -> exactly 1 node update, others verbatim.
    cache = IncrementalCache()
    cache.commit(sources)  # raw content in; hashing is internal
    assert cache.changed_files(sources) == ()
    new_sources = dict(sources)
    new_sources["scripts/agents/loop.py"] = (
        '"""Agent loop v2."""\nimport json\n\n'
        'def run():\n    """Run the loop faster."""\n    return json.loads(\'{}\')\n'
    )
    changed = cache.changed_files(new_sources)
    assert changed == ("scripts/agents/loop.py",), changed
    new_graph, rebuilt = incremental_update(
        graph, cache, "scripts/agents/loop.py", new_sources["scripts/agents/loop.py"]
    )
    assert rebuilt == 1, rebuilt
    before = {n.id: n.sha256 for n in graph.nodes}
    after = {n.id: n.sha256 for n in new_graph.nodes}
    untouched = [k for k in before if not k.startswith("file:scripts/agents/loop.py")]
    assert all(before[k] == after[k] for k in untouched), "full re-index leaked"
    updated = next(n for n in new_graph.nodes if n.id == "file:scripts/agents/loop.py")
    assert "v2" in updated.summary
    try:
        incremental_update(graph, cache, "brand/new.py", "x = 1\n")
        raise SystemExit("incremental bootstrap gate failed open")
    except GraphError:
        pass

    return True


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--resolve",
        metavar="NODE_ID",
        help="resolve a node's 1-hop context from graph.json",
    )
    parser.add_argument("--graph", default="graph.json")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("SELF-TEST OK: context_graph_resolver")
        return 0
    if args.resolve:
        with open(args.graph, encoding="utf-8") as _f:
            payload = json.load(_f)
        graph = KnowledgeGraph(
            nodes=tuple(KnowledgeNode(**n) for n in payload["nodes"]),
            edges=tuple(KnowledgeEdge(**e) for e in payload["edges"]),
        )
        r = graph.resolve_context(args.resolve)
        print(
            json.dumps(
                {
                    "root": r.root.id,
                    "tokens": r.tokens_estimate,
                    "budget_ok": r.budget_ok,
                    "edges": [e.__dict__ | {} for e in r.edges],
                    "neighbors": [n.id for n in r.neighbors],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
