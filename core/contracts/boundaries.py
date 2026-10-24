"""Cross-domain boundary contracts for ``backend/core`` → brain / adaptive_engine.

বাংলা: এই মডিউলটি Phase-5 repo-separation (issue #126) এর public-interface
চুক্তি — ``backend/core`` যেসব brain/adaptive_engine ক্ষমতা consume করে সেগুলোর
typed Protocol। লক্ষ্য: ``backend/core`` কে ``brain``/``adaptive_engine`` ছাড়া
একটি স্বয়ংসম্পূর্ণ library হিসেবে চালানো যায় (PHASE0_BOUNDARY_CLASSIFICATION.md
§1 — core→brain 14 files, core→adaptive_engine 8 files)।

নির্ভরতা-নীতি (leaf চুক্তি):
- এই মডিউল শুধু stdlib/typing import করতে পারে — কোনো ``core.*``, ``brain.*``,
  ``adaptive_engine.*`` বা third-party runtime import নিষিদ্ধ
  (``tests/test_core_isolation.py`` এ AST guard দিয়ে মেশিন-প্রয়োগকৃত)।
- ``backend/core``-এর কোনো মডিউল **module-import-time**-এ brain/adaptive_engine
  import করতে পারবে না — ভোগের জায়গায় (use site) lazy import বাধ্যতামূলক
  (কোডবেসের প্রতিষ্ঠিত "Domain adapter (lazy import)" idiom — যেমন
  ``circles/centers/llm_center.py``)। DI সাইটগুলো এই Protocol দিয়ে annotate হয়।
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "AutonomousAgentContract",
    "ModelRegistryContract",
    "ModelRoutingContract",
    "ReasoningOrchestrationContract",
]


@runtime_checkable
class ModelRoutingContract(Protocol):
    """মডেল-রাউটিং ক্ষমতার চুক্তি (brain.model_router.ModelRouter সারফেস)।"""

    def route_and_generate(
        self, prompt: str, task_type: str = "general", *args: Any, **kwargs: Any
    ) -> str:
        """প্রম্পট রাউট করে generation ফেরত দেয়।"""
        ...

    async def async_route_and_generate(
        self, prompt: str, task_type: str = "general", *args: Any, **kwargs: Any
    ) -> str:
        """async রাউট+generation।"""
        ...


@runtime_checkable
class ReasoningOrchestrationContract(Protocol):
    """রিজনিং-অর্কেস্ট্রেশন ক্ষমতার চুক্তি (brain.reasoning_orchestrator সারফেস)।"""

    def route(self, task_description: str, context: str | None = None) -> Any:
        """টাস্ক-বর্ণনা রিজনিং-পাইপলাইনে রাউট করে।"""
        ...


@runtime_checkable
class AutonomousAgentContract(Protocol):
    """স্বায়ত্তশাসিত এজেন্ট এক্সিকিউশন চুক্তি (brain.autonomous_agent সারফেস)।"""

    def run(self, task_description: str, context: str | None = None) -> Any:
        """একটি টাস্ক রান করে ফলাফল ফেরত দেয়।"""
        ...


@runtime_checkable
class ModelRegistryContract(Protocol):
    """মডেল-রেজিস্ট্রি চুক্তি (brain.model_registry.ModelRegistry সারফেস)।"""

    MODELS: Mapping[str, Any]

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        """model_id দিয়ে মডেল-মেটাডেটা lookup।"""
        ...
