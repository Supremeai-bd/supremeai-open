#!/usr/bin/env python3
"""Universal Federation Dispatch Engine core (offline, testable)."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import hourly_satellite_batcher as hb

SATELLITE_REPOS = {
    "studio": "Supremeai-bd/supremeai-studio",
    "api": "Supremeai-bd/supremeai-api",
    "vscode": "Supremeai-bd/supremeai-vscode",
    "browser": "Supremeai-bd/supremeai-browser",
    "core": "Supremeai-bd/supremeai-core",
    "command": "Supremeai-bd/supremeai-command",
    "skills": "Supremeai-bd/supremeai-skills",
    "agents": "Supremeai-bd/supremeai-agents",
    "sdk": "Supremeai-bd/supremeai-sdk",
    "archive": "Supremeai-bd/supremeai-archive",
    "infra": "Supremeai-bd/supremeai-infrastructure",
    "mcp": "Supremeai-bd/supremeai-mcp-control-plane",
}


class DispatchError(ValueError):
    pass


@dataclass(frozen=True)
class SatelliteDispatch:
    satellite: str
    repo: str
    files: tuple[str, ...]


@dataclass
class DispatchPlan:
    targets: list = field(default_factory=list)
    monorepo_paths: list = field(default_factory=list)
    unrouted: list = field(default_factory=list)
    source_sha: str = ""

    def to_dict(self):
        return {
            "source_sha": self.source_sha,
            "targets": [{"satellite": t.satellite, "repo": t.repo, "files": list(t.files)} for t in self.targets],
            "monorepo_paths": self.monorepo_paths,
            "unrouted": [{"path": p, "reason": r} for p, r in self.unrouted],
        }


def route_path(path):
    if not isinstance(path, str) or not path.strip():
        raise DispatchError(f"invalid path: {path!r}")
    return hb.route_path(path)


def plan_dispatch(paths, source_sha=""):
    if not isinstance(paths, (list, tuple)):
        raise DispatchError(f"paths must be list/tuple; got {type(paths).__name__}")
    plan = DispatchPlan(source_sha=source_sha)
    grouped = {}
    seen = {}
    for raw in paths:
        if not isinstance(raw, str) or not raw.strip():
            raise DispatchError(f"invalid path entry: {raw!r}")
        path = raw.strip()
        target = route_path(path)
        if target is None:
            plan.unrouted.append((path, "no routing rule"))
            continue
        if target == "monorepo":
            if path not in plan.monorepo_paths:
                plan.monorepo_paths.append(path)
            continue
        if target not in SATELLITE_REPOS:
            plan.unrouted.append((path, f"unknown satellite {target!r}"))
            continue
        grouped.setdefault(target, [])
        seen.setdefault(target, set())
        if path not in seen[target]:
            grouped[target].append(path)
            seen[target].add(path)
    for satellite in sorted(grouped):
        plan.targets.append(SatelliteDispatch(satellite, SATELLITE_REPOS[satellite], tuple(grouped[satellite])))
    return plan


def self_test():
    checks = []
    def check(name, ok):
        checks.append((name, ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    check("12 satellites", len(SATELLITE_REPOS) == 12)
    check("vscode route", route_path("vscode/x.ts") == "vscode")
    check("mcp route", route_path("infrastructure/mcp-control-plane/src/x.ts") == "mcp")
    check("monorepo route", route_path("scripts/agents/loop.py") == "monorepo")
    check("unrouted", route_path("README.md") is None)
    plan = plan_dispatch(["vscode/a.ts", "skills/b.md", "gateway/c.py"])
    repos = {t.repo for t in plan.targets}
    check("multi-domain split 3", len(plan.targets) == 3 and "Supremeai-bd/supremeai-vscode" in repos and "Supremeai-bd/supremeai-skills" in repos and "Supremeai-bd/supremeai-api" in repos)
    vt = next(t for t in plan.targets if t.satellite == "vscode")
    check("vscode files", vt.files == ("vscode/a.ts",))
    plan2 = plan_dispatch(["vscode/a.ts", "scripts/agents/loop.py", "README.md"])
    check("monorepo split out", "scripts/agents/loop.py" in plan2.monorepo_paths and all("scripts/agents/loop.py" not in t.files for t in plan2.targets))
    check("unrouted quarantined", any(p == "README.md" for p, _ in plan2.unrouted))
    try:
        plan_dispatch("not-a-list"); invalid_ok = False
    except DispatchError:
        invalid_ok = True
    check("non-list fails closed", invalid_ok)
    try:
        plan_dispatch(["", "   "]); bad_ok = False
    except DispatchError:
        bad_ok = True
    check("blank path fails closed", bad_ok)
    plan3 = plan_dispatch(["skills/z.md", "vscode/a.ts", "browser/b.ts"])
    check("sorted targets", [t.satellite for t in plan3.targets] == sorted(t.satellite for t in plan3.targets))
    plan4 = plan_dispatch(["vscode/a.ts", "vscode/a.ts", "vscode/b.ts"])
    vt4 = next(t for t in plan4.targets if t.satellite == "vscode")
    check("dedup", vt4.files == ("vscode/a.ts", "vscode/b.ts"))
    # 9. workflow appendix is valid YAML
    try:
        import yaml
        parsed = yaml.safe_load(render_workflow_yaml())
        yaml_ok = isinstance(parsed, dict) and "jobs" in parsed
    except Exception:  # noqa: BLE001
        yaml_ok = False
    check("workflow appendix parses as YAML", yaml_ok)

    # 10. source_sha traceability
    p = plan_dispatch(["vscode/a.ts"], source_sha="a" * 40)
    check("source_sha propagated", p.source_sha == "a" * 40 and p.to_dict()["source_sha"] == "a" * 40)
    ok = all(p for _, p in checks)
    print(f"self-test: {sum(1 for _, p in checks if p)}/{len(checks)} checks {'PASS' if ok else 'FAIL'}")
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description="Universal Federation Dispatch Engine core")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--paths", nargs="*")
    parser.add_argument("--paths-file")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--source-sha", default="", help="source commit SHA for traceability")
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if self_test() else 1
    paths = list(args.paths or [])
    if args.paths_file:
        with open(args.paths_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    paths.append(line)
    plan = plan_dispatch(paths, source_sha=args.source_sha)
    print(json.dumps(plan.to_dict(), indent=2))
    return 0


FEDERATION_WORKFLOW_YAML = """name: Federation — Auto-Sync (Universal Dispatch)
on:
  push: { branches: [main] }
  pull_request: { types: [closed], branches: [main] }
  workflow_dispatch:
    inputs:
      dry_run: { description: "Dry run", type: boolean, default: true }
jobs:
  dispatch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: python scripts/ci/federation_dispatch.py --paths-file /tmp/changed.txt --json
"""


def render_workflow_yaml() -> str:
    """Return the protected-path workflow appendix (operator applies)."""
    return FEDERATION_WORKFLOW_YAML


if __name__ == "__main__":
    raise SystemExit(main())
