"""Stealth anti-detect browser runtime and MCP tool contract (issue #335).

Zero-dependency reference implementation of the Layer 3 Tool Sandbox browser
surface: an engine-agnostic runtime that exposes the four contracted MCP tool
endpoints (``navigate``, ``screenshot``, ``scrape_text``, ``evaluate_js``)
with fingerprint randomization, proxy rotation, DOM sanitization, structured
markdown responses and fail-closed error handling.

Design invariants
-----------------
1. **Fail-closed everywhere.** Navigation policy denies private networks,
   encoded-loopback tricks and non-HTTP schemes by default; any engine crash,
   block or timeout surfaces as an honest, structured error envelope — never
   a partial success and never a silent swallow.
2. **Zero dependencies.** The runtime core is 100% standard library. The
   Playwright-backed engine is a *lazy adapter*: importing this module never
   imports playwright, and a missing/broken playwright install surfaces as a
   structured ``ENGINE_UNAVAILABLE`` envelope with actionable detail instead
   of a stack trace.
3. **Deterministic where it must be.** ``StealthProfile.randomized`` and the
   proxy pool are fully deterministic under an injected seeded
   ``random.Random``, so every behavior in this module is offline-testable.
4. **Honest scope.** The sanitizer is a reference-grade stdlib HTML-to-text
   extractor (stdlib ``html.parser``, not a full browser DOM); stealth
   arguments reduce obvious automation fingerprints but no reference
   implementation can guarantee un-detectability. Both limits are documented
   here and in ``README.md`` — the runtime never claims more than it does.

Contract anchors
----------------
- Governing issue: Supremeai-bd/supremeai-open #335 (repo:browser, P2).
- Tool response shape follows the MCP ``tools/call`` result contract used by
  the Tower (``docs/MCP_CONNECT.md``): JSON-safe ``{"content": [...],
  "isError": bool}`` with ``text`` and ``image`` content blocks.
"""

from __future__ import annotations

import base64
import html as _html
import ipaddress
import json
import random
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Error taxonomy — fail-closed, structured, honest
# ---------------------------------------------------------------------------


class BrowserRuntimeError(Exception):
    """Base class for every structured failure raised by the sandbox.

    Carries a stable machine-readable ``code``, an honest ``retryable`` flag
    and a human-readable ``detail``. Tool wrappers convert any escaped
    instance into an ``isError`` content envelope; nothing ever escapes as a
    bare string.
    """

    code = "BROWSER_RUNTIME_ERROR"
    retryable = False

    def __init__(self, detail: str, *, retryable: Optional[bool] = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if retryable is not None:
            self.retryable = retryable

    def envelope(self) -> Dict[str, Any]:
        return error_envelope(self.code, self.detail, retryable=self.retryable)


class EngineUnavailableError(BrowserRuntimeError):
    """The browser engine cannot be used at all (not installed, not started)."""

    code = "ENGINE_UNAVAILABLE"
    retryable = False


class EngineCrashedError(BrowserRuntimeError):
    """The engine process died or raised an unexpected failure mid-call."""

    code = "ENGINE_CRASHED"
    retryable = True


class NavigationBlockedError(BrowserRuntimeError):
    """The navigation policy refused the target URL (default-deny)."""

    code = "NAVIGATION_BLOCKED"
    retryable = False


class RuntimeTimeoutError(BrowserRuntimeError):
    """A bounded operation exceeded its wall-clock budget."""

    code = "RUNTIME_TIMEOUT"
    retryable = True


class RateLimitCooldownError(BrowserRuntimeError):
    """Per-target politeness window is still open (scrape etiquette)."""

    code = "RATE_LIMIT_COOLDOWN"
    retryable = True

    def __init__(self, detail: str, *, retry_after_s: float) -> None:
        super().__init__(detail)
        self.retry_after_s = max(0.0, float(retry_after_s))


class ProxyPoolExhaustedError(BrowserRuntimeError):
    """Every proxy in the pool is cooling down after failures."""

    code = "PROXY_POOL_EXHAUSTED"
    retryable = True


class InvalidArgumentError(BrowserRuntimeError):
    """Tool arguments failed poka-yoke validation (closed schemas)."""

    code = "INVALID_ARGUMENT"
    retryable = False


# ---------------------------------------------------------------------------
# Structured envelopes + deterministic markdown rendering
# ---------------------------------------------------------------------------

MAX_TEXT_OUT_CHARS = 200_000
TRUNCATION_MARKER = "\n\n[truncated by sandbox.browser_runtime output cap]"


def truncate_output(text: str, cap: int = MAX_TEXT_OUT_CHARS) -> str:
    """Deterministic output cap with an explicit, visible truncation marker."""
    if len(text) <= cap:
        return text
    return text[:cap] + TRUNCATION_MARKER


def text_block(text: str) -> Dict[str, str]:
    return {"type": "text", "text": text}


def image_block(data_b64: str, mime_type: str = "image/png") -> Dict[str, str]:
    return {"type": "image", "data": data_b64, "mimeType": mime_type}


def ok_envelope(content: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    """MCP ``tools/call`` success envelope (JSON-safe, closed key set)."""
    return {"content": list(content), "isError": False}


def error_envelope(code: str, message: str, *, retryable: bool = False) -> Dict[str, Any]:
    """MCP ``tools/call`` failure envelope: honest, structured, actionable."""
    tail = " This failure is transient; retrying may succeed." if retryable else (
        " This failure is permanent for this input; retrying unchanged input will fail again."
    )
    body = f"Error {code}: {message}{tail}"
    return {"content": [text_block(body)], "isError": True}


def structured_markdown(title: str, sections: Sequence[Tuple[str, str]]) -> str:
    """Render deterministic structured markdown.

    ``sections`` is a sequence of ``(heading, body)`` pairs; the body may
    contain pre-fenced blocks which are emitted verbatim. Headings and bodies
    are sanitized of control characters to keep the render stable.
    """
    cleaned_title = re.sub(r"[\r\n\t]+", " ", title).strip() or "(untitled)"
    parts: List[str] = [f"# {cleaned_title}", ""]
    for heading, body in sections:
        clean_heading = re.sub(r"[\r\n\t]+", " ", heading).strip()
        parts.append(f"## {clean_heading}")
        parts.append("")
        body = body.rstrip("\n")
        parts.append(body if body else "(empty)")
        parts.append("")
    return "\n".join(parts).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Stealth profiles — deterministic fingerprint randomization
# ---------------------------------------------------------------------------

_USER_AGENT_POOL: Tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0",
)

_VIEWPORT_POOL: Tuple[Tuple[int, int], ...] = (
    (1920, 1080), (1536, 864), (1440, 900), (1280, 720), (1600, 900),
)

# Locale and timezone are randomized TOGETHER so the fingerprint stays
# internally consistent (a fr-FR locale with a Asia/Tokyo timezone is the kind
# of contradiction detectors look for).
_LOCALE_TZ_POOL: Tuple[Tuple[str, str], ...] = (
    ("en-US", "America/New_York"),
    ("en-US", "America/Chicago"),
    ("en-GB", "Europe/London"),
    ("de-DE", "Europe/Berlin"),
    ("fr-FR", "Europe/Paris"),
    ("en-CA", "America/Toronto"),
)

_COLOR_SCHEMES: Tuple[str, ...] = ("light", "dark")

# Reference-grade stealth launch arguments. These suppress the most obvious
# automation markers; they are passed to the engine as plain code strings and
# are documented in README.md. No flag documentation is embedded in docstrings
# (bridge intake hygiene).
_STEALTH_LAUNCH_ARGS: Tuple[str, ...] = (
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-background-networking",
)

# Reference-grade init script applied to every new browser context. It patches
# the cheapest detection surfaces (webdriver flag, plugin/UA-CH consistency
# hints, a canvas noise salt). It is intentionally short: heavy spoofing is
# engine-specific and belongs to the private runtime, not to this reference.
_STEALTH_INIT_SCRIPT = """\
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  } catch (e) {}
  try {
    const salt = Math.floor(Math.random() * 8) + 1;
    const orig = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function (...a) {
      const ctx = this.getContext('2d');
      if (ctx && this.width > 0 && this.height > 0) {
        ctx.fillStyle = 'rgba(0,0,0,0.00' + salt + ')';
        ctx.fillRect(0, 0, 1, 1);
      }
      return orig.apply(this, a);
    };
  } catch (e) {}
})();
"""


@dataclass(frozen=True, slots=True)
class StealthProfile:
    """An immutable, self-consistent browser fingerprint.

    Every field is validated by :meth:`validate_consistency`; profiles that
    carry contradictory signals are rejected before they can be handed to an
    engine (a contradictory fingerprint is *worse* than a plain one).
    """

    user_agent: str
    viewport_width: int
    viewport_height: int
    locale: str
    timezone_id: str
    color_scheme: str
    device_scale_factor: float
    suppress_webdriver: bool = True
    init_script: str = _STEALTH_INIT_SCRIPT

    # -- construction -------------------------------------------------------

    @classmethod
    def randomized(cls, rng: random.Random) -> "StealthProfile":
        """Deterministic profile draw from a seeded ``random.Random``."""
        locale, tz = rng.choice(_LOCALE_TZ_POOL)
        return cls(
            user_agent=rng.choice(_USER_AGENT_POOL),
            viewport_width=rng.choice(_VIEWPORT_POOL)[0],
            viewport_height=rng.choice(_VIEWPORT_POOL)[1],
            locale=locale,
            timezone_id=tz,
            color_scheme=rng.choice(_COLOR_SCHEMES),
            device_scale_factor=rng.choice((1.0, 2.0)),
        )

    # -- validation ---------------------------------------------------------

    def validate_consistency(self) -> List[str]:
        """Return a list of invariant violations (empty list = consistent)."""
        problems: List[str] = []
        if not self.user_agent or len(self.user_agent) > 300:
            problems.append("user_agent missing or oversized")
        if not (320 <= self.viewport_width <= 7680 and 240 <= self.viewport_height <= 4320):
            problems.append("viewport outside sane bounds")
        if self.device_scale_factor not in (1.0, 2.0, 3.0):
            problems.append("device_scale_factor must be 1, 2 or 3")
        if self.color_scheme not in _COLOR_SCHEMES:
            problems.append("color_scheme must be light or dark")
        if (self.locale, self.timezone_id) not in _LOCALE_TZ_POOL:
            problems.append("locale/timezone pair is not internally consistent")
        if not self.suppress_webdriver:
            problems.append("webdriver suppression must stay enabled (fail-closed)")
        return problems

    # -- engine adapters ----------------------------------------------------

    def playwright_context_kwargs(self) -> Dict[str, Any]:
        """Map the profile onto documented playwright context options.

        Only options that exist in the public playwright API are emitted; the
        mapping is a closed set so a playwright rename fails loudly here
        instead of silently dropping a stealth control.
        """
        return {
            "user_agent": self.user_agent,
            "viewport": {"width": self.viewport_width, "height": self.viewport_height},
            "locale": self.locale,
            "timezone_id": self.timezone_id,
            "color_scheme": self.color_scheme,
            "device_scale_factor": self.device_scale_factor,
            "extra_http_headers": {"Accept-Language": f"{self.locale},en;q=0.8"},
        }

    def playwright_launch_args(self) -> Tuple[str, ...]:
        return _STEALTH_LAUNCH_ARGS


# ---------------------------------------------------------------------------
# Proxy pool — rotation, cooldown, fail-closed exhaustion
# ---------------------------------------------------------------------------

_PROXY_SCHEMES = frozenset({"http", "https", "socks5"})


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    """One egress proxy. Credentials are never stored here by default —
    operators inject them via environment-backed factories, and the runtime
    renders proxies by ``host:port`` only so credentials can never leak into
    tool output."""

    scheme: str
    host: str
    port: int

    def __post_init__(self) -> None:
        if self.scheme not in _PROXY_SCHEMES:
            raise InvalidArgumentError(
                f"proxy scheme must be one of {sorted(_PROXY_SCHEMES)}, got {self.scheme!r}"
            )
        if not self.host or "/" in self.host or "@" in self.host:
            raise InvalidArgumentError("proxy host must be a bare hostname or IP")
        if not (1 <= int(self.port) <= 65535):
            raise InvalidArgumentError(f"proxy port out of range: {self.port}")

    def label(self) -> str:
        """Credential-free rendering used in all tool output and logs."""
        return f"{self.scheme}://{self.host}:{self.port}"

    def playwright_proxy_kwargs(self, username: Optional[str] = None,
                                password: Optional[str] = None) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"server": f"{self.scheme}://{self.host}:{self.port}"}
        if username is not None:
            kwargs["username"] = username
        if password is not None:
            kwargs["password"] = password
        return kwargs


class ProxyPool:
    """Deterministic rotating pool with failure cooldowns.

    Strategies: ``round_robin`` (deterministic order), ``random`` (seeded),
    ``sticky`` (stable per session key). Failures put a proxy into cooldown;
    :meth:`acquire` refuses (``ProxyPoolExhaustedError``) when every proxy is
    cooling down — the caller fails honestly instead of silently going
    direct, which would defeat the purpose of the pool.
    """

    STRATEGIES = ("round_robin", "random", "sticky")
    DEFAULT_COOLDOWN_S = 60.0

    def __init__(
        self,
        proxies: Sequence[ProxyConfig],
        *,
        strategy: str = "round_robin",
        rng: Optional[random.Random] = None,
        cooldown_s: float = DEFAULT_COOLDOWN_S,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if not proxies:
            raise InvalidArgumentError("ProxyPool requires at least one proxy")
        if strategy not in self.STRATEGIES:
            raise InvalidArgumentError(
                f"strategy must be one of {list(self.STRATEGIES)}, got {strategy!r}"
            )
        self._proxies: Tuple[ProxyConfig, ...] = tuple(proxies)
        self._strategy = strategy
        self._rng = rng or random.Random()
        self._cooldown_s = float(cooldown_s)
        self._clock = clock or time.monotonic
        self._cursor = 0
        self._banned_until: Dict[str, float] = {}
        self._failures: Dict[str, int] = {}

    def acquire(self, session_key: str = "default") -> ProxyConfig:
        now = self._clock()
        live = [p for p in self._proxies if self._banned_until.get(p.label(), 0.0) <= now]
        if not live:
            raise ProxyPoolExhaustedError(
                f"all {len(self._proxies)} proxies are in failure cooldown"
            )
        if self._strategy == "round_robin":
            chosen = live[self._cursor % len(live)]
            self._cursor += 1
        elif self._strategy == "sticky":
            idx = sum(ord(c) for c in session_key) % len(live)
            chosen = live[idx]
        else:
            chosen = self._rng.choice(live)
        return chosen

    def report_failure(self, proxy: ProxyConfig) -> None:
        label = proxy.label()
        self._failures[label] = self._failures.get(label, 0) + 1
        backoff = self._cooldown_s * (2 ** min(self._failures[label] - 1, 5))
        self._banned_until[label] = self._clock() + backoff

    def report_success(self, proxy: ProxyConfig) -> None:
        label = proxy.label()
        self._failures.pop(label, None)
        self._banned_until.pop(label, None)

    def snapshot(self) -> Dict[str, Any]:
        now = self._clock()
        return {
            "strategy": self._strategy,
            "size": len(self._proxies),
            "in_cooldown": sum(1 for v in self._banned_until.values() if v > now),
        }


# ---------------------------------------------------------------------------
# Navigation policy — default-deny SSRF guard
# ---------------------------------------------------------------------------

_PRIVATE_V4 = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("198.18.0.0/15"),
]
_PRIVATE_V6 = [
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]
_BLOCKED_HOSTNAMES = frozenset({
    "metadata.google.internal",
    "metadata.goog",
})
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_MAX_URL_CHARS = 2048


@dataclass(frozen=True, slots=True)
class NavigationVerdict:
    allowed: bool
    reason: str


class NavigationPolicy:
    """Fail-closed navigation policy (default deny).

    Blocks, among others:
    - non-HTTP schemes (``javascript:``, ``file:``, ``data:``, ``ftp:``...);
    - URLs carrying embedded userinfo (``user:pass@host``);
    - every private/loopback/link-local range (IPv4 and IPv6);
    - *encoded* loopback tricks: decimal integer hosts (``http://2130706433``),
      hex hosts (``http://0x7f.0.0.1``), octal segments (``http://0177.0.0.1``)
      and zero-padded addresses — all normalized before the private-range
      verdict so the check cannot be bypassed by textual encodings;
    - cloud metadata hostnames.
    """

    def __init__(self, *, allowed_schemes: Sequence[str] = ("http", "https")) -> None:
        self._allowed = frozenset(s.lower() for s in allowed_schemes)

    def is_allowed(self, url: str) -> NavigationVerdict:
        if not isinstance(url, str) or not url.strip():
            return NavigationVerdict(False, "empty URL")
        if len(url) > _MAX_URL_CHARS:
            return NavigationVerdict(False, "URL exceeds maximum length")
        try:
            parts = urlsplit(url)
        except ValueError as exc:
            return NavigationVerdict(False, f"URL parse failure: {exc}")

        scheme = (parts.scheme or "").lower()
        if scheme not in self._allowed:
            return NavigationVerdict(False, f"scheme {scheme!r} is not allowed")
        if parts.username is not None or parts.password is not None:
            return NavigationVerdict(False, "embedded userinfo is not allowed")
        host = parts.hostname
        if not host:
            return NavigationVerdict(False, "missing host")
        if host.endswith(".localhost") or host == "localhost":
            return NavigationVerdict(False, "loopback hostname is not allowed")
        if host.lower() in _BLOCKED_HOSTNAMES:
            return NavigationVerdict(False, "cloud metadata hostname is not allowed")

        normalized = self._normalize_host(host)
        if normalized is None:
            return NavigationVerdict(False, f"unparseable host {host!r}")
        try:
            addr = ipaddress.ip_address(normalized)
        except ValueError:
            return NavigationVerdict(True, "public hostname")
        networks = _PRIVATE_V6 if addr.version == 6 else _PRIVATE_V4
        if any(addr in net for net in networks):
            return NavigationVerdict(False, f"private address {normalized} is not allowed")
        return NavigationVerdict(True, "public IP literal")

    @staticmethod
    def _normalize_host(host: str) -> Optional[str]:
        """Normalize textual IP encodings to a single canonical form.

        Closes the classic evasion tricks: bare decimal integers
        (``http://2130706433``), whole hex integers (``http://0x7f000001``),
        hex/octal segments (``http://0x7f.0.0.1``, ``http://0177.0.0.1``)
        and short dotted forms (``http://127.1``) — every numeric-ish host is
        normalized to its real address before the private-range verdict, and
        normalization failure means BLOCKED (fail-closed), never a pass.
        """
        stripped = host.strip().strip("[]").lower()
        if not stripped:
            return None
        if ":" in stripped:
            return stripped  # IPv6 literal: checked as-is by ip_address
        if stripped.isdigit():
            try:
                return str(ipaddress.ip_address(int(stripped)))
            except ValueError:
                return None
        if stripped.startswith("0x") and "." not in stripped:
            try:
                return str(ipaddress.ip_address(int(stripped, 16)))
            except ValueError:
                return None
        # Numeric-ish dotted forms (digits, optional per-segment 0x/0 octal
        # prefixes): apply inet_aton-style completion. Such hosts are never
        # legitimate DNS names, so unparseable forms are rejected outright.
        numericish = re.fullmatch(r"[0-9.]+|0x[0-9a-f.]+|([0-9]+\.)*0x[0-9a-f]+", stripped)
        if numericish and "." in stripped:
            try:
                nums: List[int] = []
                for part in stripped.split("."):
                    if part.startswith("0x"):
                        nums.append(int(part, 16))
                    elif len(part) > 1 and part.startswith("0"):
                        nums.append(int(part, 8))
                    elif part.isdigit():
                        nums.append(int(part))
                    else:
                        return None
                if len(nums) == 4:
                    if any(n > 255 for n in nums):
                        return None
                    return ".".join(str(n) for n in nums)
                if len(nums) == 3:
                    if nums[0] > 255 or nums[1] > 255 or nums[2] > 0xFFFF:
                        return None
                    value = ((nums[0] << 8) + nums[1]) << 16
                    return str(ipaddress.ip_address(value + nums[2]))
                if len(nums) == 2:
                    if nums[0] > 255 or nums[1] > 0xFFFFFF:
                        return None
                    return str(ipaddress.ip_address((nums[0] << 24) + nums[1]))
                return None
            except (ValueError, ipaddress.AddressValueError):
                return None
        # Any other host composed exclusively of hex/digit characters is more
        # likely an evasion attempt than a real name: reject it too.
        if re.fullmatch(r"[0-9a-fx.]+", stripped):
            return None
        return stripped


# ---------------------------------------------------------------------------
# DOM sanitization — stdlib HTML-to-text extractor
# ---------------------------------------------------------------------------

_SKIP_TAGS = frozenset({"script", "style", "noscript", "iframe", "object", "embed", "svg", "template"})
_NEWLINE_TAGS = frozenset({"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header", "footer"})
_MAX_DOCUMENT_CHARS = 5_000_000


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _NEWLINE_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in _NEWLINE_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data:
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks).replace("\u00a0", " ")
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
        return "\n".join(ln for ln in lines if ln)


class DomSanitizer:
    """Stdlib DOM text extraction and sanitization.

    Honest scope: this is a reference-grade extractor built on
    ``html.parser``. It removes script/style/iframe/embed content and any
    text that only renders from ignored subtrees, decodes entities, and
    normalizes whitespace — it is not a full browser DOM and makes no claim
    to be one.
    """

    def extract_text(self, html: str) -> str:
        if not isinstance(html, str):
            raise InvalidArgumentError("document must be a string")
        if len(html) > _MAX_DOCUMENT_CHARS:
            raise InvalidArgumentError(
                f"document exceeds {_MAX_DOCUMENT_CHARS} characters"
            )
        parser = _TextExtractor()
        try:
            parser.feed(html)
            parser.close()
        except Exception as exc:  # malformed HTML must not crash the runtime
            raise InvalidArgumentError(f"unparseable document: {exc}") from exc
        return parser.text()

    def extract_title(self, html: str) -> str:
        match = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
        if not match:
            return "(no title)"
        return _html.unescape(re.sub(r"\s+", " ", match.group(1))).strip() or "(no title)"


# ---------------------------------------------------------------------------
# Engine port + adapters
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PageLoad:
    """What an engine returns for a successful navigation."""

    url: str
    status: int
    title: str
    html: str


class BrowserEngine:
    """Engine port: the minimal surface a browser backend must provide.

    Implementations must be honest: raise a structured
    :class:`BrowserRuntimeError` subclass for every failure they can detect
    and let unexpected exceptions escape for the runtime to map onto
    ``ENGINE_CRASHED``.
    """

    def start(self) -> None:  # pragma: no cover - port definition
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - port definition
        raise NotImplementedError

    def navigate(self, url: str, proxy: Optional[ProxyConfig], timeout_s: float) -> PageLoad:  # noqa: D102
        raise NotImplementedError

    def screenshot(self, url: str, proxy: Optional[ProxyConfig], full_page: bool, timeout_s: float) -> bytes:  # noqa: D102
        raise NotImplementedError

    def scrape_text(self, url: str, proxy: Optional[ProxyConfig], timeout_s: float) -> PageLoad:  # noqa: D102
        raise NotImplementedError

    def evaluate_js(self, url: str, expression: str, proxy: Optional[ProxyConfig], timeout_s: float) -> str:  # noqa: D102
        raise NotImplementedError


class MockEngine(BrowserEngine):
    """Deterministic offline engine for tests and harnesses.

    Serves canned pages, records every call for audit, and supports failure
    injection (``crash_on``, ``block_on``, ``timeout_on``) so the fail-closed
    paths of the runtime are exercised without any network or browser.
    """

    # 1x1 transparent PNG, public domain shape — used as the deterministic
    # canned screenshot so base64 round-trips are testable offline.
    CANNED_PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )

    def __init__(
        self,
        pages: Optional[Mapping[str, Tuple[str, str, int]]] = None,
        *,
        crash_on: Sequence[str] = (),
        block_on: Sequence[str] = (),
        timeout_on: Sequence[str] = (),
        slow_s: float = 0.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        # url -> (title, html, status)
        self._pages: Dict[str, Tuple[str, str, int]] = dict(pages or {})
        self._crash_on = set(crash_on)
        self._block_on = set(block_on)
        self._timeout_on = set(timeout_on)
        self._slow_s = float(slow_s)
        self._clock = clock or time.monotonic
        self.calls: List[Tuple[str, str]] = []
        self.started = False
        self.stopped = False

    def add_page(self, url: str, title: str, html: str, status: int = 200) -> None:
        self._pages[url] = (title, html, status)

    def _lookup(self, kind: str, url: str) -> Tuple[str, str, int]:
        self.calls.append((kind, url))
        if url in self._crash_on:
            raise EngineCrashedError(f"mock engine crashed while handling {url}")
        if url in self._block_on:
            raise NavigationBlockedError(f"mock target refused the request: {url}")
        if url in self._timeout_on:
            raise RuntimeTimeoutError(f"mock target exceeded the time budget: {url}")
        if self._slow_s:
            deadline = self._clock() + self._slow_s
            while self._clock() < deadline:  # pragma: no cover - trivial spin
                time.sleep(min(0.001, max(0.0, deadline - self._clock())))
        if url not in self._pages:
            raise NavigationBlockedError(f"no canned page for {url}")
        return self._pages[url]

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def navigate(self, url: str, proxy: Optional[ProxyConfig], timeout_s: float) -> PageLoad:
        title, html, status = self._lookup("navigate", url)
        return PageLoad(url=url, status=status, title=title, html=html)

    def screenshot(self, url: str, proxy: Optional[ProxyConfig], full_page: bool, timeout_s: float) -> bytes:
        self._lookup("screenshot", url)
        return base64.b64decode(self.CANNED_PNG_B64)

    def scrape_text(self, url: str, proxy: Optional[ProxyConfig], timeout_s: float) -> PageLoad:
        title, html, status = self._lookup("scrape_text", url)
        return PageLoad(url=url, status=status, title=title, html=html)

    def evaluate_js(self, url: str, expression: str, proxy: Optional[ProxyConfig], timeout_s: float) -> str:
        self._lookup("evaluate_js", url)
        return f"mock-eval:{expression}"


class PlaywrightEngine(BrowserEngine):
    """Real headless engine adapter (lazy playwright import).

    The import happens inside :meth:`start` — never at module load — so the
    whole sandbox remains importable and testable on machines without
    playwright. A missing or broken install raises a structured
    ``ENGINE_UNAVAILABLE`` error with actionable detail.
    """

    DEFAULT_TIMEOUT_S = 30.0
    MAX_TIMEOUT_S = 120.0

    def __init__(self, profile: StealthProfile) -> None:
        self._profile = profile
        self._pw: Any = None
        self._browser: Any = None
        self._started = False

    # -- lifecycle ----------------------------------------------------------

    @staticmethod
    def _import_playwright() -> Any:
        """Indirection point for the playwright import (test seam)."""
        from playwright.sync_api import sync_playwright  # noqa: WPS433 (runtime dep)

        return sync_playwright

    def start(self) -> None:
        if self._started:
            return
        try:
            factory = self._import_playwright()
        except ImportError as exc:
            raise EngineUnavailableError(
                "playwright is not installed in this environment; install it "
                "with the package manager and fetch a browser binary before "
                f"using the real engine (underlying import error: {exc})"
            ) from exc
        try:
            self._pw = factory()
            self._playwright_cm = self._pw.__enter__()
            self._browser = self._playwright_cm.chromium.launch(
                headless=True,
                args=list(self._profile.playwright_launch_args()),
            )
        except Exception as exc:
            self._started = False
            raise EngineUnavailableError(
                f"playwright engine failed to launch (missing browser binary or "
                f"host problem): {exc}"
            ) from exc
        self._started = True

    def stop(self) -> None:
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if getattr(self, "_playwright_cm", None) is not None:
            try:
                self._playwright_cm.__exit__(None, None, None)
            except Exception:
                pass
            self._playwright_cm = None
        self._started = False

    def _require_started(self) -> None:
        if not self._started:
            raise EngineUnavailableError("engine not started; call start() first")

    # -- context per call ---------------------------------------------------

    def _new_context(self, proxy: Optional[ProxyConfig], timeout_s: float) -> Any:
        kwargs = self._profile.playwright_context_kwargs()
        kwargs["proxy"] = proxy.playwright_proxy_kwargs() if proxy else None
        if kwargs["proxy"] is None:
            kwargs.pop("proxy")
        context = self._browser.new_context(**kwargs)
        try:
            context.add_init_script(self._profile.init_script)
        except Exception:
            pass
        return context

    def _run(self, coro_fn: Callable[[Any], Any], proxy: Optional[ProxyConfig],
             timeout_s: float) -> Any:
        self._require_started()
        clamped = min(max(float(timeout_s), 1.0), self.MAX_TIMEOUT_S)
        context = self._new_context(proxy, clamped)
        try:
            return coro_fn(context)
        finally:
            try:
                context.close()
            except Exception:
                pass

    # -- tools --------------------------------------------------------------

    def navigate(self, url: str, proxy: Optional[ProxyConfig], timeout_s: float) -> PageLoad:
        def run(context: Any) -> PageLoad:
            page = context.new_page()
            response = page.goto(url, timeout=int(timeout_s * 1000), wait_until="domcontentloaded")
            status = int(response.status) if response is not None else 0
            return PageLoad(url=page.url, status=status, title=page.title(), html=page.content())

        return self._run(run, proxy, timeout_s)

    def screenshot(self, url: str, proxy: Optional[ProxyConfig], full_page: bool, timeout_s: float) -> bytes:
        def run(context: Any) -> bytes:
            page = context.new_page()
            page.goto(url, timeout=int(timeout_s * 1000), wait_until="domcontentloaded")
            return page.screenshot(full_page=full_page)

        return self._run(run, proxy, timeout_s)

    def scrape_text(self, url: str, proxy: Optional[ProxyConfig], timeout_s: float) -> PageLoad:
        return self.navigate(url, proxy, timeout_s)

    def evaluate_js(self, url: str, expression: str, proxy: Optional[ProxyConfig], timeout_s: float) -> str:
        def run(context: Any) -> str:
            page = context.new_page()
            page.goto(url, timeout=int(timeout_s * 1000), wait_until="domcontentloaded")
            result = page.evaluate(expression)
            return result if isinstance(result, str) else json.dumps(result)

        return self._run(run, proxy, timeout_s)


# ---------------------------------------------------------------------------
# The runtime — orchestration, politeness, envelopes
# ---------------------------------------------------------------------------

_ARG_CAPS = {
    "url": 2048,
    "expression": 100_000,
    "max_chars": 200_000,
}


def _check_str(value: Any, name: str, cap: int) -> str:
    if not isinstance(value, str):
        raise InvalidArgumentError(f"argument {name!r} must be a string")
    if not value.strip():
        raise InvalidArgumentError(f"argument {name!r} must be non-empty")
    if len(value) > cap:
        raise InvalidArgumentError(f"argument {name!r} exceeds {cap} characters")
    return value


class BrowserRuntime:
    """Orchestrates engine + policy + proxies + sanitizer into MCP tools.

    Every tool operation follows the same fail-closed pipeline:

    1. poka-yoke argument validation (closed schemas, hard caps);
    2. navigation policy verdict (SSRF / scheme / userinfo deny);
    3. per-target politeness window;
    4. proxy acquisition (pool exhaustion is an honest error);
    5. engine call inside a timeout budget;
    6. sanitize, cap, render structured markdown;
    7. wrap in an MCP ``tools/call`` envelope.

    Failures at any step produce an ``isError`` envelope with a stable code —
    never a partial success, never a bare exception escaping to the transport.
    """

    DEFAULT_TIMEOUT_S = 30.0
    MAX_TIMEOUT_S = 120.0
    MIN_HOST_INTERVAL_S_DEFAULT = 2.0

    def __init__(
        self,
        engine: BrowserEngine,
        *,
        policy: Optional[NavigationPolicy] = None,
        proxies: Optional[ProxyPool] = None,
        sanitizer: Optional[DomSanitizer] = None,
        rng: Optional[random.Random] = None,
        profile: Optional[StealthProfile] = None,
        min_host_interval_s: float = MIN_HOST_INTERVAL_S_DEFAULT,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._engine = engine
        self._policy = policy or NavigationPolicy()
        self._proxies = proxies
        self._sanitizer = sanitizer or DomSanitizer()
        self._rng = rng or random.Random()
        self._profile = profile or StealthProfile.randomized(self._rng)
        problems = self._profile.validate_consistency()
        if problems:
            raise InvalidArgumentError(
                "stealth profile is internally inconsistent: " + "; ".join(problems)
            )
        self._min_interval = float(min_host_interval_s)
        self._clock = clock or time.monotonic
        self._last_hit: Dict[str, float] = {}
        self.engine_started = False

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._engine.start()
        self.engine_started = True

    def stop(self) -> None:
        self._engine.stop()
        self.engine_started = False

    @property
    def profile(self) -> StealthProfile:
        return self._profile

    # -- internals ----------------------------------------------------------

    def _politeness(self, url: str) -> None:
        if self._min_interval <= 0:
            return
        host = urlsplit(url).hostname or ""
        now = self._clock()
        last = self._last_hit.get(host)
        if last is not None:
            waited = now - last
            if waited < self._min_interval:
                raise RateLimitCooldownError(
                    f"per-host politeness window still open for {host!r} "
                    f"({self._min_interval - waited:.2f}s remaining)",
                    retry_after_s=self._min_interval - waited,
                )
        self._last_hit[host] = now

    def _acquire_proxy(self) -> Optional[ProxyConfig]:
        if self._proxies is None:
            return None
        return self._proxies.acquire()

    def _engine_call(self, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except BrowserRuntimeError:
            raise
        except Exception as exc:
            raise EngineCrashedError(
                f"engine raised an unexpected failure: {type(exc).__name__}: {exc}"
            ) from exc

    def _blocked(self, url: str) -> Dict[str, Any]:
        verdict = self._policy.is_allowed(url)
        if verdict.allowed:
            return {}
        raise NavigationBlockedError(f"target refused by navigation policy: {verdict.reason}")

    # -- tool operations ----------------------------------------------------

    def navigate(self, url: str, *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        url = _check_str(url, "url", _ARG_CAPS["url"])
        timeout = self._clamp_timeout(timeout_s)
        self._blocked(url)
        self._politeness(url)
        proxy = self._acquire_proxy()
        load: PageLoad = self._engine_call(
            lambda: self._engine.navigate(url, proxy, timeout)
        )
        text = truncate_output(self._sanitizer.extract_text(load.html))
        md = structured_markdown(f"Navigation report: {load.title}", [
            ("Request", f"- URL: {load.url}\n- Status: {load.status}\n"
                        f"- Proxy: {proxy.label() if proxy else 'direct'}\n"
                        f"- Fingerprint: {self._profile.locale} / {self._profile.timezone_id}"),
            ("Extracted text", f"```\n{text}\n```" if text else "(empty page)"),
        ])
        return ok_envelope([text_block(md)])

    def screenshot(self, url: str, *, full_page: bool = False,
                   timeout_s: Optional[float] = None) -> Dict[str, Any]:
        url = _check_str(url, "url", _ARG_CAPS["url"])
        if not isinstance(full_page, bool):
            raise InvalidArgumentError("argument 'full_page' must be a boolean")
        timeout = self._clamp_timeout(timeout_s)
        self._blocked(url)
        self._politeness(url)
        proxy = self._acquire_proxy()
        raw: bytes = self._engine_call(
            lambda: self._engine.screenshot(url, proxy, full_page, timeout)
        )
        if not raw:
            raise EngineCrashedError("engine returned an empty screenshot")
        data = base64.b64encode(raw).decode("ascii")
        md = structured_markdown(f"Screenshot: {url}", [
            ("Capture", f"- Full page: {full_page}\n- Bytes: {len(raw)}\n"
                        f"- Proxy: {proxy.label() if proxy else 'direct'}"),
        ])
        return ok_envelope([text_block(md), image_block(data)])

    def scrape_text(self, url: str, *, max_chars: int = 20_000,
                    timeout_s: Optional[float] = None) -> Dict[str, Any]:
        url = _check_str(url, "url", _ARG_CAPS["url"])
        if not isinstance(max_chars, int) or isinstance(max_chars, bool) or not (1 <= max_chars <= _ARG_CAPS["max_chars"]):
            raise InvalidArgumentError(
                f"argument 'max_chars' must be an integer in [1, {_ARG_CAPS['max_chars']}]"
            )
        timeout = self._clamp_timeout(timeout_s)
        self._blocked(url)
        self._politeness(url)
        proxy = self._acquire_proxy()
        load: PageLoad = self._engine_call(
            lambda: self._engine.scrape_text(url, proxy, timeout)
        )
        text = truncate_output(self._sanitizer.extract_text(load.html), cap=max_chars)
        md = structured_markdown(f"Scrape report: {load.title}", [
            ("Request", f"- URL: {load.url}\n- Status: {load.status}\n"
                        f"- Proxy: {proxy.label() if proxy else 'direct'}"),
            ("Text", f"```\n{text}\n```" if text else "(empty page)"),
        ])
        return ok_envelope([text_block(md)])

    def evaluate_js(self, url: str, expression: str,
                    timeout_s: Optional[float] = None) -> Dict[str, Any]:
        url = _check_str(url, "url", _ARG_CAPS["url"])
        expression = _check_str(expression, "expression", _ARG_CAPS["expression"])
        timeout = self._clamp_timeout(timeout_s)
        self._blocked(url)
        self._politeness(url)
        proxy = self._acquire_proxy()
        result: str = self._engine_call(
            lambda: self._engine.evaluate_js(url, expression, proxy, timeout)
        )
        shown = truncate_output(result, cap=10_000)
        md = structured_markdown(f"Evaluate result: {url}", [
            ("Expression", f"```\n{expression}\n```"),
            ("Result", f"```\n{shown}\n```"),
        ])
        return ok_envelope([text_block(md)])

    # -- helpers ------------------------------------------------------------

    def _clamp_timeout(self, timeout_s: Optional[float]) -> float:
        if timeout_s is None:
            return self.DEFAULT_TIMEOUT_S
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
            raise InvalidArgumentError("argument 'timeout_s' must be a number")
        if not (1.0 <= float(timeout_s) <= self.MAX_TIMEOUT_S):
            raise InvalidArgumentError(
                f"argument 'timeout_s' must be within [1, {self.MAX_TIMEOUT_S}]"
            )
        return float(timeout_s)


# ---------------------------------------------------------------------------
# MCP tool catalog + dispatcher
# ---------------------------------------------------------------------------

TOOL_NAMES: Tuple[str, ...] = ("navigate", "screenshot", "scrape_text", "evaluate_js")

_URL_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 2048}
_TIMEOUT_SCHEMA = {"type": "number", "minimum": 1, "maximum": 120}

TOOL_CATALOG: Tuple[Dict[str, Any], ...] = (
    {
        "name": "navigate",
        "description": (
            "Navigate the stealth browser to a URL and return a structured "
            "markdown report (status, fingerprint, sanitized text preview)."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["url"],
            "properties": {
                "url": _URL_SCHEMA,
                "timeout_s": _TIMEOUT_SCHEMA,
            },
        },
    },
    {
        "name": "screenshot",
        "description": (
            "Capture a PNG screenshot of the target URL. Returns a text "
            "summary plus an image content block (base64 PNG)."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["url"],
            "properties": {
                "url": _URL_SCHEMA,
                "full_page": {"type": "boolean", "default": False},
                "timeout_s": _TIMEOUT_SCHEMA,
            },
        },
    },
    {
        "name": "scrape_text",
        "description": (
            "Extract sanitized plain text from the rendered DOM of the "
            "target URL, capped at max_chars."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["url"],
            "properties": {
                "url": _URL_SCHEMA,
                "max_chars": {"type": "integer", "minimum": 1, "maximum": 200000},
                "timeout_s": _TIMEOUT_SCHEMA,
            },
        },
    },
    {
        "name": "evaluate_js",
        "description": (
            "Evaluate a JavaScript expression in the isolated page context "
            "of the target URL and return the serialized result."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["url", "expression"],
            "properties": {
                "url": _URL_SCHEMA,
                "expression": {"type": "string", "minLength": 1, "maxLength": 100000},
                "timeout_s": _TIMEOUT_SCHEMA,
            },
        },
    },
)


def invoke_tool(runtime: BrowserRuntime, name: str, arguments: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Dispatch one MCP ``tools/call`` against the runtime.

    Unknown tools and malformed argument maps are answered with honest
    ``isError`` envelopes (content-level errors keep every transport uniform);
    protocol-level failures (bad JSON-RPC) are the server's responsibility.
    """
    if name not in TOOL_NAMES:
        return error_envelope(
            "UNKNOWN_TOOL",
            f"tool {name!r} is not part of the browser sandbox catalog "
            f"({', '.join(TOOL_NAMES)})",
        )
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, Mapping):
        return error_envelope("INVALID_ARGUMENT", "arguments must be an object")
    try:
        if name == "navigate":
            return runtime.navigate(
                arguments.get("url"),
                timeout_s=arguments.get("timeout_s"),
            )
        if name == "screenshot":
            return runtime.screenshot(
                arguments.get("url"),
                full_page=arguments.get("full_page", False),
                timeout_s=arguments.get("timeout_s"),
            )
        if name == "scrape_text":
            return runtime.scrape_text(
                arguments.get("url"),
                max_chars=arguments.get("max_chars", 20_000),
                timeout_s=arguments.get("timeout_s"),
            )
        return runtime.evaluate_js(
            arguments.get("url"),
            arguments.get("expression"),
            timeout_s=arguments.get("timeout_s"),
        )
    except BrowserRuntimeError as exc:
        return exc.envelope()
    except Exception as exc:  # last-resort honest envelope
        return error_envelope(
            "ENGINE_CRASHED",
            f"unexpected runtime failure: {type(exc).__name__}: {exc}",
            retryable=True,
        )
