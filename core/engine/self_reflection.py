# SupremeAI 2.0 - Self-Reflection Loop Engine
# বাংলা মন্তব্য: এটি প্রতিটি কাজের পর ৩টি আত্ম-পর্যালোচনামূলক প্রশ্ন বিশ্লেষণ করে জ্ঞান উন্নত করে।

from __future__ import annotations

import os
from typing import Any

import httpx

from core.logging_config import logger
from memory.episodic_memory import EpisodicMemory


class SelfReflectionLoop:
    """
    Self-Reflection Loop Engine.
    Evaluates completed tasks across 3 key canonical questions:
    1. Was the task executed with precision and evidence?
    2. Where did the bottleneck or failure occur and why?
    3. What should change in the next attempt at this task type?
    """

    def __init__(self, memory: EpisodicMemory | None = None) -> None:
        self.memory = memory or EpisodicMemory()

    async def reflect(
        self,
        task_prompt: str,
        execution_output: str,
        is_success: bool = True,
        error_details: str = "",
    ) -> dict[str, Any]:
        """
        Perform genuine LLM-driven cognitive reflection on execution results.
        """
        reflection: dict[str, Any] = {
            "is_correct": is_success,
            "success_factor": "Validated execution."
            if is_success
            else "Execution error encountered.",
            "bottleneck_analysis": "None" if is_success else str(error_details),
            "future_prevention_strategy": "Maintain optimal pattern."
            if is_success
            else "Add safeguards.",
        }

        # Query LLM for deep reflection if API keys are available
        gem_keys = [
            k.strip()
            for k in os.getenv("GEMINI_API_KEY", "").split(",")
            if k.strip().startswith("AIza")
        ]
        groq_key = os.getenv("GROQ_API_KEY", "").strip()

        reflection_prompt = (
            f"Task: {task_prompt}\n"
            f"Output: {execution_output[:1000]}\n"
            f"Success: {is_success}\n"
            f"Error Details: {error_details}\n\n"
            "Analyze this execution concisely across 3 canonical questions:\n"
            "1. What worked in this execution?\n"
            "2. Where did the bottleneck or failure occur and why?\n"
            "3. What should change in the next attempt at this task type?"
        )

        try:
            if gem_keys:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gem_keys[0]}"
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        url,
                        json={"contents": [{"parts": [{"text": reflection_prompt}]}]},
                    )
                    if resp.status_code == 200:
                        analysis = (
                            resp.json()
                            .get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                        )
                        reflection["deep_analysis"] = analysis
            elif groq_key:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {groq_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "qwen/qwen3.6-27b",
                            "messages": [{"role": "user", "content": reflection_prompt}],
                            "max_tokens": 300,
                        },
                    )
                    if resp.status_code == 200:
                        analysis = (
                            resp.json()
                            .get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )
                        reflection["deep_analysis"] = analysis
        except Exception as exc:
            logger.debug(f"LLM reflection call skipped: {exc}")

        # Store episode into long-term continuous learning matrix
        try:
            self.memory.store_episode(
                event_type="self_reflection",
                task_type="reflection",
                input_data=task_prompt,
                output_data=reflection,
                success=is_success,
            )
        except Exception as mem_err:
            logger.debug(f"Episodic memory store bypassed: {mem_err}")

        logger.info(f"Self-Reflection complete: Success={is_success}")
        return reflection
