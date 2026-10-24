import asyncio
import logging
import os
import platform
import uuid
from datetime import UTC, datetime

from core.logging_config import logger
from core.messaging.nats_messaging import NATSClient


class SwarmWorkerNode:
    """
    Distributed Edge Worker that registers itself to the Control Plane
    and listens for specific tasks.
    """

    def __init__(self, agent_type: str = "general"):
        self.worker_id = f"worker_{uuid.uuid4().hex[:8]}"
        self.agent_type = agent_type
        self.nats = NATSClient(
            url=os.getenv("NATS_URL", "nats://localhost:4222"),
            token=os.getenv("NATS_TOKEN"),
        )
        self.is_running = True

    def get_capabilities(self):
        return {
            "worker_id": self.worker_id,
            "agent_type": self.agent_type,
            "os": platform.system(),
            "cpu_optimized": True,
            "gpu_available": False,  # Mock capability
            "status": "IDLE",
            "last_heartbeat": datetime.now(UTC).isoformat(),
        }

    async def heartbeat_loop(self):
        """Periodically pushes capabilities to the KV store (JetStream)."""
        while self.is_running:
            try:
                capabilities = self.get_capabilities()
                await self.nats.register_worker(self.worker_id, capabilities)
                logger.debug(f"💓 Heartbeat sent for {self.worker_id}")
            except Exception as e:
                logger.error(f"Heartbeat failed: {e!s}")
            await asyncio.sleep(5)  # 5 seconds interval

    async def handle_task(self, payload: dict):
        """Processes incoming tasks for this agent type."""
        logger.info(f"🚀 Received task: {payload}")
        # Simulated task execution (e.g. running LangChain/LiteLLM logic)
        await asyncio.sleep(2)
        logger.info(f"✅ Task completed by {self.worker_id}")

    async def start(self):
        await self.nats.connect()
        if not self.nats.nc:
            logger.error("Could not connect to NATS. Exiting...")
            return

        logger.info(f"🟢 Swarm Worker [{self.worker_id}] connected.")

        # Start Heartbeat loop
        self._heartbeat_task = asyncio.create_task(self.heartbeat_loop())

        # Subscribe to Task queue
        subject = f"TASK.ASSIGN.{self.agent_type}"
        await self.nats.subscribe(subject, self.handle_task)
        logger.info(f"🎧 Listening for tasks on {subject}...")

        # Keep alive loop
        while self.is_running:
            await asyncio.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Defaulting to Architect for demo purposes
    worker = SwarmWorkerNode(agent_type="Architect")
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        logger.info("Shutting down worker...")
