import json

from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.llm_gateway import llm_gateway
from core.logging_config import logger
from models.dynamic_agent import DynamicAgent


class DynamicAgentFactory:
    """
    এজেন্ট ফ্যাক্টরি যা রিকোয়েস্ট অনুযায়ী ডাইনামিকালি কাস্টম এজেন্ট কনফিগারেশন তৈরি ও ডাটাবেজে রেজিস্ট্রি করে (অ্যাসিনক্রোনাস)।
    """

    def __init__(self, db_session: AsyncSession = None):
        self.db = db_session

    def get_registered_agent(self, agent_name: str) -> dict | None:
        from pathlib import Path

        registry_path = Path(__file__).resolve().parent / "agent_registry.json"
        if not registry_path.exists():
            return None

        try:
            with open(registry_path, encoding="utf-8") as f:
                registry = json.load(f)
                return registry.get(agent_name)
        except Exception as e:
            logger.error(f"Failed to read agent_registry.json: {e}")
            return None

    async def create_specialized_agent(self, task_description: str) -> dict:
        """
        বাংলা মন্তব্য: প্রিমিয়াম এআই ব্যবহার করে টাস্কের জন্য একটি এক্সিকিউটেবল পাইথন স্ক্রিপ্ট তৈরি করবে।
        এটি এখন আর শুধু ব্রাউজার অটোমেশন নয়, বরং যেকোনো কাজের জন্য একটি "Synthesized Skill"।
        """
        logger.info(f"Generating a new autonomous agent for task: {task_description}")

        system_prompt = (
            "You are the SupremeAI Agent Factory. Your job is to generate a Python script that can solve the given task. "
            "The script should be self-contained and executable. "
            "Return a raw JSON object containing 'agent_name', 'description', and 'script' (the Python code as a string). "
            "Do not return conversational text or markdown codeblocks."
        )

        # আগের execution_steps ভিত্তিক প্রম্পট এখন আরও জেনেরিক পাইথন স্ক্রিপ্টে পরিবর্তিত হয়েছে
        prompt = f"Create a Python script to solve this task: '{task_description}'"

        # বাংলা: আগে model_filters=["claude-3-5-sonnet"] হার্ডকোড ছিল — claude না থাকলে crash হতো।
        # এখন task_type="coding" দিয়ে llm_gateway নিজে best available model বেছে নেবে (failover সহ)।
        response = await llm_gateway.acompletion(
            prompt=prompt,
            system_prompt=system_prompt,
            task_type="coding",
        )

        try:
            agent_config = json.loads(response.get("text"))
        except Exception as e:
            logger.error(f"Failed to parse AI generated agent configuration JSON: {e}")
            import time

            agent_config = {
                "agent_name": f"AutoAgent_{int(time.time())}",
                "description": task_description,
                # বাংলা: fallback script-এ logger ব্যবহার করা যাবে না, কারণ script একটি string হিসেবে exec হবে
                "script": "print('Error: AI failed to generate a valid script.')",
            }

        # ডাটাবেজে আজীবনের জন্য সেভ করে রাখা
        # বাংলা মন্তব্য: script (str) কে JSON-compatible dict-এ মোড়ানো হচ্ছে — type mismatch fix
        script_content = agent_config.get("script", "")
        steps_data = (
            {"script": script_content} if isinstance(script_content, str) else script_content
        )
        await self._save_agent_to_registry(
            name=agent_config.get("agent_name"),
            description=agent_config.get("description", task_description),
            steps=steps_data,
        )

        return agent_config

    async def _save_agent_to_registry(self, name: str, description: str, steps: str | dict | list):
        try:
            from sqlalchemy import select

            stmt = select(DynamicAgent).where(DynamicAgent.name == name)
            result = await self.db.execute(stmt)
            existing = result.scalars().first()
            if existing:
                existing.execution_steps = steps  # আগে থেকেই মোড়ানো আছে, তাই সরাসরি অ্যাসাইন করা হলো
                existing.description = description
            else:
                new_agent = DynamicAgent(name=name, description=description, execution_steps=steps)
                self.db.add(new_agent)
            await self.db.commit()
            logger.success(f"🧠 [AgentFactory] New skill learned and registered: '{name}'")
        except Exception as exc:
            # বাংলা: db session None হলে rollback() ডাকলে AttributeError হবে — গার্ড যোগ করা হলো
            if self.db:
                await self.db.rollback()
            logger.error(f"Failed to save dynamic agent to registry: {exc}")
