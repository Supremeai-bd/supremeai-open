"""Server-side render proxy for the in-app browser (SSRF-hardened).

Split out of the former single-module api/routes/browser.py verbatim.
Uses stdlib urllib only (no third-party http client) so the route cannot be
dropped because of a missing optional dependency at import time.
"""

import ipaddress
import os
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Response

from api.routes.browser import router
from core.config_parsers import parse_origin_list
from core.logging_config import logger

# বাংলা মন্তব্য: ইন-অ্যাপ ব্রাউজার proxy (public) — বাহিরের সাইট X-Frame-Options/frame-ancestors দিয়ে
# iframe ব্লক করে, তাই সার্ভার-সাইড ফেচ করে iframe-এ রেন্ডার করা হয়। SSRF প্রতিরোধ জরুরি।
_BLOCKED_NETS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _host_is_blocked(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, 80)
    except (socket.gaierror, socket.herror, OSError):
        # DNS resolution failure means we cannot verify the host — treat as
        # blocked to fail-closed (deny-by-default) rather than masking the error.
        logger.warning("Host resolution failed for %s", hostname, exc_info=True)
        return True
    for info in infos:
        raw_ip = info[4][0].split("%")[0]
        try:
            addr = ipaddress.ip_address(raw_ip)
        except ValueError:
            return True
        if addr.is_loopback or addr.is_private or addr.is_reserved or addr.is_link_local:
            return True
        for net in _BLOCKED_NETS:
            if addr in net:
                return True
    return False


def _frame_ancestors_sources() -> str:
    """Build the CSP ``frame-ancestors`` source list for the render proxy.

    SEC-HARDEN P6: the proxy previously sent ``frame-ancestors *`` (plus a
    non-standard ``X-Frame-Options: ALLOWALL``). That let ANY third-party site
    embed the proxy — a clickjacking / UI-redressing surface. Now only the
    app's own surface (``'self'``) plus every operator-configured frontend
    origin (``ALLOWED_ORIGINS``) may frame it. Never ``*``.
    """
    sources = ["'self'"]
    # Roadmap 1.4 (issue #1173): canonical parser — comma ছাড়াও JSON-array
    # ফরম্যাটে সেট করা ALLOWED_ORIGINS-ও সঠিকভাবে পার্স হয়।
    for origin in parse_origin_list(os.getenv("ALLOWED_ORIGINS", "")):
        sources.append(origin)
    return " ".join(sources)


# ─── Issue #1669 (CRITICAL): ticket-based auth for the render proxy ──────────
# JWT কখনো URL query-তে যাবে না (logs/history/Referer leak)। এখন flow:
#   1) ফ্রন্টএন্ড header-auth দিয়ে POST /api/browser/render-ticket কল করে
#   2) সার্ভার এক-ব্যবহারযোগ্য, 60s-TTL টিকেট জেনারেট করে (crypto-random)
#   3) iframe src = /api/browser/render?url=…&ticket=… — টিকেট consume হয়
# Query-token সরাসরি যাচাই-ই হত না (router guard header চায়) — ফাঁস ছাড়া
# কোনো কাজ ছিল না; এখন URL-এ শুধু অননুকলনযোগ্য (unguessable) এককালীন ticket থাকে।
_TICKET_TTL_SECONDS = 60
_TICKETS: dict[str, float] = {}
_TICKETS_LOCK = threading.Lock()


def _purge_expired_tickets(now: float) -> None:
    stale = [t for t, exp in _TICKETS.items() if exp <= now]
    for t in stale:
        _TICKETS.pop(t, None)


def _issue_ticket() -> str:
    ticket = secrets.token_urlsafe(32)
    with _TICKETS_LOCK:
        _purge_expired_tickets(time.time())
        _TICKETS[ticket] = time.time() + _TICKET_TTL_SECONDS
    return ticket


def _consume_ticket(ticket: str | None) -> bool:
    """One-time consume: valid, unexpired ticket হলে তা মুছে True ফেরত।"""
    if not ticket:
        return False
    now = time.time()
    with _TICKETS_LOCK:
        exp = _TICKETS.pop(ticket, None)
    return exp is not None and exp > now


@router.post("/render-ticket")
def issue_render_ticket():
    """Issue a short-lived ONE-TIME ticket for the iframe render proxy.

    Lives on the header-authenticated router — the browser attaches the JWT
    as an Authorization header (never in a URL).
    """
    return {"ticket": _issue_ticket(), "expires_in": _TICKET_TTL_SECONDS}


# The render GET is mounted WITHOUT the header-auth guard: iframe requests
# cannot attach Authorization headers. Auth = the single-use ticket above.
render_public_router = APIRouter(prefix="/api/browser", tags=["browser"])


@render_public_router.get("/render")
def render_proxy(url: str, ticket: str = ""):
    """Server-side web proxy so the in-app browser can render sites that block iframes.

    Uses stdlib urllib only (no third-party http client) so the route cannot be dropped
    because of a missing optional dependency at import time.
    """
    # Issue #1669: fail-closed ticket auth — no/invalid/reused ticket → 401.
    if not _consume_ticket(ticket):
        raise HTTPException(
            status_code=401,
            detail="Valid one-time render ticket required (obtain via POST /api/browser/render-ticket).",
        )
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Only absolute http(s) URLs are supported.")
    if _host_is_blocked(parsed.hostname):
        raise HTTPException(status_code=400, detail="Blocked or unresolvable host.")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SupremeAI-Browser/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            ctype = resp.headers.get("Content-Type", "") or ""
            data = resp.read()
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(status_code=502, detail="Response too large to proxy.")
        proxy_headers = {
            "Cache-Control": "no-store",
            # SEC-HARDEN P6: never ALLOWALL / frame-ancestors * — only the app's
            # own surfaces may embed the proxy response (prevents clickjacking).
            "X-Frame-Options": "SAMEORIGIN",
            "Content-Security-Policy": f"frame-ancestors {_frame_ancestors_sources()}",
        }
        if "text/html" in ctype:
            text = data.decode("utf-8", errors="replace")
            base_tag = f'<base href="{url}">'
            if "<head" in text:
                text = text.replace("<head", f"<head>{base_tag}", 1)
            elif "<HEAD" in text:
                text = text.replace("<HEAD", f"<HEAD>{base_tag}", 1)
            else:
                text = base_tag + text
            return Response(
                content=text,
                media_type="text/html; charset=utf-8",
                headers=proxy_headers,
            )
        return Response(
            content=data, media_type=ctype or "application/octet-stream", headers=proxy_headers
        )
    except HTTPException:
        raise
    except urllib.error.HTTPError as e:
        logger.error(f"Render proxy upstream error: {e.code} {e.reason}")
        raise HTTPException(status_code=502, detail=f"Upstream returned {e.code}.") from e
    except Exception as e:
        logger.error(f"Render proxy error: {e!s}")
        raise HTTPException(status_code=502, detail="Failed to fetch the requested URL.") from e
