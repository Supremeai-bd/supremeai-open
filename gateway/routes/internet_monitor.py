"""
Internet Monitor API Routes
===========================
API endpoints for the Internet Monitor Agent that tracks updates and system capabilities.
"""

from fastapi import APIRouter, Depends, HTTPException

from agents.internet_monitor_agent import (
    get_internet_updates,
    get_update_history,
    get_update_summary,
    initialize_internet_monitor,
    internet_monitor_agent,
)
from api.dependencies import get_current_admin
from core.logging_config import logger

router = APIRouter(prefix="/internet-monitor", tags=["Internet Monitor"])


# Bangla comment: APIRouter-এ @router.on_event অবচিত (deprecated)। সরাসরি অন-ডিমান্ড বা Lifespan মাধ্যমে লোড করার জন্য ইনিশিয়ালাইজেশন মেথড দেওয়া হলো।
async def ensure_internet_monitor_initialized() -> None:
    """Initialize the internet monitor agent safely on demand or startup."""
    try:
        await initialize_internet_monitor()
    except Exception as exc:
        logger.error(f"Failed to initialize internet monitor agent: {exc}")


@router.get("/updates", summary="Get Latest Internet Updates")
async def get_latest_updates(current_user=Depends(get_current_admin)):
    """
    Retrieve the latest updates from internet monitoring sources.

    Returns updates from:
    - GitHub trending repositories
    - AI world updates
    - System capability comparisons
    - Security alerts
    """
    try:
        updates = await get_internet_updates()
        return {
            "success": True,
            "data": [
                {
                    "source": u.source,
                    "title": u.title,
                    "description": u.description,
                    "url": u.url,
                    "timestamp": u.timestamp.isoformat(),
                    "category": u.category,
                }
                for u in updates
            ],
            "count": len(updates),
        }
    except Exception as e:
        logger.error(f"Error fetching internet updates: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch internet updates") from e


@router.get("/summary", summary="Get Update Summary")
async def get_updates_summary(current_user=Depends(get_current_admin)):
    """
    Get a categorized summary of internet updates.

    Provides a breakdown of updates by category with top items.
    """
    try:
        summary = await get_update_summary()
        return {"success": True, "data": summary}
    except Exception as e:
        logger.error(f"Error fetching update summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch update summary") from e


@router.get("/history", summary="Get Update History")
async def get_updates_history(current_user=Depends(get_current_admin)):
    """
    Get historical updates from the monitoring system.

    Returns previously collected updates from internet sources.
    """
    try:
        history = await get_update_history()
        return {"success": True, "data": history, "count": len(history)}
    except Exception as e:
        logger.error(f"Error fetching update history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch update history") from e


@router.post("/start-monitoring", summary="Start Monitoring Process")
async def start_monitoring_process(current_user=Depends(get_current_admin)):
    """
    Start the continuous internet monitoring process.

    Initiates the background task that continuously monitors internet sources.
    """
    try:
        # Start monitoring in background
        import asyncio

        task = asyncio.create_task(internet_monitor_agent.start_monitoring_loop())

        return {
            "success": True,
            "message": "Internet monitoring started successfully",
            "task_id": id(task),  # This is just an identifier, not a real task ID
        }
    except Exception as e:
        logger.error(f"Error starting monitoring process: {e}")
        raise HTTPException(status_code=500, detail="Failed to start monitoring process") from e


@router.get("/capabilities", summary="Get System Capabilities")
async def get_system_capabilities(current_user=Depends(get_current_admin)):
    """
    Get current system capabilities and feature inventory.

    Shows what features and tools are currently available in the system.
    """
    try:
        caps = await internet_monitor_agent.get_system_capabilities()
        return {"success": True, "data": caps}
    except Exception as e:
        logger.error(f"Error fetching system capabilities: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch system capabilities") from e


@router.get("/status", summary="Get Monitor Status")
async def get_monitor_status(current_user=Depends(get_current_admin)):
    """
    Get the current status of the internet monitoring system.

    Shows whether the monitoring system is active and collecting updates.
    """
    try:
        # Check if the agent is initialized
        is_initialized = internet_monitor_agent.session is not None

        return {
            "success": True,
            "data": {
                "initialized": is_initialized,
                "name": internet_monitor_agent.name,
                "check_interval": internet_monitor_agent.check_interval,
                "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"Error fetching monitor status: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch monitor status") from e
