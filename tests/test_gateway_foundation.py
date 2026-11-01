"""tests/test_gateway_foundation.py — 3-tier verification (tier 3, unit).

Tests the SupremeAI Unified Gateway router foundation (issue #511):
- Config parsing, gateway-plane provider enum validation (schema 7 + gateway-only
  web & perplexity drivers) & drift rejection.
- Sliding window rate limiting: remaining tokens, reset epoch, retry-after.
- Provider failover chain: deterministic sequential attempt, fallback on 429/503,
  and failover exhaustion with honest transition ledger.
Fully offline, stdlib-only.
"""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gateway.config import (
    ALLOWED_PROVIDERS,
    CONFIG_SCHEMA_VERSION,
    ConfigError,
    Endpoint,
    GatewayConfig,
    parse_routing_policy,
)
from gateway.circuit_breaker import CircuitBreaker
from gateway.memory import QdrantMemoryStore
from gateway.provider_chain import (
    AttemptResult,
    ProviderChainExhausted,
    execute_chain,
)
from gateway.rate_limit import SlidingWindowLimiter


class TestGatewayConfig(unittest.TestCase):
    def test_allowed_providers_ssot(self):
        # Gateway-plane enum = task-router.schema.json's 7 schema providers
        # PLUS the gateway-only providers with live drivers + policy hops:
        # "web" (web_session.py) and "perplexity" (adapters.py, sonar cascade).
        # A copy that lags the runtime makes load_config() reject the shipped
        # routing_policy.json (drift class F-J, 2026-10-28) — extend, don't lag.
        expected = {
            "openai",
            "anthropic",
            "gemini",
            "groq",
            "openrouter",
            "mistral",
            "deepseek",
            "web",
            "perplexity",
            "manus",
        }
        self.assertEqual(ALLOWED_PROVIDERS, frozenset(expected))

    def test_routing_policy_load_valid(self):
        policy_path = REPO_ROOT / "gateway" / "routing_policy.json"
        raw = json.loads(policy_path.read_text(encoding="utf-8"))
        cfg = parse_routing_policy(
            raw,
            env={
                "SUPREMEAI_API_KEY_PYTEST": "test-key-1",
                "SUPREMEAI_API_KEY_READONLY": "test-key-2",
            },
        )
        self.assertIsInstance(cfg, GatewayConfig)
        self.assertIn("auto", cfg.chains)
        self.assertEqual(cfg.default_chain, "auto")
        self.assertGreater(cfg.rate_limit_max_requests, 0)

    def test_chain_for_bare_and_prefixed_models(self):
        policy_path = REPO_ROOT / "gateway" / "routing_policy.json"
        raw = json.loads(policy_path.read_text(encoding="utf-8"))
        cfg = parse_routing_policy(raw, env={})
        chain_qual = cfg.chain_for("anthropic/claude-sonnet-4-5")
        self.assertEqual(chain_qual[0].model, "anthropic/claude-sonnet-4-5")
        chain_bare = cfg.chain_for("claude-sonnet-4-5")
        self.assertEqual(chain_bare[0].model, "anthropic/claude-sonnet-4-5")

    def test_drift_rejection_unknown_provider(self):
        invalid_raw = {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "chains": {
                "auto": [
                    {"provider": "unauthorized-llm-provider", "model": "test-model"}
                ]
            },
            "default_chain": "auto",
            "rate_limit": {"window_seconds": 60, "max_requests": 10},
        }
        with self.assertRaises(ConfigError):
            parse_routing_policy(invalid_raw)

    def test_empty_chain_rejection(self):
        invalid_raw = {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "chains": {"auto": []},
            "default_chain": "auto",
            "rate_limit": {"window_seconds": 60, "max_requests": 10},
        }
        with self.assertRaises(ConfigError):
            parse_routing_policy(invalid_raw)

    def test_missing_default_chain_rejection(self):
        invalid_raw = {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "chains": {
                "custom": [{"provider": "groq", "model": "llama-3.1-8b-instant"}]
            },
            "default_chain": "nonexistent",
            "rate_limit": {"window_seconds": 60, "max_requests": 10},
        }
        with self.assertRaises(ConfigError):
            parse_routing_policy(invalid_raw)


class TestRateLimiter(unittest.TestCase):
    def test_sliding_window_within_limit(self):
        clock_time = 1000
        limiter = SlidingWindowLimiter(
            window_s=60, max_requests=2, clock=lambda: clock_time
        )

        d1 = asyncio.run(limiter.check("client-1"))
        self.assertTrue(d1.allowed)
        self.assertEqual(d1.remaining, 1)

        d2 = asyncio.run(limiter.check("client-1"))
        self.assertTrue(d2.allowed)
        self.assertEqual(d2.remaining, 0)

        # 3rd request in same window must be rejected
        d3 = asyncio.run(limiter.check("client-1"))
        self.assertFalse(d3.allowed)
        self.assertIsNotNone(d3.retry_after_s)
        self.assertGreaterEqual(d3.retry_after_s, 1)

    def test_sliding_window_expiration(self):
        time_holder = [1000]
        limiter = SlidingWindowLimiter(
            window_s=10, max_requests=1, clock=lambda: time_holder[0]
        )

        d1 = asyncio.run(limiter.check("client-2"))
        self.assertTrue(d1.allowed)

        # Advance past window
        time_holder[0] += 11
        d2 = asyncio.run(limiter.check("client-2"))
        self.assertTrue(d2.allowed)


class TestProviderChain(unittest.TestCase):
    def test_execute_chain_first_success(self):
        ep1 = Endpoint(provider="groq", model="llama-3.1-8b-instant")
        ep2 = Endpoint(provider="gemini", model="gemini-1.5-flash")

        async def fake_attempt(endpoint: Endpoint, payload: bytes) -> AttemptResult:
            return AttemptResult(
                endpoint=endpoint,
                status=200,
                headers={"content-type": "application/json"},
                body=b'{"choices":[{"message":{"content":"ok"}}]}',
                latency_ms=45,
            )

        res = asyncio.run(
            execute_chain(
                (ep1, ep2),
                b'{"messages":[]}',
                attempt_fn=fake_attempt,
                circuit_breaker=CircuitBreaker(),
            )
        )
        self.assertEqual(res.status, 200)
        self.assertEqual(res.endpoint.provider, "groq")

    def test_execute_chain_failover_recovery(self):
        ep1 = Endpoint(provider="groq", model="llama-3.1-8b-instant")
        ep2 = Endpoint(provider="gemini", model="gemini-1.5-flash")

        async def fake_attempt(endpoint: Endpoint, payload: bytes) -> AttemptResult:
            if endpoint.provider == "groq":
                return AttemptResult(
                    endpoint=endpoint,
                    status=503,
                    headers={"retry-after": "5"},
                    body=b'{"error":"overloaded"}',
                    latency_ms=20,
                )
            return AttemptResult(
                endpoint=endpoint,
                status=200,
                headers={},
                body=b'{"choices":[{"message":{"content":"fallback ok"}}]}',
                latency_ms=150,
            )

        res = asyncio.run(
            execute_chain(
                (ep1, ep2),
                b'{"messages":[]}',
                attempt_fn=fake_attempt,
                circuit_breaker=CircuitBreaker(),
            )
        )
        self.assertEqual(res.status, 200)
        self.assertEqual(res.endpoint.provider, "gemini")

    def test_execute_chain_exhaustion_raises(self):
        ep1 = Endpoint(provider="groq", model="m1")
        ep2 = Endpoint(provider="gemini", model="m2")

        async def fake_attempt(endpoint: Endpoint, payload: bytes) -> AttemptResult:
            return AttemptResult(
                endpoint=endpoint,
                status=500,
                headers={},
                body=b'{"error":"down"}',
                latency_ms=10,
            )

        with self.assertRaises(ProviderChainExhausted) as ctx:
            asyncio.run(
                execute_chain(
                    (ep1, ep2),
                    b'{"messages":[]}',
                    attempt_fn=fake_attempt,
                    circuit_breaker=CircuitBreaker(),
                )
            )

        self.assertEqual(len(ctx.exception.ledger), 2)

    def test_qdrant_memory_store_integration(self):
        store = QdrantMemoryStore(
            qdrant_url="http://127.0.0.1:9999",
            api_key="test-key",
            timeout_s=0.2,
        )
        self.assertEqual(store.qdrant_url, "http://127.0.0.1:9999")
        self.assertEqual(store.api_key, "test-key")

        # Embedding generation is deterministic and normalized
        v1 = store._embed("supremeai architecture")
        self.assertEqual(len(v1), 128)
        self.assertAlmostEqual(sum(x * x for x in v1), 1.0, places=4)

        # In-memory fallback functions offline when Qdrant is unreachable
        item = store.store(
            text="Autonomous multi-agent orchestration", namespace="core"
        )
        self.assertTrue(item.id.startswith("mem-"))
        self.assertEqual(item.namespace, "core")

        hits = store.search(query="orchestration", namespace="core")
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["text"], "Autonomous multi-agent orchestration")
        self.assertGreater(hits[0]["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
