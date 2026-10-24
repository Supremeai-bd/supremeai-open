"""Internet Monitor Agent for SupremeAI 2.0
Monitors GitHub trending repos, AI world updates, and system capabilities to keep admins informed.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.logging_config import logger

# aiohttp প্যাকেজ উপলব্ধ না থাকলে সেফ ইমপোর্ট ফলব্যাক।
try:
    import aiohttp
except ImportError:
    aiohttp = None

from core.cache.redis_manager import redis_manager
from core.config import settings

# Remove the problematic import and use alternative
# from core.security.authentication.auth_middleware import get_current_active_user
from core.health_check import health_checker
from core.llm.token_deductor import TokenDeductor
from core.messaging.event_bus import EventBus


@dataclass
class UpdateInfo:
    """Data class to hold update information."""

    source: str
    title: str
    description: str
    url: str
    timestamp: datetime
    category: str  # 'github_trending', 'ai_updates', 'system_capability', 'security_alert'


class InternetMonitorAgent:
    """Agent that continuously monitors internet for updates and system status."""

    def __init__(self):
        self.name = "Internet Monitor Agent"
        self.session: aiohttp.ClientSession | None = None
        self.event_bus = EventBus()
        self.token_deductor = TokenDeductor()
        self.check_interval = getattr(settings, "internet_monitor_interval", 3600)  # Default 1 hour
        self.update_history_key = "internet_monitor:update_history"
        self.system_capabilities_key = "internet_monitor:system_capabilities"

    async def initialize(self):
        """Initialize the agent with HTTP session."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "SupremeAI-InternetMonitor/2.0"},
        )
        # Load system capabilities on startup
        await self._discover_system_capabilities()

    async def cleanup(self):
        """Clean up resources."""
        if self.session:
            await self.session.close()

    async def _discover_system_capabilities(self):
        """Discover current system capabilities and store them."""
        try:
            capabilities = {
                "timestamp": datetime.utcnow().isoformat(),
                "features": [],
                "missing_features": [],
                "update_status": {},
            }

            # Check available tools
            # Since we don't have direct access to get_available_tools, let's check the tools directory
            import os

            tools_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools")
            if os.path.exists(tools_dir):
                for item in os.listdir(tools_dir):
                    if item.endswith(".py") and item != "__init__.py":
                        capabilities["features"].append(item[:-3])  # Remove .py extension

            # Check available agents
            import os

            agents_dir = os.path.join(os.path.dirname(__file__))
            if os.path.exists(agents_dir):
                for item in os.listdir(agents_dir):
                    if (
                        item.endswith(".py")
                        and item != "__init__.py"
                        and item != "internet_monitor_agent.py"
                    ):
                        capabilities["features"].append(item[:-3])  # Remove .py extension

            # Store in Redis
            await redis_manager.set_with_ttl(
                self.system_capabilities_key,
                json.dumps(capabilities),
                ttl=86400,  # 24 hours
            )

            logger.info(f"Discovered {len(capabilities['features'])} system capabilities")

        except Exception as e:
            logger.error(f"Error discovering system capabilities: {e}")

    async def get_system_capabilities(self) -> dict:
        """Get current system capabilities."""
        try:
            data = await redis_manager.get(self.system_capabilities_key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error retrieving system capabilities: {e}")

        return {"features": [], "missing_features": [], "update_status": {}}

    async def monitor_github_trending(self) -> list[UpdateInfo]:
        """Monitor GitHub trending repositories."""
        updates = []

        try:
            # Using GitHub API as an alternative to RSS
            github_token = getattr(settings, "GITHUB_TOKEN", None)
            headers = {"Authorization": f"token {github_token}"} if github_token else {}

            # Use GitHub trending API via third-party service since official API doesn't have this
            url = "https://api.github.com/search/repositories?q=stars:>1000&sort=updated&order=desc"
            params = {"per_page": 5}

            if self.session:
                async with self.session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        for repo in data.get("items", [])[:5]:  # Top 5 trending
                            updates.append(
                                UpdateInfo(
                                    source="GitHub Trending",
                                    title=f"Trending Repository: {repo.get('name', 'Unknown')}",
                                    description=repo.get("description", "No description available"),
                                    url=repo.get("html_url", ""),
                                    timestamp=datetime.utcnow(),
                                    category="github_trending",
                                )
                            )
                    else:
                        # Fallback to basic update
                        logger.warning(
                            f"GitHub API failed with status {response.status}, using fallback"
                        )
                        # This is a simplified version - in reality, we'd scrape the actual page
                        fallback_updates = [
                            UpdateInfo(
                                source="GitHub Trending (Fallback)",
                                title="Popular Repository Update",
                                description="A popular repository has gained significant traction recently",
                                url="https://github.com/trending",
                                timestamp=datetime.utcnow(),
                                category="github_trending",
                            )
                        ]
                        updates.extend(fallback_updates)
            else:
                logger.warning("HTTP session not initialized, skipping GitHub monitoring")

        except Exception as e:
            logger.error(f"Error monitoring GitHub trending: {e}")

        return updates

    async def monitor_ai_world_updates(self) -> list[UpdateInfo]:
        """Monitor AI world updates from various sources."""
        updates = []

        try:
            if not self.session:
                logger.warning("HTTP session not initialized, skipping AI world monitoring")
                return updates

            # Monitor Hugging Face model hub
            huggingface_url = "https://huggingface.co/api/models?sort=trending&limit=3"
            async with self.session.get(huggingface_url) as response:
                if response.status == 200:
                    data = await response.json()

                    for model in data[:3]:  # Top 3 trending models
                        updates.append(
                            UpdateInfo(
                                source="Hugging Face",
                                title=f"New Trending Model: {model.get('id', 'Unknown')}",
                                description=model.get("cardData", {}).get(
                                    "summary", "New AI model released"
                                ),
                                url=f"https://huggingface.co/{model.get('id', '')}",
                                timestamp=datetime.utcnow(),
                                category="ai_updates",
                            )
                        )
        except Exception as e:
            logger.error(f"Error monitoring Hugging Face: {e}")

        # Monitor AI news from a public API (using a placeholder for demo)
        try:
            # Using a news API as example - in production, could use NewsAPI or similar
            news_sources = [
                {
                    "source": "AI News",
                    "title": "Latest AI Development",
                    "description": "Important update in the AI world that may affect your system",
                    "url": "https://example.com/ai-news",
                }
            ]

            for news_item in news_sources:
                updates.append(
                    UpdateInfo(
                        source=news_item["source"],
                        title=news_item["title"],
                        description=news_item["description"],
                        url=news_item["url"],
                        timestamp=datetime.utcnow(),
                        category="ai_updates",
                    )
                )
        except Exception as e:
            logger.error(f"Error monitoring AI news: {e}")

        return updates

    async def compare_system_vs_updates(self) -> list[UpdateInfo]:
        """Compare system capabilities against new updates to identify missing features."""
        updates = []

        try:
            # Get current system capabilities
            system_caps = await self.get_system_capabilities()
            current_features = set(system_caps.get("features", []))

            # Get recent updates
            github_updates = await self.monitor_github_trending()
            ai_updates = await self.monitor_ai_world_updates()

            # Identify potentially relevant updates for our system
            for update in github_updates + ai_updates:
                # Check if this update relates to a capability we might be missing
                title_lower = update.title.lower()

                # Keywords that might indicate relevant technologies
                relevant_keywords = [
                    "llm",
                    "gpt",
                    "transformer",
                    "neural",
                    "ml",
                    "ai",
                    "chatbot",
                    "agent",
                    "supremeai",
                    "fastapi",
                    "python",
                    "gemini",
                    "openai",
                    "gemini",
                    "claude",
                    "llama",
                    "mistral",
                    "dalle",
                    "gpt",
                    "chatgpt",
                ]

                if any(keyword in title_lower for keyword in relevant_keywords):
                    # Check if this is something we don't currently have
                    missing_indicator = (
                        "not available" in update.description.lower()
                        or "new technique" in update.description.lower()
                        or "novel approach" in update.description.lower()
                    )

                    if missing_indicator or any(
                        feature.lower() in title_lower for feature in current_features
                    ):
                        updates.append(
                            UpdateInfo(
                                source=f"{update.source} - Capability Alert",
                                title=f"Potentially Missing Feature: {update.title}",
                                description=f"This update may represent a capability that's not yet available in SupremeAI: {update.description}",
                                url=update.url,
                                timestamp=datetime.utcnow(),
                                category="system_capability",
                            )
                        )
        except Exception as e:
            logger.error(f"Error comparing system vs updates: {e}")

        return updates

    async def monitor_system_health_and_gaps(self) -> list[UpdateInfo]:
        """Monitor system health and identify capability gaps."""
        updates = []

        try:
            # Check system health
            health_status = await health_checker.check_all()  # Use the correct function

            # Identify system gaps and status
            gap_description = "System is functioning normally but may have capability gaps compared to latest developments"

            # Check for any subsystem issues
            for subsystem, status in health_status.get("checks", {}).items():
                if status.get("status") == "unhealthy":
                    updates.append(
                        UpdateInfo(
                            source="System Health",
                            title=f"Sub-system Issue: {subsystem}",
                            description=status.get("message", "Unknown issue"),
                            url="",
                            timestamp=datetime.utcnow(),
                            category="system_capability",
                        )
                    )

            # Add general capability gap notice
            updates.append(
                UpdateInfo(
                    source="System Capability Monitor",
                    title="Capability Gap Assessment",
                    description=gap_description,
                    url="",
                    timestamp=datetime.utcnow(),
                    category="system_capability",
                )
            )

        except Exception as e:
            logger.error(f"Error monitoring system health: {e}")

        return updates

    async def get_latest_updates(self) -> list[UpdateInfo]:
        """Get the latest updates from all monitored sources."""
        all_updates = []

        # Gather updates from all sources
        all_updates.extend(await self.monitor_github_trending())
        all_updates.extend(await self.monitor_ai_world_updates())
        all_updates.extend(await self.compare_system_vs_updates())
        all_updates.extend(await self.monitor_system_health_and_gaps())

        # Sort by timestamp (most recent first)
        all_updates.sort(key=lambda x: x.timestamp, reverse=True)

        # Store in history
        update_dicts = [
            {
                "source": u.source,
                "title": u.title,
                "description": u.description,
                "url": u.url,
                "timestamp": u.timestamp.isoformat(),
                "category": u.category,
            }
            for u in all_updates
        ]

        # Keep last 50 updates in history
        if self.session:  # Only store if session is initialized
            try:
                # Convert list to JSON string and store in Redis
                await redis_manager.set_with_ttl(
                    self.update_history_key,
                    json.dumps(update_dicts[:50]),
                    ttl=86400,  # 24 hours
                )
            except Exception as e:
                logger.error(f"Error storing update history: {e}")

        return all_updates

    async def get_update_summary(self) -> dict[str, Any]:
        """Get a summary of updates organized by category."""
        updates = await self.get_latest_updates()

        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "total_updates": len(updates),
            "by_category": {
                "github_trending": [],
                "ai_updates": [],
                "system_capability": [],
                "security_alert": [],
            },
            "top_updates": updates[:5],  # Top 5 most recent
        }

        for update in updates:
            if update.category in summary["by_category"]:
                summary["by_category"][update.category].append(
                    {
                        "title": update.title,
                        "description": update.description,
                        "url": update.url,
                        "timestamp": update.timestamp.isoformat(),
                    }
                )

        return summary

    async def start_monitoring_loop(self):
        """Start the continuous monitoring loop."""
        logger.info("Starting Internet Monitor Agent...")

        while True:
            try:
                logger.info("Checking for updates...")
                updates = await self.get_latest_updates()

                if updates:
                    logger.info(f"Found {len(updates)} updates")

                    # Emit event for admin notification
                    await self.event_bus.emit(
                        "internet_updates_available",
                        {
                            "count": len(updates),
                            "updates": [
                                {
                                    "source": u.source,
                                    "title": u.title,
                                    "category": u.category,
                                    "timestamp": u.timestamp.isoformat(),
                                }
                                for u in updates[:3]  # Send top 3 updates
                            ],
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    )

                # Wait for next check
                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                logger.info("Internet Monitor Agent cancelled")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                # Wait before retrying
                await asyncio.sleep(300)  # 5 minutes before retrying

    async def get_update_history(self) -> list[dict]:
        """Get historical updates from Redis."""
        try:
            data = await redis_manager.get(self.update_history_key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error retrieving update history: {e}")

        return []


# Global instance
internet_monitor_agent = InternetMonitorAgent()


async def initialize_internet_monitor():
    """Initialize the internet monitor agent."""
    await internet_monitor_agent.initialize()


async def get_internet_updates():
    """Get the latest updates from the internet monitor."""
    return await internet_monitor_agent.get_latest_updates()


async def get_update_summary():
    """Get a summary of updates."""
    return await internet_monitor_agent.get_update_summary()


async def get_update_history():
    """Get historical updates."""
    return await internet_monitor_agent.get_update_history()
