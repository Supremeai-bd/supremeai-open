"""Telemetry and event publishing for policy-driven web crawler."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from core.logging_config import logger
from core.messaging.event_bus import ErrorEvent, error_event_bus
from scout.models import CrawlEventType

#: বাংলা: fire-and-forget persistence-task-দের জীবন্ত রাখার সেট (GC-সুরক্ষা)।
_PENDING_PERSIST_TASKS: set[asyncio.Task[None]] = set()


class CrawlerTelemetry:
    """Dispatches lifecycle events and metrics for crawl tasks."""

    def __init__(self, tenant_id: str, task_id: str) -> None:
        self.tenant_id = tenant_id
        self.task_id = task_id

    def emit_event(
        self,
        event_type: CrawlEventType,
        message: str,
        severity: str = "INFO",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Publishes a structured crawl lifecycle event to the central event bus."""
        event_metadata = {
            "tenant_id": self.tenant_id,
            "task_id": self.task_id,
            "crawl_event": event_type.value,
            **(metadata or {}),
        }

        # Log locally for fast observability
        logger.info(f"[Crawler:{self.tenant_id}:{self.task_id}] {event_type.value}: {message}")

        # M08 P-D (issue #453 Wave 4): durable event persistence — crawl_events
        # টেবিলে প্রতিটি লাইফসাইকেল-ইভেন্ট পৌঁছায় (record_event নিজেই
        # best-effort: store-অনুপস্থিতে বাউন্ডেড ইন-মেমরি ফলব্যাক)। আগে এই
        # কলটি ছিল টেস্ট-দ্বীপে — প্রোডাকশনে ইভেন্ট কেবল লগে থাকত।
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # বাংলা: চলমান event-loop নেই (sync টেস্ট/কোল্ড পথ) — persistence
            # বাদ, কিন্তু চুপ নয়: লাউড warning রেখে যাওয়া হয়।
            logger.warning(
                f"[Crawler:{self.tenant_id}:{self.task_id}] event not persisted "
                f"(no running loop): {event_type.value}"
            )
        else:
            task = loop.create_task(
                self._persist_event(event_type, message, severity, event_metadata)
            )
            _PENDING_PERSIST_TASKS.add(task)
            task.add_done_callback(_PENDING_PERSIST_TASKS.discard)

        # If warning or error, forward to error event pipeline
        if severity in ["WARNING", "ERROR", "CRITICAL"]:
            error_event = ErrorEvent(
                module="scout.crawler",
                error_type=f"CRAWLER_{event_type.value.upper()}",
                message=message,
                severity=severity,
                context=event_metadata,
            )
            try:
                error_event_bus.emit(error_event)
            except Exception as exc:
                logger.warning(f"Failed to emit crawler telemetry event: {exc}")

    async def _persist_event(
        self,
        event_type: CrawlEventType,
        message: str,
        severity: str,
        metadata: dict[str, Any],
    ) -> None:
        """Fire-and-forget durable persistence (কখনো ক্রলার-নির্বাহ ব্লক করে না)।"""
        try:
            from scout.persistence import record_event

            await record_event(
                tenant_id=self.tenant_id,
                task_id=self.task_id,
                event_type=event_type.value,
                message=message,
                severity=severity,
                metadata=metadata,
            )
        except Exception as exc:
            # বাংলা: persistence-ব্যর্থতা ক্রলার মেরে ফেলবে না — কিন্তু নীরবেও
            # গিলবে না; লাউড warning (False-Assurance নীতি)।
            logger.warning(
                f"[Crawler:{self.tenant_id}:{self.task_id}] event persistence skipped: {exc!r}"
            )
