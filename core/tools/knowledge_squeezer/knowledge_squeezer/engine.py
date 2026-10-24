from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .models import Candidate, Critique, KnowledgeArtifact, SqueezeResult
from .prompts import (
    AUDITOR_SYSTEM,
    FIRST_PRINCIPLES_SYSTEM,
    GENERATOR_SYSTEM,
    SOCRATIC_SYSTEM,
    SYNTHESIZER_SYSTEM,
)
from .providers import LLMProvider
from .scoring import score_artifact


@dataclass
class SqueezeConfig:
    min_candidates: int = 3
    min_final_score: float = 0.72
    max_concurrency: int = 6
    max_retries: int = 2
    require_evidence: bool = True


MemoryWriter = Callable[[KnowledgeArtifact], Awaitable[bool]]


class KnowledgeSqueezer:
    def __init__(
        self,
        providers: list[LLMProvider],
        *,
        config: SqueezeConfig | None = None,
        memory_writer: MemoryWriter | None = None,
    ) -> None:
        if not providers:
            raise ValueError("KnowledgeSqueezer requires at least one provider")
        self.providers = providers
        self.config = config or SqueezeConfig()
        self.memory_writer = memory_writer
        self._sem = asyncio.Semaphore(self.config.max_concurrency)

    async def _call(self, provider: LLMProvider, system: str, user: str) -> str:
        async with self._sem:
            last_error: Exception | None = None
            for attempt in range(self.config.max_retries + 1):
                try:
                    return await provider.complete(system, user)
                except Exception as exc:
                    last_error = exc
                    if attempt < self.config.max_retries:
                        await asyncio.sleep(0.5 * (2 ** attempt))
            raise RuntimeError(f"{provider.name} failed after retries") from last_error

    async def _parallel(self, jobs: list[tuple[LLMProvider, str, str]]) -> list[str]:
        return await asyncio.gather(*(self._call(*job) for job in jobs), return_exceptions=False)

    async def squeeze(self, topic: str, *, context: str = "", domain: str = "general") -> SqueezeResult:
        candidate_jobs = [
            (
                provider,
                GENERATOR_SYSTEM,
                f"TOPIC: {topic}\nDOMAIN: {domain}\nCONTEXT:\n{context}\n\nGenerate your strongest independent analysis.",
            )
            for provider in self.providers
        ]
        raw_candidates = await self._parallel(candidate_jobs)
        candidates = [
            Candidate(model=p.name, role="generator", content=c)
            for p, c in zip(self.providers, raw_candidates)
        ]

        audit_jobs: list[tuple[LLMProvider, str, str]] = []
        for provider in self.providers:
            for idx, candidate in enumerate(candidates):
                audit_jobs.append(
                    (
                        provider,
                        AUDITOR_SYSTEM,
                        f"TOPIC: {topic}\nCANDIDATE {idx} FROM {candidate.model}:\n{candidate.content}\n\nAudit this independently.",
                    )
                )
        raw_critiques = await self._parallel(audit_jobs)
        critiques = [
            Critique(
                model=self.providers[i % len(self.providers)].name,
                role="auditor",
                content=text,
            )
            for i, text in enumerate(raw_critiques)
        ]

        socratic_jobs = [
            (
                provider,
                SOCRATIC_SYSTEM,
                "TOPIC: " + topic + "\n\nCANDIDATES:\n"
                + "\n---\n".join(c.content for c in candidates)
                + "\n\nCRITIQUES:\n"
                + "\n---\n".join(c.content for c in critiques)
                + "\n\nMine the highest-impact hidden gaps.",
            )
            for provider in self.providers
        ]
        gaps_raw = await self._parallel(socratic_jobs)

        fp_jobs = [
            (
                provider,
                FIRST_PRINCIPLES_SYSTEM,
                f"TOPIC: {topic}\nDOMAIN: {domain}\nCANDIDATES:\n"
                + "\n---\n".join(c.content for c in candidates)
                + "\n\nReconstruct the answer from first principles.",
            )
            for provider in self.providers
        ]
        fp_raw = await self._parallel(fp_jobs)

        synthesis_prompt = {
            "topic": topic,
            "domain": domain,
            "candidates": [c.content for c in candidates],
            "critiques": [c.content for c in critiques],
            "socratic_gaps": gaps_raw,
            "first_principles": fp_raw,
            "schema": {
                "title": "string",
                "claim": "string",
                "solution": "string",
                "assumptions": ["string"],
                "invariants": ["string"],
                "failure_modes": ["string"],
                "counterarguments": ["string"],
                "evidence": ["string"],
                "confidence": "number 0..1",
                "verification_status": "unverified|reviewed|verified",
                "tags": ["string"]
            },
            "instruction": "Return ONLY one JSON object matching schema. Never fabricate citations."
        }

        synth_provider = max(self.providers, key=lambda p: (
            1 if "deepseek" in p.name.lower() else 0,
            1 if "anthropic" in p.name.lower() else 0,
        ))
        synthesized = await self._call(
            synth_provider,
            SYNTHESIZER_SYSTEM,
            json.dumps(synthesis_prompt, ensure_ascii=False),
        )
        artifact = self._parse_artifact(synthesized, topic=topic, domain=domain, candidates=candidates)

        contradiction_count = self._estimate_contradictions(candidates)
        evidence_count = len(artifact.evidence)
        novelty = self._estimate_novelty(artifact, candidates)
        score = score_artifact(
            candidate_count=len(candidates),
            critique_count=len(critiques),
            gap_count=len(gaps_raw),
            contradiction_count=contradiction_count,
            evidence_count=evidence_count,
            novelty=novelty,
            verification=0.0,
        )

        artifact.confidence = min(artifact.confidence, score.overall)
        promotion_eligible = (
            score.overall >= self.config.min_final_score
            and (not self.config.require_evidence or evidence_count > 0)
        )

        if promotion_eligible and self.memory_writer is not None:
            written = await self.memory_writer(artifact)
            artifact.verification_status = "verified" if written else "reviewed"

        return SqueezeResult(
            topic=topic,
            candidates=candidates,
            critiques=critiques,
            gaps=gaps_raw,
            artifact=artifact,
            promotion_eligible=promotion_eligible,
            score_breakdown=score.as_dict(),
        )

    @staticmethod
    def _parse_artifact(raw: str, *, topic: str, domain: str, candidates: list[Candidate]) -> KnowledgeArtifact:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.removeprefix("json")
        try:
            data: dict[str, Any] = json.loads(cleaned)
        except json.JSONDecodeError:
            data = {
                "title": topic,
                "claim": "Synthesis could not be structurally parsed.",
                "solution": raw,
                "assumptions": [],
                "invariants": [],
                "failure_modes": ["Structured synthesis parse failure"],
                "counterarguments": [],
                "evidence": [],
                "confidence": 0.2,
                "verification_status": "unverified",
                "tags": [],
            }
        return KnowledgeArtifact(
            title=str(data.get("title", topic)),
            domain=domain,
            claim=str(data.get("claim", "")),
            solution=str(data.get("solution", "")),
            assumptions=list(data.get("assumptions", [])),
            invariants=list(data.get("invariants", [])),
            failure_modes=list(data.get("failure_modes", [])),
            counterarguments=list(data.get("counterarguments", [])),
            evidence=list(data.get("evidence", [])),
            confidence=float(data.get("confidence", 0.0)),
            verification_status=str(data.get("verification_status", "unverified")),
            tags=list(data.get("tags", [])),
            provenance=[{"model": c.model, "role": c.role} for c in candidates],
        )

    @staticmethod
    def _estimate_contradictions(candidates: list[Candidate]) -> int:
        # Conservative heuristic. Replace with a semantic contradiction classifier in production.
        markers = ("however", "contradict", "wrong", "cannot", "not true", "false")
        hits = sum(any(m in c.content.lower() for m in markers) for c in candidates)
        return max(0, hits - 1)

    @staticmethod
    def _estimate_novelty(artifact: KnowledgeArtifact, candidates: list[Candidate]) -> float:
        text = artifact.claim.lower().split()
        if not text:
            return 0.0
        unique = len(set(text)) / len(text)
        return max(0.0, min(1.0, unique))
