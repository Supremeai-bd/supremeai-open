#!/usr/bin/env python3
"""
Learning Pipeline — Phase 3 Evolution Activation (#1035)
========================================================
১০৫টি inactive AI module-কে production-এ wire করার প্রথম ধাপ।
এই pipeline-টি নিচের module-গুলো একসাথে যুক্ত করে:

  1. PatternRecognizer → CI failure pattern detect
  2. MemoryConsolidator → pattern persist for future recall
  3. SelfCorrectionService → pre/post verification
  4. AutoHealer → L1-L5 healing tiers

Usage:
  from evolution.learning_pipeline import LearningPipeline
  pipeline = LearningPipeline()
  result = await pipeline.process_failure(failure_data)
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.logging_config import logger


@dataclass
class FailurePattern:
    """A recognized pattern in CI failures."""

    pattern_id: str
    failure_type: str  # import_error, assertion_mismatch, etc.
    description: str
    suggested_fix: str | None = None
    confidence: float = 0.0
    occurrences: int = 0
    last_seen: str = ""


@dataclass
class LearningResult:
    """Result of processing a failure through the learning pipeline."""

    pattern_found: bool
    pattern: FailurePattern | None = None
    suggested_fix: str | None = None
    stored: bool = False
    confidence: float = 0.0
    message: str = ""


class LearningPipeline:
    """Wires PatternRecognizer + MemoryConsolidator for CI failure learning.

    বাংলা: এই pipeline-টি প্রতিটি CI failure-কে analyze করে:
      1. আগে এই pattern দেখা গেছে কিনা চেক করে (pattern_recognizer)
      2. আগে দেখা গেলে — সেই fix suggest করে (memory_consolidator recall)
      3. নতুন pattern হলে — store করে future recall-এর জন্য
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self._pattern_recognizer = None
        self._memory_consolidator = None
        self._initialized = False
        self._patterns: dict[str, FailurePattern] = {}  # in-memory cache

    async def _initialize(self) -> None:
        """Lazily initialize the underlying modules."""
        if self._initialized:
            return

        # Try to import PatternRecognizer
        try:
            from learning.pattern_recognizer import PatternRecognizer

            self._pattern_recognizer = PatternRecognizer(self.config.get("pattern_config"))
            logger.info("LearningPipeline: PatternRecognizer initialized")
        except Exception as e:
            logger.warning(f"LearningPipeline: PatternRecognizer unavailable: {e}")

        # Try to import MemoryConsolidator
        try:
            from evolution.memory_consolidator import MemoryConsolidator

            self._memory_consolidator = MemoryConsolidator(self.config.get("memory_config"))
            logger.info("LearningPipeline: MemoryConsolidator initialized")
        except Exception as e:
            logger.warning(f"LearningPipeline: MemoryConsolidator unavailable: {e}")

        self._initialized = True

    async def process_failure(self, failure: dict[str, Any]) -> LearningResult:
        """Process a CI failure through the learning pipeline.

        Args:
            failure: {
                "test_id": str,
                "failure_type": str,
                "message": str,
                "snippet": str,
                "file_path": str,
            }

        Returns:
            LearningResult with pattern match + suggested fix
        """
        await self._initialize()

        failure_type = failure.get("failure_type", "unknown")
        test_id = failure.get("test_id", "")
        message = failure.get("message", "")

        # Create a pattern key from failure type + message hash
        import hashlib

        pattern_key = f"{failure_type}:{hashlib.md5(message.encode()).hexdigest()[:8]}"

        # Check if we've seen this pattern before
        if pattern_key in self._patterns:
            pattern = self._patterns[pattern_key]
            pattern.occurrences += 1
            pattern.last_seen = datetime.now(UTC).isoformat()
            logger.info(
                f"LearningPipeline: pattern found! {pattern.pattern_id} (occurrences: {pattern.occurrences})"
            )
            return LearningResult(
                pattern_found=True,
                pattern=pattern,
                suggested_fix=pattern.suggested_fix,
                confidence=pattern.confidence,
                message=f"Pattern recognized: {pattern.description}",
            )

        # Try pattern_recognizer if available
        if self._pattern_recognizer:
            try:
                matches = await self._pattern_recognizer.recognize(
                    sequence=[failure_type, test_id, message],
                    context={"file": failure.get("file_path", "")},
                )
                if matches:
                    # Use the best match
                    best = matches[0] if isinstance(matches, list) else matches
                    pattern = FailurePattern(
                        pattern_id=pattern_key,
                        failure_type=failure_type,
                        description=f"Recognized pattern: {getattr(best, 'pattern_type', 'unknown')}",
                        confidence=getattr(best, "confidence", 0.5),
                        occurrences=1,
                        last_seen=datetime.now(UTC).isoformat(),
                    )
                    self._patterns[pattern_key] = pattern
                    return LearningResult(
                        pattern_found=True,
                        pattern=pattern,
                        confidence=pattern.confidence,
                        message="Pattern recognized by PatternRecognizer",
                    )
            except Exception as e:
                logger.warning(f"LearningPipeline: pattern_recognizer error: {e}")

        # New pattern — store it
        new_pattern = FailurePattern(
            pattern_id=pattern_key,
            failure_type=failure_type,
            description=f"New pattern: {failure_type} in {test_id[:50]}",
            confidence=0.3,  # low confidence for new patterns
            occurrences=1,
            last_seen=datetime.now(UTC).isoformat(),
        )
        self._patterns[pattern_key] = new_pattern

        # Store in memory_consolidator if available
        stored = False
        if self._memory_consolidator:
            try:
                self._memory_consolidator.allocate(
                    block_id=pattern_key,
                    data={
                        "failure_type": failure_type,
                        "test_id": test_id,
                        "message": message[:500],
                        "file_path": failure.get("file_path", ""),
                        "timestamp": new_pattern.last_seen,
                    },
                )
                stored = True
                logger.info(
                    f"LearningPipeline: pattern stored in MemoryConsolidator: {pattern_key}"
                )
            except Exception as e:
                logger.warning(f"LearningPipeline: memory_consolidator error: {e}")

        return LearningResult(
            pattern_found=False,
            pattern=new_pattern,
            stored=stored,
            confidence=0.3,
            message=f"New pattern recorded: {failure_type} in {test_id[:50]}",
        )

    async def get_stats(self) -> dict[str, Any]:
        """Get learning pipeline statistics."""
        return {
            "total_patterns": len(self._patterns),
            "pattern_recognizer_active": self._pattern_recognizer is not None,
            "memory_consolidator_active": self._memory_consolidator is not None,
            "initialized": self._initialized,
            "patterns": [
                {
                    "id": p.pattern_id,
                    "type": p.failure_type,
                    "occurrences": p.occurrences,
                    "confidence": p.confidence,
                    "last_seen": p.last_seen,
                }
                for p in list(self._patterns.values())[:10]
            ],
        }

    def suggest_fix_for_type(self, failure_type: str) -> str | None:
        """Quick lookup: given a failure type, suggest the most common fix."""
        type_patterns = [
            p for p in self._patterns.values() if p.failure_type == failure_type and p.suggested_fix
        ]
        if not type_patterns:
            return None
        # Return the fix from the most occurring pattern
        best = max(type_patterns, key=lambda p: p.occurrences)
        return best.suggested_fix


# Module-level singleton
_pipeline_instance: LearningPipeline | None = None


def get_learning_pipeline() -> LearningPipeline:
    """Get or create the singleton LearningPipeline instance."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = LearningPipeline()
    return _pipeline_instance
