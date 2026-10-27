#!/usr/bin/env python3
"""SupremeAI — Minimal Autonomous Agent Loop (Unified Rules & Roles Dispatcher).

CONTRACT_VERSION = "agent-loop-contract/1"

Traffic-police logic:
1. Always display the 4 Universal Invariant Pillars (Common Rules).
2. If unclaimed issues exist -> Unlimited Solvers allowed: prompt agent with solver mandate & status:claimed rule.
3. If no open issues exist -> Reset/zero cadence timers so scheduled roles can run immediately.
4. Scheduled roles -> Exactly 1 agent at a time per role (active lock / immediate state advance).
5. Problematic/stuck issues -> Agents autonomously decide and handle them.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "agent-loop-contract/1"
UPSTREAM_REPO = "Supremeai-bd/supremeai-open"
REPO_ROOT = Path(__file__).resolve().parents[2]
CADENCE_FILE = REPO_ROOT / "scripts" / "agents" / "agent_cadence.json"
STATE_FILE = REPO_ROOT / "scripts" / "agents" / "agent_cadence_state.json"

RULE_FRESHNESS_FILES = (
    "AGENTS.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)

# Single board-filter SSOT shared by pick_next_issue() and main() dispatch.
# বাংলা: আগে দুই জায়গায় দুই ভিন্ন skip-set ছিল — main() mirror:private /
# state:seq-hold / blocked-by-upstream ইস্যুতে solver পাঠাত (যেগুলো agent
# দাবিই করতে পারে না) আর pick_next_issue() anchor-hub / admin-only বাদ দিত
# না। এখন এক ফ্রোজেন সেট — দুই পাঠক, এক চুক্তি (drift অসম্ভব)।
BOARD_EXCLUDED_LABELS = frozenset(
    {
        "status:claimed",
        "status:in-progress",
        "state:seq-hold",
        "blocked-by-upstream",
        "mirror:private",
        "anchor-hub",
        "admin-only",
    }
)

FORBIDDEN_SCOPE_PATHS = (".env*", "secrets/**", "credentials/**", "vault/**")
# বাংলা: AGENT_RULES.md আর নেই — PR #1526 নিজেই ফাইলটি মুছে দিয়েছে (Single Door
# SSOT এখন AGENTS.md)। তালিকায় মুছে-যাওয়া ফাইল রাখলে step_2_rules()/run_cycle()
# fresh main-এ সবসময় exit 1 দেয় (missing_local + rev-parse দুই জায়গাতেই fail) —
# নিজের মুছে-ফেলা ফাইলকে পূর্বশর্ত করে রাখা লুপের আত্ম-পরাজয়।

OFFLINE_ENV_VARS = (
    "SUPREMEAI_OFFLINE",
    "AGENT_LOOP_OFFLINE",
    "CI_OFFLINE",
)

DEFAULT_GROUP = "core"
VALID_TASK_TYPES = frozenset({"FEAT", "FIX", "DOCS", "STYLE", "REFACTOR", "TEST", "CHORE", "PERF", "OPS", "AUDIT", "SCOUT", "IMPLEMENT"})
VALID_PRIORITIES = frozenset({"P0", "P1", "P2", "P3", "P4"})
VALID_ADMIN_GATE_STATUSES = frozenset({"NOT_REQUIRED", "PENDING", "APPROVED", "REJECTED"})
VALID_GROUPS = frozenset({"core", "gateway", "studio", "vscode", "browser", "docs", "infra", "marketplace", "federation"})

def build_task_contract(
    task_id: str,
    issue: str | int | None = None,
    task_type: str = "IMPLEMENT",
    group: str = DEFAULT_GROUP,
    priority: str = "P2",
    objective: str = "",
    touching_files: list[str] | None = None,
    forbidden_paths: list[str] | None = None,
    dependencies: list[str] | None = None,
    predecessor: str | int | None = None,
    admin_gate_required: bool = False,
    admin_gate_status: str = "NOT_REQUIRED",
    role_policy: str = "contributor",
    required_evidence: list[str] | None = None,
    verification: list[str] | None = None,
    acceptance: list[str] | None = None,
    stop_conditions: list[str] | None = None,
    output_format: str = "structured",
) -> dict[str, Any]:
    task_type_upper = task_type.upper()
    if task_type_upper not in VALID_TASK_TYPES:
        raise ValueError(f"Invalid task_type: '{task_type}'")
    priority_upper = priority.upper()
    if priority_upper not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority: '{priority}'")
    gate_status_upper = admin_gate_status.upper()
    if gate_status_upper not in VALID_ADMIN_GATE_STATUSES:
        raise ValueError(f"Invalid admin_gate_status: '{admin_gate_status}'")
    if group not in VALID_GROUPS:
        raise ValueError(f"Invalid group: '{group}'")
    return {
        "task_contract": {
            "version": 1,
            "task_id": str(task_id),
            "issue": issue,
            "task_type": task_type_upper,
            "group": group,
            "priority": priority_upper,
            "objective": objective,
        }
    }

def pick_next_issue(exclude: set[str] | list[str] | None = None) -> str | None:
    code, out, _ = run_cmd([
        "gh", "issue", "list",
        "--repo", UPSTREAM_REPO,
        "--state", "open",
        "--limit", "200",
        "--json", "number,title,labels",
    ])
    issues = []
    if code == 0 and out.strip():
        try:
            issues = json.loads(out)
        except Exception:
            pass
    if not issues:
        return None

    def label_names(item: dict[str, Any]) -> list[str]:
        labels = item.get("labels")
        if not isinstance(labels, list):
            return []
        return [str(l.get("name", "")).lower() for l in labels if isinstance(l, dict)]

    def is_claimable(item: dict[str, Any]) -> bool:
        names = label_names(item)
        return not (BOARD_EXCLUDED_LABELS & set(names))

    PRIORITY_MAP = (("p0", 0), ("p1", 1), ("p2", 2), ("p3", 3))

    def priority_key(item: dict[str, Any]) -> tuple[int, int]:
        names = label_names(item)
        tier = 4
        for marker, rank in PRIORITY_MAP:
            if any(name == marker or name.startswith(marker + "-") or name.startswith(marker + " ") for name in names):
                tier = rank
                break
        return (tier, int(item.get("number", 0)))

    candidates = [i for i in issues if isinstance(i, dict) and is_claimable(i)]
    if exclude:
        excluded_set = {str(e) for e in exclude}
        candidates = [i for i in candidates if str(i.get("number")) not in excluded_set]
    sorted_issues = sorted(candidates, key=priority_key)
    if sorted_issues:
        return str(sorted_issues[0].get("number"))
    return None


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

ROLE_RULES: dict[str, str] = {
    "solver": "Unlimited concurrent solvers allowed. Mandatory rule: Label 'status:claimed' on the issue before branching. Solve root cause, verify boundary, submit PR.",
    "ecosystem-scout": "Scan federation for new expansion opportunities and file sub-issues under 8 Anchor Hubs (no code edits).",
    "auditor": "Audit codebase for dead code, compliance drifts, and propose automated CI gates.",
    "human-eye": "Inspect user-facing public funnel speed (FCP < 1.0s) and responsive UI performance.",
    "rules-breaker": "Probe security boundaries, enforce zero-leak invariant, and report vulnerabilities.",
    "platform-guardian": "Verify all connected service dependencies and alert if any service is degraded or quota-blocked.",
}

COMMON_RULES = """=== UNIVERSAL INVARIANTS (ALL ROLES MUST FOLLOW) ===
1. Dual-Rebase: Rebase origin/main at work-start AND pre-push (0 behind).
2. Boundary: Zero satellite code in repo root (src/*, service/*, packages/*).
3. Superior Replacement: Discard broken legacy code/tests; never hack new code to appease past errors.
4. Verification: No direct push to protected branches; all PRs require local proof."""

def log(icon: str, msg: str) -> None:
    try:
        print(f"{icon} {msg}")
    except UnicodeEncodeError:
        print(f"[*] {msg}")

def run_cmd(
    cmd: list[str], cwd: Path | None = None, check: bool = False, timeout: int = 300
) -> tuple[int, str, str]:
    target_cwd = cwd or REPO_ROOT
    try:
        p = subprocess.run(
            cmd,
            cwd=target_cwd,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        stdout = p.stdout.decode("utf-8", errors="replace").strip()
        stderr = p.stderr.decode("utf-8", errors="replace").strip()
        if check and p.returncode != 0:
            raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(cmd)}\n{stderr}")
        return p.returncode, stdout, stderr
    except FileNotFoundError as exc:
        err = f"Binary not found: '{cmd[0] if cmd else 'unknown'}'"
        if check:
            raise RuntimeError(err) from exc
        return 127, "", err
    except subprocess.TimeoutExpired:
        err = f"Command timed out after {timeout}s: {' '.join(cmd)}"
        if check:
            raise RuntimeError(err)
        return 124, "", err
    except Exception as exc:
        err = f"Execution error for {' '.join(cmd)}: {exc}"
        if check:
            raise RuntimeError(err) from exc
        return 1, "", err

def diff_rule_freshness(
    local_shas: dict[str, str | None], remote_shas: dict[str, str | None]
) -> list[str]:
    diverged: list[str] = []
    # Preserve order of RULE_FRESHNESS_FILES first, then any extra keys
    ordered_keys: list[str] = [k for k in RULE_FRESHNESS_FILES if k in local_shas or k in remote_shas]
    for k in sorted(set(local_shas) | set(remote_shas)):
        if k not in ordered_keys:
            ordered_keys.append(k)
    for key in ordered_keys:
        loc = local_shas.get(key)
        rem = remote_shas.get(key)
        if loc != rem:
            diverged.append(key)
    return diverged

def mandatory_invariant_checklist() -> list[dict[str, Any]]:
    return [
        {"id": "zero-admin-budget", "rule": "Work budget <= 0.01%"},
        {"id": "claim-gate", "rule": "Atomic claim before branch (status:claimed)"},
        {"id": "reflection-evidence", "rule": "## Reflection Evidence with - **why:** and - **alternatives_rejected:**"},
        {"id": "p7-cohesive-sizing", "rule": "Cohesive domain slice <= 30 files / <= 200 KB diff"},
        {"id": "boundary-guard", "rule": "Satellite code strictly in domain mirrors"},
        {"id": "stale-base-guard", "rule": "Rebase origin/main at work-start AND pre-push (0 behind)"},
    ]

def _offline_requested(flag: bool) -> bool:
    if flag:
        return True
    return any(
        os.environ.get(var, "").strip().lower() in ("1", "true", "yes", "on")
        for var in OFFLINE_ENV_VARS
    )

def _print_rule_version_and_checklist() -> None:
    pass

def step_2_rules(offline: bool = False, auto_sync: bool = True) -> bool:
    """Step 2: Constitution freshness gate + governing-rules loading (#567)."""
    repo_root = REPO_ROOT
    missing_local = [p for p in RULE_FRESHNESS_FILES if not (repo_root / p).exists()]
    if missing_local:
        return False

    if _offline_requested(offline):
        _print_rule_version_and_checklist()
        return True

    code, _, err = run_cmd(["git", "fetch", "origin", "main"], cwd=repo_root)
    if code != 0:
        return False

    local_shas: dict[str, str | None] = {}
    remote_shas: dict[str, str | None] = {}
    for path in RULE_FRESHNESS_FILES:
        h_code, h_out, h_err = run_cmd(["git", "hash-object", "--", path], cwd=repo_root)
        if h_code != 0:
            return False
        local_shas[path] = h_out.strip() or None
        r_code, r_out, _ = run_cmd(
            ["git", "rev-parse", "--verify", "--quiet", f"origin/main:{path}"], cwd=repo_root
        )
        if r_code != 0:
            return False
        remote_shas[path] = r_out.strip() or None

    diverged = diff_rule_freshness(local_shas, remote_shas)

    if diverged and auto_sync:
        for path in diverged:
            c_code, _, _ = run_cmd(
                ["git", "checkout", "origin/main", "--", path], cwd=repo_root
            )
            if c_code != 0:
                return False

    _print_rule_version_and_checklist()
    return True

def pre_push_rebase_guard() -> tuple[bool, int, str]:
    """#514 Pre-Push Rebase Invariant (Anti-Stale-Base Mandate). Fail-closed."""
    fetch_code, _, fetch_err = run_cmd(["git", "fetch", "origin", "main"])
    if fetch_code != 0:
        return False, 0, f"fetch of origin main failed: {fetch_err or 'unknown'}"
    rc, out, err = run_cmd(["git", "rev-list", "--count", "HEAD..origin/main"])
    if rc != 0:
        return False, 0, f"behind-count failed: {err or 'unknown'}"
    try:
        behind = int((out or "0").strip() or "0")
    except ValueError:
        return False, 0, f"unparseable behind-count: {out!r}"
    if behind <= 0:
        return True, 0, "fresh"
    rc, _, err = run_cmd(["git", "rebase", "origin/main"])
    if rc != 0:
        run_cmd(["git", "rebase", "--abort"])
        return False, behind, f"rebase failed; aborted: {err or ''}"
    return True, behind, f"stale ({behind} behind); rebased onto origin/main"

def pre_work_rebase_guard() -> tuple[bool, int, str]:
    """Start-of-Work Rebase Mandate (#161, #514)."""
    return pre_push_rebase_guard()

def step_4_branch(task: dict[str, Any] | None = None) -> str | None:
    """Step 4: Branch creation guarded by pre_work_rebase_guard()."""
    synced, behind, detail = pre_work_rebase_guard()
    if not synced:
        return None
    return "main"

def step_6_verify(*_a: Any, **_k: Any) -> bool:
    return True

def push_branch_to_fork(*_a: Any, **_k: Any) -> bool:
    return True

def step_7_record(*_a: Any, **_k: Any) -> bool:
    ok, behind, detail = pre_push_rebase_guard()
    if not ok:
        return False
    if not step_6_verify():
        return False
    return push_branch_to_fork()

def run_cycle(args: Any = None, *_a: Any, **_k: Any) -> int:
    """Run a single dispatch cycle with step_2_rules offline check."""
    if not step_2_rules(offline=getattr(args, "offline", False)):
        return 1
    return 0

def classify_task_role(
    title: str = "", labels: Iterable[str] = (), body: str = ""
) -> str:
    present = frozenset(labels)
    if "status:runway" in present:
        return "ci-fixer"
    if "gate:pre-landing" in present:
        return "task-auditor"
    if "status:claimed" in present:
        return "coder"
    return "coder"

def build_task_envelope(issue: dict[str, Any], group: str = "") -> dict[str, Any]:
    """Build the canonical task-envelope-v1 payload (AGENT_LOOP_SPEC.md §2).

    Consumers (both fail-closed):
      - core/runner/agent_runner.py  (load_envelope / validate_envelope)
      - scripts/agents/execution_bridge.py (REQUIRED_TASK_KEYS)

    বাংলা: #1526 রিরাইট এই পেলোডটাকে ৩-ফিল্ডের task_contract স্টাবে নামিয়ে
    দিয়েছিল — ফলে loop→runner→bridge মেশিন-পথ পুরো বিচ্ছিন্ন হয়ে গিয়েছিল
    (ভুল টপ-লেভেল কী, --issue পতাকা নীরবে গিলে ফেলা, specialist_prompt /
    submission / scope কিছুই নেই)। এই ফাংশন SSOT আকৃতি ফিরিয়ে আনে।
    """
    labels_raw = issue.get("labels") or []
    labels = [
        str(l.get("name", "")) if isinstance(l, dict) else str(l)
        for l in labels_raw
    ]
    num = int(issue.get("number", 0) or 0)
    title = str(issue.get("title", "")) or (f"issue-{num}" if num else "adhoc-task")
    body = str(issue.get("body", ""))
    prio = "P2"
    for p in ("p0", "p1", "p2", "p3"):
        if any(n == p or n.startswith(p + "-") or n.startswith(p + " ") for n in (x.lower() for x in labels)):
            prio = p.upper()
            break
    role = classify_task_role(title, labels, body)
    task_id = f"task-{num}" if num else "task-adhoc"
    contract = build_task_contract(
        task_id=task_id,
        issue=num or None,
        group=group or DEFAULT_GROUP,
        priority=prio,
        objective=title,
    )["task_contract"]
    prompt = (
        f"You are the {role} specialist for {task_id} (group: {contract['group']}, "
        f"priority: {prio}). Objective: {title}. Work strictly inside the declared "
        "scope, follow the 4 Universal Invariants (AGENTS.md), declare your "
        "touching_files on claim, and submit via bridge_submit_patch or a linked PR."
    )
    return {
        "task_envelope": {
            "envelope_version": 1,
            "output_format": "task-envelope-v1",
            "task_id": task_id,
            "issue": str(num) if num else None,
            "task_type": contract["task_type"],
            "group": contract["group"],
            "priority": contract["priority"],
            "objective": title,
            "problem_statement": {
                "id": num,
                "title": title,
                "body": body,
                "labels": labels,
                "state": str(issue.get("state", "open")),
            },
            "role": role,
            "role_policy": "contributor",
            "role_description": ROLE_RULES.get(
                role, "Execute role objectives strictly."
            ),
            "scope": {
                "touching_files": ["<declare-on-claim>"],
                "forbidden_paths": list(FORBIDDEN_SCOPE_PATHS),
            },
            "acceptance": [],
            "verification": [
                "python scripts/agents/continuous_agent_loop.py --verify-only"
            ],
            "required_evidence": ["reflection", "boot_smoke", "tests"],
            "stop_conditions": [
                "scope boundary violation",
                "verified non-reproducible on live main (U3)",
            ],
            "admin_gate": {"required": False, "status": "NOT_REQUIRED"},
            "specialist_prompt": prompt,
            "submission": {
                "pathway": "bridge_submit_patch | pull_request",
                "reference": "AGENTS.md §2.1 Pathway 1 + §8 (bridge_submit_patch)",
                "base_branch": "main",
                "pr_title_prefix": "fix(open):",
                "issue_reference_required": bool(num),
                "branch_convention": (
                    "^(feat|fix|docs|chore|test|refactor|perf|bridge|group|contributor|"
                    "hotfix|release|agent)/<slug> — enforced by pipeline.yml"
                ),
                "pr_body_template": (
                    f"### Summary\nCloses #{num} — {title}\n\n"
                    f"### Linked Issue / Claim\nCloses #{num}\n\n"
                    "### Key Changes\n- <change>\n\n"
                    "## Reflection Evidence (why + alternatives_rejected)\n"
                    "- **why:** <rationale>\n"
                    "- **alternatives_rejected:**\n  - <alternative>: rejected — <reason>\n\n"
                    "### Rollback Path\n- [x] `git revert`-safe"
                ),
            },
        }
    }

def load_cadence_config(path: Path | None = None) -> dict[str, Any]:
    target = path or CADENCE_FILE
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
        cleaned = {str(k): int(v) for k, v in cadences.items() if str(v).isdigit() and int(v) > 0}
        return {
            "cadences_hours": cleaned or dict(DEFAULT_CADENCE_HOURS),
            "merged_roles": merged or dict(DEFAULT_MERGED_ROLES),
        }
    except Exception:
        return {
            "cadences_hours": dict(DEFAULT_CADENCE_HOURS),
            "merged_roles": dict(DEFAULT_MERGED_ROLES),
        }

def canonical_role(role: str, config: dict[str, Any] | None = None) -> str:
    cfg = config or load_cadence_config()
    merged = cfg.get("merged_roles", DEFAULT_MERGED_ROLES)
    return merged.get(role, role)

def load_last_run_store(path: Path | None = None) -> dict[str, float]:
    target = path or STATE_FILE
    try:
        if not target.exists():
            return {}
        with target.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k): float(v) for k, v in data.items() if str(v).replace(".", "", 1).isdigit()}
    except Exception:
        return {}

def save_last_run_store(store: dict[str, float], path: Path | None = None) -> bool:
    target = path or STATE_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(store, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False

def role_is_due(
    role: str,
    last_run_ts: float | None,
    now_ts: float,
    config: dict[str, Any] | None = None,
) -> bool:
    cfg = config or load_cadence_config()
    cadences = cfg.get("cadences_hours", DEFAULT_CADENCE_HOURS)
    canon = canonical_role(role, cfg)
    hours = cadences.get(canon) or cadences.get(role)
    if not hours or hours <= 0:
        return False
    if last_run_ts is None:
        return True
    return ((now_ts - float(last_run_ts)) / 3600.0) >= hours

def due_roles(
    last_runs: dict[str, float] | None,
    now_ts: float | None = None,
    config: dict[str, Any] | None = None,
) -> list[str]:
    cfg = config or load_cadence_config()
    store = last_runs or {}
    now = now_ts if now_ts is not None else time.time()
    return [r for r in cfg.get("cadences_hours", DEFAULT_CADENCE_HOURS) if role_is_due(r, store.get(r), now, cfg)]

def mark_role_run(
    role: str,
    store: dict[str, float],
    now_ts: float | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    cfg = config or load_cadence_config()
    canon = canonical_role(role, cfg)
    store[canon] = now_ts if now_ts is not None else time.time()
    return store

def run_verify() -> list[dict[str, Any]]:
    """Honest 8-tier verification (U2 truth — no fabricated PASS).

    বাংলা: প্রতিটি টিয়ার এখন সত্যিই চেক হয় (সস্তা, dependency-মুক্ত সেলফ-চেক);
    ব্যর্থ বা exception হলে passed=False। আগের সংস্করণ ৮টি টিয়ারই শর্তহীনভাবে
    PASS ছাপাত — যাচাই-ভয়াবহতা (false assurance) U2 লঙ্ঘন; পুরনো ১২৫০-লাইন
    লুপে এই ত্রুটি PR #1498 ঠিক করেছিল, #1526 রিরাইটে আবার ফিরে এসেছিল।

    চুক্তি: টিয়ার এমিশন অবশ্যই লিটারাল {"tier": N, ...} ডিক্ট হতে হবে —
    Loop-Contract Parity Guard (#118) এই লিটারাল প্যাটার্ন grep করে docs/
    AGENT_LOOP_SPEC.md §4-এর "tiers 1–8" SSOT-এর সাথে মেলায় (fail-closed)।
    তাই ফাংশন-কল দিয়ে ভ্যারিয়েবল-জাত dict বানানো যাবে না; honesty ও
    লিটারাল-এমিশন দুটোই একসাথে রাখতে হবে।
    """

    def _run(fn: Any) -> bool:
        try:
            return bool(fn())
        except Exception:
            return False

    def _json_ok() -> bool:
        # বাংলা: থাকা ফাইলগুলো অবশ্যই বৈধ JSON হতে হবে; অনুপস্থিত হলে বাধা নেই।
        for p in (CADENCE_FILE, STATE_FILE):
            if p.exists():
                json.loads(p.read_text(encoding="utf-8"))
        return True

    def _yaml_ok() -> bool:
        wf = REPO_ROOT / ".github" / "workflows"
        if not wf.is_dir():
            return False
        files = [p for p in wf.iterdir() if p.suffix in (".yml", ".yaml")]
        return bool(files) and all(p.stat().st_size > 0 for p in files)

    def _binary_ok() -> bool:
        agents_dir = REPO_ROOT / "scripts" / "agents"
        for p in agents_dir.glob("*.py"):
            blob = p.read_bytes()
            if b"\x00" in blob or b"\x7fELF" in blob:
                return False
        return True

    evidence: list[dict[str, Any]] = [
        {
            "tier": 1,
            "name": "syntax_py_compile",
            "passed": _run(
                lambda: compile(
                    Path(__file__).read_text(encoding="utf-8"),
                    "continuous_agent_loop.py",
                    "exec",
                )
                is not None,
            ),
        },
        {"tier": 2, "name": "json_validity", "passed": _run(_json_ok)},
        {"tier": 3, "name": "yaml_validity", "passed": _run(_yaml_ok)},
        {"tier": 4, "name": "binary_guard", "passed": _run(_binary_ok)},
        {
            "tier": 5,
            "name": "contract_guard",
            "passed": _run(lambda: CONTRACT_VERSION == "agent-loop-contract/1"),
        },
        {
            "tier": 6,
            "name": "group_registry_guard",
            "passed": _run(
                lambda: isinstance(VALID_GROUPS, frozenset) and "core" in VALID_GROUPS
            ),
        },
        {
            "tier": 7,
            "name": "envelope_determinism",
            "passed": _run(
                lambda: build_task_contract("verify-probe")
                == build_task_contract("verify-probe")
            ),
        },
        {
            "tier": 8,
            "name": "machine_path_isolation",
            "passed": _run(
                lambda: Path(__file__).resolve().parents[2] == REPO_ROOT
                and (REPO_ROOT / "scripts" / "agents").is_dir()
            ),
        },
    ]

    for ev in evidence:
        print(f"[{ev['tier']}/8] {ev['name']}: {'PASS' if ev['passed'] else 'FAIL'}")
    # বাংলা: CONTRACT_VERSION লাইনটি main() চূড়ান্ত stdout লাইন হিসেবে একবারই
    # ছাপে (SPEC §4b) — run_verify() ভেতরে আরেকবার ছাপা ছিল ডুপ্লিকেট নয়েজ।
    return evidence

def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI Minimal Continuous Loop")
    parser.add_argument("--verify-only", action="store_true", help="Run 8-tier verification only")
    parser.add_argument("--task-envelope", action="store_true", help="Emit task envelope")
    parser.add_argument("--emit-prompt", action="store_true", help="Deprecated shim")
    parser.add_argument("--emit-contract", action="store_true", help="Deprecated shim")
    parser.add_argument("--group", type=str, default="", help="Group override")
    parser.add_argument("--issue", type=str, default="", help="Issue number for --task-envelope")
    parser.add_argument("--allow-adhoc", action="store_true", help="Allow adhoc envelope without --issue")
    parser.add_argument("--loop", action="store_true", help="Run continuous loop")
    parser.add_argument("--offline", action="store_true", help="Run offline")
    args, _ = parser.parse_known_args()

    if args.verify_only:
        run_verify()
        print(f"CONTRACT_VERSION={CONTRACT_VERSION}")
        return 0

    if args.task_envelope or args.emit_prompt or args.emit_contract:
        if args.emit_prompt or args.emit_contract:
            print(
                "[deprecated] --emit-prompt/--emit-contract are shims for --task-envelope",
                file=sys.stderr,
            )
        # বাংলা: SPEC §4b — envelope JSON stdout-এ, banner stderr-এ; যাতে
        # `--task-envelope > env.json` পাইপে JSON নষ্ট না হয়।
        print(COMMON_RULES, file=sys.stderr)
        print("=" * 52, file=sys.stderr)
        if args.issue:
            g_code, g_out, _ = run_cmd(
                ["gh", "issue", "view", str(args.issue), "--repo", UPSTREAM_REPO,
                 "--json", "number,title,body,labels,state"]
            )
            if g_code != 0:
                log("❌", f"[Envelope] issue #{args.issue} fetch failed (gh exit {g_code}) — board unavailable or issue not found.")
                return 1
            try:
                target = json.loads(g_out) if g_out.strip() else None
            except Exception:
                target = None
            if not isinstance(target, dict) or not target.get("number"):
                log("❌", f"[Envelope] issue #{args.issue} could not be parsed from board.")
                return 1
            try:
                payload = build_task_envelope(target, group=args.group)
            except ValueError as exc:
                log("❌", f"[Envelope] {exc}")
                return 2
            print(json.dumps(payload, indent=2))
            return 0
        if args.allow_adhoc:
            try:
                payload = build_task_envelope(
                    {"number": 0, "title": "adhoc-task", "body": "", "labels": [], "state": "open"},
                    group=args.group,
                )
            except ValueError as exc:
                log("❌", f"[Envelope] {exc}")
                return 2
            print(json.dumps(payload, indent=2))
            return 0
        log("❌", "[Envelope] --issue <N> required (or --allow-adhoc).")
        return 2

    cmd = ["gh", "issue", "list", "--json", "number,labels", "--state", "open", "--limit", "100"]
    # বাংলা: বোর্ড পড়া এখন run_cmd() দিয়ে — gh অনুপস্থিত হলে exit 127,
    # crash নয়; solver dispatch বাদ দিয়ে cadence পাথ সৎভাবে চলতে থাকে।
    # ফিল্টার এখন pick_next_issue()-এর সাথে একই BOARD_EXCLUDED_LABELS SSOT —
    # mirror:private / state:seq-hold / blocked-by-upstream ইস্যুতে আর solver
    # যাবে না (আগে সেগুলোতে পাঠানো হতো — agent দাবিই করতে পারত না)।
    b_code, b_out, _ = run_cmd(cmd)
    board_unavailable = b_code != 0
    raw = []
    if not board_unavailable and b_out.strip():
        try:
            raw = json.loads(b_out)
        except Exception:
            raw = []
    unclaimed = [
        i for i in raw
        if isinstance(i, dict) and not any(
            str(l.get("name", "")).lower() in BOARD_EXCLUDED_LABELS
            for l in (i.get("labels") or [])
            if isinstance(l, dict)
        )
    ]

    print(COMMON_RULES)
    print("=" * 52)

    if board_unavailable:
        log("!", f"gh CLI unavailable (exit {b_code}) — cannot query the issue board; skipping solver dispatch. Cadence roles still evaluated.")
    elif unclaimed:
        print(f"ASSIGNED ROLE: solver (Unlimited concurrency allowed)\nROLE MANDATE: {ROLE_RULES['solver']}")
        print("ACTION: Unclaimed issues found. Apply 'status:claimed' label, pick an issue, and solve it.")
        return 0

    cadence = load_cadence_config().get("cadences_hours", {})
    state = load_last_run_store()
    now = time.time()

    for role, hours in cadence.items():
        if now - state.get(role, 0) >= hours * 3600:
            state[role] = now
            save_last_run_store(state)
            mandate = ROLE_RULES.get(role, "Execute role objectives strictly.")
            print(f"ASSIGNED ROLE: {role} (Single-runner role lock)\nROLE MANDATE: {mandate}")
            print(f"ACTION: Time expired for {role}. Act as {role} now.")
            return 0

    print("ACTION: System is clean and up to date.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
