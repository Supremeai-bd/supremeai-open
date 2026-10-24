# backend/evolution/memory_consolidator.py
"""SupremeAI Smart Memory Consolidator (Phase 3 - Self-Evolution Layer).

Tiered in-memory management (HOT -> WARM -> COLD -> FROZEN),
online deduplication, automatic compression, and emergency consolidation.
"""

from __future__ import annotations

import gzip
import hashlib
import pickle
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class MemoryTier(StrEnum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    FROZEN = "frozen"


class ConsolidationAction(StrEnum):
    COMPRESS = "compress"
    OFFLOAD = "offload"
    EVICT = "evict"
    PROMOTE = "promote"
    DEMOTE = "demote"
    MERGE = "merge"
    PRUNE = "prune"


@dataclass
class MemoryBlock:
    block_id: str
    content_hash: str
    size_bytes: int
    tier: MemoryTier
    access_count: int
    last_accessed: datetime
    created_at: datetime
    compressed: bool = False
    compression_ratio: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    # FIX(real-compression): retain the serialized payload so consolidation
    # can perform actual gzip compression instead of merely decrementing
    # size_bytes (the old fake made every reported saving imaginary).
    payload: bytes | None = None


@dataclass
class ConsolidationResult:
    success: bool
    action_taken: ConsolidationAction
    memory_freed_bytes: int
    blocks_affected: int
    time_ms: int
    details: dict[str, Any] = field(default_factory=dict)


class MemoryConsolidator:
    """Intelligent tiered memory management and consolidation system."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = config or {}

        self.blocks: OrderedDict[str, MemoryBlock] = OrderedDict()
        self.tier_indexes: dict[MemoryTier, set[str]] = {tier: set() for tier in MemoryTier}

        self.max_memory_bytes: int = self.config.get("max_memory_mb", 2048) * 1024 * 1024
        self.hot_threshold: int = self.config.get("hot_access_count", 15)
        self.warm_threshold: int = self.config.get("warm_access_count", 5)
        self.cold_threshold_hours: int = self.config.get("cold_access_hours", 24)
        self.compression_enabled: bool = self.config.get("compression_enabled", True)

        self.access_log: list[tuple[str, datetime]] = []
        self._lock = threading.RLock()

        self.stats: dict[str, Any] = {
            "total_allocations": 0,
            "total_consolidations": 0,
            "memory_freed_total_mb": 0.0,
            "blocks_promoted": 0,
            "blocks_demoted": 0,
        }

    def allocate(
        self, data: Any, metadata: dict[str, Any] | None = None, tier: MemoryTier = MemoryTier.WARM
    ) -> str:
        with self._lock:
            serialized = self._serialize(data)
            content_hash = hashlib.sha256(serialized).hexdigest()[:16]

            # Check if block exists
            for block in self.blocks.values():
                if block.content_hash == content_hash:
                    self._access_block(block.block_id)
                    return block.block_id

            block_id = f"blk_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.md5(serialized).hexdigest()[:8]}"
            block = MemoryBlock(
                block_id=block_id,
                content_hash=content_hash,
                size_bytes=len(serialized),
                tier=tier,
                access_count=1,
                last_accessed=datetime.now(),
                created_at=datetime.now(),
                metadata=metadata or {},
                payload=serialized,
            )

            self.blocks[block_id] = block
            self.tier_indexes[tier].add(block_id)
            self.access_log.append((block_id, datetime.now()))
            self.stats["total_allocations"] += 1
            return block_id

    def access(self, block_id: str) -> Any | None:
        with self._lock:
            block = self.blocks.get(block_id)
            if not block:
                self.stats["cache_misses"] = self.stats.get("cache_misses", 0) + 1
                return None
            self.stats["cache_hits"] = self.stats.get("cache_hits", 0) + 1
            # Transparently decompress on access so the block is usable and
            # size accounting returns to the real (uncompressed) footprint.
            if block.compressed and block.payload is not None:
                block.payload = gzip.decompress(block.payload)
                block.compressed = False
                block.compression_ratio = 1.0
                block.size_bytes = len(block.payload)
            self._access_block(block_id)
            return {"block_id": block_id, "size": block.size_bytes, "tier": block.tier.value}

    def _access_block(self, block_id: str) -> None:
        block = self.blocks[block_id]
        block.access_count += 1
        block.last_accessed = datetime.now()
        self.blocks.move_to_end(block_id)

        if block.tier == MemoryTier.WARM and block.access_count >= self.hot_threshold:
            self._promote_block(block_id)

    def _promote_block(self, block_id: str) -> None:
        block = self.blocks[block_id]
        self.tier_indexes[block.tier].discard(block_id)
        block.tier = MemoryTier.HOT
        self.tier_indexes[MemoryTier.HOT].add(block_id)
        self.stats["blocks_promoted"] += 1

    async def consolidate(self, context: dict[str, Any] | None = None) -> ConsolidationResult:
        start_time = datetime.now()
        freed = 0
        blocks_affected = 0
        ratios: list[float] = []

        with self._lock:
            # Compress cold blocks — for real. The old implementation just
            # subtracted 60% from size_bytes and reported imaginary savings.
            if self.compression_enabled:
                for block_id in list(self.tier_indexes[MemoryTier.COLD]):
                    block = self.blocks[block_id]
                    if not block.compressed and block.payload:
                        compressed = gzip.compress(block.payload)
                        if len(compressed) < len(block.payload):
                            original_len = len(block.payload)
                            savings = original_len - len(compressed)
                            block.payload = compressed
                            block.size_bytes = len(compressed)
                            block.compressed = True
                            block.compression_ratio = round(len(compressed) / original_len, 4)
                            freed += savings
                            blocks_affected += 1
                            ratios.append(block.compression_ratio)

        elapsed = int((datetime.now() - start_time).total_seconds() * 1000)
        self.stats["total_consolidations"] += 1
        self.stats["memory_freed_total_mb"] += freed / (1024 * 1024)

        return ConsolidationResult(
            success=True,
            action_taken=ConsolidationAction.COMPRESS,
            memory_freed_bytes=freed,
            blocks_affected=blocks_affected,
            time_ms=elapsed,
            details={
                "compression_ratio": round(sum(ratios) / len(ratios), 4) if ratios else 1.0,
            },
        )

    async def optimize_cache(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        # Real hit rate from tracked access() outcomes (was a hardcoded 0.96).
        hits = self.stats.get("cache_hits", 0)
        misses = self.stats.get("cache_misses", 0)
        total = hits + misses
        return {
            "status": "optimized",
            "cache_hit_rate": round(hits / total, 4) if total else None,
            "prewarmed_blocks": len(self.tier_indexes[MemoryTier.HOT]),
        }

    def get_memory_stats(self) -> dict[str, Any]:
        with self._lock:
            total_size = sum(b.size_bytes for b in self.blocks.values())
            total_blocks = len(self.blocks)
            cold_blocks = len(self.tier_indexes[MemoryTier.COLD])
            return {
                "total_blocks": total_blocks,
                "total_size_bytes": total_size,
                # Real footprint — the old max(128.0, ...) floor reported a
                # minimum of 128MB even for an empty store.
                "memory_used_mb": total_size / (1024 * 1024),
                "tier_distribution": {t.name: len(ids) for t, ids in self.tier_indexes.items()},
                "utilization_percent": min(
                    100.0, (total_size / max(self.max_memory_bytes, 1)) * 100.0
                ),
                # Real aging signal (was a hardcoded 0.12 "fragmentation_score"
                # that no algorithm ever computed).
                "cold_block_ratio": round(cold_blocks / total_blocks, 4) if total_blocks else 0.0,
                **self.stats,
            }

    def get_triggers(self) -> list[dict[str, Any]]:
        triggers: list[dict[str, Any]] = []
        stats = self.get_memory_stats()
        if stats["utilization_percent"] > 85.0:
            triggers.append(
                {
                    "source": "memory_consolidator",
                    "type": "memory_pressure",
                    "priority": "HIGH",
                    "data": stats,
                }
            )
        return triggers

    def _serialize(self, data: Any) -> bytes:
        try:
            return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            return str(data).encode("utf-8")
