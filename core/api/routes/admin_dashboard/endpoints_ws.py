"""Admin dashboard live WebSocket (WS /admin-api/ws) — streams metrics, provider status and health map."""

import asyncio

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from api.routes.admin_dashboard import router
from api.routes.admin_dashboard.endpoints_health import get_health_map
from api.routes.admin_dashboard.endpoints_metrics import get_metrics, get_providers
from core.logging_config import logger
from core.utils.time_utils import utc_now


@router.websocket("/ws")
async def admin_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try:
                metrics = get_metrics()
                providers_status = {p["id"]: p["status"] for p in get_providers()}
                health = get_health_map()
                await websocket.send_json(
                    {
                        "type": "dashboard_update",
                        "data": {
                            "metrics": metrics,
                            "providers": providers_status,
                            "health": health,
                            "timestamp": utc_now().isoformat(),
                        },
                    }
                )
            except Exception as exc:
                logger.debug(f"WS send error: {exc}")
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        logger.info("Admin WebSocket client disconnected")
    except Exception as exc:
        logger.error(f"Admin WebSocket error: {exc}")
