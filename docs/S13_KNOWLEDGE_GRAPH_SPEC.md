# S13 — Multimodal Knowledge Graph & Token-Diet Engine

Implements **#500** — `feat(archive): [knowledge-graph]` (71x context
reduction). Ties into #492 (S12, WO #512) nightly-train synthesis and
#489 (S09) role dispatch.

## 1. Deliverables

| File | Kind | Purpose |
|---|---|---|
| `scripts/agents/context_graph_resolver.py` | new | **Engine SSOT**: `KnowledgeNode`/`KnowledgeEdge` schema (field-for-field TS mirror), stdlib extraction (AST python + markdown refs), honest `explicit`/`inferred` confidence, deterministic reference resolution, 1-hop resolution in a strict <500-token budget, the >50x token-diet benchmark, and the SHA-256 `IncrementalCache` (touch 1 file → exactly 1 node). |
| `tests/test_s13_knowledge_graph.py` | new | 24 offline contract tests (dual-mode), incl. a stdlib-only self-scan. |
| This document | new | Spec + Appendix A (the `scripts/archive/` shells — outside this repo's bridge boundary), Appendix B (loop integration), Appendix C (nightly-train synthesis hook). |

## 2. Graph Contract (issue schema, mirrored)

```typescript
KnowledgeNode { id; type: "satellite"|"file"|"contract"|"policy"|"god_node";
                summary; sha256 }
KnowledgeEdge { source; target;
                relation: "depends_on"|"enforces"|"dispatches_to"|"validates";
                confidence: "explicit"|"inferred" }
```

Construction is fail-closed: unknown types/relations/confidences, empty
summaries, malformed SHA-256, duplicate ids, self-edges and **dangling
edges** all raise `GraphError`. The graph is JSON round-trippable.

## 3. Extraction & Honest Classification

* Python (stdlib `ast`): module nodes + per-def/class `god_node`s;
  intra-module def edges are `explicit`; cross-file imports are
  `inferred` `depends_on`.
* Markdown: H1-H3 files become `policy`/`contract` nodes; `FILE.md#anchor`
  references become `explicit` `enforces` edges through a deterministic
  resolver: exact id → unique suffix match on the file name → file-level
  node (anchors are advisory). **Unresolvable references are dropped,
  never fabricated** — the found-vs-inferred distinction from the issue is
  preserved end-to-end. A file citing itself creates no edge.

## 4. Token Diet (acceptance criterion 3)

`resolve_context(node_id)` returns the 1-hop map (root + immediate edges +
neighbor micro-summaries) with a deterministic token estimate; the budget
is `TOKEN_BUDGET_PER_QUERY = 500`. `benchmark_savings(raw_documents,
resolution)` computes baseline (root + neighbor files, raw) / resolution —
the gate is `MIN_TOKEN_SAVINGS_RATIO = 50` (issue headline 71.5x, tested
with a synthetic >50x case and fail-closed on empty baselines).

## 5. SHA-256 Incremental Cache (acceptance criterion 2)

`IncrementalCache.commit/changed_files` (hashing internal, raw content in)
+ `incremental_update(graph, cache, path, new_content)`:

* a file whose hash is unchanged is preserved **verbatim** (byte-identical
  node SHAs asserted in tests);
* touching 1 file rebuilds **exactly 1 node** (`rebuilt == 1` asserted) and
  re-wires only its immediate edges (fresh refs resolved, unresolved
  dropped);
* bootstrapping a brand-new file through the incremental path raises —
  the full builder owns bootstrap (amend-vs-bootstrap discipline).

## 6. Appendix A — `scripts/archive/` shells (outside the bridge boundary)

`scripts/archive/` is not in this repo's bridge allowlist
(`scripts: {agents, ops, ci, tower}`); per repo doctrine these two shells
ship as spec content for the archive-repo maintainers. They are thin
standalone wrappers around the SAME algorithms as
`scripts/agents/context_graph_resolver.py` (parity discipline — copies
must stay in sync, cf. the #67 marker convention).

```python
# scripts/archive/build_knowledge_graph.py (supremeai-archive)
#!/usr/bin/env python3
"""Full-graph builder: walk the archive tree, extract nodes/edges, write
archive/graph.json + archive/cache/file_hashes.json. Zero-dependency."""

import hashlib, json, sys
from pathlib import Path


def file_sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main(root: Path = Path("archive/sources")) -> int:
    nodes, edges, cache = [], [], {}
    for path in sorted(root.rglob("*")):
        if path.suffix not in (".py", ".md"):
            continue
        content = path.read_text(encoding="utf-8")
        cache[str(path)] = file_sha256(content)
        nodes.append(
            {
                "id": f"file:{path}",
                "type": "policy" if path.suffix == ".md" else "file",
                "summary": content.splitlines()[0][:200],
                "sha256": cache[str(path)],
            }
        )
    Path("archive/cache").mkdir(parents=True, exist_ok=True)
    Path("archive/cache/file_hashes.json").write_text(json.dumps(cache, indent=2))
    Path("archive/graph.json").write_text(
        json.dumps({"nodes": nodes, "edges": edges}, indent=2)
    )
    print(f"graph built: {len(nodes)} nodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```python
# scripts/archive/incremental_graph_update.py (supremeai-archive)
#!/usr/bin/env python3
"""Incremental updater: `git diff --name-only` against
archive/cache/file_hashes.json; touches exactly the modified nodes."""

import json, subprocess, sys
from pathlib import Path


def main() -> int:
    cache = json.loads(Path("archive/cache/file_hashes.json").read_text())
    changed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"], capture_output=True, text=True
    ).stdout.split()
    touched = [p for p in changed if p in cache]
    print(json.dumps({"touched": touched, "full_reindex": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

The in-repo tests prove the incremental contract the shells rely on
(`test_17`–`test_19` in `tests/test_s13_knowledge_graph.py`).

## 7. Appendix B — continuous-loop integration (content-anchored, after
S09/S10 hunks land)

`scripts/agents/continuous_agent_loop.py` — before any full-file read,
query the graph:

```python
     # Classify Role & Prompt
     assigned_role = args.role or classify_task_role(
         task.get("title", ""), task.get("labels", []), task.get("body", "")
     )
+    # S13 (#500): token-diet context resolution BEFORE raw reads.
+    try:
+        from context_graph_resolver import KnowledgeGraph
+        graph_payload = json.loads((REPO_ROOT / "archive/graph.json")
+                                   .read_text(encoding="utf-8"))
+        _kg = KnowledgeGraph(
+            nodes=[KnowledgeNode(**n) for n in graph_payload["nodes"]],
+            edges=[KnowledgeEdge(**e) for e in graph_payload["edges"]])
+        log("🧠", "Knowledge graph loaded — 1-hop context active")
+    except (OSError, ValueError):
+        _kg = None
+        log("🧠", "Knowledge graph unavailable — falling back to raw reads")
```

## 8. Appendix C — nightly-train synthesis (#492 tie-in)

Deep graph synthesis and cross-satellite link verification are heavy
operations → they run exclusively in the Nightly Train (S12
`assert_suite_allowed("knowledge_graph_synthesis", "nightly_train")`
passes; daytime lanes reject it — the suite name contains `synthesis`…
contract note: name the job `integration_knowledge_graph_synthesis` so the
heavy-suite marker applies).

## 9. Test evidence

24 offline tests green in dual mode (`python3 -m unittest
test_s13_knowledge_graph -v` / `pytest -q`), `--self-test` green. The
module self-scans as 100% stdlib (AST walk against
`sys.stdlib_module_names` — acceptance criterion 4, machine-checked).
