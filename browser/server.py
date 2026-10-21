"""SupremeAI Browser - lightweight Gemini cookie relay (no browser, ~30MB RAM).

Uses stored Google session cookies to call Gemini web endpoint over HTTP.
Suitable for Render Free Tier. Falls back gracefully (502) so the gateway
can fail over to API-key providers.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("supremeai-browser-relay")

app = FastAPI(title="SupremeAI Browser Relay (cookie)")

GEMINI_URL = "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "gemini"
    messages: list[ChatMessage]
    stream: bool = False


def _cookies() -> dict[str, str]:
    c: dict[str, str] = {}
    for key in ("SUPREMEAI_GEMINI_1PSID", "SUPREMEAI_GEMINI_3PSID"):
        val = os.environ.get(key, "")
        if val:
            name = (
                key.replace("SUPREMEAI_GEMINI_", "")
                .replace("1PSID", "__Secure-1PSID")
                .replace("3PSID", "__Secure-3PSID")
            )
            c[name] = val
    return c


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "cookies_loaded": bool(_cookies())}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest) -> JSONResponse:
    cookies = _cookies()
    if not cookies:
        raise HTTPException(status_code=503, detail="no gemini cookies configured")

    prompt = "\n".join(m.content for m in req.messages if m.role == "user")
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="missing user message")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Origin": "https://gemini.google.com",
        "Referer": "https://gemini.google.com/",
    }
    try:
        async with httpx.AsyncClient(
            cookies=cookies, timeout=60.0, follow_redirects=True
        ) as client:
            resp = await client.post(
                GEMINI_URL,
                headers=headers,
                data={"f.req": json.dumps([None, [[[prompt]]]])},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502, detail=f"gemini returned {resp.status_code}"
        )

    text = resp.text
    if not text or "accounts.google.com" in text:
        raise HTTPException(status_code=502, detail="session expired or login required")

    return JSONResponse(
        {
            "id": "chatcmpl-relay",
            "object": "chat.completion",
            "created": 0,
            "model": "gemini-web-relay",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text[:2000]},
                    "finish_reason": "stop",
                }
            ],
        }
    )
