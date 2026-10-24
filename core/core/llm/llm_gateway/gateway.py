# backend/core/llm/llm_gateway/gateway.py
"""LLMGateway class assembly: mixins + __init__ + properties + async_generate.

Task 4-a package split: code moved VERBATIM from core/llm/llm_gateway.py.
The original single class body is composed from cohesive mixins:
RoutingMixin (routing.py), LitellmSetupMixin (litellm_runtime.py),
ResilienceMixin (resilience.py), CompletionMixin (completion.py),
StreamingMixin (streaming.py). Method resolution order provides exactly one
definition of each method — behavior is identical to the original monolith.
"""

from typing import Any

from core.logging_config import logger

from ...config import settings  # Fixed import path - using relative import
from ...observability.providers.langfuse_adapter import LangfuseAdapter
from ...resilience.circuit_breaker_manager import (
    get_shared_circuit_breaker,  # Fixed import path - using relative import
)
from ..interfaces import ExecutionMode
from ..providers import CloudProviderAdapter, OllamaLocalAdapter
from .completion import CompletionMixin
from .litellm_runtime import LitellmSetupMixin
from .registry import _provider_key_pool, _resolve_key_attr
from .resilience import ResilienceMixin
from .routing import RoutingMixin
from .streaming import StreamingMixin


class LLMGateway(
    RoutingMixin,
    LitellmSetupMixin,
    ResilienceMixin,
    CompletionMixin,
    StreamingMixin,
):
    """
    বাংলা মন্তব্ব: Multi-provider LLM Gateway।
    - os.environ secrets injection সম্পূর্ণ নিষিদ্ধ — per-call api_key passing।
    - litellm global state mutation নিষিদ্ধ।
    - Heavy import (litellm) function level-এ lazy load।
    - Semantic cache, fallback chain, cost guard intact।
    - CancelledError সবসময় re-raise।
    """

    def __init__(self, mode: ExecutionMode = ExecutionMode.AUTO) -> None:
        self.mode = mode
        self.cloud_adapter = CloudProviderAdapter()
        # বাংলা মন্তব্য: OllamaLocalAdapter শুধু local/test env-এ eager init করা হয়।
        # Production/staging-এ Ollama থাকে না — সেখানে None রেখে lazy init করা হবে।
        # এটি Render free-tier crash ঠেকায় (ValueError: localhost fallback in production)।
        if settings.env in ("local", "test"):
            self.local_adapter: OllamaLocalAdapter | None = OllamaLocalAdapter()
        else:
            self.local_adapter = None
        self.observability = LangfuseAdapter()

        self.routing_policy = self._load_routing_policy()
        # R2-MEM fix: litellm import costs ~240MB RSS. Constructing the gateway
        # happens during BOOT (multiple eager import chains), so setting up
        # litellm here loaded 240MB into every cold start even when no LLM call
        # was ever made. Defer to first completion call (see _ensure_litellm_ready).
        self._litellm_ready = False
        # Use centralized circuit breaker manager instead of local dict
        self._circuit_breaker_manager = get_shared_circuit_breaker

        # বাংলা: Circular import এড়ানোর জন্য performance_optimizer lazy-load করা হবে
        self._performance_optimizer = None

        # Performance tracking
        self._request_count = 0
        self._error_count = 0

        # Performance Optimization: Lazy initialize cache on demand to prevent circular imports
        self._cache = None
        self._router_obj = None

    @property
    def _router(self):
        # বাংলা মন্তব্য (audit V3 B-V2-01 fix): আগে router unset থাকলে এখানে
        # production-এ `MagicMock()` বানানো হতো — Mock-এর `.route` সবসময়
        # non-None বলে async_generate-এর MoE শাখা সবসময় প্রবেশ করত, আর
        # কলার "text"/"content" হিসেবে ভুয়া Mock অবজেক্ট পেত (আসল LLM ডাকই
        # হতো না)। এখন unset মানে সৎ None — কলার নিজের সৎ fallback পাথে যায়।
        return getattr(self, "_router_obj", None)

    @_router.setter
    def _router(self, val):
        self._router_obj = val

    @property
    def performance_optimizer(self):
        """Circular import guard: performance_enhancer → llm_gateway চক্র ভাঙতে lazy-load।"""
        if self._performance_optimizer is None:
            from core.performance_enhancer import (
                get_performance_optimizer,
            )

            self._performance_optimizer = get_performance_optimizer()
        return self._performance_optimizer

    @property
    def cache(self):
        if self._cache is None:
            from core.cache.semantic_cache import SemanticCache

            self._cache = SemanticCache()
        return self._cache

    @cache.setter
    def cache(self, value):
        self._cache = value

    async def _get_api_key_for_model(self, model: str) -> str | None:
        """
        FIX (P0, review 2026-09-12): comma-separated multi-key env strings are
        now split and rotated via _provider_key_pool. Previously the raw
        "k1,k2,k3" string was sent as a single API key, so every provider call
        failed with 401/403 and the zero-cost fallback chain was dead.
        Longest-prefix provider matching also fixes misrouting
        (openrouter/deepseek/* used to grab the deepseek key).
        """
        if not model:
            return None
        attr_name = _resolve_key_attr(model)
        if attr_name is None:
            return None
        raw_key = getattr(settings, attr_name, None)
        provider = (
            model.split("/")[0].lower()
            if "/" in model
            else attr_name.replace("_api_key", "").lower()
        )
        try:
            return await _provider_key_pool.next_key(provider, raw_key)
        except Exception:
            # pool failure fallback: first individual key (never the raw joined string)
            raw = (str(raw_key) if raw_key else "").strip()
            if not raw:
                return None
            return raw.split(",")[0].strip() or None

    async def async_generate(self, prompt: str, use_moe: bool = False, **kwargs) -> dict[str, Any]:
        """Backward-compatible helper alias for acompletion & MoE integration."""
        # বাংলা মন্তব্য (B-V2-01 fix): শুধুমাত্র সত্যিই inject করা router থাকলে MoE
        # শাখা চলে; use_moe=True কিন্তু router না থাকলে loud warning-সহ সৎ
        # acompletion fallback (নীরব ভান নয়)। route ব্যর্থ হলে warning-এ
        # diagnostics হারানো হতো না (আগে debug লেভেলে swallow)।
        router = self._router
        if router is not None and hasattr(router, "route"):
            try:
                route_res = await router.route(prompt, **kwargs)
                if route_res is not None:
                    content = getattr(route_res, "content", str(route_res))
                    return {
                        "success": True,
                        "text": content,
                        "content": content,
                        "provider": getattr(
                            getattr(route_res, "provider", None), "value", "moonshot"
                        ),
                        "cost": 0.0,
                    }
            except Exception as e:
                logger.warning(
                    f"[LLMGateway] MoE route failed ({type(e).__name__}: {e}) — falling back to acompletion"
                )
        elif use_moe:
            logger.warning(
                "[LLMGateway] use_moe=True but no router injected — falling back to acompletion"
            )
        res = await self.acompletion(prompt=prompt, **kwargs)
        if isinstance(res, dict):
            return res
        text = res.choices[0].message.content if hasattr(res, "choices") else str(res)
        return {
            "success": True,
            "text": text,
            "content": text,
            "provider": getattr(res, "provider", "moonshot"),
            "cost": 0.0,
        }
