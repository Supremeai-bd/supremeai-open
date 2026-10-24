# Python Interface Contracts: `backend/scout/`

**Feature**: `002-policy-driven-web-crawler`  
**Date**: 2026-09-05  

---

## 1. Primary Entry Point: `CrawlerService`

```python
class CrawlRequest(BaseModel):
    query_or_url: str
    tenant_id: str
    task_id: str
    max_depth: int | None = None
    max_results: int | None = None
    custom_headers: dict[str, str] = Field(default_factory=dict)


class CrawlPageResult(BaseModel):
    url: str
    domain: str
    status_code: int
    title: str
    content: str
    content_hash: str
    is_duplicate: bool
    depth: int


class CrawlResponse(BaseModel):
    task_id: str
    tenant_id: str
    query: str
    pages: list[CrawlPageResult]
    total_fetched: int
    total_duplicates_skipped: int
    token_reduction_pct: float
    extractive_summary: str
    history_id: str


class CrawlerService:
    async def execute_crawl(self, request: CrawlRequest) -> CrawlResponse:
        """Executes a policy-governed crawl, deduplicating content and generating zero-token extractive summaries."""
        ...
```

## 2. Deduplication Interface: `backend/scout/dedup.py`

```python
class ContentDeduplicator:
    def __init__(self, similarity_threshold: float = 0.80) -> None:
        self.similarity_threshold = similarity_threshold

    def is_duplicate(self, content: str) -> bool:
        """Returns True if the content exactly matches a seen hash or has Jaccard similarity >= threshold."""
        ...

    def record_content(self, content: str) -> str:
        """Stores the content hash and shingle fingerprints, returning the SHA-256 hash."""
        ...
```

## 3. Extractive Summarizer: `backend/scout/extractor.py`

```python
class ExtractiveSummarizer:
    def summarize(self, text: str, max_sentences: int = 5, max_chars: int = 2000) -> str:
        """Zero-token salience ranking to extract the most informative sentences without calling an LLM."""
        ...
```
