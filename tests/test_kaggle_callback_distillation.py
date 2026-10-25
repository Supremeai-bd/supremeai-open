import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT))

from gateway.routes.kaggle import (
    KaggleCallbackRequest,
    distill_kaggle_callback_knowledge,
    ingest_distilled_knowledge,
)


class TestKaggleCallbackDistillation(unittest.TestCase):
    def test_distillation_on_success(self):
        req = KaggleCallbackRequest(
            job_id="job-12345678-abcd",
            status="success",
            completed_at="2026-10-25T01:00:00Z",
            result={
                "task": "self_healing_code",
                "base_model": "Qwen-2.5-Coder-7B",
                "loss": 0.38,
                "why_it_worked": "QLoRA rank r=8 on attention heads preserved AST syntax integrity while avoiding VRAM OOM.",
                "why_alternatives_failed": [
                    "Dense fine-tuning ran out of memory on 16GB VRAM",
                ],
                "anti_patterns_discovered": [
                    "Unfreezing embedding layer on small dataset causes gradient variance",
                ],
                "distilled_heuristics": [
                    "For code repair specialization, target Q/V projections with r=8.",
                ],
            },
        )
        distilled = distill_kaggle_callback_knowledge(req)
        self.assertEqual(distilled["status"], "success")
        self.assertEqual(distilled["experiment"], "self_healing_code")
        self.assertIn("AST syntax integrity", distilled["causal_mechanism"]["why_this_design_succeeded"])
        self.assertEqual(len(distilled["causal_mechanism"]["why_alternatives_failed"]), 1)
        self.assertEqual(len(distilled["distilled_heuristics_for_agents"]), 1)
        self.assertIn("r=8", distilled["distilled_heuristics_for_agents"][0])

    def test_distillation_on_failure_produces_anti_patterns(self):
        req = KaggleCallbackRequest(
            job_id="job-99999999-fail",
            status="failed",
            completed_at="2026-10-25T01:00:00Z",
            error="CUDA out of memory. Tried to allocate 4.20 GiB on device 0",
        )
        distilled = distill_kaggle_callback_knowledge(req)
        self.assertEqual(distilled["status"], "failed")
        self.assertIn("Failed Kaggle Run", distilled["experiment"])
        self.assertIn("CUDA out of memory", distilled["causal_mechanism"]["why_alternatives_failed"][0])
        self.assertIn("CUDA out of memory", distilled["distilled_heuristics_for_agents"][0])

    def test_ingest_distilled_knowledge_offline_graceful(self):
        distilled = {
            "experiment": "offline_test",
            "hypothesis": "test hypothesis",
            "status": "success",
            "causal_mechanism": {
                "why_this_design_succeeded": "Unit test simulation",
                "why_alternatives_failed": [],
                "anti_patterns_to_avoid": [],
            },
            "distilled_heuristics_for_agents": ["Rule 1"],
        }
        res = asyncio.run(ingest_distilled_knowledge(distilled))
        self.assertTrue(res)

    def test_trigger_hourly_learning_cron_response(self):
        from fastapi import BackgroundTasks
        from gateway.routes.kaggle import trigger_hourly_learning_cron

        bg = BackgroundTasks()
        res = asyncio.run(trigger_hourly_learning_cron(background_tasks=bg, x_cron_source="cloudflare-edge"))
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["action"], "hourly_learning_sync_dispatched")
        self.assertEqual(res["cron_source"], "cloudflare-edge")
        self.assertIn("timestamp", res)


if __name__ == "__main__":
    unittest.main()

