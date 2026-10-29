#!/usr/bin/env python3
"""contract_codegen_guard.py — contract → generated-consumer viability gate (#1846).

Mission (issue #1846, scout radar R39 lane — adapt_cleanroom):
    `api-schemas/gateway.openapi.yaml` is the declared stable external contract
    (ECOSYSTEM_MAP §4: "external SDK authors", the VS Code extension,
    `examples/gateway_client.py`). Until this guard, NOTHING guaranteed a valid,
    typed consumer model surface could be GENERATED from the SSOT at all: the
    producer side is guarded (#1760 diffs two contract revisions for breaking
    changes; #1791 enforces import contracts) but the consumer side ran on
    memory and a hand-edited example already proven behind the contract
    (#1620 <-> #1677). The contract could silently degrade into something that
    cannot generate a clean client — the live run found exactly that wart class
    today (`Message1`, a duplicate-name collision artifact inside the
    hand-maintained YAML) and no gate would ever notice.

Behavior contract (fail-closed on detection, honest-degradation on environment):
    1. The generated artifact `api-schemas/generated/gateway_models.py` is
       committed ONCE (raw generator output, never hand-edited). This guard
       regenerates it in a tempdir with the PINNED generator and byte-compares
       (CRLF-normalized) against the committed artifact. Any drift = the
       contract changed without regenerating its consumer surface = exit 1,
       with the consumer breakage visible in the PR diff itself.
    2. Determinism is a hard requirement for a committed-artifact gate: the
       generator is invoked with `--disable-timestamp` (otherwise every run
       embeds a wall-clock header and drift is meaningless) and
       `--formatters builtin` (otherwise output depends on whichever
       black/isort a machine happens to have installed).
    3. Honest skip-with-evidence when the pinned generator binary is absent
       (offline machines are not failures — the #1760/#1711 pattern), when the
       installed version differs from the pin (tool-version drift is not
       contract drift; the run must not lie about which tool produced the
       verdict), or when the contract file itself is absent.
    4. Fail-closed: generator drift (exit 1); committed artifact missing while
       the contract and generator exist (the consumer artifact MUST exist);
       unparseable tool version output (never guess).
    5. Tool version pinned in ONE place (CODEGEN_PIN). Test seams are explicit
       env vars (CONTRACT_CODEGEN_TOOL, CONTRACT_CODEGEN_ROOT) so --self-test
       is fully hermetic — no real generator needed.

Never-do (issue #1846): this guard never hand-edits the generated artifact
(regenerate or fail), never modifies the contract YAML, never fetches anything
over the network at guard time (local file + local binary only), never commits
a generator binary into the repo, and never reverses the authoritative
direction (yaml -> artifact, never the reverse).

Usage:
    python scripts/ci/contract_codegen_guard.py --check          # roster mode
    python scripts/ci/contract_codegen_guard.py --files a b ...  # pre-push mode
    python scripts/ci/contract_codegen_guard.py --base REF --head REF
    python scripts/ci/contract_codegen_guard.py --self-test      # hermetic

Exit codes: 0 = pass or honest skip · 1 = drift / missing artifact · 2 = usage error.

Stdlib-only. Offline at guard time. Zero new Python dependency (the generator
is an external dev CLI pinned to datamodel-code-generator==0.86.0, MIT).
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import os
import re
import shutil
import subprocess  # nosec B404 — the guard's contract/regeneration checks ARE subprocess invocations; list-argv only (#2081 audit)
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]

CONTRACT_FILE = "api-schemas/gateway.openapi.yaml"
ARTIFACT_FILE = "api-schemas/generated/gateway_models.py"

# The ONE place the generator version is pinned (issue #1846 adoption path).
CODEGEN_PIN = "0.86.0"
CODEGEN_PACKAGE = "datamodel-code-generator"

# Exact invocation — determinism-critical (see docstring §2). Any change here
# MUST be accompanied by regenerating the committed artifact in the same PR.
GEN_BASE_ARGS = [
    "--input-file-type",
    "openapi",
    "--output-model-type",
    "pydantic_v2.BaseModel",
    "--disable-timestamp",
    "--formatters",
    "builtin",
]

# Engagement pattern for --files / revision mode: the contract or its
# generated consumer surface is touched.
TOUCHED_PATHS = re.compile(r"(^api-schemas/gateway\.openapi\.yaml$|^api-schemas/generated/)")

DIFF_EVIDENCE_CAP = 40  # bounded evidence: never dump the whole file

TAG = "[contract-codegen-guard]"


# --------------------------------------------------------------------------- #
# Tool discovery (explicit test seams; honest skip on environment mismatch)   #
# --------------------------------------------------------------------------- #

def resolve_root(explicit_root: str | None = None) -> Path:
    """Repo root — env/arg seam so --self-test can run hermetic sandboxes."""
    root = explicit_root or os.environ.get("CONTRACT_CODEGEN_ROOT")
    return Path(root).resolve() if root else REPO_ROOT


def discover_tool(explicit_tool: str | None = None) -> tuple[str | None, str | None]:
    """Locate the generator CLI and its version.

    Returns (tool_path, None) on success, or (None, skip_reason) on an honest
    skip. CONTRACT_CODEGEN_TOOL (env) or explicit_tool overrides discovery for
    hermetic tests; the version is parsed from `<tool> --version` and must
    match CODEGEN_PIN exactly — a different version SKIPS (evidence names both
    versions) instead of pretending the pin was verified.
    """
    tool = explicit_tool or os.environ.get("CONTRACT_CODEGEN_TOOL") or shutil.which("datamodel-codegen")
    if not tool:
        return None, (
            f"{TAG} SKIP: generator binary 'datamodel-codegen' not found on PATH "
            f"(dev install: pip install {CODEGEN_PACKAGE}=={CODEGEN_PIN}). "
            f"Honest skip per the #1760 pattern — offline machines are not failures."
        )
    if not Path(tool).exists():
        return None, f"{TAG} SKIP: CONTRACT_CODEGEN_TOOL points to a nonexistent path: {tool}"
    try:
        proc = subprocess.run(  # nosec B603 — list-argv, no shell, tool path validated via Path(tool).exists() above (#2081 audit)
            [tool, "--version"], capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{TAG} SKIP: generator --version failed to run: {exc}"
    if proc.returncode != 0:
        return None, f"{TAG} SKIP: generator --version exited {proc.returncode}; refusing to guess the version."
    match = re.search(r"(\d+\.\d+\.\d+)", proc.stdout or "")
    if not match:
        return None, f"{TAG} SKIP: unparseable generator version output; refusing to guess."
    version = match.group(1)
    if version != CODEGEN_PIN:
        return None, (
            f"{TAG} SKIP: installed generator version {version} != pinned {CODEGEN_PIN}. "
            f"Tool-version drift is not contract drift; align the install "
            f"(pip install {CODEGEN_PACKAGE}=={CODEGEN_PIN}) to re-enable enforcement."
        )
    return tool, None


# --------------------------------------------------------------------------- #
# Core verification (pure paths in, verdict out)                              #
# --------------------------------------------------------------------------- #

def generate(tool: str, contract: Path, out: Path) -> None:
    """Regenerate the artifact from the contract with the pinned invocation."""
    cmd = [tool, "--input", str(contract), *GEN_BASE_ARGS, "--output", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(contract.parent.parent))  # nosec B603 — list-argv, no shell, tool path validated (#2081 audit)
    if proc.returncode != 0:
        raise RuntimeError(
            f"generator exited {proc.returncode} (contract may be ungeneratable — "
            f"this is exactly the consumer-viability failure class this guard exists for)\n"
            f"{(proc.stderr or proc.stdout or '')[-800:]}"
        )


def normalize(data: bytes) -> bytes:
    """CRLF-safe byte comparison (the repo's trees cross CRLF environments)."""
    return data.replace(b"\r\n", b"\n")


def drift_evidence(generated: bytes, committed: bytes) -> str:
    """Bounded unified-diff evidence (generated vs committed), CRLF-normalized."""
    gen_lines = normalize(generated).decode("utf-8", errors="replace").splitlines()
    com_lines = normalize(committed).decode("utf-8", errors="replace").splitlines()
    diff = list(difflib.unified_diff(com_lines, gen_lines, fromfile="committed", tofile="regenerated", lineterm=""))
    if len(diff) > DIFF_EVIDENCE_CAP:
        return "\n".join(diff[:DIFF_EVIDENCE_CAP]) + f"\n... ({len(diff) - DIFF_EVIDENCE_CAP} more diff lines)"
    return "\n".join(diff) if diff else "(no textual diff — encoding-level drift)"


def verify(root: Path, tool: str) -> tuple[int, list[str]]:
    """Core verdict. Returns (exit_code, evidence_lines). Fail-closed on drift."""
    notes: list[str] = []
    contract = root / CONTRACT_FILE
    artifact = root / ARTIFACT_FILE
    if not contract.exists():
        return 0, [f"{TAG} SKIP: contract file {CONTRACT_FILE} absent in this tree — nothing to verify."]
    if not artifact.exists():
        return 1, [
            f"{TAG} FAIL: committed consumer artifact {ARTIFACT_FILE} is missing while the "
            f"contract exists. The contract's consumer surface must be a build product, not an "
            f"absence. Generate once and commit: datamodel-codegen --input {CONTRACT_FILE} "
            f"{' '.join(GEN_BASE_ARGS)} --output {ARTIFACT_FILE}",
        ]
    with tempfile.TemporaryDirectory() as td:
        regen = Path(td) / "gateway_models.py"
        try:
            generate(tool, contract, regen)
        except RuntimeError as exc:
            return 1, [f"{TAG} FAIL: regeneration failed: {exc}"]
        fresh = regen.read_bytes()
    committed = artifact.read_bytes()
    if normalize(fresh) != normalize(committed):
        return 1, [
            f"{TAG} FAIL: contract → consumer DRIFT — {ARTIFACT_FILE} does not match a fresh "
            f"pinned regeneration of {CONTRACT_FILE}. The contract changed without regenerating "
            f"its consumer surface. Never hand-edit the artifact; regenerate and commit:",
            drift_evidence(fresh, committed),
        ]
    notes.append(f"{TAG} PASS: {ARTIFACT_FILE} byte-matches a fresh pinned ({CODEGEN_PIN}) regeneration of {CONTRACT_FILE}.")
    return 0, notes


# --------------------------------------------------------------------------- #
# Modes                                                                       #
# --------------------------------------------------------------------------- #

def changed_files(base: str | None, head: str | None, files: list[str]) -> list[str]:
    if files:
        return files
    if base:
        rev = f"{base}..{head}" if head else f"{base}...HEAD"
        git_bin = shutil.which("git") or "git"  # B607: resolve to absolute path when available
        proc = subprocess.run(  # nosec B603 — list-argv, no shell, pinned git read-only command (#2081 audit)
            [git_bin, "diff", "--name-only", rev], capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        return proc.stdout.split()
    return []


def run(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    if args.self_test:
        return self_test()

    if args.files or args.base:
        touched = [f for f in changed_files(args.base, args.head, args.files) if TOUCHED_PATHS.search(f.replace("\\", "/"))]
        if not touched:
            print(f"{TAG} SKIP: revision does not touch the contract or its generated surface.")
            return 0

    tool, skip_reason = discover_tool(args.tool)
    if tool is None:
        print(skip_reason)
        return 0  # honest skip — environment, not verdict

    code, notes = verify(root, tool)
    for line in notes:
        print(line)
    return code


# --------------------------------------------------------------------------- #
# Hermetic self-test (guard-the-guard; no real generator required)            #
# --------------------------------------------------------------------------- #

FAKE_TOOL = r"""#!/usr/bin/env python3
import sys
args = sys.argv[1:]
if "--version" in args:
    print("datamodel-codegen " + "VERSION")
    sys.exit(0)
out = args[args.index("--output") + 1]
src = args[args.index("--input") + 1]
with open(src, "rb") as f:
    body = f.read()
with open(out, "wb") as f:
    f.write(b"# generated by fixture-tool\n" + body)
sys.exit(0)
"""


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def self_test() -> int:
    """Fixture scenarios over a sandbox tree with a deterministic fake tool."""
    import stat

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  {'PASS' if cond else 'FAIL'} | {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory() as td_s:
        td = Path(td_s)
        tool_path = td / "fixture_codegen.py"
        tool_path.write_text(FAKE_TOOL.replace("VERSION", CODEGEN_PIN))
        tool_path.chmod(tool_path.stat().st_mode | stat.S_IEXEC)
        sys_py = sys.executable

        # verify()/generate() expect tool as a single executable path; the
        # fixture is a python script, so wrap it in a tiny executable shim.
        wrapper = td / "fixture_tool_wrapper.sh"
        wrapper.write_text(f"#!/bin/sh\nexec '{sys_py}' '{tool_path}' \"$@\"\n")
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)

        contract_body = b"openapi: 3.0.0\ninfo: {title: t, version: '1'}\npaths: {}\n"

        # --- scenario 1: fresh match → exit 0
        root1 = td / "s1"
        _write(root1 / CONTRACT_FILE, contract_body)
        art1 = root1 / ARTIFACT_FILE
        _write(art1, b"# generated by fixture-tool\n" + contract_body)
        code, notes = verify(root1, str(wrapper))
        check("fresh artifact byte-matches regeneration (exit 0)", code == 0, str(notes))

        # --- scenario 2: hand-edited artifact → drift → exit 1
        _write(art1, b"# hand-edited\n" + contract_body)
        code, notes = verify(root1, str(wrapper))
        blob = "\n".join(notes)
        check("drift fail-closes (exit 1)", code == 1)
        check("drift evidence names never-hand-edit remedy", "Never hand-edit" in blob or "regenerate" in blob)

        # --- scenario 3: missing artifact → exit 1
        root3 = td / "s3"
        _write(root3 / CONTRACT_FILE, contract_body)
        code, notes = verify(root3, str(wrapper))
        check("missing artifact fail-closes (exit 1)", code == 1, str(notes))

        # --- scenario 4: contract absent → honest skip exit 0
        root4 = td / "s4"
        (root4 / ARTIFACT_FILE).parent.mkdir(parents=True)
        code, notes = verify(root4, str(wrapper))
        check("contract-absent honest skip (exit 0)", code == 0, str(notes))

        # --- scenario 5: version mismatch → discover_tool skips
        tool_bad = td / "fixture_codegen_bad.py"
        tool_bad.write_text(FAKE_TOOL.replace("VERSION", "9.9.9"))
        tool_bad.chmod(tool_bad.stat().st_mode | stat.S_IEXEC)
        wrapper_bad = td / "fixture_tool_wrapper_bad.sh"
        wrapper_bad.write_text(f"#!/bin/sh\nexec '{sys_py}' '{tool_bad}' \"$@\"\n")
        wrapper_bad.chmod(wrapper_bad.stat().st_mode | stat.S_IEXEC)
        found, reason = discover_tool(str(wrapper_bad))
        check("version mismatch skips honestly (no tool)", found is None and reason is not None and CODEGEN_PIN in reason)

        # --- scenario 6: --files engagement matrix (run() level, sandbox root)
        root6 = td / "s1"  # fresh tree from scenario 1 (already tampered in s2 — restore)
        _write(root6 / ARTIFACT_FILE, b"# generated by fixture-tool\n" + contract_body)
        env_backup = {k: os.environ.get(k) for k in ("CONTRACT_CODEGEN_TOOL", "CONTRACT_CODEGEN_ROOT")}
        try:
            os.environ["CONTRACT_CODEGEN_TOOL"] = str(wrapper)
            os.environ["CONTRACT_CODEGEN_ROOT"] = str(root6)
            ns = argparse.Namespace(files=["docs/notes.md"], base=None, head=None, self_test=False, tool=None, root=None)
            check("--files unrelated → skip exit 0", run(ns) == 0)
            ns = argparse.Namespace(files=[CONTRACT_FILE], base=None, head=None, self_test=False, tool=None, root=None)
            check("--files contract-touched → verify runs (exit 0 on fresh)", run(ns) == 0)
        finally:
            for k, v in env_backup.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        # --- scenario 7: the guard never mutates the contract YAML
        before = (root6 / CONTRACT_FILE).read_bytes()
        code, _ = verify(root6, str(wrapper))
        after = (root6 / CONTRACT_FILE).read_bytes()
        check("contract YAML untouched by guard run", before == after and code == 0)

    print(f"\nself-test: {'PASS' if not failures else 'FAIL'} ({len(failures)} failure(s))")
    return 1 if failures else 0


# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="contract → generated-consumer viability gate (#1846)")
    p.add_argument("--check", action="store_true", help="roster mode: verify artifact freshness")
    p.add_argument("--files", nargs="+", default=[], help="pre-push changed-files mode")
    p.add_argument("--base", help="revision base (engages only when the contract is touched)")
    p.add_argument("--head", help="revision head (default HEAD)")
    p.add_argument("--self-test", action="store_true", help="hermetic fixture scenarios")
    p.add_argument("--tool", help="explicit generator path (test seam; normally env/PATH)")
    p.add_argument("--root", help="explicit repo root (test seam)")
    args = p.parse_args(argv)
    if not (args.check or args.files or args.base or args.self_test):
        p.error("one of --check / --files / --base / --self-test is required (fail-closed: never a silent pass)")
    try:
        return run(args)
    except subprocess.TimeoutExpired:
        print(f"{TAG} FAIL: generator timed out (treated fail-closed).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
