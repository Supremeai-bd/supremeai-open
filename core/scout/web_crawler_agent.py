"""Legacy web crawler agent adapter delegating to CrawlerService."""

from __future__ import annotations

import asyncio
from typing import Any

from scout.crawler import CrawlerService
from scout.models import CrawlPolicy, CrawlRequest, DomainRule, TrustLevel

APPROVED_DOMAINS = ["github.com", "arxiv.org", "docs.python.org", "huggingface.co"]


class CrawlResult:
    """Backwards-compatible crawl result object."""

    def __init__(
        self,
        url: str = "",
        content: str = "",
        status: int = 200,
        title: str = "",
        extractive_summary: str = "",
    ) -> None:
        self.url = url
        self.content = content
        self.status = status
        self.title = title
        self.extractive_summary = extractive_summary


async def crawl(
    url: str,
    max_depth: int = 1,
    max_results: int = 5,
    *,
    tenant_id: str,
) -> CrawlResult:
    """Run a crawl under an explicitly supplied tenant policy."""
    if not tenant_id.strip():
        raise ValueError("tenant_id is required")

    domain_rules = [
        DomainRule(domain=domain, trust_level=TrustLevel.TRUSTED) for domain in APPROVED_DOMAINS
    ]
    policy = CrawlPolicy(
        tenant_id=tenant_id,
        allowed_domains=list(APPROVED_DOMAINS),
        domain_rules=domain_rules,
        max_depth=max_depth,
        max_results=max_results,
    )

    service = CrawlerService(policy=policy)
    request = CrawlRequest(
        query_or_url=url,
        tenant_id=tenant_id,
        max_depth=max_depth,
        max_results=max_results,
    )

    allowed, reason = service.policy_engine.is_url_allowed(url, current_depth=0)
    if not allowed:
        raise PermissionError(f"Domain not approved: {url} ({reason})")

    response = await service.execute_crawl(request)
    first_page = response.pages[0] if response.pages else None

    return CrawlResult(
        url=url,
        content=first_page.content if first_page else "",
        status=first_page.status_code if first_page else 200,
        title=first_page.title if first_page else "",
        extractive_summary=response.extractive_summary,
    )
