"""This module, `skill_manager.py`, serves as the central hub for dynamic skill management within the SupremeAI project.
It provides robust mechanisms for registering, discovering, and dynamically synthesizing AI skills at runtime,
supporting both locally defined `BaseSkill` instances and on-the-fly generation of new skill schemas via Large Language Models.
Furthermore, it integrates with a broader Multi-Agent Communication Protocol (MCP) for distributed skill discovery,
ensuring the AI ecosystem can adapt and expand its capabilities as needed.

Key Components:
- `SkillManager`: A class responsible for managing the lifecycle of AI skills, including registration, discovery, and dynamic generation.
- `register_skill()`: Registers a `BaseSkill` instance with the manager, making it available for use.
- `get_skill()`: Retrieves a skill by name, searching first in the local registry, then a database, and finally attempting discovery via the MCP.
- `synthesize_skill_schema()`: Utilizes an LLM to generate a new skill's JSON schema based on a natural language task description.
- `skill_manager`: A global singleton instance of `SkillManager` for application-wide access to skill management functionalities.

Dependencies:
- `json`: For parsing and serializing JSON data, particularly for skill schemas.
- `typing.Any`: For flexible type hinting.
- `loguru`: For comprehensive and structured logging throughout the skill management process.
- `core.llm.llm_gateway`: Provides an interface for interacting with Large Language Models for skill synthesis.
- `core.mcp_client.MCPRegistryClient`: Facilitates communication with the Multi-Agent Communication Protocol registry for skill discovery.
- `core.skills.base.BaseSkill`: The foundational abstract base class for all skills managed by this system.
- `tools.mcp.mcp_supabase`: Used for querying and retrieving skill definitions from a Supabase database."""

# backend/core/skill_manager.py
import json
import threading
from typing import Any

from core.logging_config import logger
from core.security.codegen_gate import (
    denied_reason,
    inprocess_codegen_enabled,
    warn_inprocess_codegen_boot,
)


def _get_llm_gateway():
    """R2-MEM fix: resolve the gateway LAZILY.

    `from core.llm.llm_gateway import llm_gateway` triggered the module's
    lazy __getattr__ AT IMPORT TIME, constructing LLMGateway during boot and
    dragging in litellm (~240MB RSS) on every cold start even when no skill
    ever runs. Resolving on first use keeps boot light (512MB free tier)."""
    from core.llm.llm_gateway import get_llm_gateway

    return get_llm_gateway()


from core.mcp_client import MCPRegistryClient
from core.skills.base import BaseSkill
from tools.code.fuzz_sandbox import SecurityError, run_sandbox_ast_check

# Issue #682: loud one-time boot warning when the in-process exec escape hatch
# is explicitly enabled (local development only).
if inprocess_codegen_enabled():
    warn_inprocess_codegen_boot("SkillManager.get_skill")


class SkillManager:
    """
    বাংলা মন্তব্য: Skill-as-a-Service আর্কিটেকচারের কেন্দ্রবিন্দু।
    এই ম্যানেজার রানটাইমে স্কিল রেজিস্টার, ডিসকভার এবং ডিসপ্যাচ করে।
    এটি এখন এক্সিকিউটেবল BaseSkill অবজেক্ট নিয়ে কাজ করে।
    """

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}
        self.mcp_client = MCPRegistryClient()
        logger.info("SkillManager initialized for dynamic skill dispatch.")

    def register_skill(self, skill: BaseSkill, name: str | None = None):
        """
        বাংলা মন্তব্য: একটি স্কিল ইনস্ট্যান্স রেজিস্টারে যোগ করে।
        """
        skill_name = name or skill.name
        if skill_name in self._skills:
            logger.warning(f"Skill '{skill_name}' is already registered. Overwriting.")
        self._skills[skill_name] = skill
        logger.info(f"Skill '{skill_name}' successfully registered.")

    async def get_skill(self, skill_name: str) -> BaseSkill:
        """
        বাংলা মন্তব্য: রেজিস্ট্রি থেকে একটি স্কিল খুঁজে বের করে।
        যদি লোকালি না পাওয়া যায়, তবে MCP থেকে খোঁজার চেষ্টা করে।
        """
        if skill_name in self._skills:
            logger.debug(f"Found skill '{skill_name}' in local registry.")
            return self._skills[skill_name]

        logger.info(f"Skill '{skill_name}' not in local registry. Querying Database...")
        from tools.mcp.mcp_supabase import (
            ExecuteQueryInput,
            ResponseFormat,
            supabase_execute_sql,
        )

        try:
            query = "SELECT code FROM skills WHERE skill_name = %s AND status = 'active'"
            res = await supabase_execute_sql(
                ExecuteQueryInput(
                    query=query,
                    params=[skill_name],
                    response_format=ResponseFormat.JSON,
                )
            )
            data = json.loads(res)
            if "rows" in data and len(data["rows"]) > 0:
                code_content = data["rows"][0]["code"]

                # --- নিরাপত্তা গেট ০ (issue #682): fail-closed codegen gate ---
                # The `skills` table's `code` column
                # holds arbitrary Python source — a compromised service-role key,
                # a future marketplace-submit feature, or downstream SQL injection
                # that writes one row would otherwise get in-process RCE. The AST
                # check and restricted builtins below are NOT a security boundary
                # (issue #704 precedent), so by default
                # (SUPREMEAI_ALLOW_INPROCESS_CODEGEN unset — all prod/staging)
                # nothing is executed: the skill is rejected with this module's
                # existing ValueError convention and the caller falls back.
                if not inprocess_codegen_enabled():
                    logger.warning(
                        f"[SkillManager] Blocked in-process skill exec for "
                        f"'{skill_name}': {denied_reason('SkillManager.get_skill')}"
                    )
                    raise ValueError(
                        f"Skill '{skill_name}' was not loaded: "
                        f"{denied_reason('SkillManager.get_skill')}"
                    )

                # --- নিরাপত্তা গেট ১: AST-স্তরের স্ট্যাটিক ভেটিং ---
                # আগে DB থেকে আসা কোড কোনো যাচাই ছাড়াই সরাসরি `exec(code, globals().copy(), ...)`
                # দিয়ে চালানো হতো — অর্থাৎ `skills` টেবিলে যে কেউ (compromised service-role key,
                # future marketplace-submit ফিচার, বা downstream SQL injection দিয়ে) একটি row
                # লিখতে পারলেই backend প্রসেসে remote code execution (RCE) সম্ভব ছিল। রিপোতে
                # ইতিমধ্যে এই ঠিক কাজের জন্য বানানো `run_sandbox_ast_check` (fuzz_sandbox.py) আছে
                # — os/subprocess/socket import, eval/exec/getattr/globals/locals-এর মতো বিপজ্জনক
                # প্যাটার্ন ব্লক করে — কিন্ত এই ফাইলে সেটা কখনো call করা হয়নি। এখন সেটা প্রয়োগ করা হলো।
                try:
                    ast_ok = run_sandbox_ast_check(code_content)
                except SecurityError as sec_exc:
                    logger.error(f"🚨 Blocked unsafe skill code for '{skill_name}': {sec_exc}")
                    raise ValueError(
                        f"Skill '{skill_name}' failed security validation and was not loaded."
                    ) from sec_exc
                if not ast_ok:
                    raise ValueError(
                        f"Skill '{skill_name}' has invalid/unparseable code and was not loaded."
                    )

                # --- নিরাপত্তা গেট ২: ন্যূনতম, লক-ডাউন করা exec namespace ---
                # `globals().copy()` এই মডিউলের সব ইম্পোর্ট (llm_gateway, MCPRegistryClient, logger
                # ইত্যাদি) exec করা কোডের কাছে উন্মুক্ত করে দিত। এখন শুধু ক্লাস ডিফাইন করতে যা
                # লাগে (BaseSkill) এবং একটি সীমিত builtins সেট-ই দেওয়া হচ্ছে — defense-in-depth,
                # যাতে AST-চেক এড়িয়ে গেলেও exec'd কোড অ্যাপ্লিকেশনের ইন্টারনাল ক্লায়েন্ট/সিক্রেটে
                # হাত দিতে না পারে।
                import builtins as _builtins

                _SAFE_SKILL_BUILTINS = {
                    "__build_class__": _builtins.__build_class__,  # class স্টেটমেন্টের জন্য আবশ্যক
                    "__name__": "supreme_skill_sandbox",
                    "object": object,
                    "range": range,
                    "len": len,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "list": list,
                    "dict": dict,
                    "set": set,
                    "tuple": tuple,
                    "isinstance": isinstance,
                    "super": super,
                    "Exception": Exception,
                    "ValueError": ValueError,
                }
                local_env: dict[str, Any] = {}
                exec_globals = {
                    "__builtins__": _SAFE_SKILL_BUILTINS,
                    "BaseSkill": BaseSkill,
                }
                exec(code_content, exec_globals, local_env)  # noqa: S102 -- AST-vetted, locked-down namespace above

                for item in local_env.values():
                    if isinstance(item, type) and issubclass(item, BaseSkill) and item != BaseSkill:
                        skill_instance = item()
                        self.register_skill(skill_instance, skill_name)
                        return skill_instance
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error fetching skill '{skill_name}' from DB: {e}")

        logger.info(f"Skill '{skill_name}' not in DB. Querying MCP-Hub...")
        mcp_tools = await self.mcp_client.discover_tools(domain=skill_name)
        if mcp_tools and mcp_tools[0] != "generic_tool":
            logger.info(f"Discovered MCP tool for '{skill_name}'. Wrapping as a skill.")
            # একটি র‍্যাপার তৈরি করে রেজিস্টার করা যেতে পারে
            # from core.skills.base import MCPSkillWrapper
            # mcp_skill = MCPSkillWrapper(tool_name=skill_name, mcp_client=self.mcp_client)
            # self.register_skill(mcp_skill)
            # return mcp_skill
            pass

        raise ValueError(f"Skill '{skill_name}' not found in local registry or MCP.")

    async def synthesize_skill_schema(self, task_description: str) -> dict[str, Any]:
        """
        বাংলা মন্তব্য: LLM ব্যবহার করে একটি নতুন স্কিলের JSON স্কিমা তৈরি করে।
        এটি আগের get_or_create_skill এর মূল লজিকটি ধারণ করে।
        """
        logger.warning(
            "🚀 [DB Miss] Unique task scenario. Escalating to Claude-3.5-Sonnet for Skill Generation..."
        )

        system_prompt = (
            "You are SupremeAI's Skill Architect. Your sole job is to generate a reusable, structural "
            "step-by-step automation blueprint for a Playwright browser agent based on user request. "
            "You must return ONLY a raw valid JSON object. No conversation, no markdown codeblocks."
        )
        prompt = f"""
        Create a functional automation extraction schema for the following task: '{task_description}'.
        The output format must strictly be JSON matching this shape:
        {{
            "skill_name": "UniqueCamelCaseName",
            "description": "Detailed summary of what this skill does for future lookup",
            "parameters": [
                {{"name": "url", "type": "string", "description": "Target URL"}}
            ],
            "execution_steps": [
                {{"action": "navigate", "url": "target_url"}},
                {{"action": "click", "selector": ".btn"}}
            ]
        }}
        """
        # বাংলা: আগে model_filters=["claude-3-5-sonnet"] হার্ডকোড ছিল — claude unavailable হলে skill synthesis ব্যর্থ হতো।
        # এখন task_type="coding" দিয়ে gateway নিজে best available coding model বেছে নেবে, failover সহ।
        response = await _get_llm_gateway().acompletion(
            prompt=prompt,
            system_prompt=system_prompt,
            task_type="coding",
        )

        raw_text = response.get("text", "{}").strip()
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            raw_text = "\n".join(
                lines[1:-1] if lines.startswith("```") and lines[-1].startswith("```") else lines
            )
            raw_text = "\n".join(lines).strip()

        try:
            new_skill = json.loads(raw_text)
            logger.success(f"Synthesized new skill schema: '{new_skill.get('skill_name')}'")
            return new_skill
        except Exception as e:
            logger.error(f"Failed to parse synthesized skill schema: {e!s}")
            raise ValueError("Invalid JSON configuration from Skill Factory.") from e


# Global thread-safe singleton
_skill_manager_lock = threading.Lock()
_global_skill_manager: SkillManager | None = None


def get_skill_manager() -> SkillManager:
    """Thread-safe singleton getter for SkillManager."""
    global _global_skill_manager
    if _global_skill_manager is None:
        with _skill_manager_lock:
            if _global_skill_manager is None:
                _global_skill_manager = SkillManager()
    return _global_skill_manager


class _LazySkillManagerProxy:
    """Proxy object so 'from core.skill_manager import skill_manager' stays backwards compatible."""

    def __getattr__(self, item: str) -> Any:
        return getattr(get_skill_manager(), item)


skill_manager = _LazySkillManagerProxy()
