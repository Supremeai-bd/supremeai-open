"""
Internet Monitor Service
=======================
Service to manage the lifecycle of the internet monitoring agent.
"""

import asyncio

# Fixed import path - using absolute import from backend
from agents.internet_monitor_agent import internet_monitor_agent
from core.logging_config import logger


class InternetMonitorService:
    """Service to manage the internet monitoring agent."""

    def __init__(self):
        self.agent = internet_monitor_agent
        self.monitoring_task: asyncio.Task | None = None
        self.is_running = False

    async def initialize(self):
        """Initialize the service and agent."""
        try:
            await self.agent.initialize()
            logger.info("Internet Monitor Service initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Internet Monitor Service: {e}")
            raise

    async def start_monitoring(self):
        """Start the continuous monitoring process."""
        if self.is_running:
            logger.warning("Internet monitoring is already running")
            return

        try:
            self.monitoring_task = asyncio.create_task(self.agent.start_monitoring_loop())
            self.is_running = True
            logger.info("Internet monitoring started successfully")
        except Exception as e:
            logger.error(f"Error starting internet monitoring: {e}")
            raise

    async def stop_monitoring(self):
        """Stop the continuous monitoring process."""
        if not self.is_running:
            logger.warning("Internet monitoring is not running")
            return

        try:
            if self.monitoring_task:
                self.monitoring_task.cancel()
                try:
                    await self.monitoring_task
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).exception(f"Silenced error: {e}")

            self.is_running = False
            logger.info("Internet monitoring stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping internet monitoring: {e}")
            raise

    async def get_status(self):
        """Get the current status of the monitoring service."""
        return {
            "is_running": self.is_running,
            "is_initialized": self.agent.session is not None,
            "check_interval": self.agent.check_interval,
            "name": self.agent.name,
        }

    async def get_latest_updates(self):
        """Get the latest updates from the agent."""
        return await self.agent.get_latest_updates()

    async def get_update_summary(self):
        """Get the update summary from the agent."""
        return await self.agent.get_update_summary()

    async def get_update_history(self):
        """Get the update history from the agent."""
        return await self.agent.get_update_history()


# Global instance
internet_monitor_service = InternetMonitorService()


async def initialize_internet_monitor_service():
    """Initialize the internet monitor service."""
    await internet_monitor_service.initialize()


async def start_internet_monitoring():
    """Start the internet monitoring process."""
    await internet_monitor_service.start_monitoring()


async def stop_internet_monitoring():
    """Stop the internet monitoring process."""
    await internet_monitor_service.stop_monitoring()


def get_internet_monitor_service():
    """Get the internet monitor service instance."""
    return internet_monitor_service
