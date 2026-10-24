import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.plugin_manifest import PluginManifest
from models.user_plugin_installation import UserPluginInstallation

logger = logging.getLogger(__name__)


class PluginLifecycleManager:
    """
    Manages the lifecycle of user plugin installations:
    install, configure, enable, disable, uninstall.
    """

    @staticmethod
    async def get_user_installations(
        session: AsyncSession, user_id: str
    ) -> list[UserPluginInstallation]:
        query = select(UserPluginInstallation).where(UserPluginInstallation.user_id == user_id)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def install_plugin(
        session: AsyncSession, user_id: str, plugin_id: str, granted_capabilities: list[str]
    ) -> UserPluginInstallation:
        # Check if already installed
        query = select(UserPluginInstallation).where(
            UserPluginInstallation.user_id == user_id, UserPluginInstallation.plugin_id == plugin_id
        )
        existing = (await session.execute(query)).scalars().first()
        if existing:
            return existing

        installation = UserPluginInstallation(
            user_id=user_id, plugin_id=plugin_id, granted_capabilities=granted_capabilities
        )
        session.add(installation)
        await session.commit()
        logger.info(f"User {user_id} installed plugin {plugin_id}")
        return installation

    @staticmethod
    async def uninstall_plugin(session: AsyncSession, user_id: str, plugin_id: str) -> bool:
        query = select(UserPluginInstallation).where(
            UserPluginInstallation.user_id == user_id, UserPluginInstallation.plugin_id == plugin_id
        )
        installation = (await session.execute(query)).scalars().first()
        if installation:
            session.delete(installation)
            await session.commit()
            logger.info(f"User {user_id} uninstalled plugin {plugin_id}")
            return True
        return False
