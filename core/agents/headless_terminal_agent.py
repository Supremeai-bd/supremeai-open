"""
SupremeAI — Headless Terminal AI Agent
========================================

CLI handler for terminal-based AI interactions.
- Natural language command interpretation
- Shell command execution with safety checks
- Command history and context awareness
- Zero-cost: uses LLM routing + command sandboxing
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.config_cache import config_cache
from core.errors.error_bus import with_error_bus
from core.logging_config import logger

# ── Constants ────────────────────────────────────────────────────────────────
COMMAND_TIMEOUT = 30  # seconds
MAX_OUTPUT_SIZE = 10000  # characters
SAFETY_CHECK_CACHE_TTL = 300


class CommandSafety(StrEnum):
    SAFE = "safe"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CommandResult:
    """Result of command execution."""

    command: str
    exit_code: int
    output: str
    safety_status: CommandSafety
    explanation: str | None


class CommandInterpreter:
    """
    Interprets natural language into shell commands.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm = llm_router or ModelRouter()
        self.cache = get_cache()

    async def interpret(self, natural_query: str, context: dict[str, Any] | None = None) -> str:
        """
        Convert natural language to shell command.

        Args:
            natural_query: Natural language request.
            context: Execution context (path, os, user).

        Returns:
            Shell command string.
        """
        cache_key = f"cmd_interp:{hashlib.sha256(natural_query.encode()).hexdigest()[:16]}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached  # type: ignore

        prompt = (
            "You are a shell command generator. Convert the following natural language "
            "request to a safe, accurate shell command. Return ONLY the command, no explanations.\n\n"
            f"Context: {json.dumps(context or {}, indent=2)}\n"
            f"Request: {natural_query}"
        )

        try:
            result = await self.llm.async_route_and_generate(
                prompt=prompt,
                task_type="generation",
                max_tokens=config_cache.get("headless_terminal_agent_max_tokens", 200),
                temperature=config_cache.get("headless_terminal_agent_temperature", 0.1),
            )
            command = result.get("text", "").strip()

            # Clean command
            command = re.sub(r"^```\w*\s*", "", command)
            command = re.sub(r"\s*```$", "", command)

            await self.cache.set(cache_key, command, ttl=SAFETY_CHECK_CACHE_TTL)
            return command

        except Exception as e:
            logger.error(f"Command interpretation failed: {e}")
            return ""


class SafetyChecker:
    """
    Checks command safety before execution.
    Blocks dangerous patterns.
    """

    BLOCKED_PATTERNS = [
        r"rm\s+-rf\s+/",  # Recursive root deletion
        r"mkfs",  # File system formatting
        r"dd\s+if=",  # Disk overwrite
        r">\s*/dev/sd",  # Direct disk write
        r":()\s*{\s*:\|:&\s*}",  # Fork bomb
        r"chmod\s+777",  # Insecure permissions
        r"curl.*\|\s*(bash|sh)",  # Remote code execution
        r"wget.*\|\s*(bash|sh)",  # Remote code execution
    ]

    REVIEW_PATTERNS = [
        r"sudo",  # Privilege escalation
        r"rm\s+-",  # File deletion
        r"mv\s+.*\s+/",  # Moving to root
        r"git\s+push",  # Git push
        r"npm\s+install\s+-g",  # Global package install
    ]

    @classmethod
    def check(cls, command: str) -> tuple[CommandSafety, str]:
        """
        Check command safety.

        Returns:
            Tuple of (safety status, reason).
        """
        for pattern in cls.BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return CommandSafety.BLOCKED, f"Blocked pattern: {pattern}"

        for pattern in cls.REVIEW_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return CommandSafety.REVIEW_REQUIRED, f"Review required: {pattern}"

        return CommandSafety.SAFE, "Command passed safety check"


class HeadlessTerminalAgent:
    """
    CLI-based AI agent for terminal interactions.
    """

    def __init__(
        self,
        interpreter: CommandInterpreter | None = None,
        safety_checker: SafetyChecker | None = None,
    ) -> None:
        self.interpreter = interpreter or CommandInterpreter()
        self.safety = safety_checker or SafetyChecker()
        self.cache = get_cache()
        self.command_history: list[CommandResult] = []
        logger.info("HeadlessTerminalAgent initialized")

    async def execute(
        self,
        command_or_query: str,
        context: dict[str, Any] | None = None,
        auto_confirm: bool = False,
    ) -> CommandResult:
        """
        Execute a command or natural language query.

        Args:
            command_or_query: Shell command or natural language request.
            context: Execution context.
            auto_confirm: Skip safety confirmation for review commands.

        Returns:
            CommandResult with execution details.
        """
        # Interpret if natural language
        if not self._looks_like_command(command_or_query):
            command = await self.interpreter.interpret(command_or_query, context)
        else:
            command = command_or_query

        # Safety check
        safety, reason = self.safety.check(command)

        if safety == CommandSafety.BLOCKED:
            logger.warning(f"Blocked dangerous command: {command}")
            return CommandResult(
                command=command,
                exit_code=1,
                output=f"Command blocked: {reason}",
                safety_status=safety,
                explanation=reason,
            )

        if safety == CommandSafety.REVIEW_REQUIRED and not auto_confirm:
            return CommandResult(
                command=command,
                exit_code=2,
                output=reason,
                safety_status=safety,
                explanation=f"Command requires confirmation: {command}",
            )

        # Execute command
        return await self._run_command(command)

    def _looks_like_command(self, text: str) -> bool:
        """Heuristic to detect if text is already a command.

        বাংলা: বিপজ্জনক কমান্ডগুলো সহ সব shell কমান্ড prefix এখানে রাখা হয়েছে।
        rm, sudo ইত্যাদি না থাকলে NL interpreter-এ যায় এবং safety check bypass হয় — critical bug।
        """
        cmd_indicators = [
            # ফাইল অপারেশন
            "ls",
            "cd",
            "grep",
            "find",
            "cat",
            "rm",
            "mv",
            "cp",
            "chmod",
            "chown",
            # বিপজ্জনক সিস্টেম কমান্ড — অবশ্যই safety check করতে হবে
            "sudo",
            "su",
            "mkfs",
            "dd",
            "fdisk",
            "parted",
            # নেটওয়ার্ক ও ডাউনলোড
            "wget",
            "curl",
            "ssh",
            "scp",
            "rsync",
            # প্যাকেজ ম্যানেজার
            "npm",
            "pip",
            "pip3",
            "apt",
            "apt-get",
            "yum",
            "brew",
            # ভার্সন কন্ট্রোল ও ডেভ টুল
            "git",
            "docker",
            "kubectl",
            "python",
            "python3",
            "node",
        ]
        stripped = text.strip()
        return any(stripped.startswith(c + " ") or stripped == c for c in cmd_indicators)

    async def _run_command(self, command: str) -> CommandResult:
        """Run command safely.

        বাংলা: শেল İnjeksion প্রতিরোধে `create_subprocess_shell` এর বদলে
        `create_subprocess_exec` + `shlex.split` ব্যবহার করা হয়েছে।
        LLM-উৎপন্ন commands সরাসরি shell-এ execute করা হয় না —
        tokenized argument list-এ রূপান্তর করা হয়।
        """
        try:
            # 🔒 P0 FIX: shlex.split দিয়ে command tokenize করে shell injection প্রতিরোধ
            tokens = shlex.split(command)
            if not tokens:
                return CommandResult(
                    command=command,
                    exit_code=1,
                    output="Empty command after tokenization",
                    safety_status=CommandSafety.BLOCKED,
                    explanation="Empty command",
                )

            process = await asyncio.create_subprocess_exec(
                *tokens,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=COMMAND_TIMEOUT
                )
                output = (stdout or stderr or b"").decode("utf-8")[:MAX_OUTPUT_SIZE]
                exit_code = process.returncode or 0
            except TimeoutError:
                process.kill()
                return CommandResult(
                    command=command,
                    exit_code=124,  # timeout
                    output=f"Command timed out after {COMMAND_TIMEOUT}s",
                    safety_status=CommandSafety.UNKNOWN,
                    explanation="Timeout",
                )

            result = CommandResult(
                command=command,
                exit_code=exit_code,
                output=output,
                safety_status=CommandSafety.SAFE,
                explanation=None,
            )

            self.command_history.append(result)
            return result

        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return CommandResult(
                command=command,
                exit_code=1,
                output=f"Execution error: {e}",
                safety_status=CommandSafety.UNKNOWN,
                explanation=str(e),
            )

    @with_error_bus("suggest")
    async def suggest(self, task: str, context: dict[str, Any] | None = None) -> str:
        """Suggest next command based on task and history."""
        history_context = [r.command for r in self.command_history[-5:]]

        prompt = (
            "Given the following task and recent command history, suggest the next "
            "shell command to execute. Return ONLY the command.\n\n"
            f"History: {history_context}\n"
            f"Task: {task}"
        )

        try:
            result = await self.interpreter.llm.async_route_and_generate(
                prompt=prompt,
                task_type="reasoning",
                max_tokens=config_cache.get("headless_terminal_agent_max_tokens", 200),
            )
            return result.get("text", "").strip()
        except Exception as exc:
            logger.error(f"[HeadlessTerminalAgent] suggest() failed: {exc}")
            return ""

    @with_error_bus("explain_output")
    async def explain_output(self, output: str) -> str:
        """Explain command output in natural language."""
        prompt = f"Explain the following command output in 1-2 sentences:\n\n{output[:2000]}"

        try:
            result = await self.interpreter.llm.async_route_and_generate(
                prompt=prompt,
                task_type="summarization",
                max_tokens=config_cache.get("headless_terminal_agent_max_tokens", 200),
            )
            return result.get("text", "").strip()
        except Exception as exc:
            logger.error(f"[HeadlessTerminalAgent] explain_output() failed: {exc}")
            return "Unable to explain output."


# Singleton
_agent_instance: HeadlessTerminalAgent | None = None


def get_headless_agent() -> HeadlessTerminalAgent:
    """Get or create the singleton HeadlessTerminalAgent instance."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = HeadlessTerminalAgent()
    return _agent_instance


# CLI Entry Point
if __name__ == "__main__":
    import sys

    async def main():
        agent = get_headless_agent()
        if len(sys.argv) < 2:
            return

        query = " ".join(sys.argv[1:])
        await agent.execute(query, auto_confirm=True)

    asyncio.run(main())
