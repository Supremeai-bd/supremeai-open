"""AI response engine for :class:`TelegramBotHandler`
(verbatim split artifact of the former single-module telegram_bot.py).

Vendor-agnostic chain (Issue #466): Central ModelRouter -> SupremeOrchestrator
-> graceful zero-key response. No direct vendor API calls are made here.
"""

from __future__ import annotations

import asyncio

from core.logging_config import logger


class AIEngineMixin:
    """AI-response mixin for :class:`TelegramBotHandler`."""

    async def _ai_response(self, text: str, user_id: str) -> str:
        """Route user query through SupremeAI dynamic reasoning engine ($0..N vendor-agnostic)."""
        system_instruction = (
            "You are SupremeAI 2.0, a living self-evolving autonomous intelligence. "
            "Respond helpfully, clearly, and concisely in Bengali or English according to the user's language."
        )

        # 1. Primary: Central ModelRouter & LLMGateway (Dynamic pool: OpenAI, Gemini, OpenRouter, Mistral, Groq, etc.)
        try:
            from brain.model_router import ModelRouter

            router = ModelRouter()
            full_prompt = f"{system_instruction}\n\nUser Message: {text}"
            task_type = (
                "coding"
                if any(
                    k in text.lower()
                    for k in ["code", "function", "script", "fix", "bug", "python", "javascript"]
                )
                else "general"
            )
            res = await router.async_route_and_generate(full_prompt, task_type=task_type)
            if res and res.get("success") and res.get("text"):
                return res["text"].strip()
        except Exception as router_exc:
            logger.debug(f"[TelegramBot] ModelRouter attempt notice: {router_exc}")

        # 2. Fallback: Orchestrator Processor
        if getattr(self, "processor", None):
            try:
                task_type = (
                    "coding"
                    if any(k in text.lower() for k in ["code", "function", "script", "fix", "bug"])
                    else "general"
                )
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, lambda: self.processor.execute_task(text, task_type)
                )
                if isinstance(result, dict) and result.get("result"):
                    return str(result["result"])
            except Exception as exc:
                logger.error(f"[TelegramBot] Orchestrator fallback error: {exc}")

        # 3. N = 0 Graceful Response (No keys configured)
        return "🤖 SupremeAI 2.0: আপনার বার্তাটি গ্রহণ করা হয়েছে। সিস্টেমটি সম্পূর্ণ কার্যকর রয়েছে এবং এআই প্রোভাইডার কী কনফিগারেশনের অপেক্ষায় রয়েছে।"
