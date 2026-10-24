"""Zero-token content deduplication engine (Exact SHA-256 + Jaccard Similarity)."""

from __future__ import annotations

import hashlib
import re


class ContentDeduplicator:
    """Detects exact and near-duplicate web content without using AI tokens or external APIs."""

    def __init__(self, similarity_threshold: float = 0.80) -> None:
        self.similarity_threshold = similarity_threshold
        self._exact_hashes: set[str] = set()
        self._signatures: list[tuple[str, set[tuple[str, str, str]]]] = []

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Lowercases and cleans whitespace from text."""
        return re.sub(r"\s+", " ", text.lower()).strip()

    @classmethod
    def compute_hash(cls, text: str) -> str:
        """Returns the SHA-256 hex digest of normalized content."""
        normalized = cls._normalize_text(text)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def _create_3shingles(cls, text: str) -> set[tuple[str, str, str]]:
        """Splits normalized text into 3-word shingles for near-duplicate comparison."""
        words = re.findall(r"\b\w+\b", cls._normalize_text(text))
        if len(words) < 3:
            return {(w, "", "") for w in words}
        return {tuple(words[i : i + 3]) for i in range(len(words) - 2)}  # type: ignore

    @staticmethod
    def jaccard_similarity(
        shingles_a: set[tuple[str, str, str]], shingles_b: set[tuple[str, str, str]]
    ) -> float:
        """Computes Jaccard similarity between two sets of shingles."""
        if not shingles_a or not shingles_b:
            return 0.0
        intersection = len(shingles_a & shingles_b)
        union = len(shingles_a | shingles_b)
        if union == 0:
            return 0.0
        return intersection / union

    def is_duplicate(self, text: str) -> bool:
        """Checks if text is an exact or near-duplicate of previously seen content."""
        if not text or not text.strip():
            return True

        h = self.compute_hash(text)
        if h in self._exact_hashes:
            return True

        shingles = self._create_3shingles(text)
        if not shingles:
            return False

        for _, seen_shingles in self._signatures:
            similarity = self.jaccard_similarity(shingles, seen_shingles)
            if similarity >= self.similarity_threshold:
                return True

        return False

    def record_content(self, text: str) -> tuple[str, bool]:
        """Checks and records text.

        Returns (content_hash, is_duplicate).
        If not duplicate, registers the fingerprint for subsequent comparisons.
        """
        if not text or not text.strip():
            return "", True

        h = self.compute_hash(text)
        if h in self._exact_hashes:
            return h, True

        shingles = self._create_3shingles(text)
        for _, seen_shingles in self._signatures:
            if self.jaccard_similarity(shingles, seen_shingles) >= self.similarity_threshold:
                return h, True

        # Unique content: store fingerprints
        self._exact_hashes.add(h)
        self._signatures.append((h, shingles))
        return h, False

    def reset(self) -> None:
        """Clears seen content state for a new task session."""
        self._exact_hashes.clear()
        self._signatures.clear()
