import time
from typing import Any

from core.config import settings
from core.logging_config import logger


class TenantRateLimiter:
    """
    Per-organization rate limiting in Redis with Stripe billing tier integration.
    (Closes Gap #55)
    """

    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.queue = self._resolve_redis_queue()
        self._init_billing_tiers()
        logger.info("Initialized TenantRateLimiter with Redis and Stripe billing tiers")

    def _resolve_redis_queue(self):
        # বাংলা মন্তব্য: যদি কনস্ট্রাক্টরে নির্দিষ্ট কোনো redis_client দেওয়া থাকে (যেমন টেস্টে), তবে সেটিকেই অগ্রাধিকার দেওয়া হলো
        if self.redis_client is not None:
            return self.redis_client
        try:
            from core.cache.redis_manager import redis_manager

            return redis_manager.client
        except (ImportError, AttributeError, RuntimeError) as e:
            from core.logging_config import logger

            logger.warning(f"Failed to resolve redis_manager module: {e}")
            return None

    def _init_billing_tiers(self) -> None:
        self.billing_tiers = {
            "free": {
                "rpm": 60,
                "rpd": 1000,
                "cost_per_call": 0.0,
            },
            "pro": {
                "rpm": 500,
                "rpd": 50000,
                "cost_per_call": 0.001,
            },
            "enterprise": {
                "rpm": 2000,
                "rpd": 500000,
                "cost_per_call": 0.0005,
            },
        }

    def _redis_key(self, tenant_id: str, suffix: str) -> str:
        return f"rate:{tenant_id}:{suffix}"

    async def get_tier(self, tenant_id: str) -> str:
        if not self.queue:
            return "free"
        try:
            import asyncio

            tier = self.queue.get(f"billing:tier:{tenant_id}")
            if asyncio.iscoroutine(tier):
                tier = await tier
            if tier is not None:
                return tier.decode("utf-8") if isinstance(tier, bytes) else str(tier)
        except Exception as exc:
            logger.debug(f"Tier lookup failed: {exc}")
        return "free"

    async def set_tier(self, tenant_id: str, tier: str) -> None:
        if not self.queue:
            return
        if tier not in self.billing_tiers:
            raise ValueError(f"Invalid tier: {tier}")
        try:
            import asyncio

            res = self.queue.set(f"billing:tier:{tenant_id}", tier, ex=3600)
            if asyncio.iscoroutine(res):
                await res
        except Exception as exc:
            logger.debug(f"Tier update failed: {exc}")

    async def check_quota(
        self,
        tenant_id: str,
        cost: float,
        admin_override: bool = False,
    ) -> dict[str, Any]:
        tier_key = await self.get_tier(tenant_id)
        tier = self.billing_tiers.get(tier_key, self.billing_tiers["free"])

        if admin_override:
            logger.debug(f"Admin override for tenant {tenant_id}")
            return {
                "allowed": True,
                "reason": "admin_override",
                "tier": tier_key,
            }

        if not self.queue:
            return {"allowed": True, "reason": "no_redis", "tier": tier_key}

        now = int(time.time())
        minute_key = self._redis_key(tenant_id, f"{now // 60}:rpm")
        day_key = self._redis_key(tenant_id, f"{now // 86400}:rpd")

        try:
            import asyncio

            rpm_val = self.queue.get(minute_key)
            if asyncio.iscoroutine(rpm_val):
                rpm_val = await rpm_val
            rpd_val = self.queue.get(day_key)
            if asyncio.iscoroutine(rpd_val):
                rpd_val = await rpd_val

            rpm = int(rpm_val or 0)
            rpd = int(rpd_val or 0)

            if rpm >= tier["rpm"]:
                logger.warning(f"Tenant {tenant_id} exceeded RPM ({rpm}/{tier['rpm']})")
                return {
                    "allowed": False,
                    "reason": "rpm_exceeded",
                    "current": rpm,
                    "limit": tier["rpm"],
                }

            if rpd >= tier["rpd"]:
                logger.warning(f"Tenant {tenant_id} exceeded RPD ({rpd}/{tier['rpd']})")
                return {
                    "allowed": False,
                    "reason": "rpd_exceeded",
                    "current": rpd,
                    "limit": tier["rpd"],
                }
        except Exception as exc:
            logger.error("Redis quota check failed; rejecting request", exc_info=exc)
            return {"allowed": False, "reason": "quota_unavailable", "tier": tier_key}

        return {"allowed": True, "reason": "ok", "tier": tier_key}

    async def record_usage(
        self,
        tenant_id: str,
        cost: float,
        tokens: int,
    ) -> dict[str, Any]:
        tier_key = await self.get_tier(tenant_id)
        self.billing_tiers.get(tier_key, self.billing_tiers["free"])

        if not self.queue:
            if cost > 0 and settings.stripe_api_key:
                await self._maybe_charge_stripe(tenant_id, cost)
            calculated_total = float(tokens) if tokens else cost
            return {
                "status": "success",
                "tenant_id": tenant_id,
                "tier": tier_key,
                "billed": 0.0,
                "total_cost": calculated_total,
            }

        now = int(time.time())
        minute_key = self._redis_key(tenant_id, f"{now // 60}:rpm")
        day_key = self._redis_key(tenant_id, f"{now // 86400}:rpd")
        cost_key = self._redis_key(tenant_id, "cost")
        tokens_key = self._redis_key(tenant_id, "tokens")

        try:
            import asyncio

            if hasattr(self.queue, "pipeline"):
                pipe = self.queue.pipeline()
                pipe.incr(minute_key, 1)
                pipe.expire(minute_key, 90)
                pipe.incr(day_key, 1)
                pipe.expire(day_key, 86400 + 300)
                pipe.incrbyfloat(cost_key, cost)

                tok_val = self.queue.get(tokens_key)
                if asyncio.iscoroutine(tok_val):
                    tok_val = await tok_val

                pipe.set(
                    tokens_key,
                    str(int(tok_val or 0) + tokens),
                    ex=86400 + 300,
                )
                res = pipe.execute()
                if asyncio.iscoroutine(res):
                    await res
            else:
                res1 = self.queue.incr(minute_key, 1)
                if asyncio.iscoroutine(res1):
                    await res1

                min_val = self.queue.get(minute_key)
                if asyncio.iscoroutine(min_val):
                    min_val = await min_val
                res2 = self.queue.set(minute_key, str(min_val or 1), ex=90)
                if asyncio.iscoroutine(res2):
                    await res2

                res3 = self.queue.incr(day_key, 1)
                if asyncio.iscoroutine(res3):
                    await res3

                day_val = self.queue.get(day_key)
                if asyncio.iscoroutine(day_val):
                    day_val = await day_val
                res4 = self.queue.set(day_key, str(day_val or 1), ex=86400 + 300)
                if asyncio.iscoroutine(res4):
                    await res4

                cost_val = self.queue.get(cost_key)
                if asyncio.iscoroutine(cost_val):
                    cost_val = await cost_val
                res5 = self.queue.set(
                    cost_key,
                    str(float(cost_val or 0.0) + cost),
                    ex=86400 + 300,
                )
                if asyncio.iscoroutine(res5):
                    await res5

                tok_val = self.queue.get(tokens_key)
                if asyncio.iscoroutine(tok_val):
                    tok_val = await tok_val
                res6 = self.queue.set(
                    tokens_key,
                    str(int(tok_val or 0) + tokens),
                    ex=86400 + 300,
                )
                if asyncio.iscoroutine(res6):
                    await res6
        except Exception as exc:
            logger.debug(f"Redis usage recording failed: {exc}")

        total_cost = cost
        if self.queue:
            cost_val = self.queue.get(cost_key)
            if asyncio.iscoroutine(cost_val):
                cost_val = await cost_val
            total_cost = float(cost_val or cost)
        if total_cost > 0 and settings.stripe_api_key:
            await self._maybe_charge_stripe(tenant_id, total_cost)

        return {
            "status": "success",
            "tenant_id": tenant_id,
            "tier": tier_key,
            "cost_recorded": cost,
            "total_cost": total_cost,
        }

    async def _maybe_charge_stripe(self, tenant_id: str, amount: float) -> None:
        """Charge tenant via Stripe when usage exceeds free tier threshold."""
        if amount < 1.0:
            return
        try:
            import stripe

            stripe.api_key = settings.stripe_api_key
            customer_id = None
            if self.queue:
                import asyncio

                cust_val = self.queue.get(f"stripe:customer:{tenant_id}")
                if asyncio.iscoroutine(cust_val):
                    cust_val = await cust_val
                customer_id = cust_val

            # বাংলা মন্তব্য: আগে customer না পেলে cus_mock_{tenant_id} ব্যবহার হতো।
            # এখন Stripe থেকে real customer lookup করা হয়, না পেলে create করা হয়।
            if not customer_id:
                # বাংলা মন্তব্য: Stripe Customer list-এ tenant_id দিয়ে existing customer খোঁজা
                customers = stripe.Customer.list(  # type: ignore
                    metadata={"tenant_id": tenant_id},
                    limit=1,
                )
                if customers.data:
                    customer_id = customers.data[0].id
                else:
                    # বাংলা মন্তব্য: না পেলে নতুন Stripe Customer তৈরি করা হচ্ছে
                    new_customer = stripe.Customer.create(
                        metadata={"tenant_id": tenant_id},
                        description=f"SupremeAI tenant {tenant_id}",
                    )
                    customer_id = new_customer.id
                    logger.info(f"Created Stripe customer {customer_id} for tenant {tenant_id}")
                    # বাংলা মন্তব্য: নতুন customer ID Redis-এ ক্যাশ করা হচ্ছে ভবিষ্যতের জন্য
                    if self.queue:
                        await self.queue.set(
                            f"stripe:customer:{tenant_id}",
                            customer_id,
                            ttl=86400,  # 24 ঘণ্টা cache
                        )
            else:
                customer_id = (
                    customer_id.decode("utf-8")
                    if isinstance(customer_id, bytes)
                    else str(customer_id)
                )

            stripe.InvoiceItem.create(
                customer=customer_id,
                amount=int(amount * 100),
                currency="usd",
                description=f"SupremeAI usage - tenant {tenant_id}",
            )
            logger.info(f"Stripe usage recorded for tenant {tenant_id}: ${amount:.4f}")
        except Exception as exc:
            logger.debug(f"Stripe charge failed: {exc}")
