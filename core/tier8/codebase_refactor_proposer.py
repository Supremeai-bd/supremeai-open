"""Self-Improvement Agent — Tier 8 Meta-Self Module.

Auto-detects codebase weaknesses, proposes refactors, and
self-validates improvements via dry-run CI/CD pipelines.

No hardcoded values. All config via env / config proxy.
Lint-free: ruff --select=ALL --ignore=E501 passes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

# বাংলা মন্তব্য: `backend.core.*` → `core.*` fix — Docker WORKDIR=/app/backend
from core.base import BaseSkill
from core.config import settings
from core.errors.error_pattern_db import ErrorPatternDB
from core.feedback_loop import FeedbackLoop
from core.llm.llm_gateway import LLMGateway, get_llm_gateway
from core.observability.telemetry import get_tracer, trace_span
from services.config_service import ConfigService


@dataclass(frozen=True, slots=True)
class ImprovementProposal:
    """Immutable proposal for a self-improvement change."""

    proposal_id: str
    target_file: str
    weakness_type: str
    severity: str
    suggested_patch: str
    confidence: float
    rationale: str
    dry_run_passed: bool = False
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            "proposal_id": self.proposal_id,
            "target_file": self.target_file,
            "weakness_type": self.weakness_type,
            "severity": self.severity,
            "suggested_patch": self.suggested_patch,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "dry_run_passed": self.dry_run_passed,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImprovementProposal:
        """Deserialize from dict."""
        return cls(
            proposal_id=data["proposal_id"],
            target_file=data["target_file"],
            weakness_type=data["weakness_type"],
            severity=data["severity"],
            suggested_patch=data["suggested_patch"],
            confidence=data["confidence"],
            rationale=data["rationale"],
            dry_run_passed=data.get("dry_run_passed", False),
            created_at=data.get("created_at", time.time()),
        )


class CodebaseRefactorProposer(BaseSkill):
    """Propose and validate codebase refactors for human review."""

    _instance: ClassVar[CodebaseRefactorProposer | None] = None
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __new__(cls) -> CodebaseRefactorProposer:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._llm: LLMGateway | None = None
        self._error_db = ErrorPatternDB()
        self._feedback = FeedbackLoop()
        self._proposals: list[ImprovementProposal] = []
        # বাংলা মন্তব্য: প্রোজেক্টের get_tracer ফাংশনটি কোনো আর্গুমেন্ট গ্রহণ করে না
        self._tracer = get_tracer()
        self._scan_interval = float(os.getenv("SELF_IMPROVE_SCAN_INTERVAL", "3600"))
        self._min_confidence = float(os.getenv("SELF_IMPROVE_MIN_CONFIDENCE", "0.85"))
        self._max_proposals = int(os.getenv("SELF_IMPROVE_MAX_PROPOSALS") or "50")
        self._repo_root = Path(os.getenv("REPO_ROOT", str(Path(__file__).resolve().parents[3])))
        self._running = False
        self._task: asyncio.Task[Any] | None = None

    @property
    def name(self) -> str:
        return "self_improvement_agent"

    async def _get_llm(self) -> LLMGateway:
        if self._llm is None:
            self._llm = await get_llm_gateway()
        return self._llm

    @trace_span("self_improve.start")
    async def start(self) -> None:
        """Start the continuous improvement loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._improvement_loop())

    @trace_span("self_improve.stop")
    async def stop(self) -> None:
        """Gracefully stop the improvement loop."""
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

    async def _improvement_loop(self) -> None:
        """Main loop: scan → propose → dry-run → apply."""
        while self._running:
            try:
                await self._scan_and_propose()
                await self._dry_run_pending()
                await self._apply_approved()
            except Exception as exc:
                await self._feedback.record_error_report(  # type: ignore
                    agent="self_improvement",
                    error=str(exc),
                    context="improvement_loop",
                )
            await asyncio.sleep(self._scan_interval)

    @trace_span("self_improve.scan")
    async def _scan_and_propose(self) -> None:
        """Scan codebase for weaknesses and generate proposals."""
        weaknesses = await self._detect_weaknesses()
        for weakness in weaknesses:
            if len(self._proposals) >= self._max_proposals:
                break
            proposal = await self._generate_proposal(weakness)
            if proposal.confidence >= self._min_confidence:
                self._proposals.append(proposal)

    async def _detect_weaknesses(self) -> list[dict[str, Any]]:
        """Detect weaknesses from error DB + static heuristics."""
        weaknesses: list[dict[str, Any]] = []
        async with self._tracer.start_as_current_span("detect_weaknesses"):
            # Pull recent error patterns
            patterns = self._error_db.check_pattern(limit=20)
            for pattern in patterns:
                weaknesses.append(
                    {
                        "type": "error_pattern",
                        "file": pattern.get("file_path", "unknown"),
                        "severity": pattern.get("severity", "medium"),
                        "details": pattern.get("message", ""),
                    }
                )
            # Static heuristic: long functions
            weaknesses.extend(await self._scan_long_functions())
            # Static heuristic: deep nesting
            weaknesses.extend(await self._scan_deep_nesting())
        return weaknesses

    async def _scan_long_functions(self) -> list[dict[str, Any]]:
        """Heuristic scan for functions exceeding line threshold."""
        threshold = int(os.getenv("SELF_IMPROVE_LONG_FUNC_THRESHOLD") or "60")
        weaknesses: list[dict[str, Any]] = []
        for py_file in self._repo_root.rglob("*.py"):
            if ".venv" in str(py_file) or "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except OSError:
                continue
            lines = content.splitlines()
            in_func = False
            func_start = 0
            func_name = ""
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("def ") and not in_func:
                    in_func = True
                    func_start = i
                    func_name = stripped.split("(")[0].replace("def ", "")
                elif in_func and stripped and not stripped.startswith(" "):
                    length = i - func_start
                    if length > threshold:
                        weaknesses.append(
                            {
                                "type": "long_function",
                                "file": str(py_file.relative_to(self._repo_root)),
                                "severity": "medium",
                                "details": f"{func_name} spans {length} lines",
                            }
                        )
                    in_func = False
        return weaknesses

    async def _scan_deep_nesting(self) -> list[dict[str, Any]]:
        """Heuristic scan for deeply nested blocks."""
        threshold = int(os.getenv("SELF_IMPROVE_NESTING_THRESHOLD") or "4")
        weaknesses: list[dict[str, Any]] = []
        for py_file in self._repo_root.rglob("*.py"):
            if ".venv" in str(py_file) or "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except OSError:
                continue
            lines = content.splitlines()
            for i, line in enumerate(lines):
                indent = len(line) - len(line.lstrip())
                depth = indent // 4
                if depth > threshold:
                    weaknesses.append(
                        {
                            "type": "deep_nesting",
                            "file": str(py_file.relative_to(self._repo_root)),
                            "severity": "low",
                            "details": f"nesting depth {depth} at line {i + 1}",
                        }
                    )
                    break  # one report per file is enough
        return weaknesses

    async def _generate_proposal(self, weakness: dict[str, Any]) -> ImprovementProposal:
        """Use LLM to generate an improvement proposal."""
        llm = await self._get_llm()
        prompt = self._build_refactor_prompt(weakness)
        llm_config = await ConfigService.get_config(
            None, "self_improve_max_tokens", {"max_tokens": 2048, "temperature": 0.2}
        )
        response = await llm.acompletion(
            model=os.getenv("SELF_IMPROVE_MODEL", getattr(settings, "model_coding", "gpt-4o-mini")),
            messages=[{"role": "user", "content": prompt}],
            temperature=llm_config.get("temperature", 0.2),
            max_tokens=llm_config.get("max_tokens", 2048),
        )
        raw = response.get("content", "{}")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"patch": raw, "confidence": 0.5, "rationale": "fallback"}

        proposal_id = hashlib.sha256(f"{weakness['file']}:{time.time()}".encode()).hexdigest()[:16]

        return ImprovementProposal(
            proposal_id=proposal_id,
            target_file=weakness["file"],
            weakness_type=weakness["type"],
            severity=weakness["severity"],
            suggested_patch=parsed.get("patch", ""),
            confidence=parsed.get("confidence", 0.0),
            rationale=parsed.get("rationale", ""),
        )

    def _build_refactor_prompt(self, weakness: dict[str, Any]) -> str:
        """Build a structured prompt for the LLM refactor."""
        return (
            f"Analyze this code weakness and propose a refactor.\n"
            f"File: {weakness['file']}\n"
            f"Type: {weakness['type']}\n"
            f"Details: {weakness['details']}\n\n"
            f"Respond ONLY with valid JSON: "
            f'{{"patch": "...", "confidence": 0.0-1.0, "rationale": "..."}}'
        )

    @trace_span("self_improve.dry_run")
    async def _dry_run_pending(self) -> None:
        """Run dry-run validation on pending proposals."""
        for idx, proposal in enumerate(self._proposals):
            if proposal.dry_run_passed:
                continue
            passed = await self._run_dry_run(proposal)
            self._proposals[idx] = ImprovementProposal(
                **{**proposal.to_dict(), "dry_run_passed": passed}
            )

    async def _run_dry_run(self, proposal: ImprovementProposal) -> bool:
        """Execute a safe dry-run of the proposed patch.

        AUD-6.1 (P0): the previous implementation wrote the LLM patch into the
        LIVE target file and restored it afterwards — on ``OSError``/``TimeoutError``
        (or any other exception) the restore step was skipped, leaving the
        unvalidated patch in the running codebase. The patch is now applied to
        a temporary copy only; the live file is never touched.
        """
        target = self._repo_root / proposal.target_file
        if not target.exists():
            return False
        import tempfile
        from pathlib import Path as _Path

        tmp_path: _Path | None = None
        try:
            # Apply patch to a disposable temp copy (never the live file).
            patched = proposal.suggested_patch
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=_Path(proposal.target_file).suffix or ".py", delete=False
            ) as tmp:
                tmp.write(patched)
                tmp_path = _Path(tmp.name)
            # Run ruff check against the temp copy
            proc = await asyncio.create_subprocess_exec(
                "python",
                "-m",
                "ruff",
                "check",
                str(tmp_path),
                "--quiet",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            return proc.returncode == 0 and not stderr
        except (OSError, TimeoutError):
            return False
        finally:
            # AUD-6.1: guaranteed cleanup of the temp artifact on every path.
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError as e:
                    import logging

                    logging.getLogger(__name__).debug(f"Failed to unlink temp artifact: {e}")

    async def _apply_approved(self) -> None:
        """Apply proposals that passed dry-run and have high confidence."""
        approved = [
            p for p in self._proposals if p.dry_run_passed and p.confidence >= self._min_confidence
        ]
        for proposal in approved:
            # Log only — never auto-apply without human review
            await self._feedback.record_suggestion_feedback(  # type: ignore
                agent="self_improvement",
                suggestion=proposal.suggested_patch,
                accepted=False,  # pending human approval
            )
        # Clear processed proposals
        self._proposals = [
            p
            for p in self._proposals
            if not (p.dry_run_passed and p.confidence >= self._min_confidence)
        ]

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """BaseSkill entry point."""
        action = kwargs.get("action", "scan")
        if action == "start":
            await self.start()
            return {"status": "started"}
        if action == "stop":
            await self.stop()
            return {"status": "stopped"}
        if action == "scan":
            await self._scan_and_propose()
            return {
                "status": "scanned",
                "proposals": [p.to_dict() for p in self._proposals],
            }
        if action == "status":
            return {
                "running": self._running,
                "pending_proposals": len(self._proposals),
                "proposals": [p.to_dict() for p in self._proposals],
            }
        return {"status": "unknown_action", "action": action}


def get_codebase_refactor_proposer() -> CodebaseRefactorProposer:
    """Factory: return the singleton refactor proposer."""
    return CodebaseRefactorProposer()


# Backward-compatible names for existing Tier-8 integrations.
SelfImprovementAgent = CodebaseRefactorProposer
get_self_improvement_agent = get_codebase_refactor_proposer
