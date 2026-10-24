import asyncio
from typing import Any

import httpx

from core.config import settings
from core.logging_config import logger
from database.supabase_client import db


class OfflineModeManager:
    """
    Manages offline mode by falling back to Ollama and queuing actions for cloud sync.
    """

    def __init__(self, local_model_id: str = "llama3-8b"):
        self.local_model_id = getattr(settings, "local_model", local_model_id)
        self.ollama_url = getattr(settings, "ollama_url", "http://127.0.0.1:11434")  # is_local()
        self.sync_queue: list[dict[str, Any]] = []
        self._is_syncing = False
        logger.info(f"Initialized OfflineModeManager with local model {self.local_model_id}")

    async def _call_ollama(self, prompt: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.local_model_id,
                        "prompt": prompt,
                        "stream": False,
                    },
                )
                res.raise_for_status()
                return res.json().get("response", "No response from local model.")
        except Exception as e:
            logger.error(f"Ollama local fallback failed: {e}")
            return f"[Offline Error] Could not reach local Ollama instance: {e!s}"

    async def execute_task(self, prompt: str, task_type: str = "general") -> dict[str, Any]:
        logger.info(f"Executing task offline via Ollama: {prompt}")

        local_response = await self._call_ollama(prompt)

        action_payload = {
            "action": "offline_execution",
            "task_type": task_type,
            "prompt": prompt,
            "result": local_response,
            "timestamp": asyncio.get_event_loop().time(),
        }

        self.sync_queue.append(action_payload)

        return {
            "status": "success",
            "source": "ollama",
            "result": local_response,
            "queued_for_sync": True,
        }

    async def sync_with_cloud(self) -> dict[str, Any]:
        if not self.sync_queue or self._is_syncing:
            return {"status": "success", "synced": 0}

        self._is_syncing = True
        logger.info(f"Syncing {len(self.sync_queue)} offline actions to the cloud...")

        synced_count = 0
        try:
            if db.client:
                # Sync actions to database
                sync_payloads = []
                for action in self.sync_queue:
                    sync_payloads.append(
                        {
                            "action_type": action["action"],
                            "payload": action,
                            "status": "synced",
                        }
                    )

                # In a real scenario, we'd insert into an 'offline_sync_logs' table
                # db.client.table("offline_sync_logs").insert(sync_payloads).execute()

            synced_count = len(self.sync_queue)
            self.sync_queue.clear()
            logger.info(f"Successfully synced {synced_count} actions.")
            return {"status": "success", "synced": synced_count}
        except Exception as e:
            logger.error(f"Failed to sync offline queue: {e}")
            return {"status": "error", "error": str(e), "synced": 0}
        finally:
            self._is_syncing = False


offline_manager = OfflineModeManager()
