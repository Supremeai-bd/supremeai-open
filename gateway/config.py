"""SupremeAI Gateway — fail-closed configuration (issue #336).

Layer-2 unified provider gateway per api-schemas/gateway.openapi.yaml:
- One SUPREMEAI_API_KEY consumer credential (X-SupremeAI-Key header);
  provider credentials never leave the server side (OpenAPI §security).
- Routing policy is config-driven (``routing_policy.json``), validated
  fail-closed at startup: closed provider enum (gateway-plane superset of
  the agent router's task-router.schema.json enum — its 7 schema providers
  plus the gateway-only ``web`` and ``perplexity`` drivers), non-empty
  ordered chains, positive rate-limit numbers. Unknown providers,
  empty chains, or negative limits REJECT the config — the gateway refuses
  to boot on drift (fail-closed doctrine, mirrors #330's config gate).

Reference routing_policy.json format (documented, deterministic)::

    {
      "schema_version": "gateway-routing/1",
      "chains": {
        "auto":   [{"provider": "groq", "model": "llama-3.1-8b-instant"}, ...],
        "custom": [...]
      },
      "default_chain": "auto",
      "rate_limit": {"window_seconds": 60, "max_requests": 30},
      "api_keys": {
        "supremeai-key-...": {"owner": "dev", "scopes": ["chat", "models"]}
      }
    }

Secrets: api_keys values are loaded from the environment in production
(``SUPREMEAI_API_KEY_<NAME>``); this module never logs key material.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Gateway-plane provider enum (fail-closed). SUPERSET of the agent router's
# task-router.schema.json enum (the 7 schema providers also mirrored in
# scripts/agents/dynamic_router.py): "web" and "perplexity" are gateway-only
# providers with live drivers under gateway/service/providers/ (web_session.py,
# adapters.py PROVIDER_CONFIGS/PROVIDER_MODEL_CASCADES) and hops in the shipped
# routing_policy.json. When the runtime grows a driver, extend THIS enum in the
# same change — a validator copy that lags the runtime makes load_config()
# refuse the repo's own policy (drift class F-J: perplexity hop crashed the
# gateway boot, caught by tests/test_gateway_foundation.py, fixed 2026-10-28).
ALLOWED_PROVIDERS: frozenset[str] = frozenset(
    {
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
)

ALLOWED_SCOPES: frozenset[str] = frozenset({"chat", "models"})
CONFIG_SCHEMA_VERSION = "gateway-routing/1"


class ConfigError(ValueError):
    """Fail-closed config drift — the gateway refuses to boot."""


@dataclass(frozen=True, slots=True)
class Endpoint:
    """One routable model endpoint (mirrors task-router.schema.json ModelEndpoint)."""

    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class ApiKeyRecord:
    owner: str
    scopes: frozenset[str]


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    """Validated, immutable gateway configuration."""

    chains: dict[str, tuple[Endpoint, ...]]
    default_chain: str
    rate_limit_window_s: int
    rate_limit_max_requests: int
    api_keys: dict[str, ApiKeyRecord] = field(default_factory=dict)

    def chain_for(self, model: str) -> tuple[Endpoint, ...]:
        """Resolve the ordered chain for a requested model id.

        ``auto`` (OpenAPI default) resolves the configured default chain.
        A bare model name (e.g. ``gpt-4o-mini``) resolves to the first
        configured chain that contains an endpoint with that model, so
        clients can request a specific model without a dedicated chain name.
        Unknown model names are rejected here — routing never invents chains
        (fail-closed default per task-router doctrine).
        """
        if model == "auto":
            name = self.default_chain
        else:
            name = model if model in self.chains else None
            if name is None:
                # Resolve a bare model name to a chain prioritising that model.
                for endpoints in self.chains.values():
                    for idx, ep in enumerate(endpoints):
                        if ep.model == model or ("/" in ep.model and ep.model.split("/", 1)[1] == model):
                            # Reorder: requested model first, then the rest.
                            reordered = (ep,) + endpoints[:idx] + endpoints[idx + 1 :]
                            return reordered
            if name is None:
                raise ConfigError(f"no routing chain configured for model '{model}'")
        chain = self.chains.get(name)
        if chain is None:
            raise ConfigError(f"no routing chain configured for model '{model}'")
        return chain


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def _parse_endpoint(raw: Any, where: str) -> Endpoint:
    _require(isinstance(raw, dict), f"{where}: endpoint must be an object")
    _require(
        set(raw) == {"provider", "model"},
        f"{where}: endpoint must have exactly provider+model",
    )
    provider, model = raw["provider"], raw["model"]
    _require(
        isinstance(provider, str) and provider in ALLOWED_PROVIDERS,
        f"{where}: provider '{provider}' not in closed enum {sorted(ALLOWED_PROVIDERS)}",
    )
    _require(
        isinstance(model, str)
        and 0 < len(model) <= 128
        and not any(c in model for c in " \t\r\n"),
        f"{where}: invalid model name",
    )
    return Endpoint(provider=provider, model=model)


def parse_routing_policy(
    raw: Any, *, env: dict[str, str] | None = None
) -> GatewayConfig:
    """Validate a routing policy dict fail-closed; returns the frozen config."""
    _require(isinstance(raw, dict), "routing policy must be a JSON object")
    _require(
        raw.get("schema_version") == CONFIG_SCHEMA_VERSION,
        f"schema_version must be exactly '{CONFIG_SCHEMA_VERSION}' (got {raw.get('schema_version')!r})",
    )

    chains_raw = raw.get("chains")
    _require(
        isinstance(chains_raw, dict) and chains_raw, "chains: non-empty object required"
    )
    chains: dict[str, tuple[Endpoint, ...]] = {}
    for name, chain_raw in chains_raw.items():
        _require(
            isinstance(name, str) and 0 < len(name) <= 64,
            f"chains: invalid chain name {name!r}",
        )
        _require(
            isinstance(chain_raw, list) and chain_raw,
            f"chains.{name}: non-empty ordered list required",
        )
        endpoints = tuple(
            _parse_endpoint(e, f"chains.{name}[{i}]") for i, e in enumerate(chain_raw)
        )
        chains[name] = endpoints

    default_chain = raw.get("default_chain", "auto")
    _require(
        isinstance(default_chain, str) and default_chain in chains,
        f"default_chain '{default_chain}' has no configured chain",
    )

    rl = raw.get("rate_limit", {"window_seconds": 60, "max_requests": 30})
    _require(isinstance(rl, dict), "rate_limit must be an object")
    window, max_req = rl.get("window_seconds"), rl.get("max_requests")
    _require(
        isinstance(window, int)
        and not isinstance(window, bool)
        and 0 < window <= 86400,
        "rate_limit.window_seconds must be an integer in (0, 86400]",
    )
    _require(
        isinstance(max_req, int)
        and not isinstance(max_req, bool)
        and 0 < max_req <= 100_000,
        "rate_limit.max_requests must be an integer in (0, 100000]",
    )

    api_keys_raw = raw.get("api_keys", {})
    _require(isinstance(api_keys_raw, dict), "api_keys must be an object")
    env = env if env is not None else dict(os.environ)
    api_keys: dict[str, ApiKeyRecord] = {}
    for key_id, meta in api_keys_raw.items():
        # NOTE: ids deliberately avoid OpenAI/GitHub-shaped credential prefixes
        # bridge secret scan never mistakes reference ids for live credentials.
        _require(
            isinstance(key_id, str)
            and key_id.startswith("supremeai-key-")
            and len(key_id) >= 20,
            "api_keys: key ids must look like supremeai-key-<id> (>=20 chars)",
        )
        _require(
            isinstance(meta, dict) and set(meta) == {"owner", "scopes"},
            f"api_keys entry {key_id[:14]}…: must have exactly owner+scopes",
        )
        scopes_raw = meta["scopes"]
        _require(
            isinstance(scopes_raw, list)
            and scopes_raw
            and set(scopes_raw) <= set(ALLOWED_SCOPES),
            f"api_keys entry {key_id[:14]}…: scopes must be a non-empty subset of {sorted(ALLOWED_SCOPES)}",
        )
        # Secret material: in production the VALUE rides the environment; a
        # literal second field in the JSON is rejected (never commit secrets).
        env_name = f"SUPREMEAI_API_KEY_{meta['owner'].upper().replace('-', '_')}"
        if env.get(env_name) is None:
            # Missing key material: skip entry; gateway runs guest-only.
            continue
        api_keys[key_id] = ApiKeyRecord(
            owner=str(meta["owner"]), scopes=frozenset(scopes_raw)
        )

    return GatewayConfig(
        chains=chains,
        default_chain=default_chain,
        rate_limit_window_s=window,
        rate_limit_max_requests=max_req,
        api_keys=api_keys,
    )


def load_config(
    path: str | Path | None = None, *, env: dict[str, str] | None = None
) -> GatewayConfig:
    """Load + validate routing_policy.json (default path: gateway/routing_policy.json)."""
    p = Path(path) if path else Path(__file__).resolve().parent / "routing_policy.json"
    _require(p.is_file(), f"routing policy file not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"routing policy is not valid JSON: {exc}") from exc
    return parse_routing_policy(raw, env=env)


def canonical_fixture() -> dict:
    """The deterministic reference policy used by tests and the smoke suite."""
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "chains": {
            "auto": [
                {"provider": "groq", "model": "llama-3.1-8b-instant"},
                {"provider": "openai", "model": "gpt-4o-mini"},
                {"provider": "anthropic", "model": "claude-sonnet-4-5"},
            ],
        },
        "default_chain": "auto",
        "rate_limit": {"window_seconds": 60, "max_requests": 4},
        "api_keys": {
            "supremeai-key-test-0000000001": {
                "owner": "pytest",
                "scopes": ["chat", "models"],
            },
            "supremeai-key-test-0000000002": {
                "owner": "readonly",
                "scopes": ["models"],
            },
        },
    }


def utc_ts() -> int:
    """Wall-clock seconds (rate-limit reset math only — never for digests)."""
    return int(time.time())
