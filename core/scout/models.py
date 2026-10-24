"""Pydantic data models for policy-driven web crawling."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class TrustLevel(enum.StrEnum):
    TRUSTED = "trusted"
    STANDARD = "standard"
    SUSPICIOUS = "suspicious"
    BLOCKED = "blocked"


class CrawlEventType(enum.StrEnum):
    NAV_START = "nav_start"
    NAV_COMPLETE = "nav_complete"
    EXTRACT_START = "extract_start"
    EXTRACT_COMPLETE = "extract_complete"
    DOMAIN_SKIPPED = "domain_skipped"
    DEPTH_REACHED = "depth_reached"
    RATE_LIMITED = "rate_limited"
    CACHED_ANSWER = "cached_answer"
    ERROR = "error"


class DomainRule(BaseModel):
    """Rule specifying constraints and behavior for a specific domain."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    domain: str
    trust_level: TrustLevel = TrustLevel.STANDARD
    rate_limit_per_min: int = Field(default=60, ge=1, le=1200)
    render_js: bool = False
    max_depth: int | None = Field(default=None, ge=1, le=5)
    allowed_paths: list[str] = Field(default_factory=list)
    disallowed_paths: list[str] = Field(default_factory=list)


class CrawlPolicy(BaseModel):
    """Tenant-scoped crawl governance policy."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = Field(..., min_length=1)
    name: str = Field(default="Default Policy", min_length=1, max_length=100)
    is_active: bool = True
    max_depth: int = Field(default=2, ge=1, le=5)
    max_results: int = Field(default=10, ge=1, le=50)
    default_rate_limit_per_min: int = Field(default=30, ge=1, le=600)
    request_timeout_seconds: int = Field(default=15, ge=3, le=60)
    cache_ttl_hours: int = Field(default=24, ge=0, le=720)
    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    domain_rules: list[DomainRule] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CrawlRequest(BaseModel):
    """Payload for submitting a crawl research task."""

    query_or_url: str
    tenant_id: str = Field(..., min_length=1)
    task_id: str = Field(default_factory=lambda: f"crawl-{uuid.uuid4().hex[:12]}")
    max_depth: int | None = None
    max_results: int | None = None
    custom_headers: dict[str, str] = Field(default_factory=dict)


class CrawlPageResult(BaseModel):
    """Metadata and content for a single crawled webpage."""

    url: str
    domain: str
    status_code: int
    title: str
    content: str
    content_hash: str
    is_duplicate: bool = False
    depth: int = 0
    extracted_links: list[str] = Field(default_factory=list)


class CrawlResponse(BaseModel):
    """Aggregated output from a completed crawl run."""

    task_id: str
    tenant_id: str
    query: str
    pages: list[CrawlPageResult] = Field(default_factory=list)
    total_fetched: int = 0
    total_duplicates_skipped: int = 0
    token_reduction_pct: float = 0.0
    extractive_summary: str = ""
    history_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class CrawlHistoryRecord(BaseModel):
    """Durable record stored for auditing and downstream consumption."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    tenant_id: str
    query: str
    sources_crawled: list[str] = Field(default_factory=list)
    total_pages_fetched: int = 0
    duplicate_pages_skipped: int = 0
    unique_content_hash: str = ""
    extractive_summary: str = ""
    token_reduction_pct: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
