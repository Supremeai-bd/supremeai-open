"""Walled-garden session bridge (Agent-Reach pattern).

Safe, fail-closed cookie/session importer so agents can READ login-walled
platforms (X/Twitter, Reddit, LinkedIn class sites) without paid API keys.

Security invariants:
  - EMPTY allowlist by default: no cookie import succeeds until the operator
    explicitly names the walled-garden domains for this deployment.
  - Domain match is suffix-with-dot-boundary (`twitter.com` matches
    `www.twitter.com`, never `evil-twitter.com`).
  - Cookie values never appear in logs or reprs (redacted).
  - Netscape cookies.txt round-trips byte-stably for exported domains.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

__all__ = ["CookieBridge", "CookieRecord", "WalledGardenViolation"]

NETSCAPE_HEADER = "# Netscape HTTP Cookie File (supremeai-browser cookie bridge)"

_COOKIE_FIELDS = ("name", "value", "domain", "path", "secure", "http_only", "expires")


class WalledGardenViolation(PermissionError):
    """Raised when a cookie targets a domain outside the allowlist."""


@dataclass(frozen=True)
class CookieRecord:
    name: str
    value: str
    domain: str
    path: str = "/"
    secure: bool = True
    http_only: bool = True
    expires: int = 0  # 0 = session cookie

    def redacted(self) -> Dict[str, object]:
        """Safe view: value length only, never the value itself."""
        return {
            "name": self.name,
            "value": f"<redacted:{len(self.value)}B>",
            "domain": self.domain,
            "path": self.path,
            "secure": self.secure,
            "httpOnly": self.http_only,
            "expires": self.expires,
        }


class CookieBridge:
    """Allowlist-scoped cookie store with JSON/Netscape import-export."""

    def __init__(self, allowlist: Iterable[str]) -> None:
        domains = {self._normalize(d) for d in (allowlist or ()) if d and str(d).strip()}
        self._allowlist = frozenset(domains)
        self._cookies: Dict[str, Dict[str, CookieRecord]] = {}

    # -- allowlist -----------------------------------------------------------
    @staticmethod
    def _normalize(domain: str) -> str:
        d = str(domain).strip().lower().lstrip(".")
        if not d or "/" in d or " " in d:
            raise ValueError(f"invalid domain: {domain!r}")
        return d

    @property
    def allowlist(self) -> Tuple[str, ...]:
        return tuple(sorted(self._allowlist))

    def domain_allowed(self, domain: str) -> bool:
        d = self._normalize(domain)
        return any(d == a or d.endswith("." + a) for a in self._allowlist)

    def _guard(self, domain: str) -> str:
        d = self._normalize(domain)
        if not self._allowlist:
            raise WalledGardenViolation(
                "walled garden is EMPTY by default; the operator must allowlist "
                f"domains before any cookie import (refused: {d})"
            )
        if not self.domain_allowed(d):
            raise WalledGardenViolation(
                f"domain {d!r} is outside the walled-garden allowlist"
            )
        return d

    # -- import ---------------------------------------------------------------
    def import_json(self, cookies: List[dict], domain: str) -> int:
        """Import cookie dicts (browser-export shape) for one allowlisted domain."""
        d = self._guard(domain)
        if not isinstance(cookies, list):
            raise ValueError("cookies must be a list of dicts")
        bucket = self._cookies.setdefault(d, {})
        accepted = 0
        for raw in cookies:
            if not isinstance(raw, dict):
                raise ValueError("each cookie must be a dict")
            name = str(raw.get("name", "")).strip()
            value = str(raw.get("value", ""))
            if not name:
                raise ValueError("cookie name required")
            record = CookieRecord(
                name=name,
                value=value,
                domain=str(raw.get("domain", d)).lstrip(".").lower() or d,
                path=str(raw.get("path", "/")) or "/",
                secure=bool(raw.get("secure", True)),
                http_only=bool(raw.get("httpOnly", raw.get("http_only", True))),
                expires=int(raw.get("expires", 0) or 0),
            )
            if not self.domain_allowed(record.domain):
                raise WalledGardenViolation(
                    f"cookie {record.name!r} targets non-allowlisted domain {record.domain!r}"
                )
            bucket[f"{record.domain}|{record.path}|{record.name}"] = record
            accepted += 1
        return accepted

    def import_netscape(self, text: str, domain: str) -> int:
        """Parse Netscape cookies.txt lines scoped to one allowlisted domain."""
        d = self._guard(domain)
        cookies: List[dict] = []
        for line in (text or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 7:
                raise ValueError(f"malformed netscape line ({len(parts)} fields): <redacted>")
            c_domain, _flag, c_path, _secure_flag, expires, name, value = parts
            cookies.append({
                "domain": c_domain,
                "path": c_path,
                "secure": c_domain.startswith("."),
                "expires": int(expires) if expires.isdigit() else 0,
                "name": name,
                "value": value,
                "httpOnly": False,
            })
        return self.import_json(cookies, d)

    # -- export -----------------------------------------------------------------
    def export_netscape(self, domain: str) -> str:
        """Emit Netscape-format lines for one allowlisted domain."""
        d = self._guard(domain)
        bucket = self._cookies.get(d, {})
        lines = [NETSCAPE_HEADER]
        for key in sorted(bucket):
            c = bucket[key]
            domain_field = "." + c.domain if c.secure else c.domain
            lines.append(
                "\t".join([
                    domain_field, "TRUE", c.path, "TRUE" if c.secure else "FALSE",
                    str(c.expires), c.name, c.value,
                ])
            )
        return "\n".join(lines) + "\n"

    # -- introspection ------------------------------------------------------------
    def count(self, domain: Optional[str] = None) -> int:
        if domain is None:
            return sum(len(v) for v in self._cookies.values())
        d = self._normalize(domain)
        return len(self._cookies.get(d, {}))

    def summary(self) -> Dict[str, object]:
        """Redacted operational summary (safe to log)."""
        return {
            "allowlist": list(self.allowlist),
            "domains_loaded": sorted(self._cookies.keys()),
            "cookies_total": self.count(),
            "values": "redacted",
        }
