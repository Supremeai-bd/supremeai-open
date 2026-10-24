import unittest
from scripts.ci.sync_graph_to_memory import self_test, query_symbol, trace_node_relations, format_entities_for_memory


class TestSyncGraphToMemory(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(self_test(), 0)

    def test_query_and_trace(self):
        graph = {
            "nodes": [
                {"id": "service_login", "label": "login", "source_file": "services/auth.ts", "source_location": "L10"},
                {"id": "comp_btn", "label": "LoginButton", "source_file": "components/LoginButton.tsx", "source_location": "L5"},
            ],
            "links": [
                {"source": "comp_btn", "target": "service_login", "relation": "calls"},
            ],
        }
        res = query_symbol(graph, "Login")
        self.assertEqual(len(res), 2)

        rels = trace_node_relations(graph, "comp_btn")
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]["target"], "service_login")

        payload = format_entities_for_memory(graph, "studio")
        self.assertEqual(payload["entity_count"], 2)
        self.assertEqual(payload["relation_count"], 1)


if __name__ == "__main__":
    unittest.main()
