import time
from typing import Optional

from core.logging_config import logger

from ..config import settings
from .execution_recorder import execution_recorder
from .idempotency import create_idempotency_store
from .interfaces import AutomationProvider
from .models import AutomationEvent, AutomationResult, AutomationStatus


class AutomationDispatcher:
    """
    Central dispatcher for all background events.
    Determines which provider to use based on settings and routes the event.
    Core domain logic should only depend on this dispatcher, NEVER on a specific adapter.

    Plan Section 8: idempotency — একই idempotency_key দিয়ে দ্বিতীয়বার dispatch করলে
    prior result ফেরত দেয়।
    """

    def __init__(self):
        self._provider: AutomationProvider | None = None
        self._idempotency = create_idempotency_store()
        self._initialize_provider()

    def _initialize_provider(self):
        """
        Dynamically initialize the configured provider.
        """
        if not settings.automation_enabled:
            logger.info("Automation is disabled globally.")
            return

        if settings.n8n_enabled:
            try:
                from ..providers.n8n.adapter import N8nAutomationAdapter

                self._provider = N8nAutomationAdapter()
                logger.info("Initialized n8n automation provider.")
            except ImportError as e:
                logger.error(f"Failed to load n8n provider: {e}")
        else:
            # Fallback or stub provider could be loaded here if needed
            logger.debug("No automation provider enabled.")

    async def dispatch(self, event: AutomationEvent) -> AutomationResult:
        """
        Dispatch the event to the active provider.
        Plan Section 8: idempotency — একই idempotency_key দ্বিতীয়বার এলে cached result ফেরত দেয়।
        """
        # Plan Section 8: idempotency lookup using idempotency_key (fallback to event_id)
        idem_key = event.idempotency_key or event.event_id

        cached = await self._idempotency.get(idem_key)
        if cached is not None:
            logger.info(
                f"⚡ Idempotent hit: operation {idem_key} (event {event.event_id}) already dispatched — "
                f"returning cached result (status={cached.status.value})"
            )
            return cached

        if not settings.automation_enabled:
            return AutomationResult(
                status=AutomationStatus.SKIPPED,
                provider="none",
                message="Automation is disabled globally.",
                event_id=event.event_id,
            )

        if self._provider is None:
            return AutomationResult(
                status=AutomationStatus.SKIPPED,
                provider="none",
                message="No automation provider configured or available.",
                event_id=event.event_id,
            )

        # Plan Section 7: record dispatch start (best-effort DB persistence)
        started_at = time.time()
        execution_id = await execution_recorder.record_start(event)

        try:
            result = await self._provider.dispatch(event)
            # Plan Section 7: link event → execution
            if result.event_id is None:
                result.event_id = event.event_id
            # Plan Section 8: cache result for idempotency
            # শুধু DELIVERED বা FAILED cache করি (actual dispatch হওয়া result)
            # SKIPPED cache করি না কারণ সেটা provider unavailable/disabled state
            if result.status in (AutomationStatus.DELIVERED, AutomationStatus.FAILED):
                await self._idempotency.set(idem_key, result)
            # Plan Section 7: record dispatch completion
            await execution_recorder.record_completion(
                execution_id,
                event,
                result,
                provider_name=self._provider.__class__.__name__,
                started_at=started_at,
            )
            return result
        except Exception as e:
            logger.exception("Dispatcher caught unhandled exception from provider")
            failed_result = AutomationResult(
                status=AutomationStatus.FAILED,
                provider=self._provider.__class__.__name__ if self._provider else "none",
                message=f"Dispatcher Error: {str(e)}",
                event_id=event.event_id,
            )
            # exception-ও cache করি যাতে একই event বারবার fail না করে
            await self._idempotency.set(idem_key, failed_result)
            # Plan Section 7: record dispatch failure
            await execution_recorder.record_completion(
                execution_id,
                event,
                failed_result,
                provider_name=self._provider.__class__.__name__ if self._provider else "none",
                started_at=started_at,
            )
            return failed_result

    async def clear_idempotency_cache(self) -> None:
        """Admin/test এর জন্য cache clear করার method।"""
        await self._idempotency.clear()

    async def idempotency_cache_size(self) -> int:
        """Cache-এর বর্তমান size (observability)।"""
        return await self._idempotency.size()


# Singleton instance to be injected or imported by domain logic
automation_dispatcher = AutomationDispatcher()
