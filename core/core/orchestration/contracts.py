"""Leaf contracts for the chat-centered hub-and-spoke control plane.

Issue #2476 (cycle breaks): এই মডিউলটি orchestration control plane-এর shared
dataclass চুক্তিগুলোর নির্ভরতামুক্ত (leaf) ঘর। আগে
``conversation_orchestrator`` (hub) নিজেই এই টাইপগুলোর মালিক ছিল, ফলে
spoke মডিউলগুলোর (``capability_adapters``, ``execution_recorder``) টাইপ
পেতে hub-কে import করতে হতো — অথচ hub নিজে spoke-দের lazily import করে
(Handler-registration)। এই দুইমুখী নির্ভরতাই AST-স্ক্যানে ২টি cycle
হিসেবে ধরা পড়ত এবং import-order-নির্ভর boot-failure ঝুঁকি তৈরি করত।

এখন hub ও spoke সবাই টাইপ নেয় একমুখীভাবে এই leaf থেকে — কোনো cycle নেই।
``conversation_orchestrator`` নিজ নেমস্পেসে এই নামগুলো re-export করে
রেখেছে, তাই বিদ্যমান consumer-দের import পথ অপরিবর্তিত থাকে।

নির্ভরতা-নীতি: এই মডিউল শুধুমাত্র leaf মডিউল import করতে পারে
(বর্তমানে ``core.automation.models`` — pydantic/stdlib-only leaf)।
কোনো hub/spoke/runtime মডিউল এখানে import করা নিষিদ্ধ।
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from core.automation.models import ExecutionEnvelope


@dataclass(frozen=True)
class ConversationCommand:
    prompt: str
    user_id: str
    tenant_id: str
    role: str = "user"
    project_id: str | None = None
    conversation_id: str | None = None
    confirmation: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionRecord:
    """Canonical, serializable truth record for one governed dispatch."""

    execution_id: str
    correlation_id: str
    user_id: str
    tenant_id: str
    project_id: str | None
    conversation_id: str | None
    capability: str
    status: str = "started"
    evidence: list[dict[str, Any]] = field(default_factory=list)
    envelope: ExecutionEnvelope | None = None


@dataclass
class OrchestrationResult:
    correlation_id: str
    status: str
    capability: str
    response: Any = None
    requires_confirmation: bool = False
    task_id: str | None = None
    error: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    execution: ExecutionRecord | None = None


@dataclass(frozen=True)
class Capability:
    name: str
    risk: str
    handler: Callable[[ConversationCommand], Awaitable[Any]]
    admin_only: bool = False
    destructive: bool = False
    # A registered handler is not automatically proof of a live dependency.
    availability: str = "connected"
    description: str = ""

    @property
    def is_available(self) -> bool:
        return self.availability == "connected"


__all__ = [
    "Capability",
    "ConversationCommand",
    "ExecutionRecord",
    "OrchestrationResult",
]
