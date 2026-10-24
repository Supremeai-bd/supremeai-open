"""Reasoning stream — visible intelligence on the session SSE channel.

বাংলা: MASTER_PLAN Phase 1 — "backend emits reasoning steps on the session SSE
channel; ReasoningLog.tsx finally shows the thought process। Visible intelligence
is perceived intelligence।"

আগে session SSE-তে (api/routes/session_stream.py) শুধু logs/state/filetree
channel ছিল; এজেন্টের চিন্তা-প্রক্রিয়া frontend-এ কখনোই পৌঁছাত না —
ReasoningLog.tsx চিরকাল "Waiting for agent thought process..." দেখাত।

⚠️ ডিজাইন নোট: LogBatcherService.emit() ব্যবহার করলে reasoning entry DB-র
execution_logs টেবিলে insert হওয়ার চেষ্টা হতো (schema mismatch → poison
re-queue)। তাই এখানে batcher.publish() (SSE-only fanout, DB write ছাড়া)
ব্যবহার করা হয়েছে — reasoning চিন্তা transient স্ট্রিম, durable অডিট নয়।

যেকোনো agent/pipeline এই helper দিয়ে চিন্তা স্টেপ emit করতে পারে:

    from core.observability.reasoning_stream import emit_reasoning_step
    emit_reasoning_step(session_id, step=1, content="Refining research query")
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.logging_config import logger

_REASONING_LOG_TYPE = "reasoning_step"


def emit_reasoning_step(
    session_id: str,
    step: int,
    content: str,
    token: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Publishes one reasoning step to all live SSE subscribers of a session.

    Returns True when at least one subscriber received the step (best-effort;
    reasoning is a transient stream — কেউ শোনে না হলেও এটি failure নয়)।
    """
    if not session_id or not content:
        return False
    try:
        from core.observability.log_batcher import batcher

        payload = {
            "log_type": _REASONING_LOG_TYPE,
            "session_id": str(session_id),
            "step": int(step),
            "content": str(content)[:4000],
            "token": (token or str(content))[:4000],
            "ts": datetime.now(UTC).isoformat(),
            **({"metadata": metadata} if metadata else {}),
        }
        batcher.publish(str(session_id), payload)
        return True
    except Exception as exc:  # pragma: no cover - defensive: reasoning never crashes agents
        logger.debug("reasoning_step publish skipped for %s: %s", session_id, exc)
        return False


__all__ = ["emit_reasoning_step"]
