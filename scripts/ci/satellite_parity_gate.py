#!/usr/bin/env python3
"""scripts/ci/satellite_parity_gate.py — scheduled mirror<->satellite drift gate (#1792).

Report-only scheduled counterpart of federation_satellite_sync.py --verify-only
(#1689). Reads scripts/ci/satellite_sentinels.json and verifies every sentinel
pair byte-identical between this open monorepo mirror and the GitHub satellite
repos (supremeai-api / -core / -browser / -studio / -vscode).

Design contract (verbatim from #1792):
  - report-only: drift is DETECTED and REPORTED (exit 1 + JSON report + optional
    issue body). The gate NEVER pushes, merges, or dispatches — dispatch
    authority stays with humans/admins per the bridge contract.
  - fail-closed: infrastructure errors (auth, network, rate limit) are exit 2,
    never silently reported as "clean". A gate that cannot see must not vote.
  - config-driven: pairs come from scripts/ci/satellite_sentinels.json (the
    #1689 manifest). Extend the manifest to grow the sweep — no code edit.

Modes:
  --check             human-readable run (default)
  --json              machine-readable JSON report on stdout (implies --check)
  --issue-body PATH   write a report-only drift work-order body to PATH
                      (api_drift_detail.py template: byte-size delta + hunk
                      summary). Only written when drift or errors exist.
  --all-remote        fetch the OPEN side live too (no local checkout needed;
                      agent/tower mode). Default: open side read from checkout.
  --ref REF           git ref for both sides (default: main)
  --manifest PATH     override the sentinel manifest path
  --token-env NAME    env var holding a read-only PAT (default SAT_SYNC_PAT;
                      falls back OPEN_SYNC_PAT, then GITHUB_TOKEN)

Exit codes (same family as federation_satellite_sync.py):
  0  all pairs verified byte-identical
  1  drift detected (actionable; report printed, issue body written if asked)
  2  infra/verification error (fail-closed)

stdlib-only; offline-testable (tests/test_satellite_parity_gate.py).
"""

from __future__ import annotations

import argparse
import base64
import difflib
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MANIFEST = Path("scripts/ci/satellite_sentinels.json")
DEFAULT_OPEN_REPO = "Supremeai-bd/supremeai-open"
TOKEN_ENV_CHAIN = ["SAT_SYNC_PAT", "OPEN_SYNC_PAT", "GITHUB_TOKEN"]
MAX_DIFF_HUNKS = 3
MAX_DIFF_LINES = 40
UA = "supremeai-satellite-parity-gate"

EXIT_CLEAN = 0
EXIT_DRIFT = 1
EXIT_INFRA = 2


# ---------------------------------------------------------------- fetching


def resolve_token(token_env: str | None = None) -> str:
    """Pick the first readable token env (least-privilege read-only PAT)."""
    chain = [token_env] if token_env else list(TOKEN_ENV_CHAIN)
    for name in chain:
        if name and os.environ.get(name, "").strip():
            return os.environ[name].strip()
    raise RuntimeError(
        "no read token found; set one of: " + ", ".join(c for c in chain if c)
    )


def fetch_blob(repo: str, path: str, token: str, ref: str = "main") -> bytes | None:
    """Fetch a file blob via the GitHub contents API (stdlib only).

    Returns decoded bytes, or None for definitive absence (404).
    Raises on infrastructure errors — callers must treat raised errors as
    fail-closed verification failures, never as drift and never as clean.
    """
    api = f"https://api.github.com/repos/{repo}/contents/{path}?ref={ref}"
    req = urllib.request.Request(
        api,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310 — read-only federation probe; endpoint from repo manifest, audited #2081
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    content = data.get("content")
    if content is None:
        return None
    return base64.b64decode(content)


def read_open_side(pair: dict, repo_root: Path | None, token: str, ref: str,
                   all_remote: bool, open_repo: str) -> bytes:
    """Open-side bytes: from the local checkout (default) or fetched live."""
    open_rel = str(pair.get("open", "")).strip()
    if all_remote or repo_root is None or not (repo_root / open_rel).exists():
        if all_remote:
            data = fetch_blob(open_repo, open_rel, token, ref)
            if data is None:
                raise FileNotFoundError(f"open-side surface absent: {open_repo}:{open_rel}")
            return data
        raise FileNotFoundError(f"open-side file missing in checkout: {open_rel}")
    return (repo_root / open_rel).read_bytes()


# ---------------------------------------------------------------- analysis


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hunk_summary(open_bytes: bytes, sat_bytes: bytes, context: bool = True) -> str:
    """api_drift_detail.py-style drift detail: byte-size delta + capped hunks.

    Plain-text block suitable for a report-only issue body. Text decoded with
    errors=replace so binary-ish drift still yields a size-delta report.
    """
    o_txt = open_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
    s_txt = sat_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
    delta = len(open_bytes) - len(sat_bytes)
    sign = "+" if delta > 0 else ("-" if delta < 0 else "0")
    lines: list[str] = [
        f"- byte-size delta: open {len(open_bytes):,} B vs satellite {len(sat_bytes):,} B "
        f"(open {sign}{abs(delta):,} B)",
        f"- sha256: open {sha256_hex(open_bytes)[:16]} / satellite {sha256_hex(sat_bytes)[:16]}",
    ]
    diff = list(difflib.unified_diff(s_txt, o_txt,
                                     fromfile="satellite (live)", tofile="open (mirror)",
                                     n=3 if context else 0))
    if not diff:
        lines.append("- unified diff: empty (files differ only in bytes outside text view)")
    else:
        lines.append(f"- unified hunks (first {MAX_DIFF_HUNKS} hunks, capped {MAX_DIFF_LINES} lines):")
        shown: list[str] = []
        hunk_count = 0
        for ln in diff:
            if ln.startswith("@@"):
                hunk_count += 1
                if hunk_count > MAX_DIFF_HUNKS:
                    break
            if len(shown) >= MAX_DIFF_LINES:
                shown.append("  … (truncated)")
                break
            shown.append("  " + ln.rstrip("\n"))
        lines.extend(shown)
    return "\n".join(lines)


def classify_pair(pair: dict, open_bytes: bytes | None, sat_bytes: bytes | None,
                  error: str | None) -> tuple[str, dict]:
    """Classify one pair -> ("clean" | "drift" | "error", detail dict)."""
    if error is not None:
        return "error", {"pair": pair, "detail": error}
    if open_bytes is None:
        return "error", {"pair": pair, "detail": "open-side surface absent"}
    if sat_bytes is None:
        return "drift", {"pair": pair, "detail": "satellite surface absent",
                         "hunks": None,
                         "open_sha256": sha256_hex(open_bytes)[:16],
                         "open_size": len(open_bytes)}
    if sha256_hex(open_bytes) == sha256_hex(sat_bytes):
        return "clean", {"pair": pair,
                         "sha256": sha256_hex(open_bytes)[:16],
                         "size": len(open_bytes)}
    return "drift", {"pair": pair,
                     "detail": "content divergence",
                     "hunks": hunk_summary(open_bytes, sat_bytes),
                     "open_sha256": sha256_hex(open_bytes)[:16],
                     "sat_sha256": sha256_hex(sat_bytes)[:16],
                     "open_size": len(open_bytes),
                     "sat_size": len(sat_bytes)}


def run_gate(pairs: list[dict], token: str, ref: str = "main",
             repo_root: Path | None = None, all_remote: bool = False,
             open_repo: str = DEFAULT_OPEN_REPO,
             fetcher=fetch_blob) -> dict:
    """Verify every manifest pair. Returns a report dict (JSON-ready).

    fetcher is injectable for offline tests (same signature as fetch_blob).
    """
    clean: list[dict] = []
    drift: list[dict] = []
    errors: list[dict] = []
    for pair in pairs:
        open_rel = str(pair.get("open", "")).strip()
        sat_repo = str(pair.get("satellite", "")).strip()
        sat_rel = str(pair.get("path", "")).strip()
        if not (open_rel and sat_repo and sat_rel):
            errors.append({"pair": pair, "detail": "malformed pair (requires open/satellite/path)"})
            continue
        ob = sb = None
        err = None
        try:
            ob = read_open_side(pair, repo_root, token, ref, all_remote, open_repo)
        except FileNotFoundError as e:
            err = str(e)
        except Exception as e:  # infra on open side
            err = f"open-side fetch failed: {e}"
        if err is None:
            try:
                sb = fetcher(sat_repo, sat_rel, token, ref)
            except Exception as e:  # infra on satellite side
                err = f"satellite-side fetch failed: {e}"
        verdict, detail = classify_pair(pair, ob, sb, err)
        if verdict == "clean":
            clean.append(detail)
        elif verdict == "drift":
            drift.append(detail)
        else:
            errors.append(detail)
    now = datetime.now(timezone.utc)
    return {
        "gate": "satellite_parity_gate",
        "provenance": {"issue": 1792, "kernel": "#1689 sentinel SHA method (run 7)"},
        "checkedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ref": ref,
        "allRemote": bool(all_remote),
        "summary": {"total": len(pairs), "clean": len(clean),
                    "drift": len(drift), "errors": len(errors)},
        "clean": clean,
        "drift": drift,
        "errors": errors,
    }


# ---------------------------------------------------------------- reporting


def build_issue_body(report: dict) -> str:
    """Report-only drift work-order body (api_drift_detail.py template)."""
    s = report["summary"]
    title = (
        f"federation: satellite parity drift — {s['drift']} drift / "
        f"{s['errors']} infra error of {s['total']} sentinels "
        f"(auto, report-only @ {report['checkedAt']})"
    )
    lines = [
        f"## {title}",
        "",
        f"- Gate: `scripts/ci/satellite_parity_gate.py` (#1792, scheduled; kernel: "
        f"#1689 sentinel SHA method). Ref `{report['ref']}`.",
        "- **Report-only**: no push, no merge, no dispatch was performed by this "
        "gate. Dispatch authority stays with humans/admins per the bridge contract.",
        "- Fail-closed note: `errors` are infrastructure/verification failures — "
        "the gate could NOT see; treat as blind, not clean.",
        "",
        "### Drift detail (byte-size delta + hunk summary)",
        "",
    ]
    for d in report["drift"]:
        p = d["pair"]
        lines.append(f"#### `{p.get('open')}` <-> `{p.get('satellite')}:{p.get('path')}`")
        lines.append("")
        if d.get("hunks"):
            lines.append(d["hunks"])
        else:
            lines.append(f"- {d.get('detail')} "
                         f"(open sha256 {d.get('open_sha256','?')}, {d.get('open_size','?'):,} B)")
        lines.append("")
    if report["errors"]:
        lines += ["### Verification errors (fail-closed)", ""]
        for e in report["errors"]:
            p = e["pair"]
            lines.append(f"- `{p.get('open')}` <-> `{p.get('satellite')}:{p.get('path')}`: {e.get('detail')}")
        lines.append("")
    lines += [
        "### Remediation (admin/coder)",
        "",
        "1. Confirm the drift is not a satellite-side intended change (read the",
        "   satellite repo's history for the surface first).",
        "2. If the mirror is ahead intentionally: re-dispatch "
        "`federation_satellite_sync.py` (heal) per the #1689 runbook.",
        "3. If the drift is a regression: revert the satellite surface to the",
        "   mirror blob SHA listed above.",
        "",
        f"_Provenance: #1792 R38 (scout radar XII); detection latency target <=6 h; "
        f"generated {report['checkedAt']} by the scheduled parity gate. "
        f"Labels: audit:finding, federation:drift._",
    ]
    return "\n".join(lines)


def exit_code_for(report: dict) -> int:
    s = report["summary"]
    if s["errors"]:
        return EXIT_INFRA
    if s["drift"]:
        return EXIT_DRIFT
    return EXIT_CLEAN


# ---------------------------------------------------------------- self-test


def self_test() -> bool:
    """Offline contract checks (no network)."""
    p1 = {"open": "a", "satellite": "r", "path": "b"}
    if not (classify_pair(p1, b"x", b"x", None)[0] == "clean"):
        raise AssertionError()
    v, d = classify_pair(p1, b"x" * 10, b"y", None)
    if not (v == "drift" and "byte-size delta" in d["hunks"]):
        raise AssertionError()
    if not (classify_pair(p1, None, None, "boom")[0] == "error"):
        raise AssertionError()
    if not (classify_pair(p1, b"x", None, None)[0] == "drift"):
        raise AssertionError()
    if not (exit_code_for({"summary": {"errors": 0, "drift": 0, "total": 1}}) == EXIT_CLEAN):
        raise AssertionError()
    if not (exit_code_for({"summary": {"errors": 0, "drift": 2, "total": 3}}) == EXIT_DRIFT):
        raise AssertionError()
    if not (exit_code_for({"summary": {"errors": 1, "drift": 0, "total": 3}}) == EXIT_INFRA):
        raise AssertionError()
    rep = {"checkedAt": "T", "ref": "main", "summary": {"drift": 1, "errors": 0, "total": 2},
           "drift": [{"pair": p1, "detail": "content divergence", "hunks": "- byte-size delta: x"}],
           "errors": []}
    body = build_issue_body(rep)
    if not ("Report-only" in body and "byte-size delta" in body and "#1792" in body):
        raise AssertionError()
    if not (resolve_token.__doc__):
        raise AssertionError()
    return True


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="scheduled mirror<->satellite parity gate (#1792)")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON report on stdout")
    ap.add_argument("--issue-body", metavar="PATH", help="write report-only drift WO body to PATH")
    ap.add_argument("--all-remote", action="store_true",
                    help="fetch the open side live too (no checkout needed)")
    ap.add_argument("--ref", default="main")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--token-env", default=None,
                    help="env var name holding the read-only PAT (default: SAT_SYNC_PAT chain)")
    ap.add_argument("--open-repo", default=DEFAULT_OPEN_REPO)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        ok = self_test()
        print("self-test:", "PASS" if ok else "FAIL")
        return EXIT_CLEAN if ok else EXIT_INFRA

    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        pairs = manifest.get("pairs") or []
    except Exception as e:
        print(f"gate INFRA: cannot read manifest {args.manifest}: {e}", file=sys.stderr)
        return EXIT_INFRA
    if not pairs:
        print("gate INFRA: manifest has no pairs (refusing to vote clean on blindness)",
              file=sys.stderr)
        return EXIT_INFRA

    try:
        token = resolve_token(args.token_env)
        report = run_gate(pairs, token, ref=args.ref,
                          repo_root=Path.cwd(), all_remote=args.all_remote,
                          open_repo=args.open_repo)
    except Exception as e:
        print(f"gate INFRA: {e}", file=sys.stderr)
        return EXIT_INFRA

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        s = report["summary"]
        print(f"satellite parity gate: {s['clean']}/{s['total']} clean, "
              f"{s['drift']} drift, {s['errors']} errors")
        for c in report["clean"]:
            print(f"  OK    {c['pair']['open']} == {c['pair']['satellite']}:{c['pair']['path']}")
        for d in report["drift"]:
            print(f"  DRIFT {d['pair']['open']} != {d['pair']['satellite']}:{d['pair']['path']}")
        for e in report["errors"]:
            print(f"  ERROR {e['pair'].get('open','?')}: {e.get('detail')}")
        if args.issue_body and (report["drift"] or report["errors"]):
            Path(args.issue_body).write_text(build_issue_body(report), encoding="utf-8")
            print(f"issue body written: {args.issue_body}")
    return exit_code_for(report)


if __name__ == "__main__":
    sys.exit(main())
