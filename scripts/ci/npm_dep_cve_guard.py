#!/usr/bin/env python3
"""npm_dep_cve_guard.py — npm dependency CVE ratchet gate (#2059 R45, widened #2075 R46).

Mission (issue #2059, scout radar lane R45; widened by issue #2075, lane R46):
    The dependency-CVE doctrine (#1950 coverage map, extended by #1969/#1975
    and #2042) had one blind spot left: the control plane itself. The Tower
    (supremeai-mcp-tower, `infrastructure/mcp-control-plane/render.yaml`) is
    the service every agent loop, bridge work order, and zero-credential
    handshake runs through, and its buildCommand installs from TWO npm
    lockfiles (`npm install` over the control-plane lock + `npm ci --prefix
    ../../.agents/skills/devtools-audit`) — while the landed js gate
    (#1913) parses only studio/pnpm-lock.yaml. This guard closes that gap
    with the same shrink-only ratchet fed by the same advisory SSOT
    (api.osv.dev — the database behind GHSA/npm advisories that Trivy itself
    normalizes to), as a SIBLING of #1913: separate parser (npm package-
    lock.json v2/v3), separate baseline, identical ratchet semantics and
    exit contract. The sibling split (house style: #1975 is a sibling of
    #1913) keeps each plane's floor independently shrinkable — the baseline
    may never grow, per plane.

R46 widening (#2075, same-day landing):
    R45 scoped itself to the Tower control plane, which left three tracked
    npm lockfiles machine-invisible: browser/cloudflare-worker (the real
    wrangler-deployed edge worker — its only direct dep @cloudflare/puppeteer
    ^0.0.15 drags the whole puppeteer-core transitive tree onto the deploy
    surface), vscode, and vscode/extension (editor planes; the extension
    lock is an all-dev tree — an honest zero). The `.agents/skills`
    precedent already established the doctrine's surface as "every tracked
    production lockfile", not "every Render buildCommand input", so the
    three joins are the same ratchet, not a new doctrine. The widened
    floor is seeded from a LIVE 2026-10-28 querybatch at head 09a007c
    (4 vulnerable pairs / 9 advisory ids, all in the worker lock) — surface
    growth, never floor growth: every pre-existing R45 entry is untouched.

Behavior contract (the #1913/#1796 shrink-only ratchet, externalized to a
versioned baseline because the npm plane carries a REAL floor: the live
2026-10-28 OSV querybatch run puts 19 advisory ids on 8 production pairs in
the control-plane lock — @modelcontextprotocol/sdk 1.30.0 carries 6 of them,
including GHSA-22jm-h49p-29qw on the protocol SDK the federation runs on):

    1. Parses each tracked package-lock.json (lockfileVersion >= 2) into
       the unique set of PRODUCTION (name, version) pairs it pins:
       `packages["node_modules/<name>"]` entries, nested
       `node_modules/a/node_modules/b` keys reduced to their real package
       name, `dev: true` entries skipped (dev-only trees are outside the
       deploy surface this guard owns — the #2059 finding scope), and
       non-registry entries (link:/workspace/no-version) skipped.
    2. Queries api.osv.dev/v1/querybatch once per chunk (zero-credential,
       free public API) and aggregates vulnerable pairs to
       "<lockfile-path>:name@version" -> sorted [advisory id] — keys are
       lock-scoped so two locks can share one baseline without collision.
    3. Compares against scripts/ci/npm_dep_cve_baseline.json:
         - a pair absent from the baseline, or an advisory id inside a
           baselined pair that the baseline does not list, is DRIFT;
         - ids at or below the baseline are compliant (fewer ids is an
           improvement — shrink the baseline entry in the same change; the
           file may only ever shrink).
    4. Routing (issue #2059 adoption path): NEW advisory ids fail-close
       (exit 1). The fix for a new advisory is a MAINTAINER bump decision
       on the owning lockfile (or a deliberate floor reset via --baseline;
       the baseline diff in review IS the audit trail) — in particular the
       8 seeded @modelcontextprotocol/sdk / fast-uri / ip-address /
       body-parser / hono / proxy-addr / qs / zod entries are maintainer
       bump lanes, NEVER agent edits. This guard reports findings; it
       NEVER edits a lockfile or bumps pins.
    5. Honest degradation (#1760 pattern): when the OSV API is unreachable
       after retries the guard skips with evidence (exit 0, note emitted) —
       it never fabricates a PASS. A lockfile that exists but cannot be
       READ is a surface change and fail-closes (the #1913
       unreadable-lockfile analog); a MISSING tracked lockfile is likewise
       a surface change and fail-closes.
    6. `--baseline` regenerates the versioned baseline at the CURRENT head
       (admin floor reset; review the diff). `--json` emits a machine
       report. `--files f1 ...` (pre-push mode) runs the full check only
       when the changed set intersects the guard's surface (the five
       package-lock paths + the Tower render.yaml, because buildCommand
       supply-chain claims live there, + the worker wrangler.toml, because
       the edge-worker deploy claims live there); otherwise honest skip.

Never-do (issue #1913/#1969/#2059 doctrine): no auto pin bumps; no lockfile
edits; the baseline may never grow ON A FIXED SURFACE (a surface widening
seeds its own findings in the same change, as R46 did); no scanning
.github/**; no secret values involved (advisory ids and package coordinates
only).

Usage:
    python scripts/ci/npm_dep_cve_guard.py --check            # roster mode
    python scripts/ci/npm_dep_cve_guard.py --files a b        # pre-push mode
    python scripts/ci/npm_dep_cve_guard.py --baseline         # regenerate floor
    python scripts/ci/npm_dep_cve_guard.py --json             # machine report
    python scripts/ci/npm_dep_cve_guard.py --self-test        # hermetic

Exit codes: 0 = pass / known-floor / honest skip · 1 = new drift ·
2 = usage error.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_TAG = "[npm-dep-cve-guard]"
BASELINE_PATH = Path("scripts/ci/npm_dep_cve_baseline.json")
LOCK_PATHS = (
    Path("infrastructure/mcp-control-plane/package-lock.json"),
    Path(".agents/skills/devtools-audit/package-lock.json"),
    # R46 widening (#2075): the remaining tracked npm lockfiles. The worker
    # lock is the headline (wrangler-deployed edge worker, 87 production
    # pairs, dev-zero); the two vscode locks are editor planes (10 and 0
    # production pairs — the extension lock is an all-dev honest zero).
    Path("browser/cloudflare-worker/package-lock.json"),
    Path("vscode/package-lock.json"),
    Path("vscode/extension/package-lock.json"),
)
# render.yaml carries the buildCommand that consumes both locks; its
# supply-chain claims (#707 uv pin comment vs command) are part of this
# guard's surface so pushes that touch them run the ratchet. wrangler.toml
# is the worker's deploy blueprint (#2075 deploy-surface identity) — same
# reasoning, same ratchet.
SURFACE_PATHS = tuple(str(p) for p in LOCK_PATHS) + (
    "infrastructure/mcp-control-plane/render.yaml",
    "browser/cloudflare-worker/wrangler.toml",
)

EXIT_PASS = 0
EXIT_DRIFT = 1
EXIT_USAGE = 2

OSV_QUERYBATCH = "https://api.osv.dev/v1/querybatch"
OSV_CHUNK = 250
OSV_TIMEOUT = 120
OSV_RETRIES = 3
ECOSYSTEM = "npm"


def _evidence(msg: str) -> None:
    print(f"{GUARD_TAG} {msg}")


def load_lock_pairs(lock_path: Path) -> tuple[list[tuple[str, str]], dict]:
    """Parse an npm package-lock.json (v2/v3) into its PRODUCTION pin set.

    Reads the `packages` mapping; `node_modules/<name>` keys contribute
    (name, version) unless the entry is `dev: true` (dev-only tree,
    outside the deploy surface), has no semver version (link/workspace
    entries), or is the root "" entry. Nested keys
    ("node_modules/a/node_modules/b") reduce to the innermost package
    name — npm semantics: the nested entry is what that subtree resolves.
    Returns (sorted pairs, skip counters) and raises ValueError/IOError
    for structural unreadability (fail-close decision lives in evaluate).
    """
    doc = json.loads(lock_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("lockfile malformed: top level must be an object")
    if int(doc.get("lockfileVersion") or 0) < 2:
        raise ValueError(
            f"lockfile unsupported: lockfileVersion {doc.get('lockfileVersion')!r} < 2"
        )
    packages = doc.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("lockfile malformed: 'packages' must be an object")
    pairs: set[tuple[str, str]] = set()
    skipped: dict = {"dev": 0, "non_registry": 0}
    for key, entry in packages.items():
        if not key:
            skipped["non_registry"] += 1  # root entry, not a dependency
            continue
        if not key.startswith("node_modules/"):
            skipped["non_registry"] += 1
            continue
        name = key[len("node_modules/"):].split("/node_modules/")[-1]
        if not isinstance(entry, dict):
            raise ValueError(f"lockfile malformed: entry {key!r} is not an object")
        if entry.get("dev") is True:
            skipped["dev"] += 1
            continue
        version = entry.get("version")
        if not isinstance(version, str) or not version or not version[0].isdigit():
            skipped["non_registry"] += 1  # link:/workspace:/no version
            continue
        pairs.add((name, version))
    return sorted(pairs), skipped


def query_osv_batch(
    pairs: list[tuple[str, str]], endpoint: str = OSV_QUERYBATCH
) -> dict[tuple[str, str], list[str]]:
    """One querybatch POST per OSV_CHUNK pairs; returns pair -> advisory ids.

    Raises RuntimeError after OSV_RETRIES failed attempts on any chunk —
    the honest-skip decision lives in evaluate().
    """
    queries = [
        {"package": {"name": name, "ecosystem": ECOSYSTEM}, "version": version}
        for name, version in pairs
    ]
    found: dict[tuple[str, str], list[str]] = {}
    for start in range(0, len(queries), OSV_CHUNK):
        batch = queries[start:start + OSV_CHUNK]
        body = json.dumps({"queries": batch}).encode("utf-8")
        response: dict = {}
        last_error: Exception | None = None
        for attempt in range(OSV_RETRIES):
            try:
                req = urllib.request.Request(
                    endpoint,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=OSV_TIMEOUT) as resp:
                    response = json.loads(resp.read().decode("utf-8"))
                last_error = None
                break
            except Exception as exc:  # retried below, evidence kept
                last_error = exc
                if attempt < OSV_RETRIES - 1:
                    time.sleep(2 * (attempt + 1))
        if last_error is not None:
            raise RuntimeError(
                f"OSV querybatch unreachable after {OSV_RETRIES} attempt(s): {last_error}"
            )
        results = response.get("results")
        if not isinstance(results, list) or len(results) != len(batch):
            raise ValueError(
                f"OSV querybatch response malformed: expected {len(batch)} results"
            )
        for query, result in zip(batch, results):
            vulns = (result or {}).get("vulns") or []
            if not vulns:
                continue
            key = (query["package"]["name"], query["version"])
            ids = sorted({str(v.get("id")) for v in vulns if v.get("id")})
            if ids:
                found[key] = ids
        if start + OSV_CHUNK < len(queries):
            time.sleep(1.0)
    return found


def compare(
    current: dict[str, list[str]], baseline: dict[str, list[str]]
) -> tuple[list[dict], list[dict]]:
    """Ratchet compare keyed '<lock>:name@version' -> sorted advisory ids.

    drift: new pair, or an id inside a known pair that the baseline omits.
    improvements: baselined ids/pairs that disappeared (shrink-the-floor
    hints — the baseline entry may be removed in the same change).
    """
    drift: list[dict] = []
    improvements: list[dict] = []
    for pair in sorted(current):
        cur = list(current[pair])
        base = baseline.get(pair, [])
        new_ids = [i for i in cur if i not in base]
        if not base:
            drift.append({"pair": pair, "ids": new_ids, "kind": "new-pair"})
        elif new_ids:
            drift.append({"pair": pair, "ids": new_ids, "kind": "new-id"})
    for pair in sorted(baseline):
        gone = [i for i in baseline[pair] if i not in current.get(pair, [])]
        if gone or pair not in current:
            remaining = current.get(pair, [])
            improvements.append(
                {"pair": pair, "resolved_ids": gone, "remaining": remaining}
            )
    return drift, improvements


def git_head(repo_root: Path) -> str:
    try:
        out = subprocess_run(
            ["git", "log", "-1", "--format=%h %ad", "--date=short"], cwd=repo_root
        )
        return out.strip() or "unknown"
    except Exception as exc:  # provenance is best-effort, recorded as evidence
        return f"unknown (git probe failed: {exc.__class__.__name__})"


def subprocess_run(cmd: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=30, check=False
    )
    return proc.stdout


def build_baseline_report(repo_root: Path) -> dict:
    """Live lockfiles + OSV probe -> the versioned baseline document."""
    findings: dict[str, list[str]] = {}
    totals = {"pairs_scanned": 0, "skipped_dev": 0, "skipped_non_registry": 0}
    per_lock: dict[str, dict] = {}
    for rel in LOCK_PATHS:
        lock = repo_root / rel
        pairs, skipped = load_lock_pairs(lock)
        found = query_osv_batch(pairs)
        for (n, v), ids in found.items():
            findings[f"{rel.as_posix()}:{n}@{v}"] = ids
        per_lock[rel.as_posix()] = {
            "pairs_scanned": len(pairs),
            "vulnerable_pairs": len(found),
        }
        totals["pairs_scanned"] += len(pairs)
        totals["skipped_dev"] += skipped["dev"]
        totals["skipped_non_registry"] += skipped["non_registry"]
    total_ids = sum(len(ids) for ids in findings.values())
    return {
        "meta": {
            "issue": 2075,
            "tool": "osv-querybatch (api.osv.dev/v1/querybatch, zero-credential)",
            "lockfiles": [p.as_posix() for p in LOCK_PATHS],
            "ecosystem": ECOSYSTEM,
            "dev_entries_skipped": True,
            "head": git_head(repo_root),
            "dated": "2026-10-28",
            "totals": {
                **totals,
                "vulnerable_pairs": len(findings),
                "vuln_ids": total_ids,
            },
            "per_lock": per_lock,
            "doctrine": (
                "shrink-only ratchet: entries and ids may only be REMOVED (in the "
                "same change that resolves them — a maintainer pin bump or an "
                "upstream fix absorbed by a floor reset). A new pair or a new "
                "advisory id is drift; the baseline may never grow. Seeded floor "
                "is the LIVE 2026-10-28 audit result (the #2033 lesson), not an "
                "assumed-empty one."
            ),
        },
        "findings": dict(sorted(findings.items())),
    }


def load_baseline(repo_root: Path) -> tuple[dict[str, list[str]], dict]:
    """Load the versioned baseline. Unreadable baseline is fail-closed drift."""
    path = repo_root / BASELINE_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"baseline missing: {BASELINE_PATH} (run --baseline to create)"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    findings = data.get("findings")
    if not isinstance(findings, dict):
        raise ValueError("baseline malformed: 'findings' must be an object")
    clean: dict[str, list[str]] = {}
    for pair, ids in findings.items():
        if not isinstance(pair, str) or not isinstance(ids, list):
            raise ValueError("baseline malformed: findings must be pair -> id list")
        clean[pair] = [str(i) for i in ids]
    return clean, data.get("meta", {})


def evaluate(repo_root: Path, files: list[str] | None = None) -> tuple[int, list[dict], list[dict], list[str]]:
    """Single decision tree. Returns (exit, drift, improvements, notes)."""
    notes: list[str] = []
    if files is not None:
        touched = [f for f in files if f in SURFACE_PATHS]
        if not touched:
            notes.append(
                "changed set does not touch the npm dependency surface "
                f"({', '.join(SURFACE_PATHS)}) — nothing to check"
            )
            return EXIT_PASS, [], [], notes

    # Parse phase: a missing or unreadable tracked lockfile is a surface
    # change and fail-closes (the #1913 unreadable-lockfile analog).
    lock_findings: dict[str, list[str]] = {}
    scanned = 0
    try:
        for rel in LOCK_PATHS:
            lock = repo_root / rel
            if not lock.is_file():
                raise FileNotFoundError(f"tracked lockfile missing: {rel}")
            pairs, skipped = load_lock_pairs(lock)
            scanned += len(pairs)
            found = query_osv_batch(pairs)
            for (n, v), ids in found.items():
                lock_findings[f"{rel.as_posix()}:{n}@{v}"] = ids
    except FileNotFoundError as exc:
        _evidence(f"DRIFT (fail-close): {exc}")
        return EXIT_DRIFT, [{"pair": "*", "ids": [], "kind": "surface-change"}], [], notes
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        _evidence(f"DRIFT (fail-close): lockfile unreadable: {exc}")
        return EXIT_DRIFT, [{"pair": "*", "ids": [], "kind": "surface-change"}], [], notes
    except RuntimeError as exc:  # OSV unreachable — honest skip, never fake PASS
        _evidence(f"HONEST SKIP: {exc}")
        notes.append("osv-unreachable: skip with evidence, no PASS fabricated")
        return EXIT_PASS, [], [], notes

    try:
        baseline, meta = load_baseline(repo_root)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        _evidence(f"DRIFT (fail-close): baseline unusable: {exc}")
        return EXIT_DRIFT, [{"pair": "*", "ids": [], "kind": "baseline-unusable"}], [], notes

    drift, improvements = compare(lock_findings, baseline)
    notes.append(f"surface: {len(LOCK_PATHS)} tracked npm lockfile(s), {scanned} production pair(s) scanned")
    notes.append(f"baseline: {len(baseline)} pair(s) at floor, meta.dated={meta.get('dated', 'unknown')}")
    if drift:
        _evidence(f"DRIFT: {len(drift)} new finding(s) on the npm dependency plane")
        for d in drift:
            _evidence(f"  {d['kind']}: {d['pair']} -> {d['ids']}")
        _evidence(
            "routing: pin bumps are MAINTAINER decisions on the owning lockfile; "
            "deliberate re-floor is an admin --baseline reset reviewed as a diff"
        )
        return EXIT_DRIFT, drift, improvements, notes
    if improvements:
        _evidence(
            f"ratchet hint: {len(improvements)} baseline entr(ies) resolved on the live tree — "
            "shrink the baseline in the same change"
        )
    _evidence("ratchet clean: no new advisory ids on the npm dependency plane")
    return EXIT_PASS, [], improvements, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="npm dependency CVE ratchet gate (#2059 R45, widened #2075 R46)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="full roster check")
    mode.add_argument("--files", nargs="*", help="pre-push changed-set mode")
    mode.add_argument("--baseline", action="store_true", help="regenerate the floor (admin)")
    mode.add_argument("--json", action="store_true", help="machine report")
    mode.add_argument("--self-test", action="store_true", help="hermetic self-test")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if args.baseline:
        report = build_baseline_report(REPO_ROOT)
        path = REPO_ROOT / BASELINE_PATH
        path.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        _evidence(f"baseline written: {BASELINE_PATH} (review the diff — the floor may only shrink)")
        return EXIT_PASS

    if args.json:
        report = build_baseline_report(REPO_ROOT)
        print(json.dumps(report, indent=2, sort_keys=False))
        return EXIT_PASS

    files = args.files if args.files is not None else None
    if args.files is not None and not args.files:
        # `--files` with an empty changed set: nothing on the surface to check
        _evidence("changed set empty — nothing to check")
        return EXIT_PASS

    exit_code, drift, improvements, notes = evaluate(REPO_ROOT, files)
    for n in notes:
        _evidence(f"note | {n}")
    return exit_code


def run_self_test() -> int:
    """Hermetic self-test: parser, ratchet, decision tree — zero network."""
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        if cond:
            _evidence(f"self-test OK: {name}")
        else:
            failures.append(name)
            _evidence(f"self-test FAIL: {name}")

    import tempfile

    # 1. parser: plain + scoped names, nested node_modules, dev skip, links
    with tempfile.TemporaryDirectory() as td:
        lock = Path(td) / "package-lock.json"
        lock.write_text(json.dumps({
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "root", "version": "1.0.0"},
                "node_modules/express": {"version": "4.21.2"},
                "node_modules/@modelcontextprotocol/sdk": {"version": "1.30.0"},
                "node_modules/a/node_modules/left-pad": {"version": "1.3.0"},
                "node_modules/devdep": {"version": "9.9.9", "dev": True},
                "node_modules/linked": {"resolved": "packages/linked", "link": True},
                "node_modules/qs": {"version": "6.16.0", "dev": False},
            },
        }))
        pairs, skipped = load_lock_pairs(lock)
        got = sorted(pairs)
        check("parser exact set", got == sorted([
            ("@modelcontextprotocol/sdk", "1.30.0"),
            ("left-pad", "1.3.0"),
            ("express", "4.21.2"),
            ("qs", "6.16.0"),
        ]))
        check("parser dev skipped", skipped["dev"] == 1)
        check("parser non-registry skipped", skipped["non_registry"] == 2)

    # 2. parser: v1 lockfiles are out of contract (no packages map)
    with tempfile.TemporaryDirectory() as td:
        lock = Path(td) / "package-lock.json"
        lock.write_text(json.dumps({"lockfileVersion": 1, "dependencies": {}}))
        try:
            load_lock_pairs(lock)
            check("v1 rejected", False)
        except ValueError:
            check("v1 rejected", True)

    # 3. ratchet semantics
    check("equal floor passes", compare(
        {"l:n@1": ["GHSA-a"]}, {"l:n@1": ["GHSA-a"]}) == ([], []))
    drift, _ = compare({"l:n@1": ["GHSA-a", "GHSA-b"]}, {"l:n@1": ["GHSA-a"]})
    check("new id inside known pair is drift",
          drift == [{"pair": "l:n@1", "ids": ["GHSA-b"], "kind": "new-id"}])
    drift, _ = compare({"l:new@2": ["GHSA-c"]}, {"l:n@1": ["GHSA-a"]})
    check("new pair is drift",
          drift == [{"pair": "l:new@2", "ids": ["GHSA-c"], "kind": "new-pair"}])
    _, improvements = compare({}, {"l:n@1": ["GHSA-a"]})
    check("vanished pair is improvement",
          improvements == [{"pair": "l:n@1", "resolved_ids": ["GHSA-a"], "remaining": []}])

    # 4. decision tree (hermetic: monkeypatched OSV, temp repo)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "infrastructure/mcp-control-plane").mkdir(parents=True)
        (root / ".agents/skills/devtools-audit").mkdir(parents=True)
        (root / "browser/cloudflare-worker").mkdir(parents=True)
        (root / "vscode/extension").mkdir(parents=True)
        (root / "scripts/ci").mkdir(parents=True)
        (root / "infrastructure/mcp-control-plane/package-lock.json").write_text(
            json.dumps({"lockfileVersion": 3, "packages": {
                "node_modules/express": {"version": "4.21.2"}}}))
        (root / ".agents/skills/devtools-audit/package-lock.json").write_text(
            json.dumps({"lockfileVersion": 3, "packages": {
                "node_modules/zod": {"version": "4.6.4"}}}))
        # R46 widened roster: the temp repo must carry ALL tracked locks,
        # else evaluate() fail-closes on a missing tracked lockfile.
        (root / "browser/cloudflare-worker/package-lock.json").write_text(
            json.dumps({"lockfileVersion": 3, "packages": {
                "node_modules/tar-fs": {"version": "3.0.4"}}}))
        (root / "vscode/package-lock.json").write_text(
            json.dumps({"lockfileVersion": 3, "packages": {
                "node_modules/devthing": {"version": "1.0.0", "dev": True}}}))
        (root / "vscode/extension/package-lock.json").write_text(
            json.dumps({"lockfileVersion": 3, "packages": {
                "node_modules/devonly": {"version": "2.0.0", "dev": True}}}))

        baseline = {"findings": {
            "infrastructure/mcp-control-plane/package-lock.json:express@4.21.2": ["GHSA-known"],
        }, "meta": {"dated": "2026-10-28"}}
        (root / BASELINE_PATH).write_text(json.dumps(baseline))

        def fake_osv(pairs, endpoint=OSV_QUERYBATCH):
            # Mimic the real query_osv_batch contract: only pairs WITH ids
            # appear in the result (empty responses are absent, not []).
            return {p: ["GHSA-known"] for p in pairs if p == ("express", "4.21.2")}

        # The script runs as __main__; patch THIS module's global (importing
        # npm_dep_cve_guard would create a second module instance and the
        # monkeypatch would never be seen by evaluate()).
        orig_query = globals()["query_osv_batch"]

        def _use(fn):
            globals()["query_osv_batch"] = fn

        try:
            _use(fake_osv)
            code, drift, imp, notes = evaluate(root, files=None)
            check("known floor passes (exit 0)", code == EXIT_PASS and not drift)
            # new advisory id appears on a known pair -> drift exit 1
            _use(lambda pairs, endpoint=OSV_QUERYBATCH: {
                p: (["GHSA-known", "GHSA-NEW"] if p == ("express", "4.21.2") else [])
                for p in pairs if p == ("express", "4.21.2")})
            code, drift, imp, notes = evaluate(root, files=None)
            check("new id fail-closes (exit 1)", code == EXIT_DRIFT
                  and drift and drift[0]["kind"] == "new-id")
            # OSV unreachable -> honest skip exit 0, never fake PASS
            def boom(pairs, endpoint=OSV_QUERYBATCH):
                raise RuntimeError("OSV querybatch unreachable after 3 attempt(s)")
            _use(boom)
            code, drift, imp, notes = evaluate(root, files=None)
            check("osv unreachable honest-skip (exit 0, no drift)",
                  code == EXIT_PASS and not drift
                  and any("osv-unreachable" in n for n in notes))
            # unreadable baseline -> fail-close
            _use(fake_osv)
            (root / BASELINE_PATH).write_text("{not json")
            code, drift, imp, notes = evaluate(root, files=None)
            check("malformed baseline fail-closes", code == EXIT_DRIFT
                  and drift and drift[0]["kind"] == "baseline-unusable")
            (root / BASELINE_PATH).write_text(json.dumps(baseline))
            # tracked lockfile deleted -> surface change fail-close
            (root / ".agents/skills/devtools-audit/package-lock.json").unlink()
            code, drift, imp, notes = evaluate(root, files=None)
            check("missing tracked lock fail-closes", code == EXIT_DRIFT
                  and drift and drift[0]["kind"] == "surface-change")
            (root / ".agents/skills/devtools-audit/package-lock.json").write_text(
                json.dumps({"lockfileVersion": 3, "packages": {
                    "node_modules/zod": {"version": "4.6.4"}}}))
            # --files off-surface -> honest skip
            code, drift, imp, notes = evaluate(root, files=["README.md"])
            check("off-surface --files honest skip", code == EXIT_PASS
                  and any("does not touch" in n for n in notes))
            # --files on-surface (render.yaml counts) -> full check runs
            code, drift, imp, notes = evaluate(
                root, files=["infrastructure/mcp-control-plane/render.yaml"])
            check("render.yaml in surface runs check", code == EXIT_PASS and not drift)
        finally:
            globals()["query_osv_batch"] = orig_query

    if failures:
        _evidence(f"SELF-TEST FAILED: {failures}")
        return EXIT_DRIFT
    _evidence("SELF-TEST OK: npm_dep_cve_guard")
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
