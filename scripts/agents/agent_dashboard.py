#!/usr/bin/env python3
"""scripts/agents/agent_dashboard.py — real-time agent activity dashboard (#1635).

বাংলা: কোন agent স্লট active/idle/stale, কোন issue কে claim করেছে, কতক্ষণ
ধরে আছে, linked open PR আছে কিনা — এক নজরে। এতে accidental double-claim আর
stale lock এর হাতে-কলমে cross-reference (`gh issue list` + `gh pr list` +
registry YAML) দরকার হয় না।

Data sources (all read-only):
  1. docs/master_docs/AGENT_SLOT_REGISTRY.yaml — canonical roster
     (legacy `slots:` + dynamic `role_pools:` branch patterns)
  2. `gh issue list --label status:in-progress` + per-issue atomic-claim
     marker comment (claimant + claimed-at)
  3. `gh pr list --state open` (head branch → slot mapping)

Usage:
  python scripts/agents/agent_dashboard.py                 # table (per #1635)
  python scripts/agents/agent_dashboard.py --json          # machine-readable
  python scripts/agents/agent_dashboard.py --stale-hours 4
  python scripts/agents/agent_dashboard.py --offline       # roster only

Exit codes: 0 ok (including offline), 2 bad args.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    import yaml  # PyYAML — already used by repo tooling
except ImportError:  # pragma: no cover
    yaml = None

ROOT_DIR = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT_DIR / "docs" / "master_docs" / "AGENT_SLOT_REGISTRY.yaml"

# Atomic-claim marker posted by scripts/ci/atomic_claim.sh (GAP-01).
CLAIM_MARKER_RE = re.compile(r"Atomic Claim", re.IGNORECASE)
CLAIM_AGENT_RE = re.compile(r"\*\*Agent:\*\*\s*`([^`]+)`")
CLAIM_TIME_RE = re.compile(r"\*\*Claimed at:\*\*\s*(.+)")

STALE_DEFAULT_HOURS = 4.0


# ──────────────────────────────────────────────────────────── data model ──
class Slot:
    """One roster row — legacy slot or dynamic pool slot (post-migration)."""

    def __init__(self, name: str, role: str, bot_identity: str = ""):
        self.name = name.strip()
        self.role = role.strip()
        self.bot_identity = (bot_identity or "").strip()
        # Branch prefixes that belong to this slot (PR head-branch matching).
        self.branch_tokens: set[str] = set()

    # -- identity matching (claimant comments) ----------------------------
    @property
    def identity_tokens(self) -> list[str]:
        toks = [self.name]
        if self.role:
            toks.append(self.role)
        if self.bot_identity:
            toks.append(self.bot_identity)
            toks.append(self.bot_identity.replace("[bot]", ""))
        return toks

    def add_branch_token(self, tok: str) -> None:
        if tok and tok.strip():
            self.branch_tokens.add(tok.strip())

    def matches_claimant(self, claimant: str) -> bool:
        """Exact / prefix / suffix match only — substring-bounded matching is
        intentionally limited to the slot NAME, so a pool-role token like
        'coder' can never glom onto 'agent-3-coder-1' (phantom claims)."""
        cands = [
            c
            for c in (claimant.strip().lower(), self._normalize_claimant(claimant))
            if c
        ]
        for tok in self.identity_tokens:
            t = tok.strip().lower()
            if not t:
                continue
            for c in cands:
                if c == t or c.startswith(t + "-") or c.endswith("-" + t):
                    return True
                if t == self.name.lower() and f"-{t}-" in c:
                    return True  # bounded substring — slot name only
        return False

    @staticmethod
    def _normalize_claimant(claimant: str) -> str:
        """Bot login → slot identity: 'supremeai-coder-1-bot[bot]' → 'coder-1'."""
        c = claimant.strip().lower().replace("[bot]", "")
        for prefix in ("supremeai-",):
            c = c.removeprefix(prefix)
        for suffix in ("-bot",):
            c = c.removesuffix(suffix)
        return c.strip("-")

    def matches_branch(self, branch: str) -> bool:
        b = branch.strip().lower()
        for tok in sorted(self.branch_tokens, key=len, reverse=True):
            t = tok.lower()
            if b == t or b.startswith((t + "-", t + "_")):
                return True
        return False

    def as_dict(self) -> dict:
        return {
            "slot": self.name,
            "role": self.role,
            "bot_identity": self.bot_identity,
            "branch_tokens": sorted(self.branch_tokens),
        }


# ──────────────────────────────────────────────────────────────── registry ──
def load_registry(path: Path = REGISTRY_PATH) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML required for registry parsing (pip install pyyaml)")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_roster(registry: dict) -> list[Slot]:
    """Legacy `slots:` (active) first — canonical order matching the registry."""
    roster: list[Slot] = []
    for s in registry.get("slots") or []:
        if not isinstance(s, dict) or not s.get("active", False):
            continue
        name = str(s.get("slot", "")).strip()
        if not name:
            continue
        role = str(s.get("tool") or s.get("legacy_migration_target") or name).strip()
        slot = Slot(name, role, str(s.get("bot_identity", "")))
        slot.add_branch_token(str(s.get("branch", "")))
        slot.add_branch_token(role)  # post-migration naming
        slot.add_branch_token(str(s.get("legacy_migration_target", "")))
        roster.append(slot)
    return roster


def discover_dynamic_slots(
    registry: dict, remote_branches: list[str], roster: list[Slot]
) -> list[Slot]:
    """Scan remote branches against each pool's `branch_pattern` (`pool-{N}`).

    A discovered slot merges into a legacy row when that legacy row's role /
    migration target equals the pool slot name (e.g. agent-3 ≡ coder-1);
    otherwise it becomes a new row (dynamic pools, issue #1800 Option D).
    """
    by_name = {s.name: s for s in roster}
    by_role = {s.role: s for s in roster}
    extra: list[Slot] = []

    for pool, cfg in (registry.get("role_pools") or {}).items():
        pattern = str((cfg or {}).get("branch_pattern", "")).strip()
        if "{N}" not in pattern:
            continue
        prefix = pattern.split("{N}")[0]  # 'coder-{N}' → 'coder-'
        for branch in remote_branches:
            if not branch.startswith(prefix):
                continue
            num = branch[len(prefix) :].split("-", 1)[0]
            if not num.isdigit():
                continue
            slot_name = pattern.replace("{N}", num)
            existing = by_name.get(slot_name) or by_role.get(slot_name)
            if existing is not None:
                existing.add_branch_token(prefix + num)
                continue
            new_slot = Slot(
                slot_name, str(pool), str((cfg or {}).get("bot_identity", ""))
            )
            new_slot.add_branch_token(prefix + num)
            roster.append(new_slot)
            by_name[slot_name] = new_slot
            by_role.setdefault(new_slot.role, new_slot)
            extra.append(new_slot)
    return extra


# ────────────────────────────────────────────────────────────── gh plumbing ──
def gh(*args: str, timeout: int = 30) -> str:
    """Run a read-only `gh` command; return stdout ('' on any failure)."""
    try:
        res = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=timeout, check=False
        )
        return res.stdout if res.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def gh_available() -> bool:
    """gh binary present AND authenticated (issue #2134).

    GH_TOKEN presence proves NOTHING about validity — an expired/rotated
    App installation token still passes `gh --version` (binary check only),
    which made every subsequent call fail silently and the dashboard render
    a false all-IDLE board. With a token set we verify it with a real
    authenticated call; `gh api user` is cheap and works for every token
    class that can read this repo's issues/PRs.
    """
    if bool(os.environ.get("GH_TOKEN")):
        return gh("api", "user", "--jq", ".login") != ""
    return gh("auth", "status") != ""


def fetch_remote_branches() -> list[str]:
    out = gh(
        "api",
        "repos/{owner}/{repo}/branches",
        "--paginate",
        "--jq",
        ".[].name",
        timeout=60,
    )
    return [b.strip() for b in out.splitlines() if b.strip()]


def fetch_in_progress_claims() -> list[dict]:
    """Open issues labelled status:in-progress + claimant/claimed-at parsed
    from the atomic-claim marker comment (see scripts/ci/atomic_claim.sh)."""
    raw = gh(
        "issue",
        "list",
        "--label",
        "status:in-progress",
        "--state",
        "open",
        "--json",
        "number,title,createdAt",
        "--limit",
        "100",
    )
    try:
        issues = json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError:
        issues = []

    claims: list[dict] = []
    for it in issues:
        num = it.get("number")
        body_raw = gh(
            "issue",
            "view",
            str(num),
            "--json",
            "comments",
            "--jq",
            '[.comments[].body] | join("\\n===\\n")',
        )
        agent, claimed_at = None, None
        for block in body_raw.split("\n===\n"):
            if CLAIM_MARKER_RE.search(block):
                m = CLAIM_AGENT_RE.search(block)
                t = CLAIM_TIME_RE.search(block)
                if m:
                    agent = m.group(1).strip()
                if t:
                    claimed_at = t.group(1).strip()
                break
        claims.append(
            {
                "issue": num,
                "title": it.get("title", ""),
                "created_at": it.get("createdAt", ""),
                "agent": agent,  # None → claim without marker (flagged)
                "claimed_at": claimed_at,
            }
        )
    return claims


def fetch_open_prs() -> list[dict]:
    raw = gh(
        "pr",
        "list",
        "--state",
        "open",
        "--json",
        "number,headRefName,title",
        "--limit",
        "200",
    )
    try:
        return json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError:
        return []


# ───────────────────────────────────────────────────────────── core logic ──
def parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    # Issue #2134: naive timestamps (space-separated, no zone — hand-edited
    # markers, older writers) must not crash aware-naive subtraction later;
    # assume UTC, the zone every writer in this repo uses.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def age_hours(ts: str, now: datetime) -> float | None:
    dt = parse_iso(ts)
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def fmt_age(hrs: float) -> str:
    if hrs < 1:
        return f"{int(hrs * 60)}m"
    if hrs < 48:
        return f"{hrs:.0f}h"
    return f"{hrs / 24:.0f}d"


def build_rows(
    roster: list[Slot],
    claims: list[dict],
    prs: list[dict],
    now: datetime,
    stale_hours: float,
) -> tuple[list[dict], list[str]]:
    """Join claims + PRs onto the roster; produce rows + warnings.

    Status: ACTIVE (claim or PR, healthy) / STALE (claim > stale_hours with
    no open PR) / IDLE (nothing). Claim age falls back to the issue's
    createdAt when the marker comment lacks a timestamp.
    """
    branch_to_slot: dict[str, Slot] = {}
    for slot in roster:
        for tok in slot.branch_tokens:
            branch_to_slot.setdefault(tok.lower(), slot)

    prs_by_slot: dict[str, list[dict]] = {}
    for pr in prs:
        branch = str(pr.get("headRefName", ""))
        owner = None
        for tok, slot in sorted(branch_to_slot.items(), key=lambda kv: -len(kv[0])):
            if slot.matches_branch(branch):
                owner = slot
                break
        if owner is not None:
            prs_by_slot.setdefault(owner.name, []).append(pr)

    rows: list[dict] = []
    warnings: list[str] = []
    unknown: list[tuple[int, str]] = []
    matched_issues: set[int] = set()

    for slot in roster:
        my_claims = [
            c
            for c in claims
            if c.get("agent") and slot.matches_claimant(str(c["agent"]))
        ]
        my_prs = prs_by_slot.get(slot.name, [])

        issue_str, pr_str, age_str = "—", "—", "—"
        status = "IDLE"

        if my_claims:
            c = my_claims[0]  # ONE-ACTIVE-CLAIM (AGENTS.md §13) → first wins
            matched_issues.add(int(c["issue"]))
            issue_str = f"#{c['issue']}"
            hrs = age_hours(str(c.get("claimed_at") or c.get("created_at") or ""), now)
            if hrs is not None:
                age_str = fmt_age(hrs)
            if not my_prs and hrs is not None and hrs > stale_hours:
                status = "STALE"
                warnings.append(
                    f"⚠️  {slot.name} holds #{c['issue']} for {fmt_age(hrs)} "
                    f"with no open PR — possible stale lock (>{stale_hours:g}h)"
                )
            else:
                status = "ACTIVE"
            if len(my_claims) > 1:
                extras = ", ".join(f"#{x['issue']}" for x in my_claims[1:])
                warnings.append(
                    f"⚠️  {slot.name} holds multiple claims ({issue_str}, {extras}) "
                    "— violates ONE-ACTIVE-CLAIM rule"
                )

        if my_prs:
            pr_str = f"#{my_prs[0]['number']}"
            if status == "IDLE":
                status = "ACTIVE"

        rows.append(
            {
                "slot": slot.name,
                "role": slot.role,
                "status": status,
                "issue": issue_str,
                "pr": pr_str,
                "age": age_str,
                "stale": status == "STALE",
            }
        )

    for c in claims:  # claims nobody on the roster owns
        if int(c["issue"]) in matched_issues:
            continue
        who = c.get("agent") or "UNKNOWN-claimant"
        unknown.append((int(c["issue"]), who))
    if unknown:
        detail = ", ".join(f"#{n} ({w})" for n, w in unknown[:6])
        more = f" …+{len(unknown) - 6} more" if len(unknown) > 6 else ""
        warnings.append(
            f"⚠️  {len(unknown)} in-progress issue(s) with no roster-matched "
            f"claimant: {detail}{more} — investigate"
        )
    return rows, warnings


# ─────────────────────────────────────────────────────────────── rendering ──
HEADER_LINE = "━" * 60


# Short display labels for known pool/tool names (keeps the table aligned).
ROLE_LABELS = {
    "planner": "Planner",
    "planner-and-auditor": "Planner",
    "pr-helper": "PR Gate",
    "pr-helper-1": "PR Gate",
    "coder": "Coder",
    "ci": "CI/CD",
    "ci-action": "CI/CD",
    "platform": "Platform",
    "platform-agent": "Platform",
    "browser": "Browser",
    "browser-explorer": "Browser",
    "super": "Super",
}


def role_label(role: str) -> str:
    label = ROLE_LABELS.get(role.strip().lower())
    if label:
        return label
    # 'coder-1' → 'Coder'; anything else truncates to fit the column.
    base = role.split("-")[0].strip().lower()
    if base in ROLE_LABELS:
        return ROLE_LABELS[base]
    return role[:13]


def render_table(
    rows: list[dict], generated_at: datetime, offline: bool = False
) -> str:
    stamp = generated_at.strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"AGENT DASHBOARD — {stamp}"]
    if offline:
        lines.append("(offline mode: registry roster only — no live GitHub data)")
    lines.append(HEADER_LINE)
    lines.append(f"{'Slot':<18}{'Role':<15}{'Status':<10}{'Issue':<8}{'PR':<8}{'Age'}")

    shown: list[dict] = []
    idle_dynamic: list[str] = []
    for r in rows:
        # Legacy registry slots ('agent-*') always show; dynamic pool slots
        # collapse into a summary line when IDLE (zombie branches would
        # otherwise flood the table — #1635's goal is spotting ACTIVE/STALE).
        if r["slot"].startswith("agent-") or r["status"] != "IDLE":
            shown.append(r)
        else:
            idle_dynamic.append(r["slot"])

    for r in shown:
        lines.append(
            f"{r['slot']:<18}{role_label(r['role']):<15}{r['status']:<10}"
            f"{r['issue']:<8}{r['pr']:<8}{r['age']}"
        )
    if idle_dynamic:
        shown_ids = (
            f"+ {len(idle_dynamic)} idle pool slots ({', '.join(idle_dynamic[:3])}, …)"
        )
        lines.append(f"{shown_ids:<18}{'—':<15}{'IDLE':<10}{'—':<8}{'—':<8}—")
    lines.append(HEADER_LINE)
    return "\n".join(lines)


def render_warnings(warnings: list[str]) -> str:
    return "\n".join(warnings)


# ──────────────────────────────────────────────────────────────────── main ──
def collect_dashboard(
    registry_path: Path,
    now: datetime | None = None,
    stale_hours: float = STALE_DEFAULT_HOURS,
    offline: bool = False,
) -> dict:
    """Full pipeline as data — used by main() and the unit tests."""
    now = now or datetime.now(UTC)
    registry = load_registry(registry_path)
    roster = build_roster(registry)

    live = (not offline) and gh_available()
    claims: list[dict] = []
    prs: list[dict] = []
    if live:
        discover_dynamic_slots(registry, fetch_remote_branches(), roster)
        claims = fetch_in_progress_claims()
        prs = fetch_open_prs()

    rows, warnings = build_rows(roster, claims, prs, now, stale_hours)
    return {
        "generated_at": now.isoformat(),
        "stale_hours": stale_hours,
        "offline": not live,
        "rows": rows,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Real-time agent activity dashboard (#1635)"
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument(
        "--stale-hours",
        type=float,
        default=STALE_DEFAULT_HOURS,
        help="claimed-without-PR threshold (default 4h, per #1635)",
    )
    p.add_argument(
        "--registry",
        type=str,
        default=str(REGISTRY_PATH),
        help="path to AGENT_SLOT_REGISTRY.yaml",
    )
    p.add_argument(
        "--offline", action="store_true", help="skip live GitHub data (roster only)"
    )
    a = p.parse_args(argv)

    data = collect_dashboard(
        Path(a.registry), stale_hours=a.stale_hours, offline=a.offline
    )
    if a.json:
        print(json.dumps(data, indent=2))
        return 0

    print(
        render_table(
            data["rows"],
            parse_iso(data["generated_at"]) or datetime.now(UTC),
            offline=data["offline"],
        )
    )
    w = render_warnings(data["warnings"])
    if w:
        print(w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
