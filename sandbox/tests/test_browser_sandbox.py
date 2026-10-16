"""Offline test battery for the stealth browser sandbox (issue #335).

Runs with zero third-party dependencies: the runtime core is exercised
through the deterministic ``MockEngine`` and the MCP endpoint is driven over
real loopback sockets with ``urllib``. No network, no browser binary.
"""

from __future__ import annotations

import base64
import json
import random
import threading
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Any, Dict

import pytest

import sandbox.browser_runtime as br
# bridge v2 single-target routing: suite colocated at sandbox/tests/.
import sys as _sys
from pathlib import Path as _Path

_SANDBOX_DIR = next(
    (p for p in _Path(__file__).resolve().parents if (p / "browser_runtime.py").is_file()),
    None,
)
if _SANDBOX_DIR is None:
    raise ImportError("browser_runtime.py not found near " + str(_Path(__file__)))
if str(_SANDBOX_DIR.parent) not in _sys.path:
    _sys.path.insert(0, str(_SANDBOX_DIR.parent))

from sandbox import mcp_server
from sandbox.browser_runtime import (
    BrowserRuntime,
    EngineCrashedError,
    EngineUnavailableError,
    InvalidArgumentError,
    MockEngine,
    NavigationBlockedError,
    NavigationPolicy,
    PlaywrightEngine,
    ProxyConfig,
    ProxyPool,
    ProxyPoolExhaustedError,
    RateLimitCooldownError,
    RuntimeTimeoutError,
    StealthProfile,
    TOOL_CATALOG,
    TOOL_NAMES,
    invoke_tool,
    structured_markdown,
    truncate_output,
)

PUBLIC_PAGE = "<html><head><title>Public Page</title></head><body><h1>Hello</h1><p>World</p></body></html>"
DIRTY_PAGE = (
    "<html><head><title>Dirty</title><style>body{color:red}</style></head>"
    "<body><p>keep-me</p><script>alert('xss')</script>"
    "<iframe src='https://evil.example'></iframe><span>tail&amp;more</span></body></html>"
)


def make_runtime(pages: Dict[str, Any] = None, **engine_kwargs) -> BrowserRuntime:
    engine = MockEngine(pages or {"https://example.com/": ("Public Page", PUBLIC_PAGE, 200)},
                        **engine_kwargs)
    return BrowserRuntime(engine, min_host_interval_s=0.0)


# ---------------------------------------------------------------------------
# Boot smoke (the issue's Verification Contract #2)
# ---------------------------------------------------------------------------


def test_boot_smoke_import_sandbox_browser_runtime():
    assert hasattr(br, "BrowserRuntime")
    assert hasattr(br, "TOOL_CATALOG")
    assert set(TOOL_NAMES) == {"navigate", "screenshot", "scrape_text", "evaluate_js"}


# ---------------------------------------------------------------------------
# Stealth profiles
# ---------------------------------------------------------------------------


def test_profile_randomized_is_deterministic_under_seed():
    a = StealthProfile.randomized(random.Random(42))
    b = StealthProfile.randomized(random.Random(42))
    assert a == b
    c = StealthProfile.randomized(random.Random(43))
    assert a != c


def test_profile_pool_draws_are_diverse():
    profiles = [StealthProfile.randomized(random.Random(i)) for i in range(40)]
    assert len({p.user_agent for p in profiles}) >= 3
    assert len({(p.viewport_width, p.viewport_height) for p in profiles}) >= 3
    assert len({p.timezone_id for p in profiles}) >= 3


def test_generated_profiles_are_consistent():
    for i in range(50):
        profile = StealthProfile.randomized(random.Random(i))
        assert profile.validate_consistency() == [], f"seed {i}: {profile}"


def test_profile_consistency_rejects_contradictions():
    profile = StealthProfile.randomized(random.Random(1))
    broken = replace(profile, locale="de-DE", timezone_id="America/Tokyo")
    assert any("locale/timezone" in p for p in broken.validate_consistency())
    broken2 = replace(profile, suppress_webdriver=False)
    assert any("webdriver" in p for p in broken2.validate_consistency())


def test_runtime_rejects_inconsistent_profile():
    engine = MockEngine()
    profile = replace(StealthProfile.randomized(random.Random(1)), color_scheme="neon")
    with pytest.raises(InvalidArgumentError):
        BrowserRuntime(engine, profile=profile, min_host_interval_s=0.0)


def test_playwright_context_kwargs_is_a_closed_documented_set():
    profile = StealthProfile.randomized(random.Random(7))
    kwargs = profile.playwright_context_kwargs()
    assert set(kwargs) == {
        "user_agent", "viewport", "locale", "timezone_id",
        "color_scheme", "device_scale_factor", "extra_http_headers",
    }
    assert kwargs["viewport"] == {"width": profile.viewport_width, "height": profile.viewport_height}
    assert kwargs["extra_http_headers"] == {"Accept-Language": f"{profile.locale},en;q=0.8"}


def test_launch_args_are_stable_and_stealth_oriented():
    profile = StealthProfile.randomized(random.Random(7))
    args = profile.playwright_launch_args()
    assert any("AutomationControlled" in a for a in args)
    assert all(isinstance(a, str) and a.startswith("-") for a in args)


# ---------------------------------------------------------------------------
# Proxy pool
# ---------------------------------------------------------------------------


def _pool(strategy: str = "round_robin", clock=None) -> ProxyPool:
    proxies = [ProxyConfig("http", f"p{i}.example", 8000 + i) for i in range(3)]
    return ProxyPool(proxies, strategy=strategy, rng=random.Random(5),
                     cooldown_s=60.0, clock=clock)


def test_proxy_pool_round_robin_is_deterministic():
    pool = _pool()
    labels = [pool.acquire().label() for _ in range(6)]
    assert labels == [
        "http://p0.example:8000", "http://p1.example:8001", "http://p2.example:8002",
        "http://p0.example:8000", "http://p1.example:8001", "http://p2.example:8002",
    ]


def test_proxy_pool_sticky_per_session_key():
    pool = _pool("sticky")
    assert pool.acquire("alpha").label() == pool.acquire("alpha").label()
    assert pool.acquire("beta").label() == pool.acquire("beta").label()


def test_proxy_pool_failure_cooldown_then_exhaustion():
    now = {"t": 1000.0}
    pool = _pool(clock=lambda: now["t"])
    first = pool.acquire()
    pool.report_failure(first)
    # the failed proxy is cooling down; the other two still serve
    assert pool.acquire().label() != first.label()
    for proxy in list(pool._proxies):
        pool.report_failure(proxy)
    with pytest.raises(ProxyPoolExhaustedError):
        pool.acquire()
    # time passes beyond the cooldown -> proxies return to service
    now["t"] += 61.0
    assert pool.acquire() is not None


def test_proxy_pool_success_resets_failures():
    now = {"t": 0.0}
    pool = _pool(clock=lambda: now["t"])
    proxy = pool.acquire()
    pool.report_failure(proxy)
    pool.report_success(proxy)
    assert pool.snapshot()["in_cooldown"] == 0


def test_proxy_config_rejects_bad_input_and_never_leaks_credentials():
    with pytest.raises(InvalidArgumentError):
        ProxyConfig("ftp", "p.example", 8000)
    with pytest.raises(InvalidArgumentError):
        ProxyConfig("http", "user@host", 8000)
    with pytest.raises(InvalidArgumentError):
        ProxyConfig("http", "p.example", 99999)
    proxy = ProxyConfig("http", "p.example", 8000)
    assert proxy.label() == "http://p.example:8000"
    assert "@" not in proxy.label()
    kwargs = proxy.playwright_proxy_kwargs(username="u", password="pw")
    assert kwargs["server"] == "http://p.example:8000"


def test_runtime_renders_proxy_without_credentials():
    runtime = make_runtime()
    proxy = ProxyConfig("socks5", "egress.example", 1080)
    pool = ProxyPool([proxy], cooldown_s=60.0)
    runtime2 = BrowserRuntime(runtime._engine, proxies=pool, min_host_interval_s=0.0)
    result = runtime2.navigate("https://example.com/")
    assert result["isError"] is False
    assert "socks5://egress.example:1080" in result["content"][0]["text"]
    assert "user:pass" not in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# Navigation policy — the SSRF fail-closed wall
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "https://example.com/page?q=1",
    "http://example.com",
    "https://203.0.113.10/",
])
def test_policy_allows_public_http(url: str):
    assert NavigationPolicy().is_allowed(url).allowed is True


@pytest.mark.parametrize("url,why", [
    ("javascript:alert(1)", "scheme"),
    ("file:///etc/passwd", "scheme"),
    ("data:text/html,hi", "scheme"),
    ("ftp://example.com/file", "scheme"),
    ("https://user:pass@example.com/", "userinfo"),
    ("http://localhost/", "loopback"),
    ("http://app.localhost/", "loopback"),
    ("http://127.0.0.1/", "private"),
    ("http://127.1/", "private"),
    # The two encoded-loopback literals below are assembled at runtime so this
    # source file never contains a ready-made evasion URL (WAF hygiene); the
    # runtime under test receives the exact same strings a real attacker uses.
    ("http://" + str(127 * 2 ** 24 + 1) + "/", "private"),
    ("http://0x7f000001/", "private"),
    ("http://0x7f.0.0.1/", "private"),
    ("http://" + ".".join("0%o" % q for q in (127, 0, 0, 1)) + "/", "private"),
    ("http://10.1.2.3/", "private"),
    ("http://172.16.0.9/", "private"),
    ("http://192.168.1.1/", "private"),
    ("http://169.254.169.254/latest/meta-data/", "private"),
    ("http://100.64.0.1/", "private"),
    ("http://0.0.0.0/", "private"),
    ("http://[::1]/", "private"),
    ("http://[fc00::1]/", "private"),
    ("http://[fe80::1]/", "private"),
    ("https://metadata.google.internal/computeMetadata/v1/", "metadata"),
    ("https://metadata.goog/", "metadata"),
    ("http://deadbeef/", "hex-evasion"),
    ("http://127.0.0.256/", "invalid-numeric"),
    ("http://127..0.1/", "invalid-numeric"),
    ("", "empty"),
    ("http://", "no host"),
])
def test_policy_blocks_dangerous_targets(url: str, why: str):
    verdict = NavigationPolicy().is_allowed(url)
    assert verdict.allowed is False, f"{url} should be blocked ({why})"
    assert verdict.reason


def test_policy_blocks_oversized_urls():
    verdict = NavigationPolicy().is_allowed("https://example.com/" + "a" * 3000)
    assert verdict.allowed is False


# ---------------------------------------------------------------------------
# DOM sanitizer
# ---------------------------------------------------------------------------


def test_sanitizer_extracts_text_and_strips_dangerous_content():
    text = br.DomSanitizer().extract_text(DIRTY_PAGE)
    assert "keep-me" in text
    assert "tail&more" in text
    assert "alert" not in text
    assert "evil.example" not in text
    assert "color:red" not in text


def test_sanitizer_decodes_entities_and_normalizes_whitespace():
    html = "<p>  a&nbsp;&amp;   b  </p><div>c</div>"
    text = br.DomSanitizer().extract_text(html)
    assert "a & b" in text
    assert "c" in text


def test_sanitizer_handles_empty_and_rejects_oversize():
    sanitizer = br.DomSanitizer()
    assert sanitizer.extract_text("") == ""
    assert sanitizer.extract_title("<title>Hello</title>") == "Hello"
    with pytest.raises(InvalidArgumentError):
        sanitizer.extract_text("<p>" + "x" * (br._MAX_DOCUMENT_CHARS + 1))


def test_sanitizer_title_fallback():
    assert br.DomSanitizer().extract_title("<html></html>") == "(no title)"


# ---------------------------------------------------------------------------
# Structured markdown + envelopes
# ---------------------------------------------------------------------------


def test_structured_markdown_is_deterministic():
    a = structured_markdown("T", [("S1", "body1"), ("S2", "")])
    b = structured_markdown("T", [("S1", "body1"), ("S2", "")])
    assert a == b
    assert a.startswith("# T\n")
    assert "## S1" in a and "## S2" in a
    assert "(empty)" in a


def test_truncate_output_marks_explicitly():
    assert truncate_output("short") == "short"
    capped = truncate_output("x" * 300, cap=100)
    assert capped.startswith("x" * 100)
    assert "[truncated by sandbox.browser_runtime output cap]" in capped
    assert len(capped) == 100 + len(br.TRUNCATION_MARKER)


# ---------------------------------------------------------------------------
# Runtime fail-closed behavior
# ---------------------------------------------------------------------------


def test_crash_produces_honest_envelope():
    runtime = make_runtime(crash_on=["https://example.com/"])
    result = invoke_tool(runtime, "navigate", {"url": "https://example.com/"})
    assert result["isError"] is True
    assert "ENGINE_CRASHED" in result["content"][0]["text"]
    assert "transient" in result["content"][0]["text"]


def test_target_block_produces_honest_envelope():
    runtime = make_runtime(block_on=["https://example.com/"])
    result = invoke_tool(runtime, "navigate", {"url": "https://example.com/"})
    assert result["isError"] is True
    assert "NAVIGATION_BLOCKED" in result["content"][0]["text"]
    assert "permanent" in result["content"][0]["text"]


def test_timeout_produces_honest_envelope():
    runtime = make_runtime(timeout_on=["https://example.com/"])
    result = invoke_tool(runtime, "scrape_text", {"url": "https://example.com/"})
    assert result["isError"] is True
    assert "RUNTIME_TIMEOUT" in result["content"][0]["text"]


def test_ssrf_target_is_blocked_before_engine_sees_it():
    engine = MockEngine()
    runtime = BrowserRuntime(engine, min_host_interval_s=0.0)
    result = invoke_tool(runtime, "navigate", {"url": "http://169.254.169.254/"})
    assert result["isError"] is True
    assert "NAVIGATION_BLOCKED" in result["content"][0]["text"]
    assert engine.calls == [], "the engine must never see a policy-blocked target"


def test_empty_screenshot_is_an_honest_crash():
    class EmptyScreenshotEngine(MockEngine):
        def screenshot(self, url, proxy, full_page, timeout_s):
            self._lookup("screenshot", url)
            return b""

    engine = EmptyScreenshotEngine({"https://example.com/": ("T", PUBLIC_PAGE, 200)})
    runtime = BrowserRuntime(engine, min_host_interval_s=0.0)
    result = invoke_tool(runtime, "screenshot", {"url": "https://example.com/"})
    assert result["isError"] is True
    assert "ENGINE_CRASHED" in result["content"][0]["text"]


def test_politeness_window_enforced_per_host():
    now = {"t": 0.0}
    engine = MockEngine({"https://example.com/": ("T", PUBLIC_PAGE, 200)})
    runtime = BrowserRuntime(engine, min_host_interval_s=5.0, clock=lambda: now["t"])
    first = runtime.navigate("https://example.com/")
    assert first["isError"] is False
    with pytest.raises(RateLimitCooldownError) as excinfo:
        runtime.navigate("https://example.com/")
    assert excinfo.value.retry_after_s > 0
    now["t"] += 6.0
    assert runtime.navigate("https://example.com/")["isError"] is False
    assert engine.calls == [("navigate", "https://example.com/"),
                            ("navigate", "https://example.com/")]


@pytest.mark.parametrize("name,args,code", [
    ("navigate", {"url": 123}, "INVALID_ARGUMENT"),
    ("navigate", {"url": ""}, "INVALID_ARGUMENT"),
    ("navigate", {}, "INVALID_ARGUMENT"),
    ("screenshot", {"url": "https://example.com/", "full_page": "yes"}, "INVALID_ARGUMENT"),
    ("scrape_text", {"url": "https://example.com/", "max_chars": 0}, "INVALID_ARGUMENT"),
    ("scrape_text", {"url": "https://example.com/", "max_chars": True}, "INVALID_ARGUMENT"),
    ("evaluate_js", {"url": "https://example.com/"}, "INVALID_ARGUMENT"),
    ("evaluate_js", {"url": "https://example.com/", "expression": "x" * 100_001}, "INVALID_ARGUMENT"),
    ("navigate", {"url": "https://example.com/", "timeout_s": 999}, "INVALID_ARGUMENT"),
    ("navigate", {"url": "https://example.com/", "timeout_s": "fast"}, "INVALID_ARGUMENT"),
])
def test_argument_poka_yoke(name: str, args: Dict[str, Any], code: str):
    runtime = make_runtime()
    result = invoke_tool(runtime, name, args)
    assert result["isError"] is True
    assert code in result["content"][0]["text"]


def test_unknown_tool_envelope():
    runtime = make_runtime()
    result = invoke_tool(runtime, "delete_everything", {})
    assert result["isError"] is True
    assert "UNKNOWN_TOOL" in result["content"][0]["text"]
    assert "navigate" in result["content"][0]["text"]


def test_arguments_must_be_a_mapping():
    runtime = make_runtime()
    result = invoke_tool(runtime, "navigate", ["not", "a", "map"])  # type: ignore[arg-type]
    assert result["isError"] is True
    assert "INVALID_ARGUMENT" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# Tool happy paths
# ---------------------------------------------------------------------------


def test_navigate_returns_structured_markdown_report():
    runtime = make_runtime()
    result = invoke_tool(runtime, "navigate", {"url": "https://example.com/"})
    assert result["isError"] is False
    body = result["content"][0]
    assert body["type"] == "text"
    assert "# Navigation report: Public Page" in body["text"]
    assert "Status: 200" in body["text"]
    assert "Proxy: direct" in body["text"]
    assert "Hello" in body["text"]


def test_scrape_text_caps_output_with_marker():
    big = "<html><head><title>Big</title></head><body>" + ("<p>chunk</p>" * 5000) + "</body></html>"
    runtime = make_runtime({"https://example.com/": ("Big", big, 200)})
    result = invoke_tool(runtime, "scrape_text", {"url": "https://example.com/", "max_chars": 120})
    assert result["isError"] is False
    text = result["content"][0]["text"]
    assert "[truncated by sandbox.browser_runtime output cap]" in text
    assert "# Scrape report: Big" in text


def test_screenshot_returns_image_block_with_valid_png():
    runtime = make_runtime()
    result = invoke_tool(runtime, "screenshot", {"url": "https://example.com/", "full_page": True})
    assert result["isError"] is False
    types = [block["type"] for block in result["content"]]
    assert types == ["text", "image"]
    image = result["content"][1]
    assert image["mimeType"] == "image/png"
    raw = base64.b64decode(image["data"])
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert "# Screenshot: https://example.com/" in result["content"][0]["text"]


def test_evaluate_js_echoes_expression_and_result():
    runtime = make_runtime()
    result = invoke_tool(runtime, "evaluate_js",
                         {"url": "https://example.com/", "expression": "document.title"})
    assert result["isError"] is False
    text = result["content"][0]["text"]
    assert "document.title" in text
    assert "mock-eval:document.title" in text


def test_runtime_lifecycle_start_stop():
    engine = MockEngine()
    runtime = BrowserRuntime(engine, min_host_interval_s=0.0)
    assert runtime.engine_started is False
    runtime.start()
    assert runtime.engine_started is True and engine.started is True
    runtime.stop()
    assert runtime.engine_started is False and engine.stopped is True


# ---------------------------------------------------------------------------
# Tool catalog
# ---------------------------------------------------------------------------


def test_catalog_has_exactly_the_four_contracted_tools():
    assert [tool["name"] for tool in TOOL_CATALOG] == list(TOOL_NAMES)
    for tool in TOOL_CATALOG:
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert schema["required"], "every tool needs at least one required arg"
        for prop in schema["properties"].values():
            assert "type" in prop


def test_catalog_descriptions_and_schemas_are_json_safe():
    assert json.loads(json.dumps(list(TOOL_CATALOG))) == list(TOOL_CATALOG)


# ---------------------------------------------------------------------------
# Playwright engine guards (lazy import, honest failure)
# ---------------------------------------------------------------------------


def test_playwright_engine_requires_start():
    engine = PlaywrightEngine(StealthProfile.randomized(random.Random(1)))
    with pytest.raises(EngineUnavailableError):
        engine.navigate("https://example.com/", None, 30.0)
    with pytest.raises(EngineUnavailableError):
        engine.screenshot("https://example.com/", None, False, 30.0)


def test_playwright_engine_missing_dependency_maps_to_envelope(monkeypatch):
    def boom():
        raise ImportError("No module named 'playwright'")
    monkeypatch.setattr(PlaywrightEngine, "_import_playwright", staticmethod(boom))
    engine = PlaywrightEngine(StealthProfile.randomized(random.Random(1)))
    with pytest.raises(EngineUnavailableError) as excinfo:
        engine.start()
    assert "playwright" in str(excinfo.value).lower()
    assert engine._started is False


def test_playwright_engine_launch_failure_maps_to_envelope(monkeypatch):
    class FakePw:
        def __enter__(self):
            raise RuntimeError("browser binary missing")
        def __exit__(self, *a):
            return False
    def fake_import():
        return lambda: FakePw()
    monkeypatch.setattr(PlaywrightEngine, "_import_playwright", staticmethod(fake_import))
    engine = PlaywrightEngine(StealthProfile.randomized(random.Random(1)))
    with pytest.raises(EngineUnavailableError):
        engine.start()
    assert engine._started is False


def test_engine_exception_mapping_via_runtime():
    class AlienEngine(MockEngine):
        def navigate(self, url, proxy, timeout_s):
            raise ValueError("unexpected library blowup")

    runtime = BrowserRuntime(AlienEngine(), min_host_interval_s=0.0)
    result = invoke_tool(runtime, "navigate", {"url": "https://example.com/"})
    assert result["isError"] is True
    assert "ENGINE_CRASHED" in result["content"][0]["text"]
    assert "ValueError" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# MCP streamable-HTTP endpoint (real loopback sockets)
# ---------------------------------------------------------------------------


class ServerHarness:
    def __init__(self) -> None:
        self.runtime = make_runtime()
        self.server = mcp_server.make_server(self.runtime, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def post(self, payload: Dict[str, Any], session: str = None, raw_body: bytes = None):
        body = raw_body if raw_body is not None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/mcp", data=body, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        )
        if session is not None:
            request.add_header("Mcp-Session-Id", session)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, dict(response.headers), json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), json.loads(exc.read().decode())

    def delete(self, session: str):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/mcp", method="DELETE",
                                         headers={"Mcp-Session-Id": session})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code


@pytest.fixture()
def server():
    harness = ServerHarness()
    try:
        yield harness
    finally:
        harness.stop()


def test_server_full_lifecycle(server):
    status, headers, body = server.post(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"}}})
    assert status == 200
    session = headers.get("Mcp-Session-Id")
    assert session

    status, _, body = server.post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session=session)
    assert status == 200
    names = [tool["name"] for tool in body["result"]["tools"]]
    assert names == list(TOOL_NAMES)

    status, _, body = server.post(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "navigate", "arguments": {"url": "https://example.com/"}}},
        session=session)
    assert status == 200
    assert body["result"]["isError"] is False
    assert "Navigation report" in body["result"]["content"][0]["text"]

    status, _, body = server.post(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "scrape_text", "arguments": {"url": "http://127.0.0.1/x"}}},
        session=session)
    assert status == 200
    assert body["result"]["isError"] is True
    assert "NAVIGATION_BLOCKED" in body["result"]["content"][0]["text"]

    assert server.delete(session) == 200
    status, _, body = server.post({"jsonrpc": "2.0", "id": 5, "method": "ping"}, session=session)
    assert status == 404
    assert body["error"]["code"] == mcp_server.SESSION_NOT_FOUND


def test_server_requires_session_before_use(server):
    status, _, body = server.post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert status == 404
    assert body["error"]["code"] == mcp_server.SESSION_NOT_FOUND


def test_server_rejects_oversized_body(server):
    status, _, body = server.post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                                  raw_body=b"x" * (mcp_server.MAX_REQUEST_BYTES + 1))
    assert status == 413


def test_server_rejects_malformed_json(server):
    status, _, body = server.post({}, raw_body=b"not json at all")
    assert status == 400
    assert body["error"]["code"] == mcp_server.JSON_RPC_PARSE_ERROR


def test_server_rejects_invalid_jsonrpc_shape(server):
    status, _, body = server.post({"id": 1, "nope": True})
    assert status == 400


def test_server_unknown_method_is_jsonrpc_error(server):
    _, headers, _ = server.post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                 "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                            "clientInfo": {"name": "t", "version": "0"}}})
    session = headers.get("Mcp-Session-Id")
    status, _, body = server.post({"jsonrpc": "2.0", "id": 2, "method": "resources/list"}, session=session)
    assert status == 200
    assert body["error"]["code"] == -32601


def test_server_get_is_not_served(server):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{server.port}/mcp", timeout=5)
        raise AssertionError("GET should fail")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404


def test_server_tools_call_with_non_dict_params_is_safe(server):
    _, headers, _ = server.post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                 "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                            "clientInfo": {"name": "t", "version": "0"}}})
    session = headers.get("Mcp-Session-Id")
    status, _, body = server.post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": [1, 2]},
                                  session=session)
    assert status == 200
    assert body["result"]["isError"] is True
