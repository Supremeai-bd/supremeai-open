import json
import os
from collections.abc import Callable
from typing import Any

from core.errors.error_bus import with_error_bus
from core.logging_config import logger

try:
    import nats
    from nats.errors import NoServersError
    from nats.js.errors import KeyValueError
except ModuleNotFoundError:  # pragma: no cover
    nats = None  # type: ignore[assignment]

    class NoServersError(Exception):  # type: ignore[no-redef]
        pass

    class KeyValueError(Exception):  # type: ignore[no-redef]
        pass


from pydantic import BaseModel


class NATSClient:
    """
    Centralized NATS Client for Distributed Swarm Edge Execution.
    Supports JetStream for Key-Value store (Worker Registry) and persistent queues.
    """

    def __init__(
        self,
        url: str = "nats://localhost:4222",
        token: str | None = None,
    ):
        self.url = url
        # বাংলা মন্তব্য: আগে এখানে হার্ডকোডেড ডিফল্ট টোকেন ("super_secret_token") ছিল,
        # যেটা প্রোডাকশনে ব্যবহৃত হলে একটা পাবলিকলি-জানা টোকেন দিয়ে NATS-এ authenticate
        # হয়ে যেত (security risk)। এখন worker_node.py-এর প্যাটার্ন অনুসরণ করে
        # NATS_TOKEN env var থেকে পড়া হচ্ছে, না থাকলে None (unauthenticated/no token).
        self.token = token if token is not None else os.getenv("NATS_TOKEN")
        self.nc = None
        self.js = None
        self.kv_store = None

    @with_error_bus("connect")
    async def connect(self):
        """Establishes connection to NATS with Token Auth and enables JetStream."""
        if nats is None:
            logger.warning(
                "[NATS] Optional dependency 'nats' is not installed. Skipping NATS connection."
            )
            return

        try:
            connect_kwargs = {"servers": [self.url]}
            if self.token:
                connect_kwargs["token"] = self.token

            self.nc = await nats.connect(**connect_kwargs)
            self.js = self.nc.jetstream()

            logger.info("✅ Connected to NATS Broker successfully.")

            # Initialize or bind to the Key-Value store for Worker Registry
            try:
                self.kv_store = await self.js.key_value("WORKER_REGISTRY")
            except Exception:
                # Create the bucket if it doesn't exist
                self.kv_store = await self.js.create_key_value(bucket="WORKER_REGISTRY")
                logger.info("🛠️ Created JetStream Key-Value bucket: WORKER_REGISTRY")

        except NoServersError:
            logger.error("❌ Failed to connect to NATS Broker. Is it running?")
        except Exception as e:
            logger.error(f"❌ NATS Connection Error: {e!s}")

    async def publish_event(self, subject: str, data: BaseModel | dict[str, Any]):
        """Publishes an event to a specific NATS subject."""
        if not self.nc:
            logger.warning("NATS client is not connected.")
            return

        payload = data.model_dump() if isinstance(data, BaseModel) else data
        await self.nc.publish(subject, json.dumps(payload).encode())

    async def subscribe(self, subject: str, callback: Callable):
        """Subscribes to a subject and triggers the callback asynchronously."""
        if not self.nc:
            logger.warning("NATS client is not connected.")
            return

        async def message_handler(msg):
            try:
                decoded_data = json.loads(msg.data.decode())
                await callback(decoded_data)
            except Exception as e:
                logger.error(f"Error handling NATS message on {subject}: {e!s}")

        await self.nc.subscribe(subject, cb=message_handler)

    # ---------------------------------------------------------
    # Worker Registry Methods (JetStream Key-Value Store)
    # ---------------------------------------------------------

    async def register_worker(self, worker_id: str, payload: dict):
        """Registers or updates a worker's heartbeat in the KV store."""
        if self.kv_store:
            await self.kv_store.put(worker_id, json.dumps(payload).encode())

    async def get_worker(self, worker_id: str) -> dict | None:
        """Retrieves worker info from the KV store."""
        if self.kv_store:
            try:
                entry = await self.kv_store.get(worker_id)
                return json.loads(entry.value.decode())
            except KeyValueError:
                return None
        return None

    async def get_all_workers(self) -> dict[str, dict]:
        """Retrieves all registered workers from the KV store."""
        workers: dict[str, dict] = {}
        if self.kv_store:
            try:
                keys = await self.kv_store.keys()
            except Exception as keys_err:
                # বাংলা মন্তব্য: KV store key list পেতে ব্যর্থ — swarm routing এ খালি list ফেরাবে
                logger.error(f"[NATS] Failed to list worker keys from KV store: {keys_err!r}")
                return workers
            skipped: list[str] = []
            for key in keys:
                try:
                    entry = await self.kv_store.get(key)
                    workers[key] = json.loads(entry.value.decode())
                except Exception as entry_err:
                    # বাংলা মন্তব্য: একটি key পার্স ব্যর্থ হলেও বাকিগুলো চলতে থাকবে
                    skipped.append(key)
                    logger.warning(f"[NATS] Skipped malformed worker entry '{key}': {entry_err!r}")
            if skipped:
                logger.warning(
                    f"[NATS] {len(skipped)} worker entries skipped due to errors: {skipped}"
                )
        return workers


# Global instance
nats_client = NATSClient()
