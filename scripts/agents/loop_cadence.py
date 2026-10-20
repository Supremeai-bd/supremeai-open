from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from loop_common import REPO_ROOT, UPSTREAM_REPO, log, run_cmd

# ============================================================================
# Role-Cadence + Empty-Board Issue Creation (plan Â§3, Â§4, Â§10)
# ============================================================================


CADENCE_CONFIG_PATH = REPO_ROOT / "scripts" / "agents" / "agent_cadence.json"
LAST_RUN_STORE_PATH = REPO_ROOT / ".agent_last_run.json"

DEFAULT_CADENCE_HOURS: dict[str, int] = {
    "ecosystem-scout": 12,
    "auditor": 12,
    "human-eye": 24,
    "rules-breaker": 24,
    "platform-guardian": 24,
}

DEFAULT_MERGED_ROLES: dict[str, str] = {
    "federation-auditor": "auditor",
    "task-auditor": "auditor",
}


def load_cadence_config(path: Path | None = None) -> dict[str, Any]:
    """Load role cadence config (fail-closed: missing/invalid -> defaults)."""
    target = path or CADENCE_CONFIG_PATH
    try:
        if not target.exists():
            return {
                "cadences_hours": dict(DEFAULT_CADENCE_HOURS),
                "merged_roles": dict(DEFAULT_MERGED_ROLES),
            }
        with target.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        cadences = data.get("cadences_hours") or {}
        merged = data.get("merged_roles") or {}
        # Validate: every cadence must be a positive int.
        cleaned: dict[str, int] = {}
        for role, hours in cadences.items():
            try:
                h = int(hours)
            except (TypeError, ValueError):
                continue
            if h > 0:
                cleaned[str(role)] = h
        if not cleaned:
            cleaned = dict(DEFAULT_CADENCE_HOURS)
        return {"cadences_hours": cleaned, "merged_roles": merged or dict(DEFAULT_MERGED_ROLES)}
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:  # fail-closed: never crash the loop on bad config
        log("âš ï¸", f"[Cadence] config load failed ({exc}); using defaults.")
        return {
            "cadences_hours": dict(DEFAULT_CADENCE_HOURS),
            "merged_roles": dict(DEFAULT_MERGED_ROLES),
        }


def canonical_role(role: str, config: dict[str, Any] | None = None) -> str:
    """Map merged aliases (federation-auditor/task-auditor) to canonical auditor."""
    cfg = config or load_cadence_config()
    merged = cfg.get("merged_roles", DEFAULT_MERGED_ROLES)
    return merged.get(role, role)


def load_last_run_store(path: Path | None = None) -> dict[str, float]:
    """Load per-role last_run timestamps (epoch seconds). Missing/invalid -> {}."""
    target = path or LAST_RUN_STORE_PATH
    try:
        if not target.exists():
            return {}
        with target.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        out: dict[str, float] = {}
        for k, v in data.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out
    except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def save_last_run_store(store: dict[str, float], path: Path | None = None) -> bool:
    """Persist per-role last_run timestamps. Returns True on success."""
    target = path or LAST_RUN_STORE_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as fh:
            json.dump(store, fh, indent=2, sort_keys=True)
        return True
    except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        log("âš ï¸", f"[Cadence] last_run store save failed: {exc}")
        return False


def role_is_due(
    role: str,
    last_run_ts: float | None,
    now_ts: float,
    config: dict[str, Any] | None = None,
) -> bool:
    """True if `role` has not run within its configured cadence window."""
    cfg = config or load_cadence_config()
    cadences = cfg.get("cadences_hours", DEFAULT_CADENCE_HOURS)
    canon = canonical_role(role, cfg)
    hours = cadences.get(canon) or cadences.get(role)
    if not hours or hours <= 0:
        return False
    if last_run_ts is None:
        return True
    try:
        elapsed_hours = (now_ts - float(last_run_ts)) / 3600.0
    except (TypeError, ValueError):
        return True
    return elapsed_hours >= hours


def due_roles(
    last_runs: dict[str, float] | None,
    now_ts: float | None = None,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Return the list of roles whose cadence window has elapsed."""
    cfg = config or load_cadence_config()
    store = last_runs or {}
    now = now_ts if now_ts is not None else time.time()
    result: list[str] = []
    for role in cfg.get("cadences_hours", DEFAULT_CADENCE_HOURS):
        if role_is_due(role, store.get(role), now, cfg):
            result.append(role)
    return result


def mark_role_run(
    role: str,
    store: dict[str, float],
    now_ts: float | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Record that `role` just ran. Returns the updated store (mutates in place)."""
    cfg = config or load_cadence_config()
    canon = canonical_role(role, cfg)
    ts = now_ts if now_ts is not None else time.time()
    store[canon] = ts
    return store


def create_full_project_audit_issue() -> str | None:
    """Create a scoped 'full-project audit' issue when the board is empty.

    Returns the issue number (as str) on success, None on failure/absence of gh.
    Fail-closed: missing gh or API error -> None + log, never crash the loop.
    """
    title = "audit: full-project sweep (auto-generated by continuous agent loop)"
    body = (
        "## Summary\n"
        "Auto-generated by the SupremeAI continuous agent loop because the task board "
        "was empty. An auditor should sweep the whole project and file findings as "
        "separate, scoped issues.\n\n"
        "## Scope\n"
        "- Touching files: (auditor to determine; keep <= 30 files / <= 200 KB per follow-up PR)\n"
        "- Forbidden paths: .env*, secrets/**, credentials/**, vault/**\n\n"
        "## Acceptance\n"
        "- [ ] Full project audit completed\n"
        "- [ ] Each finding filed as a separate issue with scope + acceptance + priority\n"
        "- [ ] No duplicate findings\n\n"
        "## Priority\nP2\n\n"
        "## Type of Change\n- [x] docs/audit\n"
    )
    labels = "status:unclaimed,group:agent-orchestration,type:audit"
    code, out, err = run_cmd(
        [
            "gh",
            "issue",
            "create",
            "--repo",
            UPSTREAM_REPO,
            "--title",
            title,
            "--body",
            body,
            "--label",
            labels,
        ]
    )
    if code != 0:
        log(
            "âš ï¸",
            f"[Empty-Board] audit issue creation failed ({err or out or f'code {code}'}).",
        )
        return None
    # gh issue create prints the issue URL; extract trailing number.
    url = (out or "").strip().splitlines()[-1] if out.strip() else ""
    m = re.search(r"/issues/(\d+)", url)
    if m:
        num = m.group(1)
        log("âœ…", f"[Empty-Board] created audit issue #{num}: {url}")
        return num
    log("âš ï¸", f"[Empty-Board] audit issue created but number unparseable: {out!r}")
    return None



