# SupremeAI 2.0 - Causal Root-Cause Debugger
# বাংলা মন্তব্য: এটি স্ট্যাকট্রেস ও এরর লক থেকে স্বয়ংক্রিয়ভাবে মূল কারণ (Root Cause) বিশ্লেষণ ও প্যাচ রেকমেন্ডেশন তৈরি করে।

from __future__ import annotations

import traceback
from typing import Any

from core.logging_config import logger


class CausalDebugger:
    """
    Causal Root-Cause Analysis Debugger.
    Parses tracebacks, isolates the breaking module/line, and formulates automated remediation steps.
    """

    def analyze_exception(
        self, exc: Exception, context_info: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Analyze an exception object and extract causal insights.
        """
        exc_type = type(exc).__name__
        exc_msg = str(exc)
        tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

        causal_module = "unknown"
        failing_line = -1

        # Extract root frame
        tb_frames = traceback.extract_tb(exc.__traceback__)
        if tb_frames:
            last_frame = tb_frames[-1]
            causal_module = last_frame.filename
            failing_line = last_frame.lineno

        analysis = {
            "exception_type": exc_type,
            "message": exc_msg,
            "causal_module": causal_module,
            "failing_line": failing_line,
            "traceback": tb_str,
            "suggested_remediation": self._suggest_fix(exc_type, exc_msg),
        }

        logger.info(
            f"Causal Debugger analyzed failure in [{causal_module}:{failing_line}] -> {exc_type}: {exc_msg}"
        )
        return analysis

    def _suggest_fix(self, exc_type: str, exc_msg: str) -> str:
        """Rule-based initial remediation suggestion."""
        if "KeyError" in exc_type:
            return "Ensure dictionary key exists or use dict.get() fallback."
        elif "TypeError" in exc_type:
            return "Verify function parameter types and handle None values before property access."
        elif "Connection" in exc_msg or "Timeout" in exc_msg:
            return "Verify backend service health, database pool availability, or switch to backup provider."
        elif "Permission" in exc_msg or "Denied" in exc_msg:
            return "Check sandbox permissions or file boundary restrictions."
        return "Inspect stacktrace and apply targeted delta patch."
