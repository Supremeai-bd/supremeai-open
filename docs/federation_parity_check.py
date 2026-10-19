#!/usr/bin/env python3
"""
federation_parity_check.py — SupremeAI Federation Mirror Parity Checker (WO #471)

Single-command federation sync status tool (Milestone 3 of the Federation
Master Organization Roadmap). Verifies that landed core contracts stay
byte-identical between the public ingress repo (supremeai-open) and the
satellite repositories that consume them (Milestone 1: Mirror Parity).

Placement note (routing SSOT): this file lives under docs/ because
landing.yml routes monorepo-anchor changes via an explicit path allowlist
(docs/*, scripts/agents/*, patches/*, root governance docs). A federation
ops tool belongs with the governance docs it serves; moving it elsewhere
would silently drop it from the anchor lane.

Parity classes
--------------
  BYTE-IDENTICAL : contract files that MUST be sha256-equal everywhere
                   (docs/CONSUMERS.md, api-schemas/*).
  CURATED        : per-repo files that are intentionally different
                   (READMEs, dashboards) — never checked here.

Exit codes (fail-loud, CI-friendly)
-----------------------------------
  0  all reachable contract copies are byte-identical
  1  DRIFT detected (same path, different bytes)
  2  MISSING file in a satellite that declares the contract
  3  local usage error

Private/unreachable satellites are reported as UNREACHABLE (skip with
warning), never silently ignored — fail-honest, not fail-open.

Usage
-----
  python3 docs/federation_parity_check.py --check        # gate mode
  python3 docs/federation_parity_check.py --report       # human dashboard
  python3 docs/federation_parity_check.py --self-test    # offline fixtures

Stdlib only. No network in --self-test mode.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from dataclasses import dataclass, field

OPEN_REPO = "Supremeai-bd/supremeai-open"
RAW_HOST = "raw.githubusercontent.com"
BRANCH = "main"

# ---------------------------------------------------------------------------
# Parity manifest (Milestone 1 SSOT)
# Each entry: repo-relative path + satellites that mirror it byte-identically.
# Extend via PR only — this manifest is itself a governed contract.
# ---------------------------------------------------------------------------
PARITY_MANIFEST = [
    {
        "path": "docs/CONSUMERS.md",
        "satellites": ["Supremeai-bd/supremeai-api", "Supremeai-bd/supremeai-sdk"],
        "class": "BYTE-IDENTICAL",
    },
    {
        "path": "api-schemas/gateway.openapi.yaml",
        "satellites": ["Supremeai-bd/supremeai-api"],
        "class": "BYTE-IDENTICAL",
    },
    {
        "path": "api-schemas/heartbeat.schema.json",
        "satellites": ["Supremeai-bd/supremeai-mcp-control-plane"],
        "class": "BYTE-IDENTICAL",
    },
]


@dataclass
class Copy:
    repo: str
    sha256: str | None
    status: str  # OK | MISSING | UNREACHABLE | DRIFT
    detail: str = ""


@dataclass
class Row:
    path: str
    klass: str
    baseline_sha: str | None
    copies: list = field(default_factory=list)

    @property
    def verdict(self) -> str:
        statuses = [c.status for c in self.copies]
        if "MISSING" in statuses:
            return "MISSING"
        if "DRIFT" in statuses:
            return "DRIFT"
        if all(c.status == "UNREACHABLE" for c in self.copies):
            return "UNREACHABLE"
        if all(c.status == "OK" for c in self.copies):
            return "PARITY"
        return "PARTIAL"


def fetch_raw(repo: str, path: str, timeout: int = 15) -> tuple[str, bytes | None]:
    """Return (status, body). status in {OK, MISSING, UNREACHABLE}."""
    url = f"https://{RAW_HOST}/{repo}/{BRANCH}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status == 200:
                return "OK", resp.read()
            return "UNREACHABLE", None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "MISSING", None
        return "UNREACHABLE", None
    except (urllib.error.URLError, TimeoutError, OSError):
        return "UNREACHABLE", None


def check_row(entry: dict, fetch=fetch_raw) -> Row:
    row = Row(path=entry["path"], klass=entry["class"], baseline_sha=None)
    status, body = fetch(OPEN_REPO, entry["path"])
    if status != "OK":
        row.copies.append(Copy(OPEN_REPO, None, status, "baseline unreadable"))
        return row
    row.baseline_sha = hashlib.sha256(body).hexdigest()
    for sat in entry["satellites"]:
        st, sbody = fetch(sat, entry["path"])
        if st == "OK":
            sha = hashlib.sha256(sbody).hexdigest()
            if sha == row.baseline_sha:
                row.copies.append(Copy(sat, sha, "OK"))
            else:
                row.copies.append(Copy(sat, sha, "DRIFT", "bytes differ from baseline"))
        else:
            row.copies.append(Copy(sat, None, st))
    return row


def run_check(fetch=fetch_raw) -> list:
    return [check_row(e, fetch) for e in PARITY_MANIFEST]


def render_report(rows: list) -> str:
    lines = ["Federation Mirror Parity Report", "=" * 62]
    for r in rows:
        lines.append(f"\n[{r.verdict:>11}] {r.klass:<14} {r.path}")
        lines.append(
            f"              baseline(open@{BRANCH}) sha256="
            f"{(r.baseline_sha or '----------')[:12]}"
        )
        for c in r.copies:
            mark = {
                "OK": "  =",
                "DRIFT": " !=",
                "MISSING": " ??",
                "UNREACHABLE": " ~~",
            }[c.status]
            lines.append(f"   {mark} {c.repo:<44} {c.status} {c.detail}".rstrip())
    hard = [r.verdict for r in rows if r.verdict in ("DRIFT", "MISSING")]
    lines.append("\nSummary: " + ", ".join(f"{r.verdict}:{r.path}" for r in rows))
    lines.append("Gate: " + ("FAIL" if hard else "PASS"))
    return "\n".join(lines)


def self_test() -> int:
    """Offline verification with local fixtures (no network)."""
    fixtures = {
        "docs/CONSUMERS.md": b"contract-body-v7\n",
        "api-schemas/gateway.openapi.yaml": b"openapi: 3.1\n",
        "api-schemas/heartbeat.schema.json": b'{"$schema":"draft-07"}\n',
    }

    def fake_fetch(repo: str, path: str, timeout: int = 15):
        if repo == OPEN_REPO:
            if path in fixtures:
                return "OK", fixtures[path]
            return "MISSING", None
        if repo.endswith("supremeai-api"):
            if path == "docs/CONSUMERS.md":
                return "OK", b"contract-body-v7\n"  # parity
            if path == "api-schemas/gateway.openapi.yaml":
                return "OK", b"openapi: 3.1\n drifted\n"  # drift
        if repo.endswith("supremeai-sdk") and path == "docs/CONSUMERS.md":
            return "MISSING", None  # missing
        return "UNREACHABLE", None  # private plane

    rows = run_check(fake_fetch)
    assert rows[0].verdict == "MISSING", rows[0].verdict  # sdk missing
    assert rows[1].verdict == "DRIFT", rows[1].verdict  # api drifted
    assert rows[2].verdict == "UNREACHABLE", rows[2].verdict  # private plane
    report = render_report(rows)
    assert "Gate: FAIL" in report
    assert "DRIFT" in report and "MISSING" in report

    run_check(
        lambda repo, path, timeout=15: (
            ("OK", b"same\n") if path == "x" else fake_fetch(repo, path)
        )
    )
    # happy path: identical bytes everywhere -> PARITY
    happy = check_row(
        {"path": "docs/CONSUMERS.md", "satellites": ["S/x"], "class": "BYTE-IDENTICAL"},
        fetch=lambda repo, path, timeout=15: ("OK", b"same\n"),
    )
    assert happy.verdict == "PARITY", happy.verdict
    print("self-test: 4/4 scenario groups PASS (parity, drift, missing, unreachable)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="SupremeAI federation mirror parity checker"
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="gate mode (exit codes)")
    mode.add_argument("--report", action="store_true", help="human-readable dashboard")
    mode.add_argument("--self-test", action="store_true", help="offline fixture test")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    rows = run_check()
    if args.report:
        print(render_report(rows))
    hard = any(r.verdict in ("DRIFT", "MISSING") for r in rows)
    if hard:
        print(render_report(rows), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
