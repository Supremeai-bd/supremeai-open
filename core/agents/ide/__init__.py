"""
SupremeAI IDE Trio Agents
=========================
Adapters for IDE-installed AI tools (Gemini, Kilo Code, Cline).

Each adapter wraps its respective tool and exposes a standardized
`run()` interface so the pipeline orchestrator can chain them
together as: Code Writer → Code Reviewer → Production Checker.

Roles:
    - GeminiWriter      (Code Writer)      — Generates code via Gemini API
    - KiloReviewer       (Code Reviewer)    — Reviews code via Kilo Code + Guardian rules
    - ClineChecker       (Production Check)  — Validates production readiness via Cline/CLI

Usage (backend)::
    from agents.ide import GeminiWriter, KiloReviewer, ClineChecker

    writer = GeminiWriter()
    result = await writer.write_code("Build a Python HTTP server", language="python")
"""

from agents.ide.trio_adapters import (
    ClineChecker,
    GeminiWriter,
    KiloReviewer,
)

__all__ = [
    "ClineChecker",
    "GeminiWriter",
    "KiloReviewer",
]
