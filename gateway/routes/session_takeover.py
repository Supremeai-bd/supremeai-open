import asyncio
import base64
import json
import os
import secrets
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)

try:
    from playwright.async_api import Page
except ImportError:
    # বাংলা মন্তব্য (DEP-AUDIT): playwright এখন optional `browser` group-এ।
    # Core image-এ না থাকলে module import ক্র্যাশ না করে Any-তে fallback হয়
    # (রানটাইমে annotation evaluation-safe, isinstance-ও ভাঙে না)।
    Page = Any  # type: ignore[assignment,misc]

try:
    from PIL import Image
except ImportError:
    Image: Any = None  # type: ignore
from pydantic import BaseModel

from core.logging_config import logger

router = APIRouter()

# Store active screencast streams
active_screencasts: dict[str, dict] = {}


class ScreencastStreamer:
    """
    ✅ REAL Screencast Streaming - Per Master Plan Pillar 6
    Captures Playwright page frames and streams via WebSocket
    """

    def __init__(self, page: Page, websocket: WebSocket):
        self.page = page
        self.websocket = websocket
        self.is_streaming = False
        self.fps = 10  # Target frames per second
        self.quality = 80  # JPEG quality (1-100)
        self.last_frame_hash = None
        self.frame_count = 0

    async def start_stream(self):
        """Start capturing and streaming frames"""
        self.is_streaming = True

        try:
            while self.is_streaming:
                frame_start = asyncio.get_event_loop().time()

                # Capture screenshot from Playwright
                screenshot_bytes = await self.page.screenshot(
                    full_page=False, type="jpeg", quality=self.quality
                )

                # ✅ Delta compression: Only send if frame changed
                frame_hash = hash(screenshot_bytes)

                if frame_hash != self.last_frame_hash:
                    # Encode to base64 for JSON transport
                    b64_frame = base64.b64encode(screenshot_bytes).decode("utf-8")

                    # Send frame via WebSocket
                    await self.websocket.send_json(
                        {
                            "channel": "screencast",
                            "type": "frame",
                            "data": b64_frame,
                            "timestamp": asyncio.get_event_loop().time(),
                            "frame_number": self.frame_count,
                            "encoding": "jpeg",
                            "fps": self.fps,
                        }
                    )

                    self.last_frame_hash = frame_hash
                    self.frame_count += 1
                else:
                    # Send keepalive for unchanged frames
                    await self.websocket.send_json(
                        {
                            "channel": "screencast",
                            "type": "keepalive",
                            "frame_number": self.frame_count,
                        }
                    )

                # Frame rate throttling
                frame_time = asyncio.get_event_loop().time() - frame_start
                target_frame_time = 1.0 / self.fps
                if frame_time < target_frame_time:
                    await asyncio.sleep(target_frame_time - frame_time)

        except WebSocketDisconnect:
            from core.logging_config import logger

            logger.info("Screencast client disconnected")
        except Exception as e:
            from core.logging_config import logger

            logger.info(f"Screencast error: {e}")
            await self.websocket.send_json(
                {
                    "channel": "screencast",
                    "type": "error",
                    "message": str(e),
                }
            )
        finally:
            self.is_streaming = False

    async def stop_stream(self):
        """Stop streaming frames"""
        self.is_streaming = False

    async def handle_input(self, action: str, data: dict):
        """
        ✅ Handle mouse/keyboard input from human operator
        Routes CDP Input.dispatch commands to Playwright
        """
        if action == "mouse.move":
            await self.page.mouse.move(data["x"], data["y"])

        elif action == "mouse.click":
            await self.page.mouse.click(data["x"], data["y"], delay=data.get("delay", 50))

        elif action == "mouse.down":
            await self.page.mouse.down(button=data.get("button", "left"))

        elif action == "mouse.up":
            await self.page.mouse.up(button=data.get("button", "left"))

        elif action == "mouse.wheel":
            await self.page.mouse.wheel(data["delta_x"], data["delta_y"])

        elif action == "keyboard.press":
            await self.page.keyboard.press(data["key"])

        elif action == "keyboard.type":
            await self.page.keyboard.type(data["text"], delay=data.get("delay", 20))

        elif action == "return_control":
            # Human done, hand back to AI
            await self.stop_stream()
            return {"status": "control_returned"}

        return {"status": "input_processed"}


# বাংলা মন্তব্য: TakeoverRequest — HTTP endpoint এর জন্য Pydantic model
class TakeoverRequest(BaseModel):
    session_id: str


def _require_admin(request: Request) -> dict:
    """Admin role enforcement — fail-closed."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for session takeover")
    return user


async def request_takeover(payload: TakeoverRequest, request: Request) -> dict:
    """HTTP endpoint: Admin requests a session takeover token.

    বাংলা মন্তব্য: টোকেন তৈরি করে Redis-এ store করা হয় যাতে verify করা সম্ভয় হয়।
    """
    # বাংলা মন্তব্য: Admin validation fail-closed
    _require_admin(request)
    token = f"tok_{secrets.token_urlsafe(32)}"

    # বাংলা মন্তব্য: টোকেন Redis-এ store করা (TTL সহ)
    try:
        client = await _redis_client()
        if client is not None:
            token_data = json.dumps(
                {
                    "session_id": payload.session_id,
                    "created_at": datetime.now(UTC).isoformat(),
                    "created_by": getattr(request.state, "user", {}).get("sub", "unknown"),
                }
            )
            await client.set(f"takeover_token:{token}", token_data, ex=300)
            logger.info(f"Takeover token created for session {payload.session_id}")
        else:
            # বাংলা মন্তব্য: Redis না থাকলে fallback - env var এ add করা
            logger.warning("Redis unavailable for takeover token storage")
            existing = os.environ.get("ALLOWED_TAKEOVER_TOKENS", "")
            if existing:
                os.environ["ALLOWED_TAKEOVER_TOKENS"] = f"{existing},{token}"
            else:
                os.environ["ALLOWED_TAKEOVER_TOKENS"] = token
    except Exception as e:
        logger.error(f"Failed to store takeover token: {e}")

    return {
        "token": token,
        "session_id": payload.session_id,
        "expires_in": 300,  # 5 মিনিট TTL
    }


async def release_takeover(session_id: str, request: Request) -> dict:
    """HTTP endpoint: Admin releases a session takeover."""
    _require_admin(request)

    # বাংলা মন্তব্য: Redis থেকে session-এর সব takeover token মুছে দাও
    try:
        client = await _redis_client()
        if client is not None:
            # বাংলা মন্তব্য: session_id দিয়ে সব token খুঁজে মুছে দাও
            # (একটি session-এর জন্য একাধিক token থাকতে পারে)
            pattern = "takeover_token:*"
            async for key in client.scan_iter(match=pattern):
                token_data = await client.get(key)
                if token_data:
                    data = json.loads(token_data)
                    if data.get("session_id") == session_id:
                        await client.delete(key)
                        logger.info(f"Deleted takeover token for session {session_id}")
    except Exception as e:
        logger.warning(f"Failed to clean up takeover tokens: {e}")

    return {"status": "released", "session_id": session_id}


def release_takeover(session_id: str, request: Request) -> dict:
    """HTTP endpoint: Admin releases a session takeover."""
    _require_admin(request)
    return {"status": "released", "session_id": session_id}


def get_takeover_status(session_id: str, request: Request) -> dict:
    """HTTP endpoint: Get current takeover status for a session."""
    _require_admin(request)
    # বাংলা মন্তব্য: Redis check synchronous wrapper — real impl async
    try:
        import asyncio as _asyncio

        loop = _asyncio.new_event_loop()
        data = loop.run_until_complete(_get_status_from_redis(session_id))
        loop.close()
    except Exception:
        data = None
    if data:
        return {"status": "active", "session_id": session_id, "data": data}
    return {"status": "inactive", "session_id": session_id}


async def _get_status_from_redis(session_id: str) -> dict | None:
    """Redis থেকে session status নিয়ে আসা।"""
    try:
        client = await _redis_client()
        if client is None:
            return None
        raw = await client.get(f"takeover_session:{session_id}")
        if raw:
            return json.loads(raw) if isinstance(raw, str | bytes) else raw
    except Exception as e:
        logger.debug(f"Redis status check failed: {e}")
    return None


# গ্যাপ ফিক্স (Security/Anti-Silent-Failure):
# ১. verify_takeover_token() আগে শুধু একটি env-var কমা-সেপারেটেড লিস্টের বিরুদ্ধে চেক করত (কোনো
#    expiry বা single-use গ্যারান্টি ছাড়াই) — এখন একটি ব্যবহৃত টোকেন Redis-এ single-use হিসেবে
#    মার্ক করা হয় (রেপ্লে-অ্যাটাক প্রতিরোধ), Redis না থাকলে গ্রেসফুলি আগের বেস চেকে ফলব্যাক করে।
# ২. mock_screencast_emitter() আগে *সব* environment-এ (production সহ) একটি স্ট্যাটিক কালো ফ্রেম
#    "লাইভ স্ট্রিম" হিসেবে পাঠাত — একজন অ্যাডমিন সন্দেহভাজন কম্প্রোমাইজড ডিভাইসে JIT session
#    takeover করার সময় ভুলভাবে ভাবতে পারতেন তিনি রিয়েল স্ক্রিন দেখছেন। এখন এটি শুধু non-production
#    এ ডেভ/স্ট্রেস-টেস্ট মোডে চলে; production-এ honest "unavailable" স্ট্যাটাস পাঠিয়ে বন্ধ হয়ে যায়,
#    আর কেন্দ্রীয় error bus-এ রিপোর্ট করে (self-healing পর্যবেক্ষণযোগ্যতার জন্য)।


async def _redis_client():
    """Best-effort shared Redis client for single-use token consumption. Returns None if unavailable."""
    try:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]

        from core.config import settings as app_settings

        redis_url = (
            getattr(app_settings, "redis_url", None)
            or os.getenv("REDIS_URL")
            or os.getenv("UPSTASH_REDIS_URL")
        )
        if not redis_url:
            return None
        return aioredis.from_url(redis_url, decode_responses=True)
    except Exception as exc:
        logger.debug(
            f"Redis unavailable for takeover-token consumption, falling back to base check only: {exc}"
        )
        return None


async def verify_takeover_token(token: str) -> bool:
    """
    Validates the takeover token, then consumes it as single-use in Redis (when available)
    to block replay of a leaked/logged token.

    বাংলা মন্তব্য: টোকেন প্রথমে Redis-এ খোঁজা হয় (request_takeover-এ store করা টোকেন),
    তারপর env var এ fallback করা হয়।
    """
    if not token or not token.startswith("tok_"):
        return False

    try:
        # বাংলা মন্তব্য: প্রথমে Redis-এ টোকেন আছে কিনা চেক করা
        client = await _redis_client()
        token_found_in_redis = False

        if client is not None:
            try:
                # বাংলা মন্তব্য: টোকেন Redis-এ আছে কিনা চেক করা
                stored_data = await client.get(f"takeover_token:{token}")
                if stored_data:
                    token_found_in_redis = True
                    # বাংলা মন্তব্য: টোকেন ব্যবহৃহীত হিসেবে mark করা (single-use)
                    await client.delete(f"takeover_token:{token}")
                    logger.info(f"Takeover token verified and consumed from Redis: {token[:10]}...")
            except Exception as exc:
                logger.warning(f"Redis token lookup failed: {exc}")

        # বাংলা মন্তব্য: Redis-এ না থাকলে env var এ fallback চেক
        if not token_found_in_redis:
            valid_tokens = os.environ.get("ALLOWED_TAKEOVER_TOKENS", "").split(",")
            if token not in valid_tokens:
                logger.warning(f"Unauthorized takeover attempt with token: {token[:10]}...")
                return False
            logger.info(f"Takeover token verified from env var: {token[:10]}...")

        # বাংলা মন্তব্য: Replay protection - Redis এ SETNX-স্টাইল single-use consumption
        # token একবার ব্যবহার হলে ৫ মিনিটের জন্য লক থাকে, দ্বিতীয়বার set ফেইল করবে
        if client is not None:
            try:
                consumed = await client.set(f"takeover_used:{token}", "1", nx=True, ex=300)
                if not consumed:
                    logger.warning(
                        f"Replay attempt detected for already-used takeover token: {token[:10]}..."
                    )
                    return False
            except Exception as exc:
                logger.warning(f"Failed to mark token as used: {exc}")

        return True
    except Exception as e:
        logger.error(f"Token verification failed: {e!s}")
        return False


def _is_production() -> bool:
    return os.environ.get("SUPREMEAI_ENV", "").lower() == "production"


@router.websocket("/ws/session/{session_id}/takeover")
async def takeover_session_websocket(websocket: WebSocket, session_id: str):
    """
    Ephemeral WebSocket gateway for Sandbox Viewport takeover.
    Validates token, streams CDP frames to client, and receives mouse/keyboard events.
    Mounts ONLY when control_mode == 'human'.
    """
    await websocket.accept()

    # First-message authentication
    try:
        auth_msg = await websocket.receive_json()
        token = auth_msg.get("token")
        if auth_msg.get("type") != "auth" or not token:
            await websocket.send_json({"error": "Authentication required as first message"})
            await websocket.close(code=1008)
            return
    except Exception:
        await websocket.close(code=1008)
        return

    if not await verify_takeover_token(token):
        await websocket.send_json({"error": "Invalid, expired, or already-used takeover token"})
        await websocket.close(code=1008)
        return

    logger.info(f"WebSocket takeover initiated for session {session_id}")

    # ✅ Resolve the Playwright page via the canonical session manager (#2253).
    # The previous code called PlaywrightBrowserAgent.get_or_create_session(),
    # a method that never existed on that class — every takeover died with an
    # unhandled AttributeError at this exact line. The canonical,
    # lifespan-owned session store is core/browser_session_manager.py; HITL
    # takeover uses the privileged admin lookup (the takeover token above has
    # already authenticated the admin, who is by definition not the session's
    # original owner).
    try:
        from core.browser_session_manager import session_manager

        session = await session_manager.get_for_admin(session_id)
    except KeyError:
        await websocket.close(code=5003, reason="Browser session not found or expired")
        return
    except Exception as e:
        logger.error(f"Takeover session resolution failed for {session_id}: {e}")
        await websocket.close(code=5003, reason="Cannot resolve browser session")
        return

    page = session.page

    if not page:
        await websocket.close(code=5003, reason="Cannot create browser session")
        return

    # ✅ REAL screencast streaming
    streamer = ScreencastStreamer(page, websocket)

    # Start streaming in background
    stream_task = asyncio.create_task(streamer.start_stream())
    active_screencasts[session_id] = {"streamer": streamer, "task": stream_task}

    start_time = time.monotonic()
    try:
        while True:
            data = await websocket.receive_json()

            action = data.get("action") or data.get("method")
            if not action:
                continue

            # Route input actions to streamer
            result = await streamer.handle_input(action, data.get("data", {}))

            if result.get("status") == "control_returned":
                logger.info(f"Session {session_id} returned control to agent.")
                break

            # Confirm input received
            await websocket.send_json(
                {
                    "channel": "input_ack",
                    "action": action,
                    "result": result,
                }
            )

    except WebSocketDisconnect:
        logger.info(f"WebSocket takeover disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket takeover error: {e}")
    finally:
        if "stream_task" in locals():
            stream_task.cancel()
            await streamer.stop_stream()

        if session_id in active_screencasts:
            del active_screencasts[session_id]

        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()
        logger.debug(f"Takeover session {session_id} lasted {time.monotonic() - start_time:.1f}s")
