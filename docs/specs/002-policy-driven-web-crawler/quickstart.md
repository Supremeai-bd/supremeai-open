# Quickstart Validation Guide: Policy-Driven Web Crawler

**Feature**: `002-policy-driven-web-crawler`  
**Date**: 2026-09-05  

---

## 1. Unit & Component Verification

Run the dedicated test suite for the crawler components:

```bash
# 1. Test pure deduplication logic (exact hash + Jaccard similarity)
pytest backend/tests/scout/test_dedup.py -vv

# 2. Test zero-token extractive summarization with all AI providers unconfigured
pytest backend/tests/scout/test_extractor.py -vv

# 3. Test policy enforcement (domain allowlist, rate pacing, depth limits)
pytest backend/tests/scout/test_crawler_policy.py -vv
```

---

## 2. Manual Integration Smoke Test

Execute an in-process smoke test script to verify real-world execution:

```python
import asyncio
from backend.scout.crawler import CrawlerService, CrawlRequest

async def smoke_test():
    crawler = CrawlerService()
    # Request crawling on an allowed domain
    req = CrawlRequest(
        query_or_url="https://docs.python.org/3/",
        tenant_id="test-tenant",
        task_id="task-smoke-001",
        max_depth=2,
        max_results=5
    )
    result = await crawler.execute_crawl(req)
    print(f"Total fetched: {result.total_fetched}")
    print(f"Duplicates skipped: {result.total_duplicates_skipped}")
    print(f"Token reduction: {result.token_reduction_pct:.1f}%")
    print(f"Extractive summary preview:\n{result.extractive_summary[:300]}...")

if __name__ == "__main__":
    asyncio.run(smoke_test())
```

---

## 3. Verifying Acceptance Criteria

1. **Policy Pacing & Blocking**:
   - Verify that non-allowlisted domains generate a `domain_skipped` event and are never requested.
   - Verify that requests to the same domain maintain $\ge 1$ second interval (or policy-defined limit).
2. **Zero-Token Offline Summary**:
   - Run tests with `OPENAI_API_KEY=""` and `GEMINI_API_KEY=""`. Verify that `CrawlResponse.extractive_summary` is populated without exception.
3. **Downstream Token Reduction**:
   - Verify that duplicate sections/pages are omitted, achieving $\ge 30\%$ reduction in downstream characters passed to LLMs.
