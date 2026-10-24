import asyncio
from datetime import UTC, datetime

from core.logging_config import logger
from core.messaging.nats_messaging import nats_client


class WorkerRegistry:
    """
    Control Plane service that monitors active workers via NATS JetStream KV store.
    Provides Smart Routing capabilities.
    """

    def __init__(self):
        self.active_workers: dict[str, dict] = {}
        self.is_running = True

    async def watch_registry(self):
        """Watches the KV store for new/updated workers (Heartbeat Monitor)."""
        await nats_client.connect()
        if not nats_client.kv_store:
            logger.error("NATS KV store not initialized. Cannot watch registry.")
            return

        logger.info("🔭 WorkerRegistry is now watching for active edge nodes...")

        while self.is_running:
            try:
                workers = await nats_client.get_all_workers()
                current_time = datetime.now(UTC)

                valid_workers = {}
                for worker_id, data in workers.items():
                    # Check if worker is stale (no heartbeat in 15 seconds)
                    try:
                        last_heartbeat = datetime.fromisoformat(data["last_heartbeat"])
                        delta = (current_time - last_heartbeat).total_seconds()

                        if delta < 15:
                            if worker_id not in self.active_workers:
                                logger.info(
                                    f"🟢 New Worker Discovered: {worker_id} [{data.get('agent_type')}]"
                                )
                            valid_workers[worker_id] = data
                        else:
                            if worker_id in self.active_workers:
                                logger.warning(
                                    f"⚠️ Worker {worker_id} is stale and has been removed from active registry."
                                )
                            # Delete stale record from KV
                            await nats_client.kv_store.delete(worker_id)
                    except Exception as hb_err:
                        # বাংলা মন্তব্য: heartbeat পার্স বা KV delete ব্যর্থ হলে worker_id ও এরর লগ করা হচ্ছে
                        logger.warning(
                            f"⚠️ Worker registry: failed to process heartbeat for worker '{worker_id}'. "
                            f"Error: {hb_err!r}. This worker will be excluded from routing."
                        )

                self.active_workers = valid_workers
            except Exception as e:
                logger.error(f"Error reading worker registry: {e!s}")

            await asyncio.sleep(5)

    def get_workers_by_type(self, agent_type: str) -> list[dict]:
        """Returns active workers matching the requested type."""
        return [w for w in self.active_workers.values() if w.get("agent_type") == agent_type]

    async def schedule_maintenance(self, task_name: str = "intelligence-consolidation") -> dict:
        """Return a proposal for a worker; dispatch remains approval-controlled."""
        worker_id = self.get_smart_route("maintenance")
        return {
            "task": task_name,
            "worker_id": worker_id,
            "status": "proposal" if worker_id else "unavailable",
            "requires_approval": True,
        }

    def get_smart_route(self, agent_type: str, requires_gpu: bool = False) -> str | None:
        """
        Implements Smart Routing:
        Finds the best available worker for the task.
        """
        candidates = self.get_workers_by_type(agent_type)
        if requires_gpu:
            candidates = [c for c in candidates if c.get("gpu_available")]

        if not candidates:
            return None

        # For simplicity, returning the first available worker. Can be expanded to Round-Robin or Load-based.
        return candidates[0]["worker_id"]


worker_registry = WorkerRegistry()
