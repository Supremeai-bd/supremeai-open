from __future__ import annotations

from dataclasses import dataclass

from core.action_policy import ActionMode, get_action_definition
from core.effective_policy import get_effective_policy


@dataclass(frozen=True)
class TaskPolicyDecision:
    allowed: bool
    risk: str
    message: str
    action: str = "read"


def evaluate_goal(goal: str, user_id: str | None = None) -> TaskPolicyDecision:
    normalized = goal.casefold()
    policy = get_effective_policy(user_id)
    if not policy.features.get("browser_tasks", True):
        return TaskPolicyDecision(
            False,
            "disabled",
            "This task type is currently disabled by your workspace administrator.",
        )

    manual_terms = {
        "payment": "payment",
        "pay": "payment",
        "password": "password_change",
        "security setting": "security_change",
        "delete account": "account_deletion",
        "wire transfer": "payment",
    }
    for term, action_name in manual_terms.items():
        if term in normalized:
            action = get_action_definition(action_name)
            return TaskPolicyDecision(
                False,
                "manual",
                action.description + " Please complete that step manually.",
                action_name,
            )

    approval_terms = tuple(str(term).casefold() for term in policy.rules.get("approval_terms", []))
    for term in approval_terms:
        if term in normalized:
            action_name = term if term in policy.actions else "submit"
            action = get_action_definition(action_name, policy.actions.get(action_name))
            if (
                not policy.rules.get("allow_submissions", True)
                or action.mode == ActionMode.DISABLED
            ):
                return TaskPolicyDecision(
                    False,
                    "disabled",
                    "This action is currently disabled by your workspace administrator.",
                    action_name,
                )
            if action.mode == ActionMode.MANUAL:
                return TaskPolicyDecision(
                    False,
                    "manual",
                    action.description + " Please complete that step manually.",
                    action_name,
                )
            return TaskPolicyDecision(
                True,
                "approval",
                "This action needs your approval immediately before it is submitted.",
                action_name,
            )

    if not policy.rules.get("allow_read_only", True):
        return TaskPolicyDecision(
            False,
            "disabled",
            "Read-only browser tasks are currently disabled by your workspace administrator.",
            "read",
        )
    return TaskPolicyDecision(
        True,
        "low",
        "SupremeAI can start with a safe read-only step and will pause before anything sensitive.",
        "read",
    )
