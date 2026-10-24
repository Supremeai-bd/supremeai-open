"""This module centralizes the definition of data models and static configuration for billing and subscription plans within the SupremeAI backend. It provides a standardized structure for initiating checkout requests and a comprehensive list of available subscription tiers, ensuring consistency across payment processing, user management, and feature access services.

Key Components:
- `CheckoutRequest`: A Pydantic model defining the required parameters for initiating a user checkout process for a specific billing plan.
- `SUBSCRIPTION_PLANS`: A constant dict keyed by plan name, each containing details like price, cost (Decimal), currency, interval, and included features.

Dependencies:
- `pydantic`: Used for defining `CheckoutRequest` to ensure robust data validation and serialization.

#1828 (single pricing source of truth): tier prices are LOADED from
`backend/config/pricing_tiers.json` (same file the quota enforcer reads), so
Stripe checkout catalog and quota allowances can never disagree again. Only
Stripe price IDs remain hardcoded here. Override the file path with the
`PRICING_TIERS_PATH` env var (mirrors scripts/billing/quota_enforcer.py).
"""

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel

from core.logging_config import logger


def _load_tier_prices() -> dict[str, Decimal]:
    """Load tier → monthly USD price from pricing_tiers.json (#1828).

    Missing/unreadable file → {} (callers fall back to the config defaults
    below so behavior stays deterministic). Never raises at import time.
    """
    default_path = Path(__file__).resolve().parents[2] / "config" / "pricing_tiers.json"
    path = Path(os.getenv("PRICING_TIERS_PATH") or default_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        tiers = data.get("tiers", {})
        return {
            str(tier): Decimal(str(cfg.get("monthly_credits_usd", 0)))
            for tier, cfg in tiers.items()
            if isinstance(cfg, dict)
        }
    except (OSError, ValueError, AttributeError) as exc:
        logger.warning(f"pricing_tiers.json unreadable ({exc}) — billing plans use fallback prices")
        return {}


# Fallbacks mirror backend/config/pricing_tiers.json defaults — used ONLY when
# the config file is missing/unreadable, so a broken deploy still bills predictably.
_FALLBACK_TIER_PRICES: dict[str, Decimal] = {
    "free": Decimal("0.00"),
    "pro": Decimal("10.00"),
    "enterprise": Decimal("100.00"),
}


def _tier_price(tier: str) -> Decimal:
    return _load_tier_prices_cache().get(tier, _FALLBACK_TIER_PRICES[tier])


def _load_tier_prices_cache() -> dict[str, Decimal]:
    global _TIER_PRICES
    if _TIER_PRICES is None:
        _TIER_PRICES = _load_tier_prices()
    return _TIER_PRICES


_TIER_PRICES: dict[str, Decimal] | None = None


class CheckoutRequest(BaseModel):
    price_id: str
    success_url: str
    cancel_url: str
    user_id: str | None = None


# বাংলা মন্তব্য: SubscriptionPlan dataclass — cost (Decimal) সহ সব tier-এর তথ্য।
# SUBSCRIPTION_PLANS dict কারণ tests `SUBSCRIPTION_PLANS["free"]` এভাবে access করে।
@dataclass
class SubscriptionPlan:
    id: str
    name: str
    price: float
    cost: Decimal
    currency: str
    interval: str
    features: list


SUBSCRIPTION_PLANS: dict[str, SubscriptionPlan] = {
    "free": SubscriptionPlan(
        id="price_free",
        name="Free Plan",
        price=float(_tier_price("free")),
        cost=_tier_price("free"),
        currency="usd",
        interval="month",
        features=["100 AI Credits", "Basic Models", "Community Support"],
    ),
    "pro": SubscriptionPlan(
        id="price_pro_monthly",
        name="Pro Plan",
        price=float(_tier_price("pro")),
        cost=_tier_price("pro"),
        currency="usd",
        interval="month",
        features=["1000 AI Credits", "Advanced Models", "Priority Support"],
    ),
    "enterprise": SubscriptionPlan(
        id="price_enterprise_monthly",
        name="Enterprise Plan",
        price=float(_tier_price("enterprise")),
        cost=_tier_price("enterprise"),
        currency="usd",
        interval="month",
        features=["Unlimited AI Credits", "Dedicated Account Manager", "Custom SLAs", "API Access"],
    ),
}

# বাংলা মন্তব্য: backward compatibility-র জন্য list format preserve করা হলো
SUBSCRIPTION_PLANS_LIST = [
    {
        "id": p.id,
        "name": p.name,
        "price": p.price,
        "currency": p.currency,
        "interval": p.interval,
        "features": p.features,
    }
    for p in SUBSCRIPTION_PLANS.values()
]
