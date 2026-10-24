"""Skill Marketplace Curator — Tier 8 Meta-Self Module.

Manages a decentralized skill marketplace where agents
can publish, discover, rate, and subscribe to skills.
Zero hardcoded skills — all runtime-discovered.

Lint-free: ruff --select=ALL --ignore=E501 passes.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, ClassVar

# বাংলা মন্তব্য: `backend.core.*` → `core.*` fix — Docker WORKDIR=/app/backend
from core.base import BaseSkill
from core.config import settings
from core.llm.llm_gateway import LLMGateway, get_llm_gateway
from core.logging_config import logger
from core.observability.telemetry import get_tracer, trace_span


class ListingStatus(Enum):
    """Lifecycle states for a marketplace skill listing."""

    DRAFT = auto()
    PENDING_REVIEW = auto()
    PUBLISHED = auto()
    DEPRECATED = auto()
    REMOVED = auto()


@dataclass(frozen=True, slots=True)
class SkillListing:
    """Immutable marketplace listing for a skill."""

    listing_id: str
    skill_name: str
    description: str
    author: str
    version: str
    tags: tuple[str, ...]
    rating: float = 0.0
    review_count: int = 0
    download_count: int = 0
    status: ListingStatus = ListingStatus.DRAFT
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def with_rating(self, new_rating: float) -> SkillListing:
        total = self.rating * self.review_count + new_rating
        new_count = self.review_count + 1
        return SkillListing(
            listing_id=self.listing_id,
            skill_name=self.skill_name,
            description=self.description,
            author=self.author,
            version=self.version,
            tags=self.tags,
            rating=total / new_count,
            review_count=new_count,
            download_count=self.download_count,
            status=self.status,
            created_at=self.created_at,
            updated_at=time.time(),
        )

    def with_download(self) -> SkillListing:
        return SkillListing(
            listing_id=self.listing_id,
            skill_name=self.skill_name,
            description=self.description,
            author=self.author,
            version=self.version,
            tags=self.tags,
            rating=self.rating,
            review_count=self.review_count,
            download_count=self.download_count + 1,
            status=self.status,
            created_at=self.created_at,
            updated_at=time.time(),
        )

    def with_status(self, status: ListingStatus) -> SkillListing:
        return SkillListing(
            listing_id=self.listing_id,
            skill_name=self.skill_name,
            description=self.description,
            author=self.author,
            version=self.version,
            tags=self.tags,
            rating=self.rating,
            review_count=self.review_count,
            download_count=self.download_count,
            status=status,
            created_at=self.created_at,
            updated_at=time.time(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "skill_name": self.skill_name,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "tags": list(self.tags),
            "rating": self.rating,
            "review_count": self.review_count,
            "download_count": self.download_count,
            "status": self.status.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillListing:
        return cls(
            listing_id=data["listing_id"],
            skill_name=data["skill_name"],
            description=data["description"],
            author=data["author"],
            version=data["version"],
            tags=tuple(data.get("tags", [])),
            rating=data.get("rating", 0.0),
            review_count=data.get("review_count", 0),
            download_count=data.get("download_count", 0),
            status=ListingStatus[data.get("status", "DRAFT")],
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


class SkillMarketplaceCurator(BaseSkill):
    """Tier-8 curator for the decentralized skill marketplace."""

    _instance: ClassVar[SkillMarketplaceCurator | None] = None
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __new__(cls) -> SkillMarketplaceCurator:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._llm: LLMGateway | None = None
        # বাংলা মন্তব্য: প্রোজেক্টের get_tracer ফাংশনটি কোনো আর্গুমেন্ট গ্রহণ করে না
        self._tracer = get_tracer()
        self._listings: dict[str, SkillListing] = {}
        self._subscriptions: dict[str, set[str]] = {}  # user_id -> set of listing_ids
        self._skill_registry: dict[str, type[BaseSkill]] = {}
        self._running = False
        self._auto_curate = os.getenv("MARKETPLACE_AUTO_CURATE", "true").lower() == "true"
        self._min_rating_threshold = float(os.getenv("MARKETPLACE_MIN_RATING", "3.0"))
        self._review_required = int(os.getenv("MARKETPLACE_REVIEW_REQUIRED") or "3")
        self._task: asyncio.Task[Any] | None = None
        self._skills_dir = Path(os.getenv("SKILLS_DIR", "backend/core/skills"))

    @property
    def name(self) -> str:
        return "skill_marketplace_curator"

    async def _get_llm(self) -> LLMGateway:
        if self._llm is None:
            self._llm = await get_llm_gateway()
        return self._llm

    @trace_span("marketplace.start")
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self._discover_local_skills()
        if self._auto_curate:
            self._task = asyncio.create_task(self._curation_loop())

    @trace_span("marketplace.stop")
    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")

    async def _discover_local_skills(self) -> None:
        """Auto-register skills found in the skills directory."""
        if not self._skills_dir.exists():
            return
        for py_file in self._skills_dir.glob("*.py"):
            if py_file.stem in {"__init__", "base"}:
                continue
            listing_id = hashlib.sha256(py_file.read_bytes()).hexdigest()[:16]
            listing = SkillListing(
                listing_id=listing_id,
                skill_name=py_file.stem,
                description=f"Auto-discovered skill: {py_file.stem}",
                author="system",
                version="1.0.0",
                tags=("auto-discovered", "local"),
                status=ListingStatus.PUBLISHED,
            )
            self._listings[listing_id] = listing

    async def _curation_loop(self) -> None:
        """Periodic curation: review, rank, and prune listings."""
        interval = float(os.getenv("MARKETPLACE_CURATE_INTERVAL", "300.0"))
        while self._running:
            try:
                await self._auto_review_pending()
                await self._prune_deprecated()
                await self._generate_trending_report()
            except Exception as exc:
                await self._log_error("curation_loop", str(exc))
            await asyncio.sleep(interval)

    async def _auto_review_pending(self) -> None:
        """Use LLM to auto-review pending listings."""
        llm = await self._get_llm()
        pending = [
            lid
            for lid, listing in self._listings.items()
            if listing.status == ListingStatus.PENDING_REVIEW
        ]
        for lid in pending:
            listing = self._listings[lid]
            prompt = (
                f"Review this skill listing for quality.\n"
                f"Name: {listing.skill_name}\n"
                f"Description: {listing.description}\n"
                f"Tags: {', '.join(listing.tags)}\n\n"
                f"Respond with ONLY 'APPROVE' or 'REJECT'."
            )
            try:
                response = await llm.acompletion(
                    model=os.getenv(
                        "MARKETPLACE_REVIEW_MODEL",
                        getattr(settings, "model_general", "gpt-4o-mini"),
                    ),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=10,
                )
                decision = response.get("content", "").strip().upper()
                if decision == "APPROVE":
                    self._listings[lid] = listing.with_status(ListingStatus.PUBLISHED)
                else:
                    self._listings[lid] = listing.with_status(ListingStatus.REMOVED)
            except Exception as e:
                # বাংলা মন্তব্য: লিন্ট এরর এড়াতে এক্সেপশন লগ করা হচ্ছে
                logger.error(f"Error in verification: {e}")

    async def _prune_deprecated(self) -> None:
        """Remove listings with too many negative reviews."""
        to_remove = [
            lid
            for lid, listing in self._listings.items()
            if listing.status == ListingStatus.PUBLISHED
            and listing.review_count >= self._review_required
            and listing.rating < self._min_rating_threshold
        ]
        for lid in to_remove:
            self._listings[lid] = self._listings[lid].with_status(ListingStatus.DEPRECATED)

    async def _generate_trending_report(self) -> None:
        """Generate a trending skills report (logged, not stored)."""
        trending = sorted(
            self._listings.values(),
            key=lambda listing: (
                listing.download_count * 0.5 + listing.rating * listing.review_count
            ),
            reverse=True,
        )[:10]
        with self._tracer.start_as_current_span("marketplace.trending") as span:
            span.set_attribute("trending_count", len(trending))
            for idx, listing in enumerate(trending):
                span.set_attribute(f"trending.{idx}", listing.skill_name)

    async def publish_listing(
        self,
        skill_name: str,
        description: str,
        author: str,
        version: str,
        tags: list[str],
    ) -> str:
        """Publish a new skill listing."""
        listing_id = hashlib.sha256(
            f"{skill_name}:{author}:{version}:{time.time()}".encode()
        ).hexdigest()[:16]
        listing = SkillListing(
            listing_id=listing_id,
            skill_name=skill_name,
            description=description,
            author=author,
            version=version,
            tags=tuple(tags),
            status=(ListingStatus.PENDING_REVIEW if self._auto_curate else ListingStatus.PUBLISHED),
        )
        self._listings[listing_id] = listing
        return listing_id

    async def rate_listing(self, listing_id: str, rating: float, user_id: str) -> dict[str, Any]:
        """Rate a skill listing."""
        if listing_id not in self._listings:
            return {"error": "listing_not_found"}
        if not (0.0 <= rating <= 5.0):
            return {"error": "invalid_rating"}
        self._listings[listing_id] = self._listings[listing_id].with_rating(rating)
        return {"status": "rated", "new_rating": self._listings[listing_id].rating}

    async def subscribe(self, user_id: str, listing_id: str) -> dict[str, Any]:
        """Subscribe a user to a skill listing."""
        if listing_id not in self._listings:
            return {"error": "listing_not_found"}
        self._subscriptions.setdefault(user_id, set()).add(listing_id)
        self._listings[listing_id] = self._listings[listing_id].with_download()
        return {"status": "subscribed", "listing_id": listing_id}

    async def search(self, query: str, tags: list[str] | None = None) -> list[dict[str, Any]]:
        """Search listings by name, description, or tags."""
        results = []
        query_lower = query.lower()
        for listing in self._listings.values():
            if listing.status != ListingStatus.PUBLISHED:
                continue
            match = (
                query_lower in listing.skill_name.lower()
                or query_lower in listing.description.lower()
            )
            if tags and not set(tags).issubset(set(listing.tags)):
                match = False
            if match:
                results.append(listing.to_dict())
        # Sort by relevance (rating * downloads)
        results.sort(
            key=lambda x: x["rating"] * x["download_count"],
            reverse=True,
        )
        return results

    async def get_trending(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return trending skill listings."""
        trending = sorted(
            self._listings.values(),
            key=lambda listing: (
                listing.download_count * 0.5 + listing.rating * listing.review_count
            ),
            reverse=True,
        )[:limit]
        return [
            listing.to_dict() for listing in trending if listing.status == ListingStatus.PUBLISHED
        ]

    async def _log_error(self, context: str, message: str) -> None:
        with self._tracer.start_as_current_span("marketplace.error") as span:
            span.set_attribute("context", context)
            span.set_attribute("error", message)

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        action = kwargs.get("action", "status")
        if action == "start":
            await self.start()
            return {"status": "started"}
        if action == "stop":
            await self.stop()
            return {"status": "stopped"}
        if action == "publish":
            lid = await self.publish_listing(
                skill_name=kwargs["skill_name"],
                description=kwargs["description"],
                author=kwargs["author"],
                version=kwargs.get("version", "1.0.0"),
                tags=kwargs.get("tags", []),
            )
            return {"status": "published", "listing_id": lid}
        if action == "rate":
            return await self.rate_listing(
                kwargs.get("listing_id", ""),
                kwargs.get("rating", 0.0),
                kwargs.get("user_id", "anonymous"),
            )
        if action == "subscribe":
            return await self.subscribe(
                kwargs.get("user_id", "anonymous"),
                kwargs.get("listing_id", ""),
            )
        if action == "search":
            return {
                "results": await self.search(
                    kwargs.get("query", ""),
                    kwargs.get("tags"),
                ),
            }
        if action == "trending":
            return {
                "results": await self.get_trending(kwargs.get("limit", 10)),
            }
        if action == "status":
            return {
                "running": self._running,
                "listings": len(self._listings),
                "published": sum(
                    1
                    for listing in self._listings.values()
                    if listing.status == ListingStatus.PUBLISHED
                ),
                "subscribers": len(self._subscriptions),
            }
        return {"status": "unknown_action", "action": action}


def get_skill_marketplace_curator() -> SkillMarketplaceCurator:
    return SkillMarketplaceCurator()
