"""
test_reply_path_guards.py — regression guards for the stealth chat reply path.

Guards three defect classes found in the live deployed gateway (service/app.py +
service/providers/web_session.py):

  D1. Guest-class requests (x-guest-mode / studio origin / "guest"-style tokens)
      bypassed auth AND had no rate limit -> the single paid reply path
      (stealth relay) was open to unlimited free-tier abuse.
  D2. The native web-session path fabricated success replies
      ("[<PROVIDER> Web Session Active] Authenticated via ...") and credited
      account health (mark_success) for requests that never executed.
  D3. /health always reported "healthy" even with no configured chat reply
      path -> monitoring blind spot (tower dashboard showed healthy during a
      full relay outage). /readyz now carries the capability signal.

Dual-mode: runs under pytest OR as a plain script (python tests/test_reply_path_guards.py).
Layout-aware: works in the satellite repo root (service/...) and in the open-repo
mirror layout (gateway/service/...). Skips gracefully when fastapi is absent.
"""
import asyncio
import importlib
import importlib.util
import json
import os
import sys

if importlib.util.find_spec("fastapi") is None:
    if "pytest" in sys.modules:
        import pytest

        pytest.skip("fastapi not installed", allow_module_level=True)
    print("SKIP: fastapi not installed; reply-path guards not verifiable here")
    sys.exit(0)

from fastapi.testclient import TestClient  # noqa: E402

# repo-root on sys.path for plain-script mode (pytest run from root already has it)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

app_module = None
ws_module = None
try:  # satellite layout (repo root)
    import service.app as app_module  # type: ignore[no-redef]
    try:
        from service.providers import web_session as ws_module
    except ImportError:
        ws_module = None
except ImportError:  # open-repo mirror layout
    try:
        import gateway.service.app as app_module  # type: ignore[no-redef]
        try:
            from gateway.service.providers import web_session as ws_module  # type: ignore[no-redef]
        except ImportError:
            ws_module = None  # open mirror does not carry web_session.py
    except ImportError:
        app_module = None

if app_module is None:
    if "pytest" in sys.modules:
        import pytest

        pytest.skip("gateway app module not importable here", allow_module_level=True)
    print("SKIP: gateway app module not importable in this layout")
    sys.exit(0)

PASS, FAIL = 0, []


def check(name: str, cond: bool, detail: str = ""):
    global PASS
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        if "pytest" in sys.modules:  # fail-fast under pytest runners
            raise AssertionError(f"{name} {detail}")
        print(f"  FAIL  {name} {detail}")


_TEST_ENV_KEYS = ("STEALTH_WEBHOOK_URL", "GUEST_RATE_LIMIT_PER_MIN", "SUPREMEAI_API_KEY", "ENVIRONMENT")


def reload_app(**env):
    """Reload service.app with a controlled env. NOTE: env is intentionally left
    set after reload — _verify_client_auth re-reads SUPREMEAI_API_KEY per request,
    so restoring immediately would break keyed-auth cases. main() cleans up."""
    os.environ.update(env)
    importlib.reload(app_module)
    if hasattr(app_module, "_guest_hits"):
        app_module._guest_hits.clear()  # absent on pre-fix code — differential mode
    return TestClient(app_module.app)


def guest_post(c, ip=None, **headers):
    h = {"x-guest-mode": "true"}
    h.update(headers)
    if ip:
        h["X-Forwarded-For"] = ip
    return c.post("/v1/chat/completions", headers=h,
                  json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]})


def test_guest_throttle():
    print("[D1] guest-class requests are throttled; keyed auth is not")
    c = reload_app(STEALTH_WEBHOOK_URL="http://127.0.0.1:9/unreachable",
                   GUEST_RATE_LIMIT_PER_MIN="3", ENVIRONMENT="development")

    codes = [guest_post(c).status_code for _ in range(5)]
    check("first 3 guest requests processed (not 429)",
          codes[:3] == [502, 502, 502], f"got {codes}")
    check("request 4 throttled with 429", codes[3] == 429, f"got {codes}")
    check("request 5 still throttled", codes[4] == 429, f"got {codes}")

    r = guest_post(c)
    check("429 carries Retry-After header", r.status_code == 429 and "retry-after" in {k.lower() for k in r.headers},
          f"status={r.status_code} headers={dict(r.headers)}")

    # Bearer "guest" token must take the SAME throttle path (shared token extractor).
    # Exhaust the bucket first so a non-throttled request is deterministically 502.
    if hasattr(app_module, "_guest_hits"):
        app_module._guest_hits.clear()
        for _ in range(3):
            guest_post(c)
    r2 = c.post("/v1/chat/completions", headers={"Authorization": "Bearer guest"},
                json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]})
    check("Bearer guest bypasses auth but not throttle",
          r2.status_code == 429, f"got {r2.status_code}")


def test_keyed_auth_unthrottled():
    print("[D1] keyed auth never throttled; fail-closed preserved")
    c = reload_app(STEALTH_WEBHOOK_URL="http://127.0.0.1:9/unreachable",
                   GUEST_RATE_LIMIT_PER_MIN="2", SUPREMEAI_API_KEY="test-master-key-123")
    codes = []
    for _ in range(6):
        codes.append(c.post("/v1/chat/completions",
                            headers={"X-SupremeAI-Key": "test-master-key-123"},
                            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]}).status_code)
    check("6 keyed requests all processed, zero 429", all(s == 502 for s in codes), f"got {codes}")

    r = c.post("/v1/chat/completions", json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]})
    check("unauthenticated request still fails closed (401)", r.status_code == 401, f"got {r.status_code}")


def test_per_ip_isolation():
    print("[D1] buckets are per client IP (last XFF hop), memory-bounded")
    c = reload_app(STEALTH_WEBHOOK_URL="http://127.0.0.1:9/unreachable", GUEST_RATE_LIMIT_PER_MIN="2")

    a = [guest_post(c, ip="spoof, 10.0.0.1").status_code for _ in range(3)]
    b = [guest_post(c, ip="spoof, 10.0.0.2").status_code for _ in range(3)]
    check("IP A: first 2 pass, 3rd throttled", a == [502, 502, 429], f"got {a}")
    check("IP B independent bucket", b == [502, 502, 429], f"got {b}")

    c2 = reload_app(STEALTH_WEBHOOK_URL="http://127.0.0.1:9/unreachable", GUEST_RATE_LIMIT_PER_MIN="1")
    for i in range(50):
        guest_post(c2, ip=f"10.1.{i}.7")
    if hasattr(app_module, "_guest_hits"):
        check("bucket count stays bounded under IP flood",
              len(app_module._guest_hits) <= app_module._GUEST_BUCKET_CAP,
              f"buckets={len(app_module._guest_hits)}")
    else:
        check("bucket count stays bounded under IP flood", False, "no guest limiter present (pre-fix)")


def test_readiness_probe():
    print("[D3] /readyz capability probe distinct from /health liveness")
    c = reload_app(STEALTH_WEBHOOK_URL="http://127.0.0.1:9/unreachable")
    r = c.get("/readyz")
    check("/readyz 200 when relay configured", r.status_code == 200 and r.json().get("chat_ready") is True)

    h = c.get("/health")
    check("/health stays 200 liveness", h.status_code == 200)
    check("/health exposes chat_ready field", h.json().get("chat_ready") is True)

    c2 = reload_app(STEALTH_WEBHOOK_URL="")
    r2 = c2.get("/readyz")
    check("/readyz 503 when no reply path configured",
          r2.status_code == 503 and r2.json().get("chat_ready") is False, f"got {r2.status_code}")
    h2 = c2.get("/health")
    check("/health STILL 200 (liveness never flaps)", h2.status_code == 200)
    check("/health chat_ready false when unconfigured", h2.json().get("chat_ready") is False)


def test_native_session_honesty():
    if ws_module is None:
        print("SKIP: web_session module not present in this layout")
        return
    print("[D2] native web-session path fails closed — no fabricated replies")
    os.environ["GEMINI_SESSION_COOKIE"] = "test-cookie=1"
    try:
        importlib.reload(ws_module)
        bridge = ws_module.web_bridge
        check("test account registered", len(bridge.accounts) == 1)

        acc = bridge.accounts[0]
        status, body = asyncio.run(
            bridge.forward_web_chat({"model": "auto", "messages": [{"role": "user", "content": "hi"}]})
        )
        check("native path returns honest 503", status == 503, f"got {status} {body}")
        check("no fabricated content marker",
              "Web Session Active" not in json.dumps(body), f"{body}")
        check("account health NOT credited for non-executed request",
              acc.total_requests == 0 and acc.health_score == 100,
              f"requests={acc.total_requests} health={acc.health_score}")

        wrapped = bridge._wrap_openai_format("ok", "gemini")
        check("_wrap_openai_format has exactly one id key",
              json.dumps(wrapped).count('"id"') == 1, f"{json.dumps(wrapped)[:80]}")
        # json.dumps cannot see duplicate literal keys (last wins) — check source.
        src = open(ws_module.__file__, encoding="utf-8").read()
        check("no duplicate id literal in _wrap_openai_format source",
              src.count('"id": "chatcmpl-web-') == 1,
              f"count={src.count(chr(34) + 'id' + chr(34) + ': ' + chr(34) + 'chatcmpl-web-')}")
    finally:
        os.environ.pop("GEMINI_SESSION_COOKIE", None)


def test_relay_path_preserved():
    if ws_module is None:
        print("SKIP: web_session module not present in this layout")
        return
    print("[P3] relay path untouched: unreachable relay still yields honest error dict")
    os.environ["GEMINI_SESSION_COOKIE"] = "test-cookie=1"
    try:
        importlib.reload(ws_module)
        status, body = asyncio.run(ws_module.web_bridge.forward_web_chat(
            {"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
            webhook_url="http://127.0.0.1:9/unreachable",
        ))
        check("relay error surfaced honestly (4xx/5xx dict)", status >= 400 and isinstance(body, dict) and "error" in body,
              f"got {status} {body}")
    finally:
        os.environ.pop("GEMINI_SESSION_COOKIE", None)


def main() -> int:
    for t in (test_guest_throttle, test_keyed_auth_unthrottled, test_per_ip_isolation,
              test_readiness_probe, test_native_session_honesty, test_relay_path_preserved):
        t()
    for k in _TEST_ENV_KEYS:
        os.environ.pop(k, None)
    print(f"\n===== {PASS} passed, {len(FAIL)} failed =====")
    if FAIL:
        print("failed:", *FAIL, sep="\n  - ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
