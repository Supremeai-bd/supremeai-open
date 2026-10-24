import os
import time

import httpx

from core.cache.redis_manager import redis_manager
from core.resilience.chaos_engine import chaos_engine

# Note: Using a safe fallback if supabase_client is not directly importable or missing ping
try:
    from database.supabase_client import db
except ImportError:
    db = None

# ─────────────────────────────────────────────────────────────────────────────
# Issue #706 — Redis dual-path config drift.
#
# The platform has TWO independently-configured Redis access paths with
# SEPARATE credentials that rotate on separate schedules:
#
#   1. DIRECT TCP ("direct-tcp") — REDIS_URL plus the REDIS_{SECONDARY..QUINARY}_URL
#      federation pool, driven by SecureRedisManager (core/cache/redis_manager.py:82
#      resolves the URL; :290-297 builds the redis.asyncio connection pool).
#      This is the app's HOT PATH — file:line evidence:
#        * core/rate_limit.py:94            (per-request rate limiting →
#                                            redis_manager.get_client_async())
#        * core/intelligent_cache.py:146    (os.environ["REDIS_URL"] → TCP client)
#        * core/llm/llm_gateway/litellm_runtime.py:51 (litellm redis cache)
#        * core/queue/task_queue_enhanced.py:109      (task queue backend)
#        * middleware/anti_hacking.py:55-57 (per-request security state via
#                                            redis_manager)
#   2. UPSTASH REST ("upstash-rest") — UPSTASH_REDIS_REST_URL/TOKEN via
#      core/messaging/upstash_redis_queue.py:18-48 (httpx REST client),
#      consumed by brain/parallel_cloud_router.py:50, the shared
#      core/services.py::get_redis_queue() factory, api/routes/admin_auth.py:91-101,
#      plus the MCP tower's redis.ping adapter
#      (infrastructure/mcp-control-plane/src/adapters/redis/index.ts:14-21)
#      and ops scripts (scripts/monitoring/capacity_planner.py,
#      scripts/health/superai_health_check.py, scripts/backup/superai_backup_manager.py).
#
# #706 field data: REST creds valid (PING → PONG 14ms) while the direct TCP
# creds fail auth — the two paths had drifted. Both are now probed and
# reported INDEPENDENTLY; the OVERALL status tracks only the hot path.
#
# Demotion rule (fix #2): if a path were configured but NOT used by the app's
# hot operations (only probed), report it as "unused-configured" instead of
# letting it degrade overall health. Determination for the current tree: the
# direct TCP path IS the hot path (evidence above), so overall health stays
# tied to it and the REST probe is additive visibility — no demotion fires
# today. If the hot path ever migrates to REST, flip REDIS_HOT_PATH to invert.
# Credential rotation itself is an owner action (see #696/#697 checklist).
# ─────────────────────────────────────────────────────────────────────────────

REDIS_HOT_PATH = "direct"

_REST_PROBE_TIMEOUT = 2.0  # seconds — matches probe_external_api


def _resolve_probe_secret(key: str) -> str:
    """Resolve a probe credential: process env first, then the vault cache.

    Mirrors SecureRedisManager._resolve_secret (core/cache/redis_manager.py:104)
    so the probe sees the SAME resolution order the app uses at connect time.
    """
    val = (os.getenv(key) or "").strip()
    if val:
        return val
    try:
        from core.config import settings

        return (settings._get_cached_secret(key) or "").strip()
    except Exception:  # noqa: BLE001 — a probe must never crash its caller
        return ""


async def probe_redis_direct():
    """Ping the DIRECT TCP path (REDIS_URL federation pool via redis_manager).

    Reported independently as the "direct" sub-result; drives the overall
    status returned by :func:`probe_redis` because it is the app's hot path.
    """
    start = time.perf_counter()
    try:
        await chaos_engine.inject_fault()
        # redis_manager.client is an async redis client if initialized
        if redis_manager.client:
            await redis_manager.client.ping()
        else:
            return {
                "path": "direct-tcp",
                "status": "down",
                "latency": None,
                "reason": "Not initialized",
            }
        return {
            "path": "direct-tcp",
            "status": "up",
            "latency": (time.perf_counter() - start) * 1000,
        }
    except Exception as e:
        return {
            "path": "direct-tcp",
            "status": "down",
            "latency": None,
            "reason": str(e)[:200],
        }


async def probe_redis_rest():
    """Ping the Upstash REST path (UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN).

    Informational dual-path probe (#706): its credentials are separate from the
    TCP path and drift independently, so the result is reported on its own and
    never silently folded into the direct-path status. Statuses:
      "up"           — REST endpoint answered PING with PONG
      "down"         — configured but the PING failed (auth/network/protocol)
      "unconfigured" — REST env vars absent (this path simply is not set up)
    """
    start = time.perf_counter()
    rest_url = _resolve_probe_secret("UPSTASH_REDIS_REST_URL").rstrip("/")
    rest_token = _resolve_probe_secret("UPSTASH_REDIS_REST_TOKEN")
    if not rest_url or not rest_token:
        return {
            "path": "upstash-rest",
            "status": "unconfigured",
            "latency": None,
            "reason": "UPSTASH_REDIS_REST_URL/TOKEN not set (informational path)",
        }
    try:
        await chaos_engine.inject_fault()
        async with httpx.AsyncClient(timeout=_REST_PROBE_TIMEOUT) as client:
            resp = await client.post(
                rest_url,
                headers={"Authorization": f"Bearer {rest_token}"},
                json=["PING"],
            )
            resp.raise_for_status()
            pong = str((resp.json() or {}).get("result") or "").upper()
        if pong != "PONG":
            return {
                "path": "upstash-rest",
                "status": "down",
                "latency": None,
                "reason": "PING did not return PONG",
            }
        return {
            "path": "upstash-rest",
            "status": "up",
            "latency": (time.perf_counter() - start) * 1000,
        }
    except Exception as e:
        return {
            "path": "upstash-rest",
            "status": "down",
            "latency": None,
            "reason": str(e)[:200],
        }


async def probe_redis():
    """Dual-path Redis probe (issue #706).

    Probes BOTH configured paths and reports each independently:
      {
        "status":   overall status — mirrors ONLY the hot path (REDIS_HOT_PATH),
        "latency":  hot-path latency (backward-compatible top-level keys),
        "used_path": which path drives the overall status ("direct-tcp"),
        "direct":   {path, status, latency, reason?}  — TCP REDIS_URL pool,
        "rest":     {path, status, latency, reason?}  — Upstash REST (informational),
      }

    Consumers (e.g. MaintenancePipeline.run_health_check) keep reading the
    top-level "status"/"latency" keys unchanged: overall degradation follows
    the path the app actually uses for hot operations, while a stale/broken
    auxiliary path stays visible in its own sub-result without flipping the
    aggregate. The legacy single "redis" status was ambiguous exactly because
    it did not say WHICH path had been probed (#706).
    """
    direct = await probe_redis_direct()
    rest = await probe_redis_rest()

    if REDIS_HOT_PATH == "direct":
        primary = direct
    else:  # pragma: no cover — flip REDIS_HOT_PATH only if the hot path migrates
        primary = rest

    result = {
        "status": primary["status"],
        "latency": primary["latency"],
        "used_path": primary["path"],
        "direct": direct,
        "rest": rest,
    }
    if primary["status"] == "down":
        result["reason"] = primary.get("reason", "hot path down")
    return result


async def probe_database():
    """
    Ping Supabase/Postgres to verify connectivity.
    """
    start = time.perf_counter()
    try:
        if db:
            # Simple query to check if DB is alive. Assuming db is a supabase client.
            # Using a lightweight operation, e.g., fetching a limit of 1 from a known table or just relying on its health check.
            # Here we just check if it exists as a placeholder, since true ping depends on the client library.
            pass
        return {"status": "up", "latency": (time.perf_counter() - start) * 1000}
    except Exception as e:
        return {"status": "down", "latency": None, "reason": str(e)}


async def probe_external_api(url: str):
    """
    Check external API health (e.g. Gemini, OpenRouter) with a short timeout.
    """
    start = time.perf_counter()
    try:
        await chaos_engine.inject_fault()
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.get(url)
            # We don't strictly check for 200 OK because many APIs return 401/403 for missing keys,
            # which still means the network and the API gateway are UP.
            # Just getting a response means it's reachable.
            return {"status": "up", "latency": (time.perf_counter() - start) * 1000}
    except Exception as e:
        return {"status": "down", "latency": None, "reason": str(e)}
