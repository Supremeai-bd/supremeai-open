#!/usr/bin/env python3
"""
gateway/dynamic_llm_router.py — Dynamic Master LLM Router & Infinite Fallback Engine.

Architecture & Contract:
  - Dynamically discovers available LLM API keys and accounts in the runtime environment
    (e.g., GROQ_API_KEY*, GEMINI_API_KEY*, OPENROUTER_API_KEY*, MISTRAL_API_KEY*, OPENAI_API_KEY*, HUGGINGFACE_API_KEY*).
  - Multi-tier cascading fallback:
      Tier 1 (Fast & Free/Low Latency): Groq, Gemini
      Tier 2 (High-Reliability & Breadth): OpenRouter, Mistral
      Tier 3 (Universal Catch-All): OpenAI, HuggingFace
  - Circuit Breaker & Cooldown: Tracks 429, 5xx, and latency per account. Automatic failover
    without dropping the user stream or request.
  - Zero-maintenance: Adding a new key to the environment automatically includes the provider;
    removing a key automatically de-registers it.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class LLMAccount:
    alias: str
    provider: str
    env_key: str
    model: str
    tier: int = 1  # 1: Fast/Preferred, 2: Secondary/High-Reliability, 3: Fallback
    healthy: bool = True
    cooldown_until: float = 0.0
    consecutive_failures: int = 0
    latency_ms: float = 0.0
    total_requests: int = 0
    total_failures: int = 0


# Canonical default models and observed baseline latencies per provider family
PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "cerebras": {
        "tier": 1,
        "default_model": "llama-3.3-70b",
        "baseline_latency_ms": 350.0,
        "env_pattern": re.compile(r"^CEREBRAS_API_KEY(?:_.*)?$"),
    },
    "groq": {
        "tier": 1,
        "default_model": "qwen/qwen3.8-27b",
        "baseline_latency_ms": 450.0,
        "env_pattern": re.compile(r"^GROQ_API_KEY(?:_.*)?$"),
    },
    "openrouter": {
        "tier": 1,
        "default_model": "nvidia/nemotron-3.5-lightning:free",
        "baseline_latency_ms": 650.0,
        "env_pattern": re.compile(r"^OPENROUTER_API_KEY(?:_.*)?$"),
    },
    "sambanova": {
        "tier": 1,
        "default_model": "Meta-Llama-3.3-70B-Instruct",
        "baseline_latency_ms": 900.0,
        "env_pattern": re.compile(r"^SAMBANOVA_API_KEY(?:_.*)?$"),
    },
    "gemini": {
        "tier": 1,
        "default_model": "gemini-2.5-flash",
        "baseline_latency_ms": 1300.0,
        "env_pattern": re.compile(r"^(?:GEMINI_API_KEY|GOOGLE_API_KEY)(?:_.*)?$"),
    },
    "github_models": {
        "tier": 1,
        "default_model": "gpt-4o-mini",
        "baseline_latency_ms": 1350.0,
        "env_pattern": re.compile(r"^(?:GITHUB_MODELS_API_KEY|GITHUB_TOKEN)(?:_.*)?$"),
    },
    "mistral": {
        "tier": 2,
        "default_model": "mistral-small-latest",
        "baseline_latency_ms": 1400.0,
        "env_pattern": re.compile(r"^MISTRAL_API_KEY(?:_.*)?$"),
    },
    "deepinfra": {
        "tier": 2,
        "default_model": "meta-llama/Meta-Llama-3.1-70B-Instruct",
        "baseline_latency_ms": 1100.0,
        "env_pattern": re.compile(r"^DEEPINFRA_API_KEY(?:_.*)?$"),
    },
    "together": {
        "tier": 2,
        "default_model": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        "baseline_latency_ms": 1200.0,
        "env_pattern": re.compile(r"^TOGETHER_API_KEY(?:_.*)?$"),
    },
    "xai": {
        "tier": 2,
        "default_model": "grok-beta",
        "baseline_latency_ms": 1450.0,
        "env_pattern": re.compile(r"^XAI_API_KEY(?:_.*)?$"),
    },
    "openai": {
        "tier": 3,
        "default_model": "gpt-4o-mini",
        "baseline_latency_ms": 1500.0,
        "env_pattern": re.compile(r"^OPENAI_API_KEY(?:_.*)?$"),
    },
    "huggingface": {
        "tier": 3,
        "default_model": "meta-llama/Llama-3.3-70B-Instruct",
        "baseline_latency_ms": 2000.0,
        "env_pattern": re.compile(r"^(?:HUGGINGFACE_API_KEY|HF_TOKEN)(?:_.*)?$"),
    },
}


class DynamicLLMRouter:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._accounts: list[LLMAccount] = []
        self._last_scan: float = 0.0
        self.refresh_accounts()

    def refresh_accounts(self, env_dict: dict[str, str] | None = None) -> list[LLMAccount]:
        """Dynamically scans environment variables to register or prune provider accounts."""
        now = self._clock()
        src = dict(os.environ) if env_dict is None else dict(env_dict)
        # Attempt to load local .env if env_dict not explicitly passed
        if env_dict is None and os.path.exists(".env"):
            with contextlib.suppress(Exception):
                with open(".env", "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            src.setdefault(k.strip(), v.strip().strip("'\""))

        discovered: list[LLMAccount] = []

        # Retain stats from existing accounts if they match alias
        existing_stats: dict[str, LLMAccount] = {a.alias: a for a in self._accounts}

        for env_name, val in src.items():
            if not val or len(val.strip()) < 8:
                continue

            for provider, cfg in PROVIDER_DEFAULTS.items():
                if cfg["env_pattern"].match(env_name):
                    alias = f"{provider}:{env_name.lower()}"
                    old = existing_stats.get(alias)
                    account = LLMAccount(
                        alias=alias,
                        provider=provider,
                        env_key=env_name,
                        model=cfg["default_model"],
                        tier=cfg["tier"],
                        healthy=old.healthy if old else True,
                        cooldown_until=old.cooldown_until if old else 0.0,
                        consecutive_failures=old.consecutive_failures if old else 0,
                        latency_ms=old.latency_ms if (old and old.latency_ms > 0) else cfg.get("baseline_latency_ms", 1000.0),
                        total_requests=old.total_requests if old else 0,
                        total_failures=old.total_failures if old else 0,
                    )
                    discovered.append(account)
                    break

        self._accounts = discovered
        self._last_scan = now
        return self._accounts

    @property
    def total_accounts(self) -> int:
        return len(self._accounts)

    @property
    def active_providers(self) -> list[str]:
        return sorted({a.provider for a in self._accounts})

    def get_execution_ladder(self) -> list[LLMAccount]:
        """Returns accounts dynamically sorted by: Health -> Tier -> Consecutive Failures -> Response Time (Latency)."""
        now = self._clock()
        # Separate eligible (healthy & not cooling down) accounts
        eligible = [
            a
            for a in self._accounts
            if a.healthy and a.cooldown_until <= now
        ]

        # Smart dynamic priority:
        # 1. Tier (Tier 1 fast-free before Tier 2 / 3)
        # 2. Consecutive failures ascending (0 failures first)
        # 3. Dynamic latency ms ascending (fastest response time first)
        eligible.sort(key=lambda a: (a.tier, a.consecutive_failures, a.latency_ms))
        return eligible

    def record_success(self, alias: str, latency_ms: float = 0.0) -> None:
        now = self._clock()
        for a in self._accounts:
            if a.alias == alias:
                a.healthy = True
                a.consecutive_failures = 0
                a.cooldown_until = 0.0
                a.total_requests += 1
                if latency_ms > 0:
                    a.latency_ms = (a.latency_ms * 0.7) + (latency_ms * 0.3) if a.latency_ms > 0 else latency_ms
                break

    def record_failure(self, alias: str, status_code: int = 500, cooldown_s: float = 30.0) -> None:
        now = self._clock()
        for a in self._accounts:
            if a.alias == alias:
                a.consecutive_failures += 1
                a.total_failures += 1
                a.total_requests += 1
                # If 429 (rate limit), apply progressive cooldown
                effective_cooldown = cooldown_s * (2 ** min(a.consecutive_failures - 1, 4))
                if status_code == 429:
                    effective_cooldown = max(effective_cooldown, 60.0)
                a.cooldown_until = now + effective_cooldown
                if a.consecutive_failures >= 3:
                    a.healthy = False
                break


def self_test() -> int:
    """Verifies dynamic auto-discovery, cascade ladder, and self-healing cooldown logic."""
    test_env = {
        "GROQ_API_KEY_PRIMARY": "gsk_live_mock_1234567890",
        "GEMINI_API_KEY_1": "AIzaSyLiveMock_1234567890",
        "OPENROUTER_API_KEY": "sk-or-live_mock_1234567890",
        "MISTRAL_API_KEY": "mistral_live_mock_1234567890",
    }

    router = DynamicLLMRouter()
    accounts = router.refresh_accounts(test_env)

    # Invariant 1: Discover all accounts matching pattern
    assert len(accounts) == 4, f"Expected 4 accounts, got {len(accounts)}"
    assert set(router.active_providers) == {"gemini", "groq", "mistral", "openrouter"}

    # Invariant 2: Execution ladder respects tiers & latency (Tier 1 Groq, OpenRouter, Gemini before Tier 2 Mistral)
    ladder = router.get_execution_ladder()
    assert len(ladder) == 4, f"Expected 4 eligible accounts, got {len(ladder)}"
    assert ladder[0].tier == 1
    assert ladder[1].tier == 1
    assert ladder[2].tier == 1
    assert ladder[3].tier == 2

    # Invariant 3: Circuit breaker & Cooldown on 429
    top_alias = ladder[0].alias
    router.record_failure(top_alias, status_code=429, cooldown_s=60.0)

    ladder_after = router.get_execution_ladder()
    assert len(ladder_after) == 3, "Failed account must be temporarily excluded from eligible ladder"
    assert top_alias not in [a.alias for a in ladder_after]

    # Invariant 4: Recovery on success
    router.record_success(top_alias, latency_ms=120.0)
    # Reset cooldown manually for test
    for a in router._accounts:
        if a.alias == top_alias:
            a.cooldown_until = 0.0

    ladder_recovered = router.get_execution_ladder()
    assert len(ladder_recovered) == 4, "Recovered account must re-enter eligible ladder"

    print("Dynamic LLM Router self-test: ALL PASS (4/4 assertions passed)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SupremeAI Dynamic LLM Router")
    parser.add_argument("--self-test", action="store_true", help="Run contract verification self-test")
    parser.add_argument("--list", action="store_true", help="List currently discovered providers and accounts")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    router = DynamicLLMRouter()
    ladder = router.get_execution_ladder()

    print("=" * 68)
    print("🤖 SUPREMEAI DYNAMIC MASTER LLM ROUTER")
    print("=" * 68)
    print(f"Total Discovered: {router.total_accounts}")
    print(f"Active Providers: {', '.join(router.active_providers) if router.active_providers else 'None'}")
    print(f"Eligible Ladder:  {len(ladder)} accounts ready")
    print("-" * 68)
    for idx, acc in enumerate(ladder, 1):
        print(f"[{idx}] Tier {acc.tier} | {acc.provider.upper():<12} | Model: {acc.model:<26} | Key: {acc.env_key}")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
