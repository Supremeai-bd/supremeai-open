"""Crawl policy evaluation engine and SSRF security enforcement."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from core.security import is_safe_url
from scout.models import CrawlPolicy, DomainRule, TrustLevel


class PolicyEngine:
    """Evaluates whether target URLs and domains comply with active tenant policy and security standards."""

    def __init__(self, policy: CrawlPolicy | None = None) -> None:
        if policy is None:
            raise ValueError("A tenant-scoped crawl policy is required")
        self.policy = policy
        self._rules_by_domain: dict[str, DomainRule] = {
            r.domain.lower(): r for r in self.policy.domain_rules
        }

    @staticmethod
    def extract_domain(url: str) -> str:
        """Extracts the normalized lowercase domain/hostname from a URL."""
        try:
            parsed = urlparse(url)
            return (parsed.hostname or "").lower()
        except Exception:
            return ""

    @staticmethod
    def _matches_pattern(domain: str, pattern: str) -> bool:
        """Matches a domain against a pattern, supporting wildcards like *.python.org."""
        pattern = pattern.lower().strip()
        domain = domain.lower().strip()
        if pattern == "*" or pattern == domain:
            return True
        if pattern.startswith("*."):
            suffix = pattern[2:]
            return domain == suffix or domain.endswith("." + suffix)
        return False

    def is_active(self) -> bool:
        """বাংলা: নিষ্ক্রিয় policy মানেই কোনো crawl নয় (Policy Before Power)।"""
        return bool(self.policy.is_active)

    def is_url_allowed(self, url: str, current_depth: int = 0) -> tuple[bool, str]:
        """Validates URL against SSRF, domain permissions, depth limits, and trust levels.

        Returns (is_allowed, reason).
        """
        # 0. Policy must be active — an inactive policy authorizes nothing (fail-closed)
        if not self.policy.is_active:
            return False, "policy_inactive"

        # 1. Scheme and Hostname extraction
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            return False, "invalid_scheme"

        domain = self.extract_domain(url)
        if not domain:
            return False, "missing_hostname"

        # 2. Blocked domains list
        if any(self._matches_pattern(domain, pat) for pat in self.policy.blocked_domains):
            return False, "domain_explicitly_blocked"

        # 3. Depth validation
        max_depth = self.policy.max_depth
        domain_rule = self._rules_by_domain.get(domain)
        if domain_rule and domain_rule.max_depth is not None:
            max_depth = domain_rule.max_depth

        if current_depth > max_depth:
            return False, "depth_exceeded"

        # 4. Domain rule check if explicitly configured
        if domain_rule:
            if domain_rule.trust_level == TrustLevel.BLOCKED:
                return False, "domain_blocked"

            # Check path patterns
            parsed_path = urlparse(url).path or "/"
            if domain_rule.disallowed_paths:
                for pattern in domain_rule.disallowed_paths:
                    if re.search(pattern, parsed_path):
                        return False, "path_disallowed"

            if domain_rule.allowed_paths:
                allowed = any(re.search(p, parsed_path) for p in domain_rule.allowed_paths)
                if not allowed:
                    return False, "path_not_in_allowlist"
        elif self.policy.allowed_domains:
            # Check policy.allowed_domains if specified
            allowed = any(self._matches_pattern(domain, pat) for pat in self.policy.allowed_domains)
            if not allowed:
                return False, "domain_not_in_allowed_domains"
        elif self.policy.domain_rules:
            # If domain_rules list is non-empty and domain wasn't in it, fail closed
            return False, "domain_not_allowlisted"
        else:
            # বাংলা: কোনো allowlist/domain_rules নেই এমন খালি policy কিছুই অনুমোদন
            # করবে না — এটাই Spec 002 (US1 scenario 4) ও Constitution-এর
            # "Capability ≠ Permission" নীতির fail-closed প্রয়োগ। আগে এটি fail-open
            # ছিল — অর্থাৎ default policy-তে সব ডোমেইন crawl করা যেত।
            return False, "policy_fail_closed_no_allowlist"

        # 5. SSRF validation (only for domains passing domain policy)
        if not is_safe_url(url):
            return False, "ssrf_blocked"

        return True, "allowed"

    def get_rate_limit_for_domain(self, domain: str) -> int:
        """Returns the requests-per-minute limit for the domain."""
        rule = self._rules_by_domain.get(domain.lower())
        if rule:
            return rule.rate_limit_per_min
        return self.policy.default_rate_limit_per_min

    def requires_js_render(self, domain: str) -> bool:
        """Determines if the domain requires Playwright headless rendering."""
        rule = self._rules_by_domain.get(domain.lower())
        return bool(rule and rule.render_js)
