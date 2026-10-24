"""backend/core/intelligence/playground_runner.py — Real-time Playground Sandboxing.

বাংলা মন্তব্য (#2707, Gap-H): স্যান্ডবক্স primitive গুলো (MicroVMSandbox,
DockerSandbox, cloud orchestrator) আগে থেকেই REAL ছিল — কিন্তু "playground
pattern" (N-টি parallel candidate → স্যান্ডবক্সে test → শুধু বিজয়ী merge)
কোথাও বাস্তবায়িত ছিল না। এই মডিউল সেই অনুপস্থিত অর্ধেক:

1. ``generate_test_select(candidates, task)`` — সব candidate ``asyncio.gather``
   দিয়ে parallel-ভাবে আসল স্যান্ডবক্সে (``execute_code_securely`` — AST
   gate + Firecracker/gVisor/Docker) চলে;
2. প্রতিটির আসল execution-output parse করে deterministic score;
3. সর্বোচ্চ score-এর candidate-ই winner — কোনো hardcode নয়;
4. স্যান্ডবক্স unavailable হলে সৎ ``verified_in_sandbox=False`` (Honesty over
   polish — ভান-verification নিষিদ্ধ, False-Assurance Ban)।
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.logging_config import logger

# বাংলা মন্তব্য: স্কোরিং-ওয়েট — এক জায়গায় টিউনযোগ্য; deterministic (no LLM)।
_W_SUCCESS = 50.0
_W_CONFIDENCE = 50.0
_MAX_CANDIDATES = 8  # বাংলা: parallel-ক্যাপ — free-tier রিসোর্স-গার্ড (Rule #2)


@dataclass
class PlaygroundCandidate:
    """বাংলা মন্তব্য: একটি executable candidate — label + স্যান্ডবক্সে চলার মতো কোড।"""

    label: str
    code: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaygroundResult:
    """বাংলা মন্তব্য: একটি candidate-এর আসল স্যান্ডবক্স-রান ফলাফল।"""

    label: str
    executed: bool
    ok: bool
    score: float
    output: str = ""
    error: str = ""
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "executed": self.executed,
            "ok": self.ok,
            "score": self.score,
            "output": self.output[:500],
            "error": self.error[:300],
            "execution_time_ms": self.execution_time_ms,
        }


class PlaygroundRunner:
    """N parallel candidates → real sandbox → deterministic score → winner।"""

    def __init__(
        self,
        executor: Callable[..., Any] | None = None,
        per_candidate_timeout: float = 15.0,
    ) -> None:
        # বাংলা মন্তব্য: executor injectable — টেস্টে নকল-স্যান্ডবক্স বসানো যায়;
        # ডিফল্ট None মানে আসল execute_code_securely ব্যবহার হবে।
        self._executor = executor
        self.per_candidate_timeout = per_candidate_timeout

    async def _run_candidate(self, candidate: PlaygroundCandidate) -> PlaygroundResult:
        """বাংলা মন্তব্য: একটি candidate আসল স্যান্ডবক্সে চালানো + deterministic score।"""
        started = asyncio.get_event_loop().time()
        executed = False
        ok = False
        output = ""
        error = ""
        confidence = 0.0

        try:
            if self._executor is not None:
                result = await asyncio.wait_for(
                    self._executor(candidate.code), timeout=self.per_candidate_timeout
                )
            else:
                from core.microvm_sandbox import execute_code_securely

                result = await asyncio.wait_for(
                    execute_code_securely(candidate.code, timeout=int(self.per_candidate_timeout)),
                    timeout=self.per_candidate_timeout + 5.0,
                )

            executed = bool(result.get("success", False))
            output = str(result.get("output") or result.get("stdout") or "")
            error = str(result.get("error") or result.get("stderr") or "")

            # বাংলা মন্তব্য: candidate-চুক্তি — stdout-এ JSON verdict
            # {"ok": bool, "confidence": float}; আসল output থেকে parse।
            verdict = _parse_verdict(output)
            if verdict is not None:
                ok = bool(verdict.get("ok"))
                confidence = float(verdict.get("confidence") or 0.0)
            else:
                ok = executed and bool(output.strip())
        except TimeoutError:
            error = f"candidate timed out after {self.per_candidate_timeout}s"
        except Exception as exc:
            error = f"sandbox execution error: {str(exc)[:200]}"

        # বাংলা মন্তব্য: deterministic score — সফল-execution ভিত্তি + candidate-নিজের
        # ঘোষিত confidence (আসল output থেকে); কোনো hardcode/winner-পূর্বনির্ধারণ নেই।
        score = 0.0
        if executed and ok:
            score = _W_SUCCESS + _W_CONFIDENCE * max(0.0, min(1.0, confidence))
        elif executed:
            score = _W_SUCCESS / 2.0

        elapsed_ms = (asyncio.get_event_loop().time() - started) * 1000.0
        return PlaygroundResult(
            label=candidate.label,
            executed=executed,
            ok=ok,
            score=score,
            output=output,
            error=error,
            execution_time_ms=round(elapsed_ms, 2),
        )

    async def generate_test_select(
        self, candidates: list[PlaygroundCandidate], task: str
    ) -> dict[str, Any]:
        """#2707 API: ``generate_test_select(candidates, task) -> winner``।

        ফলাফল-চুক্তি (সব ক্ষেত্রে সৎ):
        - ``winner``: সর্বোচ্চ-score candidate (আসল স্যান্ডবক্স-ফল থেকে) বা None;
        - ``verified_in_sandbox``: winner সত্যিই স্যান্ডবক্সে ok-হলেই True;
        - ``results``: প্রতিটি candidate-এর বিস্তারিত ফল;
        - স্যান্ডবক্স unavailable → সব failed + reason (কোনো ভান-সাফল্য নয়)।
        """
        bounded = (candidates or [])[:_MAX_CANDIDATES]
        if not bounded:
            return {
                "task": task,
                "winner": None,
                "verified_in_sandbox": False,
                "results": [],
                "reason": "no_candidates",
            }

        # বাংলা মন্তব্য: THE playground pattern — N candidate parallel স্যান্ডবক্সে।
        results = await asyncio.gather(
            *(self._run_candidate(c) for c in bounded), return_exceptions=True
        )
        resolved: list[PlaygroundResult] = []
        for candidate, res in zip(bounded, results, strict=True):
            if isinstance(res, BaseException):
                logger.debug(f"[PlaygroundRunner] candidate '{candidate.label}' crashed: {res}")
                resolved.append(
                    PlaygroundResult(
                        label=candidate.label,
                        executed=False,
                        ok=False,
                        score=0.0,
                        error=f"exception: {str(res)[:200]}",
                    )
                )
            else:
                resolved.append(res)

        # বাংলা মন্তব্য: winner = আসল স্কোর-সর্বোচ্চ; tie হলে প্রথম (stable)।
        winner_result: PlaygroundResult | None = None
        for res in resolved:
            if (
                res.executed
                and res.ok
                and (winner_result is None or res.score > winner_result.score)
            ):
                winner_result = res

        winner_label = winner_result.label if winner_result else None
        return {
            "task": task,
            "winner": winner_label,
            "verified_in_sandbox": winner_result is not None,
            "winner_score": winner_result.score if winner_result else 0.0,
            "results": [r.to_dict() for r in resolved],
            "reason": ("ok" if winner_result else _unavailable_reason(resolved)),
        }


def _parse_verdict(output: str) -> dict[str, Any] | None:
    """বাংলা মন্তব্য: candidate-আউটপুট থেকে JSON verdict বের করা (দয়া করে শেষ লাইন)।"""
    if not output:
        return None
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            if isinstance(data, dict) and ("ok" in data or "confidence" in data):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _unavailable_reason(results: list[PlaygroundResult]) -> str:
    """বাংলা মন্তব্য: কেন কোনো winner নেই — সৎ কারণ-শ্রেণি।"""
    if results and all("unavailable" in (r.error or "").lower() for r in results):
        return "sandbox_unavailable"
    if results and all(not r.executed for r in results):
        return "all_candidates_failed_execution"
    return "no_candidate_passed"


# বাংলা মন্তব্য: মডিউল-স্তরের singleton — dispatcher/production পথ একটাই runner শেয়ার করে।
_playground_runner: PlaygroundRunner | None = None


def get_playground_runner() -> PlaygroundRunner:
    global _playground_runner
    if _playground_runner is None:
        _playground_runner = PlaygroundRunner()
    return _playground_runner
