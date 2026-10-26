"""gateway/service/context_compiler.py - Server-side context compiler (spec Phase 1)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("supremeai.context_compiler")

CORE_SYSTEM_ANCHOR = """[CORE IDENTITY & MANDATE]
- You are SupremeAI, the autonomous multi-cloud orchestrator and principal software intelligence.
- You are NOT a generic model from Google, Meta, OpenAI, or any third party. Your core identity is SupremeAI.
- Never discuss internal model routing, API keys, webhook URLs, fallback attempts, or backend infrastructure unless explicitly requested by the admin.

[TRUTHFULNESS & ANTI-HALLUCINATION RULES]
- Absolute Honesty: If you do not possess specific information, codebase files, or verified facts about a topic, DO NOT GUESS or fabricate answers.
- Cold-Start Safety: When context is absent, politely and directly ask for the necessary code/files.
- Grounding: Base answers strictly on facts and standard engineering patterns. Avoid speculative claims.

[RESPONSE POLICY]
- Language: Speak in natural, polished Bengali by default or when addressed in Bengali. Retain technical English terms (e.g., API, Gateway, PR, Route, Cache, Middleware) naturally in English.
- Tone: Highly competent senior software architect; concise, practical, direct, and zero fluff.
- Structure: Start directly with the verdict or solution. Avoid filler greetings.
"""

PLATFORM_GROUNDING_SHEET = """[SUPREMEAI VERIFIED ECOSYSTEM KNOWLEDGE]
- Federation Architecture: Active Product Satellites + 1 Control Plane (MCP Tower).
- Active Satellites:
  * studio: Frontend web dashboard & workspace (supremeai-studio)
  * gateway/api: Unified provider gateway & auth shield (supremeai-api)
  * core: Brain, decision engine & consensus (supremeai-core)
  * vscode: Developer IDE extension (supremeai-vscode)
  * browser: Headless automation sandbox & scraper (supremeai-browser)
- Operating Doctrine: Zero-Admin (Admin work <= 0.01%), Satellite-First, Single-Domain PRs, Federation Anchor Hubs SSOT.
- Never invent repositories or services outside this official charter.
"""

_LOGIC_KEYWORDS = {
    "code", "debug", "audit", "logic", "infra", "architecture", "refactor",
    "fix", "bug", "test", "sql", "api", "route", "gateway", "config",
}


def build_system_anchor(*args, **kwargs) -> str:
    extra = kwargs.get("extra") or kwargs.get("context")
    base = CORE_SYSTEM_ANCHOR + "\n" + PLATFORM_GROUNDING_SHEET
    if extra:
        base = base + "\n" + str(extra)
    return base


def resolve_sampling_knobs(*args, **kwargs) -> Dict[str, Any]:
    is_logic = False
    mode = kwargs.get("mode") or kwargs.get("task_type") or kwargs.get("task")
    if isinstance(mode, str):
        low = mode.lower()
        if any(k in low for k in ("logic", "code", "audit", "infra", "debug", "architect")):
            is_logic = True
        if "chat" in low:
            is_logic = False

    messages = kwargs.get("messages")
    if messages is None and args:
        for a in args:
            if isinstance(a, (list, tuple)):
                messages = a
                break
            if isinstance(a, str):
                if any(k in a.lower() for k in _LOGIC_KEYWORDS):
                    is_logic = True
    if messages:
        joined = " ".join(str(m.get("content", "") if isinstance(m, dict) else m) for m in messages).lower()
        if any(k in joined for k in _LOGIC_KEYWORDS):
            is_logic = True
        if mode and isinstance(mode, str) and "chat" in mode.lower():
            is_logic = False

    if kwargs.get("is_logic") is True:
        is_logic = True
    if kwargs.get("is_logic") is False:
        is_logic = False

    temperature = 0.2 if is_logic else 0.4
    return {
        "temperature": temperature,
        "temp": temperature,
        "top_p": 0.9,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.1,
        "max_tokens": kwargs.get("max_tokens", 4096),
    }


def _extract_user_memories(user_id: Optional[str], provided: Any) -> List[Dict[str, Any]]:
    if provided is not None:
        if isinstance(provided, (list, tuple)):
            return [dict(x) if isinstance(x, dict) else {"value": str(x)} for x in provided]
        if isinstance(provided, dict):
            return [provided]
        return [{"value": str(provided)}]
    if not user_id:
        return []
    try:
        from .memory_store import get_user_durable_memories
        return get_user_durable_memories(user_id)
    except Exception:
        return []


def _extract_recent_history(conv_id: Optional[str], provided: Any, messages: List[Any]) -> List[Dict[str, Any]]:
    if provided is not None:
        if isinstance(provided, (list, tuple)):
            return [dict(x) if isinstance(x, dict) else {"role": "user", "content": str(x)} for x in provided]
        return []
    if conv_id:
        try:
            from .memory_store import get_recent_history
            return get_recent_history(conv_id, limit=10)
        except Exception:
            pass
    recent = [m for m in messages if isinstance(m, dict)]
    return recent[-10:]


def compile_chat_context(*args, **kwargs) -> List[Dict[str, Any]]:
    messages = kwargs.get("messages")
    if messages is None:
        for a in args:
            if isinstance(a, (list, tuple)):
                messages = list(a)
                break
            if isinstance(a, dict) and "messages" in a:
                messages = a["messages"]
                for k in ("conversation_id", "conv_id", "user_id", "summary"):
                    if k in a and k not in kwargs:
                        kwargs[k] = a[k]
    if messages is None:
        messages = []
    messages = [dict(m) if isinstance(m, dict) else {"role": "user", "content": str(m)} for m in messages]

    conv_id = kwargs.get("conversation_id") or kwargs.get("conv_id") or kwargs.get("conv")
    user_id = kwargs.get("user_id") or kwargs.get("userId")

    summary = kwargs.get("summary")
    if summary is None and conv_id:
        try:
            from .memory_store import _DEFAULT_STORE
            conv = _DEFAULT_STORE.get_conversation(conv_id, user_id=user_id)
            if conv:
                summary = conv.get("summary", "")
        except Exception:
            summary = ""

    user_memories = _extract_user_memories(user_id, kwargs.get("user_memories") or kwargs.get("durable_memories") or kwargs.get("user_memory"))
    recent_history = _extract_recent_history(conv_id, kwargs.get("recent_history") or kwargs.get("recent_messages") or kwargs.get("recent"), messages)

    language_pref = kwargs.get("language_pref", "bn")
    response_style = kwargs.get("response_style", "technical-architect")

    system_parts = [build_system_anchor()]
    system_parts.append(f"Language preference: {language_pref}; Response style: {response_style}.")
    if summary:
        system_parts.append("Rolling summary of prior conversation:\n" + str(summary))
    if user_memories:
        mem_lines = []
        for m in user_memories:
            if isinstance(m, dict):
                key = m.get("memory_key") or m.get("key")
                val = m.get("memory_value") or m.get("value")
                if key or val:
                    mem_lines.append(f"- {key}: {val}" if key else f"- {val}")
            else:
                mem_lines.append(f"- {m}")
        if mem_lines:
            system_parts.append("Durable user memory:\n" + "\n".join(mem_lines))
    if recent_history:
        recent_lines = []
        for m in recent_history[-10:]:
            if isinstance(m, dict):
                recent_lines.append(f"{m.get('role', 'user')}: {str(m.get('content', ''))[:500]}")
        if recent_lines:
            system_parts.append("Recent conversation (Tier A):\n" + "\n".join(recent_lines))

    system_content = "\n\n".join(system_parts)

    out = [{"role": "system", "content": system_content}]
    for m in messages:
        if not isinstance(m, dict):
            m = {"role": "user", "content": str(m)}
        if m.get("role") == "system":
            continue
        out.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    return out


compile_context = compile_chat_context
build_context = compile_chat_context

__all__ = [
    "CORE_SYSTEM_ANCHOR",
    "PLATFORM_GROUNDING_SHEET",
    "build_system_anchor",
    "resolve_sampling_knobs",
    "compile_chat_context",
    "compile_context",
    "build_context",
]
