"""core.tool_loop — governed tool-execution loop (M09 P-A).

বাংলা: ``ReasoningOrchestrator.decide()`` এখন পর্যন্ত শুধু *সিদ্ধান্ত*
ফেরত দিত — কোনো টুল সত্যিই চলত না (decision-without-execution)। এই মডিউল
সেই অর্ধেক সম্পূর্ণ করে: প্রতিটি নির্বাচিত টুল কল তিনটি গেট পার হয়ে
নির্বাহ হয় —

1. **ফ্ল্যাগ-গেট** — ``SUPREMEAI_AGENT_TOOLS=true`` না থাকলে কিছুই চলে না
   (default OFF, fail-safe; অজানা মানও OFF);
2. **রেজিস্ট্রি-গেট** — শুধু ``tools.agent_tools.SUPREME_TOOLS``-এর সদস্য
   চলতে পারে; অজানা টুল = সৎ ``unknown_tool`` ব্যর্থতা;
3. **পলিসি-গেট** — ``core.mcp_policy.evaluate_tool`` (R0 → ALLOW,
   R5 → REQUIRE_APPROVAL); অনুমোদন-বিহীন ঝুঁকি-টুল চলে না, সৎ
   ``policy_blocked`` অবস্থা ফেরত যায় (P-B-তে HITL-hook যুক্ত হবে)।

কোনো স্তরেই নীরব ভান নেই — প্রতিটি ফলাফলে স্পষ্ট ``status`` থাকে।
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

from core.logging_config import logger
from core.mcp_policy import evaluate_tool

#: প্রতি-টুল প্রাথমিক প্যারামিটার-নাম — deterministic fallback
#: ``{"target": task}`` আকৃতিটিকে টুলের প্রকৃত সিগনেচারে ম্যাপ করত।
_PRIMARY_ARG: dict[str, str] = {
    "search_database": "query",
    "execute_python_code": "code",
}

#: বাংলা (M09 P-G): বহু-প্যারামিটার টুল — নাম-মিল কেবল জানা কীগুলোর,
#: অতিরিক্ত কী পাস হয় না (গভর্নড পৃষ্ঠ)।
_MULTI_ARG: dict[str, tuple[str, ...]] = {
    "cot_verify_math": ("expression", "claimed_result"),
}


def agent_tools_enabled() -> bool:
    """Flag-gate: ``SUPREMEAI_AGENT_TOOLS=true`` হলেই কেবল সত্য (default OFF)।"""
    return os.environ.get("SUPREMEAI_AGENT_TOOLS", "").strip().lower() == "true"


def tool_registry() -> dict[str, Callable[..., Any]]:
    """নাম → কলযোগ্য ম্যাপ — কেবল governed রেজিস্ট্রি-সদস্যই নির্বাহযোগ্য।

    বাংলা (M09 P-G): ``governed_tools()`` flag-off-এ SUPREME_TOOLS-এর
    প্রতিলিপি (আজকের আচরণ), flag-on-এ প্রথম-ফ্লিট টুল যুক্ত হয়।
    """
    from tools.agent_tools import governed_tools

    return {fn.__name__: fn for fn in governed_tools()}


def _resolve_call_args(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """LLM/fallback-args-কে টুল-সিগনেচারে নিরাপদে ম্যাপ করা।"""
    multi = _MULTI_ARG.get(tool)
    if multi is not None:
        return {k: str(args[k]) for k in multi if k in (args or {})}
    param = _PRIMARY_ARG.get(tool)
    if param is None:
        # check_system_health — বিধানহীন টুল।
        return {}
    if param in (args or {}):
        return {param: args[param]}
    target = (args or {}).get("target") or (args or {}).get(param)
    return {param: str(target)} if target else {param: ""}


async def execute_tool_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Execute one ReAct tool decision through all three governance gates.

    বাংলা: রিটার্ন-চুক্তি — ``{"tool", "executed": bool, "status", ...}``;
    ``executed=True`` মানে টুল সত্যিই চলেছে এবং ``observation`` এ প্রকৃত
    আউটপুট; বাকি সব ক্ষেত্রে স্পষ্ট কারণ।

    M06 P-A (৮/৮ RunType adoption): প্রতিটি গভর্নড টুল-নির্বাহ ক্যানোনিকাল
    ``run_type="tool"`` রান হিসেবেও পর্যবেক্ষিত (flag-gated, best-effort —
    রান-ফ্যাব্রিক ব্যর্থতা টুল-নির্বাহ কখনো ব্লক করে না)।
    """
    from runs.run_scope import observe_run

    tool_name = str((decision or {}).get("tool", "done"))
    async with observe_run(
        run_type="tool",
        title=f"tool:{tool_name}",
        source_type="tool",
        source_ref=tool_name,
    ) as run_ctx:
        result = await _execute_tool_decision_gated(decision)
        if run_ctx is not None:
            # বাংলা: বাস্তব ব্যর্থতা কেবল execution-error; gate-refusal (disabled/
            # unknown/policy_blocked) নির্বাহ-অনুপস্থিতি — সেটি failed নয়।
            run_ctx.finish("failed" if result.get("status") == "error" else "succeeded")
        return result


async def _execute_tool_decision_gated(decision: dict[str, Any]) -> dict[str, Any]:
    tool = str((decision or {}).get("tool", "done"))
    base: dict[str, Any] = {
        "tool": tool,
        "decision_source": (decision or {}).get("source", "unknown"),
    }

    if not agent_tools_enabled():
        logger.debug("[tool_loop] disabled (SUPREMEAI_AGENT_TOOLS!=true) — no execution")
        return {
            **base,
            "executed": False,
            "status": "disabled",
            "reason": "SUPREMEAI_AGENT_TOOLS != true — governed tool execution is OFF (fail-safe)",
        }

    if tool == "done":
        return {**base, "executed": False, "status": "done"}

    registry = tool_registry()
    if tool not in registry:
        return {
            **base,
            "executed": False,
            "status": "unknown_tool",
            "reason": f"tool '{tool}' is not in the governed SUPREME_TOOLS registry",
        }

    policy_decision, risk = evaluate_tool(tool)
    if policy_decision != "ALLOW":
        logger.warning(
            f"[tool_loop] {tool} blocked by policy (risk={risk}, decision={policy_decision})"
        )
        return {
            **base,
            "executed": False,
            "status": "policy_blocked",
            "policy": policy_decision,
            "risk": risk,
            "reason": f"policy decision '{policy_decision}' (risk {risk}) — human approval required",
        }

    fn = registry[tool]
    call_args = _resolve_call_args(tool, decision.get("args") or {})
    try:
        if asyncio.iscoroutinefunction(fn):
            observation = await fn(**call_args)
        else:
            observation = fn(**call_args)
    except Exception as exc:
        logger.error(f"[tool_loop] {tool} execution failed: {type(exc).__name__}: {exc}")
        return {
            **base,
            "executed": False,
            "status": "error",
            "policy": policy_decision,
            "risk": risk,
            "error": f"{type(exc).__name__}: {exc}",
        }

    logger.info(
        f"[tool_loop] {tool} executed (risk={risk}) — observation len={len(str(observation))}"
    )
    return {
        **base,
        "executed": True,
        "status": "ok",
        "policy": policy_decision,
        "risk": risk,
        "observation": str(observation),
    }
