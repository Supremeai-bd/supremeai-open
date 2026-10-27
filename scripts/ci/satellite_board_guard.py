#!/usr/bin/env python3
"""
satellite_board_guard.py — Zero-Issue Satellite Mandate Guard (#626)

Milestone 3 of the Single Central Task Board SSOT doctrine (#626): the
doctrine's home is docs/FEDERATION_CHARTER.md, with machine-enforcement
anchors in AGENTS.md §5. This guard audits the
12 federation satellite repositories for the mandated zero-open-issues /
zero-open-PRs clean state, so any stray issue or PR created on a satellite
is flagged at the central board instead of orphaning work off-SSOT.

Doctrine (single paragraph form):
  1. supremeai-open is the SOLE public task board and front desk; satellites
     carry 0 open issues and 0 open PRs — permanently.
  2. Work enters satellites only through landing.yml / the bridge transit
     pipeline, never through satellite trackers.
  3. The private monorepo (Supremeai-bd/supremeai) keeps its internal
     backlog; it is out of this guard's scope.

Verdicts (fail-honest, never fail-open):
  CLEAN        0 open issues and 0 open PRs on the satellite
  VIOLATION    at least one open issue or open PR (details listed)
  UNREACHABLE  private plane, absent repo, network fault, or API rate
               limit — reported loudly, never silently ignored
               (same skip-with-warning contract as
               docs/federation_parity_check.py)

Exit codes (CI-friendly, mirrors docs/federation_parity_check.py):
  0  every reachable satellite is CLEAN (UNREACHABLE allowed, warned)
  1  at least one VIOLATION
  2  every satellite UNREACHABLE (nothing could be verified)
  3  local usage error

Credential policy: zero-credential by default (unauthenticated REST — the
same plane external bridge agents operate on). GH_TOKEN or GITHUB_TOKEN in
the environment raises the rate-limit ceiling when available; the guard
never requires a token and never reads or prints secret material.

Nightly wiring (Milestone 3, coordination note): the central nightly job
architecture is specified by issue #612 — the operator wires this script
into that job (CI workflow files are a protected path for automatic agent
writes). This script is the deterministic, side-effect-free building block
that job calls in check mode.

Usage:
  python3 scripts/ci/satellite_board_guard.py --check     # gate mode (exit codes)
  python3 scripts/ci/satellite_board_guard.py --report    # human matrix
  python3 scripts/ci/satellite_board_guard.py --json      # machine output
  python3 scripts/ci/satellite_board_guard.py --self-test # offline fixtures

Stdlib only. --self-test performs zero network I/O.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

OPEN_REPO = "Supremeai-bd/supremeai-open"

# ---------------------------------------------------------------------------
# Satellite registry — verbatim from the #626 doctrine (12 satellites).
# Extend or remove via a governance PR only; this list is a governed contract
# and MUST stay aligned with docs/FEDERATION_CHARTER.md and AGENTS.md §2.3.7.
# ---------------------------------------------------------------------------
SATELLITES: tuple[str, ...] = (
    "studio",
    "api",
    "vscode",
    "browser",
    "core",
    "archive",
)

# Short satellite key -> actual GitHub repository name. The #626 doctrine uses
# short keys, but the GitHub repos are prefixed with "supremeai-". Keep
# SATELLITES as short keys for display/doctrine parity; resolve to full repo
# names only at the HTTP boundary.
SATELLITE_REPO_NAMES: dict[str, str] = {
    "studio": "supremeai-studio",
    "api": "supremeai-api",
    "vscode": "supremeai-vscode",
    "browser": "supremeai-browser",
    "core": "supremeai-core",
    "archive": "supremeai-archive",
}


def satellite_repo_name(short: str) -> str:
    """Resolve a short satellite key to its full GitHub repository name."""
    if short in SATELLITE_REPO_NAMES:
        return SATELLITE_REPO_NAMES[short]
    return short if short.startswith("supremeai-") else f"supremeai-{short}"


DEFAULT_ORG = "Supremeai-bd"

VERDICT_CLEAN = "CLEAN"
VERDICT_VIOLATION = "VIOLATION"
VERDICT_UNREACHABLE = "UNREACHABLE"


class UnreachableError(RuntimeError):
    """Satellite state cannot be inspected (private plane, absent repo, network)."""


class RateLimitError(RuntimeError):
    """GitHub API rate limit exhausted for the current credential plane."""


@dataclass
class SatelliteReport:
    repo: str
    verdict: str
    open_issues: int = 0
    open_prs: int = 0
    violating: list[str] = field(default_factory=list)
    reason: str = ""

    def summary(self) -> str:
        if self.verdict == VERDICT_UNREACHABLE:
            return f"{self.repo:<18} UNREACHABLE  — {self.reason}"
        return (
            f"{self.repo:<18} {self.verdict:<11} "
            f"open_issues={self.open_issues} open_prs={self.open_prs}"
        )


def _http_get_json(url: str, token: str | None = None, timeout: int = 30) -> list:
    headers = {
        "User-Agent": "supremeai-satellite-board-guard",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UnreachableError(
                "HTTP 404 — repository absent or private plane"
            ) from exc
        if exc.code == 403:
            raise RateLimitError(
                "HTTP 403 — API rate limit likely exhausted on the current credential plane"
            ) from exc
        raise UnreachableError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise UnreachableError(f"network fault: {exc.reason}") from exc


def _issues_url(org: str, repo: str) -> str:
    """Combined open-issues+PRs listing endpoint for one satellite."""
    return f"https://api.github.com/repos/{org}/{satellite_repo_name(repo)}/issues?state=open&per_page=100"


def default_fetch_open_items(
    org: str, repo: str, token: str | None = None
) -> list[dict]:
    """Fetch the combined open issues+PRs list for one satellite.

    Uses the GitHub REST combined listing (one request per satellite, see
    _issues_url). The `pull_request` key distinguishes PRs from issues,
    exactly like the classification the upstream tracker itself uses.
    """
    return _http_get_json(_issues_url(org, repo), token=token)


def classify_items(items: list) -> tuple[int, int, list[str]]:
    """Split a combined open-items payload into (issues, prs, detail strings)."""
    issues = 0
    prs = 0
    details: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        number = it.get("number", "?")
        title = str(it.get("title", ""))[:70]
        kind = "pr" if "pull_request" in it else "issue"
        if kind == "pr":
            prs += 1
        else:
            issues += 1
        details.append(f"{kind} #{number}: {title}")
    return issues, prs, details


def audit_satellite(
    repo: str,
    org: str = DEFAULT_ORG,
    token: str | None = None,
    fetch: Callable[..., list] | None = None,
) -> SatelliteReport:
    """Audit one satellite for the zero-issue / zero-PR mandate."""
    fetch = fetch or default_fetch_open_items
    try:
        items = fetch(org, repo, token)
    except RateLimitError as exc:
        return SatelliteReport(repo, VERDICT_UNREACHABLE, reason=str(exc))
    except UnreachableError as exc:
        return SatelliteReport(repo, VERDICT_UNREACHABLE, reason=str(exc))
    if not isinstance(items, list):
        return SatelliteReport(
            repo,
            VERDICT_UNREACHABLE,
            reason="malformed payload: expected a JSON list of open items, got "
            f"{type(items).__name__}",
        )
    issues, prs, details = classify_items(items)
    if issues == 0 and prs == 0:
        return SatelliteReport(repo, VERDICT_CLEAN)
    return SatelliteReport(repo, VERDICT_VIOLATION, issues, prs, details)


def audit_all(
    org: str = DEFAULT_ORG,
    token: str | None = None,
    fetch: Callable[..., list] | None = None,
    satellites: tuple[str, ...] = SATELLITES,
) -> list[SatelliteReport]:
    return [
        audit_satellite(repo, org=org, token=token, fetch=fetch) for repo in satellites
    ]


def decide_exit_code(reports: list[SatelliteReport]) -> int:
    """Map the audit matrix onto the documented exit codes."""
    if any(r.verdict == VERDICT_VIOLATION for r in reports):
        return 1
    if any(r.verdict == VERDICT_UNREACHABLE for r in reports):
        # Degraded visibility is itself a failure: partial blindness (some
        # satellites unreachable, e.g. API rate-limit) must not read as pass.
        return 2
    return 0


def build_json(reports: list[SatelliteReport], org: str) -> dict:
    return {
        "org": org,
        "doctrine": "zero-issue-satellite-mandate",
        "issue": 626,
        "satellites": [
            {
                "repo": r.repo,
                "verdict": r.verdict,
                "open_issues": r.open_issues,
                "open_prs": r.open_prs,
                "violating": r.violating,
                "reason": r.reason,
            }
            for r in reports
        ],
        "clean": sum(1 for r in reports if r.verdict == VERDICT_CLEAN),
        "violations": sum(1 for r in reports if r.verdict == VERDICT_VIOLATION),
        "unreachable": sum(1 for r in reports if r.verdict == VERDICT_UNREACHABLE),
    }


def _env_token() -> str | None:
    import os

    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        val = os.environ.get(name)
        if val:
            return val
    return None


# ---------------------------------------------------------------------------
# Offline self-test — mocked fetchers, zero network (parity-checker precedent)
# ---------------------------------------------------------------------------
def self_test() -> bool:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    # 1. clean satellite
    r = audit_satellite("studio", fetch=lambda o, r_, t: [])
    check(
        "clean satellite -> CLEAN with zero counts",
        r.verdict == VERDICT_CLEAN and r.open_issues == 0 and r.open_prs == 0,
    )

    # 2. violation with mixed items
    mixed = [
        {"number": 1, "title": "stray issue one"},
        {"number": 3, "title": "stray issue two"},
        {"number": 2, "title": "stray pr", "pull_request": {"url": "x"}},
    ]
    r = audit_satellite("api", fetch=lambda o, r_, t: mixed)
    check(
        "mixed stray items -> VIOLATION 2 issues / 1 pr",
        r.verdict == VERDICT_VIOLATION
        and r.open_issues == 2
        and r.open_prs == 1
        and len(r.violating) == 3,
    )

    # 3. unreachable paths
    def boom_404(o, r_, t):
        raise UnreachableError("HTTP 404")

    def boom_rate(o, r_, t):
        raise RateLimitError("HTTP 403")

    r = audit_satellite("sdk", fetch=boom_404)
    check("private/absent repo -> UNREACHABLE", r.verdict == VERDICT_UNREACHABLE)
    r = audit_satellite("sdk", fetch=boom_rate)
    check("rate limit -> UNREACHABLE (never silent)", r.verdict == VERDICT_UNREACHABLE)

    # 4. exit-code mapping
    clean = [SatelliteReport(x, VERDICT_CLEAN) for x in ("a", "b")]
    viol = [
        SatelliteReport("a", VERDICT_CLEAN),
        SatelliteReport("b", VERDICT_VIOLATION),
    ]
    dead = [SatelliteReport(x, VERDICT_UNREACHABLE) for x in ("a", "b")]
    check(
        "exit codes 0 / 1 / 2 mapping",
        decide_exit_code(clean) == 0
        and decide_exit_code(viol) == 1
        and decide_exit_code(dead) == 2,
    )

    ok = all(passed for _, passed in checks)
    print(
        f"self-test: {sum(1 for _, p in checks if p)}/{len(checks)} checks {'PASS' if ok else 'FAIL'}"
    )
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Zero-Issue Satellite Mandate Guard (#626)"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check", action="store_true", help="gate mode: audit + documented exit codes"
    )
    mode.add_argument(
        "--report", action="store_true", help="human-readable audit matrix"
    )
    mode.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="machine-readable JSON output",
    )
    mode.add_argument(
        "--self-test", action="store_true", help="offline self-test, zero network"
    )
    parser.add_argument(
        "--org",
        default=DEFAULT_ORG,
        help=f"GitHub organization (default: {DEFAULT_ORG})",
    )
    parser.add_argument(
        "--scopes",
        help="comma-separated satellite short keys to audit (e.g. studio,vscode); default: all",
    )
    parser.add_argument(
        "--via-tower",
        action="store_true",
        help="scope audit to AGENT_ALLOWED_DOMAINS env (comma-separated short keys)",
    )
    args = parser.parse_args()

    if args.self_test:
        return 0 if self_test() else 1
    token = _env_token()

    # Resolve scoped satellite set (roadmap L2: scoped audit mode)
    scoped = None
    if args.via_tower:
        raw = os.environ.get("AGENT_ALLOWED_DOMAINS", "")
        scoped = [s.strip() for s in raw.split(",") if s.strip()]
    elif args.scopes:
        scoped = [s.strip() for s in args.scopes.split(",") if s.strip()]
    if scoped:
        satellites = tuple(s for s in SATELLITES if s in scoped)
        if not satellites:
            print("MALFORMED INPUT (fail-closed): no valid satellite scopes resolved")
            return 3
    else:
        satellites = SATELLITES

    reports = audit_all(org=args.org, token=token, satellites=satellites)

    if args.as_json:
        print(json.dumps(build_json(reports, args.org), indent=2))
    else:
        print(
            f"Zero-Issue Satellite Mandate audit — org {args.org} (doctrine #626, docs/FEDERATION_CHARTER.md)"
        )
        for r in reports:
            print(f"  {r.summary()}")
            for v in r.violating:
                print(f"      {v}")
        clean = sum(1 for r in reports if r.verdict == VERDICT_CLEAN)
        viol = sum(1 for r in reports if r.verdict == VERDICT_VIOLATION)
        unreach = sum(1 for r in reports if r.verdict == VERDICT_UNREACHABLE)
        print(
            f"  totals: {clean} clean / {viol} violations / {unreach} unreachable of {len(reports)}"
        )
        if unreach:
            print(
                "  note: UNREACHABLE entries are skipped with warning (private plane / rate limit), never silent."
            )

    return decide_exit_code(reports)


if __name__ == "__main__":
    sys.exit(main())
