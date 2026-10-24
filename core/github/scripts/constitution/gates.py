"""Automated System Gates (Issue #2251 — Phase 5 governance flip).

বাংলা: AGENTS.md v2-এর "prose → gate" রূপান্তরের তিনটি সক্রিয় gate:
  1. Verification Gate — PR description-এ Test Evidence (টেস্ট লগ) বাধ্যতামূলক।
  2. Scope Gate       — claim comment-এর "Touching files:" বাইরের ফাইল বদলালে BLOCK।
  3. Lease Gate       — bot PR-এর branch অবশ্যই লেখকের leased slot-এর ভেতরে হতে হবে।

প্রতিটি gate-এর থ্রেশহোল্ড/পলিসি `.github/constitution/rules.yml`-এ থাকে
(machine-readable constitution) — এই মডিউল শুধু সেটা পড়ে enforce করে।

CLI:
    PYTHONPATH=.github/scripts python -m constitution.gates verification --pr 123
    PYTHONPATH=.github/scripts python -m constitution.gates scope --pr 123
    PYTHONPATH=.github/scripts python -m constitution.gates lease --pr 123
    PYTHONPATH=.github/scripts python -m constitution.gates all --pr 123

Exit code: 0 = pass, 1 = BLOCK, 2 = config/arg error.
SYSTEM_GATES_MODE=warn env দিলে BLOCK-এর বদলে শুধু সতর্কতা (rollout soft-launch)।
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = REPO_ROOT / ".github" / "constitution" / "rules.yml"

DEFAULT_SCOPE_POLICY = {
    "declaration_marker": "Touching files:",
    "undeclared_files": "block",
    "missing_declaration": "block",
    "advisory_authors": ["OWNER", "MEMBER", "COLLABORATOR"],
    "allowlist": ["docs/generated/**"],
}
DEFAULT_VERIFICATION_POLICY = {
    "min_evidence_chars": 40,
    "section_names": ["Test Evidence", "Tests", "পরীক্ষা", "টেস্ট এভিডেন্স"],
    "output_markers": ["passed", "pytest", "unittest", "bun test", "vitest"],
}
DEFAULT_LEASE_POLICY = {
    "bot_author_regex": r"^supremeai-([a-z0-9]+)-([0-9]+)-bot(\[bot\])?$",
    "bot_branch_regex": r"^([a-z0-9]+)-([0-9]+)([-_.].+)?$",
    "exempt_authors": ["dependabot[bot]", "github-actions[bot]", "renovate[bot]"],
    "docs_branch_prefix": "docs/",
    "mesh_advisory_env": "SUPREME_MESH_URL",
}


# ─────────────────────────── policy loading ───────────────────────────

def load_policies(rules_path: Optional[Path] = None) -> dict:
    """Load gate policies from the machine-readable constitution (rules.yml)."""
    path = Path(rules_path) if rules_path else RULES_PATH
    try:
        import yaml
    except ImportError:
        print("::warning::PyYAML unavailable — falling back to built-in gate defaults")
        return {
            "scope_policy": dict(DEFAULT_SCOPE_POLICY),
            "verification_policy": dict(DEFAULT_VERIFICATION_POLICY),
            "lease_policy": dict(DEFAULT_LEASE_POLICY),
        }
    if not path.exists():
        print(f"::warning::{path} not found — falling back to built-in gate defaults")
        return {
            "scope_policy": dict(DEFAULT_SCOPE_POLICY),
            "verification_policy": dict(DEFAULT_VERIFICATION_POLICY),
            "lease_policy": dict(DEFAULT_LEASE_POLICY),
        }
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {
        "scope_policy": {**DEFAULT_SCOPE_POLICY, **(data.get("scope_policy") or {})},
        "verification_policy": {**DEFAULT_VERIFICATION_POLICY, **(data.get("verification_policy") or {})},
        "lease_policy": {**DEFAULT_LEASE_POLICY, **(data.get("lease_policy") or {})},
    }


# ─────────────────────────── shared helpers ───────────────────────────

def path_matches(path: str, pattern: str) -> bool:
    """fnmatch-style matcher that also honours trailing `/**` directory globs."""
    path = path.lstrip("./")
    pattern = pattern.lstrip("./")
    if fnmatch.fnmatch(path, pattern):
        return True
    if pattern.endswith("/**"):
        base = pattern[:-3]
        return path == base or path.startswith(base + "/")
    return False


def path_matches_any(path: str, patterns: list) -> bool:
    return any(path_matches(path, p) for p in patterns)


def is_truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "warn"}


def gh_api(endpoint: str, token: Optional[str] = None) -> object:
    """Minimal GitHub REST GET via gh CLI first, then urllib fallback."""
    try:
        res = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return json.loads(res.stdout)
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError):
        pass
    tok = token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not tok:
        raise RuntimeError(f"no gh CLI and no token for API call: {endpoint}")
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def gate_result(name: str, ok: bool, message: str) -> int:
    """Print gate verdict consistently and return the process exit code for it."""
    mode = os.environ.get("SYSTEM_GATES_MODE", "strict").strip().lower()
    if ok:
        print(f"[PASSED] {name}: {message}")
        return 0
    if mode == "warn":
        print(f"::warning::[WARN-MODE] {name}: {message}")
        print(f"[WARNED] {name} ran in warn mode (SYSTEM_GATES_MODE=warn) — not blocking.")
        return 0
    print(f"::error::{name} BLOCK: {message}")
    return 1


# ─────────────────────── Verification Gate (test logs required) ───────────────────────

def extract_test_evidence(body: str, policy: dict) -> tuple[bool, str]:
    """Return (has_evidence, reason). Body must contain a Test Evidence section
    whose content is non-trivial and looks like test output / commands."""
    if not body or not body.strip():
        return False, "PR body is empty — no Test Evidence section"
    names = policy.get("section_names") or DEFAULT_VERIFICATION_POLICY["section_names"]
    min_chars = int(policy.get("min_evidence_chars", 40))
    markers = policy.get("output_markers") or DEFAULT_VERIFICATION_POLICY["output_markers"]

    section = None
    for name in names:
        pattern = re.compile(
            rf"^#+\s*(?:.*)?{re.escape(name)}.*$",
            re.IGNORECASE | re.MULTILINE,
        )
        m = pattern.search(body)
        if m:
            section = body[m.end():]
            # cut at the next markdown heading (any level) that follows
            nxt = re.search(r"\n#{1,6}\s+\S", section, re.MULTILINE)
            if nxt:
                section = section[: nxt.start()]
            break
    if section is None:
        return False, (
            "No Test Evidence section found in PR body "
            f"(expected any of: {', '.join(names)}). "
            "Add a '## Test Evidence' section with the actual test log/commands."
        )
    text = section.strip()
    if len(text) < min_chars:
        return False, (
            f"Test Evidence section too short ({len(text)} < {min_chars} chars) — "
            "paste the real test command + result summary"
        )
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in markers):
        return True, f"Test Evidence found ({len(text)} chars, contains test-output markers)"
    return False, (
        "Test Evidence section has no recognizable test output marker "
        f"(looking for any of: {', '.join(map(str, markers[:8]))}...)"
    )


def run_verification_gate(pr_body: str, policy: dict) -> int:
    ok, reason = extract_test_evidence(pr_body or "", policy)
    return gate_result("Verification Gate", ok, reason)


# ─────────────────── Scope Gate (claim declaration vs changed files) ───────────────────

def parse_declared_files(comments: list) -> set:
    """Extract declared paths from claim comments containing 'Touching files:'.

    Supports both formats used by agents:
      - `**Touching files:**` followed by a bullet/backtick list (multi-line)
      - `Touching files: a.py, b.py` inline
    Annotations like `(delete — ...)`, `(new — ...)` are stripped.
    """
    marker = "Touching files:"
    declared: set = set()
    path_re = re.compile(r"[\w./@-]+\.[A-Za-z0-9]{1,12}|[\w./@-]+(?:/[\w.@*-]+)+")

    def harvest(segment: str) -> None:
        segment = re.sub(r"\([^)]*\)", " ", segment)  # strip annotations
        segment = segment.replace("**", " ").replace("`", " ")
        for token in re.split(r"[,\s]+", segment):
            token = token.strip().strip("`").strip("*").strip(",").strip("-")
            if not token:
                continue
            if "/" in token or "." in token.split("/")[-1]:
                if path_re.fullmatch(token):
                    declared.add(token.strip("/"))

    for body in comments or []:
        if not body or marker not in body:
            continue
        lines = body.splitlines()
        for idx, line in enumerate(lines):
            if marker not in line:
                continue
            harvest(line.split(marker, 1)[1])
            # multi-line block: consume following bullet/backtick lines until a
            # non-list line (heading, prose paragraph, blank+prose) appears.
            for follow in lines[idx + 1 :]:
                stripped = follow.strip()
                if not stripped:
                    continue  # blank line — keep scanning (lists often have gaps)
                if stripped.startswith(("#", ">")) and marker not in stripped:
                    break  # new heading/quote — declaration block ended
                if stripped.startswith(("-", "*", "`")):
                    harvest(stripped)
                    continue
                # prose line — only treat as part of declaration if it looks path-y
                if "/" in stripped or "`" in stripped:
                    harvest(stripped)
                    continue
                break
    return declared


def find_linked_issue_numbers(title: str, body: str) -> list:
    """Issue reference from PR title suffix '(#N)' (repo convention) or closing keywords."""
    nums: list = []
    m = re.search(r"\(#(\d+)\)\s*$", (title or "").strip())
    if m:
        nums.append(int(m.group(1)))
    for m in re.finditer(
        r"(?:\b(?:closes?|fixes?|resolves?)\s+#(\d+))", (body or ""), re.IGNORECASE
    ):
        if int(m.group(1)) not in nums:
            nums.append(int(m.group(1)))
    return nums


def find_undeclared_files(changed: list, declared: set, allowlist: list) -> list:
    """Files changed by the PR that are neither declared in the claim nor allowlisted.

    Declaration semantics: an exact path matches itself; a declaration that ends
    with `/` (or is a known directory prefix) matches its whole subtree — agents
    commonly declare directories like `.github/scripts/`.
    """
    out = []
    dir_decls = {d.rstrip("/") for d in declared or [] if d.endswith("/")}
    file_decls = {d for d in declared or [] if not d.endswith("/")}
    for path in changed or []:
        if path in file_decls:
            continue
        if any(path == d or path.startswith(d + "/") for d in dir_decls):
            continue
        if path_matches_any(path, allowlist or []):
            continue
        out.append(path)
    return sorted(out)


def run_scope_gate(pr_number: int, pr_author_association: str, pr_title: str,
                   pr_body: str, policy: dict, api=None) -> int:
    api = api or gh_api
    allowlist = policy.get("allowlist") or []
    advisory_authors = policy.get("advisory_authors") or []
    undeclared_action = policy.get("undeclared_files", "block")
    missing_action = policy.get("missing_declaration", "block")

    files_payload = api(f"repos/{_repo()}/pulls/{pr_number}/files?per_page=100")
    changed = [f["filename"] for f in files_payload or []]

    issue_nums = find_linked_issue_numbers(pr_title, pr_body)
    comments: list = []
    if issue_nums:
        for num in issue_nums[:3]:
            try:
                comments.extend(api(f"repos/{_repo()}/issues/{num}/comments?per_page=100") or [])
            except Exception as err:  # noqa: BLE001 — gate must not crash on API hiccup
                print(f"::warning::could not fetch issue #{num} comments: {err}")
    bodies = [c.get("body", "") for c in comments if isinstance(c, dict)]
    declared = parse_declared_files(bodies)

    if not declared:
        msg = (
            "No 'Touching files:' declaration found on the linked claim issue "
            f"(linked: {issue_nums or 'none'}). Rule 2/20: No Claim, No Code — "
            "post the claim comment with declared files, then re-run."
        )
        if pr_author_association in advisory_authors:
            print(f"::warning::[advisory:{pr_author_association}] {msg}")
            print("[PASSED] Scope Gate (advisory author — warn only)")
            return 0
        return gate_result("Scope Gate", missing_action != "block", msg)

    undeclared = find_undeclared_files(changed, declared, allowlist)
    if not undeclared:
        print(f"[PASSED] Scope Gate: {len(changed)} changed files, all declared or allowlisted")
        return 0
    listing = ", ".join(undeclared[:20]) + (" …" if len(undeclared) > 20 else "")
    msg = (
        f"{len(undeclared)} file(s) changed outside the declared 'Touching files:' set: {listing}. "
        "Fix: update the claim comment on the issue (or drop the undeclared changes)."
    )
    if pr_author_association in advisory_authors:
        print(f"::warning::[advisory:{pr_author_association}] {msg}")
        return 0
    return gate_result("Scope Gate", undeclared_action != "block", msg)


def _repo() -> str:
    env = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY")
    if env:
        return env
    res = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)
    m = re.search(r"github\.com[/:]([\w.-]+/[\w.-]+?)(?:\.git)?$", res.stdout.strip())
    if not m:
        raise RuntimeError("cannot determine GH repo (set GH_REPO)")
    return m.group(1)


# ─────────────────────────── Lease Gate (slot identity) ───────────────────────────

def check_lease(author: str, branch: str, policy: dict) -> tuple[bool, str]:
    """Bot authors may only push from their leased slot branch (or docs/).

    Returns (ok, reason). Humans and exempt bots always pass.
    """
    author = (author or "").strip()
    branch = (branch or "").strip()
    exempt = set(policy.get("exempt_authors") or [])
    if author in exempt or author.endswith("[bot]") and "supremeai-" not in author:
        return True, f"author '{author}' is exempt from lease gate"
    m = re.match(policy.get("bot_author_regex", DEFAULT_LEASE_POLICY["bot_author_regex"]), author)
    if not m:
        return True, f"author '{author}' is not a slot bot — lease gate advisory only"
    lane, slot = m.group(1), m.group(2)
    docs_prefix = policy.get("docs_branch_prefix", "docs/")
    if branch.startswith(docs_prefix):
        return True, f"docs branch '{branch}' allowed for slot {lane}-{slot}"
    bm = re.match(policy.get("bot_branch_regex", DEFAULT_LEASE_POLICY["bot_branch_regex"]), branch)
    if not bm:
        return False, (
            f"branch '{branch}' does not match slot pattern <lane>-<N> for author '{author}' "
            f"(leased slot: {lane}-{slot})"
        )
    if (bm.group(1), bm.group(2)) != (lane, slot):
        return False, (
            f"cross-slot push: author '{author}' leases {lane}-{slot} "
            f"but branch '{branch}' belongs to {bm.group(1)}-{bm.group(2)}"
        )
    ok, reason = _mesh_lease_advisory(policy)
    if not ok:
        return False, reason
    return True, f"branch '{branch}' matches leased slot {lane}-{slot}"


def _mesh_lease_advisory(policy: dict) -> tuple[bool, str]:
    """Best-effort mesh lease freshness check (only when SUPREME_MESH_URL is set)."""
    env_key = policy.get("mesh_advisory_env", "SUPREME_MESH_URL")
    base = os.environ.get(env_key, "").strip().rstrip("/")
    if not base:
        return True, "mesh registry not configured — slot-pattern check stands"
    try:
        req = urllib.request.Request(f"{base}/api/v1/nodes", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            nodes = (json.loads(resp.read().decode("utf-8")) or {}).get("nodes", [])
        stale = [n.get("node_id") for n in nodes if n.get("lease_active") is False]
        return True, f"mesh reachable ({len(nodes)} nodes, {len(stale)} idle) — lease advisory OK"
    except Exception as err:  # noqa: BLE001 — CI cannot hard-depend on mesh uptime
        print(f"::warning::mesh registry unreachable ({err}) — lease gate falls back to slot-pattern only")
        return True, "mesh unreachable — fallback check used"


def run_lease_gate(pr_author: str, pr_branch: str, policy: dict) -> int:
    ok, reason = check_lease(pr_author or "", pr_branch or "", policy)
    return gate_result("Lease Gate", ok, reason)


# ─────────────────────────────── CLI ───────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI Automated System Gates")
    parser.add_argument("gate", choices=["verification", "scope", "lease", "all"])
    parser.add_argument("--pr", type=int, default=0, help="PR number (for scope gate)")
    parser.add_argument("--title", default="", help="PR title (else fetched via API)")
    parser.add_argument("--body", default="", help="PR body (else fetched via API)")
    parser.add_argument("--author", default="", help="PR author login (else fetched)")
    parser.add_argument("--branch", default="", help="PR head branch (else fetched)")
    parser.add_argument("--author-association", default="", help="PR author association")
    parser.add_argument("--rules", default=str(RULES_PATH), help="path to rules.yml")
    args = parser.parse_args()

    policies = load_policies(Path(args.rules))
    failures: list = []
    needs_ctx = args.gate in ("verification", "all", "scope") or (
        args.gate == "lease" and not (args.author and args.branch)
    )
    if needs_ctx and args.pr:
        title, body, author, branch, assoc = _resolve_pr_context(args)
    else:
        title, body, author, branch, assoc = (
            args.title, args.body, args.author, args.branch, args.author_association,
        )

    if args.gate in ("verification", "all"):
        rc = run_verification_gate(body, policies["verification_policy"])
        if rc:
            failures.append("verification")

    if args.gate in ("lease", "all"):
        rc = run_lease_gate(author, branch, policies["lease_policy"])
        if rc:
            failures.append("lease")

    if args.gate in ("scope", "all"):
        rc = run_scope_gate(args.pr, assoc or "NONE", title, body, policies["scope_policy"])
        if rc:
            failures.append("scope")

    if failures:
        print(f"[FAILED] System gates failed: {', '.join(failures)}")
        return 1
    print("[PASSED] System gates: all requested gates green.")
    return 0


def _resolve_pr_context(args) -> tuple:
    """Fetch PR metadata from API when not supplied via flags."""
    if args.pr and os.environ.get("SYSTEM_GATES_SKIP_API") != "1":
        try:
            pr = gh_api(f"repos/{_repo()}/pulls/{args.pr}")
            return (
                pr.get("title", ""),
                pr.get("body") or "",
                (pr.get("user") or {}).get("login", ""),
                (pr.get("head") or {}).get("ref", ""),
                pr.get("author_association", "NONE"),
            )
        except Exception as err:  # noqa: BLE001
            print(f"::warning::API fetch failed ({err}) — using supplied flags")
    return args.title, args.body, args.author, args.branch, args.author_association


if __name__ == "__main__":
    raise SystemExit(main())
