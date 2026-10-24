"""core/skills/skill_dispatcher.py — Universal task→skill resolver (Infinity plan Way 13).

বাংলা: নির্দিষ্ট agent-type-কেন্দ্রিক স্থাপত্য থেকে skill-কেন্দ্রিক স্থাপত্যে সেতু।
Agent = task worker; Skill = reusable method. এই মডিউলটি task description থেকে
সবচেয়ে প্রাসঙ্গিক skill বেছে দেয় (existing SkillRegistry-র উপরে পাতলা স্তর)।

Design (plan Way 13, "reuse 80% existing code"):
- Reads the SAME manifests the SkillRegistry already discovers — zero new sources
  of truth, zero registry status flips (P3 shape-preserving).
- Scoring = deterministic TF (term frequency in task) × IDF (inverse manifest
  frequency across the skill corpus) over name + description + capability tokens.
  No embeddings, no network, stdlib-only → safe to import anywhere in core/.
- Fail-open: no manifests / empty corpus → empty result rather than an exception,
  so callers keep working agent-centric as before.
- Tie-break: score desc, then lexicographic skill_id (deterministic).

Verification hook (plan evidence "skill resolution tests"):
    pytest tests/test_skill_dispatcher.py

Usage:
    from core.skills.skill_dispatcher import SkillDispatcher
    d = SkillDispatcher()                      # discovers via SkillRegistry
    m = d.resolve_best("summarize the core docs")   # -> SkillDispatch | None
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # reuse the existing registry — never duplicate it (P3)
    from core.skills.skill_registry import SkillRegistry
except ImportError:  # pragma: no cover - direct-import fallback (repo-root runs)
    from skills.skill_registry import SkillRegistry  # type: ignore[no-redef]

_WORD_RE = re.compile(r"[a-z0-9_]{2,}")

# Domain stopwords that carry no discriminative signal for skill matching.
_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
    "this", "that", "it", "is", "are", "be", "as", "at", "by", "from", "up",
    "please", "can", "you", "me", "my", "we", "our", "do", "does", "did",
    "task", "job", "work", "need", "want", "help", "make", "made", "get",
}


@dataclass(frozen=True, slots=True)
class SkillDispatch:
    """Result of resolving a task against the skill corpus."""

    skill_id: str
    score: float
    matched_terms: tuple[str, ...] = field(default=())
    runner: str | None = None  # manifest-declared entrypoint, if any

    @property
    def matched(self) -> bool:
        return bool(self.skill_id) and self.score > 0.0


class SkillDispatcher:
    """Resolves a natural-language task to the most relevant registered skill.

    বাংলা: task-এর টোকেন ও skill-ম্যানিফেস্টের টোকেনের TF-IDF মিল থেকে
    deterministic স্কোর বের করে; threshold-এর নিচে হলে মিল নেই বলে দেয়।
    """

    MIN_SCORE = 0.08  # calibrated so 1 rare-term hit on a 10-skill corpus clears

    def __init__(self, manifests_path: Path | None = None) -> None:
        self._registry = (
            SkillRegistry(manifests_path) if manifests_path is not None else SkillRegistry()
        )
        self._skills: dict[str, dict[str, Any]] = {}
        self._idf: dict[str, float] = {}
        self._tokens: dict[str, set[str]] = {}
        self._refresh()

    # ------------------------------------------------------------------ index
    def _refresh(self) -> None:
        """(Re)build the inverted index from the registry's own discovery."""
        discovered = self._registry.discover_skills() or {}
        self._skills = dict(discovered)
        self._tokens = {sid: self._tokenize_skill(m) for sid, m in self._skills.items()}
        n = max(len(self._skills), 1)
        df: dict[str, int] = {}
        for toks in self._tokens.values():
            for t in toks:
                df[t] = df.get(t, 0) + 1
        # Smoothed IDF: rare manifest terms dominate, common terms dampen.
        self._idf = {t: math.log((1.0 + n) / (1.0 + c)) + 1.0 for t, c in df.items()}

    @staticmethod
    def _tokenize_skill(manifest: dict[str, Any]) -> set[str]:
        """Flatten a skill manifest into its matchable token set.

        বাংলা: নাম + বর্ণনা + ক্যাপাবিলিটি/ট্যাগ — সব একসাথে টোকেনাইজ।
        """
        parts: list[str] = []
        for key in ("id", "name", "title", "description", "summary"):
            v = manifest.get(key)
            if isinstance(v, str):
                parts.append(v)
        for key in ("capabilities", "tags", "keywords", "triggers"):
            v = manifest.get(key)
            if isinstance(v, list):
                parts.extend(str(x) for x in v)
            elif isinstance(v, str):
                parts.append(v)
        blob = " ".join(parts).lower().replace("-", " ").replace("_", " ")
        return {t for t in _WORD_RE.findall(blob) if t not in _STOP}

    # ----------------------------------------------------------------- public
    @property
    def skill_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._skills))

    def reload(self) -> None:
        """Re-discover manifests (safe to call after skill installs)."""
        self._refresh()

    def resolve(self, task: str, top_k: int = 1) -> list[SkillDispatch]:
        """Return the top_k best-matching skills for *task*, best first.

        বাংলা: task টোকেনের TF × ম্যানিফেস্ট IDF — স্কোর ডিসেন্ডিং; deterministic।
        """
        if not task or not self._skills:
            return []
        task_tokens = [t for t in _WORD_RE.findall(task.lower()) if t not in _STOP]
        if not task_tokens:
            return []

        tf: dict[str, int] = {}
        for t in task_tokens:
            tf[t] = tf.get(t, 0) + 1

        scored: list[tuple[float, str, tuple[str, ...]]] = []
        for sid, skill_tokens in self._tokens.items():
            score = 0.0
            matched: list[str] = []
            for tok, freq in tf.items():
                if tok in skill_tokens:
                    idf = self._idf.get(tok, 1.0)
                    score += (1.0 + math.log(freq)) * idf
                    matched.append(tok)
            if score > 0.0:
                # Normalise by task length so long verbose tasks don't inflate.
                scored.append((score / math.sqrt(len(task_tokens)), sid, tuple(matched)))

        scored.sort(key=lambda x: (-x[0], x[1]))
        out: list[SkillDispatch] = []
        for sc, sid, matched in scored[: max(1, top_k)]:
            manifest = self._skills.get(sid) or {}
            runner = manifest.get("entrypoint") or manifest.get("runner")
            out.append(
                SkillDispatch(
                    skill_id=sid,
                    score=round(sc, 6),
                    matched_terms=matched,
                    runner=str(runner) if runner else None,
                )
            )
        return out

    def resolve_best(self, task: str) -> SkillDispatch | None:
        """Best match above MIN_SCORE, else None (agent-centric fallback)."""
        best = self.resolve(task, top_k=1)
        if best and best[0].score >= self.MIN_SCORE:
            return best[0]
        return None
