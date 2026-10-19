#!/usr/bin/env python3
"""Gateway shield reference implementation (#469, Rules 18-22).

Executable spec for the unified provider gateway (supremeai-api):
- Rule 18: single external entry point; OpenAI-compatible surface
  (/v1/models, /v1/chat/completions) — ROUTES is the contract.
- Rule 19: vault-only provider keys. This module NEVER reads provider
  credentials; provider access is via opaque handles only. A structural
  invariant test asserts no provider key material exists here.
- Rule 20: deterministic failover chain (groq -> gemini -> fallback)
  with transparent rotation and model degradation metadata.
- Rule 21: one-key SSOT. Downstream callers authenticate with
  SUPREMEAI_API_KEY via Bearer token or X-SupremeAI-Key header. Any
  direct provider credential presented by a caller is rejected.
- Rule 22: tenant quota (RPS/RPM) + usage attribution events.

Pure-stdlib, deterministic, offline-testable, fail-closed.
Self-test: python3 gateway_shield_reference.py --self-test
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

ROUTES = ("/v1/models", "/v1/chat/completions")
SSOT_KEY_NAME = "SUPREMEAI_API_KEY"
SSOT_HEADER = "X-SupremeAI-Key"
DEFAULT_CHAIN = ("groq", "gemini", "fallback")
PROVIDER_ENV_NAMES = frozenset(
    {
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    }
)


class GatewayError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def authenticate(headers: dict, env: dict) -> dict:
    """Rule 21 SSOT auth (fail-closed).

    Accepts exactly one credential form: Bearer <key> or X-SupremeAI-Key.
    The presented secret must equal env[SSOT_KEY_NAME]. Provider keys
    presented by callers are rejected on principle (they are not SSOT
    material and MUST not be accepted downstream).
    """
    ssot = env.get(SSOT_KEY_NAME)
    if not ssot or not isinstance(ssot, str) or len(ssot) < 16:
        raise GatewayError(
            500, "ssot_unconfigured", "gateway has no SUPREMEAI_API_KEY configured"
        )
    presented = None
    authz = headers.get("authorization") or headers.get("Authorization")
    if authz and authz.startswith("Bearer "):
        presented = authz[len("Bearer ") :].strip()
    elif headers.get(SSOT_HEADER):
        presented = headers[SSOT_HEADER].strip()
    if not presented:
        raise GatewayError(
            401, "missing_credential", f"present Bearer token or {SSOT_HEADER} header"
        )
    if presented != ssot:
        if presented.lower().startswith(("gsk_", "aiza=", "sk-or-", "sk-ant")):
            raise GatewayError(
                401,
                "provider_key_rejected",
                "direct provider credentials are never "
                "accepted at the gateway (Rule 19/21)",
            )
        raise GatewayError(401, "invalid_credential", "SSOT key mismatch")
    return {"authenticated": True, "scheme": "ssot"}


def next_target(chain: tuple = DEFAULT_CHAIN, failed: tuple = ()) -> str | None:
    """Rule 20: first chain hop not yet failed; None when exhausted."""
    if not chain:
        raise GatewayError(500, "chain_unconfigured", "empty failover chain")
    bad = set(failed or ())
    for hop in chain:
        if hop not in bad:
            return hop
    return None


def failover_decision(chain: tuple = DEFAULT_CHAIN, failed: tuple = ()) -> dict:
    """Deterministic Rule 20 decision record for a request lifecycle."""
    target = next_target(chain, failed)
    return {
        "chain": list(chain),
        "failed_hops": list(failed or ()),
        "target": target,
        "exhausted": target is None,
        "status": 503 if target is None else 200,
        "served_by_header": target,
    }


def quota_check(tenant: dict, counters: dict, now_ts: float) -> dict:
    """Rule 22: RPS/RPM sliding-window admission for one tenant.

    tenant: {"tenant": str, "rps": int, "rpm": int}
    counters: {"second_bucket": [ts...], "minute_bucket": [ts...]}
    Mutates counters (append + prune). Deterministic.
    """
    name = tenant.get("tenant")
    if (
        not name
        or not isinstance(tenant.get("rps"), int)
        or not isinstance(tenant.get("rpm"), int)
    ):
        raise GatewayError(500, "bad_tenant_config", "tenant/rps/rpm required")
    sec = [t for t in counters.get("second_bucket", []) if now_ts - t < 1.0]
    minute = [t for t in counters.get("minute_bucket", []) if now_ts - t < 60.0]
    allowed = len(sec) < tenant["rps"] and len(minute) < tenant["rpm"]
    if allowed:
        sec.append(now_ts)
        minute.append(now_ts)
    counters["second_bucket"], counters["minute_bucket"] = sec, minute
    return {
        "tenant": name,
        "allowed": allowed,
        "limit": {"rps": tenant["rps"], "rpm": tenant["rpm"]},
        "usage": {"rps_window": len(sec), "rpm_window": len(minute)},
    }


def attribution_event(
    tenant: str, model: str, provider: str, tokens: int, now: datetime | None = None
) -> dict:
    """Rule 22: usage telemetry attribution (key-plane safe: no secrets)."""
    if tokens < 0:
        raise GatewayError(500, "bad_usage", "negative tokens")
    return {
        "tenant": tenant,
        "model": model,
        "provider": provider,
        "total_tokens": tokens,
        "ts": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def no_provider_key_material(text: str) -> bool:
    """Structural invariant helper (Rule 19): a config blob must carry no
    provider credential assignments. NAME=value / NAME: value with real
    material fails; vault/indirection placeholders pass."""
    for name in PROVIDER_ENV_NAMES:
        for m in re.finditer(rf"{name}\s*[=:]\s*(\S+)", text):
            value = m.group(1).strip("'\"").rstrip(",")
            if value and not value.startswith(("<", "${", "vault:", "vault://")):
                return False
    return True


def _self_test() -> int:
    env = {SSOT_KEY_NAME: "ssot-key-0123456789abcdef"}  # gitleaks:allow
    assert authenticate({"Authorization": "Bearer ssot-key-0123456789abcdef"}, env)
    assert authenticate({SSOT_HEADER: "ssot-key-0123456789abcdef"}, env)
    for h in (
        {},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer wrong-key-0123456789"},
        {SSOT_HEADER: "wrong-key-0123456789abcdef"},
    ):
        try:
            authenticate(h, env)
            raise AssertionError("expected 401")
        except GatewayError as e:
            assert e.status == 401, e.status
    try:
        authenticate({"Authorization": "Bearer gsk_provider_material_123"}, env)
        raise AssertionError("provider key must be rejected")
    except GatewayError as e:
        assert e.code == "provider_key_rejected"
    try:
        authenticate({}, {})
        raise AssertionError("unconfigured ssot must 500")
    except GatewayError as e:
        assert e.status == 500
    assert next_target(DEFAULT_CHAIN, ()) == "groq"
    assert next_target(DEFAULT_CHAIN, ("groq",)) == "gemini"
    assert next_target(DEFAULT_CHAIN, ("groq", "gemini")) == "fallback"
    assert next_target(DEFAULT_CHAIN, DEFAULT_CHAIN) is None
    d = failover_decision(DEFAULT_CHAIN, ("groq",))
    assert d["target"] == "gemini" and d["served_by_header"] == "gemini"
    d2 = failover_decision(DEFAULT_CHAIN, DEFAULT_CHAIN)
    assert d2["exhausted"] and d2["status"] == 503
    t, c = {"tenant": "acme", "rps": 2, "rpm": 3}, {}
    assert quota_check(t, c, 1.0)["allowed"]
    assert quota_check(t, c, 1.1)["allowed"]
    assert not quota_check(t, c, 1.2)["allowed"], "3rd hit within 1s > rps=2"
    assert quota_check(t, c, 2.0)["allowed"], "new second window; minute=3"
    assert not quota_check(t, c, 2.1)["allowed"], "minute bucket full (rpm=3)"
    assert quota_check(t, c, 120.0)["allowed"], "windows pruned"
    ev = attribution_event("acme", "llm-large", "groq", 128)
    assert ev["tenant"] == "acme" and ev["total_tokens"] == 128
    assert no_provider_key_material("GEMINI_MODEL=x\n# safe") is True
    names = sorted(PROVIDER_ENV_NAMES)
    sample = names[0] + "=abc123"
    assert no_provider_key_material(sample) is False
    vaulted = names[1] + ": vault://render"
    assert no_provider_key_material(vaulted) is True
    try:
        quota_check({"tenant": "x"}, {}, 1.0)
        raise AssertionError("bad tenant config must fail-closed")
    except GatewayError:
        pass
    print("self-test OK: gateway_shield_reference")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    print(
        json.dumps(
            {
                "routes": ROUTES,
                "chain": list(DEFAULT_CHAIN),
                "ssot": {"env": SSOT_KEY_NAME, "header": SSOT_HEADER},
            }
        )
    )
    sys.exit(0)
