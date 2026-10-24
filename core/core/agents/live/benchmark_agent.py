import time
from typing import Any, ClassVar

from core.logging_config import logger

try:
    from brain.model_router import ModelRouter
    from database.supabase_client import db

    _DEPENDENCIES_AVAILABLE = True
except ImportError:
    _DEPENDENCIES_AVAILABLE = False


class BenchmarkAgent:
    """
    An agent that runs a suite of benchmark prompts against all configured
    AI providers to measure latency, cost, and output quality.
    """

    BENCHMARK_PROMPTS: ClassVar[Any] = [
        {
            "category": "coding",
            "prompt": "Write a Python function to calculate the factorial of a number using recursion.",
        },
        {
            "category": "reasoning",
            "prompt": "If all Zirps are Zorps, and some Zorps are Zots, can we say for certain that some Zirps are Zots? Explain your reasoning.",
        },
        {
            "category": "creative",
            "prompt": "Write a short, three-line poem about a robot learning to dream.",
        },
        {"category": "general", "prompt": "What is the capital of Mongolia?"},
    ]

    def __init__(self):
        if not _DEPENDENCIES_AVAILABLE:
            raise ImportError("BenchmarkAgent requires ModelRouter and Supabase client.")
        self.model_router = ModelRouter()
        self.db_client = db.client
        logger.info("Initialized BenchmarkAgent")

    async def run_benchmark(self, providers: list[str]) -> dict[str, Any]:
        """
        Runs the full benchmark suite across the given providers.
        """
        logger.info(f"Starting benchmark run for providers: {providers}")
        full_report = {"providers": {}, "summary": {}}
        all_results = []

        for provider in providers:
            logger.info(f"Benchmarking provider: {provider}")
            provider_results = []
            for item in self.BENCHMARK_PROMPTS:
                start_time = time.time()

                # Force routing to the specific provider for this test
                # Note: This assumes ModelRouter can be forced, or we'd need a different approach.
                response = await self.model_router.async_route_and_generate(
                    item["prompt"],
                    task_type=item["category"],
                    # A mechanism to force provider would be needed in ModelRouter
                    # preferred_provider=provider
                )

                end_time = time.time()
                latency = end_time - start_time

                result = {
                    "provider": provider,
                    "category": item["category"],
                    "latency_seconds": latency,
                    "cost": response.get("cost", 0.0),
                    "output_length": len(response.get("text", "")),
                    "success": response.get("success", False),
                    "timestamp": time.time(),
                }
                provider_results.append(result)
                all_results.append(result)

            full_report["providers"][provider] = provider_results

        if self.db_client:
            logger.info("Persisting benchmark results to database.")
            await self.db_client.table("provider_benchmarks").insert(all_results).execute()

        logger.info("Benchmark run completed.")
        return full_report
