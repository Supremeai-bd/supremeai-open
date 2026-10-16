# SupremeAI Stealth Browser Sandbox (issue #335)

Zero-dependency reference implementation of the Layer 3 Tool Sandbox browser
surface: an engine-agnostic stealth browser runtime exposing the four
contracted MCP tool endpoints (`navigate`, `screenshot`, `scrape_text`,
`evaluate_js`) with fingerprint randomization, proxy rotation, DOM
sanitization, structured markdown responses and fail-closed error handling.

## Layout

| File | Role |
|---|---|
| `browser_runtime.py` | Error taxonomy, stealth profiles, proxy pool, navigation policy (SSRF wall), DOM sanitizer, engine port, `MockEngine`, `PlaywrightEngine` (lazy), `BrowserRuntime`, MCP tool catalog + `invoke_tool` dispatcher |
| `mcp_server.py` | Minimal streamable-HTTP MCP endpoint (stdlib `http.server`): `initialize` mints `Mcp-Session-Id`, `tools/list`, `tools/call`, `ping`, `DELETE` terminate, `404` `-32001` for stale sessions, `413` body cap |
| `../tests/test_browser_sandbox.py` | Offline pytest battery (mock engine + real loopback sockets) |

## Verification contract (issue #335)

```bash
python -c 'import sandbox.browser_runtime'   # boot smoke
pytest tests/test_browser_sandbox.py -v      # full offline battery
```

## Acceptance criteria mapping

1. **Headless runner with stealth profiles** — `PlaywrightEngine` is a real
   adapter: lazy playwright import (a missing install is a structured
   `ENGINE_UNAVAILABLE` envelope, never a stack trace), launch arguments and
   context options driven by `StealthProfile` (UA, viewport, locale +
   timezone drawn *together* so the fingerprint stays internally consistent,
   color scheme, device scale, per-context init script suppressing the
   webdriver flag and adding canvas noise).
2. **MCP tool wrappers with structured markdown and screenshots** —
   `TOOL_CATALOG` provides closed input schemas (`additionalProperties:
   false`) for all four tools; `invoke_tool` returns MCP `tools/call`
   envelopes: `text` blocks with deterministic structured markdown and
   `image` blocks (base64 PNG) for screenshots. `mcp_server.py` wires the
   same catalog onto a streamable-HTTP transport with Tower-compatible
   session semantics.
3. **Fail-closed error handling** — navigation policy denies non-HTTP
   schemes, embedded userinfo, all private/loopback/link-local ranges
   (IPv4 + IPv6), cloud metadata hostnames, and every encoded-host evasion
   trick (decimal `http://2130706433`, hex `http://0x7f000001`, octal
   `http://0177.0.0.1`, short forms `http://127.1`); unparseable hosts are
   blocked, never passed. Engine crashes, target blocks, timeouts, proxy
   pool exhaustion and politeness windows all surface as honest
   `isError` envelopes with stable codes and truthful `retryable` flags.

## Honest limitations

- The sanitizer is a reference-grade extractor on stdlib `html.parser`
  (removes script/style/iframe/embed content, decodes entities, normalizes
  whitespace); it is not a full browser DOM engine.
- Stealth arguments reduce obvious automation markers; no reference
  implementation can guarantee un-detectability. Heavier engine-specific
  spoofing belongs to the private runtime.
- The navigation policy checks URL *text*; resolution-time DNS pinning
  (rebinding defense) is enforced by the private deployment layer, and the
  policy therefore blocks all private-range addresses by default.
- Proxy credentials are never stored in `ProxyConfig` — operators inject
  them via the playwright adapter at call time, and every rendering path
  uses credential-free `scheme://host:port` labels only.

## Dependency posture

Standard library only. Playwright is an *optional runtime* behind a lazy
import: the module, the catalog and the whole test battery run on machines
without it, and the real engine is a thin, honest adapter for environments
that provide the browser binary operator-side.
