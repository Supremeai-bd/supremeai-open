# backend/core/llm/llm_gateway/spend_meter.py
"""M16 P-A — UsageSettlement-lite: বাস্তব টোকেন-খরচের metering feed.

বাংলা মন্তব্য: এই মডিউলটি LLM Gateway-র completion ও streaming পথ থেকে
"বাস্তব খরচ" (provider-রিপোর্টেড usage × প্ল্যাটফর্মের ঘোষিত meter-rate) কে
বিদ্যমান ``CostGuard.record_spend`` পথে (Redis ``cost_guard:{tenant}:{tier}:spent``)
ফিড করে — যাতে /ws/cost-updates ও analytics আর চিরস্থায়ী $0 না দেখায়।

সততা-মতবাদ (V5/V6):
- কখনো বানানো সংখ্যা নয় — provider usage না পেলে কিছুই record করা হয় না,
  gap-টি দৃশ্যমান warning লগে জানানো হয়।
- rate হলো ``settings.llm_cost_per_token`` — pre-flight estimate ও token_deductor
  একই ঘোষিত হার ব্যবহার করে; এটি per-model pricing (M16 P-C) নয়, এক-হারের meter।
- metering ব্যর্থ হলে ব্যবহারকারীর inference কখনো fail করবে না (hot-path-বাইরে,
  fail-open-for-metering) — কিন্তু ব্যর্থতা নীরবে গিলে ফেলা হয় না, loguru error যায়।
"""

from __future__ import annotations

import math
from typing import Any

from core.logging_config import logger  # loguru logger (monitoring.logging_config shim)


def _finite_non_negative(value: Any) -> float | None:
    """Return the value as float when it is a finite, non-negative number; else None."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num) or num < 0:
        return None
    return num


def resolve_metered_spend(
    *,
    usage: dict[str, Any] | None,
    actual_cost: float | None,
) -> tuple[float, str] | None:
    """Resolve the honest spend amount + accounting basis from provider response data.

    বাংলা মন্তব্য: ফেরত None মানে "সত্যিকারে কিছু জানা নেই" — কিছু রেকর্ড করা হবে না।
    basis "provider-usage" মানে provider-রিপোর্টেড টোকেন × ঘোষিত meter-rate;
    basis "provider-cost" মানে provider নিজেই যে actual cost দিয়েছে।
    """
    prompt_tokens = _finite_non_negative((usage or {}).get("prompt_tokens"))
    completion_tokens = _finite_non_negative((usage or {}).get("completion_tokens"))
    if prompt_tokens is not None and completion_tokens is not None:
        from core.config import settings  # lazy — re-import-proof (token_deductor pattern)

        rate = _finite_non_negative(getattr(settings, "llm_cost_per_token", None)) or 0.0
        tokens = prompt_tokens + completion_tokens
        return tokens * rate, "provider-usage"

    if actual_cost is not None:
        cost = _finite_non_negative(actual_cost)
        if cost is not None and cost > 0:
            return cost, "provider-cost"

    return None


def get_cost_guard() -> Any:
    """Resolver seam for tests — returns the CostGuard singleton used for metering."""
    from core.cost_guard import cost_guard

    return cost_guard


async def settle_gateway_spend(
    *,
    tenant_id: str | None,
    tier: str | None,
    model: str,
    task_type: str,
    path: str,
    usage: dict[str, Any] | None = None,
    actual_cost: float | None = None,
) -> None:
    """Record actual token spend into the existing billing meter (CostGuard Redis counter).

    বাংলা মন্তব্য: এটি inference-এর সাফল্য-পথে ডাকা হয়; কোনো অবস্থায় ব্যতিক্রম
    inference-এ ছড়াবে না (best-effort metering) — কিন্তু প্রতিটি ব্যর্থতা/gap
    দৃশ্যমানভাবে লগ হয়, কখনো নীরবে চাপা পড়ে না।
    """
    if not tenant_id:
        # বাংলা মন্তব্য: tenant না জানা গেলে খরচ কার হিসাবে রাখব না — জালভাবে
        # "unknown"-এ ভাগ করার বদলে gap দৃশ্যমান warning হিসেবে জানানো হচ্ছে
        # (M16 P-A-র ন্যূনতম সৎ আচরণ: log + skip with visible warning)।
        logger.warning(
            f"[SpendMeter] spend NOT metered — tenant unresolved | path={path} | "
            f"model={model} | task_type={task_type} | reason=tenant_id-missing"
        )
        return

    resolved = resolve_metered_spend(usage=usage, actual_cost=actual_cost)
    if resolved is None:
        # বাংলা মন্তব্য: provider usage/cost দেয়নি — বানানো সংখ্যা রেকর্ড করা মতবাদ-
        # লঙ্ঘন; gap-টি স্পষ্টভাবে লগ করা হলো যেন অদৃশ্য খরচ লুকিয়ে থাকে না।
        logger.warning(
            f"[SpendMeter] spend NOT metered — usage unavailable from provider | path={path} | "
            f"model={model} | task_type={task_type} | tenant={tenant_id} | reason=no-usage-data"
        )
        return

    spend, basis = resolved
    if spend <= 0.0:
        # বাংলা মন্তব্য: 0 টোকেন/0 খরচ সত্যিই শূন্য (যেমন সম্পূর্ণ cache/local) —
        # এটি gap নয়, তাই warning নয়; শুধু ট্রেস-স্তরের নোট।
        logger.debug(
            f"[SpendMeter] zero-cost call — nothing to meter | path={path} | model={model} | "
            f"tenant={tenant_id} | basis={basis}"
        )
        return

    tier_label = (tier or "unknown").strip() or "unknown"
    try:
        guard = get_cost_guard()
        await guard.record_spend(tenant_id, tier_label, spend)
        logger.info(
            f"[SpendMeter] spend metered | tenant={tenant_id} | tier={tier_label} | "
            f"spend=${spend:.6f} | basis={basis} | model={model} | task_type={task_type} | path={path}"
        )
    except Exception as meter_err:
        # বাংলা মন্তব্য: metering ব্যর্থতা inference ভাঙবে না (ব্যবহারকারী ইতোমধ্যে
        # সেবা পেয়েছে; fail-open-for-metering) — কিন্তু নীরব হারানো খরচ নিষিদ্ধ,
        # তাই error লগ + CostGuard-এর নিজস্ব event-bus emit-ও থাকে।
        logger.error(
            f"[SpendMeter] record_spend FAILED — spend lost from dashboards | "
            f"tenant={tenant_id} | tier={tier_label} | spend=${spend:.6f} | path={path} | "
            f"model={model} | error={meter_err}"
        )
