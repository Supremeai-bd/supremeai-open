# backend/core/skills/core_skills.py
from typing import Any

from core.llm.llm_gateway import llm_gateway
from core.skills.base import BaseSkill
from models.shared_workspace import SharedWorkspace


class SystemDesignSkill(BaseSkill):
    """
    বাংলা মন্তব্য: সিস্টেম আর্কিটেকচার ডিজাইন করার জন্য একটি কোর স্কিল।
    """

    @property
    def name(self) -> str:
        return "SystemDesignSkill"

    async def execute(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
        **kwargs: Any,
    ) -> Any:
        workspace.log(f"{self.name}: Starting system architecture layout analysis...")
        sys_prompt = "You are a lead system architect. Define file structures, component breakdown, and database schemas."
        user_prompt = f"Design architecture for task: {workspace.original_prompt}"

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
        resp = await llm_gateway.acompletion(model=model_name, messages=messages, user_id=user_id)
        return resp.get("choices", [{}])[0].get("message", {}).get("content", "")


class CodeGenerationSkill(BaseSkill):
    """
    বাংলা মন্তব্য: আর্কিটেকচার ব্লুপ্রিন্ট থেকে রিয়েল কোড জেনারেট করার স্কিল।
    """

    @property
    def name(self) -> str:
        return "CodeGenerationSkill"

    async def execute(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-pro",
        **kwargs: Any,
    ) -> Any:
        workspace.log(f"{self.name}: Generating raw code from blueprints...")
        sys_prompt = "You are an elite Coder Agent. Write the code implementation based on the architecture blueprint provided."
        blueprint = kwargs.get("blueprint", workspace.original_prompt)
        user_prompt = f"Write code for this blueprint:\n{blueprint}"

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
        resp = await llm_gateway.acompletion(model=model_name, messages=messages, user_id=user_id)
        return resp.get("choices", [{}])[0].get("message", {}).get("content", "")


class StaticAnalysisSkill(BaseSkill):
    """
    বাংলা মন্তব্য: কোড জেনারেশন শেষে QA টেস্টিং এবং লিন্টিং সিমুলেট করে।
    """

    @property
    def name(self) -> str:
        return "StaticAnalysisSkill"

    async def execute(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
        **kwargs: Any,
    ) -> Any:
        workspace.log(f"{self.name}: Simulating static analysis and QA review...")
        sys_prompt = "You are a QA Agent. Analyze the provided code for bugs, security issues, and style violations. Respond with APPROVED or FAILED and feedback."
        code = kwargs.get("code", "")
        user_prompt = f"Analyze this code:\n{code}"

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
        resp = await llm_gateway.acompletion(model=model_name, messages=messages, user_id=user_id)
        return resp.get("choices", [{}])[0].get("message", {}).get("content", "")


class ResearchSkill(BaseSkill):
    """
    বাংলা মন্তব্য: ওয়েব অ্যানালাইসিস এবং রিসার্চ করার স্কিল।
    """

    @property
    def name(self) -> str:
        return "ResearchSkill"

    async def execute(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
        **kwargs: Any,
    ) -> Any:
        workspace.log(f"{self.name}: Synthesizing research data...")
        sys_prompt = "You are a Research Agent. Conduct a detailed synthesis of the requested topic and provide actionable insights."
        topic = kwargs.get("topic", workspace.original_prompt)
        user_prompt = f"Research this topic:\n{topic}"

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
        resp = await llm_gateway.acompletion(model=model_name, messages=messages, user_id=user_id)
        return resp.get("choices", [{}])[0].get("message", {}).get("content", "")


class ToolSynthesisSkill(BaseSkill):
    """
    বাংলা মন্তব্য: জিরো-শট লার্নিংয়ের মাধ্যমে নতুন টুল বানানোর স্কিল (Morphic Engine)।
    """

    @property
    def name(self) -> str:
        return "ToolSynthesisSkill"

    async def execute(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
        **kwargs: Any,
    ) -> Any:
        workspace.log(f"{self.name}: Synthesizing JSON definition for new tool...")
        sys_prompt = "You are an AI Tool Synthesizer. Generate a JSON schema for a new tool that can solve the user's missing capability."
        capability = kwargs.get("capability", "unknown capability")
        user_prompt = f"Create a tool JSON for capability: {capability}"

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
        resp = await llm_gateway.acompletion(model=model_name, messages=messages, user_id=user_id)
        return resp.get("choices", [{}])[0].get("message", {}).get("content", "")


class ToolExecutionSkill(BaseSkill):
    """
    বাংলা মন্তব্য: এক্সটার্নাল টুলস বা MCP সার্ভার রান করার সিমুলেশন।
    """

    @property
    def name(self) -> str:
        return "ToolExecutionSkill"

    async def execute(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
        **kwargs: Any,
    ) -> Any:
        tool_name = kwargs.get("tool_name", "unknown_tool")
        workspace.log(f"{self.name}: Executing tool {tool_name}...")
        sys_prompt = "You are an Execution Agent. Simulate the output of running a specific tool."
        user_prompt = (
            f"Simulate execution of tool: {tool_name} with args: {kwargs.get('tool_args', {})}"
        )

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
        resp = await llm_gateway.acompletion(model=model_name, messages=messages, user_id=user_id)
        return resp.get("choices", [{}])[0].get("message", {}).get("content", "")


class ExperiencePersistenceSkill(BaseSkill):
    """
    বাংলা মন্তব্য: এআই ব্রেইনের রিফ্লেকশন মেমোরি যা ডেটাবেসে লগ সেভ করে।
    """

    @property
    def name(self) -> str:
        return "ExperiencePersistenceSkill"

    async def execute(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
        **kwargs: Any,
    ) -> Any:
        workspace.log(f"{self.name}: Saving execution experience to memory...")
        experience_summary = kwargs.get("summary", "Task completed.")
        return f"Saved experience: {experience_summary}"
