from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from threading import RLock
from typing import Any

from core.action_policy import DEFAULT_ACTIONS, IMMUTABLE_SAFETY_ACTIONS


@dataclass(frozen=True)
class EffectivePolicy:
    rules: dict[str, Any]
    features: dict[str, bool]
    actions: dict[str, str] = field(default_factory=dict)
    limits: dict[str, int] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    version: int = 1
    updated_at: str = ""


class ConfigurablePolicyStore:
    """Canonical policy store with safe defaults and persistence-ready metadata."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._version = 1
        self._updated_at = datetime.now(UTC).isoformat()
        self._admin_rules: dict[str, Any] = {
            "task_mode": "approval_first",
            "allow_read_only": True,
            "allow_submissions": True,
            "allow_uploads": True,
            "manual_only_terms": [],
            "approval_terms": ["post", "publish", "send", "submit", "upload", "book"],
        }
        self._features: dict[str, bool] = {
            "browser_tasks": True,
            "social_tasks": True,
            "dashboard_mutations": True,
        }
        self._actions: dict[str, str] = {
            name: definition.mode.value for name, definition in DEFAULT_ACTIONS.items()
        }
        self._limits: dict[str, int] = {
            "max_sessions": 3,
            "idle_timeout_seconds": 900,
            "task_timeout_seconds": 300,
            "max_task_steps": 12,
            "max_retries": 2,
        }
        self._user_rules: dict[str, dict[str, Any]] = {}

    def _touch(self) -> None:
        self._version += 1
        self._updated_at = datetime.now(UTC).isoformat()

    def snapshot(self, user_id: str | None = None) -> EffectivePolicy:
        with self._lock:
            rules = dict(self._admin_rules)
            features = dict(self._features)
            actions = dict(self._actions)
            limits = dict(self._limits)
            sources = {key: "admin" for key in rules}
            sources.update({f"feature:{key}": "admin" for key in features})
            sources.update({f"action:{key}": "admin" for key in actions})
            sources.update({f"limit:{key}": "admin" for key in limits})
            if user_id and user_id in self._user_rules:
                for key, value in self._user_rules[user_id].items():
                    if key in rules:
                        rules[key] = value
                        sources[key] = "user"
            for name, definition in IMMUTABLE_SAFETY_ACTIONS.items():
                actions[name] = definition.mode.value
                sources[f"action:{name}"] = "platform"
            return EffectivePolicy(
                rules, features, actions, limits, sources, self._version, self._updated_at
            )

    def update_admin(
        self,
        rules: dict[str, Any] | None = None,
        features: dict[str, bool] | None = None,
        actions: dict[str, str] | None = None,
        limits: dict[str, int] | None = None,
    ) -> EffectivePolicy:
        with self._lock:
            if rules:
                self._admin_rules.update(rules)
            if features:
                self._features.update({key: bool(value) for key, value in features.items()})
            if actions:
                for key, value in actions.items():
                    if key not in IMMUTABLE_SAFETY_ACTIONS:
                        self._actions[key] = str(value)
            if limits:
                for key, value in limits.items():
                    if key in self._limits and int(value) > 0:
                        self._limits[key] = min(
                            int(value), self._limits[key] if key == "max_retries" else 3600
                        )
            self._touch()
            return self.snapshot()

    def update_user(self, user_id: str, rules: dict[str, Any]) -> EffectivePolicy:
        with self._lock:
            self._user_rules[user_id] = {
                key: value
                for key, value in rules.items()
                if key in {"task_mode", "allow_submissions", "allow_uploads", "allow_read_only"}
            }
            self._touch()
            return self.snapshot(user_id)


policy_store = ConfigurablePolicyStore()


def get_effective_policy(user_id: str | None = None) -> EffectivePolicy:
    return policy_store.snapshot(user_id)


__all__ = ["EffectivePolicy", "ConfigurablePolicyStore", "policy_store", "get_effective_policy"]
