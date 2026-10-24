import asyncio
import json
import os
import time

import httpx
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from core.config import settings
from core.logging_config import logger
from core.security import verify_token_async
from database.supabase_client import db
from models.voice_interaction import VoiceInteractionLog

router = APIRouter(prefix="/ws", tags=["Voice Engine Stream"])


class VoiceConnectionManager:
    # FIX (DoS): connection cap — unbounded list previously let memory grow
    # without limit (Render free tier has 512MB). Matches websocket_agent.py policy.
    MAX_CONNECTIONS = int(os.getenv("WS_MAX_CONNECTIONS", "50"))

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> bool:
        if len(self.active_connections) >= self.MAX_CONNECTIONS:
            await websocket.close(code=1013, reason="Too many connections")
            logger.warning(f"🛡️ [WS] Voice connection rejected: cap {self.MAX_CONNECTIONS} reached")
            return False
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("🟢 [WS] Voice Client Connected to SupremeAI Nexus.")
        return True

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("🔴 [WS] Voice Client Disconnected.")

    async def _authenticate(self, websocket: WebSocket) -> dict | None:
        try:
            auth_msg = await websocket.receive_json()
            token = auth_msg.get("token")
            if auth_msg.get("type") != "auth" or not token:
                return None
            return await verify_token_async(token)
        except Exception as e:
            import jwt

            if isinstance(e, jwt.ExpiredSignatureError):
                client_host = websocket.client.host if websocket.client else "unknown"
                logger.info(f"⚠️ [WS Auth] Expired token attempt from {client_host}")
            return None


manager = VoiceConnectionManager()


async def process_audio_dynamically(audio_bytes: bytes) -> str:
    """
    Sends audio buffer to dynamic VoiceService cascade (Groq -> OpenAI -> HF -> Graceful degradation).
    Vendor-agnostic STT (Issue #466).
    """
    try:
        from services.voice_service import get_voice_service

        voice = get_voice_service()
        res = await voice.speech_to_text(audio_bytes, filename="audio.webm")
        if res.get("status") == "success":
            return res.get("transcript", "")
        if res.get("status") == "unavailable":
            return res.get("message", "Speech-to-text is awaiting AI provider key configuration.")
        return res.get("message", "Unable to process audio.")
    except Exception as e:
        logger.error(f"❌ [Dynamic STT Error]: {e}")
        return f"Error processing audio: {e!s}"


# Backward-compatibility alias
process_audio_with_groq = process_audio_dynamically


async def handle_intent(transcript: str, websocket: WebSocket, start_time: float, user_id: str):
    # Intent Router
    transcript_clean = transcript.strip()

    # Check if it's a command
    if transcript_clean.startswith("/"):
        supremeai_response = (
            f"Executing system command: {transcript_clean}... Authorization confirmed."
        )
    else:
        # Natural Language Processing (Simulating conversational Groq/LLM)
        supremeai_response = f"Hello! You said: '{transcript_clean}'. I am Aethel, your SupremeAI orchestrator. How can I assist you with the cluster today?"

    # Log to database
    if db.client:
        latency_ms = int((time.time() - start_time) * 1000)
        log_entry = VoiceInteractionLog(
            user_id=user_id,
            transcript=transcript_clean,
            supremeai_response=supremeai_response,
            latency_ms=latency_ms,
        )
        try:
            await (
                db.client.table("voice_interactions")
                .insert(log_entry.dict(exclude_none=True))
                .execute()
            )
        except Exception as db_err:
            logger.info(f"⚠️ [DB Logging Error]: {db_err}")

    # Stream text response back for Web Speech API TTS
    words = supremeai_response.split(" ")
    for word in words:
        await websocket.send_json({"type": "response_chunk", "text": word + " "})
        await asyncio.sleep(0.05)

    await websocket.send_json({"type": "response_complete"})


@router.websocket("/voice")
async def websocket_voice_endpoint(
    websocket: WebSocket,
):
    """
    Real-time WebSocket for Voice-to-Voice Streaming.
    Receives binary audio chunks, uses Groq Whisper for STT, and returns the response.
    """
    auth_payload = await manager._authenticate(websocket)
    if not auth_payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    connected = await manager.connect(websocket)
    if not connected:
        return

    # Store audio chunks in memory
    audio_buffer = bytearray()
    start_time = time.time()

    try:
        while True:
            # We accept both text (commands like {"action": "process"}) and binary (audio chunks)
            message = await websocket.receive()

            if "bytes" in message:
                # Append binary chunk to buffer
                audio_buffer.extend(message["bytes"])
            elif "text" in message:
                try:
                    payload = json.loads(message["text"])
                    action = payload.get("action")

                    if action == "process":
                        if len(audio_buffer) == 0:
                            await websocket.send_json({"error": "Empty audio buffer"})
                            continue

                        # 1. Process STT using Dynamic VoiceService
                        logger.info(
                            f"🎙️ [WS] Processing audio buffer ({len(audio_buffer)} bytes)..."
                        )
                        transcript = await process_audio_dynamically(bytes(audio_buffer))
                        logger.info(f"🗣️ [User Voice]: {transcript}")

                        # Clear buffer for next recording
                        audio_buffer.clear()

                        # Send transcript to UI
                        await websocket.send_json({"type": "transcript", "text": transcript})

                        # 2. Intent Router
                        await handle_intent(
                            transcript,
                            websocket,
                            start_time,
                            auth_payload.get("sub", "anonymous"),
                        )
                        start_time = time.time()  # Reset timer

                    elif action == "text_chat":
                        transcript = payload.get("text", "")
                        logger.info(f"💬 [User Text]: {transcript}")

                        # Process text intent directly
                        await handle_intent(
                            transcript,
                            websocket,
                            start_time,
                            auth_payload.get("sub", "anonymous"),
                        )
                        start_time = time.time()  # Reset timer

                except json.JSONDecodeError:
                    logger.info("⚠️ [WS] Received invalid text message.")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.info(f"❌ [WS Voice Engine Error]: {e}")
        manager.disconnect(websocket)
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception as exc:
            logger.exception(f"WebSocket close failed after error: {exc}")
