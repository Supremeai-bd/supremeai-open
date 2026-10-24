"""Scanner orchestrator: runs every detector and (optionally) every fixer."""

from __future__ import annotations

import time
from pathlib import Path

from pyerrorfix.core.issue import Issue, ScanResult
from pyerrorfix.detectors import ALL_DETECTORS
from pyerrorfix.fixers import ALL_FIXERS
from pyerrorfix.pyerrorfix_config import load_config


class Scanner:
    """Runs all detectors against a single source string."""

    def __init__(self, config: dict | None = None, apply_fixers: bool = False) -> None:
        self.config = config if config is not None else load_config()
        self.apply_fixers = apply_fixers

    # ---- single source ----
    def scan_source(self, source: str, filename: str = "<stdin>") -> ScanResult:
        t0 = time.perf_counter()
        issues: list[Issue] = []
        for detector_cls in ALL_DETECTORS:
            try:
                det = detector_cls(source=source, filename=filename, config=self.config)
                issues.extend(det.run())
            except Exception:
                # detectors must never crash the pipeline
                continue
        fixed = None
        if self.apply_fixers:
            fixed = self._apply_fixers(source, issues)
        elapsed = int((time.perf_counter() - t0) * 1000)
        # stable order: by line, then severity weight, then rule_id
        issues.sort(key=lambda i: (i.line, _sev_weight(i.severity), i.rule_id))
        return ScanResult(issues=issues, fixed_source=fixed, files_scanned=1, elapsed_ms=elapsed)

    # ---- directory walk ----
    def scan_path(self, path: str | Path) -> ScanResult:
        root = Path(path)
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        all_issues: list[Issue] = []
        latest_fixed = None
        for f in files:
            if _should_skip(f):
                continue
            try:
                src = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            res = self.scan_source(src, filename=str(f))
            all_issues.extend(res.issues)
            if res.fixed_source is not None:
                # write the fix back to disk when scanning a real file
                f.write_text(res.fixed_source, encoding="utf-8")
                latest_fixed = res.fixed_source
        all_issues.sort(key=lambda i: (i.file, i.line, _sev_weight(i.severity)))
        return ScanResult(
            issues=all_issues, fixed_source=latest_fixed, files_scanned=len(files), elapsed_ms=0
        )

    # ---- fixers ----
    def _apply_fixers(self, source: str, issues: list[Issue]) -> str:
        """Run each fixer in turn.

        Fixers mutate the source (e.g. remove an import line, insert `await`).
        That shifts subsequent line numbers, so after every fixer that actually
        changes the text we **re-run detection** to refresh the issue offsets
        before handing them to the next fixer. This keeps every fixer's
        position data accurate and is what makes the pipeline idempotent.
        """
        current = source
        current_issues = list(issues)
        for fixer_cls in ALL_FIXERS:
            try:
                fixer = fixer_cls(source=current, issues=current_issues)
                new_source = fixer.apply()
            except Exception:
                continue
            if new_source != current:
                current = new_source
                # re-detect so the next fixer sees fresh line numbers
                current_issues = self._detect(current)
        return current

    def _detect(self, source: str) -> list[Issue]:
        fresh: list[Issue] = []
        for detector_cls in ALL_DETECTORS:
            try:
                det = detector_cls(source=source, filename="<fixed>", config=self.config)
                fresh.extend(det.run())
            except Exception:
                continue
        fresh.sort(key=lambda i: (i.line, _sev_weight(i.severity), i.rule_id))
        return fresh


def _sev_weight(sev) -> int:
    from pyerrorfix.core.issue import Severity

    return {
        Severity.CRITICAL: 0,
        Severity.ERROR: 1,
        Severity.WARNING: 2,
        Severity.INFO: 3,
    }.get(sev, 4)


def _should_skip(path: Path) -> bool:
    parts = path.parts
    if any(
        p
        in {
            "__pycache__",
            ".venv",
            "venv",
            "env",
            ".git",
            "node_modules",
            "dist",
            "build",
            ".tox",
            ".mypy_cache",
            ".pytest_cache",
        }
        for p in parts
    ):
        return True
    return False
