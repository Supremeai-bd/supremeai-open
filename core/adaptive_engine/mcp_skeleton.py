"""MCP Skeleton — generic control operation, NOT a god object (ROADMAP §45, §46).

বাংলা: ROADMAP §45 — MCP হল ecosystem-এর interface, ecosystem নিজে নয়। এটা
high-level capability expose করে: Observe / Analyze / Act।

ROADMAP §46 — MCP-তে 500 provider-specific function ঢুকিয়ে god object বানানো যাবে না।
সঠিক পথ:
  MCP → generic control operation → resource registry → provider adapter।

এটি শুধু foundation skeleton — ভবিষ্যতে MCP client (Claude Desktop / IDE) এই
operations-গুলোকে কল করবে।
"""

from __future__ import annotations

import enum
from typing import Any

from adaptive_engine._store import jdump
from adaptive_engine.capability_registry import get_capability_registry
from adaptive_engine.correlation import current_correlation
from adaptive_engine.deployment_tracker import get_deployment_tracker
from adaptive_engine.governance import ActionRisk, get_governance_engine
from adaptive_engine.health_model import get_health_aggregator
from adaptive_engine.resource_registry import get_resource_registry


class MCPOperationCategory(enum.StrEnum):
    """ROADMAP §45 — three operation families."""

    OBSERVE = "observe"  # read-only
    ANALYZE = "analyze"  # inference / correlation
    ACT = "act"  # mutating — governance-gated


class MCPOperationError(RuntimeError):
    """Base error for MCP operations."""


class MCPOperationNotRegisteredError(KeyError):
    """Raised when an operation is not registered in the MCP skeleton."""


class MCPActionDenied(PermissionError):
    """Raised when an action is denied by governance."""


# বাংলা: ROADMAP §45 — MCP-তে expose হওয়া high-level operations।
_OBSERVE_OPS = {
    "list_resources",
    "get_resource",
    "get_health",
    "get_metrics",
    "get_logs",
    "get_deployment",
    "get_task_status",
    "get_capabilities",
    "get_kaggle_quota",
}

_ANALYZE_OPS = {
    "find_capability",
    "detect_capability_gap",
    "forecast_capability",
    "trace_dependency",
    "correlate_error",
    "analyze_resource_usage",
}

_ACT_OPS = {
    "create_capability",
    "activate_capability",
    "archive_capability",
    "restart",
    "deploy",
    "rollback",
    "trigger_job",
    "trigger_kaggle",
    "create_github_pr",
}


class MCPSkeleton:
    """Single stable MCP surface over the ecosystem (ROADMAP §45, §46)."""

    def __init__(self) -> None:
        self._resources = get_resource_registry()
        self._caps = get_capability_registry()
        self._health = get_health_aggregator()
        self._deployments = get_deployment_tracker()
        self._gov = get_governance_engine()

    # -- public dispatch ---------------------------------------------------

    async def call(
        self, operation: str, *, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Single generic entry point. Dispatches to the right subsystem."""
        args = arguments or {}
        category = self._category_of(operation)
        if category is None:
            return {"ok": False, "error": "unknown_operation", "operation": operation}

        # ROADMAP §28 — ACT ops go through governance + correlation
        if category == MCPOperationCategory.ACT:
            decision = self._gov.authorize(
                operation,
                scope=args.get("scope", "global"),
                scope_value=args.get("scope_value", "global"),
                context=args,
                correlation=current_correlation().as_headers(),
            )
            if not decision.allowed:
                return {
                    "ok": False,
                    "error": "denied_by_governance",
                    "reason": decision.reason,
                    "risk": decision.risk,
                    "requires_approval": decision.requires_approval,
                }
            if decision.requires_approval:
                return {
                    "ok": False,
                    "error": "approval_required",
                    "risk": decision.risk,
                    "requires_approval": True,
                    "hint": "Submit via /api/v1/ecosystem/admin/proposals first.",
                }

        # dispatch to handler
        handler = getattr(self, f"_op_{operation}", None)
        if handler is None:
            return {"ok": False, "error": "operation_not_implemented", "operation": operation}
        try:
            result = await handler(args)
        except Exception as exc:  # noqa: BLE001 — MCP must never crash a caller
            return {"ok": False, "error": "handler_error", "detail": str(exc)}
        return {"ok": True, "operation": operation, "category": category, "result": result}

    # -- observe handlers --------------------------------------------------

    async def _op_list_resources(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self._resources.list(
            provider=args.get("provider"),
            environment=args.get("environment"),
            limit=int(args.get("limit", 200)),
        )
        return [r.model_dump() for r in rows]

    async def _op_get_resource(self, args: dict[str, Any]) -> dict[str, Any] | None:
        r = self._resources.get(args["resource_id"])
        return r.model_dump() if r else None

    async def _op_get_health(self, args: dict[str, Any]) -> Any:
        """ROADMAP §41 — if a real adapter is registered, call it live; else
        return the last stored snapshot. If neither exists, return None."""
        if args.get("resource_id"):
            # Try the live adapter first (ROADMAP §37 — generic control op).
            live = await self._resources.control(args["resource_id"], "get_health")
            if live.get("ok"):
                return live.get("result")
            # Fall back to the stored snapshot.
            h = self._health.latest(args["resource_id"])
            return h.model_dump() if h else None
        return {
            "composite": str(self._health.composite_status()),
            "resources": [h.model_dump() for h in self._health.all_latest()],
        }

    async def _op_get_metrics(self, args: dict[str, Any]) -> dict[str, Any]:
        resource_id = args["resource_id"]
        # generic dispatch to the registered adapter's get_metrics
        return await self._resources.control(resource_id, "get_metrics")

    async def _op_get_logs(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._resources.control(
            args["resource_id"],
            "get_logs",
            payload={"limit": int(args.get("limit", 100)), "level": args.get("level")},
        )

    async def _op_get_deployment(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        deps = self._deployments.list_by_resource(
            args["resource_id"], limit=int(args.get("limit", 20))
        )
        return [d.model_dump() for d in deps]

    async def _op_get_capabilities(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        from adaptive_engine.capability_registry import CapabilityLifecycleState

        state = args.get("state")
        caps = self._caps.list(
            state=CapabilityLifecycleState(state) if state else None,
            category=args.get("category"),
            limit=int(args.get("limit", 200)),
        )
        return [c.model_dump() for c in caps]

    async def _op_get_task_status(
        self, args: dict[str, Any]
    ) -> dict[str, Any] | list[dict[str, Any]]:
        from adaptive_engine.task_engine import get_task_engine

        if args.get("task_id"):
            t = get_task_engine().get(args["task_id"])
            return t.model_dump() if t else None
        tasks = get_task_engine().list(limit=int(args.get("limit", 50)))
        return [t.model_dump() for t in tasks]

    async def _op_get_kaggle_quota(self, args: dict[str, Any]) -> dict[str, Any]:
        # ROADMAP §35 — N nodes abstraction; admin never picks account manually.
        kaggle = self._resources.list(provider="kaggle", limit=50)
        return {
            "accounts_registered": len(kaggle),
            "accounts": [
                {"resource_id": k.resource_id, "state": k.state, "name": k.name} for k in kaggle
            ],
        }

    # -- analyze handlers --------------------------------------------------

    async def _op_find_capability(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        caps = self._caps.search_for_requirement(
            args["requirement"],
            signature_hint=args.get("signature_hint"),
            category_hint=args.get("category_hint"),
            limit=int(args.get("limit", 10)),
        )
        return [c.model_dump() for c in caps]

    async def _op_detect_capability_gap(self, args: dict[str, Any]) -> dict[str, Any]:
        """ROADMAP §14, §25 — search existing capabilities before creating new."""
        matches = self._caps.search_for_requirement(args["requirement"], limit=5)
        return {
            "requirement": args["requirement"],
            "gap_detected": len(matches) == 0,
            "candidates": [c.model_dump() for c in matches],
            "rule": "REUSE > ADAPT > EXTEND > CREATE",
        }

    async def _op_forecast_capability(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"forecast": "stub", "signal": args.get("signal"), "note": "later phase"}

    async def _op_trace_dependency(self, args: dict[str, Any]) -> dict[str, Any]:
        """ROADMAP §39 — User → Task → Capability → Resource → Deployment graph."""
        out: dict[str, Any] = {"task_id": args.get("task_id")}
        if args.get("task_id"):
            from adaptive_engine.task_engine import get_task_engine

            t = get_task_engine().get(args["task_id"])
            if t:
                out["task"] = t.model_dump()
                if t.capability_id:
                    out["capability"] = (
                        self._caps.get(t.capability_id).model_dump()
                        if self._caps.get(t.capability_id)
                        else None
                    )
                if t.resource_id:
                    out["resource"] = (
                        self._resources.get(t.resource_id).model_dump()
                        if self._resources.get(t.resource_id)
                        else None
                    )
                    if out["resource"]:
                        out["deployments"] = [
                            d.model_dump()
                            for d in self._deployments.list_by_resource(t.resource_id)
                        ]
        return out

    async def _op_correlate_error(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"error_ref": args.get("error_ref"), "correlations": [], "note": "stub"}

    async def _op_analyze_resource_usage(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "composite_status": str(self._health.composite_status()),
            "top_memory": [h.model_dump() for h in self._health.top_memory_consumers(5)],
        }

    # -- act handlers (governance-gated above) ------------------------------

    async def _op_restart(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._resources.control(args["resource_id"], "restart")

    async def _op_deploy(self, args: dict[str, Any]) -> dict[str, Any]:
        rec = self._deployments.start(
            resource_id=args["resource_id"],
            repository=args["repository"],
            commit_sha=args.get("commit_sha"),
            image_digest=args.get("image_digest"),
            environment=args.get("environment", "production"),
            triggered_by=args.get("triggered_by", "mcp"),
        )
        return rec.model_dump()

    async def _op_rollback(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._resources.control(
            args["resource_id"], "rollback", payload={"deployment_id": args["deployment_id"]}
        )

    async def _op_archive_capability(self, args: dict[str, Any]) -> dict[str, Any]:
        cap = self._caps.archive(args["capability_id"], actor=args.get("actor", "mcp"))
        return cap.model_dump()

    async def _op_activate_capability(self, args: dict[str, Any]) -> dict[str, Any]:
        from adaptive_engine.capability_registry import CapabilityLifecycleState

        cap = self._caps.transition(
            args["capability_id"],
            CapabilityLifecycleState.ACTIVE,
            actor=args.get("actor", "mcp"),
        )
        return cap.model_dump()

    # বাংলা: বাকি ACT ops (create_capability, trigger_job, trigger_kaggle,
    # create_github_pr) পরবর্তী phase-এ যুক্ত হবে — এখানে stub রাখা হলো যাতে
    # MCP surface স্থিতিশীল থাকে।

    async def _op_create_capability(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": False,
            "error": "use_proposal_endpoint",
            "hint": "POST /api/v1/ecosystem/admin/proposals",
        }

    async def _op_trigger_job(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._resources.control(args["resource_id"], "trigger_job")

    async def _op_trigger_kaggle(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._resources.control(args["resource_id"], "trigger_kaggle")

    async def _op_create_github_pr(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._resources.control(args["resource_id"], "create_pr")

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _category_of(operation: str) -> MCPOperationCategory | None:
        if operation in _OBSERVE_OPS:
            return MCPOperationCategory.OBSERVE
        if operation in _ANALYZE_OPS:
            return MCPOperationCategory.ANALYZE
        if operation in _ACT_OPS:
            return MCPOperationCategory.ACT
        return None

    def manifest(self) -> dict[str, Any]:
        """ROADMAP §45 — expose the high-level capability list to MCP clients."""
        return {
            "observe": sorted(_OBSERVE_OPS),
            "analyze": sorted(_ANALYZE_OPS),
            "act": sorted(_ACT_OPS),
            "note": "Mutating ACT operations are governance-gated (ROADMAP §28).",
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_mcp: MCPSkeleton | None = None


def get_mcp_skeleton() -> MCPSkeleton:
    global _mcp
    if _mcp is None:
        _mcp = MCPSkeleton()
    return _mcp


__all__ = [
    "MCPOperationCategory",
    "MCPSkeleton",
    "get_mcp_skeleton",
    "MCPOperationError",
    "MCPOperationNotRegisteredError",
    "MCPActionDenied",
]
