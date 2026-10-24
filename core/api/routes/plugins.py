from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

# FIX (AUDIT-WIRE-2, blocker): `api.dependencies` একটি মডিউল, প্যাকেজ নয় —
# `api.dependencies.auth` কখনোই resolve হত না (ModuleNotFoundError), তাই এই
# রাউটারটি মাউন্ট করা অসম্ভব ছিল। ক্যানোনিকাল auth dependency ব্যবহার করা হলো
# এবং user identity JWT payload ('sub') থেকে নেওয়া হয়।
from api.dependencies import get_current_user_token
from core.plugins.lifecycle_manager import PluginLifecycleManager
from core.plugins.manifest_registry import PluginManifestRegistry
from database.session import get_db_session

router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])


def _current_user_id(payload: dict = Depends(get_current_user_token)) -> str:
    """JWT payload থেকে user id ('sub') — আগের অসম্ভর get_current_user.uid-এর বিকল্প।"""
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token structure")
    return str(sub)


class InstallRequest(BaseModel):
    plugin_id: str
    granted_capabilities: list[str]


@router.get("/marketplace")
async def list_marketplace_plugins(db: AsyncSession = Depends(get_db_session)):
    """Returns all available plugins in the marketplace."""
    manifests = await PluginManifestRegistry.get_all_manifests(db, active_only=True)
    return {"plugins": manifests}


@router.get("/installed")
async def list_installed_plugins(
    db: AsyncSession = Depends(get_db_session), user_id=Depends(_current_user_id)
):
    """Returns plugins installed by the current user."""
    installations = await PluginLifecycleManager.get_user_installations(db, user_id)
    return {"installations": installations}


@router.post("/install")
async def install_plugin(
    req: InstallRequest,
    db: AsyncSession = Depends(get_db_session),
    user_id=Depends(_current_user_id),
):
    """Installs a plugin for the user."""
    manifest = await PluginManifestRegistry.get_manifest_by_id(db, req.plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Plugin not found")

    installation = await PluginLifecycleManager.install_plugin(
        session=db,
        user_id=user_id,
        plugin_id=req.plugin_id,
        granted_capabilities=req.granted_capabilities,
    )
    return {"message": "Plugin installed successfully", "installation_id": str(installation.id)}


@router.delete("/uninstall/{plugin_id}")
async def uninstall_plugin(
    plugin_id: str, db: AsyncSession = Depends(get_db_session), user_id=Depends(_current_user_id)
):
    """Uninstalls a plugin for the user."""
    success = await PluginLifecycleManager.uninstall_plugin(db, user_id, plugin_id)
    if not success:
        raise HTTPException(status_code=404, detail="Installation not found")
    return {"message": "Plugin uninstalled successfully"}
