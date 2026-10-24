import asyncio
import json
import os

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from core.config import settings
from core.logging_config import logger
from core.messaging.event_bus import ErrorEvent, error_event_bus
from core.security import ALGORITHM

router = APIRouter(prefix="/ws/hitl", tags=["hitl"])


class HITLConnectionManager:
    # FIX (DoS): connection cap — previously unbounded set (512MB free-tier survival).
    MAX_CONNECTIONS = int(os.getenv("WS_MAX_CONNECTIONS", "50"))

    def __init__(self):
        # Set ব্যবহার করা হয়েছে যাতে O(1) কমপ্লেক্সিটিতে কানেকশন রিমুভ করা যায় এবং ডুপ্লিকেট এড়ানো যায়।
        self.active_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()  # রেস কন্ডিশন এড়ানোর জন্য অ্যাসিনক্রোনাস লক

    async def connect(self, websocket: WebSocket) -> bool:
        async with self._lock:
            if len(self.active_connections) >= self.MAX_CONNECTIONS:
                await websocket.close(code=1013, reason="Too many connections")
                logger.warning(
                    f"🛡️ [WS] HITL connection rejected: cap {self.MAX_CONNECTIONS} reached"
                )
                return False
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(
            f"New HITL WebSocket connection. Total connections: {len(self.active_connections)}"
        )
        return True

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(
            f"HITL WebSocket disconnected. Total connections: {len(self.active_connections)}"
        )

    async def broadcast(self, message: str):
        # কানেকশন ড্রপ বা এরর হ্যান্ডল করার জন্য ব্রডকাস্ট লজিক ইমপ্রুভ করা হয়েছে।
        disconnected = set()
        async with self._lock:
            # Iterating over a copy to safely remove items if necessary
            connections = list(self.active_connections)

        for connection in connections:
            try:
                await connection.send_text(message)
            except WebSocketDisconnect:
                disconnected.add(connection)
            except Exception as e:
                logger.error(f"Error sending message to HITL WebSocket: {e}")
                disconnected.add(connection)

        # ফেইলড কানেকশনগুলো পরিষ্কার করা হচ্ছে
        for conn in disconnected:
            await self.disconnect(conn)


manager = HITLConnectionManager()


async def hitl_event_listener(event: ErrorEvent):
    """Listens to the event bus and broadcasts HITL review requests to active WebSockets."""
    if event.error_type == "HITL_REVIEW_REQUIRED":
        try:
            payload = {
                "type": "HITL_REVIEW_REQUIRED",
                "message": event.message,
                "context": event.context,
                "severity": event.severity,
                "module": event.module,
            }
            # json.dumps এরর হ্যান্ডলিং যোগ করা হয়েছে, যদি non-serializable object থাকে
            message = json.dumps(payload)
            await manager.broadcast(message)
        except TypeError as e:
            logger.error(f"Failed to serialize HITL event payload: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in HITL event listener: {e}")


# Register listener so we can push fixes to UI in real-time
error_event_bus.register_listener("*", hitl_event_listener)


async def verify_hitl_token(websocket: WebSocket) -> bool:
    """
    Verify the JWT token scopes to ensure only ADMIN or SUPERVISOR can access HITL WS.
    Extracts token from Authorization header, query param 'token', or Sec-WebSocket-Protocol.
    """
    token = websocket.headers.get("Authorization") or websocket.headers.get("X-API-KEY")

    # Fallback to query parameters (common for browsers)
    if not token:
        token = websocket.query_params.get("token")

    # Fallback to Sec-WebSocket-Protocol (often used to pass tokens in JS WebSockets)
    if not token:
        protocols = websocket.headers.get("sec-websocket-protocol", "").split(",")
        for p in protocols:
            p = p.strip()
            if p and p != "hitl":
                token = p
                break

    if not token:
        logger.warning("HITL WebSocket connection rejected: Missing token")
        return False

    if token.startswith("Bearer "):
        token = token[7:]

    try:
        # FIX (latent-crash): this decode previously passed `settings.jwt_algorithm`,
        # but the Settings object has NO such field — every call raised
        # AttributeError, which the broad handler below swallowed, so the HITL
        # WebSocket could NEVER authenticate anyone (every admin/supervisor got
        # a 1008 policy-violation close). Wire the canonical core.security
        # ALGORITHM constant ("HS256") instead — the same constant the auth
        # middleware and token issuer use.
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        role = payload.get("role", "").lower()

        # হার্ডকোডেড রোলের বদলে কনফিগারেশন থেকে রোল নেয়া যেতে পারে (আপাতত settings.allowed_hitl_roles ব্যবহার করা হচ্ছে, না থাকলে ডিফল্ট)
        allowed_roles = getattr(settings, "allowed_hitl_roles", ["admin", "supervisor"])
        if role not in allowed_roles:
            logger.warning(f"HITL WebSocket connection rejected: Insufficient role '{role}'")
            return False
        return True
    except jwt.ExpiredSignatureError:
        logger.warning("HITL WebSocket connection rejected: Token expired")
        return False
    except jwt.PyJWTError as e:
        logger.warning(f"HITL WebSocket connection rejected: Invalid token - {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {e}")
        return False


@router.websocket("/")
async def websocket_hitl_endpoint(websocket: WebSocket):
    # Enforce Auth
    is_authorized = await verify_hitl_token(websocket)
    if not is_authorized:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    connected = await manager.connect(websocket)
    if not connected:
        return
    try:
        while True:
            # Ping/Pong Heartbeat to keep connection alive and detect drops
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info("HITL WebSocket client gracefully disconnected.")
    except Exception as e:
        logger.error(f"HITL WebSocket error: {e}")
    finally:
        # finally block নিশ্চিত করে যে যেকোনো এরর বা ডিসকানেক্টে কানেকশন রিমুভ হবে
        await manager.disconnect(websocket)
