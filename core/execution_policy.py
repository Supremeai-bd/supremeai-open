"""Quota-aware, policy-compliant execution decisions.

This module deliberately never rotates credentials or keeps third-party notebooks
alive. It centralizes admission, degradation, and offload decisions so adapters
can remain small and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutionMode(StrEnum):
    CACHE = "cache"
    SERVER = "server"
    QUEUED = "queued"
    CLIENT = "client"
    BYOC = "byoc"
    RESEARCH = "research"
    UNAVAILABLE = "unavailable"


class TaskClass(StrEnum):
    LOCAL_SAFE = "local_safe"
    LIGHTWEIGHT = "lightweight"
    QUEUED_HEAVY = "queued_heavy"
    BROWSER_ONLY = "browser_only"
    PRIVATE_DATA = "private_data"
    RESEARCH = "research"


@dataclass(frozen=True)
class ProviderBudget:
    name: str
    remaining_ratio: float
    healthy: bool = True
    supports_task: bool = True
    authorized: bool = True


@dataclass(frozen=True)
class ExecutionDecision:
    mode: ExecutionMode
    provider: str | None
    reason: str
    degraded: bool = False


def choose_execution(
    task_class: TaskClass,
    *,
    cache_hit: bool = False,
    providers: tuple[ProviderBudget, ...] = (),
    client_available: bool = False,
    byoc_available: bool = False,
    urgent: bool = False,
) -> ExecutionDecision:
    """Choose the cheapest valid path without bypassing provider controls."""
    if cache_hit:
        return ExecutionDecision(ExecutionMode.CACHE, None, "cache_hit")

    if task_class is TaskClass.LOCAL_SAFE and client_available:
        return ExecutionDecision(ExecutionMode.CLIENT, None, "local_safe_client_execution")

    if task_class is TaskClass.PRIVATE_DATA and byoc_available:
        return ExecutionDecision(ExecutionMode.BYOC, None, "explicit_user_owned_execution")

    eligible = [
        p
        for p in providers
        if p.healthy and p.supports_task and p.authorized and p.remaining_ratio > 0
    ]
    eligible.sort(key=lambda p: p.remaining_ratio, reverse=True)
    if eligible:
        provider = eligible[0]
        degraded = provider.remaining_ratio < 0.30
        if task_class in (TaskClass.QUEUED_HEAVY, TaskClass.BROWSER_ONLY, TaskClass.RESEARCH):
            return ExecutionDecision(
                ExecutionMode.QUEUED, provider.name, "bounded_async_execution", degraded
            )
        return ExecutionDecision(
            ExecutionMode.SERVER, provider.name, "authorized_quota_available", degraded
        )

    if byoc_available and not urgent:
        return ExecutionDecision(ExecutionMode.BYOC, None, "provider_quota_exhausted")
    if task_class is TaskClass.RESEARCH:
        return ExecutionDecision(
            ExecutionMode.RESEARCH, None, "provider_supported_research_only", degraded=True
        )
    return ExecutionDecision(ExecutionMode.UNAVAILABLE, None, "no_authorized_capacity")


__all__ = ["ExecutionDecision", "ExecutionMode", "ProviderBudget", "TaskClass", "choose_execution"]
