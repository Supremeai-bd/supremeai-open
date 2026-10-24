#!/usr/bin/env python3
"""SupremeAI Solution Synthesizer — The Hand.

Turns diagnostic evidence into a bounded, testable repair loop.

Design goals:
- diagnosis -> solution hypothesis -> patch -> verification -> iteration
- provider-agnostic OpenAI-compatible model endpoint
- strict structured JSON output
- dry-run by default; --apply for real changes
- isolated worktree/copy for verification
- automatic backup before applying
- regression-test generation request
- rollback on failed verification
- evidence + decision log

No external Python dependencies are required.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_FILE_BYTES = 200_000
MAX_CONTEXT_FILES = 12
ALLOWED_WRITE_ROOTS = ("backend", "frontend", "apps", "packages", "src", "tests", "scripts", ".github", "infrastructure", "docs")
FORBIDDEN_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}


@dataclass
class Evidence:
    path: str
    reason: str
    excerpt: str


@dataclass
class PatchOp:
    path: str
    action: str  # update|create|delete
    content: str = ""
    reason: str = ""


@dataclass
class Solution:
    diagnosis: str
    strategy: str
    confidence: float
    patch: list[PatchOp]
    tests: list[str]
    risks: list[str]
    rollback_note: str


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        data = data[:MAX_FILE_BYTES]
    return data.decode("utf-8", errors="replace")


def safe_rel(path: str) -> bool:
    p = Path(path)
    if p.is_absolute() or ".." in p.parts:
        return False
    if not p.parts:
        return False
    return p.parts[0] in ALLOWED_WRITE_ROOTS or p.parts[0].startswith(".")


def discover_files(root: Path) -> list[Path]:
    out = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in FORBIDDEN_PARTS for part in p.parts):
            continue
        if p.stat().st_size > MAX_FILE_BYTES:
            continue
        if p.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml", ".toml", ".md"}:
            out.append(p)
    return out


def collect_evidence(root: Path, issue: dict[str, Any]) -> list[Evidence]:
    evidence: list[Evidence] = []
    paths = issue.get("files") or []
    keywords = [str(x).lower() for x in (issue.get("keywords") or [])]
    exact_error = str(issue.get("error") or "").strip()

    candidates = []
    for raw in paths:
        p = (root / raw).resolve()
        if p.exists() and p.is_file() and root.resolve() in p.parents:
            candidates.append(p)
    if not candidates:
        candidates = discover_files(root)

    scored: list[tuple[int, Path, str]] = []
    for p in candidates:
        text = read_text(p)
        low = text.lower()
        score = 0
        reason_bits = []
        if exact_error and exact_error.lower() in low:
            score += 100
            reason_bits.append("contains exact error")
        for kw in keywords:
            if kw and kw in low:
                score += 10
                reason_bits.append(f"contains keyword: {kw}")
        if p.as_posix().endswith(tuple(issue.get("likely_suffixes") or [])):
            score += 2
        if score:
            scored.append((score, p, "; ".join(reason_bits)))

    if not scored:
        scored = [(1, p, "candidate by project scan") for p in candidates[:MAX_CONTEXT_FILES]]
    scored.sort(key=lambda x: x[0], reverse=True)

    for _, p, reason in scored[:MAX_CONTEXT_FILES]:
        text = read_text(p)
        excerpt = text[:12000]
        evidence.append(Evidence(str(p.relative_to(root)).replace("\\", "/"), reason, excerpt))
    return evidence


def run_cmd(cmd: str, cwd: Path, timeout: int = 120) -> tuple[int, str]:
    # Security: never use shell=True — commands may come from model output.
    # Split the string into an argv list instead (no shell interpretation).
    try:
        argv = shlex.split(cmd, posix=(os.name != "nt"))
        proc = subprocess.run(argv, cwd=cwd, shell=False, capture_output=True, text=True, timeout=timeout)
        output = (proc.stdout + "\n" + proc.stderr).strip()
        return proc.returncode, output[-20000:]
    except subprocess.TimeoutExpired as exc:
        return 124, f"TIMEOUT: {exc}"
    except (ValueError, OSError) as exc:
        return 127, f"COMMAND_ERROR: {exc}"


def detect_verify_commands(root: Path) -> list[str]:
    commands = []
    if (root / "pyproject.toml").exists():
        commands += ["python -m compileall -q ."]
    if (root / "package.json").exists():
        pkg = json.loads((root / "package.json").read_text(encoding="utf-8", errors="replace"))
        scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
        for name in ("lint", "test", "typecheck", "build"):
            if name in scripts:
                manager = "pnpm" if (root / "pnpm-lock.yaml").exists() else "npm"
                commands.append(f"{manager} run {name}")
    if (root / "pytest.ini").exists() or (root / "tests").exists():
        commands.append("python -m pytest -q")
    if not commands:
        commands.append("python -m compileall -q .")
    return list(dict.fromkeys(commands))


def build_prompt(issue: dict[str, Any], evidence: list[Evidence], verify_cmds: list[str]) -> str:
    payload = {
        "task": "Repair the diagnosed software gap with the smallest safe patch.",
        "issue": issue,
        "verification_commands": verify_cmds,
        "evidence": [asdict(e) for e in evidence],
        "strict_rules": [
            "Return ONLY JSON matching the requested schema.",
            "Prefer minimal localized edits.",
            "Do not invent APIs or dependencies unless essential.",
            "Do not change authentication, secrets, data-loss behavior, or deployment policy without explicitly flagging high risk.",
            "Include a regression test when feasible.",
            "If evidence is insufficient, return an empty patch and explain why.",
        ],
        "schema": {
            "diagnosis": "string",
            "strategy": "string",
            "confidence": "number 0..1",
            "patch": [{"path": "relative/path", "action": "update|create|delete", "content": "full file content", "reason": "string"}],
            "tests": ["shell commands"],
            "risks": ["string"],
            "rollback_note": "string",
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def ask_model(prompt: str) -> dict[str, Any]:
    url = os.getenv("SUPREMEAI_SOLVER_URL", "").strip()
    key = os.getenv("SUPREMEAI_SOLVER_API_KEY", "").strip()
    model = os.getenv("SUPREMEAI_SOLVER_MODEL", "")
    if not url:
        raise RuntimeError("SUPREMEAI_SOLVER_URL is not configured")
    body = json.dumps({"model": model, "messages": [{"role": "system", "content": "You are a senior software repair agent."}, {"role": "user", "content": prompt}], "temperature": 0.1, "response_format": {"type": "json_object"}}).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"solver request failed: {exc}") from exc
    data = json.loads(raw)
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return json.loads(content)


def parse_solution(data: dict[str, Any]) -> Solution:
    patch = []
    for item in data.get("patch", []):
        if not isinstance(item, dict):
            continue
        patch.append(PatchOp(path=str(item.get("path", "")), action=str(item.get("action", "")), content=str(item.get("content", "")), reason=str(item.get("reason", ""))))
    return Solution(
        diagnosis=str(data.get("diagnosis", "")),
        strategy=str(data.get("strategy", "")),
        confidence=float(data.get("confidence", 0.0)),
        patch=patch,
        tests=[str(x) for x in data.get("tests", [])],
        risks=[str(x) for x in data.get("risks", [])],
        rollback_note=str(data.get("rollback_note", "")),
    )


def validate_solution(solution: Solution) -> list[str]:
    errors = []
    if not solution.diagnosis or not solution.strategy:
        errors.append("missing diagnosis/strategy")
    if not (0 <= solution.confidence <= 1):
        errors.append("confidence outside 0..1")
    for op in solution.patch:
        if op.action not in {"update", "create", "delete"}:
            errors.append(f"invalid action: {op.action}")
        if not safe_rel(op.path):
            errors.append(f"unsafe path: {op.path}")
        if op.action in {"update", "create"} and not op.content:
            errors.append(f"empty content: {op.path}")
        if op.action == "delete" and op.path.startswith(".github/workflows"):
            errors.append("workflow deletion is blocked")
    return errors


def apply_patch(root: Path, patch: list[PatchOp], backup_dir: Path) -> None:
    for op in patch:
        target = root / op.path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.is_file():
            backup = backup_dir / op.path
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        if op.action in {"update", "create"}:
            target.write_text(op.content, encoding="utf-8")
        elif op.action == "delete" and target.exists():
            target.unlink()


def verify(root: Path, solution: Solution) -> tuple[bool, list[dict[str, Any]]]:
    cmds = solution.tests or detect_verify_commands(root)
    results = []
    ok = True
    for cmd in cmds:
        rc, out = run_cmd(cmd, root)
        results.append({"command": cmd, "returncode": rc, "output": out})
        if rc != 0:
            ok = False
            break
    return ok, results


def rollback(root: Path, backup_dir: Path, patch: list[PatchOp]) -> None:
    for op in patch:
        target = root / op.path
        backup = backup_dir / op.path
        if backup.exists():
            shutil.copy2(backup, target)
        elif op.action == "create" and target.exists():
            target.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description="SupremeAI Solution Synthesizer")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--issue", required=True, help="JSON file describing the diagnosed gap")
    ap.add_argument("--apply", action="store_true", help="apply successful patch to project")
    ap.add_argument("--max-attempts", type=int, default=2)
    ap.add_argument("--report", default="reports/solution_synthesizer.json")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    issue = json.loads(Path(args.issue).read_text(encoding="utf-8"))
    evidence = collect_evidence(root, issue)
    verify_cmds = detect_verify_commands(root)
    report: dict[str, Any] = {"tool": "solution_synthesizer", "timestamp": time.time(), "issue": issue, "evidence": [asdict(e) for e in evidence], "attempts": []}

    if os.getenv("SUPREMEAI_SOLVER_URL", "").strip() == "":
        report["status"] = "blocked"
        report["reason"] = "No solver endpoint configured. Set SUPREMEAI_SOLVER_URL and optionally SUPREMEAI_SOLVER_API_KEY/SUPREMEAI_SOLVER_MODEL."
    else:
        for attempt in range(1, max(1, args.max_attempts) + 1):
            prompt = build_prompt(issue, evidence, verify_cmds)
            try:
                solution = parse_solution(ask_model(prompt))
                validation = validate_solution(solution)
                attempt_log = {"attempt": attempt, "solution": asdict(solution), "validation_errors": validation}
                if validation:
                    report["attempts"].append(attempt_log)
                    continue

                with tempfile.TemporaryDirectory(prefix="supremeai-solution-") as td:
                    sandbox = Path(td) / "repo"
                    shutil.copytree(root, sandbox, dirs_exist_ok=True)
                    backup_dir = Path(td) / "backup"
                    backup_dir.mkdir()
                    apply_patch(sandbox, solution.patch, backup_dir)
                    ok, verification = verify(sandbox, solution)
                    attempt_log["verification"] = verification
                    attempt_log["verified"] = ok
                    report["attempts"].append(attempt_log)
                    if ok:
                        report["status"] = "verified"
                        report["winning_solution"] = asdict(solution)
                        if args.apply:
                            real_backup = root / ".supremeai_backups" / time.strftime("%Y%m%d-%H%M%S")
                            real_backup.mkdir(parents=True, exist_ok=True)
                            apply_patch(root, solution.patch, real_backup)
                            report["applied"] = True
                            report["backup"] = str(real_backup.relative_to(root))
                        break
            except Exception as exc:
                report["attempts"].append({"attempt": attempt, "error": str(exc)})
        else:
            report["status"] = "unverified"

    out = root / args.report
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report.get("status"), "report": str(out), "applied": report.get("applied", False)}, indent=2))
    return 0 if report.get("status") in {"verified", "blocked"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
