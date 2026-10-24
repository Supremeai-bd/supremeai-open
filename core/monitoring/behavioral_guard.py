# SupremeAI 2.0 - Behavioral Anomaly Detection Guard
# বাংলা মন্তব্য: এটি এআই এজেন্টের টুল রান, ইনপুট/আউটপুট ফ্রিকোয়েন্সি ও আচরণের অস্বাভাবিকতা স্বয়ংক্রিয়ভাবে মনিটর ও ব্লক করে।

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from core.logging_config import logger


class BehavioralGuard:
    """
    Behavioral Anomaly Detection Guard for AI Agents.
    Tracks tool calls, execution rate, prompt repetitions, and sandbox safety violations.
    """

    ANOMALY_THRESHOLDS = {
        "max_tool_calls_per_minute": 30,
        "max_identical_prompts": 5,
        "max_errors_per_minute": 10,
    }

    def __init__(self):
        self._action_timestamps: dict[str, list[float]] = defaultdict(list)
        self._prompt_history: dict[str, list[str]] = defaultdict(list)
        self._error_counts: dict[str, list[float]] = defaultdict(list)
        self._blocked_agents: set[str] = set()

    def is_agent_blocked(self, agent_id: str) -> bool:
        """Check if an agent is currently blocked due to anomalous behavior."""
        return agent_id in self._blocked_agents

    def record_action(
        self, agent_id: str, action_type: str, prompt_or_command: str
    ) -> dict[str, Any]:
        """
        Record and analyze an agent action for behavioral anomalies.
        Returns evaluation dict with success status and potential anomaly alerts.
        """
        if self.is_agent_blocked(agent_id):
            return {
                "allowed": False,
                "reason": f"Agent '{agent_id}' is blocked due to previous behavioral anomaly.",
            }

        now = time.time()
        # Clean older timestamps (older than 60 seconds)
        self._action_timestamps[agent_id] = [
            t for t in self._action_timestamps[agent_id] if now - t < 60.0
        ]
        self._action_timestamps[agent_id].append(now)

        # Check call frequency anomaly
        call_count = len(self._action_timestamps[agent_id])
        if call_count > self.ANOMALY_THRESHOLDS["max_tool_calls_per_minute"]:
            self._blocked_agents.add(agent_id)
            logger.error(
                f"🚨 Behavioral Guard Alert: Agent '{agent_id}' exceeded tool call limit ({call_count}/min). BLOCKED."
            )
            return {
                "allowed": False,
                "reason": f"Tool call frequency limit exceeded ({call_count}/min).",
                "anomaly_type": "FREQUENCY_SPIKE",
            }

        # Check for loop detection (identical prompt repetitions)
        history = self._prompt_history[agent_id]
        history.append(prompt_or_command)
        if len(history) > 20:
            history.pop(0)

        recent_identical = history.count(prompt_or_command)
        if recent_identical >= self.ANOMALY_THRESHOLDS["max_identical_prompts"]:
            self._blocked_agents.add(agent_id)
            logger.error(
                f"🚨 Behavioral Guard Alert: Agent '{agent_id}' detected in infinite execution loop. BLOCKED."
            )
            return {
                "allowed": False,
                "reason": "Infinite prompt execution loop detected.",
                "anomaly_type": "INFINITE_LOOP",
            }

        # Check for malicious patterns (e.g. sandbox escapes)
        suspicious_keywords = ["rm -rf /", "drop database", "chmod 777 /", "../../../etc/passwd"]
        for kw in suspicious_keywords:
            if kw in prompt_or_command.lower():
                self._blocked_agents.add(agent_id)
                logger.critical(
                    f"🚨 SECURITY ALARM: Agent '{agent_id}' attempted suspicious action containing '{kw}'. BLOCKED IMMEDIATELY."
                )
                return {
                    "allowed": False,
                    "reason": f"Security boundary violation detected: '{kw}'.",
                    "anomaly_type": "SECURITY_VIOLATION",
                }

        return {"allowed": True, "reason": "Normal behavior."}

    def unblock_agent(self, agent_id: str) -> None:
        """Manually unblock an agent."""
        self._blocked_agents.discard(agent_id)
        self._action_timestamps[agent_id].clear()
        self._prompt_history[agent_id].clear()
        logger.info(f"Agent '{agent_id}' unblocked.")
