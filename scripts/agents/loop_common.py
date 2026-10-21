"""Shared primitives for the continuous agent loop modules."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_REPO = "Supremeai-bd/supremeai-open"


def log(icon: str, msg: str) -> None:
    print(f"{icon} {msg}")


def run_cmd(
    cmd: list[str], cwd: Path = REPO_ROOT, check: bool = False, timeout: int = 300
) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        stdout = p.stdout.decode("utf-8", errors="replace").strip()
        stderr = p.stderr.decode("utf-8", errors="replace").strip()
        if check and p.returncode != 0:
            raise RuntimeError(
                f"Command failed ({p.returncode}): {' '.join(cmd)}\n{stderr}"
            )
        return p.returncode, stdout, stderr
    except FileNotFoundError as exc:
        binary = cmd[0] if cmd else "unknown"
        err = f"Binary not found: '{binary}'. Please install it or proceed in zero-credential offline mode."
        if check:
            raise RuntimeError(err) from exc
        return 127, "", err
    except subprocess.TimeoutExpired:
        err = f"Command timed out after {timeout}s: {' '.join(cmd)}"
        if check:
            raise RuntimeError(err)
        return 124, "", err
    except (
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        err = f"Execution error for {' '.join(cmd)}: {exc}"
        if check:
            raise RuntimeError(err) from exc
        return 1, "", err
