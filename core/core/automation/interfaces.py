from typing import Protocol, runtime_checkable

from .models import AutomationEvent, AutomationResult, IntegrationHealth


@runtime_checkable
class AutomationProvider(Protocol):
    """
    Protocol defining the contract for any background automation provider (n8n, Celery, etc).
    """

    async def dispatch(self, event: AutomationEvent) -> AutomationResult:
        """
        Dispatch an event to the automation provider.

        Args:
            event: The validated event payload and routing key.

        Returns:
            AutomationResult containing the status and provider info.
        """
        ...

    async def health(self) -> IntegrationHealth:
        """
        Check the health of the integration.
        """
        ...
