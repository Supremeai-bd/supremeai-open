# SupremeAI 2.0 - Dynamic Tool Forge Engine
# বাংলা মন্তব্য: এটি উপযুক্ত টুল না থাকলে তাৎক্ষণিকভাবে নতুন হেলপার টুল জেনারেট ও এক্সিকিউট করতে পারে।

from __future__ import annotations

from typing import Any

from core.logging_config import logger


class ToolForge:
    """
    Dynamic Tool Forge Engine.
    Synthesizes custom Python helper tools on-the-fly when pre-built skills are unavailable.
    """

    def __init__(self):
        self._synthesized_tools: dict[str, dict[str, Any]] = {}

    async def synthesize_tool(
        self, tool_name: str, task_description: str, code_snippet: str
    ) -> bool:
        """
        Synthesize and register a dynamic helper tool.
        """
        try:
            from core.security.scanning.ast_scanner import ASTSandboxScanner

            scanner = ASTSandboxScanner()
            scan_res = scanner.scan(code_snippet)
            if not scan_res.is_safe:
                logger.error(
                    f"Tool Forge rejected unsafe code for tool '{tool_name}': {scan_res.violations}"
                )
                return False

            self._synthesized_tools[tool_name] = {
                "name": tool_name,
                "description": task_description,
                "code": code_snippet,
            }
            logger.info(
                f"Tool Forge successfully synthesized and verified dynamic tool: '{tool_name}'"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to synthesize tool '{tool_name}': {e}")
            return False

    def get_tool(self, tool_name: str) -> dict[str, Any] | None:
        """Retrieve a synthesized tool specification."""
        return self._synthesized_tools.get(tool_name)
