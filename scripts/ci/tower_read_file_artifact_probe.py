#!/usr/bin/env python3
"""tower_read_file_artifact_probe.py — zero-credential evidence guard for tower
github.read_file payloads (U6 Zero-Recurrence mechanical guard, 2026-10-30).

Mission (live discovery, GLM Agent 32 / Job 486850 cycle, evidence for open#3441
triage plane):
    The tower's `github.read_file` tool mangles every bracket sequence of the
    shape `[<digits/semicolons>...]m` — the ANSI-SGR color-code class — even
    when the ESC byte is absent, i.e. the stripper regex
    `\\[[0-9;]*m` is applied to plain-text payloads. Proven by byte-compare:
    a blob whose LOCAL bytes contain `branches: [main]` and
    "leading `[m`" reads back from the tower as `branches: ain]` and
    "leading " (two `[m` spans eaten in one blob, blob sha unchanged — the
    API echoes the true blob sha while the content payload is altered).

    Downstream damage class this guard exists to stop: triage receipts that
    cite tower read_file bytes as "byte-exact" file content. The landed
    docs/reports/CORE_TRIAGE receipt's F1 (`branches: ain]` corruption in
    supremeai-core ci.yml) is reclassified by this probe's evidence as an
    artifact of exactly this class — with follow-on consequences: agents
    would "fix" a corruption that the file does not contain (and .github/
    is protected-path anyway), while the REAL red (run 41072422845's
    "Core Pytest & Lint" job) stays unchased.

    Fidelity is NONDETERMINISTIC (live 2026-10-30): the same blob read
    stripped at ~14:52Z and faithful at ~15:05Z+ (5/5 suspect spans intact)
    with the mojibake drift present in BOTH reads — so a single clean read
    proves nothing about the next one. Every read cited as evidence needs
    its own PASS verdict; blob-sha echo identity alone is NOT sufficient
    (the sha comes from the API envelope, the mangling happens in the
    content payload afterwards).

Report-only contract:
    - NO writes of any kind: the probe opens tracked files read-only and
      calls the tower read-only github.read_file. Zero stdout noise beyond
      the verdict block + machine-readable JSON line.
    - NO decisions: the probe classifies evidence; what to file, fix, or
      close remains with the caller/agent/admin lanes.
    - NO duplication: no existing repo surface validates tower read bytes
      (scanned scripts/ci on 2026-10-30); this is the first evidence-quality
      guard for the read_file lane. mcp_conformance_selftest checks the
      WIRE (protocol/headers), not PAYLOAD fidelity — complementary.

Usage contract for every agent citing file bytes from the tower:
    1. Run this probe live BEFORE writing "byte-exact" into any receipt.
    2. Cite the blob sha echo (unmangled) TOGETHER with the probe verdict.
    3. While the live verdict is ARTIFACT_*, bracket-bearing content claims
       from tower reads are inadmissible as evidence; use the admin plane
       or cite blob shas only.

Exit contract:
    --self-test  hermetic offline unit pass (classifier, real-capture pair) -> 0/1
    (default)    live probe: local tracked fixture vs tower read_file       ->
                 0 = PASS (payload faithful), 1 = ARTIFACT_* (evidence guard
                 tripped), 2 = usage error, 3 = wiring error (tower/client).
    --path P     probe an arbitrary tracked file instead of the fixture.
    --ref R      pin the tower read to a ref (also prints the blob-sha echo
                 so receipts can cite ref+sha pairs; ref-pinning is itself a
                 pitfall: the landed CORE_TRIAGE receipt misattributed a
                 HEAD read to commit feda45e4).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = "scripts/ci/fixtures/tower_read_probe_fixture.txt"
DEFAULT_REPO = "Supremeai-bd/supremeai-open"
TOWER_CLIENT = REPO_ROOT / "scripts" / "agents" / "mcp_tower_client.py"

# The suspect class: ANSI-SGR-ish sequences WITHOUT a required ESC byte.
# Evidence-fitted: strips "[m" inside "[main]" (live capture) while leaving
# "[pousr]", "[A-Za-z0-9]", "[ -f x ]", "[Mm]" untouched (live capture).
SUSPECT = re.compile(r"\[[0-9;]*m")


def simulate_strip(text: str) -> str:
    """What the suspect stripper WOULD leave behind."""
    return SUSPECT.sub("", text)


def unmojibake(text: str) -> str | None:
    """Undo the tower's UTF-8->latin-1 double-decode drift (e.g. em-dash).

    Returns None when the payload cannot be round-tripped (then the compare
    is inconclusive on non-ASCII spans — honest limitation, never guessed).
    """
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None


def classify(local_text: str, tower_text: str) -> tuple[str, str]:
    """Three-way evidence verdict (never silent, never guessed)."""
    norm = unmojibake(tower_text)
    if norm is None:
        return "ENCODING_UNSAFE", "tower payload not latin-1 roundtrippable; compare inconclusive"
    if norm == local_text:
        return "PASS", "tower payload is faithful to local ground truth"
    sim = simulate_strip(local_text)
    if norm == sim:
        spans = sorted({m.group(0) for m in SUSPECT.finditer(local_text)})
        return (
            "ARTIFACT_MATCH",
            f"suspect stripper explains the whole delta; stripped classes: {spans}",
        )
    return "ARTIFACT_OTHER", "payload diverges in ways the suspect stripper does NOT explain"


def git_blob_sha(data: bytes) -> str:
    """Git blob object id, pure python (no subprocess, zero-write)."""
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def _load_tower_client():
    spec = importlib.util.spec_from_file_location("mcp_tower_client", TOWER_CLIENT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("mcp_tower_client", mod)
    spec.loader.exec_module(mod)
    return mod


def run_self_test() -> int:
    """Hermetic offline pass: classifier against synthetic pairs built from
    the two real captures (2026-10-30) plus adversarial negatives."""
    cases = [
        # (name, local, tower, expected verdict)
        ("live-capture-fix-line", "go: branches: [main]\n", "go: branches: ain]\n", "ARTIFACT_MATCH"),
        ("live-capture-doc-line", "byte-exact; `[main]` minus its leading `[m`).", "byte-exact; `ain]` minus its leading ``).", "ARTIFACT_MATCH"),
        ("preserved-lower-bracket", "tok gh[pousr]_x", "tok gh[pousr]_x", "PASS"),
        ("preserved-charset", "[A-Za-z0-9]{36,}", "[A-Za-z0-9]{36,}", "PASS"),
        ("preserved-spaced-bracket", "if [ -f requirements.txt ]", "if [ -f requirements.txt ]", "PASS"),
        ("sgr-color-codes", "c=[0;32m and [1;33m and [42m", "c= and  and ", "ARTIFACT_MATCH"),
        ("mojibake-roundtrip", "dash — here", "dash â\x80\x94 here", "PASS"),
        ("unexplained-delta", "alpha [main] beta", "alpha [main] GAMMA", "ARTIFACT_OTHER"),
    ]
    failures = []
    for name, local, tower, want in cases:
        got, detail = classify(local, tower)
        status = "PASS" if got == want else "FAIL"
        if got != want:
            failures.append(name)
        print(f"  [{status}] {name}: {got} — {detail}")
    # classifier sanity: simulate_strip never widens text
    assert len(simulate_strip("a [main] b")) < len("a [main] b")
    # blob sha sanity against a known-good git value shape
    sha = git_blob_sha(b"hello\n")
    assert re.fullmatch(r"[0-9a-f]{40}", sha), sha
    # fixture sanity (offline): fixture must exist in the worktree and carry
    # at least one suspect span, so live mode has something to catch.
    fx = REPO_ROOT / DEFAULT_FIXTURE
    assert fx.exists(), f"fixture missing: {fx}"
    fx_text = fx.read_text(encoding="utf-8")
    assert SUSPECT.search(fx_text), "fixture carries no suspect spans"
    if failures:
        print(f"SELF-TEST FAIL: {len(failures)} case(s): {failures}")
        return 1
    print(f"SELF-TEST PASS: {len(cases)}/8 classifier cases + fixture/git sanity")
    return 0


def run_live(path: str, repo: str, ref: str | None) -> int:
    local_path = REPO_ROOT / path
    if not local_path.exists():
        print(f"WIRING ERROR: local ground-truth file missing: {local_path}")
        return 3
    local_bytes = local_path.read_bytes()
    local_text = local_bytes.decode("utf-8")
    local_sha = git_blob_sha(local_bytes)

    try:
        client_mod = _load_tower_client()
        client = client_mod.McpTowerClient()
        client.connect()
        args = {"repo": repo, "path": path}
        if ref:
            args["ref"] = ref
        resp = client.call_tool("github.read_file", args)
        client.close()
    except Exception as exc:  # wiring, not evidence
        print(f"WIRING ERROR: tower read failed: {exc}")
        return 3

    payload = resp["content"][0]["text"] if isinstance(resp, dict) and "content" in resp else str(resp)
    try:
        inner = json.loads(payload)
    except json.JSONDecodeError:
        print("WIRING ERROR: tower payload is not the read_file JSON envelope")
        return 3
    tower_sha = inner.get("sha", "")
    tower_text = inner.get("content", "")
    if not tower_sha or ("content" not in inner):
        # Error envelope (404/permission/...), not a file payload — a wiring
        # outcome, never evidence: do NOT let it masquerade as ARTIFACT_*.
        print("WIRING ERROR: tower returned no blob sha/content (file missing on the probed ref, or read denied)")
        print(f"  envelope head: {payload[:160]}")
        return 3
    verdict, detail = classify(local_text, tower_text)

    sha_note = "MATCH" if tower_sha == local_sha else "DIFFER"
    print("=== tower_read_file_artifact_probe (live) ===")
    print(f"  path        : {path}")
    print(f"  ref         : {ref or 'HEAD/main'}")
    print(f"  blob sha    : local {local_sha[:12]} vs tower {tower_sha[:12]} -> {sha_note}")
    if sha_note == "DIFFER":
        print("  (note: working tree may be stale vs the probed ref; sha identity is not required for the verdict below)")
    print(f"  verdict     : {verdict}")
    print(f"  detail      : {detail}")
    print(json.dumps({
        "probe": "tower_read_file_artifact_probe",
        "path": path,
        "ref": ref,
        "localBlobSha": local_sha,
        "towerBlobSha": tower_sha,
        "verdict": verdict,
    }))
    if verdict == "PASS":
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true", help="hermetic offline unit pass")
    ap.add_argument("--path", default=DEFAULT_FIXTURE, help="tracked file to probe (default: canonical fixture)")
    ap.add_argument("--repo", default=DEFAULT_REPO, help="target repo for the tower read")
    ap.add_argument("--ref", default=None, help="pin the tower read to a branch/sha (default: repo default branch)")
    args = ap.parse_args(argv)
    if args.self_test:
        return run_self_test()
    return run_live(args.path, args.repo, args.ref)


if __name__ == "__main__":
    raise SystemExit(main())
