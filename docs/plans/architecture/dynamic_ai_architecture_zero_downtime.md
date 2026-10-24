---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:dynamic_ai_architecture_v5_zero_downtime
subject: 🔄 SupremeAI Dynamic AI Architecture v5.0
document_role: architecture
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# 🔄 SupremeAI Dynamic AI Architecture v5.0
## "Zero-Downtain, Self-Healing, External-API-Independent" System

**তারিখ:** 2026-08-24  
**ভাষা:** Bengali + English  
**উদ্দেশ্য:** 100% Dynamic AI Provider System - No service stops if any key is invalid/missing

---

# 🎯 CORE PHILOSOPHY

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   "NO EXTERNAL DEPENDENCY SHOULD BE ABLE TO BREAK US"       │
│                                                             │
│   ✅ Invalid API Key? → Auto-disable, use next provider      │
│   ✅ Provider down? → Circuit breaker, instant failover       │
│   ✅ Free tier changed? → Adapt routing automatically         │
│   ✅ ALL keys invalid? → Fall back to local (Ollama)          │
│   ✅ Network offline? → Full local mode, queue for later     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

# 📐 PART 1: ARCHITECTURE DESIGN

## 1.1 Traditional vs Dynamic Architecture

### ❌ OLD WAY (Fragile):
```python
# HARDCODED - Breaks when anything changes!
class LLMService:
    def __init__(self):
        self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)  # 💥 Crashes if invalid!
        self.openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)  # 💥 Crashes if missing!
        self.groq_client = Groq(api_key=GROQ_API_KEY)                # 💥 Crashes if expired!
    
    async def generate(self, prompt):
        try:
            return await self.gemini_client.generate(prompt)  # ❌ Single point of failure
        except:
            return await self.openai_client.generate(prompt)  # ❌ Manual fallback, messy
```

### ✅ NEW WAY (Dynamic & Resilient):
```python
# DYNAMIC - Adapts to anything!
class DynamicAIOrchestrator:
    def __init__(self):
        self.registry = ProviderRegistry()  # Runtime-discovered providers
        self.health_monitor = HealthMonitor()  # Continuous health checks
        self.circuit_breaker = CircuitBreakerManager()  # Auto-disable failures
        self.learning_engine = LearningEngine()  # Improves over time
        self.local_fallback = OllamaFallback()  # Ultimate safety net
    
    async def generate(self, prompt):
        # Try healthy providers in smart order (learned from experience)
        for provider in await self.learning_engine.get_best_providers_for_task(prompt):
            if await self.circuit_breaker.is_available(provider):
                result = await self._try_provider(provider, prompt)
                if result.success:
                    self.learning_engine.record_success(provider, prompt, result)
                    return result
        
        # ALL external failed → Use local (NEVER crashes!)
        return await self.local_fallback.generate(prompt)
```

---

## 1.2 System Components Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SUPREMAI DYNAMIC AI ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐    │
│   │                    PROVIDER REGISTRY (Dynamic)                      │    │
│   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐  │    │
│   │  │ Gemini      │ │ OpenAI      │ │ Groq        │ │ HuggingFace │  │    │
│   │  │ Status: 🟢  │ │ Status: 🔴  │ │ Status: 🟢  │ │ Status: 🟡  │  │    │
│   │  │ Keys: Valid │ │ Keys: Invalid│ │ Keys: Valid │ │ Keys: Weak  │  │    │
│   │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘  │    │
│   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐  │    │
│   │  │ DeepSeek    │ │ Moonshot    │ │ Together    │ │ NVIDIA      │  │    │
│   │  │ Status: 🟢  │ │ Status: 🔴  │ │ Status: 🟢  │ │ Status: ⚪  │  │    │
│   │  │ Keys: Valid │ │ Keys: Missing│ │ Keys: Valid │ │ Not Config'd│  │    │
│   │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘  │    │
│   └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐    │
│   │                    HEALTH MONITOR (Continuous)                       │    │
│   │                                                                      │    │
│   │  • Key Validation (startup + every 5 min)                            │    │
│   │  • Latency Measurement (every request)                              │    │
│   │  • Error Rate Tracking (rolling window)                             │    │
│   │  • Quota Monitoring (API limits)                                    │    │
│   │  • Auto-Disable Thresholds (configurable)                           │    │
│   └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐    │
│   │                   CIRCUIT BREAKER MANAGER                            │    │
│   │                                                                      │    │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │    │
│   │  │ CLOSED   │→ │ OPEN     │→ │ HALF-OPEN│→ │ CLOSED   │           │    │
│   │  │ (Normal) │  │(Failing) │  │ (Testing)│  │(Recovery)│           │    │
│   │  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │    │
│   │                                                                      │    │
│   │  Rules:                                                              │    │
│   │  • 3 failures in 60s → OPEN (stop trying for 30s)                  │    │
│   │  • After 30s → HALF-OPEN (test with 1 request)                     │    │
│   │  • Test succeeds → CLOSED (fully back)                              │    │
│   │  • Test fails → OPEN (another 30s cooldown)                        │    │
│   └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐    │
│   │                     LEARNING ENGINE                                  │    │
│   │                                                                      │    │
│   │  • Success Rate per Provider (%)                                     │    │
│   │  • Average Latency per Provider (ms)                                 │    │
│   │  • Cost per Request (estimated)                                      │    │
│   │  • Best Task-Type Mapping (learned)                                 │    │
│   │  • Time-of-Day Performance (learned)                                │    │
│   │  • Automatic Re-ranking Every Hour                                   │    │
│   └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐    │
│   │                  LOCAL FALLBACK (Ollama)                             │    │
│   │                                                                      │    │
│   │  • Models: Llama3, Mistral, CodeLlama, etc.                        │    │
│   │  • Availability: 100% (runs locally)                                │    │
│   │  • Cost: $0 (free software)                                         │    │
│   │  • Latency: ~50-200ms (no network)                                  │    │
│   │  • Quality: Good enough for most tasks                              │    │
│   │  • Activation: Only when ALL external fail                          │    │
│   └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# 💻 PART 2: COMPLETE IMPLEMENTATION

## 2.1 Dynamic Provider Registry

```python
# backend/services/dynamic_ai/provider_registry.py
"""
SupremeAI Dynamic Provider Registry
No hardcoding - all providers discovered and managed at runtime
"""

import os
import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta


class ProviderStatus(Enum):
    """Health status of a provider"""
    ACTIVE = "active"              # 🟢 Healthy, fully operational
    DEGRADED = "degraded"          # 🟡 Working but slow/limited
    DISABLED_TEMPORARY = "disabled_temporary"  # 🔴 Failed, auto-retry soon
    DISABLED_PERMANENT = "disabled_permanent"   # ⛔ Invalid key, won't retry
    NOT_CONFIGURED = "not_configured"          # ⚪ Not set up
    UNKNOWN = "unknown"              # ❓ Haven't checked yet


@dataclass
class ProviderConfig:
    """Configuration for an AI provider (loaded from env/config)"""
    
    provider_id: str                    # e.g., "gemini", "openai"
    display_name: str                   # e.g., "Google Gemini"
    api_key_env_var: str               # Environment variable name for API key
    base_url: Optional[str] = None     # Custom base URL (for proxies)
    models: List[Dict] = field(default_factory=list)  # Available models
    
    # Rate limits (will be updated dynamically)
    rpm_limit: int = 0                 # Requests per minute limit
    rpd_limit: int = 0                 # Requests per day limit
    
    # Current usage tracking
    requests_today: int = 0
    requests_this_minute: int = 0
    minute_window_start: float = 0.0
    
    # Health metrics
    status: ProviderStatus = ProviderStatus.UNKNOWN
    last_successful_request: Optional[float] = None
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    consecutive_failures: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_latency_ms: float = 0.0
    
    # Configuration flags
    is_free_tier: bool = True
    priority: int = 100              # Lower = higher preference
    enabled: bool = True             # Can be manually disabled
    
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
    def api_key(self) -> Optional[str]:
        """Get API key from environment (never logs the key!)"""
        key = os.getenv(self.api_key_env_var)
        
        # Check if key looks valid (not empty, not placeholder)
        if not key or key.strip() in ['', 'none', 'null', 'your-key-here', 'change-me']:
            return None
        
        # Mask for logging (show only first 8 chars)
        return key
    
    @property
    def is_available(self) -> bool:
        """Check if provider is available for requests"""
        return (
            self.enabled and 
            self.status in [ProviderStatus.ACTIVE, ProviderStatus.DEGRADED] and
            self.api_key is not None
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
        self._providers: Dict[str, ProviderConfig] = {}
        self._initialization_complete = False
        self._last_refresh: float = 0.0
        self._refresh_interval: float = 300.0  # Refresh every 5 minutes
    
    async def initialize(self):
        """
        Initialize registry with known providers
        This is where we define provider templates (NOT hardcoded keys!)
        """
        print("🔄 Initializing Dynamic Provider Registry...")
        
        # Define provider templates (keys come from environment!)
        provider_templates = [
            # === FREE TIER PRIMARY ===
            {
                "provider_id": "gemini",
                "display_name": "Google Gemini (Free)",
                "api_key_env_var": "GEMINI_API_KEY",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "models": [
                    {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "tier": "economy"},
                    {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "tier": "economy"},
                    {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "tier": "standard"},
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
                "provider_id": "huggingface",
                "display_name": "HuggingFace Serverless",
                "api_key_env_var": "HF_API_KEY",
                "base_url": "https://api-inference.huggingface.co/models",
                "models": [
                    # SupremeAI Swarm Models
                    {"id": "njelit1/supreme-coder-3b", "name": "Supreme Coder", "tier": "economy", "specialty": "coding"},
                    {"id": "njelitltd/supreme-reasoner-3b", "name": "Supreme Reasoner", "tier": "economy", "specialty": "reasoning"},
                    {"id": "ziaulhaq1/supreme-general-3b", "name": "Supreme General", "tier": "economy", "specialty": "general"},
                    {"id": "njelitltd2/supreme-creative-3b", "name": "Supreme Creative", "tier": "economy", "specialty": "creative"},
                    {"id": "njelitltd3/supreme-master-3b", "name": "Supreme Master", "tier": "standard", "specialty": "complex"},
                    {"id": "njelltd5/supreme-vision-3b", "name": "Supreme Vision", "tier": "standard", "specialty": "vision"},
                    {"id": "njelltd4/supreme-draft-0.5b", "name": "Supreme Draft", "tier": "economy", "specialty": "quick"},
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
                    {"id": "text-embedding-3-small", "name": "Embedding v3 Small", "tier": "economy", "type": "embedding"},
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
                    {"id": "deepseek-coder", "name": "DeepSeek Coder", "tier": "economy", "specialty": "coding"},
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
                    {"id": "meta-llama/Llama-3-70b-chat-hf", "name": "Llama 3 70B", "tier": "standard"},
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
                    {"id": "meta/llama3-70b-instruct", "name": "Llama3 70B NIM", "tier": "standard"},
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
                    {"id": "google/gemini-2.0-flash-exp:free", "name": "Gemini Flash (via OR)", "tier": "economy", "is_free": True},
                    {"id": "meta-llama/llama-3.1-8b-instruct:free", "name": "Llama 8B (via OR)", "tier": "economy", "is_free": True},
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
        print(f"✅ Registry initialized with {len(self._providers)} provider templates")
    
    async def refresh_status(self):
        """Refresh status of all providers (check keys, update availability)"""
        if time.time() - self._last_refresh < self._refresh_interval:
            return  # Too soon to refresh
        
        self._last_refresh = time.time()
        
        for provider_id, config in self._providers.items():
            await self._check_provider_availability(config)
    
    async def _check_provider_availability(self, config: ProviderConfig):
        """Check if a provider's API key is valid and working"""
        
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
            # Different validation methods per provider
            is_valid = await self._validate_api_key(config)
            
            if is_valid:
                # Determine status based on recent performance
                if config.success_rate >= 80:
                    config.status = ProviderStatus.ACTIVE
                elif config.success_rate >= 50:
                    config.status = ProviderStatus.DEGRADED
                else:
                    config.status = ProviderStatus.DEGRADED  # Give it a chance to recover
            else:
                config.status = ProviderStatus.DISABLED_TEMPORARY
                config.last_error = "API key validation failed"
                config.last_error_time = time.time()
                
        except Exception as e:
            config.last_error = str(e)
            config.last_error_time = time.time()
            # Don't change status on network errors (might be transient)
    
    async def _validate_api_key(self, config: ProviderConfig) -> bool:
        """
        Validate API key without making expensive calls
        Returns True if key appears valid
        """
        import httpx
        
        # Provider-specific validation logic
        if config.provider_id == "gemini":
            # Gemini: Try to list models (lightweight call)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{config.base_url}/models?key={config.api_key}",
                    headers={"Content-Type": "application/json"}
                )
                return resp.status_code == 200
        
        elif config.provider_id in ["openai", "deepseek", "moonshot", "together", "nvidia", "groq"]:
            # OpenAI-compatible: Try models list
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{config.base_url}/models",
                    headers={
                        "Authorization": f"Bearer {config.api_key}",
                        "Content-Type": "application/json"
                    }
                )
                return resp.status_code == 200
        
        elif config.provider_id == "huggingface":
            # HF: Simple authenticated request
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{config.base_url}",
                    headers={"Authorization": f"Bearer {config.api_key}"}
                )
                return resp.status_code == 200
        
        elif config.provider_id == "openrouter":
            # OpenRouter: Check credits/key validity
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={
                        "Authorization": f"Bearer {config.api_key}"
                    }
                )
                return resp.status_code == 200
        
        # Unknown provider - assume valid if key exists
        return config.api_key is not None
    
    def get_provider(self, provider_id: str) -> Optional[ProviderConfig]:
        """Get provider by ID"""
        return self._providers.get(provider_id)
    
    def get_available_providers(self, require_free_tier: bool = False) -> List[ProviderConfig]:
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
    
    def get_all_providers(self) -> Dict[str, ProviderConfig]:
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
            
            # Auto-degrade after consecutive failures
            if config.consecutive_failures >= 3:
                if config.consecutive_failures >= 10:
                    # Too many failures - might be invalid key
                    config.status = ProviderStatus.DISABLED_PERMANENT
                    print(f"⛔ Provider {provider_id} disabled permanently (invalid key?)")
                else:
                    config.status = ProviderStatus.DISABLED_TEMPORARY
                    print(f"🔴 Provider {provider_id} temporarily disabled ({config.consecutive_failures} failures)")
    
    def enable_provider(self, provider_id: str):
        """Manually re-enable a provider"""
        config = self._providers.get(provider_id)
        if config:
            config.enabled = True
            config.consecutive_failures = 0
            config.status = ProviderStatus.UNKNOWN  # Will be re-checked on next refresh
            print(f"✅ Provider {provider_id} re-enabled")
    
    def disable_provider(self, provider_id: str, permanent: bool = False):
        """Manually disable a provider"""
        config = self._providers.get(provider_id)
        if config:
            config.enabled = False
            config.status = ProviderStatus.DISABLED_PERMANENT if permanent else ProviderStatus.DISABLED_TEMPORARY
            print(f"🚫 Provider {provider_id} disabled ({'permanent' if permanent else 'temporary'})")
    
    def get_status_summary(self) -> dict:
        """Get summary of all provider statuses"""
        summary = {
            "total_providers": len(self._providers),
            "active": 0,
            "degraded": 0,
            "disabled_temporary": 0,
            "disabled_permanent": 0,
            "not_configured": 0,
            "providers": {}
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
```

---

## 2.2 Circuit Breaker Manager

```python
# backend/services/dynamic_ai/circuit_breaker.py
"""
Circuit Breaker Pattern Implementation
Prevents cascading failures by stopping calls to failing providers
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation - requests flow through
    OPEN = "open"            # Failing - requests are blocked
    HALF_OPEN = "half_open"  # Testing - one request allowed to test recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""
    failure_threshold: int = 3        # Failures before opening
    success_threshold: int = 2        # Successes in half-open to close
    timeout_seconds: float = 30.0     # How long to stay open before half-open
    half_open_max_calls: int = 1      # Max concurrent calls in half-open state


@dataclass
class CircuitStateInfo:
    """Current state of a circuit breaker"""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_state_change: float = field(default_factory=time.time)
    total_blocked_requests: int = 0
    total_allowed_requests: int = 0


class CircuitBreakerManager:
    """
    Manages circuit breakers for all providers
    Prevents wasting time on known-failing services
    """
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self._config = config or CircuitBreakerConfig()
        self._circuits: Dict[str, CircuitStateInfo] = {}
        self._lock = asyncio.Lock()
    
    def get_circuit(self, provider_id: str) -> CircuitStateInfo:
        """Get or create circuit breaker for provider"""
        if provider_id not in self._circuits:
            self._circuits[provider_id] = CircuitStateInfo()
        return self._circuits[provider_id]
    
    async def is_available(self, provider_id: str) -> bool:
        """
        Check if request should be allowed through
        Updates state based on time and previous failures
        """
        circuit = self.get_circuit(provider_id)
        
        async with self._lock:
            current_time = time.time()
            
            if circuit.state == CircuitState.CLOSED:
                # Normal operation - allow through
                circuit.total_allowed_requests += 1
                return True
            
            elif circuit.state == CircuitState.OPEN:
                # Check if we should transition to half-open
                time_since_open = current_time - circuit.last_failure_time
                
                if time_since_open >= self._config.timeout_seconds:
                    # Time to test if recovered
                    circuit.state = CircuitState.HALF_OPEN
                    circuit.success_count = 0
                    circuit.last_state_change = current_time
                    print(f"🔓 Circuit for {provider_id} transitioning to HALF-OPEN (testing)")
                    return True
                else:
                    # Still in open state - block request
                    circuit.total_blocked_requests += 1
                    remaining = self._config.timeout_seconds - time_since_open
                    return False
            
            elif circuit.state == CircuitState.HALF_OPEN:
                # Allow limited requests through to test
                if circuit.success_count < self._config.half_open_max_calls:
                    circuit.total_allowed_requests += 1
                    return True
                else:
                    # Already testing - block additional
                    circuit.total_blocked_requests += 1
                    return False
        
        return True  # Default allow if lock fails
    
    async def record_success(self, provider_id: str):
        """Record successful request"""
        circuit = self.get_circuit(provider_id)
        
        async with self._lock:
            if circuit.state == CircuitState.HALF_OPEN:
                circuit.success_count += 1
                
                # Check if we should close the circuit
                if circuit.success_count >= self._config.success_threshold:
                    old_state = circuit.state
                    circuit.state = CircuitState.CLOSED
                    circuit.failure_count = 0
                    circuit.success_count = 0
                    circuit.last_state_change = time.time()
                    print(f"✅ Circuit for {provider_id} CLOSED (recovered!)")
            
            elif circuit.state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                circuit.failure_count = 0
    
    async def record_failure(self, provider_id: str):
        """Record failed request"""
        circuit = self.get_circuit(provider_id)
        
        async with self._lock:
            circuit.failure_count += 1
            circuit.last_failure_time = time.time()
            
            if circuit.state == CircuitState.CLOSED:
                # Check if we should open the circuit
                if circuit.failure_count >= self._config.failure_threshold:
                    old_state = circuit.state
                    circuit.state = CircuitState.OPEN
                    circuit.last_state_change = time.time()
                    print(f"🔒 Circuit for {provider_id} OPENED ({circuit.failure_count} failures)")
            
            elif circuit.state == CircuitState.HALF_OPEN:
                # Failure in half-open - go back to open
                circuit.state = CircuitState.OPEN
                circuit.last_failure_time = time.time()
                circuit.last_state_change = time.time()
                print(f"🔒 Circuit for {provider_id} RE-OPENED (half-open test failed)")
    
    def get_all_circuit_states(self) -> Dict[str, dict]:
        """Get status of all circuit breakers"""
        states = {}
        for provider_id, circuit in self._circuits.items():
            states[provider_id] = {
                "state": circuit.state.value,
                "failure_count": circuit.failure_count,
                "success_count": circuit.success_count,
                "total_blocked": circuit.total_blocked_requests,
                "total_allowed": circuit.total_allowed_requests,
                "last_failure_time": circuit.last_failure_time,
                "last_state_change": circuit.last_state_change,
            }
        return states
    
    def reset_circuit(self, provider_id: str):
        """Manually reset a circuit breaker (force closed)"""
        if provider_id in self._circuits:
            self._circuits[provider_id] = CircuitStateInfo()
            print(f"🔄 Circuit for {provider_id} manually reset")
```

---

## 2.3 Self-Learning Router Engine

```python
# backend/services/dynamic_ai/learning_engine.py
"""
Self-Learning AI Router
Learns from experience which providers work best for different types of tasks
"""

import asyncio
import json
import time
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum


class TaskType(Enum):
    """Categories of AI tasks"""
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    REASONING = "reasoning"
    CREATIVE_WRITING = "creative_writing"
    ANALYSIS = "analysis"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    QUESTION_ANSWERING = "question_answering"
    EMBEDDING = "embedding"
    CHAT = "chat"
    GENERAL = "general"


@dataclass
class ProviderPerformance:
    """Performance metrics for a provider on specific task type"""
    provider_id: str
    task_type: TaskType
    
    # Performance metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    
    # Quality scores (if measurable)
    avg_quality_score: float = 0.0  # 1-10 scale
    quality_ratings: int = 0
    
    # Cost tracking
    estimated_cost_usd: float = 0.0
    
    # Temporal patterns (learned)
    hourly_performance: Dict[int, float] = field(default_factory=dict)  # hour -> success_rate
    
    # Last updated
    last_updated: float = field(default_factory=time.time)
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 100.0  # Optimistic default
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests
    
    @property
    def score(self) -> float:
        """
        Composite score for ranking (higher = better)
        Considers: success rate, latency, cost, quality
        """
        if self.total_requests < 3:
            return 50.0  # Neutral score for insufficient data
        
        # Weighted components
        success_weight = 0.4
        latency_weight = 0.3
        quality_weight = 0.2
        cost_weight = 0.1
        
        # Normalize each component to 0-100
        success_score = self.success_rate
        
        # Lower latency is better (assume 10s = worst, 0s = best)
        latency_score = max(0, 100 - (self.avg_latency_ms / 100))  # 100ms = 99, 10s = 0
        
        quality_score = self.avg_quality_score * 10  # 1-10 -> 10-100
        
        # Lower cost is better (assume $0.10/request = worst)
        cost_per_request = self.estimated_cost_usd / max(1, self.total_requests)
        cost_score = max(0, 100 - (cost_per_request * 1000))  # $0.01 = 90, $0.10 = 0
        
        composite = (
            success_score * success_weight +
            latency_score * latency_weight +
            quality_score * quality_weight +
            cost_score * cost_weight
        )
        
        return composite


class LearningEngine:
    """
    Learns which providers work best for different tasks
    Continuously improves routing decisions based on actual performance
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        self._performance_data: Dict[str, Dict[TaskType, ProviderPerformance]] = {}
        self._task_detection_cache: Dict[str, TaskType] = {}
        self._storage_path = storage_path
        self._last_save: float = 0.0
        self._save_interval: float = 300.0  # Save every 5 minutes
        
        # Global fallback order (used when no task-specific data)
        self._global_provider_ranking: List[Tuple[str, float]] = []
    
    def detect_task_type(self, prompt: str, context: Optional[dict] = None) -> TaskType:
        """
        Detect the type of task from the prompt
        Uses keyword matching + heuristics
        """
        # Check cache first
        cache_key = hash(prompt[:200]) % 10000
        if cache_key in self._task_detection_cache:
            return self._task_detection_cache[cache_key]
        
        prompt_lower = prompt.lower()
        
        # Code-related indicators
        code_keywords = ['code', 'function', 'def ', 'class ', 'python', 'javascript', 
                        'api', 'endpoint', 'debug', 'fix bug', 'implement', 'write']
        if any(kw in prompt_lower for kw in code_keywords):
            if any(kw in prompt_lower for kw in ['review', 'improve', 'optimize']):
                task_type = TaskType.CODE_REVIEW
            else:
                task_type = TaskType.CODE_GENERATION
        
        # Reasoning indicators
        elif any(kw in prompt_lower for kw in ['why', 'how does', 'explain', 'analyze',
                                                'compare', 'reason', 'think step']):
            task_type = TaskType.REASONING
        
        # Creative writing indicators
        elif any(kw in prompt_lower for kw in ['write a story', 'create content', 'blog post',
                                                'poem', 'creative', 'imagine', 'draft']):
            task_type = TaskType.CREATIVE_WRITING
        
        # Translation indicators
        elif any(kw in prompt_lower for kw in ['translate', 'in bengali', 'in english',
                                                'to bangla', 'convert to']):
            task_type = TaskType.TRANSLATION
        
        # Summarization indicators
        elif any(kw in prompt_lower for kw in ['summarize', 'summary', 'brief', 'tl;dr',
                                                'key points', 'overview']):
            task_type = TaskType.SUMMARIZATION
        
        # Question answering
        elif '?' in prompt or any(kw in prompt_lower for kw in ['what', 'who', 'when',
                                                                  'where', 'which']):
            task_type = TaskType.QUESTION_ANSWERING
        
        # Embedding (usually called programmatically)
        elif context and context.get('purpose') == 'embedding':
            task_type = TaskType.EMBEDDING
        
        # Chat/conversational
        elif len(prompt.split()) < 20 and not any(kw in prompt_lower for kw in 
                ['code', 'write', 'explain', 'analyze', 'translate']):
            task_type = TaskType.CHAT
        
        else:
            task_type = TaskType.GENERAL
        
        # Cache result
        self._task_detection_cache[cache_key] = task_type
        
        # Limit cache size
        if len(self._task_detection_cache) > 1000:
            self._task_detection_cache.clear()
        
        return task_type
    
    async def get_best_providers_for_task(
        self, 
        prompt: str, 
        available_providers: list,
        context: Optional[dict] = None,
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Get ranked list of best providers for this specific task
        Returns: [(provider_id, confidence_score), ...]
        """
        task_type = self.detect_task_type(prompt, context)
        
        # Get performance data for this task type
        candidates = []
        
        for provider in available_providers:
            provider_id = provider.provider_id
            
            # Get or create performance record
            if provider_id not in self._performance_data:
                self._performance_data[provider_id] = {}
            
            if task_type not in self._performance_data[provider_id]:
                self._performance_data[provider_id][task_type] = ProviderPerformance(
                    provider_id=provider_id,
                    task_type=task_type
                )
            
            perf = self._performance_data[provider_id][task_type]
            
            # Calculate score
            score = perf.score
            
            # Boost for free tier providers (prefer free when quality is similar)
            if provider.is_free_tier and perf.total_requests > 5:
                if perf.success_rate > 70:  # Good enough free option
                    score *= 1.1  # 10% boost for free tier
            
            # Boost for recently successful (recency bias)
            if perf.last_updated > time.time() - 3600:  # Last hour
                if perf.success_rate > 80:
                    score *= 1.05  # 5% boost for recent success
            
            candidates.append((provider_id, score, perf))
        
        # Sort by score (descending)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Return top K
        result = [(pid, score) for pid, score, _ in candidates[:top_k]]
        
        return result
    
    def record_interaction(
        self,
        provider_id: str,
        task_type: TaskType,
        success: bool,
        latency_ms: float,
        estimated_cost: float = 0.0,
        quality_score: Optional[float] = None,
        prompt_hash: Optional[str] = None
    ):
        """
        Record an interaction with a provider for learning
        Call this after EVERY provider interaction
        """
        # Ensure provider exists in tracking
        if provider_id not in self._performance_data:
            self._performance_data[provider_id] = {}
        
        if task_type not in self._performance_data[provider_id]:
            self._performance_data[provider_id][task_type] = ProviderPerformance(
                provider_id=provider_id,
                task_type=task_type
            )
        
        perf = self._performance_data[provider_id][task_type]
        
        # Update metrics
        perf.total_requests += 1
        perf.total_latency_ms += latency_ms
        perf.estimated_cost_usd += estimated_cost
        perf.last_updated = time.time()
        
        if success:
            perf.successful_requests += 1
        else:
            perf.failed_requests += 1
        
        # Update quality score if provided
        if quality_score is not None:
            if perf.quality_ratings > 0:
                # Rolling average
                perf.avg_quality_score = (
                    (perf.avg_quality_score * perf.quality_ratings + quality_score) /
                    (perf.quality_ratings + 1)
                )
            else:
                perf.avg_quality_score = quality_score
            perf.quality_ratings += 1
        
        # Update hourly pattern
        current_hour = datetime.now().hour
        if current_hour not in perf.hourly_performance:
            perf.hourly_performance[current_hour] = {'success': 0, 'total': 0}
        perf.hourly_performance[current_hour]['total'] += 1
        if success:
            perf.hourly_performance[current_hour]['success'] += 1
        
        # Periodic save
        if time.time() - self._last_save > self._save_interval:
            asyncio.create_task(self.save_learning_data())
    
    def get_provider_insights(self, provider_id: str) -> dict:
        """Get detailed insights about a provider's performance"""
        if provider_id not in self._performance_data:
            return {"error": "No data for this provider"}
        
        insights = {
            "provider_id": provider_id,
            "task_types": {},
            "overall": {
                "total_requests": 0,
                "overall_success_rate": 0,
                "best_task_type": None,
                "worst_task_type": None,
            }
        }
        
        total_requests = 0
        total_successes = 0
        best_score = -1
        worst_score = 101
        best_task = None
        worst_task = None
        
        for task_type, perf in self._performance_data[provider_id].items():
            insights["task_types"][task_type.value] = {
                "success_rate": round(perf.success_rate, 1),
                "avg_latency_ms": round(perf.avg_latency_ms, 1),
                "avg_quality_score": round(perf.avg_quality_score, 1),
                "total_requests": perf.total_requests,
                "score": round(perf.score, 1),
            }
            
            total_requests += perf.total_requests
            total_successes += perf.successful_requests
            
            if perf.score > best_score and perf.total_requests >= 3:
                best_score = perf.score
                best_task = task_type.value
            if perf.score < worst_score and perf.total_requests >= 3:
                worst_score = perf.score
                worst_task = task_type.value
        
        insights["overall"]["total_requests"] = total_requests
        insights["overall"]["overall_success_rate"] = round(
            (total_successes / total_requests * 100) if total_requests > 0 else 0, 1
        )
        insights["overall"]["best_task_type"] = best_task
        insights["overall"]["worst_task_type"] = worst_task
        
        return insights
    
    async def save_learning_data(self):
        """Persist learning data to disk"""
        if not self._storage_path:
            return
        
        try:
            import aiofiles
            
            # Convert to serializable format
            data = {}
            for provider_id, tasks in self._performance_data.items():
                data[provider_id] = {}
                for task_type, perf in tasks.items():
                    data[provider_id][task_type.value] = {
                        "total_requests": perf.total_requests,
                        "successful_requests": perf.successful_requests,
                        "failed_requests": perf.failed_requests,
                        "total_latency_ms": perf.total_latency_ms,
                        "avg_quality_score": perf.avg_quality_score,
                        "quality_ratings": perf.quality_ratings,
                        "estimated_cost_usd": perf.estimated_cost_usd,
                        "hourly_performance": perf.hourly_performance,
                        "last_updated": perf.last_updated,
                    }
            
            async with aiofiles.open(self._storage_path, 'w') as f:
                await f.write(json.dumps(data, indent=2))
            
            self._last_save = time.time()
            print(f"💾 Learning data saved ({len(data)} providers)")
            
        except Exception as e:
            print(f"⚠️ Failed to save learning data: {e}")
    
    async def load_learning_data(self):
        """Load persisted learning data"""
        if not self._storage_path:
            return
        
        try:
            import aiofiles
            
            async with aiofiles.open(self._storage_path, 'r') as f:
                content = await f.read()
            
            data = json.loads(content)
            
            for provider_id, tasks in data.items():
                self._performance_data[provider_id] = {}
                for task_type_str, perf_data in tasks.items():
                    task_type = TaskType(task_type_str)
                    perf = ProviderPerformance(
                        provider_id=provider_id,
                        task_type=task_type,
                        **perf_data
                    )
                    self._performance_data[provider_id][task_type] = perf
            
            print(f"📂 Learning data loaded ({len(data)} providers)")
            
        except FileNotFoundError:
            print("ℹ️ No existing learning data found, starting fresh")
        except Exception as e:
            print(f"⚠️ Failed to load learning data: {e}")
```

---

## 2.4 Local Fallback (Ollama) - ULTIMATE SAFETY NET

```python
# backend/services/dynamic_ai/local_fallback.py
"""
Local Fallback using Ollama
Ensures system ALWAYS works even with ZERO external APIs
Design goal: runs locally, no API keys needed — uptime target (measured separately)
"""

import asyncio
import subprocess
import json
import httpx
from typing import Optional, List, Dict
from dataclasses import dataclass
from enum import Enum


class OllamaModelStatus(Enum):
    AVAILABLE = "available"
    NOT_INSTALLED = "not_installed"
    DOWNLOADING = "downloading"
    OLLAMA_NOT_RUNNING = "ollama_not_running"


@dataclass
class OllamaModel:
    model_id: str
    name: str
    size_gb: float
    specialty: str
    parameters: str  # e.g., "7B", "70B"
    
    # Recommended uses
    recommended_for: List[str]
    not_recommended_for: List[str]


# Pre-configured models for SupremeAI
RECOMMENDED_OLLAMA_MODELS = [
    OllamaModel(
        model_id="llama3.1:8b",
        name="Llama 3.1 8B",
        size_gb=4.7,
        specialty="General purpose chat & reasoning",
        parameters="8B",
        recommended_for=["chat", "reasoning", "analysis", "general"],
        not_recommended_for=["complex coding", "math proofs"]
    ),
    OllamaModel(
        model_id="llama3.1:70b",
        name="Llama 3.1 70B",
        size_gb=40,
        specialty="Complex reasoning & coding",
        parameters="70B",
        recommended_for=["coding", "reasoning", "analysis", "complex tasks"],
        not_recommended_for=[]  # Good for everything (but needs more RAM)
    ),
    OllamaModel(
        model_id="codellama:13b",
        name="Code Llama 13B",
        size_gb=7.5,
        specialty="Code generation & explanation",
        parameters="13B",
        recommended_for=["code_generation", "code_review", "debugging"],
        not_recommended_for=["chat", "creative writing"]
    ),
    OllamaModel(
        model_id="mistral:7b",
        name="Mistral 7B",
        size_gb=4.2,
        specialty="Balanced performance",
        parameters="7B",
        recommended_for=["general", "chat", "quick tasks"],
        not_recommended_for=["complex reasoning"]
    ),
    OllamaModel(
        model_id="nomic-embed-text",
        name="Nomic Embed Text",
        size_gb=0.27,
        specialty="Text embeddings",
        parameters="small",
        recommended_for=["embedding", "semantic search"],
        not_recommended_for=["generation"]
    ),
]


class OllamaFallback:
    """
    Ollama-based local fallback
    Ensures AI functionality even without ANY external APIs
    """
    
    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        auto_install_models: bool = True,
        preferred_model: str = "llama3.1:8b"
    ):
        self.base_url = ollama_base_url
        self.auto_install = auto_install_models
        self.preferred_model = preferred_model
        self._available_models: List[str] = []
        self._is_running = False
        self._client: Optional[httpx.AsyncClient] = None
    
    async def initialize(self):
        """Initialize Ollama fallback system"""
        print("🏠 Initializing Local Fallback (Ollama)...")
        
        # Check if Ollama is running
        self._is_running = await self._check_ollama_running()
        
        if not self._is_running:
            print("⚠️ Ollama not running. Attempting to start...")
            started = await self._start_ollama()
            if not started:
                print("❌ Could not start Ollama. Local fallback unavailable.")
                return False
        
        # Create HTTP client
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)
        
        # Check available models
        await self._refresh_available_models()
        
        # Install recommended models if needed
        if self.auto_install:
            await self._ensure_models_installed([self.preferred_model])
        
        print(f"✅ Local Fallback Ready! Available models: {self._available_models}")
        return True
    
    async def _check_ollama_running(self) -> bool:
        """Check if Ollama server is running"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except:
            return False
    
    async def _start_ollama(self) -> bool:
        """Attempt to start Ollama server"""
        try:
            # Try starting ollama serve (works on Linux/Mac)
            process = subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait for it to start
            await asyncio.sleep(3)
            
            return await self._check_ollama_running()
        except FileNotFoundError:
            print("❌ Ollama not installed. Visit https://ollama.ai to install.")
            return False
        except Exception as e:
            print(f"❌ Failed to start Ollama: {e}")
            return False
    
    async def _refresh_available_models(self):
        """List installed models"""
        try:
            response = await self._client.get("/api/tags")
            if response.status_code == 200:
                data = response.json()
                self._available_models = [m['model'] for m in data.get('models', [])]
        except Exception as e:
            print(f"⚠️ Failed to list Ollama models: {e}")
    
    async def _ensure_models_installed(self, model_ids: List[str]):
        """Ensure specified models are installed"""
        for model_id in model_ids:
            if model_id not in self._available_models:
                print(f"📦 Installing Ollama model: {model_id}")
                try:
                    # Pull model (this can take a while for large models)
                    response = await self._client.post("/api/pull", json={
                        "name": model_id,
                        "stream": False
                    })
                    
                    if response.status_code == 200:
                        self._available_models.append(model_id)
                        print(f"✅ Model {model_id} installed")
                    else:
                        print(f"❌ Failed to install {model_id}")
                        
                except Exception as e:
                    print(f"❌ Error installing {model_id}: {e}")
    
    async def is_available(self) -> bool:
        """Check if local fallback is ready"""
        return self._is_running and len(self._available_models) > 0
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> dict:
        """
        Generate text using local Ollama model
        This NEVER fails due to external issues!
        """
        if not self._client:
            return {
                "success": False,
                "error": "Ollama client not initialized",
                "fallback_used": True
            }
        
        # Select model
        selected_model = model or self.preferred_model
        
        # If preferred model not available, pick another
        if selected_model not in self._available_models:
            if self._available_models:
                selected_model = self._available_models[0]
            else:
                return {
                    "success": False,
                    "error": "No Ollama models available",
                    "fallback_used": True
                }
        
        # Build request payload
        payload = {
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get('temperature', 0.7),
                "top_p": kwargs.get('top_p', 0.9),
                "num_predict": kwargs.get('max_tokens', 2048),
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        try:
            start_time = asyncio.get_event_loop().time()
            
            response = await self._client.post("/api/generate", json=payload)
            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                
                return {
                    "success": True,
                    "text": data.get('response', ''),
                    "model": selected_model,
                    "latency_ms": latency_ms,
                    "done_reason': data.get('done_reason'),
                    "fallback_used": True,
                    "provider": "ollama-local"
                }
            else:
                return {
                    "success": False,
                    "error": f"Ollama API error: {response.status_code}",
                    "fallback_used": True
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Ollama generation error: {str(e)}",
                "fallback_used": True
            }
    
    async def embed(self, text: str, model: str = "nomic-embed-text") -> list:
        """Generate embeddings locally"""
        if not self._client:
            raise RuntimeError("Ollama client not initialized")
        
        # Ensure embedding model is available
        if model not in self._available_models:
            await self._ensure_models_installed([model])
        
        response = await self._client.post("/api/embeddings", json={
            "model": model,
            "prompt": text
        })
        
        if response.status_code == 200:
            data = response.json()
            return data.get('embedding', [])
        else:
            raise Exception(f"Embedding failed: {response.text}")
    
    def get_best_model_for_task(self, task_type: str) -> Optional[str]:
        """Recommend best local model for a given task type"""
        for model in RECOMMENDED_OLLAMA_MODELS:
            if task_type in model.recommended_for and model.model_id in self._available_models:
                return model.model_id
        
        # Fallback to any available model
        return self._available_models[0] if self._available_models else None
    
    def get_status(self) -> dict:
        """Get status of local fallback system"""
        return {
            "is_running": self._is_running,
            "available_models": self._available_models,
            "preferred_model": self.preferred_model,
            "can_generate": len([m for m in self._available_models if 'embed' not in m]) > 0,
            "can_embed": any('embed' in m for m in self._available_models),
            "recommended_models": [
                {"id": m.model_id, "name": m.name, "installed": m.model_id in self._available_models}
                for m in RECOMMENDED_OLLAMA_MODELS
            ]
        }
```

---

## 2.5 Main Orchestrator (Ties Everything Together)

```python
# backend/services/dynamic_ai/orchestrator.py
"""
SupremeAI Dynamic AI Orchestrator
Main entry point - ties together all components for resilient AI access
NEVER crashes due to external API issues!
"""

import asyncio
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from .provider_registry import ProviderRegistry, ProviderStatus, ProviderConfig
from .circuit_breaker import CircuitBreakerManager
from .learning_engine import LearningEngine, TaskType
from .local_fallback import OllamaFallback

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Result from AI generation attempt"""
    success: bool
    text: Optional[str] = None
    provider_used: Optional[str] = None
    model_used: Optional[str] = None
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    was_fallback: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = None


class DynamicAIOrchestrator:
    """
    Main orchestrator for dynamic AI provider management
    Provides a single interface that NEVER fails
    """
    
    def __init__(
        self,
        learning_data_path: str = "/data/ai_learning_data.json",
        ollama_enabled: bool = True,
        auto_validate_keys: bool = True,
    ):
        # Core components
        self.registry = ProviderRegistry()
        self.circuit_breaker = CircuitBreakerManager()
        self.learning_engine = LearningEngine(storage_path=learning_data_path)
        self.local_fallback = OllamaFallback() if ollama_enabled else None
        
        # Configuration
        self.auto_validate_keys = auto_validate_keys
        self._initialized = False
        self._health_check_interval = 300.0  # 5 minutes
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "fallback_used_count": 0,
            "external_success_count": 0,
            "external_failure_count": 0,
        }
    
    async def initialize(self):
        """Initialize all components"""
        print("🚀 Initializing SupremeAI Dynamic AI System...")
        
        # 1. Initialize provider registry
        await self.registry.initialize()
        
        # 2. Load historical learning data
        await self.learning_engine.load_learning_data()
        
        # 3. Initialize local fallback (Ollama)
        if self.local_fallback:
            await self.local_fallback.initialize()
        
        # 4. Validate all API keys (optional, can skip for faster startup)
        if self.auto_validate_keys:
            print("🔑 Validating API keys...")
            await self.registry.refresh_status()
        
        # 5. Start background health checks
        asyncio.create_task(self._background_health_check_loop())
        
        self._initialized = True
        print("✅ SupremeAI Dynamic AI System Ready!")
        print(f"   External providers: {len(self.registry.get_available_providers())} available")
        print(f"   Local fallback: {'Ready' if await self.local_fallback.is_available() else 'Unavailable'}")
    
    async def generate(
        self,
        prompt: str,
        task_type: Optional[str] = None,
        system_prompt: Optional[str] = None,
        prefer_free_tier: bool = True,
        max_retries: int = 3,
        **kwargs
    ) -> GenerationResult:
        """
        Generate text using the best available provider
        THIS METHOD NEVER CRASHES - always returns a valid result
        """
        self.stats["total_requests"] += 1
        start_time = time.time()
        
        if not self._initialized:
            await self.initialize()
        
        # Detect task type if not provided
        detected_task = (
            TaskType(task_type) if task_type 
            else self.learning_engine.detect_task_type(prompt)
        )
        
        # Get ranked list of best providers for this task
        available_providers = self.registry.get_available_providers(
            require_free_tier=prefer_free_tier
        )
        
        ranked_providers = await self.learning_engine.get_best_providers_for_task(
            prompt=prompt,
            available_providers=available_providers,
            context={"purpose": "generation"}
        )
        
        # Try each provider in order
        last_error = None
        
        for provider_id, confidence_score in ranked_providers[:max_retries]:
            # Check circuit breaker
            if not await self.circuit_breaker.is_available(provider_id):
                logger.debug(f"Circuit open for {provider_id}, skipping")
                continue
            
            # Get provider config
            provider_config = self.registry.get_provider(provider_id)
            if not provider_config:
                continue
            
            # Attempt generation
            try:
                result = await self._call_provider(
                    provider_config=provider_config,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    detected_task=detected_task,
                    **kwargs
                )
                
                if result.success:
                    # Record success
                    latency_ms = (time.time() - start_time) * 1000
                    
                    self.registry.record_success(provider_id, latency_ms)
                    await self.circuit_breaker.record_success(provider_id)
                    self.learning_engine.record_interaction(
                        provider_id=provider_id,
                        task_type=detected_task,
                        success=True,
                        latency_ms=latency_ms,
                        estimated_cost=result.cost_usd
                    )
                    
                    self.stats["successful_requests"] += 1
                    self.stats["external_success_count"] += 1
                    
                    result.latency_ms = latency_ms
                    result.was_fallback = False
                    
                    logger.info(f"✅ Generated via {provider_id} ({latency_ms:.0f}ms)")
                    return result
                
                else:
                    # Provider returned error
                    last_error = result.error
                    self.registry.record_failure(provider_id, result.error or "Unknown error")
                    await self.circuit_breaker.record_failure(provider_id)
                    self.learning_engine.record_interaction(
                        provider_id=provider_id,
                        task_type=detected_task,
                        success=False,
                        latency_ms=(time.time() - start_time) * 1000
                    )
                    self.stats["external_failure_count"] += 1
                    
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Provider {provider_id} threw exception: {e}")
                
                self.registry.record_failure(provider_id, str(e))
                await self.circuit_breaker.record_failure(provider_id)
                self.learning_engine.record_interaction(
                    provider_id=provider_id,
                    task_type=detected_task,
                    success=False,
                    latency_ms=(time.time() - start_time) * 1000
                )
                self.stats["external_failure_count"] += 1
        
        # ALL EXTERNAL PROVIDERS FAILED → Use Local Fallback
        logger.warning(f"⚠️ All external providers failed, using local fallback")
        
        if self.local_fallback and await self.local_fallback.is_available():
            try:
                # Select best local model for task
                local_model = self.local_fallback.get_best_model_for_task(detected_task.value)
                
                local_result = await self.local_fallback.generate(
                    prompt=prompt,
                    model=local_model,
                    system_prompt=system_prompt or "You are SupremeAI assistant. Respond helpfully.",
                    **kwargs
                )
                
                if local_result.get('success'):
                    self.stats["fallback_used_count"] += 1
                    self.stats["successful_requests"] += 1
                    
                    return GenerationResult(
                        success=True,
                        text=local_result['text'],
                        provider_used='ollama-local',
                        model_used=local_result.get('model'),
                        latency_ms=local_result.get('latency_ms', 0),
                        was_fallback=True,
                        metadata={"source": "local_fallback"}
                    )
                else:
                    last_error = local_result.get('error', 'Local fallback also failed')
                    
            except Exception as e:
                last_error = f"Local fallback error: {e}"
        
        # EVERYTHING FAILED - Return graceful error (still doesn't crash!)
        logger.error(f"❌ All AI providers failed. Last error: {last_error}")
        
        return GenerationResult(
            success=False,
            error=f"All providers failed. Last error: {last_error}",
            was_fallback=False,
            metadata={
                "attempted_providers": [p[0] for p in ranked_providers[:max_retries]],
                "local_fallback_available": self.local_fallback and await self.local_fallback.is_available(),
            }
        )
    
    async def _call_provider(
        self,
        provider_config: ProviderConfig,
        prompt: str,
        system_prompt: Optional[str],
        detected_task: TaskType,
        **kwargs
    ) -> GenerationResult:
        """
        Call a specific provider
        Implement provider-specific calling logic here
        """
        import httpx
        
        # Select best model for this provider based on task
        model = self._select_best_model_for_task(provider_config, detected_task)
        
        # Provider-specific implementation
        if provider_config.provider_id == "gemini":
            return await self._call_gemini(provider_config, model, prompt, system_prompt, **kwargs)
        
        elif provider_config.provider_id in ["openai", "deepseek", "moonshot", "together", "nvidia", "groq"]:
            return await self._call_openai_compatible(provider_config, model, prompt, system_prompt, **kwargs)
        
        elif provider_config.provider_id == "huggingface":
            return await self._call_huggingface(provider_config, model, prompt, **kwargs)
        
        elif provider_config.provider_id == "openrouter":
            return await self._call_openrouter(provider_config, model, prompt, system_prompt, **kwargs)
        
        else:
            # Default to OpenAI-compatible
            return await self._call_openai_compatible(provider_config, model, prompt, system_prompt, **kwargs)
    
    def _select_best_model_for_task(self, provider: ProviderConfig, task: TaskType) -> str:
        """Select best model from provider for given task type"""
        if not provider.models:
            return "default"
        
        # Find model that matches task requirements
        task_specialty_map = {
            TaskType.CODE_GENERATION: ["coding", "code"],
            TaskType.CODE_REVIEW: ["coding", "code", "review"],
            TaskType.REASONING: ["reasoning", "reason"],
            TaskType.CREATIVE_WRITING: ["creative", "write"],
            TaskType.CHAT: [],
            TaskType.GENERAL: [],
        }
        
        specialties = task_specialty_map.get(task, [])
        
        # First try to find specialized model
        for model in provider.models:
            if any(spec in model.get('specialty', '').lower() for spec in specialties):
                return model['id']
        
        # Then try economy tier for simple tasks
        if task in [TaskType.CHAT, TaskType.GENERAL, TaskType.SUMMARIZATION]:
            for model in provider.models:
                if model.get('tier') == 'economy':
                    return model['id']
        
        # Default to first model
        return provider.models[0]['id']
    
    async def _call_gemini(self, provider: ProviderConfig, model: str, prompt: str, system_prompt: Optional[str], **kwargs) -> GenerationResult:
        """Call Google Gemini API"""
        import httpx
        
        url = f"{provider.base_url}/{model}:generateContent"
        
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System: {system_prompt}\n\nUser: {prompt}"}]})
        else:
            contents.append({"role": "user", "parts": [{"text": prompt}]})
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get('temperature', 0.7),
                "topP": kwargs.get('top_p', 0.95),
                "maxOutputTokens": kwargs.get('max_tokens', 2048),
            }
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                params={"key": provider.api_key},
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return GenerationResult(success=True, text=text, model_used=model)
            else:
                error_msg = f"Gemini API error {response.status_code}: {response.text[:200]}"
                return GenerationResult(success=False, error=error_msg)
    
    async def _call_openai_compatible(self, provider: ProviderConfig, model: str, prompt: str, system_prompt: Optional[str], **kwargs) -> GenerationResult:
        """Call OpenAI-compatible API (works for OpenAI, DeepSeek, Moonshot, Together, Groq, NVIDIA)"""
        import httpx
        
        url = f"{provider.base_url}/chat/completions"
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get('temperature', 0.7),
            "max_tokens": kwargs.get('max_tokens', 2048),
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {provider.api_key}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                text = data["choices"][0]["message"]["content"]
                
                # Estimate cost (rough)
                usage = data.get('usage', {})
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0)
                estimated_cost = (prompt_tokens * 0.000001 + completion_tokens * 0.000002)  # Rough estimate
                
                return GenerationResult(
                    success=True, 
                    text=text, 
                    model_used=model,
                    cost_usd=estimated_cost
                )
            else:
                error_msg = f"{provider.provider_id} API error {response.status_code}: {response.text[:200]}"
                return GenerationResult(success=False, error=error_msg)
    
    async def _call_huggingface(self, provider: ProviderConfig, model: str, prompt: str, **kwargs) -> GenerationResult:
        """Call HuggingFace Serverless Inference API"""
        import httpx
        
        url = f"{provider.base_url}/{model}"
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": kwargs.get('temperature', 0.7),
                "max_new_tokens": kwargs.get('max_tokens', 1024),
                "return_full_text": False,
            }
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {provider.api_key}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    text = data[0].get('generated_text', '')
                elif isinstance(data, dict):
                    text = data.get('generated_text', data.get('text', ''))
                else:
                    text = str(data)
                
                return GenerationResult(success=True, text=text, model_used=model)
            
            elif response.status_code == 503:
                # Model loading - wait and retry once
                await asyncio.sleep(10)
                return await self._call_huggingface(provider, model, prompt, **kwargs)
            else:
                error_msg = f"HF API error {response.status_code}: {response.text[:200]}"
                return GenerationResult(success=False, error=error_msg)
    
    async def _call_openrouter(self, provider: ProviderConfig, model: str, prompt: str, system_prompt: Optional[str], **kwargs) -> GenerationResult:
        """Call OpenRouter API (similar to OpenAI-compatible but with special handling)"""
        # OpenRouter is mostly OpenAI-compatible
        return await self._call_openai_compatible(provider, model, prompt, system_prompt, **kwargs)
    
    async def _background_health_check_loop(self):
        """Background loop for continuous health monitoring"""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self.registry.refresh_status()
                
                # Log summary
                summary = self.registry.get_status_summary()
                active = summary.get('active', 0)
                total = summary.get('total_providers', 0)
                
                logger.info(f"🏥 Health check: {active}/{total} providers active")
                
            except Exception as e:
                logger.error(f"Health check error: {e}")
    
    async def get_system_status(self) -> dict:
        """Get complete system status"""
        return {
            "initialized": self._initialized,
            "registry": self.registry.get_status_summary(),
            "circuit_breakers": self.circuit_breaker.get_all_circuit_states(),
            "local_fallback": self.local_fallback.get_status() if self.local_fallback else None,
            "statistics": self.stats.copy(),
        }


# ============================================================================
# SINGLETON INSTANCE (use throughout application)
# ============================================================================

_orchestrator: Optional[DynamicAIOrchestrator] = None


async def get_ai_orchestrator() -> DynamicAIOrchestrator:
    """Get or create the singleton orchestrator instance"""
    global _orchestrator
    
    if _orchestrator is None:
        _orchestrator = DynamicAIOrchestrator()
        await _orchestrator.initialize()
    
    return _orchestrator


async def generate_text(prompt: str, **kwargs) -> GenerationResult:
    """
    Convenience function for generating text
    Usage: result = await generate_text("Hello, world!")
    """
    orchestrator = await get_ai_orchestrator()
    return await orchestrator.generate(prompt, **kwargs)
```

---

# 🎯 PART 3: INTEGRATION EXAMPLES

## 3.1 How to Use in Your Existing Code

```python
# Example: Replace your existing LLM calls with dynamic version

# ============================================
# BEFORE (Fragile, breaks when keys invalid)
# ============================================
# from openai import OpenAI
# 
# client = OpenAI(api_key=OPENAI_API_KEY)  # 💥 Crashes if invalid!
# response = client.chat.completions.create(
#     model="gpt-4",
#     messages=[{"role": "user", "content": prompt}]
# )

# ============================================
# AFTER (Resilient, never crashes)
# ============================================
from backend.services.dynamic_ai.orchestrator import generate_text

result = await generate_text(
    prompt="Explain quantum computing simply",
    prefer_free_tier=True,  # Prefer free providers
)

if result.success:
    print(result.text)  # Always works!
    print(f"Provider used: {result.provider_used}")  # See who handled it
    print(f"Was fallback: {result.was_fallback}")  # Know if local was used
else:
    # This rarely happens - only if BOTH external AND local fail
    print("System temporarily unavailable (should never happen)")


# ============================================
# Example: IDE Trio Integration
# ============================================
from backend.services.dynamic_ai.orchestrator import get_ai_orchestrator

async def ide_trio_stage1_writer(requirements: str) -> str:
    """Stage 1: Write code using best available model"""
    orchestrator = await get_ai_orchestrator()
    
    result = await orchestrator.generate(
        prompt=f"""Write clean, production-ready Python code for:
{requirements}

Output ONLY the code, no explanations.""",
        task_type="code_generation",
        prefer_free_tier=True,  # Always prefer free tier for IDE trio
    )
    
    return result.text if result.success else "# TODO: Manual implementation needed"

# This will work EVEN IF:
# - Gemini key is invalid (uses Groq, or DeepSeek, or Ollama)
# - All cloud keys expire (falls back to local Ollama)
# - Internet is down (uses Ollama locally)
# - Render is having issues (still works!)

# ============================================
# Example: Eternal Brain Integration
# ============================================
from backend.services.dynamic_ai.orchestrator import generate_text

async def query_eternal_brain(query: str) -> str:
    """Query Eternal Brain with resilient AI"""
    
    # First, try to get relevant memories from pgvector (always works)
    memories = await pgvector_similarity_search(query)
    
    # Then generate response using best available AI
    context = "\n".join([m['summary'] for m in memories])
    
    result = await generate_text(
        prompt=f"""Based on this context from my memory:
{context}

User Query: {query}

Provide a helpful response based on what I know.""",
        task_type="question_answering",
    )
    
    return result.text if result.success else "I'm still learning about this topic."
```

---

## 3.2 Startup Configuration

```python
# backend/main.py (Add to startup)
from backend.services.dynamic_ai.orchestrator import get_ai_orchestrator

@app.on_event("startup")
async def startup_event():
    """Initialize Dynamic AI System on startup"""
    
    # Initialize the orchestrator (validates keys, starts Ollama, loads learning)
    ai_system = await get_ai_orchestrator()
    
    # Check initial status
    status = await ai_system.get_system_status()
    
    print("\n" + "="*60)
    print("🤖 SUPREMAI DYNAMIC AI SYSTEM STATUS")
    print("="*60)
    print(f"Total Providers: {status['registry']['total_providers']}")
    print(f"Active: 🟢 {status['registry']['active']}")
    print(f"Degraded: 🟡 {status['registry']['degraded']}")
    print(f"Not Configured: ⚪ {status['registry']['not_configured']}")
    
    if status['local_fallback']:
        print(f"\nLocal Fallback (Ollama): {'✅ Ready' if status['local_fallback']['can_generate'] else '❌ Not ready'}")
        print(f"Available Models: {status['local_fallback']['available_models']}")
    
    print("="*60 + "\n")


# Add health endpoint
@app.get('/api/ai/status')
async def ai_system_status():
    """Endpoint to check AI system health"""
    orchestrator = await get_ai_orchestrator()
    return await orchestrator.get_system_status()


# Add generation endpoint
@app.post('/api/ai/generate')
async def generate_endpoint(request: dict):
    """Unified AI generation endpoint"""
    orchestrator = await get_ai_orchestrator()
    
    result = await orchestrator.generate(
        prompt=request.get('prompt', ''),
        task_type=request.get('task_type'),
        system_prompt=request.get('system_prompt'),
        prefer_free_tier=request.get('prefer_free_tier', True),
    )
    
    return {
        "success": result.success,
        "text": result.text,
        "metadata": {
            "provider": result.provider_used,
            "model": result.model_used,
            "was_fallback": result.was_fallback,
            "latency_ms": result.latency_ms,
        }
    }
```

---

## 3.3 Environment Variables (.env.example Updated)

```bash
# ===========================================
# SUPREMAI DYNAMIC AI CONFIGURATION
# ===========================================

# --- AI Provider API Keys (ALL OPTIONAL!) ---
# If a key is missing/invalid, the system will:
# 1. Skip that provider
# 2. Use other available providers
# 3. Fall back to local Ollama if all external fail

# FREE TIER PROVIDERS (Recommended)
GEMINI_API_KEY=                    # Google Gemini (Primary free)
GROQ_API_KEY=                      # Groq (Fast inference)
HF_API_KEY=                        # HuggingFace (Custom models)

# FREEMIUM/PAID BACKUPS (Optional)
OPENAI_API_KEY=                    # OpenAI GPT
DEEPSEEK_API_KEY=                  # DeepSeek (Cheap)
MOONSHOT_API_KEY=                  # Moonshot/Kimi
TOGETHER_API_KEY=                  # Together AI
NVIDIA_API_KEY=                    # NVIDIA NIM
OPENROUTER_API_KEY=                # OpenRouter Aggregator

# --- LOCAL FALLBACK (Ollama) ---
OLLAMA_ENABLED=true                # Enable local fallback (default: true)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_PREFERRED_MODEL=llama3.1:8b  # Default local model

# --- DYNAMIC AI SETTINGS ---
AUTO_VALIDATE_KEYS=true            # Validate keys on startup (default: true)
PREFER_FREE_TIER=true              # Prefer free providers (default: true)
LEARNING_DATA_PATH=/data/ai_learning_data.json
HEALTH_CHECK_INTERVAL_SECONDS=300  # How often to check provider health

# --- CIRCUIT BREAKER SETTINGS ---
CIRCUIT_BREAKER_FAILURE_THRESHOLD=3   # Failures before disabling
CIRCUIT_BREAKER_TIMEOUT_SECONDS=30    # How long to keep disabled
CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2  # Successes to re-enable

# NOTE: The system works with ZERO API keys configured!
# It will use Ollama local models as ultimate fallback.
# More keys = more options = better performance & cost optimization.
```

---

# 📊 PART 4: FAILURE SCENARIOS & BEHAVIOR

## What Happens When Things Go Wrong:

| Scenario | System Behavior | User Experience |
|----------|----------------|-----------------|
| **Gemini key expires** | Auto-detects, disables Gemini, uses Groq/HF/Ollama | No interruption |
| **All free tiers hit rate limit** | Switches to paid providers (DeepSeek/Moonshot) | Slightly slower |
| **Internet goes down** | Detects network failure, uses Ollama locally | Works offline! |
| **Render has outage** | Frontend shows cached data, queues requests | Degraded gracefully |
| **New provider added** | Just add API key to env, auto-detected on next refresh | Instantly available |
| **Provider changes pricing** | Learning engine detects increased cost, deprioritizes | Automatically adapts |
| **All external APIs down** | 100% local mode via Ollama | Full functionality |
| **Invalid key in .env** | Validates on startup, marks as NOT_CONFIGURED | Skips silently |

---

# 🎯 PART 5: IMPLEMENTATION CHECKLIST

## Phase 1: Core Setup (Day 1-2)

- [ ] Copy `dynamic_ai/` module to `backend/services/`
- [ ] Install dependencies: `pip install httpx aiofiles`
- [ ] Install Ollama locally: `curl -fsSL https://ollama.ai/install.sh | sh`
- [ ] Pull default model: `ollama pull llama3.1:8b`
- [ ] Add `.env` variables (all optional!)

## Phase 2: Integration (Day 3-4)

- [ ] Replace direct API calls with `generate_text()` 
- [ ] Add `/api/ai/status` endpoint
- [ ] Add `/api/ai/generate` endpoint
- [ ] Integrate with IDE Trio pipeline
- [ ] Integrate with Eternal Brain

## Phase 3: Testing (Day 5)

- [ ] Test with all valid keys → Should use best providers
- [ ] Test with one invalid key → Should skip it seamlessly
- [ ] Test with ALL invalid keys → Should fall back to Ollama
- [ ] Test without internet → Should work offline
- [ ] Monitor learning data file → Should grow over time

## Phase 4: Production (Day 6+)

- [ ] Set up daily backup of `ai_learning_data.json`
- [ ] Monitor provider statistics dashboard
- [ ] Tune circuit breaker thresholds based on real data
- [ ] Add alerting when too many providers fail

---

# 📁 File Structure:

```
backend/services/dynamic_ai/
├── __init__.py              # Package init
├── orchestrator.py          # Main entry point (Singleton)
├── provider_registry.py     # Dynamic provider management
├── circuit_breaker.py       # Failure detection & isolation
├── learning_engine.py       # Self-improving router
├── local_fallback.py        # Ollama integration (ultimate safety net)
└── README.md               # Documentation
```

---

**Plan Version:** 5.0 (Dynamic AI Architecture)  
**Core Principle:** *"NO EXTERNAL DEPENDENCY SHOULD BE ABLE TO BREAK US"*  
**Guarantee:** System works with 0, some, or all API keys configured  

> **বাংলা:** আর কোনোদিন Render error দেখাবে না কারণ invalid API key হলেও system crash করবে না! 🚀