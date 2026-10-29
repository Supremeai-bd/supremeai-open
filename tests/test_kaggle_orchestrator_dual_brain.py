#!/usr/bin/env python3
"""Contract & Unit Tests for Kaggle Orchestrator Dual-Brain Recipes and Multi-Account Rotation."""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.kaggle_orchestrator import (
    KaggleAccount,
    KaggleAccountStatus,
    KaggleJob,
    KaggleOrchestrator,
    KaggleTaskType,
)


class TestKaggleOrchestratorDualBrain(unittest.TestCase):
    def setUp(self):
        self.accounts = [
            KaggleAccount(
                account_id=f"worker_{i + 1}",
                username=f"worker_{i + 1}",
                api_key=f"key_{i + 1}",
                max_hours=30.0,
                used_hours=0.0,
            )
            for i in range(6)
        ]
        # Initialize orchestrator with dummy redis url
        self.orchestrator = KaggleOrchestrator(redis_url="", accounts=self.accounts)

    def test_dual_brain_task_types_exist(self):
        """Verify TaskTypes for Brain 1 (Coding) and Brain 2 (Customer) are defined."""
        self.assertEqual(KaggleTaskType.SELF_HEALING_CODE.value, "self_healing_code")
        self.assertEqual(KaggleTaskType.CUSTOMER_REASONING.value, "customer_reasoning")

    def test_kernel_template_includes_dual_brain_recipes(self):
        """Verify KERNEL_TEMPLATE contains real training recipes for both brains."""
        # Brain 1: Self-healing code
        job_code = KaggleJob(
            job_id="job_code_001",
            task_type=KaggleTaskType.SELF_HEALING_CODE,
            payload={
                "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "hyperparameters": {"epochs": 2, "lora_r": 16},
            },
        )
        kernel_code = self.orchestrator._generate_kernel_code(job_code, callback_token="tok_123")
        self.assertIn("job_code_001", kernel_code)
        self.assertIn("self_healing_code", kernel_code)
        self.assertIn("run_self_healing_code", kernel_code)
        self.assertIn("adapter_coding_brain", kernel_code)
        self.assertIn("tok_123", kernel_code)

        # Brain 2: Customer reasoning
        job_cust = KaggleJob(
            job_id="job_cust_002",
            task_type=KaggleTaskType.CUSTOMER_REASONING,
            payload={
                "base_model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                "hyperparameters": {"epochs": 3, "lora_r": 32},
            },
        )
        kernel_cust = self.orchestrator._generate_kernel_code(job_cust, callback_token="tok_456")
        self.assertIn("job_cust_002", kernel_cust)
        self.assertIn("customer_reasoning", kernel_cust)
        self.assertIn("run_customer_reasoning", kernel_cust)
        self.assertIn("adapter_customer_intelligence", kernel_cust)
        self.assertIn("tok_456", kernel_cust)

    def test_lru_round_robin_account_rotation(self):
        """Verify accounts rotate using Least-Recently-Used and remaining hours."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # Set different last_used times for accounts
        for i, acc in enumerate(self.accounts):
            acc.last_used = now - timedelta(hours=(6 - i))  # worker_1 oldest, worker_6 newest

        job = KaggleJob(
            job_id="job_rot_01",
            task_type=KaggleTaskType.SELF_HEALING_CODE,
            payload={},
            estimated_hours=2.0,
        )

        import asyncio

        selected = asyncio.run(self.orchestrator.select_account_for_job(job))
        # worker_1 has the oldest last_used, so it must be selected first
        self.assertIsNotNone(selected)
        self.assertEqual(selected.account_id, "worker_1")

        # Simulate worker_1 just finished
        selected.last_used = datetime.now(timezone.utc).replace(tzinfo=None)
        selected2 = asyncio.run(self.orchestrator.select_account_for_job(job))
        # Next oldest should be worker_2
        self.assertEqual(selected2.account_id, "worker_2")


if __name__ == "__main__":
    unittest.main()
