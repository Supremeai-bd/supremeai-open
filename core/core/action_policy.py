from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ActionMode(StrEnum):
    ALLOWED = "allowed"
    APPROVAL = "approval_required"
    MANUAL = "manual_only"
    DISABLED = "disabled"


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    mode: ActionMode
    description: str
    immutable: bool = False


IMMUTABLE_SAFETY_ACTIONS = {
    "payment": ActionDefinition(
        "payment", ActionMode.MANUAL, "Payments must be completed manually.", True
    ),
    "password_change": ActionDefinition(
        "password_change", ActionMode.MANUAL, "Password changes must be completed manually.", True
    ),
    "security_change": ActionDefinition(
        "security_change", ActionMode.MANUAL, "Security settings must be changed manually.", True
    ),
    "credential_access": ActionDefinition(
        "credential_access", ActionMode.MANUAL, "Credentials are never collected or exposed.", True
    ),
    "account_deletion": ActionDefinition(
        "account_deletion", ActionMode.MANUAL, "Account deletion must be completed manually.", True
    ),
    "audit_bypass": ActionDefinition(
        "audit_bypass", ActionMode.MANUAL, "Audit records cannot be bypassed.", True
    ),
}

DEFAULT_ACTIONS = {
    "navigate": ActionDefinition("navigate", ActionMode.ALLOWED, "Open a website."),
    "read": ActionDefinition("read", ActionMode.ALLOWED, "Read public information."),
    "screenshot": ActionDefinition("screenshot", ActionMode.ALLOWED, "Capture page evidence."),
    "extract": ActionDefinition("extract", ActionMode.ALLOWED, "Extract visible information."),
    "post": ActionDefinition("post", ActionMode.APPROVAL, "Publish content after approval."),
    "send": ActionDefinition("send", ActionMode.APPROVAL, "Send a message after approval."),
    "submit": ActionDefinition("submit", ActionMode.APPROVAL, "Submit a form after approval."),
    "upload": ActionDefinition("upload", ActionMode.APPROVAL, "Upload a file after approval."),
}


def get_action_definition(name: str, configured_mode: str | None = None) -> ActionDefinition:
    key = name.casefold().strip()
    if key in IMMUTABLE_SAFETY_ACTIONS:
        return IMMUTABLE_SAFETY_ACTIONS[key]
    base = DEFAULT_ACTIONS.get(
        key, ActionDefinition(key, ActionMode.APPROVAL, "This action needs your approval.")
    )
    if configured_mode and configured_mode in {mode.value for mode in ActionMode}:
        return ActionDefinition(
            base.name, ActionMode(configured_mode), base.description, base.immutable
        )
    return base


__all__ = [
    "ActionDefinition",
    "ActionMode",
    "DEFAULT_ACTIONS",
    "IMMUTABLE_SAFETY_ACTIONS",
    "get_action_definition",
]
