"""
SupremeAI Automation Workflow Registry
========================================
বাংলা: Plan Section 5 অনুযায়ী metadata-driven workflow registry। প্রতিটি
workflow declare করে: key, route, enabled, timeout, max_retries, synchronous,
sensitive, version। এটি policy controls, retries, timeout, sync/async semantics,
sensitive-data rules, observability, UI metadata, versioning দেয়।

Backward-compat: AUTOMATION_REGISTRY (dict[str, str]) ও get_workflow_route()
এখনও কাজ করে — existing callers (n8n adapter, admin route) কোনো change ছাড়াই
কাজ চালিয়ে যাবে।
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class WorkflowDefinition:
    """
    Plan Section 5: একটি automation workflow-এর full metadata।

    বাংলা: আগে registry শুধু {key: route} dict ছিল। এখন প্রতিটি workflow
    তার policy (timeout, retries, sync/async, sensitive, enabled) সহ declare
    করে। এটি dispatcher ও adapter-কে এই policies enforce করতে দেয়।
    """

    key: str  # unique workflow key (e.g., 'USER_REGISTERED')
    route: str  # webhook path (e.g., '/webhook/user-registered')
    enabled: bool = True  # disabled হলে dispatch skip হবে
    timeout_seconds: int = 15  # per-attempt timeout
    max_retries: int = 3  # transient failure-এ retry count
    synchronous: bool = False  # True হলে caller result wait করে; False হলে fire-and-forget
    sensitive: bool = False  # True হলে payload-এ sensitive data (privacy mode apply)
    version: str = "1"  # workflow version (future migration)
    description: str = ""  # human-readable purpose


# ── Workflow definitions (Plan Section 5: metadata-driven) ──────────────────
# বাংলা: প্রতিটি workflow এখন তার policy সহ declare করা।
_WORKFLOW_DEFINITIONS: dict[str, WorkflowDefinition] = {
    "USER_REGISTERED": WorkflowDefinition(
        key="USER_REGISTERED",
        route="/webhook/user-registered",
        enabled=True,
        timeout_seconds=15,
        max_retries=3,
        synchronous=False,
        sensitive=False,  # user registration data — not highly sensitive
        description="Triggered when a new user registers. Sends welcome flow + onboarding.",
    ),
    "SECURITY_ALERT": WorkflowDefinition(
        key="SECURITY_ALERT",
        route="/webhook/security-alert",
        enabled=True,
        timeout_seconds=10,  # security alerts — fast timeout
        max_retries=5,  # security — more retries (don't lose alerts)
        synchronous=False,
        sensitive=True,  # may contain attack details — privacy mode apply
        description="Triggered on security incidents. High-retry to avoid losing alerts.",
    ),
    "HITL_REQUIRED": WorkflowDefinition(
        key="HITL_REQUIRED",
        route="/webhook/hitl-required",
        enabled=True,
        timeout_seconds=20,  # HITL — human-in-loop, may take longer
        max_retries=3,
        synchronous=False,
        sensitive=True,  # HITL payloads often contain user data
        description="Human-in-the-loop approval required. Sensitive payload.",
    ),
    "PAYMENT_SUCCESS": WorkflowDefinition(
        key="PAYMENT_SUCCESS",
        route="/webhook/payment-success",
        enabled=True,
        timeout_seconds=15,
        max_retries=5,  # payments — don't lose (revenue-critical)
        synchronous=False,
        sensitive=True,  # payment data — privacy mode apply
        description="Payment succeeded. Revenue-critical, high-retry.",
    ),
    "PAYMENT_FAILED": WorkflowDefinition(
        key="PAYMENT_FAILED",
        route="/webhook/payment-failed",
        enabled=True,
        timeout_seconds=15,
        max_retries=5,  # payments — don't lose (revenue-critical)
        synchronous=False,
        sensitive=True,
        description="Payment failed. Revenue-critical, high-retry.",
    ),
    "SYS_HEALTH_DEGRADED": WorkflowDefinition(
        key="SYS_HEALTH_DEGRADED",
        route="/webhook/sys-health-degraded",
        enabled=True,
        timeout_seconds=10,
        max_retries=3,
        synchronous=False,
        sensitive=False,  # health status — not sensitive
        description="System health degraded below threshold. Triggers ops alerting.",
    ),
}


# ── Backward-compat: AUTOMATION_REGISTRY as dict[str, str] ───────────────────
# বাংলা: আগে এটা {key: route} dict ছিল। এখন WorkflowDefinition থেকে derive
# হয়, কিন্তু existing callers (admin route) এখনও dict হিসেবে access করতে পারে।
AUTOMATION_REGISTRY: dict[str, str] = {key: wf.route for key, wf in _WORKFLOW_DEFINITIONS.items()}


# ── Public API ─────────────────────────────────────────────────────────────────


def is_valid_workflow(workflow_key: str) -> bool:
    """Check if the provided key is registered AND enabled."""
    wf = _WORKFLOW_DEFINITIONS.get(workflow_key)
    return wf is not None and wf.enabled


def get_workflow_route(workflow_key: str) -> str:
    """
    Get the target route for a registered workflow key.
    Backward-compat: returns the route string (same as before).
    """
    wf = _WORKFLOW_DEFINITIONS.get(workflow_key)
    if wf is None:
        raise ValueError(f"Unknown workflow key: {workflow_key}")
    return wf.route


def get_workflow_definition(workflow_key: str) -> WorkflowDefinition | None:
    """
    Plan Section 5: একটি workflow-এর full metadata পাওয়া।
    None হলে workflow নেই। enabled=False হলেও definition ফেরত দেয়
    (caller নিজে চেক করবে)।
    """
    return _WORKFLOW_DEFINITIONS.get(workflow_key)


def list_workflow_definitions() -> list[WorkflowDefinition]:
    """সব workflow definition-এর তালিকা (admin UI-এর জন্য)।"""
    return list(_WORKFLOW_DEFINITIONS.values())


def list_enabled_workflows() -> list[WorkflowDefinition]:
    """শুধু enabled workflow-গুলো (dispatcher-এর জন্য)।"""
    return [wf for wf in _WORKFLOW_DEFINITIONS.values() if wf.enabled]
