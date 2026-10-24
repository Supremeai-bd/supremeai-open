# backend/services/dynamic_ai/provider_registry.py
"""
SupremeAI Dynamic Provider Registry
No hardcoding - all providers discovered and managed at runtime
"""

import os
import time
from dataclasses import dataclass, field
from enum import Enum

from core.logging_config import logger


class ProviderStatus(Enum):
    """Health status of a provider"""

    ACTIVE = "active"  # 🟢 Healthy, fully operational
    DEGRADED = "degraded"  # 🟡 Working but slow/limited
    DISABLED_TEMPORARY = "disabled_temporary"  # 🔴 Failed, auto-retry soon
    DISABLED_PERMANENT = "disabled_permanent"  # ⛔ Invalid key, won't retry
    NOT_CONFIGURED = "not_configured"  # ⚪ Not set up
    UNKNOWN = "unknown"  # ❓ Haven't checked yet


@dataclass
class ProviderConfig:
    """Configuration for an AI provider (loaded from env/config)"""

    provider_id: str  # e.g., "gemini", "openai"
    display_name: str  # e.g., "Google Gemini"
    api_key_env_var: str  # Environment variable name for API key
    base_url: str | None = None  # Custom base URL (for proxies)
    models: list[dict] = field(default_factory=list)  # Available models

    # Rate limits (will be updated dynamically)
    rpm_limit: int = 0  # Requests per minute limit
    rpd_limit: int = 0  # Requests per day limit

    # Current usage tracking
    requests_today: int = 0
    requests_this_minute: int = 0
    minute_window_start: float = 0.0

    # Health metrics
    status: ProviderStatus = ProviderStatus.UNKNOWN
    last_successful_request: float | None = None
    last_error: str | None = None
    last_error_time: float | None = None
    consecutive_failures: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_latency_ms: float = 0.0

    # Configuration flags
    is_free_tier: bool = True
    priority: int = 100  # Lower = higher preference
    enabled: bool = True  # Can be manually disabled

    def reset_daily_counters(self):
        """Reset daily counters (call at midnight UTC)"""
        self.requests_today = 0

    def reset_minute_counter(self):
        """Reset per-minute counter"""
        now = time.time()
        if now - self.minute_window_start >= 60:
            self.requests_this_minute = 0
            self.minute_window_start = now

    @property
    def api_key(self) -> str | None:
        """Get API key from environment (never logs the key!)"""
        key = os.getenv(self.api_key_env_var)

        # Check if key looks valid (not empty, not placeholder)
        if not key or key.strip() in ["", "none", "null", "your-key-here", "change-me"]:
            return None

        # Mask for logging (show only first 8 chars)
        return key

    @property
    def is_available(self) -> bool:
        """Check if provider is available for requests"""
        return (
            self.enabled
            and self.status in [ProviderStatus.ACTIVE, ProviderStatus.DEGRADED]
            and self.api_key is not None
        )

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        total = self.success_count + self.failure_count
        if total == 0:
            return 100.0  # Assume good until proven otherwise
        return (self.success_count / total) * 100


class ProviderRegistry:
    """
    Dynamic registry of all AI providers
    Providers are registered at startup and can be added/removed at runtime
    """

    def __init__(self):
        self._providers: dict[str, ProviderConfig] = {}
        self._initialization_complete = False
        self._last_refresh: float = 0.0
        self._refresh_interval: float = 300.0  # Refresh every 5 minutes

    async def initialize(self):
        """
        Initialize registry with known providers
        This is where we define provider templates (NOT hardcoded keys!)
        """
        logger.debug("🔄 Initializing Dynamic Provider Registry...")

        # Define provider templates (keys come from environment!)
        provider_templates = [
            # === FREE TIER PRIMARY ===
            {
                "provider_id": "gemini",
                "display_name": "Google Gemini (Free)",
                "api_key_env_var": "GEMINI_API_KEY",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "models": [
                    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "tier": "economy"},
                    {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "tier": "economy"},
                    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "tier": "standard"},
                ],
                "rpm_limit": 15,
                "rpd_limit": 1500,
                "is_free_tier": True,
                "priority": 10,  # Highest priority (free!)
            },
            {
                "provider_id": "groq",
                "display_name": "Groq (Fast Inference)",
                "api_key_env_var": "GROQ_API_KEY",
                "base_url": "https://api.groq.com/openai/v1",
                "models": [
                    {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "tier": "standard"},
                    {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "tier": "economy"},
                ],
                "rpm_limit": 30,
                "rpd_limit": 14400,
                "is_free_tier": True,
                "priority": 20,
            },
            {
                "provider_id": "bynara",
                "display_name": "Bynara Router (Free Tier)",
                "api_key_env_var": "BYNARA_API_KEY",
                "base_url": "https://router.bynara.id/v1",
                "models": [
                    {
                        "id": "agnes-2.5-flash",
                        "name": "Agnes 2.5 Flash",
                        "tier": "economy",
                        "specialty": "coding",
                    },
                    {
                        "id": "laguna-s-2.1",
                        "name": "Laguna S 2.1",
                        "tier": "standard",
                        "specialty": "reasoning",
                    },
                    {
                        "id": "stepfun-3.7-flash",
                        "name": "StepFun 3.7 Flash",
                        "tier": "economy",
                        "specialty": "general",
                    },
                    {
                        "id": "nemotron-3.5-lightning-free",
                        "name": "Nemotron 3.5 Free",
                        "tier": "economy",
                        "specialty": "quick",
                    },
                ],
                "rpm_limit": 60,
                "rpd_limit": 10000,
                "is_free_tier": True,
                "priority": 12,
            },
            {
                "provider_id": "bai",
                "display_name": "b.ai Router",
                "api_key_env_var": "BAI_API_KEY",
                "base_url": "https://api.b.ai/v1",
                "models": [
                    {
                        "id": "qwen3.8-flash",
                        "name": "Qwen 3.8 Flash",
                        "tier": "economy",
                        "specialty": "coding",
                    },
                    {
                        "id": "mimo-v2.5",
                        "name": "MiMo v2.5",
                        "tier": "economy",
                        "specialty": "general",
                    },
                    {"id": "hy3", "name": "HY3 Backup", "tier": "economy", "specialty": "backup"},
                ],
                "rpm_limit": 60,
                "rpd_limit": 10000,
                "is_free_tier": True,
                "priority": 15,
            },
            {
                "provider_id": "huggingface",
                "display_name": "HuggingFace Serverless",
                "api_key_env_var": "HF_API_KEY",
                "base_url": "https://api-inference.huggingface.co/models",
                "models": [
                    # SupremeAI Swarm Models
                    {
                        "id": "njelit1/supreme-coder-3b",
                        "name": "Supreme Coder",
                        "tier": "economy",
                        "specialty": "coding",
                    },
                    {
                        "id": "njelitltd/supreme-reasoner-3b",
                        "name": "Supreme Reasoner",
                        "tier": "economy",
                        "specialty": "reasoning",
                    },
                    {
                        "id": "ziaulhaq1/supreme-general-3b",
                        "name": "Supreme General",
                        "tier": "economy",
                        "specialty": "general",
                    },
                    {
                        "id": "njelitltd2/supreme-creative-3b",
                        "name": "Supreme Creative",
                        "tier": "economy",
                        "specialty": "creative",
                    },
                    {
                        "id": "njelitltd3/supreme-master-3b",
                        "name": "Supreme Master",
                        "tier": "standard",
                        "specialty": "complex",
                    },
                    {
                        "id": "njelltd5/supreme-vision-3b",
                        "name": "Supreme Vision",
                        "tier": "standard",
                        "specialty": "vision",
                    },
                    {
                        "id": "njelltd4/supreme-draft-0.5b",
                        "name": "Supreme Draft",
                        "tier": "economy",
                        "specialty": "quick",
                    },
                ],
                "rpm_limit": 60,  # Approximate for serverless
                "is_free_tier": True,
                "priority": 25,
            },
            # === PAID / FREEMIUM BACKUPS ===
            {
                "provider_id": "openai",
                "display_name": "OpenAI GPT",
                "api_key_env_var": "OPENAI_API_KEY",
                "base_url": "https://api.openai.com/v1",
                "models": [
                    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "tier": "economy"},
                    {"id": "gpt-4o", "name": "GPT-4o", "tier": "premium"},
                    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "tier": "premium"},
                    {
                        "id": "text-embedding-3-small",
                        "name": "Embedding v3 Small",
                        "tier": "economy",
                        "type": "embedding",
                    },
                ],
                "rpm_limit": 500,
                "rpd_limit": 10000,
                "is_free_tier": False,
                "priority": 50,
            },
            {
                "provider_id": "deepseek",
                "display_name": "DeepSeek (Cost-Efficient)",
                "api_key_env_var": "DEEPSEEK_API_KEY",
                "base_url": "https://api.deepseek.com/v1",
                "models": [
                    {"id": "deepseek-chat", "name": "DeepSeek Chat", "tier": "economy"},
                    {
                        "id": "deepseek-coder",
                        "name": "DeepSeek Coder",
                        "tier": "economy",
                        "specialty": "coding",
                    },
                ],
                "rpm_limit": 60,
                "priority": 35,
            },
            {
                "provider_id": "moonshot",
                "display_name": "Moonshot (Kimi)",
                "api_key_env_var": "MOONSHOT_API_KEY",
                "base_url": "https://api.moonshot.cn/v1",
                "models": [
                    {"id": "moonshot-v1-8k", "name": "Kimi 8K", "tier": "standard"},
                    {"id": "moonshot-v1-32k", "name": "Kimi 32K", "tier": "standard"},
                    {"id": "moonshot-v1-128k", "name": "Kimi 128K", "tier": "premium"},
                ],
                "rpm_limit": 60,
                "priority": 40,
            },
            {
                "provider_id": "together",
                "display_name": "Together AI",
                "api_key_env_var": "TOGETHER_API_KEY",
                "base_url": "https://api.together.xyz/v1",
                "models": [
                    {
                        "id": "meta-llama/Llama-3-70b-chat-hf",
                        "name": "Llama 3 70B",
                        "tier": "standard",
                    },
                ],
                "rpm_limit": 60,
                "priority": 45,
            },
            {
                "provider_id": "nvidia",
                "display_name": "NVIDIA NIM",
                "api_key_env_var": "NVIDIA_API_KEY",
                "base_url": "https://integrate.api.nvidia.com/v1",
                "models": [
                    {
                        "id": "meta/llama3-70b-instruct",
                        "name": "Llama3 70B NIM",
                        "tier": "standard",
                    },
                ],
                "rpm_limit": 60,
                "priority": 55,
            },
            {
                "provider_id": "openrouter",
                "display_name": "OpenRouter (Aggregator)",
                "api_key_env_var": "OPENROUTER_API_KEY",
                "base_url": "https://openrouter.ai/api/v1",
                "models": [
                    # OpenRouter provides access to many models
                    {
                        "id": "google/gemini-2.5-flash",
                        "name": "Gemini Flash (via OR)",
                        "tier": "economy",
                        "is_free": True,
                    },
                    {
                        "id": "meta-llama/llama-3.1-8b-instruct:free",
                        "name": "Llama 8B (via OR)",
                        "tier": "economy",
                        "is_free": True,
                    },
                ],
                "rpm_limit": 60,
                "priority": 30,
            },
        ]

        # Register all providers
        for template in provider_templates:
            config = ProviderConfig(
                provider_id=template["provider_id"],
                display_name=template["display_name"],
                api_key_env_var=template["api_key_env_var"],
                base_url=template.get("base_url"),
                models=template.get("models", []),
                rpm_limit=template.get("rpm_limit", 0),
                rpd_limit=template.get("rpd_limit", 0),
                is_free_tier=template.get("is_free_tier", True),
                priority=template.get("priority", 100),
            )

            self._providers[config.provider_id] = config

        self._initialization_complete = True
        logger.debug(f"Registry initialized with {len(self._providers)} provider templates")

    async def refresh_status(self):
        """Refresh status of all providers (check keys, update availability)"""
        if time.time() - self._last_refresh < self._refresh_interval:
            return  # Too soon to refresh

        self._last_refresh = time.time()

        for provider_id, config in self._providers.items():
            await self._check_provider_availability(config)

    async def _check_provider_availability(self, config: ProviderConfig):
        """Check if a provider's API key is valid and working

        Issue #438: auth rejections (401/403) from the key-validation endpoint are
        DEFINITIVE proof the key is invalid — they now disable the provider
        PERMANENTLY (with an actionable error message) instead of cycling through
        DISABLED_TEMPORARY every refresh interval, which re-probed the dead key
        every 5 minutes and logged 401s forever. refresh_status() already skips
        DISABLED_PERMANENT providers, so the probe storm stops after the first
        definitive rejection. Network errors and other HTTP codes keep the old
        transient-friendly behavior.
        """

        # Skip if permanently disabled
        if config.status == ProviderStatus.DISABLED_PERMANENT:
            return

        # Check if API key exists
        if not config.api_key:
            config.status = ProviderStatus.NOT_CONFIGURED
            config.last_error = f"No API key found in {config.api_key_env_var}"
            return

        # Quick validation call (lightweight endpoint)
        try:
            # Different validation methods per provider.
            # Contract (issue #438): _validate_api_key returns the provider's HTTP
            # status code, or None when there is no provider-specific probe
            # (unknown provider — assume valid if a key exists).
            status_code = await self._validate_api_key(config)

            if status_code is None or status_code == 200:
                # Determine status based on recent performance
                if config.success_rate >= 80:
                    config.status = ProviderStatus.ACTIVE
                elif config.success_rate >= 50:
                    config.status = ProviderStatus.DEGRADED
                else:
                    config.status = ProviderStatus.DEGRADED  # Give it a chance to recover
            elif status_code in (401, 403):
                # Definitive auth rejection — the key is invalid. Stop probing it.
                config.status = ProviderStatus.DISABLED_PERMANENT
                config.last_error = (
                    f"API key rejected ({status_code}) — rotate {config.api_key_env_var} "
                    "in the vault/env and restart to re-enable this provider"
                )
                config.last_error_time = time.time()
                logger.error(
                    "⛔ Provider %s DISABLED PERMANENTLY: API key rejected with HTTP %s. "
                    "Fix: rotate %s. (No further probes until restart.)",
                    config.provider_id,
                    status_code,
                    config.api_key_env_var,
                )
            else:
                config.status = ProviderStatus.DISABLED_TEMPORARY
                config.last_error = f"API key validation failed (HTTP {status_code})"
                config.last_error_time = time.time()

        except Exception as e:
            config.last_error = str(e)
            config.last_error_time = time.time()
            # Don't change status on network errors (might be transient)

    async def _validate_api_key(self, config: ProviderConfig) -> int | None:
        """
        Validate API key without making expensive calls.

        Returns the provider's HTTP status code for the lightweight probe
        endpoint, or None when no provider-specific probe exists (unknown
        provider — treated as valid when a key is present).

        বাংলা: হালকা এন্ডপয়েন্ট দিয়ে কী ভ্যালিডেশন — HTTP স্ট্যাটাস কোড রিটার্ন করে
        যাতে ৪০১/৪০৩ (কী অবৈধ) ও অন্যান্য ত্রুটি আলাদা করা যায় (issue #438)।
        """
        from utils.http_client import create_async_client

        # Provider-specific validation logic
        if config.provider_id == "gemini":
            # Gemini: Try to list models (lightweight call)
            async with create_async_client(timeout=10.0) as client:
                resp = await client.get(
                    f"{config.base_url}/models?key={config.api_key}",
                    headers={"Content-Type": "application/json"},
                )
                return resp.status_code

        elif config.provider_id in ["openai", "deepseek", "moonshot", "together", "nvidia", "groq"]:
            # OpenAI-compatible: Try models list
            async with create_async_client(timeout=10.0) as client:
                resp = await client.get(
                    f"{config.base_url}/models",
                    headers={
                        "Authorization": f"Bearer {config.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                return resp.status_code

        elif config.provider_id == "huggingface":
            # HF: Simple authenticated request
            async with create_async_client(timeout=10.0) as client:
                resp = await client.get(
                    f"{config.base_url}", headers={"Authorization": f"Bearer {config.api_key}"}
                )
                return resp.status_code

        elif config.provider_id == "openrouter":
            # OpenRouter: Check credits/key validity
            async with create_async_client(timeout=10.0) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={"Authorization": f"Bearer {config.api_key}"},
                )
                return resp.status_code

        # Unknown provider - assume valid if key exists
        return None

    def get_provider(self, provider_id: str) -> ProviderConfig | None:
        """Get provider by ID"""
        return self._providers.get(provider_id)

    def get_available_providers(self, require_free_tier: bool = False) -> list[ProviderConfig]:
        """
        Get list of currently available providers
        Sorted by priority (best first)
        """
        available = []

        for config in self._providers.values():
            if config.is_available:
                if require_free_tier and not config.is_free_tier:
                    continue
                available.append(config)

        # Sort by priority (lower = better), then by success rate
        available.sort(key=lambda p: (p.priority, -p.success_rate))

        return available

    def get_all_providers(self) -> dict[str, ProviderConfig]:
        """Get all providers (including unavailable ones)"""
        return self._providers.copy()

    def record_success(self, provider_id: str, latency_ms: float):
        """Record a successful request"""
        config = self._providers.get(provider_id)
        if config:
            config.success_count += 1
            config.consecutive_failures = 0
            config.last_successful_request = time.time()
            config.requests_today += 1
            config.reset_minute_counter()
            config.requests_this_minute += 1

            # Update rolling average latency
            if config.avg_latency_ms == 0:
                config.avg_latency_ms = latency_ms
            else:
                config.avg_latency_ms = 0.9 * config.avg_latency_ms + 0.1 * latency_ms

    def record_failure(self, provider_id: str, error: str):
        """Record a failed request"""
        config = self._providers.get(provider_id)
        if config:
            config.failure_count += 1
            config.consecutive_failures += 1
            config.last_error = error
            config.last_error_time = time.time()

            # Issue #438: a request-time 401/403 is definitive auth evidence —
            # disable permanently immediately instead of burning through the
            # 3→temporary / 10→permanent ladder (each intermediate step kept
            # re-probing the dead key every refresh interval).
            error_lower = str(error).lower()
            if "api error 401" in error_lower or "api error 403" in error_lower:
                config.status = ProviderStatus.DISABLED_PERMANENT
                logger.error(
                    "⛔ Provider %s DISABLED PERMANENTLY after auth error (401/403) at "
                    "request time. Fix: rotate its API key, then restart or call "
                    "enable_provider(). Error: %s",
                    provider_id,
                    str(error)[:160],
                )
                return

            # Auto-degrade after consecutive failures
            if config.consecutive_failures >= 3:
                if config.consecutive_failures >= 10:
                    # Too many failures - might be invalid key
                    config.status = ProviderStatus.DISABLED_PERMANENT
                    logger.debug(f"⛔ Provider {provider_id} disabled permanently (invalid key?)")
                else:
                    config.status = ProviderStatus.DISABLED_TEMPORARY
                    logger.debug(
                        f"🔴 Provider {provider_id} temporarily disabled ({config.consecutive_failures} failures)"
                    )

    def enable_provider(self, provider_id: str):
        """Manually re-enable a provider"""
        config = self._providers.get(provider_id)
        if config:
            config.enabled = True
            config.consecutive_failures = 0
            config.status = ProviderStatus.UNKNOWN  # Will be re-checked on next refresh
            logger.debug(f"Provider {provider_id} re-enabled")

    def disable_provider(self, provider_id: str, permanent: bool = False):
        """Manually disable a provider"""
        config = self._providers.get(provider_id)
        if config:
            config.enabled = False
            config.status = (
                ProviderStatus.DISABLED_PERMANENT
                if permanent
                else ProviderStatus.DISABLED_TEMPORARY
            )
            logger.debug(
                f"🚫 Provider {provider_id} disabled ({'permanent' if permanent else 'temporary'})"
            )

    def get_status_summary(self) -> dict:
        """Get summary of all provider statuses"""
        summary = {
            "total_providers": len(self._providers),
            "active": 0,
            "degraded": 0,
            "disabled_temporary": 0,
            "disabled_permanent": 0,
            "not_configured": 0,
            "providers": {},
        }

        for provider_id, config in self._providers.items():
            status = config.status.value
            if status in summary:
                summary[status] += 1

            summary["providers"][provider_id] = {
                "display_name": config.display_name,
                "status": status,
                "has_api_key": config.api_key is not None,
                "success_rate": round(config.success_rate, 1),
                "avg_latency_ms": round(config.avg_latency_ms, 1),
                "requests_today": config.requests_today,
                "is_free_tier": config.is_free_tier,
                "priority": config.priority,
            }

        return summary
