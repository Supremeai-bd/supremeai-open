"""
Minimal SSRF protection for the standalone scraper service.
Self-contained — does NOT import from backend/core/security to avoid
pulling in DB/Redis/asyncpg dependencies.

Two layers (issue #511, BE-05 — SSRF via HTTP redirects + DNS rebinding):

  1. ``is_safe_url()`` — synchronous parse-time screening (scheme + hostname
     literals). Cheap, no DNS. Suitable for request intake.
  2. ``is_safe_url_resolved()`` — request-time screening: resolves the
     hostname to ALL its A/AAAA records and rejects the URL if ANY resolved
     IP is private/loopback/link-local/metadata/reserved. The fetch path must
     call this immediately before EVERY HTTP request (initial URL and every
     redirect hop), closing the redirect and DNS-rebinding bypasses of
     layer 1.

Residual risk (documented per issue #511): between the resolved-IP check and
the actual TCP connect, httpx re-resolves DNS on its own. A rebinding server
flipping its answer inside that TOCTOU window could still land the connection
on a private IP. Full mitigation requires pinning the validated IP at the
transport layer (custom httpcore backend) — intentionally out of scope here;
per-hop re-validation shrinks the window to a single connect.
"""

from ipaddress import IPv6Address, ip_address, ip_network
from socket import gaierror, getaddrinfo
from urllib.parse import urlparse

_BLOCKED_SCHEMES = {"file", "ftp", "gopher", "dict", "ldap", "javascript", "data"}
_BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata",  # GCP metadata (resolvable via /etc/hosts on GCP)
    "metadata.google.internal",  # GCP metadata endpoint
}  # is_local()
_PRIVATE_PREFIXES = ("10.", "172.16.", "192.168.", "169.254.", "100.64.", "fc", "fe80:")

# Issue #511: networks that must never be dialed, matched against *resolved*
# IPs (not just URL literals). Superset of the legacy _PRIVATE_PREFIXES list —
# adds CGNAT 100.64/10 (which also covers Alibaba metadata 100.100.100.200),
# multicast, benchmarking and documentation/reserved ranges.
_BLOCKED_V4_NETWORKS = tuple(
    ip_network(n)
    for n in (
        "0.0.0.0/8",  # unspecified / "this host"
        "10.0.0.0/8",  # private (RFC1918)
        "100.64.0.0/10",  # CGNAT / carrier NAT
        "127.0.0.0/8",  # loopback
        "169.254.0.0/16",  # link-local (AWS/GCP/Azure metadata lives here)
        "172.16.0.0/12",  # private (RFC1918)
        "192.0.0.0/24",  # IETF protocol assignments
        "192.0.2.0/24",  # TEST-NET-1 (documentation)
        "192.168.0.0/16",  # private (RFC1918)
        "198.18.0.0/15",  # benchmarking
        "198.51.100.0/24",  # TEST-NET-2 (documentation)
        "203.0.113.0/24",  # TEST-NET-3 (documentation)
        "224.0.0.0/4",  # multicast
        "240.0.0.0/4",  # reserved (incl. 255.255.255.255)
    )
)
_BLOCKED_V6_NETWORKS = tuple(
    ip_network(n)
    for n in (
        "::/128",  # unspecified
        "::1/128",  # loopback
        "100::/64",  # discard-only
        "2001:db8::/32",  # documentation
        "fc00::/7",  # unique-local (private)
        "fe80::/10",  # link-local
        "ff00::/8",  # multicast
    )
)


def _is_private_ip(hostname: str) -> bool:
    """Parse-time literal-IP check (kept for backward compatibility)."""
    try:
        ip = ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def _is_blocked_ip(ip: str) -> bool:
    """True if ``ip`` may never be dialed. Fails closed on malformed input."""
    try:
        addr = ip_address(ip)
    except ValueError:
        return True
    if isinstance(addr, IPv6Address) and addr.ipv4_mapped is not None:
        # Screen the embedded IPv4 address of an IPv4-mapped IPv6 literal
        # (::ffff:10.0.0.1 is just 10.0.0.1 in disguise).
        addr = addr.ipv4_mapped
    networks = _BLOCKED_V4_NETWORKS if addr.version == 4 else _BLOCKED_V6_NETWORKS
    return any(addr in net for net in networks)


def resolve_hostname(hostname: str) -> list[str]:
    """Resolve ``hostname`` to every A/AAAA record.

    No caching on purpose — a DNS cache would widen the rebinding TOCTOU
    window (issue #511). Returns [] when resolution fails; callers must fail
    closed (a hostile resolver answering NXDOMAIN to us and 127.0.0.1 to
    httpx must not slip through).
    """
    try:
        infos = getaddrinfo(hostname, None)
    except (gaierror, OSError, UnicodeError):
        return []
    ips: list[str] = []
    for info in infos:
        candidate = str(info[4][0])
        if candidate not in ips:
            ips.append(candidate)
    return ips


def is_safe_url(url: str) -> bool:
    """Validate URL to prevent SSRF attacks in the standalone scraper service.

    Parse-time checks only (scheme + hostname literals) — does NOT resolve
    DNS and does NOT see redirect targets. The fetch path must additionally
    call :func:`is_safe_url_resolved` immediately before every request
    (issue #511).
    """
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or scheme in _BLOCKED_SCHEMES:
            return False

        hostname = parsed.hostname or ""
        if not hostname:
            return False

        if hostname.lower() in _BLOCKED_HOSTS:
            return False

        if _is_private_ip(hostname):
            return False

        for prefix in _PRIVATE_PREFIXES:
            if hostname.lower().startswith(prefix):
                return False

        return True
    except Exception:  # noqa: BLE001
        return False


def is_safe_url_resolved(url: str) -> bool:
    """Request-time SSRF validation for the fetch path (issue #511).

    Runs the parse-time checks, then resolves the hostname and rejects the
    URL if ANY resolved A/AAAA record is private/loopback/link-local/etc.
    Fails closed when DNS resolution fails.
    """
    if not is_safe_url(url):
        return False
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001
        return False
    if not hostname:
        return False
    resolved = resolve_hostname(hostname)
    if not resolved:
        return False  # DNS failure — fail closed (issue #511)
    return all(not _is_blocked_ip(ip) for ip in resolved)
