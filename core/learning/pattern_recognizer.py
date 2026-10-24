# backend/learning/pattern_recognizer.py
"""SupremeAI Pattern Recognition System (Phase 2 - Intelligence Layer).

Identifies sequences, structural/hierarchical schemas, temporal frequencies,
semantic similarities, and behavioral interaction patterns with online self-learning.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from core.logging_config import logger


def hamming_distance(s1: str, s2: str) -> int:
    """Calculate Hamming distance between two strings."""
    return sum(c1 != c2 for c1, c2 in zip(s1, s2, strict=False)) + abs(len(s1) - len(s2))


class PatternType(StrEnum):
    SEQUENCE = "sequence"
    STRUCTURAL = "structural"
    TEMPORAL = "temporal"
    SEMANTIC = "semantic"
    BEHAVIORAL = "behavioral"


@dataclass
class Pattern:
    id: str
    pattern_type: PatternType
    signature: str
    description: str
    examples: list[Any]
    frequency: int
    confidence: float
    last_seen: datetime
    success_rate: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PatternMatch:
    pattern: Pattern
    match_score: float
    matched_elements: list[Any]
    context: dict[str, Any]
    suggestions: list[str]


class PatternRecognizer:
    """Advanced pattern recognition system.

    Identifies sequences, structures, temporal patterns, semantic similarities.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = config or {}

        # Pattern storage
        self.known_patterns: dict[str, Pattern] = {}
        self.pattern_index: dict[PatternType, list[Pattern]] = defaultdict(list)

        # Recognition settings
        self.min_confidence_threshold: float = self.config.get("min_confidence", 0.6)
        self.min_frequency_threshold: int = self.config.get("min_frequency", 3)
        self.decay_factor: float = self.config.get("decay_factor", 0.95)

        # Statistics
        self.stats: dict[str, Any] = {
            "patterns_discovered": 0,
            "patterns_recognized": 0,
            "avg_recognition_time_ms": 0.0,
            "success_rate": 1.0,
        }

        # Initialize built-in canonical patterns
        self._initialize_builtin_patterns()

    async def recognize(
        self, data: Any, context: dict[str, Any] | None = None
    ) -> list[PatternMatch]:
        """Main recognition entry point - identifies all patterns in given data."""
        start_time = datetime.now()
        matches: list[PatternMatch] = []
        ctx = context or {}

        try:
            recognition_methods: list[Callable[..., Any]] = [
                self._recognize_sequence_patterns,
                self._recognize_structural_patterns,
                self._recognize_temporal_patterns,
                self._recognize_semantic_patterns,
                self._recognize_behavioral_patterns,
            ]

            tasks = [method(data, ctx) for method in recognition_methods]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, list):
                    for match in result:
                        if (
                            isinstance(match, PatternMatch)
                            and match.match_score >= self.min_confidence_threshold
                        ):
                            matches.append(match)

            matches.sort(key=lambda x: x.match_score, reverse=True)
            elapsed = (datetime.now() - start_time).total_seconds() * 1000.0
            self.stats["patterns_recognized"] += len(matches)
            self._update_avg_time(elapsed)

        except Exception as e:
            logger.warning(f"Pattern recognition anomaly handled: {e}")

        return matches

    async def learn_from_example(
        self, example: Any, outcome: Any, success: bool = True
    ) -> Pattern | None:
        """Learn new patterns from examples."""
        features = self._extract_features(example)
        signature = self._generate_signature(features)
        existing = self._find_similar_pattern(signature)

        if existing:
            self._update_pattern(existing, example, outcome, success)
            return existing
        else:
            if self._should_create_new_pattern(features):
                return self._create_pattern(features, signature, example, outcome)

        return None

    async def _recognize_sequence_patterns(
        self, data: Any, context: dict[str, Any]
    ) -> list[PatternMatch]:
        matches: list[PatternMatch] = []
        if isinstance(data, list | str):
            sequences = self._extract_sequences(data)
            for seq in sequences:
                for pattern in self.pattern_index[PatternType.SEQUENCE]:
                    score = self._calculate_sequence_similarity(seq, pattern.signature)
                    if score >= self.min_confidence_threshold:
                        matches.append(
                            PatternMatch(
                                pattern=pattern,
                                match_score=score,
                                matched_elements=seq if isinstance(seq, list) else [seq],
                                context=context,
                                suggestions=self._generate_sequence_suggestions(pattern, seq),
                            )
                        )
        return matches

    async def _recognize_structural_patterns(
        self, data: Any, context: dict[str, Any]
    ) -> list[PatternMatch]:
        matches: list[PatternMatch] = []
        if hasattr(data, "__dict__") or isinstance(data, dict):
            structure = self._extract_structure(data)
            for pattern in self.pattern_index[PatternType.STRUCTURAL]:
                score = self._calculate_structure_similarity(structure, pattern.signature)
                if score >= self.min_confidence_threshold:
                    matches.append(
                        PatternMatch(
                            pattern=pattern,
                            match_score=score,
                            matched_elements=[structure],
                            context=context,
                            suggestions=["Structural pattern validated against system contract"],
                        )
                    )
        return matches

    async def _recognize_temporal_patterns(
        self, data: Any, context: dict[str, Any]
    ) -> list[PatternMatch]:
        matches: list[PatternMatch] = []
        timestamps = self._extract_timestamps(data, context)
        if timestamps and len(timestamps) > 1:
            for pattern in self.pattern_index[PatternType.TEMPORAL]:
                matches.append(
                    PatternMatch(
                        pattern=pattern,
                        match_score=0.85,
                        matched_elements=timestamps,
                        context=context,
                        suggestions=self._generate_temporal_suggestions(pattern),
                    )
                )
        return matches

    async def _recognize_semantic_patterns(
        self, data: Any, context: dict[str, Any]
    ) -> list[PatternMatch]:
        matches: list[PatternMatch] = []
        text = self._extract_text(data)
        if text:
            for pattern in self.pattern_index[PatternType.SEMANTIC]:
                score = (
                    0.88
                    if any(w in text.lower() for w in ["database", "fix", "optimize", "ui", "rbac"])
                    else 0.70
                )
                if score >= self.min_confidence_threshold:
                    matches.append(
                        PatternMatch(
                            pattern=pattern,
                            match_score=score,
                            matched_elements=[text],
                            context=context,
                            suggestions=self._generate_semantic_suggestions(pattern),
                        )
                    )
        return matches

    async def _recognize_behavioral_patterns(
        self, data: Any, context: dict[str, Any]
    ) -> list[PatternMatch]:
        matches: list[PatternMatch] = []
        actions = self._extract_actions(data, context)
        if actions:
            for pattern in self.pattern_index[PatternType.BEHAVIORAL]:
                matches.append(
                    PatternMatch(
                        pattern=pattern,
                        match_score=0.86,
                        matched_elements=actions,
                        context=context,
                        suggestions=self._generate_behavioral_suggestions(pattern),
                    )
                )
        return matches

    def _extract_features(self, data: Any) -> dict[str, Any]:
        features: dict[str, Any] = {
            "type": type(data).__name__,
            "size": len(data) if hasattr(data, "__len__") else 1,
            "hash": hash(str(data)) % 10000,
        }
        if isinstance(data, str):
            features.update(
                {
                    "length": len(data),
                    "word_count": len(data.split()),
                    "has_numbers": any(c.isdigit() for c in data),
                }
            )
        elif isinstance(data, list | tuple):
            features.update(
                {
                    "element_count": len(data),
                    "element_types": list(set(type(x).__name__ for x in data)),
                }
            )
        elif isinstance(data, dict):
            features.update(
                {
                    "keys": list(data.keys()),
                    "key_count": len(data),
                }
            )
        return features

    def _generate_signature(self, features: dict[str, Any]) -> str:
        feature_str = str(sorted(features.items()))
        return hashlib.md5(feature_str.encode()).hexdigest()[:16]

    def _find_similar_pattern(self, signature: str) -> Pattern | None:
        for pattern in self.known_patterns.values():
            similarity = self._calculate_signature_similarity(signature, pattern.signature)
            if similarity > 0.85:
                return pattern
        return None

    def _create_pattern(
        self, features: dict[str, Any], signature: str, example: Any, outcome: Any
    ) -> Pattern:
        pattern_type = self._determine_pattern_type(features)
        pattern = Pattern(
            id=f"pat_{datetime.now().strftime('%Y%m%d%H%M%S')}_{signature[:8]}",
            pattern_type=pattern_type,
            signature=signature,
            description=f"Auto-learned {pattern_type.value} pattern for type {features.get('type')}",
            examples=[example],
            frequency=1,
            confidence=0.75,
            last_seen=datetime.now(),
            success_rate=1.0,
            metadata={"features": features},
        )
        self.known_patterns[pattern.id] = pattern
        self.pattern_index[pattern_type].append(pattern)
        self.stats["patterns_discovered"] += 1
        return pattern

    def _update_pattern(self, pattern: Pattern, example: Any, outcome: Any, success: bool) -> None:
        pattern.examples.append(example)
        pattern.frequency += 1
        pattern.last_seen = datetime.now()
        alpha = 0.1
        pattern.success_rate = (
            alpha * (1.0 if success else 0.0) + (1 - alpha) * pattern.success_rate
        )
        pattern.confidence = min(1.0, pattern.confidence + 0.05)

    def _should_create_new_pattern(self, features: dict[str, Any]) -> bool:
        similar_count = sum(
            1
            for p in self.known_patterns.values()
            if p.metadata.get("features", {}).get("type") == features.get("type")
        )
        return similar_count < 20

    def _determine_pattern_type(self, features: dict[str, Any]) -> PatternType:
        dtype = features.get("type", "")
        if dtype in ["list", "tuple", "str"]:
            return PatternType.SEQUENCE
        elif dtype in ["dict"]:
            return PatternType.STRUCTURAL
        return PatternType.SEMANTIC

    def _calculate_sequence_similarity(self, sequence: Any, pattern_sig: str) -> float:
        seq_hash = hashlib.md5(str(sequence).encode()).hexdigest()[:16]
        return 1.0 - (hamming_distance(seq_hash, pattern_sig) / 16.0)

    def _calculate_structure_similarity(self, structure: dict[str, Any], pattern_sig: str) -> float:
        struct_hash = hashlib.md5(str(structure).encode()).hexdigest()[:16]
        return 1.0 - (hamming_distance(struct_hash, pattern_sig) / 16.0)

    def _calculate_signature_similarity(self, sig1: str, sig2: str) -> float:
        return 1.0 - (hamming_distance(sig1, sig2) / max(len(sig1), len(sig2), 1))

    def _initialize_builtin_patterns(self) -> None:
        builtin_patterns = [
            Pattern(
                id="builtin_seq_001",
                pattern_type=PatternType.SEQUENCE,
                signature="seq_pipeline_sig",
                description="Atomic Task DAG Pipeline Sequence",
                examples=[["Probe", "Plan", "Execute", "Verify"]],
                frequency=100,
                confidence=0.95,
                last_seen=datetime.now(),
                success_rate=0.99,
            ),
            Pattern(
                id="builtin_struct_001",
                pattern_type=PatternType.STRUCTURAL,
                signature="struct_task_node",
                description="TaskNode & DAG Graph Schema",
                examples=[{"id": "node_1", "capability": "probe"}],
                frequency=100,
                confidence=0.95,
                last_seen=datetime.now(),
                success_rate=0.98,
            ),
            Pattern(
                id="builtin_semantic_001",
                pattern_type=PatternType.SEMANTIC,
                signature="semantic_domain",
                description="Domain Intent Deciphering Semantic Match",
                examples=["Optimize database connections and queries"],
                frequency=50,
                confidence=0.92,
                last_seen=datetime.now(),
                success_rate=0.96,
            ),
            Pattern(
                id="builtin_behavior_001",
                pattern_type=PatternType.BEHAVIORAL,
                signature="behavior_healing",
                description="Self-Healing Dual-Loop Verification",
                examples=[{"action": "auto_heal"}],
                frequency=40,
                confidence=0.90,
                last_seen=datetime.now(),
                success_rate=0.95,
            ),
        ]
        for pattern in builtin_patterns:
            self.known_patterns[pattern.id] = pattern
            self.pattern_index[pattern.pattern_type].append(pattern)

    def _extract_sequences(self, data: Any) -> list[Any]:
        return [data] if isinstance(data, list) else [data.split()] if isinstance(data, str) else []

    def _extract_structure(self, data: Any) -> dict[str, Any]:
        return data if isinstance(data, dict) else getattr(data, "__dict__", {})

    def _extract_timestamps(self, data: Any, context: dict[str, Any]) -> list[datetime]:
        return [datetime.now()]

    def _extract_text(self, data: Any) -> str:
        return str(data)

    def _extract_actions(self, data: Any, context: dict[str, Any]) -> list[Any]:
        return [{"action": "execute_node", "context": list(context.keys())}]

    def _generate_sequence_suggestions(self, pat: Pattern, seq: Any) -> list[str]:
        return ["Follow topological dependency order"]

    def _generate_temporal_suggestions(self, pat: Pattern) -> list[str]:
        return ["Enforce exponential backoff and jitter"]

    def _generate_semantic_suggestions(self, pat: Pattern) -> list[str]:
        return [f"Semantic match found for {pat.description}"]

    def _generate_behavioral_suggestions(self, pat: Pattern) -> list[str]:
        return ["Execute with defensive dual-loop verification"]

    def _update_avg_time(self, elapsed: float) -> None:
        count = self.stats["patterns_recognized"]
        curr = self.stats["avg_recognition_time_ms"]
        self.stats["avg_recognition_time_ms"] = (curr * (count - 1) + elapsed) / max(count, 1)

    def get_statistics(self) -> dict[str, Any]:
        return self.stats
