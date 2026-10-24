import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.plugins.seed_manifests import OFFICIAL_PLUGINS
from models.plugin_manifest import PluginManifest

logger = logging.getLogger(__name__)


class PluginManifestRegistry:
    """
    Handles discovery and retrieval of Plugin Manifests.
    Separates concerns from system integration registry (which handles n8n, etc.).
    """

    @staticmethod
    async def get_all_manifests(
        session: AsyncSession, active_only: bool = True
    ) -> list[PluginManifest]:
        query = select(PluginManifest)
        if active_only:
            query = query.where(PluginManifest.is_active)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_manifest_by_id(session: AsyncSession, plugin_id: str) -> PluginManifest | None:
        query = select(PluginManifest).where(PluginManifest.id == plugin_id)
        result = await session.execute(query)
        return result.scalars().first()

    @staticmethod
    async def seed_official_plugins(session: AsyncSession) -> None:
        """
        Idempotent seeding of official plugins from code into the database.
        """
        for plugin_data in OFFICIAL_PLUGINS:
            existing = await PluginManifestRegistry.get_manifest_by_id(session, plugin_data["id"])
            if not existing:
                manifest = PluginManifest(**plugin_data)
                session.add(manifest)
                logger.info(f"Seeded official plugin: {plugin_data['id']}")
            else:
                # Update existing
                for key, value in plugin_data.items():
                    setattr(existing, key, value)
                logger.info(f"Updated official plugin: {plugin_data['id']}")

        await session.commit()
