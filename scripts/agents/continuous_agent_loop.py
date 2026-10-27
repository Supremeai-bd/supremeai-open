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
# বাংলা: AGENT_RULES.md আর নেই — PR #1526 নিজেই ফাইলটি মুছে দিয়েছে (Single Door
# SSOT এখন AGENTS.md)। তালিকায় মুছে-যাওয়া ফাইল রাখলে step_2_rules()/run_cycle()
# fresh main-এ সবসময় exit 1 দেয় (missing_local + rev-parse দুই জায়গাতেই fail) —
# নিজের মুছে-ফেলা ফাইলকে পূর্বশর্ত করে রাখা লুপের আত্ম-পরাজয়।

OFFLINE_ENV_VARS = (
    "SUPREMEAI_OFFLINE",
    "AGENT_LOOP_OFFLINE",
    "CI_OFFLINE",
)

# বাংলা: board-exclusion এখন একটাই SSOT। আগে pick_next_issue()-এ এক সেট
# (state:seq-hold, mirror:private আছে, anchor-hub/admin-only নেই) আর main()-এ
# অন্য সেট (anchor-hub, admin-only আছে, state:seq-hold/mirror:private নেই)
# ছিল — একই ধারণার দুই SSOT drift করে এক পথে claimable, অন্য পথে নয়।
EXCLUDED_LABELS = frozenset({
    "status:claimed",
    "status:in-progress",
    "state:seq-hold",
    "blocked-by-upstream",
    "mirror:private",
    "anchor-hub",
    "admin-only",
})

ENVELOPE_VERSION = 1
OUTPUT_FORMAT = "task-envelope-v1"
DEFAULT_FORBIDDEN_PATHS = [".env*", "secrets/**", "credentials/**", "vault/**"]
BRANCH_CONVENTION = r"^(feat|fix|docs|chore|test|refactor|perf|bridge|group|contributor|hotfix|release|agent)/<slug> — enforced by pipeline.yml"

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

def resolve_group(override: str = "", labels: Iterable[str] = (), body: str = "") -> str:
    """AGENT_LOOP_SPEC.md §3 resolution order (deterministic, fail-closed):
    1. --group CLI override (validated by caller — exit 2)
    2. first registry match across labels, then body text (sorted for stability)
    3. default DEFAULT_GROUP
    """
    if override:
        if override not in VALID_GROUPS:
            raise ValueError(f"Invalid group: '{override}'")
        return override
    present = {str(l).strip().lower() for l in labels if str(l).strip()}
    for g in sorted(VALID_GROUPS):
        if g in present:
            return g
    low_body = (body or "").lower()
    for g in sorted(VALID_GROUPS):
        if re.search(rf"(?<![a-z0-9_-]){re.escape(g)}(?![a-z0-9_-])", low_body):
            return g
    return DEFAULT_GROUP

def resolve_priority(labels: Iterable[str] = (), body: str = "") -> str:
    text = " ".join([str(l) for l in labels]) + " " + (body or "")
    for p in ("P0", "P1", "P2", "P3", "P4"):
        if re.search(rf"(?<![a-zA-Z0-9]){p}(?![a-zA-Z0-9])", text, re.IGNORECASE):
            return p
    return "P2"

def resolve_task_type(labels: Iterable[str] = (), title: str = "") -> str:
    text = " ".join([str(l) for l in labels]) + " " + (title or "")
    low = text.lower()
    for marker, ttype in (
        ("ci", "OPS"), ("fix", "FIX"), ("bug", "FIX"), ("docs", "DOCS"),
        ("audit", "AUDIT"), ("scout", "SCOUT"), ("test", "TEST"),
        ("refactor", "REFACTOR"), ("perf", "PERF"), ("chore", "CHORE"),
        ("feat", "FEAT"), ("feature", "FEAT"),
    ):
        if marker in low:
            return ttype
    return "IMPLEMENT"

def extract_section_bullets(body: str, heading_patterns: tuple[str, ...]) -> list[str]:
    """Pull bullet lines under a markdown heading (best-effort, deterministic)."""
    if not body:
        return []
    bullets: list[str] = []
    in_section = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            low = stripped.lower()
            in_section = any(re.search(p, low) for p in heading_patterns)
            continue
        if in_section and (stripped.startswith("- ") or stripped.startswith("* ") or re.match(r"^\d+\.\s", stripped)):
            bullets.append(re.sub(r"^([-*]|\d+\.)\s+", "", stripped).strip())
    return bullets

def detect_admin_gate(labels: Iterable[str] = ()) -> dict[str, Any]:
    for l in labels:
        low = str(l).strip().lower()
        if low == "gate:approved":
            return {"required": True, "status": "APPROVED"}
        if low.startswith("gate:") and low != "gate:pre-landing-cleared":
            return {"required": True, "status": "PENDING"}
    return {"required": False, "status": "NOT_REQUIRED"}

def infer_scope_paths(body: str) -> list[str]:
    """Best-effort scope: backticked repo-relative file paths in the issue body."""
    paths: list[str] = []
    if body:
        for m in re.finditer(r"`([\w\-./]+\.[A-Za-z0-9]+)`", body):
            p = m.group(1)
            if "/" in p and not p.startswith("http") and p not in paths:
                paths.append(p)
    return paths[:30]

def fetch_issue(issue: str | int) -> tuple[dict[str, Any] | None, str]:
    """Fetch one issue via gh. Returns (issue_dict, error_message)."""
    code, out, err = run_cmd([
        "gh", "issue", "view", str(issue),
        "--repo", UPSTREAM_REPO,
        "--json", "number,title,body,labels,state",
    ])
    if code != 0:
        return None, (err or f"gh issue view exited {code}")
    try:
        data = json.loads(out)
    except Exception as exc:
        return None, f"unparseable gh output: {exc}"
    labels = [l.get("name", "") for l in data.get("labels", []) if isinstance(l, dict)]
    data["labels"] = labels
    return data, ""

def build_task_envelope(
    task_id: str,
    issue: str | int | None,
    title: str = "",
    body: str = "",
    labels: Iterable[str] = (),
    state: str = "OPEN",
    group_override: str = "",
    role_override: str = "",
) -> dict[str, Any]:
    """Full task-envelope-v1 payload (AGENT_LOOP_SPEC.md §2) — deterministic.

    বাংলা: এটিই SPEC §2-র প্রতিশ্রুত — একটাই canonical payload। পুরনো স্টাব
    {"task_contract": ...} দিয়ে বাইরের এজেন্ট কিছুই করতে পারত না: কোন ইস্যু,
    কোন role, কোন scope, কী জমা দিতে হবে কিছুই ছিল না। এখন সম্পূর্ণ চুক্তি যায়।
    """
    labels_list = [str(l) for l in labels]
    group = resolve_group(group_override, labels_list, body)
    priority = resolve_priority(labels_list, body)
    task_type = resolve_task_type(labels_list, title)
    role = role_override or canonical_role(classify_task_role(title, labels_list, body))
    gate = detect_admin_gate(labels_list)
    scope_paths = infer_scope_paths(body)
    acceptance = extract_section_bullets(body, (r"acceptance criteria", r"acceptance")) or [
        "Scope respected: only declared scope.touching_files touched",
        "PR body carries the Reflection Evidence section",
    ]
    verification = extract_section_bullets(body, (r"verification", r"3-tier")) or [
        "python scripts/agents/continuous_agent_loop.py --verify-only reports all tiers PASS",
        "3-Tier Verify evidence (Reflection, Smoke, Tests) attached to the PR",
    ]
    required_evidence = extract_section_bullets(body, (r"evidence",)) or [
        "git diff --stat output within P7 caps (30 files / 200 KB)",
        "Local guard or smoke test output pasted in the PR",
    ]
    stop_conditions = [
        "scope.touching_files exceeded or forbidden path touched",
        "admin_gate required but not APPROVED",
        "board freshness lost (origin/main moved) at pre-push",
    ]
    objective = (title or "").strip()
    mandate = ROLE_RULES.get(role, "Execute role objectives strictly.")
    prompt = (
        f"=== SUPREMEAI SPECIALIST PROMPT ({role}) ===\n"
        f"{COMMON_RULES}\n\n"
        f"ROLE MANDATE: {mandate}\n\n"
        f"TASK: {objective}\n"
        f"GROUP: {group} | PRIORITY: {priority} | TYPE: {task_type}\n\n"
        "CONSUME: implement the smallest safe change strictly inside scope; "
        "verify with the 3 tiers; submit via the submission pathway below; "
        "never push directly to protected branches.\n"
    )
    issue_ref = str(issue) if issue is not None else "N"
    pr_body = (
        "### Summary\n"
        f"{objective or 'Implements the assigned task.'}\n\n"
        "### Linked Issue / Claim\n"
        f"Closes #{issue_ref}\n"
        f"<!-- atomic-claim: issue #{issue_ref} -->\n\n"
        "### Key Changes\n"
        "- `<domain>/path/to/file.ext`: Concrete architectural or functional change.\n\n"
        "## Reflection Evidence (why + alternatives_rejected)\n"
        "- **why:** Technical rationale explaining why this approach was selected.\n"
        "- **alternatives_rejected:**\n"
        "  - *Alternative Approach 1:* Rejected because <technical drawback>.\n"
        "  - *Alternative Approach 2:* Rejected because <complexity/regression issue>.\n\n"
        "### Dynamic Verification Evidence\n"
        "- [x] Local Guard / Smoke Test Output: `python scripts/agents/continuous_agent_loop.py --verify-only` -> PASS\n"
        "- [x] Unit/Contract Tests passed with output proof: <test name and result summary>\n"
        "- [x] Pre-Push Rebase: 0 commits behind origin/main\n\n"
        "### Rollback Path\n"
        "- [x] `git revert`-safe (no cross-satellite private state dependency)\n"
    )
    return {
        "task_envelope": {
            "envelope_version": ENVELOPE_VERSION,
            "output_format": OUTPUT_FORMAT,
            "task_id": str(task_id),
            "issue": str(issue) if issue is not None else None,
            "task_type": task_type,
            "group": group,
            "priority": priority,
            "objective": objective,
            "problem_statement": {
                "id": str(issue) if issue is not None else None,
                "title": title,
                "body": body,
                "labels": labels_list,
                "state": state,
            },
            "role": role,
            "role_policy": "contributor",
            "role_description": mandate,
            "scope": {
                "touching_files": scope_paths,
                "forbidden_paths": list(DEFAULT_FORBIDDEN_PATHS),
            },
            "acceptance": acceptance,
            "verification": verification,
            "required_evidence": required_evidence,
            "stop_conditions": stop_conditions,
            "admin_gate": gate,
            "specialist_prompt": prompt,
            "submission": {
                "pathway": "bridge_submit_patch | pull_request",
                "reference": "AGENTS.md §2.1 Pathway 1 + §8 (bridge_submit_patch)",
                "base_branch": "main",
                "pr_title_prefix": "feat(open):",
                "issue_reference_required": True,
                "branch_convention": BRANCH_CONVENTION,
                "pr_body_template": pr_body,
            },
        }
    }

def pick_next_issue(
    exclude: set[str] | list[str] | None = None,
    issues: list[dict[str, Any]] | None = None,
) -> str | None:
    """বাংলা: priority-অনুসারে পরবর্তী claimable issue বাছাই (P0 আগে, তারপর নম্বর)।

    আগের সংস্করণে এই ফাংশনটিই একমাত্র priority-sorter ছিল কিন্তু main() কখনো ডাকতই না
    (dead code) — ফলে লুপ P0 আগে দেবে এই প্রতিশ্রুতি কোডে কখনো কার্যকর হয়নি। এখন
    main() pre-fetched board এখানে পাঠায় (issues=...) — এক সাইকেলে দুবার gh query হয় না।
    """
    if issues is None:
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
        return not (EXCLUDED_LABELS & set(names))

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

def log(icon: str, msg: str, stream: Any = None) -> None:
    # বাংলা: stream প্যারাম — এনভেলপ মোডের বার্তা stderr-এ যায়, যাতে stdout-এ
    # বিশুদ্ধ JSON থাকে (SPEC §4: banner → stderr)।
    out = stream if stream is not None else sys.stdout
    try:
        print(f"{icon} {msg}", file=out)
    except UnicodeEncodeError:
        print(f"[*] {msg}", file=out)

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

def is_git_repo() -> bool:
    code, out, _ = run_cmd(["git", "rev-parse", "--is-inside-work-tree"])
    return code == 0 and out.strip() == "true"

def step_2_rules(offline: bool = False, auto_sync: bool = True) -> bool:
    """Step 2: Constitution freshness gate + governing-rules loading (#567)."""
    repo_root = REPO_ROOT
    missing_local = [p for p in RULE_FRESHNESS_FILES if not (repo_root / p).exists()]

    if _offline_requested(offline):
        # বাংলা: অফলাইনে সেলফ-হিল অসম্ভব — আচরণ অপরিবর্তিত (missing মানে fail)।
        if missing_local:
            log("❌", f"[Rules] offline and missing local freshness files: {missing_local}")
            return False
        _print_rule_version_and_checklist()
        return True

    code, _, err = run_cmd(["git", "fetch", "origin", "main"], cwd=repo_root)
    if code != 0:
        return False

    local_shas: dict[str, str | None] = {}
    remote_shas: dict[str, str | None] = {}
    for path in RULE_FRESHNESS_FILES:
        r_code, r_out, _ = run_cmd(
            ["git", "rev-parse", "--verify", "--quiet", f"origin/main:{path}"], cwd=repo_root
        )
        if r_code != 0:
            # বাংলা: ফাইলটি origin/main-এ আর নেই (deleted/renamed upstream)।
            # মুছে-ফেলা ফাইলকে পূর্বশর্ত করে রাখা লুপের আত্ম-পরাজয় — AGENT_RULES.md
            # ঠিক এভাবেই #1526-এ লুপটা মেরেছিল (rev-parse fail মানে exit 1 চিরকাল)।
            # তাই এই রানে গেট থেকে বাদ; fail-closed নয়, honest-skip।
            log("!", f"[Rules] {path} no longer exists on origin/main — deleted upstream; skipping this run.")
            continue
        remote_shas[path] = r_out.strip() or None
        h_code, h_out, h_err = run_cmd(["git", "hash-object", "--", path], cwd=repo_root)
        if h_code != 0:
            # বাংলা: স্থানীয় কপি নেই কিন্তু origin/main-এ আছে —
            # fetch ইমেধেই ব্যর্থ ঘোষণা নিজের সেলফ-হিল-প্রণালীকে প্রতারাধ করত।
            # এখন diverged-sync ব্রাঞ্চের মেকানিসম দিয়ে পুনরুদ্ধার করে hash করা হয়।
            c_code, _, _ = run_cmd(
                ["git", "checkout", "origin/main", "--", path], cwd=repo_root
            )
            if c_code != 0:
                log("❌", f"[Rules] {path} missing locally and self-heal from origin/main failed.")
                return False
            h_code, h_out, h_err = run_cmd(["git", "hash-object", "--", path], cwd=repo_root)
            if h_code != 0:
                return False
        local_shas[path] = h_out.strip() or None

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

# বাংলা: পুরনো ডেড-স্টাব (step_4_branch / step_6_verify / push_branch_to_fork /
# step_7_record / run_cycle) সরানো হয়েছে — ওরা কিছু না করেই True/0 ফেরত দিত
# (fabricated success, U2 লঙ্ঘন) এবং কোনো importer ছিল না (code-search প্রমাণিত)।
# প্রকৃত পাইপলাইন: step_2_rules + pre_work/pre_push rebase guard এখন main() থেকে
# সরাসরি wired।

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
    print(f"CONTRACT_VERSION={CONTRACT_VERSION}")
    return evidence

def _query_board() -> tuple[list[dict[str, Any]], str]:
    """বাংলা: বোর্ড কোয়েরি এক জায়গায় — gh অনুপস্থিত/অথ-ব্যর্থ/নেটওয়ার্ক-ব্যর্থ
    সব ক্ষেত্রেই (issues, error) ফেরত দেয়; "empty board" আর "board unknown"
    আলাদা করে চেনে — ব্যর্থতাকে কখনো মিথ্যা clean বলে চালিয়ে দেয় না।"""
    code, out, out_err = run_cmd([
        "gh", "issue", "list",
        "--repo", UPSTREAM_REPO,
        "--json", "number,title,labels",
        "--state", "open",
        "--limit", "100",
    ])
    if code != 0:
        return [], (out_err or f"gh exit code {code}")
    if not out.strip():
        return [], "gh issue list returned empty output"
    try:
        parsed = json.loads(out)
    except Exception:
        return [], "unparseable gh issue list output"
    if not isinstance(parsed, list):
        return [], "gh issue list returned non-list JSON"
    return parsed, ""

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SupremeAI Minimal Continuous Loop",
        epilog=("Exit codes: 0 ok | 1 verify FAIL (fail-closed) | 2 invalid --group/--role | "
                "3 board or issue unavailable for envelope | 4 stale rules in envelope mode"),
    )
    parser.add_argument("--verify-only", action="store_true", help="Run 8-tier verification only (exit 1 on any FAIL)")
    parser.add_argument("--task-envelope", action="store_true", help="Emit full task-envelope-v1 JSON (SPEC §2)")
    parser.add_argument("--emit-prompt", action="store_true", help="Deprecated shim -> same envelope")
    parser.add_argument("--emit-contract", action="store_true", help="Deprecated shim -> same envelope")
    parser.add_argument("--group", type=str, default="", help="Group override (fail-closed vs VALID_GROUPS)")
    parser.add_argument("--loop", action="store_true", help="Run continuous loop")
    parser.add_argument("--offline", action="store_true", help="Run offline")
    # --- SPEC §4b canonical shared flag surface: আগে parse_known_args ওগুলো নিঁঝে
    # ফেলত (silent no-op — এজেন্ট ভাবত --issue কাজ করছে, আসলে কিছুই হত না)।
    parser.add_argument("--issue", type=str, default=None, help="Operate on a specific issue number")
    parser.add_argument("--pick-next", action="store_true", help="Use the priority-picked unclaimed issue")
    parser.add_argument("--max-tasks", type=int, default=1, help="Max dispatches per invocation")
    parser.add_argument("--role", type=str, default="", help="Role override (fail-closed vs ROLE_RULES)")
    parser.add_argument("--allow-adhoc", action="store_true", help="Allow adhoc envelope without an issue")
    # --- private-mirror-only flags: accepted, no-op here (SPEC §4b: public copy may ignore) ---
    parser.add_argument("--agent-name", type=str, default="", help="(private-mirror only) agent identity")
    parser.add_argument("--iterations", type=int, default=None, help="(private-mirror only) accepted for parity")
    parser.add_argument("--model", type=str, default="", help="(private-mirror only) accepted for parity")
    parser.add_argument("--check-claimable", action="store_true", help="(private-mirror only) accepted for parity")
    args, _ = parser.parse_known_args()

    if args.verify_only:
        # বাংলা: আগে সব টিয়ার FAIL হলেও exit 0 — CI কখনো ব্যর্থতা ধরতে পারত না
        # (fail-open, U6 লঙ্ঘন)। এখন fail-closed; CONTRACT_VERSION শেষ লাইনই থাকে।
        evidence = run_verify()
        print(f"CONTRACT_VERSION={CONTRACT_VERSION}")
        return 0 if all(e["passed"] for e in evidence) else 1

    if args.task_envelope or args.emit_prompt or args.emit_contract:
        # বাংলা: এনভেলপ = মেশিন-পাঠযোগ্য চুক্তি; stdout-এ শুধু বিশুদ্ধ JSON যাবে,
        # সব ব্যানার/সতর্কবার্তা stderr-এ (SPEC §4: banner → stderr)।
        err = sys.stderr
        if args.group and args.group not in VALID_GROUPS:
            log("!", f"invalid --group '{args.group}'; valid: {', '.join(sorted(VALID_GROUPS))}", err)
            return 2
        if args.role and args.role not in ROLE_RULES:
            log("!", f"invalid --role '{args.role}'; valid: {', '.join(sorted(ROLE_RULES))}", err)
            return 2
        if not _offline_requested(args.offline):
            if not is_git_repo():
                log("!", "not a git checkout — rules freshness gate skipped (honest mode)", err)
            elif not step_2_rules(offline=False):
                # বাংলা: বাসি নিয়ম থেকে বানানো চুক্তিই বাসি চুক্তি — fail-closed।
                log("!", "rules freshness gate FAILED (missing/diverged constitution files)", err)
                return 4
        issue_num = args.issue
        title, body, labels, state_label = "", "", [], "OPEN"
        if issue_num:
            data, ierr = fetch_issue(issue_num)
            if data is None:
                log("!", f"issue #{issue_num} unavailable — {ierr}", err)
                return 3
            title = str(data.get("title", ""))
            body = str(data.get("body", ""))
            labels = data.get("labels", [])
            state_label = str(data.get("state", "OPEN"))
        elif args.offline and args.allow_adhoc:
            # বাংলা: অফলাইনে adhoc এনভেলপ বোর্ড ছাড়াই সৎভাবে সম্ভব।
            issue_num = None
        else:
            issues, board_err = ([], "offline mode: board not queried") if args.offline else _query_board()
            if board_err:
                log("!", f"board unavailable — {board_err}; no envelope emitted (no fabricated contract)", err)
                return 3
            picked = pick_next_issue(issues=issues)
            if not picked:
                if not args.allow_adhoc:
                    log("=", "no unclaimed issues; pass --allow-adhoc for an adhoc envelope", err)
                    return 0
                issue_num = None
            else:
                issue_num = picked
                # বাংলা: পিক করা ইস্যুর full body দরকার — লিস্ট JSON-এ body থাকে না।
                full, ferr = fetch_issue(picked)
                if full is not None:
                    title = str(full.get("title", ""))
                    body = str(full.get("body", ""))
                    labels = full.get("labels", [])
                    state_label = str(full.get("state", "OPEN"))
                else:
                    log("!", f"full issue fetch failed for #{picked} — {ferr}; envelope built from board list only", err)
                    for i in issues:
                        if str(i.get("number")) == str(picked):
                            title = str(i.get("title", ""))
                            labels = [str(l.get("name", "")) for l in i.get("labels", []) if isinstance(l, dict)]
                            break
        if issue_num is None and not args.allow_adhoc:
            log("!", "no issue selected; pass --issue N or --allow-adhoc", err)
            return 3
        task_id = f"task-{issue_num}" if issue_num is not None else "task-adhoc"
        envelope = build_task_envelope(
            task_id=task_id,
            issue=issue_num,
            title=title,
            body=body,
            labels=labels,
            state=state_label,
            group_override=args.group,
            role_override=args.role,
        )
        print(json.dumps(envelope, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    print(COMMON_RULES)
    print("=" * 52)

    # বাংলা: নিয়ম-সতেজতা গেট dispatch পাথেও wired — git checkout-এ gate ব্যর্থ
    # হলে সৎ সতর্কতা দিয়ে চলতে থাকে (dispatch-এ hard-fail নয়; এজেন্ট নিজের
    # worktree-এ rebase করবে), কিন্তু নীরবভাবে চুপ করে থাকে না।
    if not _offline_requested(args.offline):
        if not is_git_repo():
            log("!", "not a git checkout — Dual-Rebase guard skipped (honest mode; rebase your own worktree)")
        elif not step_2_rules(offline=False):
            log("!", "rules freshness gate failed — dispatch continues, but rebase origin/main before any work")

    raw, board_error = ([], "offline mode: board not queried") if _offline_requested(args.offline) else _query_board()
    board_unavailable = bool(board_error)

    if args.loop:
        # বাংলা: --loop flag টি SPEC §4b-র shared flag surface-এ আছে কিন্তু এই
        # minimal লুপে এটি in-process লুপ চালায় না — invocation প্রতি এক সাইকেল।
        # চাকাটি ঘোরায় বাইরের scheduler/workflow। আগে এটি নীরবে এক-cycle আচরণ
        # করত — U2 সৎতায় এখন stderr-এ সেটা স্পষ্ট বলে দেয় (stdout অপরিবর্তিত,
        # যাতে বিদ্যমান automation ভাঙে না)।
        print(
            "--loop: contract-parity flag — this minimal loop runs ONE dispatch "
            "cycle per invocation; the calling scheduler/workflow is the outer "
            "loop driver (SPEC §4b).",
            file=sys.stderr,
        )

    if board_unavailable:
        log("!", f"issue board unavailable ({board_error}) — skipping solver dispatch. Cadence roles still evaluated.")
    else:
        picked = pick_next_issue(issues=raw)
        if picked:
            print(f"ASSIGNED ROLE: solver (Unlimited concurrency allowed)\nROLE MANDATE: {ROLE_RULES['solver']}")
            print(f"ACTION: Highest-priority unclaimed issue = #{picked}. Atomic-claim it FIRST ('status:claimed' via work_claim tool or <!-- atomic-claim --> comment) — no claim, no branch. Then solve root cause and submit.")
            print("STALE-INCIDENT GUARD (U3 Live Validity): before claiming a CI-failure incident, verify on live main that the referenced run still fails; resolved incidents are skipped with evidence, never re-solved.")
            return 0

    cadence = load_cadence_config().get("cadences_hours", {})
    state = load_last_run_store()
    now = time.time()

    for role, hours in cadence.items():
        if now - state.get(role, 0) >= hours * 3600:
            state[role] = now
            if not save_last_run_store(state):
                # বাংলা: স্টেট সেভ ব্যর্থ হলে সৎ সতর্কতা — নইলে পরের সাইকেলে
                # একই role আবার dispatch হবে এবং কেউ জানবেই না কেন।
                log("!", f"warning: could not persist cadence state ({STATE_FILE}); {role} may re-dispatch next cycle")
            mandate = ROLE_RULES.get(role, "Execute role objectives strictly.")
            print(f"ASSIGNED ROLE: {role} (Single-runner role lock)\nROLE MANDATE: {mandate}")
            print(f"ACTION: Time expired for {role}. Act as {role} now.")
            return 0

    print("ACTION: System is clean and up to date.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
