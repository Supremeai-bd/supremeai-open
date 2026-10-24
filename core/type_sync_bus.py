"""
SupremeAI — Type Sync Bus
==========================

Bridges the existing NATS messaging infrastructure with the Pydantic type generator.
Publishes schema change events whenever Pydantic models are modified, and provides
drift detection between generated types and source schemas.

Channels:
    types.sync           — Trigger type regeneration
    types.drift_detected — Alert when generated types are out of sync

Bengali:
    পাইথন পিজ্যান্টিক মডেল থেকে টাইপস্ক্রিপ্ট ও ডার্ট ফাইল জেনারেট করার লুপ
    মডেল স্কিমার যেকোনো পরিবর্তনে টাইপ ড্রিফট সনাক্ত করা হয়
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logging_config import logger

# ── Constants ─────────────────────────────────────────────────────────────────
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
GENERATE_TYPES_SCRIPT = SCRIPTS_DIR / "generate_types.py"
CHECKSUM_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "packages"
    / "shared-types"
    / ".type_checksums.json"
)

# NATS channels
CHANNEL_TYPE_SYNC = "types.sync"
CHANNEL_TYPE_DRIFT = "types.drift_detected"

# Event types
EVENT_GENERATE = "generate"
EVENT_DRIFT_DETECTED = "drift_detected"
EVENT_GENERATION_COMPLETE = "generation_complete"
EVENT_GENERATION_FAILED = "generation_failed"


class TypeSyncBus:
    """
    Type synchronization bus that bridges NATS messaging with type generation.

    Uses the existing NATSClient for message publishing and can optionally
    use SwarmPubSub as a fallback when NATS is unavailable.

    Usage:
        bus = TypeSyncBus()
        await bus.connect()
        await bus.trigger_generation()  # Manual trigger
        await bus.start_watching()      # Watch for schema changes
    """

    def __init__(self, nats_client: Any = None, swarm_pubsub: Any = None):
        self._nats = nats_client
        self._swarm = swarm_pubsub
        self._running = False
        self._watch_task: asyncio.Task | None = None

    async def connect(self) -> None:
        """Connect to the messaging infrastructure."""
        # Try NATS first
        if self._nats is not None:
            try:
                await self._nats.connect()
                logger.info("[TypeSyncBus] Connected to NATS")
                return
            except Exception as e:
                logger.warning(f"[TypeSyncBus] NATS connection failed: {e}")

        # Fall back to SwarmPubSub (Redis)
        if self._swarm is not None:
            logger.info("[TypeSyncBus] Using SwarmPubSub (Redis) as fallback")
            return

        logger.warning(
            "[TypeSyncBus] No messaging infrastructure available. Running in local mode."
        )

    async def disconnect(self) -> None:
        """Disconnect from the messaging infrastructure."""
        self._running = False
        if self._watch_task is not None:
            self._watch_task.cancel()
            self._watch_task = None
        logger.info("[TypeSyncBus] Disconnected")

    async def trigger_generation(self, source: str = "manual") -> dict[str, Any]:
        """
        Trigger type generation and publish result to the event bus.

        Args:
            source: Source of the trigger (e.g., 'manual', 'schema_change', 'ci')

        Returns:
            Dict with generation results
        """
        logger.info(f"[TypeSyncBus] Triggering type generation (source: {source})")

        # Run the generator script
        result = await self._run_generator()

        # Publish event
        event = {
            "type": EVENT_GENERATION_COMPLETE if result["success"] else EVENT_GENERATION_FAILED,
            "source": source,
            "timestamp": datetime.now(UTC).isoformat(),
            "result": result,
        }

        await self._publish(CHANNEL_TYPE_SYNC, event)

        # Check for drift after generation
        if result["success"]:
            drift_result = await self._check_drift()
            if drift_result["drift_detected"]:
                await self._publish(
                    CHANNEL_TYPE_DRIFT,
                    {
                        "type": EVENT_DRIFT_DETECTED,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "details": drift_result,
                    },
                )

        return result

    async def check_drift(self) -> dict[str, Any]:
        """Check if generated types are out of sync with schemas."""
        return await self._check_drift()

    async def start_watching(self, interval: int = 300) -> None:
        """
        Start watching for schema changes at a regular interval.

        Args:
            interval: Check interval in seconds (default: 5 minutes)
        """
        if self._running:
            logger.warning("[TypeSyncBus] Already watching")
            return

        self._running = True
        self._watch_task = asyncio.create_task(self._watch_loop(interval))
        logger.info(f"[TypeSyncBus] Started watching (interval: {interval}s)")

    async def stop_watching(self) -> None:
        """Stop watching for schema changes."""
        self._running = False
        if self._watch_task is not None:
            self._watch_task.cancel()
            self._watch_task = None
        logger.info("[TypeSyncBus] Stopped watching")

    # ── Internal Methods ──────────────────────────────────────────────────────

    async def _run_generator(self) -> dict[str, Any]:
        """Run the type generator script as a subprocess."""
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(GENERATE_TYPES_SCRIPT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=SCRIPTS_DIR.parent,  # Run from repo root
            )
            timeout_val = float(os.getenv("TYPE_SYNC_TIMEOUT", "120"))
            stdout, stderr = await proc.communicate(timeout=timeout_val)  # type: ignore

            success = proc.returncode == 0
            return {
                "success": success,
                "return_code": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace") if stdout else "",
                "stderr": stderr.decode("utf-8", errors="replace") if stderr else "",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except TimeoutError:
            return {
                "success": False,
                "error": f"Generation timed out after {timeout_val} seconds",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def _check_drift(self) -> dict[str, Any]:
        """Check for type drift by running the generator in validate mode."""
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(GENERATE_TYPES_SCRIPT),
                "--validate",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=SCRIPTS_DIR.parent,
            )
            timeout_val_validate = float(os.getenv("TYPE_SYNC_TIMEOUT", "60"))
            stdout, _stderr = await proc.communicate(timeout=timeout_val_validate)  # type: ignore

            drift_detected = proc.returncode != 0
            return {
                "drift_detected": drift_detected,
                "return_code": proc.returncode,
                "output": stdout.decode("utf-8", errors="replace") if stdout else "",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            return {
                "drift_detected": True,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def _publish(self, channel: str, data: dict[str, Any]) -> None:
        """Publish a message to the event bus."""
        message = json.dumps(data, default=str)

        # Try NATS
        if self._nats is not None:
            try:
                await self._nats.publish(channel, message)
                logger.debug(f"[TypeSyncBus] Published to NATS channel '{channel}'")
                return
            except Exception as e:
                logger.warning(f"[TypeSyncBus] NATS publish failed: {e}")

        # Try SwarmPubSub
        if self._swarm is not None:
            try:
                await self._swarm.publish(channel, message)
                logger.debug(f"[TypeSyncBus] Published to SwarmPubSub channel '{channel}'")
                return
            except Exception as e:
                logger.warning(f"[TypeSyncBus] SwarmPubSub publish failed: {e}")

        logger.debug(f"[TypeSyncBus] (local) Event: {channel} — {message[:200]}")

    async def _watch_loop(self, interval: int) -> None:
        """Background loop that periodically checks for drift."""
        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    break

                logger.debug("[TypeSyncBus] Running periodic drift check...")
                drift = await self._check_drift()

                if drift["drift_detected"]:
                    logger.warning("[TypeSyncBus] Drift detected! Triggering regeneration...")
                    await self.trigger_generation(source="periodic_check")
                else:
                    logger.debug("[TypeSyncBus] No drift detected")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[TypeSyncBus] Watch loop error: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────

_type_sync_bus_instance: TypeSyncBus | None = None


def get_type_sync_bus(nats_client: Any = None, swarm_pubsub: Any = None) -> TypeSyncBus:
    """
    Get or create the TypeSyncBus singleton.

    Args:
        nats_client: Optional NATSClient instance
        swarm_pubsub: Optional SwarmPubSub instance

    Returns:
        TypeSyncBus singleton
    """
    global _type_sync_bus_instance
    if _type_sync_bus_instance is None:
        _type_sync_bus_instance = TypeSyncBus(
            nats_client=nats_client,
            swarm_pubsub=swarm_pubsub,
        )
    return _type_sync_bus_instance
