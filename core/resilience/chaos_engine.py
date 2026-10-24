import asyncio
import os
import random

from core.logging_config import logger


class ChaosEngine:
    def __init__(self):
        # Only enable if explicitly set to "True" to prevent accidental production chaos
        self.enabled = os.getenv("ENABLE_CHAOS_MODE", "False").lower() == "true"

    async def inject_fault(self):
        """Randomly injects faults if chaos mode is enabled."""
        if not self.enabled:
            return

        # 5% chance to inject a fault when called
        if random.random() > 0.05:
            return

        fault_type = random.choice(["latency", "timeout", "cache_evict", "llm_down"])
        if fault_type == "latency":
            logger.warning("💉 Chaos: Injecting 2s latency to simulate network spike")
            await asyncio.sleep(2)
        elif fault_type == "timeout":
            logger.critical("💉 Chaos: Injecting artificial TimeoutError")
            raise TimeoutError("Simulated Chaos Timeout")
        elif fault_type == "cache_evict":
            logger.warning("💉 Chaos: Simulating Redis connection loss")
            # In a real scenario, this might close the redis connection
            # raise ConnectionError("Simulated Redis Connection Loss")
            pass
        elif fault_type == "llm_down":
            logger.critical("💉 Chaos: Simulating LLM Provider failure")
            # We can raise a simulated exception or just rely on the timeout
            raise ConnectionError("Simulated LLM Provider Down")


chaos_engine = ChaosEngine()
