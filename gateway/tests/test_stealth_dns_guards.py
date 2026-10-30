"""
tests/test_stealth_dns_guards.py — guards for the Oct-23 stealth-relay outage class.

Outage signature: STEALTH_WEBHOOK_URL held a value whose hostname failed DNS
([Errno -2] Name or service not known) — every chat reply died in ~0.1s while
/health + /readyz reported healthy/ready (they only checked env-var presence),
and neither logs nor the 502 body identified the broken host. Guest chat fell
back to the flat "Webhook relay is currently offline or unreachable." line with
no diagnostic context.

Guards (dual-mode: pytest OR plain `python3 test_stealth_dns_guards.py`):
  G1  normalize_stealth_url strips env-quoting accidents (\"...\" / '...')
  G2  normalize_stealth_url collapses internal whitespace
  G3  normalize_stealth_url repairs doubled scheme (https://https:// -> ENOTFOUND host 'https')
  G4  normalize_stealth_url legacy behaviors pinned (/mcp, /chat, /v1, query, schemeless)
  G5  _mask_host strips userinfo/path/query and truncates the host
  G6  forward_stealth_webhook on DNS ConnectError -> 502 with masked host + reason=dns
  G7  forward_stealth_webhook refused connection -> reason=refused (class split)
  G8  reply-wrapping path still works and emits exactly one \"id\" key (P3 pin)
  G9  workers.dev APEX config raises a one-shot CRITICAL log
  G10 /readyz -> 503 when configured host does not resolve, with a GENERIC reason
      (redaction contract #1902: no env-var name, no Infisical, no host detail)
  G11 /readyz -> 200 ready when DNS ok; /readyz -> 503 when unconfigured;
      body is the redacted readiness contract (status/chat_ready/timestamp)
  G12 /health stays 200 (liveness) and REDACTED (#1729): stealth_dns absent
Run layouts: satellite (service.*) — mirrors gateway/service.* byte-for-byte.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Dict

BASE = os.path.dirname(os.path.abspath(__file__))
SAT = os.path.abspath(os.path.join(BASE, ".."))
if SAT not in sys.path:
    sys.path.insert(0, SAT)

import httpx  # noqa: E402

RESULTS: list = []


def check(name: str, cond: bool, evidence: str = "") -> None:
    RESULTS.append((name, bool(cond), evidence))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {evidence}" if evidence and not cond else ""))


# ── Import target modules (dual layout, canonical-first) ──────────────────────
# Identity rule (drift class F-K, 2026-10-28): always bind the CANONICAL
# gateway.service.* module when it exists. Bare service.* imports create a SECOND
# module object (split-brain singletons: telemetry collector, adapters state) the
# moment any file puts the gateway/ dir on sys.path — order-dependent suite reds.
# Satellite repos (no gateway/ package) fall back to the bare layout.
os.environ["STEALTH_WEBHOOK_URL"] = "https://dead-host.invalid/v1/chat/completions"
try:
    from gateway.service.providers import adapters as ad  # noqa: E402
    from gateway.service import app as appmod  # noqa: E402
except ImportError:  # satellite layout: repo root IS the gateway package dir
    from service.providers import adapters as ad  # noqa: E402
    import service.app as appmod  # noqa: E402


# ── G1..G4 normalize_stealth_url ────────────────────────────────────────────
def test_normalize() -> None:
    print("G1..G4 normalize_stealth_url")
    check("G1 double-quoted env value unquoted",
          ad.normalize_stealth_url('"https://relay.example.com"') == "https://relay.example.com/v1/chat/completions")
    check("G1b single-quoted env value unquoted",
          ad.normalize_stealth_url("'https://relay.example.com'").startswith("https://relay.example.com/v1/chat/completions"))
    check("G2 internal whitespace collapsed (ENOTFOUND 'relay example')",
          ad.normalize_stealth_url("https://relay example.com") == "https://relayexample.com/v1/chat/completions")
    check("G3 doubled scheme repaired (host would be 'https')",
          ad.normalize_stealth_url("https://https://relay.example.com") == "https://relay.example.com/v1/chat/completions")
    check("G4a /mcp suffix stripped",
          ad.normalize_stealth_url("https://x.example.com/mcp") == "https://x.example.com/v1/chat/completions")
    check("G4b /chat suffix stripped",
          ad.normalize_stealth_url("https://x.example.com/chat").endswith("/v1/chat/completions"))
    check("G4c /v1 extended not duplicated",
          ad.normalize_stealth_url("https://x.example.com/v1") == "https://x.example.com/v1/chat/completions")
    check("G4d query preserved",
          ad.normalize_stealth_url("https://x.example.com?k=1") == "https://x.example.com/v1/chat/completions?k=1")
    check("G4e schemeless host gets http:// + endpoint",
          ad.normalize_stealth_url("x.example.com") == "http://x.example.com/v1/chat/completions")
    check("G4f clean URL unchanged",
          ad.normalize_stealth_url("https://x.example.com/v1/chat/completions") == "https://x.example.com/v1/chat/completions")
    check("G4g empty -> empty",
          ad.normalize_stealth_url("   ") == "")


# ── G5 _mask_host ───────────────────────────────────────────────────────────
def test_mask_host() -> None:
    print("G5 _mask_host")
    masked = ad._mask_host("https://user:tok@supremeai-worker.paykaribazaronline.workers.dev/v1/chat/completions?x=1")
    check("G5a userinfo/path/query stripped, host truncated", masked == "supr…workers.dev" and "tok" not in masked and "chat" not in masked, f"got {masked!r}")
    check("G5b short host kept readable", ad._mask_host("https://x.com/v1") == "x.com")
    check("G5c unparseable safe fallback", ad._mask_host("http://") == "(unparseable-host)")


# ── Fake transport for forwarder tests ──────────────────────────────────────
class _FakeResponse:
    def __init__(self, status_code: int, data: Any) -> None:
        self.status_code = status_code
        self._data = data

    def json(self) -> Any:
        return self._data

    @property
    def text(self) -> str:
        return str(self._data)


class _FakeClientFactory:
    def __init__(self, behavior: str) -> None:
        self._behavior = behavior
        self.last_call: Dict[str, Any] = {}

    def __call__(self, *a: Any, **k: Any) -> "_FakeClient":
        return _FakeClient(self._behavior, self.last_call)


class _FakeClient:
    def __init__(self, behavior: str, last_call: Dict[str, Any]) -> None:
        self._behavior = behavior
        self._last_call = last_call

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    async def post(self, url: str, **k: Any) -> Any:
        self._last_call["url"] = url
        self._last_call.update(k)
        if self._behavior == "dns":
            raise httpx.ConnectError("[Errno -2] Name or service not known")
        if self._behavior == "refused":
            raise httpx.ConnectError("[Errno 111] Connection refused")
        return _FakeResponse(200, {"reply": "hello from relay"})


def test_forwarder() -> None:
    print("G6..G8 forward_stealth_webhook")
    real_client = httpx.AsyncClient
    # Defense-in-depth: a REAL client cached in ad._STEALTH_CLIENT by an earlier
    # test file's forward call (2026-10-28: model_cascades' class-level post
    # patch caches a real client) makes _get_stealth_client() return BEFORE
    # consulting the patched httpx.AsyncClient — drop the pool so the fake
    # factory below is authoritative. Fakes lack is_closed, so nothing is cached
    # by this test itself.
    ad._STEALTH_CLIENT = None
    try:
        factory = _FakeClientFactory("dns")
        ad.httpx.AsyncClient = factory  # type: ignore[assignment]
        status, body = asyncio.run(ad.forward_stealth_webhook("https://deadrelay.example.com", None, {"model": "m", "messages": []}))
        check("G6a DNS failure -> 502", status == 502)
        check("G6b error carries masked host", "dead…" in str(body.get("error", "")) or "deadr" in str(body.get("error", "")), str(body)[:120])
        check("G6c structured host field", isinstance(body.get("host"), str) and "example.com" in body["host"], str(body.get("host")))
        check("G6d classified as dns", body.get("reason") == "dns")
        check("G6e target normalized to /v1/chat/completions", factory.last_call.get("url", "").endswith("/v1/chat/completions"), str(factory.last_call.get("url")))

        factory2 = _FakeClientFactory("refused")
        ad.httpx.AsyncClient = factory2  # type: ignore[assignment]
        status2, body2 = asyncio.run(ad.forward_stealth_webhook("https://down.example.com", None, {"messages": []}))
        check("G7 refused classified (not dns)", status2 == 502 and body2.get("reason") == "refused", str(body2))

        factory3 = _FakeClientFactory("ok")
        ad.httpx.AsyncClient = factory3  # type: ignore[assignment]
        status3, body3 = asyncio.run(ad.forward_stealth_webhook("https://ok.example.com", "sekret", {"model": "m", "messages": []}))
        check("G8a reply-wrapped OpenAI format", status3 == 200 and body3.get("choices", [{}])[0].get("message", {}).get("content") == "hello from relay")
        check("G8b exactly one id key (P3 pin)", isinstance(body3, dict) and list(body3.keys()).count("id") == 1, str(list(body3.keys())))
        check("G8c secret forwarded as Authorization", factory3.last_call.get("headers", {}).get("Authorization") == "Bearer sekret")
    finally:
        ad.httpx.AsyncClient = real_client  # type: ignore[assignment]


# ── G9 apex config CRITICAL ─────────────────────────────────────────────────
def test_apex_warning() -> None:
    print("G9 workers.dev apex one-shot CRITICAL")
    ad._stealth_warned.clear()
    records: list = []

    class _H(logging.Handler):
        def emit(self, r: logging.LogRecord) -> None:
            records.append(r)

    h = _H()
    ad.logger.addHandler(h)
    try:
        ad.normalize_stealth_url("https://paykaribazaronline.workers.dev")
        ad.normalize_stealth_url("https://paykaribazaronline.workers.dev")  # second call: no repeat
        crits = [r for r in records if r.levelno == logging.CRITICAL and "APEX" in r.getMessage()]
        check("G9 apex raises CRITICAL exactly once", len(crits) == 1, f"got {len(crits)}")
    finally:
        ad.logger.removeHandler(h)
        ad._stealth_warned.clear()


# ── G10..G12 endpoint behavior (TestClient, snapshot monkeypatched) ─────────
def test_endpoints() -> None:
    print("G10..G12 /readyz + /health")
    from fastapi.testclient import TestClient

    client = TestClient(appmod.app)
    real = appmod._stealth_dns_snapshot
    # Pin the import-captured global: /readyz branches on `if STEALTH_WEBHOOK_URL`
    # BEFORE consulting _stealth_dns_snapshot, so a leaked empty global from an
    # earlier test file (2026-10-28: reply-path reload left "") silently bypassed
    # every monkeypatched snapshot below — G10b/G10c/G11a/G11b suite reds.
    real_url = appmod.STEALTH_WEBHOOK_URL
    appmod.STEALTH_WEBHOOK_URL = "https://dead-host.invalid/v1/chat/completions"

    async def _bad(force: bool = False) -> Dict[str, Any]:
        return {"ok": False, "checked_at": 1.0, "detail": "host dead… invalid does not resolve ([Errno -2] Name or service not known) — fix Infisical STEALTH_WEBHOOK_URL"}

    async def _good(force: bool = False) -> Dict[str, Any]:
        return {"ok": True, "checked_at": 1.0, "detail": "resolved 2 addr(s)"}

    appmod._stealth_dns_snapshot = _bad  # type: ignore[assignment]
    try:
        r = client.get("/readyz")
        check("G10a readyz 503 on unresolvable host", r.status_code == 503, str(r.status_code))
        j = r.json()
        # Redaction contract (#1902): the Oct-23 fix hint shipped the env-var name,
        # the secret store and the masked host to unauthenticated callers; the
        # capability semantics stay loud via the 503, the posture detail is
        # operator-gated (/internal/status).
        reason = j.get("reason", "")
        check("G10b reason is generic (no env var / store / host detail)",
              "STEALTH_WEBHOOK_URL" not in reason and "Infisical" not in reason
              and "invalid" not in reason, reason[:120])
        check("G10c readyz ships NO stealth posture unauth",
              "stealth_dns" not in j and "stealth_priority1_configured" not in j,
              str(sorted(j.keys())))
        rh = client.get("/health")
        check("G12a /health stays 200 (liveness)", rh.status_code == 200, str(rh.status_code))
        check("G12b /health REDACTED: stealth_dns absent (#1729)",
              "stealth_dns" not in rh.json(), str(sorted(rh.json().keys())))

        appmod._stealth_dns_snapshot = _good  # type: ignore[assignment]
        r2 = client.get("/readyz")
        check("G11a readyz 200 ready when DNS ok", r2.status_code == 200 and r2.json().get("status") == "ready", str(r2.status_code))
        check("G11b readyz body is the redacted readiness contract",
              set(r2.json().keys()) == {"status", "chat_ready", "timestamp"},
              str(sorted(r2.json().keys())))
    finally:
        appmod.STEALTH_WEBHOOK_URL = real_url
        appmod._stealth_dns_snapshot = real  # type: ignore[assignment]


def test_unconfigured(monkeypatched: Dict[str, Any] | None = None) -> None:
    print("G11c unconfigured -> 503 (no env mutation: snapshot returns not-configured)")
    from fastapi.testclient import TestClient

    client = TestClient(appmod.app)
    real_env = os.environ.get("STEALTH_WEBHOOK_URL")
    os.environ["STEALTH_WEBHOOK_URL"] = ""
    try:
        # module captured STEALTH_WEBHOOK_URL at import; emulate unconfigured via empty snapshot
        real = appmod._stealth_dns_snapshot

        async def _unset(force: bool = False) -> Dict[str, Any]:
            return {"ok": None, "checked_at": 0.0, "detail": "STEALTH_WEBHOOK_URL not configured"}

        appmod._stealth_dns_snapshot = _unset  # type: ignore[assignment]
        # force the endpoint down the unconfigured branch by monkeypatching the flag
        real_url = appmod.STEALTH_WEBHOOK_URL
        appmod.STEALTH_WEBHOOK_URL = ""
        try:
            r = client.get("/readyz")
            check("G11c readyz 503 when unconfigured", r.status_code == 503 and "not configured" in r.json().get("reason", ""), str(r.status_code))
        finally:
            appmod.STEALTH_WEBHOOK_URL = real_url
            appmod._stealth_dns_snapshot = real  # type: ignore[assignment]
    finally:
        if real_env is None:
            os.environ.pop("STEALTH_WEBHOOK_URL", None)
        else:
            os.environ["STEALTH_WEBHOOK_URL"] = real_env


# ── pytest wrappers ─────────────────────────────────────────────────────────
def _assert_from(mark: int) -> None:
    """Assert only this wrapper's own guard slice.

    The historical _assert_all() asserted the WHOLE accumulated RESULTS, so one
    real check failure failed every wrapper after it (2026-10-28: 4 real G10/G11
    failures surfaced as 5 pytest failures, masking the root cause). Each block
    is still asserted exactly once — by its own wrapper."""
    failed = [r for r in RESULTS[mark:] if not r[1]]
    assert not failed, f"failed guards: {[f[0] for f in failed]}"


def test_normalize_stealth_url() -> None:  # pragma: no cover
    mark = len(RESULTS)
    test_normalize()
    _assert_from(mark)


def test_mask_host_fn() -> None:  # pragma: no cover
    mark = len(RESULTS)
    test_mask_host()
    _assert_from(mark)


def test_forwarder_paths() -> None:  # pragma: no cover
    mark = len(RESULTS)
    test_forwarder()
    _assert_from(mark)


def test_apex_critical() -> None:  # pragma: no cover
    mark = len(RESULTS)
    test_apex_warning()
    _assert_from(mark)


def test_probe_endpoints() -> None:  # pragma: no cover
    mark = len(RESULTS)
    test_endpoints()
    test_unconfigured()
    _assert_from(mark)


if __name__ == "__main__":
    test_normalize()
    test_mask_host()
    test_forwarder()
    test_apex_warning()
    test_endpoints()
    test_unconfigured()
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n==== {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS ====")
    sys.exit(1 if failed else 0)
