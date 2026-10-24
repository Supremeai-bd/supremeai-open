"""
token_budget.py
===============
Added by Agent Antigravity on 2026-06-22

Token budget management for free-tier AI providers.
Estimates, compresses, and enforces token limits to avoid
wasting free-tier quota on over-long prompts.

Key features:
- Character-based token estimation (no tiktoken dependency needed)
- Prompt truncation with smart sentence-boundary detection
- Per-provider token budget awareness
- Usage statistics
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus

# ---------------------------------------------------------------------------
# Per-provider max token budgets (conservative — leaves headroom for system prompts)
# ---------------------------------------------------------------------------
PROVIDER_TOKEN_BUDGETS: dict[str, dict[str, int]] = {
    "gemini": {
        "max_input_tokens": 6_000,  # context window is much larger but TPM is the constraint
        "max_output_tokens": 2_000,
    },
    "groq": {
        "max_input_tokens": 4_000,  # 30k TPM shared; keep inputs short
        "max_output_tokens": 1_500,
    },
    "openrouter": {
        "max_input_tokens": 4_000,
        "max_output_tokens": 1_500,
    },
    "cloudflare": {
        "max_input_tokens": 3_000,  # Cloudflare Workers AI has smaller context
        "max_output_tokens": 1_000,
    },
    "nvidia": {
        "max_input_tokens": 4_000,
        "max_output_tokens": 1_500,
    },
    "huggingface": {
        "max_input_tokens": 1_500,  # HF inference API has small context windows
        "max_output_tokens": 500,
    },
    "ollama": {
        "max_input_tokens": 8_000,  # local — can handle larger context
        "max_output_tokens": 4_000,
    },
    "deepseek": {
        "max_input_tokens": 8_000,
        "max_output_tokens": 4_000,
    },
    "default": {
        "max_input_tokens": 4_000,
        "max_output_tokens": 1_500,
    },
}

# Rough chars-per-token ratio (average English text ≈ 4 chars/token)
_CHARS_PER_TOKEN: float = 4.0


# ---------------------------------------------------------------------------
# Local in-memory fallback budget tracker (issue #1687)
# ---------------------------------------------------------------------------
# Redis অনুপলব্ধ হলে production/staging-এ ব্যবহৃত degraded-mode কাউন্টার —
# conservative limit = Redis দৈনিক সীমার ১০% (সর্বনিম্ন ১,০০০)।
_LOCAL_FALLBACK_RATIO: float = 0.1
_LOCAL_FALLBACK_MIN: int = 1_000
_LOCAL_TRACKER_MAX_USERS: int = 10_000


class _LocalBudgetTracker:
    """Thread-safe in-memory per-user daily token counter (issue #1687).

    Redis down হলে check_user_budget এই ট্র্যাকারের উপর conservative cap
    প্রয়োগ করে: সার্ভিস সম্পূর্ণ deny-outage হয় না (আগের B-V2-03 আচরণ),
    আবার unlimited spend-ও হয় না (মূল নীরব fail-open)। record_user_usage
    সর্বদা এই মিররটি আপডেট রাখে যাতে Redis মাঝপথে মরলে আজকের ব্যবহার জানা
    থাকে (আগে Redis-fail = usage রেকর্ড চুপচাপ হারানো)।
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}

    @staticmethod
    def _key(user_id: str) -> str:
        return f"{user_id}:{time.strftime('%Y-%m-%d')}"

    def record(self, user_id: str, tokens: int) -> None:
        if tokens <= 0:
            return
        with self._lock:
            if len(self._counts) > _LOCAL_TRACKER_MAX_USERS:
                # Opportunistic prune: শুধু আজকের এন্ট্রি রাখি (date rollover)
                today = time.strftime("%Y-%m-%d")
                self._counts = {k: v for k, v in self._counts.items() if k.endswith(f":{today}")}
            key = self._key(user_id)
            self._counts[key] = self._counts.get(key, 0) + tokens

    def get_today(self, user_id: str) -> int:
        with self._lock:
            return self._counts.get(self._key(user_id), 0)

    def fallback_limit(self, daily_limit: int) -> int:
        """Conservative degraded-mode cap: Redis দৈনিক সীমার ১০%
        (সর্বনিম্ন _LOCAL_FALLBACK_MIN) — Redis ছাড়া এর বেশি spend
        কোনো অবস্থাতেই অনুমোদিত নয়।"""
        return max(_LOCAL_FALLBACK_MIN, int(daily_limit * _LOCAL_FALLBACK_RATIO))


def estimate_tokens(text: str) -> int:
    """
    Fast character-based token count estimate.
    Accurate enough for budget enforcement without requiring tiktoken.

    English text: ~4 chars/token
    Code: ~3.5 chars/token (more tokens per char due to punctuation)
    CJK: ~2 chars/token
    Bengali: ~2 chars/token (blended per-script — M19 P-D single owner
    ``core.i18n.bengali_text``; বাংলা প্রম্পটে পুরনো flat 4.0 অনুমান
    প্রায় ২ গুণ under-count করত — quota-ভাঙার ঝুঁকি)
    """
    if not text:
        return 0

    # M19 P-D: বাংলা-অংশ blended ওজন একক মালিক মডিউলে — কোড/CJK শাখা
    # সেখানেও বিদ্যমান অনুপাতে সংরক্ষিত।
    from core.i18n.bengali_text import estimate_tokens_bengali_aware

    return estimate_tokens_bengali_aware(text)


def truncate_to_token_limit(text: str, max_tokens: int, from_end: bool = False) -> str:
    """
    Truncate *text* so that estimate_tokens(result) <= max_tokens.
    Tries to cut at sentence boundaries to preserve coherence.
    Falls back to hard character truncation when no boundary is found.
    If from_end=True, keeps the END of the text (useful for recent context).
    """
    if estimate_tokens(text) <= max_tokens:
        return text

    # Target character count
    target_chars = int(max_tokens * _CHARS_PER_TOKEN)

    if from_end:
        truncated = text[-target_chars:]
        # Trim to first sentence boundary (।/॥ = বাংলা বাক্যশেষ — M19 P-D)
        match = re.search(r"[.!?।॥\n]", truncated)
        if match:
            truncated = truncated[match.start() + 1 :]
        return truncated.strip()
    else:
        truncated = text[:target_chars]
        # Trim to last sentence boundary; fall back to hard cut if none found
        # (।/॥ = বাংলা বাক্যশেষ — M19 P-D: ডাঁড়ি-মাঝে কাটা বাক্য-অর্থ ভাঙত)
        match = re.search(r"[.!?।॥\n](?=[^.!?\u0964\u0965\n]*$)", truncated)
        if match:
            truncated = truncated[: match.start() + 1]
        return truncated.strip()


@dataclass
class TokenBudgetStats:
    """Accumulates per-provider token usage stats."""

    provider: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_calls: int = 0
    truncated_calls: int = 0
    tokens_saved_by_truncation: int = 0
    started_at: float = field(default_factory=time.time)

    def record_call(
        self,
        input_tokens: int,
        output_tokens: int,
        was_truncated: bool = False,
        tokens_saved: int = 0,
    ) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_calls += 1
        if was_truncated:
            self.truncated_calls += 1
            self.tokens_saved_by_truncation += tokens_saved

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "avg_input_tokens": (
                self.total_input_tokens // self.total_calls if self.total_calls else 0
            ),
            "truncated_calls": self.truncated_calls,
            "tokens_saved_by_truncation": self.tokens_saved_by_truncation,
            "tracking_since": self.started_at,
        }


class TokenBudgetManager:
    """
    Manages per-provider token budgets and prompt compression.

    Usage::

        budget = TokenBudgetManager()

        # Compress a prompt before sending
        compressed, meta = budget.prepare_prompt("very long prompt...", provider="groq")

        # After getting a response, record usage
        budget.record_usage(
            provider="groq",
            input_tokens=meta["estimated_input_tokens"],
            output_tokens=budget.estimate("response text"),
        )

        # Get stats
        stats = budget.get_stats()
    """

    def __init__(
        self,
        custom_budgets: dict[str, dict[str, int]] | None = None,
    ) -> None:
        self._budgets = {**PROVIDER_TOKEN_BUDGETS, **(custom_budgets or {})}
        self._stats: dict[str, TokenBudgetStats] = {}
        self._redis = None
        self._local = _LocalBudgetTracker()

    async def _get_redis(self):
        if not self._redis:
            import redis.asyncio as aioredis

            try:
                import os

                from core.config import settings

                redis_url = getattr(settings, "redis_url", None) or os.environ.get(
                    "REDIS_URL", "redis://<your-redis-url>"
                )
            except ImportError:
                import os

                redis_url = os.environ.get("REDIS_URL", None)

            # বাংলা মন্তব্য (audit V3, B-V2-03 fix, 2026-09-17): আগে placeholder
            # URL `redis://<your-redis-url>` দিয়ে ক্লায়েন্ট বানানো হতো —
            # Redis না থাকলে প্রতিটি call নীরবে exception → fail-open। এখন
            # unconfigured অবস্থা স্পষ্টভাবে ধরা হয় এবং সৎ error ছোড়া হয়,
            # যাতে কলার সিদ্ধান্ত (fail-closed/fail-open) env-অনুযায়ী হয়।
            if not redis_url or "<your-redis-url>" in str(redis_url):
                raise RuntimeError(
                    "Redis URL not configured — per-user token budget check is UNAVAILABLE"
                )
            self._redis = aioredis.from_url(redis_url, decode_responses=True)
        return self._redis

    async def check_user_budget(self, user_id: str, daily_limit: int = 100000) -> bool:
        """
        Check if the user has exceeded their daily token limit.
        Uses Redis to support multi-worker environments.

        Failure policy (audit V3 / B-V2-03): budget check করা না গেলে
        production/staging-এ fail-CLOSED (অনুমতি নেই), dev/test-এ fail-open
        + loud log — কোনো অবস্থাতেই নীরব ভান নেই।
        """
        try:
            redis = await self._get_redis()
            today = time.strftime("%Y-%m-%d")
            key = f"user_budget:{user_id}:{today}"
            current = await redis.get(key)
            if current and int(current) >= daily_limit:
                logger.warning(f"User {user_id} exceeded daily token budget of {daily_limit}")
                return False
            return True
        except Exception as e:
            # বাংলা মন্তব্য (B-V2-03 fix): আগে সর্বদা `return True # fail open` —
            # মানে Redis ছাড়া per-user দৈনিক quota কার্যত অসীম (unlimited
            # spend)। এখন production/staging-এ অনুমতি অস্বীকার করা হয় (fail-
            # closed), dev/test-এ অনুমতি + loud error log। সিদ্ধান্তটি
            # token_deductor-এর বিদ্যমান env-policy-র সাথে সামঞ্জস্যপূর্ণ।
            try:
                from core.config import settings

                current_env = str(getattr(settings, "env", "")).lower()
            except Exception:
                current_env = ""
            logger.error(
                f"User budget check UNAVAILABLE (env={current_env or 'unknown'}): "
                f"{type(e).__name__}: {e}"
            )
            if current_env in {"production", "prod", "staging"}:
                # Issue #1687: সরাসরি deny নয় — আগে লোকাল in-memory fallback
                # দেখা হয় (conservative cap)। Redis-down outage-এ সার্ভিস
                # চলে, কিন্তু spend capped — unlimited fail-open নয়, আবার
                # 100% deny-outage-ও নয়।
                fallback_cap = self._local.fallback_limit(daily_limit)
                local_used = self._local.get_today(user_id)
                if local_used >= fallback_cap:
                    logger.warning(
                        f"User {user_id} exceeded LOCAL fallback budget "
                        f"({local_used}/{fallback_cap}) while Redis is "
                        f"unavailable — denying (fail-closed on cap)"
                    )
                    return False  # fail-closed: local conservative cap ভাঙা যাবে না
                logger.warning(
                    f"Redis unavailable — LOCAL fallback budget active for "
                    f"{user_id}: {local_used}/{fallback_cap} (degraded mode)"
                )
                return True
            return True  # dev/test: fail-open (উপরের error log-এ স্পষ্ট)

    async def record_user_usage(self, user_id: str, tokens: int) -> None:
        """
        Record tokens used by a user in Redis.

        Issue #1687: সর্বদা local mirror-ও আপডেট হয় — Redis মাঝপথে ডাউন
        হলে check_user_budget-এর degraded fallback অন্তত আজকের ব্যবহার
        জানবে (আগে Redis-fail = usage রেকর্ড সম্পূর্ণ হারানো)।
        """
        if tokens <= 0:
            return
        self._local.record(user_id, tokens)
        try:
            redis = await self._get_redis()
            today = time.strftime("%Y-%m-%d")
            key = f"user_budget:{user_id}:{today}"
            current = await redis.incrby(key, tokens)
            if current == tokens:
                await redis.expire(key, 86400)  # 24 hours
        except Exception as e:
            logger.error(
                "Redis user budget record failed (local fallback mirror "
                f"kept {self._local.get_today(user_id)} tokens for today): {e}"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate(self, text: str) -> int:
        """Estimate token count for *text*."""
        return estimate_tokens(text)

    def prepare_prompt(
        self,
        prompt: str,
        provider: str = "default",
        system_prompt: str | None = None,
        reserve_output_tokens: bool = True,
    ) -> tuple[str, dict[str, Any]]:
        """
        Validate and compress *prompt* to fit within *provider*'s input budget.

        Returns (processed_prompt, metadata_dict).
        Metadata includes estimated token counts and whether truncation happened.
        """
        limits = self._budgets.get(provider, self._budgets["default"])
        max_input = limits["max_input_tokens"]

        # Reduce input budget if we need to reserve space for output
        if reserve_output_tokens:
            max_input = max(500, max_input - limits.get("max_output_tokens", 0) // 2)

        original_tokens = estimate_tokens(prompt)
        system_tokens = estimate_tokens(system_prompt) if system_prompt else 0
        available_for_user = max_input - system_tokens

        if available_for_user <= 0:
            msg = f"Token budget exhausted for {provider}. System prompt uses {system_tokens} tokens, max allowed is {max_input}."
            logger.error(f"[TokenBudget] {msg}")
            error_event_bus.emit(
                ErrorEvent(
                    module="token_budget",
                    error_type="BUDGET_EXHAUSTION",
                    message=msg,
                    severity="ERROR",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={
                        "provider": provider,
                        "system_tokens": system_tokens,
                        "max_input": max_input,
                    },
                )
            )
            raise ValueError(msg)

        truncated = False
        tokens_saved = 0

        if original_tokens > available_for_user:
            truncated_prompt = truncate_to_token_limit(prompt, available_for_user)
            tokens_saved = original_tokens - estimate_tokens(truncated_prompt)
            logger.info(
                f"[TokenBudget] Truncated prompt for {provider}: "
                f"{original_tokens} → {estimate_tokens(truncated_prompt)} tokens "
                f"(saved {tokens_saved})"
            )
            prompt = truncated_prompt
            truncated = True

        final_tokens = estimate_tokens(prompt)

        meta: dict[str, Any] = {
            "provider": provider,
            "estimated_input_tokens": final_tokens,
            "original_tokens": original_tokens,
            "truncated": truncated,
            "tokens_saved": tokens_saved,
            "max_output_tokens": limits["max_output_tokens"],
        }

        # Record stats
        self._get_stats(provider).record_call(
            input_tokens=final_tokens,
            output_tokens=0,  # will be updated after response
            was_truncated=truncated,
            tokens_saved=tokens_saved,
        )

        return prompt, meta

    def record_usage(
        self,
        provider: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record actual token usage after a completed API call."""
        self._get_stats(provider).total_output_tokens += output_tokens
        logger.debug(
            f"[TokenBudget] {provider} usage: in={input_tokens} out={output_tokens} total_in={self._get_stats(provider).total_input_tokens}"
        )

    def fits_in_budget(self, prompt: str, provider: str = "default") -> bool:
        """Return True if *prompt* fits within provider's input token budget."""
        limits = self._budgets.get(provider, self._budgets["default"])
        return estimate_tokens(prompt) <= limits["max_input_tokens"]

    def get_stats(self) -> dict[str, Any]:
        """Return token usage stats for all providers."""
        return {provider: stats.to_dict() for provider, stats in self._stats.items()}

    def get_provider_budget(self, provider: str) -> dict[str, int]:
        """Return token limits for a specific provider."""
        return self._budgets.get(provider, self._budgets["default"])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_stats(self, provider: str) -> TokenBudgetStats:
        if provider not in self._stats:
            self._stats[provider] = TokenBudgetStats(provider=provider)
        return self._stats[provider]


# ---------------------------------------------------------------------------
# Module-level dictionary for per-user managers (TTLCache if cachetools available)
# ---------------------------------------------------------------------------
try:
    import cachetools

    _managers: dict = cachetools.TTLCache(maxsize=10000, ttl=86400)
except ImportError:
    logger.warning(
        "[TokenBudget] cachetools not available, using plain dict for per-user manager cache."
    )
    _managers = {}


def get_budget_manager(
    custom_budgets: dict[str, dict[str, int]] | None = None,
    user_id: str = "default",
) -> TokenBudgetManager:
    """Return the per-user TokenBudgetManager."""
    global _managers
    if user_id not in _managers:
        _managers[user_id] = TokenBudgetManager(custom_budgets=custom_budgets)
        logger.info(f"[TokenBudget] TokenBudgetManager initialized for user: {user_id}")
    return _managers[user_id]
