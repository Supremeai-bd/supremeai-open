#!/usr/bin/env python3
"""Offline contract tests for the S13 Knowledge Graph & Token-Diet Engine
(issue #500).

Covers: the KnowledgeNode/KnowledgeEdge schema (field-for-field TS mirror,
fail-closed construction), stdlib extraction (AST python nodes, markdown
policy/contract nodes, honest explicit-vs-inferred confidence), reference
resolution (exact -> unique suffix -> honest drop; anchors advisory), 1-hop
context resolution within the <500-token budget, the >50x token-diet
benchmark gate, and SHA-256 incremental updates (touch 1 file -> exactly
1 node, no full re-index).

Pure stdlib. Run: python3 -m unittest test_s13_knowledge_graph -v
"""
import json
import sys
import unittest
from pathlib import Path

AGENTS = Path(__file__).resolve().parent.parent / "scripts" / "agents"
sys.path.insert(0, str(AGENTS))

import context_graph_resolver as kg  # noqa: E402


def sources() -> dict[str, str]:
    return {
        "docs/AGENT_RULES.md":
            "# Rules\n\nU4 hold doctrine. See GATEWAY.md#auth for keys\n",
        "docs/GATEWAY.md": "# Gateway SSOT\nBearer + key auth\n",
        "scripts/agents/loop.py":
            '"""Agent loop."""\nimport json\n\n'
            "def run():\n    \"\"\"Run the loop.\"\"\"\n"
            "    return json.loads('{}')\n",
    }


def graph() -> kg.KnowledgeGraph:
    return kg.build_graph(sources())


class SchemaContract(unittest.TestCase):
    def test_01_ts_interface_mirror(self):
        self.assertEqual(kg.NODE_TYPES,
                         ("satellite", "file", "contract", "policy",
                          "god_node"))
        self.assertEqual(kg.EDGE_RELATIONS,
                         ("depends_on", "enforces", "dispatches_to",
                          "validates"))
        self.assertEqual(kg.EDGE_CONFIDENCE, ("explicit", "inferred"))

    def test_02_valid_graph_constructs(self):
        g = graph()
        self.assertGreaterEqual(len(g.nodes), 4)
        self.assertTrue(any(n.type == "god_node" and
                            n.id.endswith("#run") for n in g.nodes))

    def test_03_fail_closed_construction(self):
        cases = (
            lambda: kg.KnowledgeGraph(
                (kg.KnowledgeNode("x", "alien", "s", "a" * 64),), ()),
            lambda: kg.KnowledgeGraph(
                (kg.KnowledgeNode("x", "file", "", "a" * 64),), ()),
            lambda: kg.KnowledgeGraph(
                (kg.KnowledgeNode("x", "file", "s", "nothex"),), ()),
            lambda: kg.KnowledgeGraph(
                (kg.KnowledgeNode("x", "file", "s", "a" * 64),),
                (kg.KnowledgeEdge("x", "x", "depends_on", "explicit"),)),
            lambda: kg.KnowledgeGraph(
                (kg.KnowledgeNode("x", "file", "s", "a" * 64),),
                (kg.KnowledgeEdge("x", "y", "depends_on", "explicit"),)),
            lambda: kg.KnowledgeGraph(
                (kg.KnowledgeNode("x", "file", "s", "a" * 64),
                 kg.KnowledgeNode("x", "file", "s2", "b" * 64)), ()),
            lambda: kg.KnowledgeGraph(
                (kg.KnowledgeNode("x", "file", "s", "a" * 64),),
                (kg.KnowledgeEdge("x", "x", "marries", "explicit"),)),
            lambda: kg.KnowledgeGraph(
                (kg.KnowledgeNode("x", "file", "s", "a" * 64),),
                (kg.KnowledgeEdge("x", "x", "depends_on", "maybe"),)),
        )
        for build in cases:
            with self.assertRaises(kg.GraphError):
                build()


class StdlibExtraction(unittest.TestCase):
    def test_04_python_ast_nodes_and_edges(self):
        g = graph()
        loop = next(n for n in g.nodes if n.id == "file:scripts/agents/loop.py")
        self.assertEqual(loop.type, "file")
        self.assertEqual(loop.sha256, kg.file_sha256(sources()
                                                     ["scripts/agents/loop.py"]))
        run = next(n for n in g.nodes if n.id == "file:scripts/agents/loop.py#run")
        self.assertEqual(run.type, "god_node")
        # def run -> explicit depends_on edge from the module node.
        self.assertTrue(any(e.source == loop.id and e.target == run.id
                            and e.relation == "depends_on"
                            and e.confidence == "explicit"
                            for e in g.edges))

    def test_05_import_edges_inferred_and_resolved(self):
        g = graph()
        # `import json` has no local target -> honestly dropped.
        self.assertFalse(any(e.target.endswith("json.py") for e in g.edges))

    def test_06_markdown_refs_resolved(self):
        g = graph()
        edge = next(e for e in g.edges
                    if e.source == "file:docs/AGENT_RULES.md")
        self.assertEqual(edge.relation, "enforces")
        self.assertEqual(edge.confidence, "explicit")
        self.assertEqual(edge.target, "file:docs/GATEWAY.md")

    def test_07_self_reference_dropped(self):
        # A file citing itself (even with an anchor) is not an edge.
        g = kg.build_graph({"docs/SOLO.md": "# S\nSee SOLO.md#x\n"})
        self.assertFalse(any(e.source == "file:docs/SOLO.md"
                             for e in g.edges))

    def test_08_unresolvable_refs_dropped_honestly(self):
        g = kg.build_graph({
            "docs/A.md": "# A\nSee NOWHERE_AT_ALL.md#x\n",
            "docs/B.md": "# B\nplain\n",
        })
        self.assertFalse(any(e.source == "file:docs/A.md" for e in g.edges))

    def test_09_unsupported_type_fail_closed(self):
        with self.assertRaises(kg.GraphError):
            kg.build_graph({"data.csv": "a,b\n1,2\n"})

    def test_10_broken_python_fail_closed(self):
        with self.assertRaises(kg.GraphError):
            kg.build_graph({"bad.py": "def broken(:\n"})


class OneHopResolution(unittest.TestCase):
    def test_11_budget_contract(self):
        self.assertEqual(kg.TOKEN_BUDGET_PER_QUERY, 500)
        r = graph().resolve_context("file:docs/AGENT_RULES.md")
        self.assertTrue(r.budget_ok)
        self.assertLessEqual(r.tokens_estimate, kg.TOKEN_BUDGET_PER_QUERY)

    def test_12_neighbors_via_edges(self):
        r = graph().resolve_context("file:docs/AGENT_RULES.md")
        self.assertIn("file:docs/GATEWAY.md",
                      {n.id for n in r.neighbors})

    def test_13_unknown_node_fail_closed(self):
        with self.assertRaises(kg.GraphError):
            graph().resolve_context("file:ghost.md")

    def test_14_bidirectional_hop(self):
        # Resolving the TARGET also sees the incoming edge.
        r = graph().resolve_context("file:docs/GATEWAY.md")
        self.assertTrue(any(e.source == "file:docs/AGENT_RULES.md"
                            for e in r.edges))


class TokenDietBenchmark(unittest.TestCase):
    def test_15_ratio_gate(self):
        self.assertGreaterEqual(kg.MIN_TOKEN_SAVINGS_RATIO, 50.0)
        big = "word " * 4000
        raw = {"docs/AGENT_RULES.md": big, "docs/GATEWAY.md": big}
        slim = kg.KnowledgeGraph(
            nodes=(kg.KnowledgeNode("file:docs/AGENT_RULES.md", "policy",
                                    "one line", "a" * 64),
                   kg.KnowledgeNode("file:docs/GATEWAY.md", "contract",
                                    "one line", "b" * 64)),
            edges=(kg.KnowledgeEdge("file:docs/AGENT_RULES.md",
                                    "file:docs/GATEWAY.md", "enforces",
                                    "explicit"),))
        ratio = kg.benchmark_savings(raw, slim.resolve_context(
            "file:docs/AGENT_RULES.md"))
        self.assertGreater(ratio, kg.MIN_TOKEN_SAVINGS_RATIO)

    def test_16_benchmark_fail_closed(self):
        slim = kg.KnowledgeGraph(
            (kg.KnowledgeNode("file:x.md", "contract", "s", "a" * 64),), ())
        with self.assertRaises(kg.GraphError):
            kg.benchmark_savings({}, slim.resolve_context("file:x.md"))
        with self.assertRaises(kg.GraphError):
            kg.benchmark_savings({"other.md": "text"},
                                 slim.resolve_context("file:x.md"))


class IncrementalCacheContract(unittest.TestCase):
    def test_17_touch_one_file_updates_exactly_one_node(self):
        g = graph()
        cache = kg.IncrementalCache()
        cache.commit(sources())
        self.assertEqual(cache.changed_files(sources()), ())
        new_sources = sources()
        new_sources["scripts/agents/loop.py"] = (
            '"""Agent loop v2."""\nimport json\n\n'
            "def run():\n    \"\"\"Run faster.\"\"\"\n"
            "    return json.loads('{}')\n")
        self.assertEqual(cache.changed_files(new_sources),
                         ("scripts/agents/loop.py",))
        new_graph, rebuilt = kg.incremental_update(
            g, cache, "scripts/agents/loop.py",
            new_sources["scripts/agents/loop.py"])
        self.assertEqual(rebuilt, 1)
        self.assertIn("v2", next(n for n in new_graph.nodes
                                 if n.id == "file:scripts/agents/loop.py").summary)

    def test_18_untouched_nodes_verbatim(self):
        g = graph()
        cache = kg.IncrementalCache()
        cache.commit(sources())
        new_graph, _ = kg.incremental_update(
            g, cache, "scripts/agents/loop.py",
            '"""Agent loop v3."""\nimport json\n\n'
            "def run():\n    return 1\n")
        before = {n.id: n.sha256 for n in g.nodes}
        after = {n.id: n.sha256 for n in new_graph.nodes}
        for node_id in before:
            if not node_id.startswith("file:scripts/agents/loop.py"):
                self.assertEqual(before[node_id], after[node_id], node_id)

    def test_19_no_bootstrap_via_incremental(self):
        cache = kg.IncrementalCache()
        with self.assertRaises(kg.GraphError):
            kg.incremental_update(graph(), cache, "brand/new.py", "x = 1\n")

    def test_20_changed_files_detects_content_drift(self):
        cache = kg.IncrementalCache()
        cache.commit(sources())
        drifted = sources()
        drifted["docs/GATEWAY.md"] = "# Gateway SSOT v9\nchanged\n"
        self.assertEqual(cache.changed_files(drifted), ("docs/GATEWAY.md",))


class Canon(unittest.TestCase):
    def test_21_stdlib_only_implementation(self):
        import ast as _ast
        module_src = Path(kg.__file__).read_text(encoding="utf-8")
        tree = _ast.parse(module_src)
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                for alias in node.names:
                    self.assertIn(alias.name.split(".")[0],
                                  sys.stdlib_module_names, alias.name)
            if isinstance(node, _ast.ImportFrom) and node.module:
                self.assertIn(node.module.split(".")[0],
                              sys.stdlib_module_names, node.module)

    def test_22_deployment_layout_documented(self):
        # The engine core is the SSOT; archive shells are doc appendix.
        self.assertIn("scripts/archive/build_knowledge_graph.py",
                      Path(kg.__file__).read_text(encoding="utf-8"))

    def test_23_self_test_entrypoint_green(self):
        self.assertTrue(kg.self_test())

    def test_24_json_round_trip(self):
        g = graph()
        payload = {"nodes": [n.__dict__ for n in g.nodes],
                   "edges": [e.__dict__ for e in g.edges]}
        text = json.dumps(payload)
        loaded = json.loads(text)
        g2 = kg.KnowledgeGraph(
            nodes=tuple(kg.KnowledgeNode(**n) for n in loaded["nodes"]),
            edges=tuple(kg.KnowledgeEdge(**e) for e in loaded["edges"]))
        self.assertEqual({n.id: n.sha256 for n in g.nodes},
                         {n.id: n.sha256 for n in g2.nodes})


if __name__ == "__main__":
    unittest.main(verbosity=2)
