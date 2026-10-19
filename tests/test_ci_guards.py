#!/usr/bin/env python3
"""tests/test_ci_guards.py — fail-closed behavioral suite for the #392 CI guards.

Verifies the two constitutional guards mandated by issue #392
("fix(ci): enforce mandatory Claim Gate & Knowledge Sharing Guard in
pipeline.yml"), delivered via WO #395 as byte-exact appendices for the
protected ``.github/`` path:

  - ``claim-guard``              — no claim, no work (AGENTS.md Step 4)
  - ``knowledge-sharing-guard``  — reflection evidence on every PR body

Design (zero-dependency doctrine, AGENT_RULES.md §13 — dual mode):

  - pytest:  pytest tests/test_ci_guards.py
  - stdlib:  python3 tests/test_ci_guards.py   (plain runner, no pytest import)

SSOT extraction: the guard run-blocks are pulled from the LIVE
``.github/workflows/pipeline.yml`` (never duplicated here), materialized
with a stubbed ``gh`` + fixture JSON payloads and executed for real under
bash. The suite therefore tests whatever the maintainers actually applied.

Sequencing honesty: if the guard jobs are not yet present in pipeline.yml
(WO #395 appendices pending application), every guard test SKIPS with a
pointer — absence of a pending handoff is a pending state, not a
regression. The moment the appendices land, the suite activates and
enforces the fail-closed contract permanently.

Every test is offline and deterministic; the only network-adjacent tool
(``gh``) is a local stub reading fixture files.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE = REPO_ROOT / ".github" / "workflows" / "pipeline.yml"
PR_TEMPLATE = REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"

# Exact strings mandated verbatim by issue #392 (acceptance criteria).
CLAIM_ERROR_PREFIX = "::error::PR opened without a prior claim on Issue #"
# 4301d9a loop variant: the guard now reports EVERY referenced issue (loop
# over title/body/branch refs) when none carries an active claim plane.
CLAIM_ERROR_ISSUES_PREFIX = (
    "::error::PR opened without a prior claim on any referenced issue (#"
)
CLAIM_ERROR_TAIL = ". Per AGENTS.md Step 4 (No claim, no work), claim the issue before creating a branch or PR."
REFL_ERROR_EXACT = (
    "::error::PR body missing required '## Reflection Evidence (why + alternatives_rejected)'. "
    "AGENTS.md mandates knowledge capture on every contribution."
)

# Byte-exact contract with the deployed claim-guard label plane. The plane
# accepts the bridge lifecycle labels (bridge:queued/in-gates/landed) in
# addition to the status labels — oracle re-synced after 4301d9a extended the
# guard without updating this constant (2 tests red on main since then).
CLAIM_JQ_LABEL = (
    'any(.labels[]?; .name == "status:claimed" or .name == "status:in-progress"'
    ' or .name == "bridge:queued" or .name == "bridge:in-gates"'
    ' or .name == "bridge:landed")'
)
CLAIM_JQ_MARKER = 'any(.comments[]?; (.body // "") | contains("<!-- atomic-claim -->"))'

# High fixture numbers — deliberately outside the real issue range.
FX_CLAIMED = 5001  # status:claimed label
FX_ATOMIC = 5002  # <!-- atomic-claim --> comment
FX_UNCLAIMED = 5003  # neither plane (non-claim label only)
FX_MISSING = 5004  # gh lookup fails (no fixture) -> fail-closed
FX_BRIDGE_QUEUED = 5005  # bridge:queued label — active claim plane per 4301d9a

FIXTURE_ISSUES = {
    str(FX_CLAIMED): {"labels": [{"name": "status:claimed"}], "comments": []},
    str(FX_ATOMIC): {
        "labels": [],
        "comments": [{"body": "<!-- atomic-claim -->\n🎯 **Claimed**"}],
    },
    str(FX_UNCLAIMED): {
        "labels": [{"name": "question"}],
        "comments": [{"body": "regular comment"}],
    },
    str(FX_BRIDGE_QUEUED): {"labels": [{"name": "bridge:queued"}], "comments": []},
}

GOOD_BODY = (
    "## Reflection Evidence (why + alternatives_rejected)\n"
    "- **why:** Guards fail closed at PR time so ghost PRs never reach triage.\n"
    "- **alternatives_rejected:**\n"
    "  - server-side push hook — needs admin tokens the bridge must never hold\n"
)


class _Skip(Exception):
    """Stdlib-mode skip signal (pytest path uses pytest.skip instead)."""


def _skip(reason: str) -> None:
    # Under pytest -> real pytest.skip; stdlib mode -> plain _Skip signal.
    if "PYTEST_CURRENT_TEST" in os.environ:
        import pytest

        pytest.skip(reason)
    raise _Skip(reason)


# --------------------------------------------------------------------------- #
# SSOT extraction from the live pipeline.yml (indent-scan; no PyYAML needed)  #
# --------------------------------------------------------------------------- #


def _load_pipeline_text() -> str:
    if not PIPELINE.is_file():
        raise AssertionError(
            f"pipeline.yml missing at {PIPELINE} — constitutional workflow file required"
        )
    return PIPELINE.read_text(encoding="utf-8")


def _extract_job_block(text: str, job_name: str) -> str | None:
    """Return the raw text of a 2-space-indented job key block, or None."""
    lines = text.splitlines()
    key_re = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
    start = None
    for i, ln in enumerate(lines):
        m = key_re.match(ln)
        if m and m.group(1) == job_name:
            start = i
            break
    if start is None:
        return None
    out = [lines[start]]
    for ln in lines[start + 1 :]:
        if key_re.match(ln) or (ln.strip() and not ln[0].isspace()):
            break
        out.append(ln)
    return "\n".join(out)


def _extract_run_script(block: str) -> str | None:
    """Return the decoded `run: |` literal of a job block, or None."""
    lines = block.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"^(\s*)run:\s*\|\s*$", ln)
        if not m:
            continue
        indent = len(m.group(1)) + 2
        out: list[str] = []
        pending: list[str] = []
        for l2 in lines[i + 1 :]:
            if l2.strip() == "":
                pending.append("")
                continue
            if len(l2) - len(l2.lstrip()) < indent:
                break
            out.extend(pending)
            pending = []
            out.append(l2[indent:])
        while out and out[-1] == "":
            out.pop()
        return "\n".join(out)
    return None


_PIPELINE_TEXT = ""
CLAIM_BLOCK: str | None = None
KS_BLOCK: str | None = None

try:
    _PIPELINE_TEXT = _load_pipeline_text()
    CLAIM_BLOCK = _extract_job_block(_PIPELINE_TEXT, "claim-guard")
    KS_BLOCK = _extract_job_block(_PIPELINE_TEXT, "knowledge-sharing-guard")
except AssertionError:
    pass  # surfaced as a hard failure by test_pipeline_exists

GUARDS_PRESENT = bool(CLAIM_BLOCK) and bool(KS_BLOCK)
_SKIP_REASON = (
    "claim-guard / knowledge-sharing-guard not yet in .github/workflows/pipeline.yml — "
    "WO #395 appendices pending application (issue #392 handoff)"
)


def _require_guards() -> None:
    if PIPELINE.exists() and not GUARDS_PRESENT:
        _skip(_SKIP_REASON)


# --------------------------------------------------------------------------- #
# Harness: stubbed gh + fixture JSONs + materialization + real bash execution #
# --------------------------------------------------------------------------- #


class _GuardHarness:
    """Event-context execution rig: stub `gh`, fixture issues, real bash."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ci_guard_test_"))
        self.fixtures = self.root / "fixtures"
        self.fixtures.mkdir()
        shim_dir = self.root / "bin"
        shim_dir.mkdir()
        shim = shim_dir / "gh"
        shim.write_text(
            "#!/bin/bash\n"
            "# gh shim: `gh issue view <num> --json labels,comments` -> fixture JSON; else exit 1\n"
            'args=("$@")\n'
            'if [ "${args[0]}" = "issue" ] && [ "${args[1]}" = "view" ]; then\n'
            '  num="${args[2]}"\n'
            '  f="FIXTURE_DIR/issue_${num}.json"\n'
            '  if [ -f "$f" ]; then cat "$f"; exit 0; fi\n'
            "  exit 1\n"
            "fi\n"
            "exit 1\n".replace("FIXTURE_DIR", str(self.fixtures)),
            encoding="utf-8",
        )
        shim.chmod(0o755)
        for num, obj in FIXTURE_ISSUES.items():
            (self.fixtures / f"issue_{num}.json").write_text(
                json.dumps(obj), encoding="utf-8"
            )

    def materialize(self, script: str) -> str:
        """Substitute every `${{ }}` expression; fail closed if any remain."""
        script = script.replace(
            "${{ github.repository }}", "Supremeai-bd/supremeai-open"
        )
        script = script.replace("${{ secrets.GITHUB_TOKEN }}", "testtoken")
        if "${{" in script:
            i = script.index("${{")
            raise AssertionError(
                f"unsubstituted expression remains: {script[i : i + 60]!r}"
            )
        return script

    def run(self, script_text: str, **env: str) -> subprocess.CompletedProcess:
        path = self.root / "scenario.sh"
        path.write_text(self.materialize(script_text), encoding="utf-8")
        e = {
            "PATH": f"{self.root / 'bin'}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.root),
            "LANG": "C.UTF-8",
            "GH_TOKEN": "testtoken",
        }
        e.update(env)
        return subprocess.run(
            ["bash", str(path)], capture_output=True, text=True, env=e, timeout=120
        )

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def _claim_env(num: int, labels: str = "", head_ref: str | None = None) -> dict:
    return {
        "PR_TITLE": f"feat: x (Closes #{num})",
        "PR_BODY": f"Closes #{num}",
        "PR_LABELS": labels,
        "HEAD_REF": head_ref or f"contributor/issue-{num}",
    }


# --------------------------------------------------------------------------- #
# Static contract tests (structure of the applied jobs)                       #
# --------------------------------------------------------------------------- #


def test_pipeline_exists():
    assert PIPELINE.is_file(), f"pipeline.yml missing at {PIPELINE}"


def test_guards_present_in_pipeline():
    _require_guards()
    assert CLAIM_BLOCK and CLAIM_BLOCK.lstrip().startswith("claim-guard:")
    assert KS_BLOCK and KS_BLOCK.lstrip().startswith("knowledge-sharing-guard:")


def test_claim_guard_pr_only_zero_checkout_and_timeout():
    _require_guards()
    b = CLAIM_BLOCK or ""
    assert "github.event_name == 'pull_request'" in b, "guard must be PR-only"
    assert "timeout-minutes: 3" in b, "house style: fast zero-checkout guard"
    assert "actions/checkout" not in b, "zero-checkout: event-context env only"


def test_claim_guard_permissions_and_claim_planes():
    _require_guards()
    b = CLAIM_BLOCK or ""
    assert re.search(r"permissions:\s*\n\s+issues:\s*read", b), "needs issues:read only"
    assert CLAIM_JQ_LABEL in b, "label plane (CLAIMED_LABELS registry) missing"
    assert CLAIM_JQ_MARKER in b, "comment plane (<!-- atomic-claim -->) missing"


def test_claim_guard_exact_error_string():
    _require_guards()
    b = CLAIM_BLOCK or ""
    assert CLAIM_ERROR_PREFIX in b
    assert CLAIM_ERROR_TAIL in b, "issue #392 mandates this exact tail verbatim"


def test_claim_guard_escape_hatch_order():
    _require_guards()
    b = CLAIM_BLOCK or ""
    assert "guard-exempt" in b, "admin escape hatch required by issue #392"
    assert b.index("guard-exempt") < b.index("dependabot"), (
        "exempt check must come first"
    )
    assert "status:claimed" in b[b.index("guard-exempt") :], (
        "claim planes follow the hatch"
    )


def test_ks_guard_pr_only_zero_checkout_and_timeout():
    _require_guards()
    b = KS_BLOCK or ""
    assert "github.event_name == 'pull_request'" in b
    assert "timeout-minutes: 3" in b
    assert "actions/checkout" not in b


def test_ks_guard_exact_error_string_and_parsers():
    _require_guards()
    b = KS_BLOCK or ""
    assert REFL_ERROR_EXACT in b, "issue #392 mandates this exact error verbatim"
    assert "**why:**" in b and "**alternatives_rejected:**" in b
    assert "guard-exempt" in b, "admin escape hatch required by issue #392"


# --------------------------------------------------------------------------- #
# Behavioral matrix (real bash execution; issue #392 acceptance criteria)     #
# --------------------------------------------------------------------------- #


def _claim_script(h: _GuardHarness) -> str:
    block = CLAIM_BLOCK or ""
    script = _extract_run_script(block)
    if script is None:
        raise AssertionError("claim-guard run literal not extractable")
    return script


def _ks_script(h: _GuardHarness) -> str:
    block = KS_BLOCK or ""
    script = _extract_run_script(block)
    if script is None:
        raise AssertionError("knowledge-sharing-guard run literal not extractable")
    return script


def test_claim_guard_behavior_matrix():
    _require_guards()
    h = _GuardHarness()
    try:
        script = _claim_script(h)
        cases = [
            ("claim label passes", _claim_env(FX_CLAIMED), 0, None),
            (
                "bridge:queued label passes (4301d9a plane)",
                _claim_env(FX_BRIDGE_QUEUED),
                0,
                None,
            ),
            ("atomic-claim comment passes", _claim_env(FX_ATOMIC), 0, None),
            (
                "unclaimed fails with exact message",
                _claim_env(FX_UNCLAIMED),
                1,
                f"{CLAIM_ERROR_ISSUES_PREFIX}{FX_UNCLAIMED}){CLAIM_ERROR_TAIL}",
            ),
            (
                "gh lookup failure fails closed",
                _claim_env(FX_MISSING),
                1,
                f"{CLAIM_ERROR_ISSUES_PREFIX}{FX_MISSING}){CLAIM_ERROR_TAIL}",
            ),
            (
                "guard-exempt bypasses",
                _claim_env(FX_UNCLAIMED, labels="guard-exempt"),
                0,
                None,
            ),
            (
                "bot branch bypasses",
                _claim_env(FX_UNCLAIMED, head_ref="dependabot/npm_and_yarn/pkg-1.2.3"),
                0,
                None,
            ),
            # No issue ref: the guard echoes the literal #<num> template form.
            (
                "no issue reference fails closed",
                dict(
                    PR_TITLE="feat: nothing",
                    PR_BODY="no refs here",
                    PR_LABELS="",
                    HEAD_REF="agent/work-1",
                ),
                1,
                f"{CLAIM_ERROR_PREFIX}<num>.",
            ),
        ]
        for name, env, want, want_msg in cases:
            r = h.run(script, **env)
            assert r.returncode == want, (
                f"{name}: exit {r.returncode} != {want}; out={r.stdout[:200]!r}"
            )
            if want_msg:
                assert want_msg in r.stdout and CLAIM_ERROR_TAIL in r.stdout, (
                    f"{name}: exact issue-#392 error not emitted; out={r.stdout[:240]!r}"
                )
    finally:
        h.close()


def test_ks_guard_behavior_matrix():
    _require_guards()
    h = _GuardHarness()
    try:
        script = _ks_script(h)

        def body(section: str) -> str:
            return f"## Summary\n{section}"

        cases = [
            ("valid body passes", GOOD_BODY, 0, False),
            ("missing section fails", body("nothing here"), 1, True),
            (
                "empty why fails",
                "## Reflection Evidence (why + alternatives_rejected)\n- **why:**\n- **alternatives_rejected:**\n  - a\n",
                1,
                True,
            ),
            (
                "placeholder why fails",
                "## Reflection Evidence (why + alternatives_rejected)\n- **why:** <replace: rationale>\n- **alternatives_rejected:**\n  - real reason\n",
                1,
                True,
            ),
            (
                "inline alternatives passes",
                "## Reflection Evidence (why + alternatives_rejected)\n- **why:** because\n- **alternatives_rejected:** did it inline instead\n",
                0,
                False,
            ),
            (
                "empty alternatives fails",
                "## Reflection Evidence (why + alternatives_rejected)\n- **why:** because\n- **alternatives_rejected:**\n",
                1,
                True,
            ),
            (
                "placeholder alternatives fails",
                "## Reflection Evidence (why + alternatives_rejected)\n- **why:** because\n- **alternatives_rejected:**\n  - <replace: alternative approach 1, rejected because ...>\n",
                1,
                True,
            ),
        ]
        for name, pr_body, want, want_msg in cases:
            r = h.run(
                script, PR_BODY=pr_body, PR_LABELS="", HEAD_REF="contributor/issue-392"
            )
            assert r.returncode == want, (
                f"{name}: exit {r.returncode} != {want}; out={r.stdout[:200]!r}"
            )
            if want_msg:
                assert REFL_ERROR_EXACT in r.stdout, (
                    f"{name}: exact error not emitted; out={r.stdout[:240]!r}"
                )

        # escape hatches
        r = h.run(script, PR_BODY="empty", PR_LABELS="guard-exempt", HEAD_REF="agent/x")
        assert r.returncode == 0, "guard-exempt must bypass reflection check"
        r = h.run(script, PR_BODY="", PR_LABELS="", HEAD_REF="github-actions[bot]/auto")
        assert r.returncode == 0, "bot branch must bypass reflection check"
    finally:
        h.close()


def test_combined_claim_and_reflection_pass_together():
    # Issue #392 acceptance: claimed issue + valid reflection -> both guards pass.
    _require_guards()
    h = _GuardHarness()
    try:
        r1 = h.run(_claim_script(h), **_claim_env(FX_CLAIMED))
        r2 = h.run(
            _ks_script(h),
            PR_BODY=GOOD_BODY,
            PR_LABELS="",
            HEAD_REF="contributor/issue-392",
        )
        assert r1.returncode == 0 and r2.returncode == 0, (
            f"combined pass failed: claim={r1.returncode}, reflection={r2.returncode}"
        )
    finally:
        h.close()


def test_unfilled_template_body_fails_ks_guard():
    # Tier-4 dogfood: the template's own unfilled placeholders must be rejected.
    _require_guards()
    if not PR_TEMPLATE.is_file():
        _skip(".github/PULL_REQUEST_TEMPLATE.md not yet applied (WO #395 appendix C)")
    tpl = PR_TEMPLATE.read_text(encoding="utf-8")
    unfilled = re.sub(r"<!--.*?-->", "", tpl, flags=re.DOTALL)
    unfilled = re.sub(r"\n{3,}", "\n\n", unfilled).strip()
    h = _GuardHarness()
    try:
        r = h.run(
            _ks_script(h),
            PR_BODY=unfilled,
            PR_LABELS="",
            HEAD_REF="contributor/issue-392",
        )
        assert r.returncode == 1, (
            "unfilled template body must FAIL the guard (fail-closed)"
        )
        assert REFL_ERROR_EXACT in r.stdout
    finally:
        h.close()


# --------------------------------------------------------------------------- #
# Dual-mode runner (stdlib path; pytest discovers test_* above directly)      #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    fns = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
    failed = skipped = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS | {fn.__name__}")
        except _Skip as exc:
            skipped += 1
            print(f"  SKIP | {fn.__name__}: {exc}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL | {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — honest failure reporting
            failed += 1
            print(f"  ERROR | {fn.__name__}: {type(exc).__name__}: {exc}")
    passed = len(fns) - failed - skipped
    if skipped:
        print(f"{passed}/{len(fns)} tests passed ({skipped} skipped, guards pending)")
    else:
        print(f"{passed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
