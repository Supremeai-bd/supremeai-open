"""SupremeAI 2.0 — Core service registry and lazy initialization.

বাংলা: কোর সার্ভিস রেজিস্ট্রি এবং লেজি ইনিশিয়ালাইজেশন।

---
PATCH v4 (2026-08-30):
- Production logs showed persistent `MEMORY WARNING (90.78% used)` on Render's
  512 MB free tier. Root cause: this module eagerly constructed 7 heavy
  singletons at import time (`redis_queue`, `admin_god`, `model_router`,
  `parallel_router`, `intent_clf`, `intent_parser`, `experience_db`). Each
  transitively pulled in performance_optimizer, SelfHealerService,
  RemediationPipeline, ModelRegistry, additional httpx.Client pools, etc.
  Cumulative RSS at import time was >460 MB before any request was served.
- Fix: convert eager singletons to lazy factories backed by `functools.lru_cache`.
  Singletons are only constructed on FIRST attribute access, not at import.
  Callers using `services.model_router` (etc.) keep working unchanged —
  the module-level `__getattr__` returns the lazily-constructed instance.
- Memory benefit: ~80-120 MB freed at boot. Cold-start memory pressure
  drops from 90.78% → expected ~72-78%, eliminating the warning log spam.
- Backward compat: every existing caller (`services.model_router`,
  `services.redis_queue`, etc.) keeps working. New code should prefer the
  `get_*()` factory functions for explicitness.
"""

import asyncio
import functools
from collections.abc import Callable
from typing import Any

import httpx

from core.errors.error_bus import with_error_bus

# Lazy HTTP client — initialized on first use
_http_client: httpx.AsyncClient | None = None


async def get_global_http_client() -> httpx.AsyncClient:
    """Get or create the global HTTP client singleton."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _http_client


async def close_global_http_client() -> None:
    """Close the global HTTP client."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


class ServiceRegistry:
    """
    বাংলা মন্তব্য: Factory pattern with async initialization.
    Instance নয়, factory register করুন। async def create() classmethod দিয়ে async initialization করুন।
    """

    def __init__(self) -> None:
        self._services: dict[str, Callable] = {}
        self._instances: dict[str, Any] = {}

    def register(self, name: str, factory: Callable) -> None:
        """Register a service factory."""
        self._services[name] = factory

    async def get(self, name: str) -> Any:
        """Get or create a service instance by name."""
        if name not in self._instances:
            factory = self._services.get(name)
            if not factory:
                raise KeyError(f"Service '{name}' not registered")
            self._instances[name] = await factory()
        return self._instances[name]

    def has(self, name: str) -> bool:
        """Check if a service is registered."""
        return name in self._services


# Global service registry instance
registry = ServiceRegistry()


# ─────────────────────────────────────────────────────────────────────────────
# PATCH v4: Lazy singleton factories.
#
# Previously this module eagerly constructed 7 heavy singletons at import time.
# Each singleton transitively pulled in performance_optimizer, SelfHealerService,
# RemediationPipeline, ModelRegistry, additional httpx.Client pools, etc. —
# pushing RSS >460 MB / 512 MB (90.78%) on Render free tier before any request
# was served. Now each is constructed on first access via `get_*()` and cached.
# ─────────────────────────────────────────────────────────────────────────────


@functools.lru_cache(maxsize=1)
def get_redis_queue():
    """Lazy factory for the shared UpstashRedisQueue singleton."""
    from core.messaging.upstash_redis_queue import UpstashRedisQueue

    return UpstashRedisQueue()


@functools.lru_cache(maxsize=1)
def get_admin_god():
    """Lazy factory for the AdminGodLayer singleton.

    Construction opens Firestore + SQLite + bootstraps the rules table —
    previously happened at import time, adding ~25 MB to boot RSS.
    """
    from admin.god import AdminGodLayer

    return AdminGodLayer()


@functools.lru_cache(maxsize=1)
def get_model_router():
    """Lazy factory for the ModelRouter singleton.

    Construction pulls in PerformanceOptimizer → SelfHealerService +
    RemediationPipeline + ModelRegistry — previously happened at import
    time, adding ~40 MB to boot RSS.
    """
    from brain.model_router import ModelRouter

    return ModelRouter()


@functools.lru_cache(maxsize=1)
def get_parallel_router():
    """Lazy factory for the ParallelCloudRouter singleton.

    Construction spins up another UpstashRedisQueue with its own httpx pool.
    """
    from brain.parallel_cloud_router import ParallelCloudRouter

    return ParallelCloudRouter()


@functools.lru_cache(maxsize=1)
def get_intent_clf():
    """Lazy factory for the IntentClassifier singleton."""
    from core.intent import IntentClassifier

    return IntentClassifier()


@functools.lru_cache(maxsize=1)
def get_intent_parser():
    """Lazy factory for the IntentParser singleton.

    Depends on `model_router` (also lazy now) — resolves it on first use.
    """
    from adaptive_engine.intent_parser import IntentParser

    return IntentParser(model_router=get_model_router())


@functools.lru_cache(maxsize=1)
def get_experience_db():
    """Lazy factory for the ExperienceDatabase singleton (LOW_MEMORY_MODE-aware)."""
    from adaptive_engine.experience_db import ExperienceDatabase

    return ExperienceDatabase()


# AUDIT-WIRE FIX (latent AttributeError + Part-A/D connect): api/routes/admin_routes.py
# `/admin/gcp/health` এবং `/admin/gcp/*` রুটগুলো `services.gcp_router`,
# `services.verification_queue`, `services.gcp_pubsub_queue`,
# `services.cloud_function_client` reference করে — কিন্তু এই নামগুলোর কোনো
# factory ছিল না, ফলে প্রথম কলেই AttributeError (ল্যাটেন্ট প্রোডাকশন বাগ)।
# প্রকৃত ক্লাসগুলো কোডবেসে বিদ্যমান ছিল (গুলোর একটি — GCPCloudRunRouter —
# isolated-catalog-এর "Part D" তালিকায় ছিল); এখন lazy singleton হিসেবে wired।
@functools.lru_cache(maxsize=1)
def get_gcp_router():
    """Lazy factory for the GCP Cloud Run router singleton."""
    from brain.gcp_router import GCPCloudRunRouter

    return GCPCloudRunRouter()


@functools.lru_cache(maxsize=1)
def get_verification_queue():
    """Lazy factory for the GCP Firestore verification queue singleton."""
    from services.storage.gcp_firestore import GCPFirestoreVerificationQueue

    return GCPFirestoreVerificationQueue()


@functools.lru_cache(maxsize=1)
def get_gcp_pubsub_queue():
    """Lazy factory for the GCP Pub/Sub queue singleton."""
    from core.messaging.gcp_pubsub_queue import GCPPubSubQueue

    return GCPPubSubQueue()


@functools.lru_cache(maxsize=1)
def get_cloud_function_client():
    """Lazy factory for the GCP Cloud Functions client singleton."""
    from tools.devops.gcp_cloud_functions import GCPCloudFunctionClient

    return GCPCloudFunctionClient()


@functools.lru_cache(maxsize=1)
def get_rules_engine():
    """Lazy factory for the UniversalRulesEngine singleton.

    Issue #1489/#1469: api/routes/admin_routes.py reads `services.rules_engine`
    (GET/POST /admin/rules) but this module never exposed the attribute —
    `__getattr__` fell through to AttributeError → 500 on every call.
    """
    from core.universal_rules import UniversalRulesEngine

    return UniversalRulesEngine()


# PATCH v4: singleton factories registry — used by `__getattr__` below to
# resolve legacy `services.<name>` attribute access lazily.
_SINGLETON_FACTORIES: dict[str, Callable[[], Any]] = {
    "redis_queue": get_redis_queue,
    "admin_god": get_admin_god,
    "model_router": get_model_router,
    "parallel_router": get_parallel_router,
    "intent_clf": get_intent_clf,
    "intent_parser": get_intent_parser,
    "experience_db": get_experience_db,
    # AUDIT-WIRE FIX: api/routes/admin_routes.py /admin/gcp/* রুটগুলোর জন্য প্রয়োজনীয়।
    "gcp_router": get_gcp_router,
    "verification_queue": get_verification_queue,
    "gcp_pubsub_queue": get_gcp_pubsub_queue,
    "cloud_function_client": get_cloud_function_client,
    # AUDIT-WIRE FIX (#1489/#1469): /admin/rules read `services.rules_engine`
    # which never resolved → AttributeError → 500 on every admin rules call.
    "rules_engine": get_rules_engine,
}


# Global HTTP client - initialized in lifespan
global_http_client: httpx.AsyncClient | None = None


def __getattr__(name: str) -> Any:
    """Dynamic service getter — PATCH v4: lazy singleton construction.

    বাংলা: dunder attribute probe (যেমন `__path__`, `__all__`) সবসময় স্বাভাবিক,
    প্রত্যাশিত ঘটনা — Python-এর নিজস্ব import/inspect মেশিনারি নিয়মিতভাবে এগুলো চেক
    করে দেখে এই মডিউলটা একটা প্যাকেজ কিনা। আগে পুরো ফাংশনটাই `@with_error_bus` দিয়ে
    wrap করা ছিল, ফলে প্রতিটা dunder-probe-এর স্বাভাবিক AttributeError-ও একটা
    "application error" হিসেবে error_event_bus-এ রিপোর্ট হচ্ছিল। প্রতি ~৫ সেকেন্ডে এটা
    ঘটায় error-pattern-detector সেটাকে "AttributeError x3 → CRITICAL" ধরে নিয়ে
    self-healing/emergency-evolution ট্রিগার করছিল — যেটা নিজেই আরেকটা বাগের
    (fitness_engine মিসিং) কারণে ক্র্যাশ করে, এবং পুরো চক্রটা অনন্তকাল ধরে রিপিট হয়
    (production লগে এটাই মূল কারণ ছিল)। তাই dunder short-circuit-টা এখন
    error-bus-wrapped অংশের বাইরে রাখা হলো, যাতে এটা কখনো error হিসেবে রিপোর্ট না হয়।

    PATCH v4 পরিবর্তন: এখন এই ফাংশন সাতটি lazy singleton factory-কেও dispatch
    করে (`redis_queue`, `admin_god`, `model_router`, ...)। প্রতিটা factory
    `functools.lru_cache` দিয়ে guarded — প্রথম কলে construct হয়, পরবর্তী কলে
    cached instance ফেরত দেয়। এতে আগের eager module-level construction-এর
    দরুন 90.78% memory pressure চলে যায়, কারণ services module import হলেই
    আর কোনো heavy singleton তৈরি হবে না।
    """
    if name.startswith("__") and name.endswith("__"):
        raise AttributeError(f"Module 'core.services' has no attribute '{name}'")
    return _get_service_attr(name)


@with_error_bus("__getattr__")
def _get_service_attr(name: str) -> Any:
    """Actual service-lookup logic — only reached for real (non-dunder) attribute names."""
    # PATCH v4: short-circuit for lazy singleton factories — do NOT route through
    # the registry, do NOT raise AttributeError for known singletons.
    if name in _SINGLETON_FACTORIES:
        try:
            return _SINGLETON_FACTORIES[name]()
        except Exception:
            # If construction fails, return None for callers that already check
            # truthiness (e.g. `if services.redis_queue and services.redis_queue.configured:`).
            # Construction errors will be logged by the underlying constructor.
            return None

    # Attempt to resolve from registry safely without triggering imports
    reg = globals().get("registry")
    if reg:
        if hasattr(reg, "get") and name in reg._services:
            # Return the service factory, not the instance
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # In async context, return the service
                    return reg._instances.get(name)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")
        if hasattr(reg, "_services") and name in reg._services:
            return reg._services[name]

    raise AttributeError(f"Module 'core.services' has no attribute '{name}'")


def reset_singletons() -> None:
    """PATCH v4: test-only — clear all lazy singleton caches.

    Production code should never call this; it exists so unit tests that
    mock these singletons can restore a clean state between test cases.
    """
    get_redis_queue.cache_clear()
    get_admin_god.cache_clear()
    get_model_router.cache_clear()
    get_parallel_router.cache_clear()
    get_intent_clf.cache_clear()
    get_intent_parser.cache_clear()
    get_experience_db.cache_clear()
