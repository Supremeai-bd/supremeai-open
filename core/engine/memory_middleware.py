"""engine/memory_middleware.py — RAG memory injection middleware.

বাংলা মন্তব্য: এই middleware task prompt-কে historical context দিয়ে augment করে।
আর paid OpenAI embedding call করে না — raw text সরাসরি vector_db adapter-এ পাঠায়,
যেটা নিজেই free sentence-transformers দিয়ে embed করে।
"""

from core.logging_config import logger
from engine.vector_db import vector_db


class MemoryMiddleware:
    """
    Injects Neural Memory (RAG) into Swarm Tasks by retrieving past experiences.
    Allows agents to learn from historical data — zero paid API calls.
    """

    def __init__(self):
        self.vector_db = vector_db

    async def augment_task(self, task_prompt: str) -> str:
        try:
            logger.info("🧠 MemoryMiddleware: Fetching relevant past experiences...")

            # বাংলা মন্তব্য: raw text সরাসরি পাঠানো হচ্ছে — embedding vector_db adapter
            # নিজেই free sentence-transformers দিয়ে তৈরি করবে। আর paid OpenAI দরকার নেই।
            experiences = await self.vector_db.find_similar_experiences(task_prompt, top_k=2)

            # বাংলা মন্তব্য: degraded state চেক করা হচ্ছে — এটা "কোনো past experience নেই"
            # এর মতো না। memory backend নিজেই down/absent হলে agent ভুলে "clean slate"
            # ভাবতে পারে। তাই ERROR level-এ স্পষ্টভাবে জানানো হচ্ছে।
            if getattr(self.vector_db, "degraded", False):
                logger.error(
                    "🧠 MemoryMiddleware: vector memory backend is DEGRADED — "
                    "proceeding WITHOUT historical context."
                )
                return task_prompt

            if not experiences:
                logger.info("🧠 MemoryMiddleware: No relevant past experiences found.")
                return task_prompt

            # 3. Add context to prompt
            logger.info(
                f"🧠 MemoryMiddleware: Found {len(experiences)} relevant memory chunks. Augmenting prompt."
            )
            memory_context = "\n".join(
                [
                    f"- Past insight: {exp.get('metadata', {}).get('solution', exp.get('solution', 'Unknown'))}"
                    for exp in experiences
                ]
            )
            return f"{task_prompt}\n\n--- RELEVANT PAST EXPERIENCE ---\n{memory_context}\n--------------------------------"

        except Exception as e:
            # বাংলা মন্তব্য: silent failure নিষিদ্ধ — ERROR level-এ log করা হচ্ছে
            # যাতে health monitoring এই failure ধরতে পারে।
            logger.error(
                f"❌ MemoryMiddleware.augment_task() FAILED "
                f"(proceeding WITHOUT historical context): {e!r}"
            )
            return task_prompt  # Fallback to original prompt — never crash the agent

    async def intercept_result(
        self, task_prompt: str, intent_domain: str, execution_result: dict, success: bool = True
    ) -> None:
        """
        Intercepts execution results and stores them with intent tags to enable the self-healing feedback loop.
        """
        try:
            import json

            from services.memory_service import memory_service

            summary = f"Task: {task_prompt} | Result: {'Success' if success else 'Failed'}"

            memory_service.store_memory(
                file_path=f"intercept_{hash(task_prompt)}",
                content=json.dumps(execution_result),
                summary=summary,
                structure="execution_result",
                session_id="memory_middleware",
                agent_type="system",
                task_type=intent_domain,
                metadata={"success": success, "intent": intent_domain, "result": execution_result},
            )
            logger.info(
                f"🧠 MemoryMiddleware: Intercepted and stored memory with intent tag '{intent_domain}'"
            )
        except Exception as e:
            logger.error(f"❌ MemoryMiddleware.intercept_result() FAILED: {e!r}")


memory_mw = MemoryMiddleware()
