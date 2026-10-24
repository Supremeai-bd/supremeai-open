import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from brain.model_router import ModelRouter
from core.llm.llm_gateway.errors import GatewayError

router = APIRouter(prefix="/api/stream", tags=["stream"])
model_router = ModelRouter()


class StreamRequest(BaseModel):
    prompt: str
    task_type: str = "general"
    max_cost: float = 0.01


@router.post("/chat")
def stream_chat(req: StreamRequest):
    def event_generator():
        try:
            for chunk in model_router.route_and_stream(
                prompt=req.prompt,
                task_type=req.task_type,
                max_cost=req.max_cost,
            ):
                token = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                yield f"data: {json.dumps({'token': token})}\n\n"
        except GatewayError as exc:
            # বাংলা (M03 P1): বানানো "Hello World" ফলব্যাক অবসান — ব্যর্থতা এখন
            # স্ট্রাকচার্ড ও সৎ; ব্যবহারকারী স্পষ্ট error-event দেখেন, ভুয়া টোকেন নয়।
            retry_after = getattr(exc, "retry_after_seconds", None)
            payload: dict[str, Any] = {
                "error": "llm_unavailable",
                "message": str(exc),
            }
            if retry_after:
                payload["retry_after_seconds"] = retry_after
            yield f"data: {json.dumps(payload)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
