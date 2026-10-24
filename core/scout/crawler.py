"""Primary policy-governed crawler service."""

from __future__ import annotations

import asyncio
import collections
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from core.logging_config import logger
from scout.cache import CrawlerCache
from scout.dedup import ContentDeduplicator
from scout.extractor import ExtractiveSummarizer
from scout.models import (
    CrawlEventType,
    CrawlPageResult,
    CrawlPolicy,
    CrawlRequest,
    CrawlResponse,
)
from scout.policy import PolicyEngine
from scout.robots import RobotsCache
from scout.telemetry import CrawlerTelemetry

_MAX_REDIRECT_HOPS = 5


class CrawlerService:
    """Orchestrates policy-guided crawling, deduplication, caching, and extractive summarization.

    বাংলা: Spec 002-এর hardening স্তর — per-domain rate pacing (FR-005),
    প্রতিটি redirect hop-এ SSRF/policy re-validation (FR-012), robots.txt সম্মান
    (FR-018), এবং পূর্ণ lifecycle event coverage (FR-010)।
    """

    def __init__(
        self,
        policy: CrawlPolicy | None = None,
        deduplicator: ContentDeduplicator | None = None,
        summarizer: ExtractiveSummarizer | None = None,
        cache: CrawlerCache | None = None,
    ) -> None:
        self.policy_engine = PolicyEngine(policy)
        self.deduplicator = deduplicator or ContentDeduplicator()
        self.summarizer = summarizer or ExtractiveSummarizer()
        self.cache = cache or CrawlerCache()
        self.robots = RobotsCache()
        self._rate_limiter = None

    async def _acquire_rate_slot(self, domain: str) -> bool:
        """বাংলা: ডোমেইন-ভিত্তিক pacing — policy-র rate_limit_per_min সম্মান করে।

        Redis না থাকলে AsyncRateLimiter নিজেই in-memory fallback ব্যবহার করে।
        যেকোনো limiter ত্রুটিতে আমরা degrade করে allow করি কিন্তু log রাখি।
        """
        limit = self.policy_engine.get_rate_limit_for_domain(domain)
        try:
            if self._rate_limiter is None:
                from middleware.rate_limiter import AsyncRateLimiter

                self._rate_limiter = AsyncRateLimiter()
            return await self._rate_limiter.acquire(f"scout:{domain}", limit=limit, window=60)
        except Exception as exc:
            logger.debug(f"rate limiter unavailable for {domain}: {exc}")
            return True

    @staticmethod
    def _clean_html(html: str) -> tuple[str, str, list[str]]:
        """Strips scripts, styling, navbars and returns (title, clean_text, links)."""
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else "No Title"

        # Remove irrelevant noise tags
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
            tag.decompose()

        text = " ".join(soup.get_text(separator=" ").split())
        links = [a.get("href", "") for a in soup.find_all("a", href=True) if a.get("href")]
        return title, text, links

    async def _fetch_with_redirect_validation(
        self,
        client: httpx.AsyncClient,
        url: str,
        telemetry: CrawlerTelemetry,
    ) -> httpx.Response | None:
        """Fetches `url` following redirects manually, re-validating every hop.

        বাংলা: follow_redirects=True দিলে httpx ভেতরের hop-গুলো policy/SSRF
        check ছাড়াই follow করত — এটা একটা redirect-based SSRF/rebinding দরজা ছিল
        (Spec 002 FR-012)। এখন প্রতিটি hop আবার PolicyEngine দিয়ে যায়।
        """
        current = url
        for _hop in range(_MAX_REDIRECT_HOPS + 1):
            allowed, reason = self.policy_engine.is_url_allowed(current)
            if not allowed:
                telemetry.emit_event(
                    CrawlEventType.DOMAIN_SKIPPED,
                    f"redirect hop rejected: {current} ({reason})",
                    severity="WARNING",
                    metadata={"url": current, "reason": reason},
                )
                return None
            resp = await client.get(current)
            if resp.is_redirect:
                location = resp.headers.get("location", "")
                if not location:
                    return resp
                current = urljoin(current, location)
                continue
            return resp
        telemetry.emit_event(
            CrawlEventType.ERROR,
            f"redirect hop limit exceeded for {url}",
            severity="WARNING",
            metadata={"url": url},
        )
        return None

    async def execute_crawl(self, request: CrawlRequest) -> CrawlResponse:
        """Executes a bounded, policy-controlled crawl starting from the target URL."""
        start_url = request.query_or_url
        max_depth = request.max_depth or self.policy_engine.policy.max_depth
        max_results = request.max_results or self.policy_engine.policy.max_results
        timeout_sec = self.policy_engine.policy.request_timeout_seconds
        telemetry = CrawlerTelemetry(request.tenant_id, request.task_id)

        # 0. Policy Before Power — inactive policy authorizes nothing
        if not self.policy_engine.is_active():
            telemetry.emit_event(
                CrawlEventType.ERROR,
                "crawl refused: policy is inactive",
                severity="WARNING",
                metadata={"policy_id": self.policy_engine.policy.id},
            )
            return CrawlResponse(
                task_id=request.task_id,
                tenant_id=request.tenant_id,
                query=request.query_or_url,
                pages=[],
                total_fetched=0,
                total_duplicates_skipped=0,
                token_reduction_pct=0.0,
                extractive_summary="",
            )

        # 1. Check cache first
        cached = await self.cache.get_cached_response(
            request.tenant_id, start_url, max_depth=max_depth
        )
        if cached:
            telemetry.emit_event(
                CrawlEventType.CACHED_ANSWER,
                f"Returning cached crawl response for {start_url}",
            )
            return cached

        telemetry.emit_event(
            CrawlEventType.NAV_START,
            f"Starting crawl on {start_url} (depth={max_depth}, results={max_results})",
        )

        queue: collections.deque[tuple[str, int]] = collections.deque([(start_url, 0)])
        visited_urls: set[str] = set()
        pages: list[CrawlPageResult] = []
        unique_texts: list[str] = []
        total_fetched = 0
        total_duplicates = 0
        raw_char_count = 0

        # Reset deduplication tracking for this run
        self.deduplicator.reset()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 SupremeAI-Scout/2.0",
            **request.custom_headers,
        }

        async with httpx.AsyncClient(
            headers=headers, timeout=float(timeout_sec), follow_redirects=False
        ) as client:
            while queue and len(pages) < max_results:
                url, depth = queue.popleft()
                if url in visited_urls:
                    continue
                visited_urls.add(url)

                # Policy gate: SSRF, allowed domain, depth check
                allowed, reason = self.policy_engine.is_url_allowed(url, current_depth=depth)
                if not allowed:
                    # বাংলা: আগে শুধু debug log ছিল — এখন observable event (FR-002/010)
                    event_type = (
                        CrawlEventType.DEPTH_REACHED
                        if reason == "depth_exceeded"
                        else CrawlEventType.DOMAIN_SKIPPED
                    )
                    telemetry.emit_event(
                        event_type,
                        f"skipped {url} ({reason})",
                        metadata={"url": url, "reason": reason, "depth": depth},
                    )
                    continue

                domain = self.policy_engine.extract_domain(url)

                # robots.txt compliance (FR-018) — governed fetch শুধু অনুমোদিত পথে
                if not await self.robots.is_allowed(url):
                    telemetry.emit_event(
                        CrawlEventType.DOMAIN_SKIPPED,
                        f"robots.txt disallows {url}",
                        severity="WARNING",
                        metadata={"url": url, "reason": "robots_disallowed"},
                    )
                    continue

                # Per-domain rate pacing (FR-005) — shared limiter across tasks
                if not await self._acquire_rate_slot(domain):
                    telemetry.emit_event(
                        CrawlEventType.RATE_LIMITED,
                        f"rate limit reached for {domain}; deferring {url}",
                        severity="WARNING",
                        metadata={"url": url, "domain": domain},
                    )
                    queue.append((url, depth))  # re-schedule instead of dropping
                    await asyncio.sleep(1.0)
                    continue

                try:
                    resp = await self._fetch_with_redirect_validation(client, url, telemetry)
                    if resp is None:
                        continue
                    total_fetched += 1
                    if resp.status_code >= 400:
                        telemetry.emit_event(
                            CrawlEventType.ERROR,
                            f"fetch returned HTTP {resp.status_code} for {url}",
                            severity="WARNING",
                            metadata={"url": url, "status_code": resp.status_code},
                        )
                        continue

                    telemetry.emit_event(
                        CrawlEventType.EXTRACT_START, f"extracting {url}", metadata={"url": url}
                    )
                    title, text, links = self._clean_html(resp.text)
                    raw_char_count += len(text)

                    # Deduplication check
                    content_hash, is_dup = self.deduplicator.record_content(text)
                    if is_dup:
                        total_duplicates += 1
                    else:
                        unique_texts.append(text)

                    page_result = CrawlPageResult(
                        url=url,
                        domain=domain,
                        status_code=resp.status_code,
                        title=title,
                        content=text if not is_dup else "[Duplicate Content Omitted]",
                        content_hash=content_hash,
                        is_duplicate=is_dup,
                        depth=depth,
                        extracted_links=links[:25],
                    )
                    pages.append(page_result)
                    telemetry.emit_event(
                        CrawlEventType.EXTRACT_COMPLETE,
                        f"extracted {url} ({len(text)} chars)",
                        metadata={"url": url, "chars": len(text)},
                    )

                    # Expand links if within depth limit
                    if depth < max_depth:
                        for raw_link in links:
                            resolved = urljoin(url, raw_link)
                            if resolved.startswith("http") and resolved not in visited_urls:
                                queue.append((resolved, depth + 1))

                except Exception as exc:
                    # বাংলা: একক ডোমেইনের ব্যর্থতা পুরো task ভাঙবে না (FR-014),
                    # কিন্তু এখন সেটা event-এ দৃশ্যমান হবে (No Silent Failure)
                    telemetry.emit_event(
                        CrawlEventType.ERROR,
                        f"failed to fetch {url}: {exc}",
                        severity="WARNING",
                        metadata={"url": url, "error": str(exc)[:300]},
                    )
                    continue

        # Zero-token extractive summarization across unique content
        merged_unique_content = " ".join(unique_texts)
        summary = self.summarizer.summarize(merged_unique_content, max_sentences=5, max_chars=2500)
        final_char_count = len(summary)

        token_reduction = 0.0
        if raw_char_count > 0 and final_char_count < raw_char_count:
            token_reduction = round((1.0 - (final_char_count / raw_char_count)) * 100, 1)

        response = CrawlResponse(
            task_id=request.task_id,
            tenant_id=request.tenant_id,
            query=request.query_or_url,
            pages=pages,
            total_fetched=total_fetched,
            total_duplicates_skipped=total_duplicates,
            token_reduction_pct=token_reduction,
            extractive_summary=summary,
        )

        telemetry.emit_event(
            CrawlEventType.NAV_COMPLETE,
            f"Crawl completed for {start_url}: {len(pages)} pages fetched, {total_duplicates} duplicates skipped, {token_reduction}% tokens saved",
            metadata={
                "pages_count": len(pages),
                "token_reduction_pct": token_reduction,
            },
        )

        # Store in cache
        await self.cache.store_response(
            request.tenant_id,
            start_url,
            max_depth=max_depth,
            response=response,
            ttl_seconds=self.policy_engine.policy.cache_ttl_hours * 3600,
        )

        return response
