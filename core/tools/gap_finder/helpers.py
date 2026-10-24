from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path

from .config import TEXT_EXTENSIONS
from .models import Finding


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def severity_rank(value: str) -> int:
    return {
        "CRITICAL": 0,
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3,
        "INFO": 4,
    }.get(value, 99)


def add_finding(
    findings: list[Finding],
    *,
    rule_id: str,
    category: str,
    severity: str,
    confidence: float,
    title: str,
    message: str,
    path: str | None = None,
    line: int | None = None,
    evidence: Iterable[str] = (),
    impact: str = "",
    remediation: str = "",
    verification: str = "",
) -> None:
    findings.append(
        Finding(
            rule_id=rule_id,
            category=category,
            severity=severity,
            confidence=max(0.0, min(1.0, confidence)),
            title=title,
            message=message,
            path=path,
            line=line,
            evidence=list(evidence),
            impact=impact,
            remediation=remediation,
            verification=verification,
        ).finalize()
    )


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name in {
        "Dockerfile",
        "Makefile",
        "Procfile",
        ".env.example",
        ".gitignore",
        ".dockerignore",
    }


def iter_files(root: Path, ignores: set[str], max_files: int) -> list[Path]:
    result: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ignores and not d.startswith(".pytest_cache")]
        for name in files:
            if name in ignores:
                continue
            path = Path(current) / name
            result.append(path)
            if len(result) >= max_files:
                return result
    return result


def read_text(path: Path, limit: int = 2_000_000) -> str | None:
    try:
        data = path.read_bytes()
        if len(data) > limit:
            data = data[:limit]
        return data.decode("utf-8", errors="replace")
    except Exception:
        return None


def looks_like_generated(path: Path) -> bool:
    name = path.name.lower()
    markers = (
        ".min.", ".map", ".lock", "generated", "gen_", "_generated",
        ".g.dart", ".freezed.dart",
    )
    return any(marker in name for marker in markers)


def normalize_target(path: str) -> str:
    p = path.replace("\\", "/").strip()
    p = re.sub(r"^\./", "", p)
    p = re.sub(r"/+", "/", p)
    return p


