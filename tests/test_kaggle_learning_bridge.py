#!/usr/bin/env python3
"""Contract tests for Kaggle Intelligent Learning Bridge."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import kaggle_learning_bridge as klb


class TestKaggleLearningBridge(unittest.TestCase):
    def test_self_test_passes(self):
        code = klb.run_self_test()
        self.assertEqual(code, 0)

    def test_auth_header_parsing(self):
        basic = klb.parse_kaggle_auth("user:key")
        self.assertTrue(basic.startswith("Basic "))
        bearer = klb.parse_kaggle_auth("KGAT_123456789")
        self.assertTrue(bearer.startswith("Bearer "))

    def test_distillation_structure(self):
        engine = klb.KaggleLearningEngine(tokens=["mock:key"])
        raw = {
            "experiment_name": "Quantization Benchmark",
            "hypothesis": "4-bit AWQ provides lower perplexity loss than GGUF Q4_K_M for agent tool calling",
            "metrics": {"tool_call_accuracy": 0.94},
            "why_it_worked": "AWQ protects salient weights identified via activation outliers.",
            "why_alternatives_failed": ["Naive round-to-nearest quantization destroyed json syntax validity"],
            "anti_patterns_discovered": ["Never quantize attention norm layers in function calling models"],
            "distilled_heuristics": ["Use AWQ for high precision tool JSON generation"],
        }
        res = engine.distill_why_knowledge(raw)
        self.assertEqual(res["experiment"], "Quantization Benchmark")
        self.assertIn("salient weights", res["causal_mechanism"]["why_this_design_succeeded"])
        self.assertEqual(len(res["causal_mechanism"]["why_alternatives_failed"]), 1)
        self.assertEqual(len(res["distilled_heuristics_for_agents"]), 1)


if __name__ == "__main__":
    unittest.main()
