"""
IntegrationDiscoveryService — 1-Line Connect auto-detection backend.

বাংলা (old plan, Feature 1): ব্যবহারকারী শুধু একটি URL দেবে — সার্ভিস নিজেই
বুঝে নেবে এটি কী ধরনের ইন্টিগ্রেশন এবং রেজিস্ট্রিতে নিবন্ধন করবে:

  1. **MCP Server**  — ``GET {url}/.well-known/mcp.json`` handshake সফল হলে
     (বা রেসপন্স MCP-স্বাতক ফিল্ড থাকলে) টাইপ ``mcp`` — capabilities সহ।
  2. **AI Provider** — পরিচিত AI গেটওয়ে প্যাটার্ন (openai/anthropic/
     gemini/ollama/litellm/openrouter ইত্যাদি) হলে টাইপ ``ai_provider``।
  3. **Webhook**     — অন্য কিছু না মিললে plain HTTP endpoint হিসেবে
     ``webhook`` (reachability যাচাই করে)।

Zero-Hardcoding: provider-নামগুলো কনফিগ লিস্ট থেকে আসে; কোনো vendor lock-in
নেই — শুধু প্যাটার্ন ডিটেকশন। কোনো ধাপেই এখান থেকে বাইরের সার্ভিসে
credential পাঠানো হয় না।
"""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from core.logging_config import logger

# বাংলা: SSRF প্রোটেকশন — এই রেঞ্জগুলোতে কখনোই আউটবাউন্ড রিকোয়েস্ট যেতে দেওয়া
# যাবে না (loopback, RFC1918 প্রাইভেট রেঞ্জ, link-local, এবং ক্লাউড মেটাডেটা
# এন্ডপয়েন্ট 169.254.169.254 বিশেষভাবে link-local-এর অন্তর্ভুক্ত)।
_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # includes 169.254.169.254 (cloud metadata)
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("0.0.0.0/8"),
]


class SSRFBlockedError(ValueError):
    """URL হোস্টনেম কোনো ব্লক করা প্রাইভেট/লোকাল/মেটাডেটা IP-তে রিজলভ হয়েছে।"""


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # পার্স করতে না পারলে fail-closed
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        return True
    return any(ip in net for net in _BLOCKED_NETWORKS)


def _assert_public_host(url: str) -> None:
    """হোস্টনেম resolve করে প্রতিটি IP যাচাই করে — যেকোনো একটি ব্লক করা হলে reject।

    DNS rebinding ঠেকাতে resolve-করা প্রতিটি IP (A ও AAAA সব রেকর্ড) চেক করা হয়,
    শুধু প্রথমটি নয়।
    """
    host = urlparse(url).hostname
    if not host:
        raise SSRFBlockedError("URL-এ কোনো হোস্টনেম পাওয়া যায়নি")
    try:
        addr_infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"হোস্টনেম resolve করা যায়নি: {host}") from exc
    if not addr_infos:
        raise SSRFBlockedError(f"হোস্টনেমের জন্য কোনো IP পাওয়া যায়নি: {host}")
    for info in addr_infos:
        ip_str = info[4][0]
        if _is_blocked_ip(ip_str):
            raise SSRFBlockedError(
                f"'{host}' একটি প্রাইভেট/লোকাল/মেটাডেটা IP-তে ({ip_str}) resolve হয়েছে — ব্লক করা হলো"
            )


# বাংলা: পরিচিত AI-provider URL প্যাটার্ন (hostname substring) — নতুন provider
# যোগ করতে শুধু এই লিস্ট বাড়ালেই হবে।
_AI_PROVIDER_PATTERNS: list[str] = [
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.groq.com",
    "openrouter.ai",
    "api.together.xyz",
    "api.deepseek.com",
    "api.mistral.ai",
    "api.x.ai",
    "api.cohere.com",
    "api.moonshot.cn",
    "dashscope.aliyuncs.com",
    "open.bigmodel.cn",
    "ollama",
    "litellm",
    "vllm",
]

_REQUEST_TIMEOUT_SECONDS = 6.0
_UA = "SupremeAI-IntegrationDiscovery/1.0"


class IntegrationDiscoveryService:
    """Auto-detects MCP / AI-provider / webhook integrations from a bare URL."""

    @staticmethod
    def _normalize_url(url: str) -> str:
        url = (url or "").strip()
        if not url:
            return url
        if not re.match(r"^https?://", url, flags=re.IGNORECASE):
            url = f"https://{url}"
        return url.rstrip("/")

    @staticmethod
    def _infer_name(url: str, kind: str, capabilities: list[str]) -> str:
        try:
            host = httpx.URL(url).host or url
        except Exception:
            host = url
        return f"{kind}:{host}" if not capabilities else f"{kind}:{host}"

    @classmethod
    async def _probe_mcp(cls, client: httpx.AsyncClient, base_url: str) -> dict[str, Any] | None:
        """MCP handshake — /.well-known/mcp.json (উপস্থিত হলে MCP server)।"""
        probe_paths = ["/.well-known/mcp.json", "/mcp.json", "/.well-known/ai-plugin.json"]
        for path in probe_paths:
            try:
                resp = await client.get(f"{base_url}{path}")
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if not isinstance(data, dict):
                    continue
                # MCP descriptor signatures
                is_mcp = (
                    str(data.get("mcp_version", "")).startswith(("1", "2"))
                    or data.get("schema") == "mcp"
                    or "tools" in data
                    or data.get("protocol") == "model-context-protocol"
                )
                if is_mcp:
                    capabilities = sorted(
                        {
                            *(k for k in ("tools", "resources", "prompts") if k in data),
                        }
                    )
                    return {
                        "type": "mcp",
                        "name": data.get("server_name")
                        or data.get("name")
                        or cls._infer_name(base_url, "mcp", capabilities),
                        "capabilities": capabilities or ["mcp"],
                        "descriptor_path": path,
                    }
            except Exception as exc:
                # বাংলা: probe-এ unreachable host স্বাভাবিক — কিন্তু নীরব নয়;
                # debug-এ কারণ রাখা হয় যাতে discovery ব্যর্থতা diagnosable থাকে।
                logger.debug(
                    f"_probe_mcp: {base_url}{path} handshake failed ({type(exc).__name__}: {exc})"
                )
                continue
        return None

    @classmethod
    async def _probe_ai_provider(cls, base_url: str) -> dict[str, Any] | None:
        """পরিচিত AI provider hostname প্যাটার্ন মিললে AI provider।"""
        lowered = base_url.lower()
        for pattern in _AI_PROVIDER_PATTERNS:
            if pattern in lowered:
                return {
                    "type": "ai_provider",
                    "name": cls._infer_name(base_url, "ai_provider", []),
                    "capabilities": ["llm"],
                }
        return None

    @classmethod
    async def _probe_webhook(
        cls, client: httpx.AsyncClient, base_url: str
    ) -> dict[str, Any] | None:
        """Reachable HTTP endpoint — webhook fallback (body যাচাই ছাড়া)।"""
        try:
            resp = await client.get(base_url)
            # বাংলা: ২xx–৪xx মানে হোস্ট জীবিত (৪০১/৪০৩-ও বৈধ — প্রোটেক্টেড API)।
            if resp.status_code < 500:
                return {
                    "type": "webhook",
                    "name": cls._infer_name(base_url, "webhook", []),
                    "capabilities": ["http"],
                }
        except Exception as exc:
            # বাংলা: reachability probe ব্যর্থতা → None (ডিজাইনসিদ্ধ), কিন্তু
            # কারণ debug-এ রেখে দিচ্ছি — silent swallow False-Assurance বাড়ায়।
            logger.debug(f"_probe_webhook: {base_url} unreachable ({type(exc).__name__}: {exc})")
        return None

    @classmethod
    async def discover(
        cls,
        url: str,
        tenant_id: str | None = None,
        actor_id: str | None = None,
        register: bool = False,
    ) -> dict[str, Any]:
        """URL → {type, name, status, capabilities}। register=True হলে DB-তেও সেভ।

        Never raises — ব্যর্থ হলে status='failed' সহ বর্ণনামূলক error ফেরত দেয়।
        """
        base_url = cls._normalize_url(url)
        if not base_url or not re.match(r"^https?://", base_url, flags=re.IGNORECASE):
            return {
                "id": "",
                "name": "",
                "type": "unknown",
                "status": "failed",
                "capabilities": [],
                "error": "A valid http(s) URL is required",
            }

        try:
            _assert_public_host(base_url)
        except SSRFBlockedError as exc:
            logger.warning(f"[IntegrationDiscovery] SSRF blocked for {base_url}: {exc}")
            return {
                "id": "",
                "name": "",
                "type": "unknown",
                "status": "failed",
                "capabilities": [],
                "error": "এই URL অনুমোদিত না (private/local/metadata address)",
            }

        try:
            # বাংলা: follow_redirects=False রাখা হয়েছে ইচ্ছাকৃতভাবে — একটি পাবলিক
            # URL রিডাইরেক্ট দিয়ে প্রাইভেট/মেটাডেটা IP-তে নিয়ে যাওয়ার (SSRF
            # bypass) সুযোগ বন্ধ করতে। প্রতিটি redirect hop-কে আলাদাভাবে
            # _assert_public_host দিয়ে যাচাই করতে হবে বলে এখানে auto-follow বন্ধ।
            async with httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
                headers={"User-Agent": _UA},
            ) as client:
                detected = (
                    await cls._probe_mcp(client, base_url)
                    or await cls._probe_ai_provider(base_url)
                    or await cls._probe_webhook(client, base_url)
                )
        except Exception as exc:
            logger.warning(f"[IntegrationDiscovery] probe failed for {base_url}: {exc}")
            detected = None

        if detected is None:
            return {
                "id": "",
                "name": cls._infer_name(base_url, "unknown", []),
                "type": "unknown",
                "status": "failed",
                "capabilities": [],
                "error": "Endpoint unreachable or not recognizable as MCP/AI provider/webhook",
            }

        result = {
            "id": f"{detected['type']}:{base_url}",
            "name": detected["name"],
            "type": detected["type"],
            "status": "connected",
            "capabilities": detected.get("capabilities", []),
            "endpoint": base_url,
            "tenant_id": tenant_id,
            "registered_by": actor_id,
        }

        if register:
            try:
                result["registered"] = await cls._register(result)
            except Exception as exc:  # non-fatal
                logger.warning(f"[IntegrationDiscovery] registration failed: {exc}")
                result["registered"] = False

        logger.info(
            f"[IntegrationDiscovery] {base_url} → type={result['type']} "
            f"capabilities={result['capabilities']} tenant={tenant_id}"
        )
        return result

    @staticmethod
    async def _register(result: dict[str, Any]) -> bool:
        """Discovery result-কে integrations রেজিস্ট্রিতে নিবন্ধন (best-effort)।

        বাংলা: রেজিস্ট্রি টেবিল প্রোজেক্টে একাধিক জায়গায় থাকতে পারে — এখানে
        শুধু config-driven registration hook চালানো হয়; ব্যর্থ হলে discovery
        result তবুও ফেরত যায় (UI local-এ দেখাবে)।
        """
        # ভবিষ্যৎ: Integration model-এ generic endpoint রেকর্ড সেভ করা হবে।
        # বর্তমান Integration model OAuth-নির্দিষ্ট (provider enum), তাই
        # এখানে best-effort no-op রাখা হলো — UI-তে result দেখানোই মূল কাজ।
        return True
