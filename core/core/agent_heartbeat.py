"""Agent-10 slot heartbeat — SupremeAI announces itself as alive (issue #1402).

The dashboard (`/api/agents` on the Z.ai preview) distinguishes:

    🟢 online   → heartbeat written within 90s
    🔵 assigned → slot active in AGENT_SLOT_REGISTRY.yaml, no live heartbeat
    ⚪ standby  → slot inactive

Before this loop, agent-10 always showed 🔵 "no heartbeat (tool closed?)" even
while the backend was running, because only the Z.ai dashboard (agent-11)
pinged. This module closes that gap for the self-development slot.

Storage contract (shared with the MCP tower `agent_heartbeat` tool, the
dashboard API route, and scripts/agents/heartbeat_ping.*):

    Key:   supremeai:agent-heartbeat:agent-10
    Value: JSON {slot, agentId, source, updatedAtMs, updatedAt}
    TTL:   300s (a missed ping does not immediately drop the slot)

Cadence: one SET every 45s ≈ 1,920 commands/day (≈0.4% of the Upstash
free-tier budget — quota-safe, R2-03 pattern).

Multi-account failover: the canonical Upstash PRIMARY repeatedly hits its
500k/day ceiling (see issue #1402 "Redis" note). Each tick walks the account
chain until one account accepts the write — REDIS_URL (TCP) first, then the
UPSTASH_REDIS_{,SECONDARY,TERTIARY,QUATERNARY,QUINARY}_REST_* accounts when
present in the process env. Fails soft: errors are logged and the loop
retries on the next tick — a heartbeat outage must never destabilize the
backend.

Env:
    ENABLE_AGENT_HEARTBEAT   "false" disables the loop (default: on —
                             zero-LLM-cost, honest-feature default per
                             LEARNING_LOOP/SYNAPTIC_DREAM precedent)
    AGENT_HEARTBEAT_INTERVAL seconds between pings (default 45)
"""

import asyncio
import json
import os
import time
from typing import Any

from core.logging_config import logger

SLOT = "agent-10"
AGENT_ID = "SupremeAI"
SOURCE = "backend"
DEFAULT_INTERVAL_SECONDS = 45
TTL_SECONDS = 300
KEY_PREFIX = "supremeai:agent-heartbeat:"

# Same placeholder guard as core.queue.task_queue (R2-03): booting against a
# template URL burns quota with zero useful work.
_PLACEHOLDER_TOKENS = ("<your-redis-url>", "<your", "example.com")

# Canonical account order — mirrors settings.upstash_redis_rest_pool and the
# tower/dashboard chain labels.
_ACCOUNT_LABELS = ("primary", "secondary", "tertiary", "quaternary", "quinary")


def _redis_url() -> str:
    """Resolve the real REDIS_URL (env first, settings fallback)."""
    url = os.environ.get("REDIS_URL", "")
    if not url:
        try:
            from core.config import settings

            url = getattr(settings, "redis_url", "") or ""
        except Exception:  # pragma: no cover — settings import must never break heartbeat
            url = ""
    return (url or "").strip()


def _tcp_configured() -> bool:
    url = _redis_url()
    if not url:
        return False
    return not any(token in url for token in _PLACEHOLDER_TOKENS)


def _rest_pool() -> list[tuple[str, str, str]]:
    """(label, url, token) for every configured Upstash REST account.

    Delegates to settings.upstash_redis_rest_pool, which resolves each key
    12-factor style: process env FIRST, then the Infisical vault — so the
    chain works even when the deploy env only carries a subset of the vars.
    """
    try:
        from core.config import settings

        pool = settings.upstash_redis_rest_pool
    except Exception as exc:  # pragma: no cover — settings must never break heartbeat
        logger.warning(f"⚠️ agent-10 heartbeat could not read the Upstash pool: {exc}")
        return []
    labeled: list[tuple[str, str, str]] = []
    for index, (url, token) in enumerate(pool):
        label = _ACCOUNT_LABELS[index] if index < len(_ACCOUNT_LABELS) else f"pool[{index}]"
        labeled.append((label, url, token))
    return labeled


def redis_configured_for_heartbeat() -> bool:
    """True when at least ONE account in the chain is configured."""
    if _tcp_configured():
        return True
    return bool(_rest_pool())


def _build_payload() -> str:
    now_ms = int(time.time() * 1000)
    return json.dumps(
        {
            "slot": SLOT,
            "agentId": AGENT_ID,
            "source": SOURCE,
            "updatedAtMs": now_ms,
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now_ms / 1000)),
        }
    )


async def _ping_tcp(tcp_url: str, payload: str) -> str:
    import redis.asyncio as aioredis

    client = aioredis.from_url(tcp_url, decode_responses=True)
    try:
        await client.set(f"{KEY_PREFIX}{SLOT}", payload, ex=TTL_SECONDS)
    finally:
        await client.aclose()
    return "primary/tcp"


async def _ping_rest(label: str, url: str, token: str, payload: str) -> str:
    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            url,
            json=["SET", f"{KEY_PREFIX}{SLOT}", payload, "EX", TTL_SECONDS],
            headers={"Authorization": f"Bearer {token}"},
        )
    if res.status_code != 200:
        raise RuntimeError(f"upstash[{label}] HTTP {res.status_code}: {res.text[:120]}")
    data: dict[str, Any] = res.json()
    if data.get("error"):
        raise RuntimeError(f"upstash[{label}]: {data['error']}")
    return f"{label}/rest"


async def run_agent_heartbeat_loop() -> None:
    """Long-lived heartbeat loop for slot agent-10.

    Started via AgentSupervisor in core.startup.agents. Every tick walks the
    account chain (TCP primary → REST chain) until one write succeeds.
    """
    interval = max(15, int(os.getenv("AGENT_HEARTBEAT_INTERVAL", str(DEFAULT_INTERVAL_SECONDS))))
    logger.info(
        f"✅ Agent-10 heartbeat loop started (slot={SLOT}, interval={interval}s, "
        f"ttl={TTL_SECONDS}s, key={KEY_PREFIX}{SLOT}, multi-account failover on)."
    )

    while True:
        payload = _build_payload()
        wrote_via: str | None = None
        try:
            if _tcp_configured():
                try:
                    wrote_via = await _ping_tcp(_redis_url(), payload)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(f"⚠️ agent-10 heartbeat TCP write failed: {exc}")

            if wrote_via is None:
                for label, url, token in _rest_pool():
                    try:
                        wrote_via = await _ping_rest(label, url, token, payload)
                        break
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning(f"⚠️ agent-10 heartbeat REST write failed: {exc}")

            if wrote_via is None:
                logger.warning(
                    "⚠️ agent-10 heartbeat: every configured Redis account rejected "
                    "the write this tick (non-fatal, retrying next tick)."
                )
        except asyncio.CancelledError:
            logger.info("ℹ️ Agent-10 heartbeat loop cancelled — shutting down cleanly.")
            raise
        except Exception as exc:  # pragma: no cover — absolute fail-soft guarantee
            logger.warning(f"⚠️ agent-10 heartbeat tick failed (non-fatal): {exc}")

        await asyncio.sleep(interval)
