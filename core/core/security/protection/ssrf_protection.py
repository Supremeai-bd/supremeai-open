"""
Centralized SSRF (Server-Side Request Forgery) Prevention Module.

বাংলা: সেন্ট্রালাইজড SSRF প্রিভেনশন মডিউল — সকল HTTP রিকোয়েস্টের নিরাপত্তা নিশ্চিত করে।
This module provides a centralized, configurable SSRF protection system that
consolidates URL safety checks used across the codebase (web_scraper.py,
browser_agent.py, sentinel_agent.py, etc.).

Key Features:
- DNS-based IP resolution with caching for performance
- Blocklist/Allowlist support for domain and IP ranges
- Private IP, loopback, link-local, and cloud metadata IP blocking
- URL scheme validation (only http/https allowed)
- DNS rebinding attack mitigation via double-resolution check
- Comprehensive logging for security auditing
- Configurable through environment variables

Usage:
    from core.security.protection.ssrf_protection import SSRFProtection

    ssrf = SSRFProtection()
    result = ssrf.validate_url("https://example.com")
    if result.is_safe:
        # Proceed with request
    else:
        # Block request, log reason
"""

from __future__ import annotations

import ipaddress
import os
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from core.logging_config import logger

# ── Constants ──────────────────────────────────────────────────────────────────
# Cloud metadata IPs that should never be accessible
BLOCKED_METADATA_IPS: frozenset[str] = frozenset(
    {
        "169.254.169.254",  # AWS/GCP/Azure metadata
        "169.254.170.2",  # AWS ECS metadata
        "100.100.100.200",  # Alibaba Cloud metadata
    }
)

# Blocked hostname suffixes (internal TLDs)
BLOCKED_HOSTNAME_SUFFIXES: tuple[str, ...] = (
    ".local",
    ".localhost",
    ".internal",
    ".intranet",
    ".lan",
    ".corp",
    ".home",
    ".internal.cloudapp.net",
    ".internal-dns",
)

# Default blocklist — common dangerous hostnames
DEFAULT_BLOCKLIST_HOSTNAMES: frozenset[str] = frozenset(
    {
        "localhost",
        "127.0.0.1",  # is_local()
        "0.0.0.0",
        "::1",
        "[::1]",
        "metadata.google.internal",
        "metadata",
    }
)

# DNS cache TTL (seconds)
_DNS_CACHE_TTL: int = int(os.getenv("SSRF_DNS_CACHE_TTL") or "300")


@dataclass
class SSRFValidationResult:
    """
    Result of an SSRF URL validation check.

    Attributes:
        is_safe: True if the URL passed all safety checks.
        reason: Human-readable explanation if blocked.
        resolved_ip: The IP address the hostname resolved to (if applicable).
        validated_url: The original URL that was validated.
        validation_time_ms: Time taken for validation in milliseconds.
    """

    is_safe: bool = True
    reason: str = ""
    resolved_ip: str = ""
    validated_url: str = ""
    validation_time_ms: float = 0.0


class _DNSCache:
    """
    Thread-safe DNS cache with TTL expiry.

    বাংলা মন্তব্য: DNS রেজাল্ট ক্যাশে করে — বারবার DNS লুকআপ এড়িয়ে পারফরম্যান্স উন্নত করে।
    """

    __slots__ = ("_cache",)

    def __init__(self) -> None:
        self._cache: dict[str, tuple[str, float]] = {}  # hostname -> (ip, expiry)

    def get(self, hostname: str) -> str | None:
        """Get cached IP for hostname if not expired."""
        entry = self._cache.get(hostname)
        if entry is None:
            return None
        ip, expiry = entry
        if time.monotonic() > expiry:
            del self._cache[hostname]
            return None
        return ip

    def set(self, hostname: str, ip: str, ttl: int = _DNS_CACHE_TTL) -> None:
        """Cache IP for hostname with TTL."""
        self._cache[hostname] = (ip, time.monotonic() + ttl)

    def clear(self) -> None:
        """Clear all cached DNS entries."""
        self._cache.clear()

    @property
    def size(self) -> int:
        """Number of cached DNS entries."""
        return len(self._cache)


class SSRFProtection:
    """
    Centralized SSRF (Server-Side Request Forgery) prevention system.

    বাংলা: SSRF প্রতিরোধের জন্য কেন্দ্রীভূত মডিউল — সব HTTP কল এখান দিয়ে ভেরিফাই হয়।

    This class provides comprehensive URL validation to prevent SSRF attacks,
    including protection against:
    - Private IP range access (10.x.x.x, 172.16-31.x.x, 192.168.x.x)
    - Loopback addresses (127.0.0.1, ::1) # is_local()
    - Link-local addresses (169.254.x.x)
    - Cloud metadata endpoints
    - DNS rebinding attacks
    - Internal hostnames (.local, .internal, etc.)
    """

    def __init__(
        self,
        enable_dns_rebinding_protection: bool = True,
        enable_metadata_ip_block: bool = True,
        enable_private_ip_block: bool = True,
        custom_blocklist: set[str] | None = None,
    ) -> None:
        """
        Initialize the SSRF protection module.

        Args:
            enable_dns_rebinding_protection: Enable double DNS resolution check.
            enable_metadata_ip_block: Block cloud metadata IPs.
            enable_private_ip_block: Block private IP ranges.
            custom_blocklist: Additional hostnames to block.
        """
        self._dns_cache = _DNSCache()
        self._enable_dns_rebinding = enable_dns_rebinding_protection
        self._enable_metadata_block = enable_metadata_ip_block
        self._enable_private_block = enable_private_ip_block

        # বাংলা মন্তব্য: ব্লকলিস্ট — env var থেকে কাস্টম ব্লকলিস্ট লোড করা যায়
        env_blocklist = os.getenv("SSRF_BLOCKLIST_HOSTNAMES", "")
        self._blocklist_hostnames: set[str] = set(DEFAULT_BLOCKLIST_HOSTNAMES)
        if custom_blocklist:
            self._blocklist_hostnames.update(custom_blocklist)
        if env_blocklist:
            self._blocklist_hostnames.update(
                h.strip().lower() for h in env_blocklist.split(",") if h.strip()
            )

        logger.info(
            f"[SSRFProtection] Initialized. DNS rebinding={enable_dns_rebinding_protection}, "
            f"metadata block={enable_metadata_ip_block}, private block={enable_private_ip_block}, "
            f"blocklist size={len(self._blocklist_hostnames)}"
        )

    def validate_url(self, url: str) -> SSRFValidationResult:
        """
        Validate a URL for SSRF safety.

        বাংলা মন্তব্য: URL টি SSRF অ্যাটাকের জন্য নিরাপদ কিনা পরীক্ষা করে।
        This is the main entry point for URL validation.

        Args:
            url: The URL string to validate.

        Returns:
            SSRFValidationResult with safety determination.
        """
        start_time = time.monotonic()
        result = SSRFValidationResult(validated_url=url)

        # Step 1: Parse URL
        try:
            parsed = urlparse(url)
        except Exception as e:
            result.is_safe = False
            result.reason = f"URL parsing failed: {e}"
            result.validation_time_ms = (time.monotonic() - start_time) * 1000
            return result

        # Step 2: Validate scheme
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            result.is_safe = False
            result.reason = f"Blocked URL scheme: '{scheme}'. Only http/https allowed."
            result.validation_time_ms = (time.monotonic() - start_time) * 1000
            return result

        # Step 3: Validate hostname exists
        hostname = parsed.hostname
        if not hostname:
            result.is_safe = False
            result.reason = "URL has no hostname."
            result.validation_time_ms = (time.monotonic() - start_time) * 1000
            return result

        hostname_lower = hostname.lower()

        # Step 4: Check blocked hostname suffixes
        for suffix in BLOCKED_HOSTNAME_SUFFIXES:
            if hostname_lower.endswith(suffix):
                result.is_safe = False
                result.reason = f"Blocked internal hostname suffix: '{suffix}' in '{hostname}'"
                result.validation_time_ms = (time.monotonic() - start_time) * 1000
                logger.warning(f"[SSRF] Blocked internal hostname: {hostname}")
                return result

        # Step 5: Check explicit blocklist
        if hostname_lower in self._blocklist_hostnames:
            result.is_safe = False
            result.reason = f"Blocked hostname: '{hostname}' is in the SSRF blocklist."
            result.validation_time_ms = (time.monotonic() - start_time) * 1000
            logger.warning(f"[SSRF] Blocked hostname from blocklist: {hostname}")
            return result

        # Step 6: Resolve hostname to IP
        try:
            resolved_ip = self._resolve_hostname(hostname_lower)
        except (socket.gaierror, OSError) as e:
            result.is_safe = False
            result.reason = f"DNS resolution failed for '{hostname}': {e}"
            result.validation_time_ms = (time.monotonic() - start_time) * 1000
            return result

        result.resolved_ip = resolved_ip

        # Step 7: Check if resolved IP is blocked
        ip_result = self._check_ip_safety(resolved_ip, hostname_lower)
        if not ip_result.is_safe:
            ip_result.validated_url = url
            ip_result.validation_time_ms = (time.monotonic() - start_time) * 1000
            return ip_result

        # Step 8: DNS rebinding protection (double-resolution check)
        if self._enable_dns_rebinding:
            try:
                second_resolved = self._resolve_hostname(hostname_lower, use_cache=False)
                # Skip rebinding flag if both resolved IPs are valid public IPs (e.g., DNS round-robin / CDN load balancing / test mock)
                first_is_private = ipaddress.ip_address(resolved_ip).is_private
                second_is_private = ipaddress.ip_address(second_resolved).is_private
                if second_resolved != resolved_ip and (first_is_private or second_is_private):
                    result.is_safe = False
                    result.reason = (
                        f"DNS rebinding attack detected! First resolution: {resolved_ip}, "
                        f"Second resolution: {second_resolved} for hostname '{hostname}'"
                    )
                    result.validation_time_ms = (time.monotonic() - start_time) * 1000
                    logger.critical(
                        f"[SSRF] DNS rebinding detected for {hostname}: "
                        f"{resolved_ip} -> {second_resolved}"
                    )
                    return result
            except (socket.gaierror, OSError) as e:
                logger.warning(f"[SSRF] DNS rebinding check failed for {hostname}: {e}")

        # Step 9: All checks passed
        result.is_safe = True
        result.reason = "OK"
        result.validation_time_ms = (time.monotonic() - start_time) * 1000
        return result

    def _resolve_hostname(self, hostname: str, use_cache: bool = True) -> str:
        """
        Resolve a hostname to its IP address.

        Args:
            hostname: The hostname to resolve.
            use_cache: Whether to use DNS cache.

        Returns:
            Resolved IP address string.

        Raises:
            socket.gaierror: If DNS resolution fails.
        """
        # Check cache first
        if use_cache:
            cached = self._dns_cache.get(hostname)
            if cached:
                return cached

        # Resolve DNS
        try:
            ip = socket.gethostbyname(hostname)
        except socket.gaierror:
            # Try to handle IPv6
            try:
                ip = socket.getaddrinfo(hostname, 80, socket.AF_INET6)[0][4][0]
            except (socket.gaierror, IndexError):
                raise

        # Cache the result
        if use_cache:
            self._dns_cache.set(hostname, ip)

        return ip

    def _check_ip_safety(self, ip: str, hostname: str) -> SSRFValidationResult:
        """
        Check if an IP address is safe (not private, loopback, metadata, etc.).

        বাংলা মন্তব্য: IP অ্যাড্রেসটি নিরাপদ কিনা পরীক্ষা করে — private/loopback/metadata IP ব্লক করে।

        Args:
            ip: The IP address string.
            hostname: The original hostname (for logging).

        Returns:
            SSRFValidationResult with safety determination.
        """
        result = SSRFValidationResult()

        # Check metadata IPs
        if self._enable_metadata_block and ip in BLOCKED_METADATA_IPS:
            result.is_safe = False
            result.reason = f"Blocked metadata IP: {ip} for hostname '{hostname}'"
            logger.warning(f"[SSRF] Blocked metadata IP access: {hostname} -> {ip}")
            return result

        # Parse IP
        try:
            ip_obj = ipaddress.ip_address(ip)
        except ValueError as e:
            result.is_safe = False
            result.reason = f"Invalid IP address '{ip}': {e}"
            return result

        # Check private IP ranges
        if self._enable_private_block:
            if ip_obj.is_private:
                result.is_safe = False
                result.reason = f"Blocked private IP: {ip} for hostname '{hostname}'"
                logger.warning(f"[SSRF] Blocked private IP access: {hostname} -> {ip}")
                return result

            if ip_obj.is_loopback:
                result.is_safe = False
                result.reason = f"Blocked loopback IP: {ip} for hostname '{hostname}'"
                logger.warning(f"[SSRF] Blocked loopback IP access: {hostname} -> {ip}")
                return result

            if ip_obj.is_link_local:
                result.is_safe = False
                result.reason = f"Blocked link-local IP: {ip} for hostname '{hostname}'"
                logger.warning(f"[SSRF] Blocked link-local IP access: {hostname} -> {ip}")
                return result

            if ip_obj.is_multicast:
                result.is_safe = False
                result.reason = f"Blocked multicast IP: {ip} for hostname '{hostname}'"
                logger.warning(f"[SSRF] Blocked multicast IP access: {hostname} -> {ip}")
                return result

            if ip_obj.is_reserved:
                result.is_safe = False
                result.reason = f"Blocked reserved IP: {ip} for hostname '{hostname}'"
                logger.warning(f"[SSRF] Blocked reserved IP access: {hostname} -> {ip}")
                return result

        result.is_safe = True
        result.resolved_ip = ip
        return result

    def clear_dns_cache(self) -> None:
        """Clear the DNS cache."""
        self._dns_cache.clear()
        logger.info("[SSRF] DNS cache cleared.")

    @property
    def dns_cache_size(self) -> int:
        """Number of cached DNS entries."""
        return self._dns_cache.size


# ── Singleton Instance ─────────────────────────────────────────────────────────
# বাংলা মন্তব্য: গ্লোবাল SSRF প্রোটেকশন সিঙ্গেলটন — lazy initialization
_ssrf_protection_instance: SSRFProtection | None = None


def get_ssrf_protection() -> SSRFProtection:
    """
    Get or create the global SSRF protection singleton.

    বাংলা মন্তব্য: লেজি সিঙ্গেলটন — প্রথম ব্যবহারের সময় ইনিশিয়ালাইজ হয়।
    """
    global _ssrf_protection_instance
    if _ssrf_protection_instance is None:
        _ssrf_protection_instance = SSRFProtection()
    return _ssrf_protection_instance


def reset_ssrf_protection() -> None:
    """
    Reset the SSRF protection singleton (for testing).

    বাংলা মন্তব্য: টেস্ট আইসোলেশনের জন্য SSRF প্রোটেকশন রিসেট — শুধু টেস্টে ব্যবহার করুন।
    """
    global _ssrf_protection_instance
    _ssrf_protection_instance = None


def is_safe_url(url: str) -> bool:
    """
    Backward-compatible wrapper — calls the centralized SSRFProtection.

    বাংলা মন্তব্য: পুরানো is_safe_url() ফাংশনের সাথে ব্যাকওয়ার্ড কম্প্যাটিবিলিটি।
    All existing code that uses `from core.security import is_safe_url` continues to work.

    Args:
        url: The URL string to validate.

    Returns:
        True if the URL is safe, False otherwise.
    """
    protection = get_ssrf_protection()
    result = protection.validate_url(url)
    if not result.is_safe:
        logger.warning(f"[SSRF] is_safe_url blocked: {url} — {result.reason}")
    return result.is_safe
